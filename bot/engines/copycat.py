"""Copy-trade JetFadil's Polymarket orders for current window."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from bot.executor import Executor
from bot.feeds import PriceFeed

logger = logging.getLogger(__name__)

JETFADIL = "0xe0229e10a858860218b6132f4234602c47bd6603"
ORDER_USD = 1.50
CLOB_HOST = "https://clob.polymarket.com"
ORDER_ENDPOINT = "/data/orders"


class CopycatModule:
    def __init__(self, feed: PriceFeed, executor: Executor):
        self.feed = feed
        self.executor = executor
        self.client = executor.client
        self._seen: set[str] = set()
        self._up_token = ""
        self._down_token = ""
        self._last_poll = 0.0

    def set_tokens(self, up_token_id: str, down_token_id: str) -> None:
        self._up_token = up_token_id
        self._down_token = down_token_id

    async def tick(self) -> None:
        if not self._up_token:
            return

        if not self.client:
            await self._sim_tick()
            return

        now = time.time()
        if now - self._last_poll < 0.2:
            return
        self._last_poll = now

        try:
            raw = await self._fetch_jetfadil_orders()
            data = raw.get("data") if isinstance(raw, dict) else raw
            if not data:
                return
            for order in data:
                await self._try_copy(order)
        except Exception as e:
            logger.warning("copycat poll: %s", e)

    async def _fetch_jetfadil_orders(self) -> Any:
        from py_clob_client_v2.endpoints import ORDERS

        headers = self.client._l2_headers("GET", ORDERS)
        params = {"maker_address": JETFADIL, "limit": 5}
        return await asyncio.to_thread(
            lambda: self.client._get(f"{CLOB_HOST}{ORDERS}", headers=headers, params=params)
        )

    async def _try_copy(self, order: dict[str, Any]) -> None:
        oid = order.get("id") or order.get("orderID") or ""
        if not oid or oid in self._seen:
            return
        raw_asset = order.get("asset_id") or order.get("token_id") or ""
        if not raw_asset:
            return

        side = None
        if raw_asset == self._up_token:
            side = "Up"
        elif raw_asset == self._down_token:
            side = "Down"
        else:
            return

        if self.executor.budget_left() < ORDER_USD:
            return

        price = self.feed.up_price if side == "Up" else self.feed.down_price
        if price <= 0:
            return

        ok = await self._market_buy(side, price)
        if ok:
            self._seen.add(oid)
            logger.info("COPY JetFadil %s $%.2f", side, ORDER_USD)

    async def _market_buy(self, side: str, gamma_price: float) -> bool:
        if gamma_price < 0.02 or self.executor.budget_left() < ORDER_USD:
            return False

        if self.executor.simulation:
            shares = max(5, int(ORDER_USD / gamma_price))
            t = await self.executor.buy(side, gamma_price * 0.88, shares, "copycat")
            return t is not None

        try:
            from bot.markets import fetch_market
            from bot.orders import async_place_market_buy

            m = fetch_market()
            tok = m.up if side == "Up" else m.down
            resp = await async_place_market_buy(self.executor.client, tok, ORDER_USD)
            if resp is None:
                return False
            has_fill = (
                resp.get("orderID") or resp.get("id")
                or resp.get("makingAmount") or resp.get("makerAmount")
            )
            if not has_fill:
                return False

            estimate = max(5, int(ORDER_USD / gamma_price))
            t = await self.executor.buy(side, gamma_price, estimate, "copycat",
                                        skip_clob_check=True, skip_live=True)
            if t is None:
                return False

            raw_c = resp.get("makerAmount") or resp.get("makingAmount") or ""
            raw_s = resp.get("takerAmount") or resp.get("takingAmount") or ""
            if raw_c and raw_s:
                try:
                    self.executor.record_fill(float(raw_c), int(float(raw_s)))
                except (ValueError, TypeError):
                    pass
            return True
        except Exception as e:
            logger.warning("copycat buy %s: %s", side, e)
        return False

    #
    # Simulation mode — generate mock JetFadil orders
    #
    async def _sim_tick(self) -> None:
        now = time.time()
        if not hasattr(self, "_sim_orders"):
            self._sim_orders = [
                {"id": "sim_pair_up",  "asset_id": self._up_token,   "_at": now + 0.5},
                {"id": "sim_pair_dn",  "asset_id": self._down_token, "_at": now + 0.5},
                {"id": "sim_sig",      "asset_id": self._up_token,   "_at": now + 60},
            ]
        remaining = []
        for order in self._sim_orders:
            if order["_at"] <= now:
                if order["id"] not in self._seen:
                    await self._try_copy(order)
            else:
                remaining.append(order)
        self._sim_orders = remaining

    def clean_up(self) -> None:
        pass
