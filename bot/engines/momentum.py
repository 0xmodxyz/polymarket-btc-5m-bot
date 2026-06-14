"""Momentum module — progressive buying as trend continues, with TP/SL/flip."""

from __future__ import annotations

import logging
import time

from bot.feeds import PriceFeed
from bot.executor import Executor

logger = logging.getLogger(__name__)

MIN_BTC_PCT = 0.02
FLIP_PCT = 0.03
PRICE_CAP = 0.75
TP_MULTIPLIER = 1.5
SL_CENTS = -0.10
SHARES = 5
FLIP_COOLDOWN = 2.0
ENTRY_COOLDOWN = 0.5
CVD_THRESHOLD = 500  # minimum |CVD| to confirm direction
LIMIT_RETRY_COOLDOWN = 5  # seconds to wait after limit error


class MomentumModule:
    def __init__(self, feed: PriceFeed, executor: Executor):
        self.feed = feed
        self.executor = executor
        self.in_position = False
        self.position_side: str | None = None
        self.entry_price = 0.0
        self.consecutive_buys = 0
        self.last_buy_time = 0.0
        self.last_flip_time = 0.0
        self._deadline = float("inf")
        self._buy_order_id: str | None = None
        self._buy_order_side: str | None = None
        self._sell_order_id: str | None = None
        self._last_poll = 0.0
        self._limit_error_until = 0.0  # cooldown after limit order size error
        self._hedged = False  # holds both sides → arbitrage handles
        self._hedge_order_id: str | None = None
        self._hedge_order_side: str | None = None

    def set_deadline(self, ts: float) -> None:
        self._deadline = ts

    async def tick(self) -> None:
        freeze = time.time() >= self._deadline - 30
        change = self.feed.btc_change_pct_3s
        if self._hedge_order_id:
            if time.time() - self._last_poll > 2.0:
                self._last_poll = time.time()
                await self._check_hedge_order()
            return
        # Poll pending orders (always active)
        if self._buy_order_id:
            if time.time() - self._last_poll > 2.0:
                self._last_poll = time.time()
                await self._check_buy_order()
            return
        if self._sell_order_id:
            if time.time() - self._last_poll > 2.0:
                self._last_poll = time.time()
                await self._check_sell_order()
            return
        # Manage existing positions (always active)
        if self.in_position:
            if self._hedged:
                return  # arbitrage handles paired position
            await self._manage(change)
            return
        # Last 30s quarantine — no new entries
        if freeze:
            return
        if abs(change) < MIN_BTC_PCT:
            return
        # CVD confirmation: BTC direction and CVD sign must match
        cvd = self.feed.cvd_value
        if change > 0 and cvd < -CVD_THRESHOLD:
            logger.info("CVD bearish (%.0f) — BTC up confirmed negative, skip Up", cvd)
            return
        if change < 0 and cvd > CVD_THRESHOLD:
            logger.info("CVD bullish (%.0f) — BTC down confirmed positive, skip Down", cvd)
            return
        side = "Up" if change > 0 else "Down"
        price = self.feed.up_price if side == "Up" else self.feed.down_price
        if price > PRICE_CAP or price <= 0.01:
            return
        await self._buy(side, price, change)

    async def _buy(self, side: str, price: float, change: float) -> None:
        if self.executor.budget_left() < price * SHARES:
            return
        if self.executor.simulation:
            await self._sim_buy(side, price, change)
        else:
            await self._live_buy(side, price, change)

    async def _sim_buy(self, side: str, price: float, change: float) -> None:
        await self.executor.buy(side, price, SHARES, "momentum")
        self._set_position(side, change, price)

    async def _live_buy(self, side: str, price: float, change: float) -> None:
        from bot.orders import async_get_best_ask, async_get_best_bid, async_place_limit_order
        from bot.markets import fetch_market
        from py_clob_client_v2.order_builder.constants import BUY
        # Limit error cooldown
        if time.time() < self._limit_error_until:
            return
        try:
            m = fetch_market()
            tok = m.up if side == "Up" else m.down
            ask = await async_get_best_ask(tok.token_id)
            bid = await async_get_best_bid(tok.token_id)
        except Exception as e:
            logger.warning("Ask check: %s", e)
            return
        # Spread filter — skip market buy if spread is too wide
        if ask - bid > 0.10:
            logger.info("Spread too wide (%.3f), using limit order", ask - bid)
        # Market buy if ask reasonable
        elif ask <= PRICE_CAP:
            await self.executor.buy(side, ask, SHARES, "momentum")
            self._set_position(side, change, ask)
            return
        # Limit buy at fair price
        limit_p = min(price, PRICE_CAP)
        if limit_p <= 0.01:
            return
        try:
            resp = await async_place_limit_order(self.executor.client, tok.token_id, BUY, limit_p, SHARES)
            oid = resp.get("orderID") or resp.get("id")
            if resp.get("status") == "matched":
                # LIMIT BUY response: takingAmount=shares, makingAmount=USD
                filled_s = int(float(resp.get("takingAmount", 0)))
                cost = float(resp.get("makingAmount", 0))
                if filled_s > 0:
                    fill_p = cost / filled_s
                    t = await self.executor.buy(side, fill_p, filled_s, "momentum", skip_clob_check=True)
                    if t:
                        self._set_position(side, change, fill_p)
                        await self._place_tp_sell(side, filled_s)
            elif oid:
                self._buy_order_id = oid
                self._buy_order_side = side
                logger.info("LIMIT BUY %s %.4f x %d", side, limit_p, SHARES)
        except Exception as e:
            e_msg = str(e)
            if "minimum" in e_msg.lower() and "size" in e_msg.lower():
                logger.warning("Limit size error (%s) — cooldown %ds", e_msg, LIMIT_RETRY_COOLDOWN)
                self._limit_error_until = time.time() + LIMIT_RETRY_COOLDOWN
            else:
                logger.warning("Limit buy: %s", e_msg)

    async def _check_buy_order(self) -> None:
        try:
            from bot.orders import async_get_order
            info = await async_get_order(self.executor.client, self._buy_order_id)
            if not info:
                self._buy_order_id = None
                return
            remaining = float(info.get("remainingSize", info.get("size", 0)))
            total = float(info.get("originalSize", info.get("size", 0)))
            if total > 0 and remaining < total:
                filled = int(total - remaining)
                fill_p = float(info.get("price", 0))
                if fill_p <= 0:
                    fill_p = float(info.get("avgPrice", 0.5))
                side = self._buy_order_side
                t = await self.executor.buy(side, fill_p, filled, "momentum", skip_clob_check=True)
                if t:
                    self._set_position(side, None, fill_p)
                    self._buy_order_id = None
                    await self._place_tp_sell(side, filled)
        except Exception as e:
            logger.debug("Check buy: %s", e)

    async def _place_tp_sell(self, side: str, shares: int) -> None:
        from bot.orders import async_place_limit_order
        from bot.markets import fetch_market
        from py_clob_client_v2.order_builder.constants import SELL
        avg = self.executor.avg_price(side)
        target = min(avg * TP_MULTIPLIER, 0.99)
        try:
            m = fetch_market()
            tok = m.up if side == "Up" else m.down
            resp = await async_place_limit_order(self.executor.client, tok.token_id, SELL, target, shares)
            if resp.get("status") == "matched":
                logger.info("TP SELL FILLED %dsh @ %.4f", shares, target)
                await self.executor.sell(side, target, shares, "tp")
                self._clear()
            else:
                oid = resp.get("orderID") or resp.get("id")
                if oid:
                    self._sell_order_id = oid
                    logger.info("LIMIT SELL %s %.4f x %d", side, target, shares)
        except Exception as e:
            logger.warning("TP sell: %s", e)

    async def _check_sell_order(self) -> None:
        try:
            from bot.orders import async_get_order
            info = await async_get_order(self.executor.client, self._sell_order_id)
            if not info:
                self._sell_order_id = None
                return
            remaining = float(info.get("remainingSize", info.get("size", 0)))
            total = float(info.get("originalSize", info.get("size", 0)))
            if total > 0 and remaining < total:
                sold = int(total - remaining)
                sale_p = float(info.get("price", 0))
                await self.executor.sell(self.position_side, sale_p, sold, "tp")
                self._sell_order_id = None
                self._clear()
        except Exception as e:
            logger.debug("Check sell: %s", e)

    async def _manage(self, change: float) -> None:
        if self._hedged:
            return
        cur = self.feed.up_price if self.position_side == "Up" else self.feed.down_price
        target = self.entry_price * TP_MULTIPLIER
        delta = cur - self.entry_price
        pnl_pct = (delta / self.entry_price) * 100.0 if self.entry_price > 0 else 0.0
        if cur >= target:
            logger.info("TP %s: +%.1f%% @ %.3f", self.position_side, pnl_pct, cur)
            if self.executor.simulation:
                await self.executor.sell(self.position_side, cur, self.executor.total_shares(self.position_side), "tp")
                self._clear()
            else:
                await self._place_tp_sell(self.position_side, self.executor.total_shares(self.position_side))
            return
        if delta <= SL_CENTS:
            logger.info("SL %s: %.1f%% @ %.3f", self.position_side, pnl_pct, cur)
            if not self.executor.simulation:
                from bot.orders import async_get_best_bid
                from bot.markets import fetch_market
                try:
                    m = fetch_market()
                    tok = m.up if self.position_side == "Up" else m.down
                    bid = await async_get_best_bid(tok.token_id)
                    if bid > cur * 0.5:
                        await self.executor.sell(self.position_side, bid, self.executor.total_shares(self.position_side), "sl")
                        self._clear()
                        return
                except Exception:
                    pass
                logger.warning("SL triggered but no buyer — holding")
                return
            await self.executor.sell(self.position_side, cur, self.executor.total_shares(self.position_side), "sl")
            self._clear()
            return
        now = time.time()
        if now - self.last_flip_time > FLIP_COOLDOWN:
            if change < -FLIP_PCT and self.position_side == "Up" and not self._hedged:
                await self._try_hedge("Down", self.feed.down_price, change)
                return
            if change > FLIP_PCT and self.position_side == "Down" and not self._hedged:
                await self._try_hedge("Up", self.feed.up_price, change)
                return
        if now - self.last_buy_time > ENTRY_COOLDOWN:
            trending = (change > MIN_BTC_PCT and self.position_side == "Up") or \
                       (change < -MIN_BTC_PCT and self.position_side == "Down")
            if trending:
                cvd = self.feed.cvd_value
                if trending and self.position_side == "Up" and cvd < -CVD_THRESHOLD:
                    logger.info("Progressive Up blocked — CVD bearish (%.0f)", cvd)
                    return
                if trending and self.position_side == "Down" and cvd > CVD_THRESHOLD:
                    logger.info("Progressive Down blocked — CVD bullish (%.0f)", cvd)
                    return
                price = self.feed.up_price if self.position_side == "Up" else self.feed.down_price
                if price <= PRICE_CAP and price > 0.01:
                    await self._buy(self.position_side, price, change)

    async def _try_hedge(self, new_side: str, price: float, change: float) -> None:
        """Buy opposite side without selling current — creates a hedge pair."""
        if self._hedged:
            return
        # Already have opposite side?
        if self.executor.total_shares(new_side) >= SHARES:
            self._hedged = True
            logger.info("HEDGE: already have %s %dsh, marked hedged", new_side, self.executor.total_shares(new_side))
            return
        if price <= 0.01 or price > PRICE_CAP:
            return
        if self.executor.budget_left() < price * SHARES:
            return
        logger.info("HEDGE: %s + %s @ %.3f x %d", self.position_side, new_side, price, SHARES)
        if self.executor.simulation:
            t = await self.executor.buy(new_side, price, SHARES, "hedge")
            if t:
                self._hedged = True
        else:
            await self._live_hedge_buy(new_side, price, change)
        self.last_flip_time = time.time()

    async def _live_hedge_buy(self, side: str, price: float, change: float) -> None:
        """Place hedge limit buy — don't change momentum module state."""
        from bot.orders import async_place_limit_order
        from bot.markets import fetch_market
        from py_clob_client_v2.order_builder.constants import BUY
        if time.time() < self._limit_error_until:
            return
        m = fetch_market()
        tok = m.up if side == "Up" else m.down
        limit_p = min(price, PRICE_CAP)
        if limit_p <= 0.01:
            return
        try:
            resp = await async_place_limit_order(self.executor.client, tok.token_id, BUY, limit_p, SHARES)
            if resp.get("status") == "matched":
                filled_s = int(float(resp.get("takingAmount", 0)))
                cost = float(resp.get("makingAmount", 0))
                if filled_s > 0:
                    fill_p = cost / filled_s
                    t = await self.executor.buy(side, fill_p, filled_s, "hedge", skip_clob_check=True)
                    if t:
                        self._hedged = True
                        logger.info("HEDGE FILLED %s %dsh @ %.4f", side, filled_s, fill_p)
            elif resp.get("orderID") or resp.get("id"):
                oid = resp.get("orderID") or resp.get("id")
                self._hedge_order_id = oid
                self._hedge_order_side = side
                logger.info("HEDGE LIMIT %s %.4f x %d (pending)", side, limit_p, SHARES)
        except Exception as e:
            e_msg = str(e)
            if "minimum" in e_msg.lower():
                self._limit_error_until = time.time() + LIMIT_RETRY_COOLDOWN
            logger.warning("Hedge limit buy: %s", e_msg)

    async def _check_hedge_order(self) -> None:
        """Poll pending hedge limit order fill."""
        try:
            from bot.orders import async_get_order
            info = await async_get_order(self.executor.client, self._hedge_order_id)
            if not info:
                self._hedge_order_id = None
                return
            remaining = float(info.get("remainingSize", info.get("size", 0)))
            total = float(info.get("originalSize", info.get("size", 0)))
            if total > 0 and remaining < total:
                filled = int(total - remaining)
                fill_p = float(info.get("price", 0.5))
                side = self._hedge_order_side
                t = await self.executor.buy(side, fill_p, filled, "hedge", skip_clob_check=True)
                if t:
                    self._hedged = True
                    self._hedge_order_id = None
                    self._hedge_order_side = None
                    logger.info("HEDGE FILLED %s %dsh @ %.4f", side, filled, fill_p)
        except Exception as e:
            logger.debug("Check hedge: %s", e)

    def _set_position(self, side: str, change: float | None, price: float) -> None:
        self.in_position = True
        self.position_side = side
        self.entry_price = self.executor.avg_price(side)
        self.consecutive_buys += 1
        self.last_buy_time = time.time()
        logger.info("MOMENTUM %s +%dsh @ %.3f (avg=%.3f, #%d)",
                    side, SHARES, price, self.entry_price, self.consecutive_buys)

    def clean_up(self) -> None:
        for oid in [self._buy_order_id, self._sell_order_id, self._hedge_order_id]:
            if oid:
                try:
                    self.executor.client.cancel_order(oid)
                except Exception:
                    pass
        self._buy_order_id = None
        self._buy_order_side = None
        self._sell_order_id = None
        self._hedge_order_id = None
        self._hedge_order_side = None
        self.consecutive_buys = 0
        self._hedged = False
        self._limit_error_until = 0.0

    def _clear(self) -> None:
        self.in_position = False
        self.position_side = None
        self.entry_price = 0.0
        self.consecutive_buys = 0
        self._hedged = False
        self._hedge_order_id = None
        self._hedge_order_side = None
