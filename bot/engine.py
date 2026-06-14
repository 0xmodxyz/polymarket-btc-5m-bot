"""Main async engine — runs feeds + modules concurrently per window."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import requests  # safe to use sync requests inside asyncio.to_thread

from bot.client import build_deposit_wallet_client
from bot.config import load_settings
from bot.engines.sniper import SniperModule
from bot.executor import Executor
from bot.feeds import BinanceWebSocket, ClobBookPoller, CoinbaseWebSocket, GammaPoller, PriceFeed, RtdsWebSocket
from bot.markets import fetch_market, seconds_until_window_end

logger = logging.getLogger(__name__)

FORCE_EXIT_S = 3


class Engine:
    def __init__(self, simulation: bool = True, budget: float = 50.0):
        self.simulation = simulation
        self.feed = PriceFeed()
        self.executor = Executor(simulation=simulation, max_budget=budget)
        if not simulation:
            try:
                settings = load_settings()
                client = build_deposit_wallet_client(settings)
                self.executor.set_client(client)
                logger.info("CLOB client ready for live trading")
            except Exception as exc:
                logger.error("Failed to build CLOB client: %s — falling back to simulation", exc)
                self.simulation = True
                self.executor.simulation = True
        self.rtds_ws = RtdsWebSocket(self.feed)
        self.binance_ws = BinanceWebSocket(self.feed)
        self.coinbase_ws = CoinbaseWebSocket(self.feed)
        self.gamma: GammaPoller | None = None
        self.sniper: SniperModule | None = None
        self._cycle = 0
        self._last_slug: str | None = None
        self._feed_tasks: list[asyncio.Task] = []

    async def _start_feeds(self) -> None:
        """Start persistent price feeds (RTDS/Binance/Coinbase) as background tasks."""
        if self._feed_tasks:
            return
        logger.info("Starting persistent price feeds...")
        self._feed_tasks = [
            asyncio.create_task(self.rtds_ws.start(), name="rtds"),
            asyncio.create_task(self.binance_ws.start(), name="binance"),
            asyncio.create_task(self.coinbase_ws.start(), name="coinbase"),
        ]

    async def _stop_feeds(self) -> None:
        for t in self._feed_tasks:
            t.cancel()
        self._feed_tasks = []

    async def prewarm(self) -> None:
        """Ensure price feeds are running ~10s before window opens."""
        if not self._feed_tasks:
            if self.simulation:
                self._feed_tasks = [asyncio.create_task(self.binance_ws.start(), name="binance")]
            else:
                await self._start_feeds()
            await asyncio.sleep(2)

    async def run_window(self) -> None:
        self._cycle += 1
        market = fetch_market()
        window_secs = seconds_until_window_end()
        slug = market.slug

        logger.info("=" * 55)
        logger.info("WINDOW %d: %s", self._cycle, market.title)
        logger.info("Ends in %.0fs | Budget: $%.2f/$%.2f | Open: U=%d D=%d",
                    window_secs, self.executor.budget_spent, self.executor.max_budget,
                    self.executor.total_shares("Up"), self.executor.total_shares("Down"))
        logger.info("=" * 55)

        if window_secs < 10:
            logger.warning("Window too short, skip.")
            return

        logger.info("Waiting for SOL price feed (RTDS/Binance/Coinbase)...")
        start_wait = time.time()
        while not self.feed.is_ready and time.time() - start_wait < 5.0:
            await asyncio.sleep(0.2)
        if not self.feed.is_ready:
            logger.warning("No SOL price after 5s — trading with caution")
        else:
            logger.info("Feed ready via %s (SOL=$%.2f)", self.feed.price_source, self.feed.price)

        self.feed._market_ended = False
        self.feed.cvd_value = 0.0
        self.feed._window_start_price = self.feed.price

        # Check if previous window resolved
        if self._last_slug:
            try:
                await asyncio.to_thread(self._try_redeem, self._last_slug)
            except Exception:
                pass

        # Pre-warm token metadata cache (tick_size, neg_risk)
        try:
            from bot.orders import cache_token_meta
            cache_token_meta(market.up.token_id)
            cache_token_meta(market.down.token_id)
        except Exception:
            pass

        self.gamma = GammaPoller(self.feed, slug)

        # Initialize Sniper module
        self.sniper = SniperModule(self.feed, self.executor)
        self.sniper.set_tokens(market.up.token_id, market.down.token_id)
        self.clob_book = ClobBookPoller(self.feed, [market.up.token_id, market.down.token_id])

        # Start persistent feeds on first call
        if not self._feed_tasks:
            if self.simulation:
                # Simulation uses only Binance WS (free, real SOL price)
                self._feed_tasks = [asyncio.create_task(self.binance_ws.start(), name="binance")]
            else:
                await self._start_feeds()
            await asyncio.sleep(2)

        win_deadline = time.time() + window_secs - FORCE_EXIT_S

        window_tasks = [
            asyncio.create_task(self.gamma.start(poll_s=0.2), name="gamma"),
            asyncio.create_task(self.clob_book.start(poll_s=1.0), name="clob_book"),
            asyncio.create_task(self._module_loop(win_deadline), name="modules"),
        ]

        try:
            await asyncio.wait([window_tasks[-1]], timeout=window_secs + 10)
        except asyncio.TimeoutError:
            pass
        finally:
            for t in window_tasks:
                t.cancel()
            await asyncio.sleep(0.1)

        # Clear Sniper lock when window ends
        if self.sniper:
            self.sniper.clean_up()

        # Log window-end SOL change and theoretical PnL
        up_sh = self.executor.total_shares("Up")
        dn_sh = self.executor.total_shares("Down")
        if up_sh > 0 or dn_sh > 0:
            start_price = getattr(self.feed, "_window_start_price", 0)
            end_price = self.feed.price
            if start_price > 0 and end_price > 0:
                pct = ((end_price - start_price) / start_price) * 100
                winner = "Up" if end_price >= start_price else "Down"
                up_cost = self.executor.total_cost("Up")
                dn_cost = self.executor.total_cost("Down")
                up_val = up_sh * 1.0 if winner == "Up" else 0.0
                dn_val = dn_sh * 1.0 if winner == "Down" else 0.0
                theo_pnl = (up_val + dn_val) - (up_cost + dn_cost)
                logger.info("Window SOL: $%.2f->$%.2f (%.2f%%) Winner=%s | Theo PnL: $%.2f",
                            start_price, end_price, pct, winner, theo_pnl)

        # Save slug on window close and try redeem
        self._last_slug = slug
        try:
            await asyncio.to_thread(self._try_redeem, slug)
        except Exception:
            pass

        self._window_summary()

    def _try_redeem(self, slug: str) -> None:
        """Check if held positions for a given slug can be redeemed."""
        if not self.executor.total_shares("Up") and not self.executor.total_shares("Down"):
            return

        from requests.adapters import HTTPAdapter, Retry
        sess = requests.Session()
        sess.mount("https://", HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.3, status_forcelist=[429, 500, 502])))

        try:
            r = sess.get(
                "https://gamma-api.polymarket.com/events",
                params={"slug": slug}, timeout=10,
            )
            events = r.json()
            if not events:
                return
            m = events[0].get("markets", [{}])[0]
            raw = m.get("outcomePrices") or "[]"
            if isinstance(raw, str):
                raw = json.loads(raw)
            if len(raw) < 2:
                return
            up_p, down_p = float(raw[0]), float(raw[1])
            if up_p < 0.99 and down_p < 0.99:
                return  # not resolved
            total = self.executor.redeem(up_p, down_p)
            if total > 0:
                logger.info("Redeemed $%.2f from resolved market %s", total, slug)
        except Exception:
            return

    async def _module_loop(self, deadline: float) -> None:
        if self.feed.price > 0 and self.feed._window_start_price == 0:
            self.feed._window_start_price = self.feed.price

        while time.time() < deadline:
            try:
                if self.sniper:
                    self.sniper.ends_in = int(deadline - time.time())
                    await self.sniper.tick()
            except Exception as e:
                logger.exception("Module tick error: %s", e)

            # 120s safety barrier — disabled (fixed-share mode)

            await asyncio.sleep(0.002)

        logger.info("Window deadline reached.")

    def _window_summary(self) -> None:
        tr = self.executor.trades
        if not tr:
            logger.info("No trades this window.")
            return

        up_sh = self.executor.total_shares("Up")
        dn_sh = self.executor.total_shares("Down")
        used = self.executor.budget_spent
        pnl = self.executor.total_realized_pnl()
        logger.info("--- WINDOW %d: %d trades | Realized PnL: $%.2f ---",
                    self._cycle, len(tr), pnl)
        logger.info("Open: Up=%dsh Down=%dsh | Budget used: $%.2f/$%.2f",
                    up_sh, dn_sh, used, self.executor.max_budget)

        pairs = min(up_sh, dn_sh)
        if pairs > 0:
            locked = (1.0 - self.executor.avg_price("Up") - self.executor.avg_price("Down")) * pairs
            logger.info("Arbitrage pairs: %d | Potential locked profit: $%.2f", pairs, max(0, locked))

        for t in tr[-3:]:
            if "SOLD" in t.side:
                logger.info("  %s %dsh @ %.3f (pnl=$%.2f)", t.module, t.shares, t.price, t.realized_pnl)
            else:
                logger.info("  %s %s %dsh @ %.3f ($%.2f)", t.module, t.side, t.shares, t.price, t.cost)

    def final_summary(self) -> str:
        tr = len(self.executor.trades)
        pnl = self.executor.total_realized_pnl()
        up_sh = self.executor.total_shares("Up")
        dn_sh = self.executor.total_shares("Down")
        lines = [
            "=" * 50,
            "  FINAL PORTFOLIO SUMMARY",
            "=" * 50,
            f"  Total trades:     {tr}",
            f"  Realized PnL:     ${pnl:.2f}",
            f"  Open Up:          {up_sh} shares (cost ${self.executor.total_cost('Up'):.2f})",
            f"  Open Down:        {dn_sh} shares (cost ${self.executor.total_cost('Down'):.2f})",
            f"  Budget left:      ${self.executor.budget_left():.2f}",
        ]
        pairs = min(up_sh, dn_sh)
        if pairs > 0:
            u_avg = self.executor.avg_price("Up")
            d_avg = self.executor.avg_price("Down")
            locked = (1.0 - u_avg - d_avg) * pairs
            lines.append(f"  Arbitrage pairs:  {pairs} (locked profit: ${max(0, locked):.2f})")
        lines.append("=" * 50)
        return "\n".join(lines)
