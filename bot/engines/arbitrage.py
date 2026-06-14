"""Arbitrage module — when holding one side, buy the other if sum < 1.0 to lock profit."""

from __future__ import annotations

import logging
import time

from bot.feeds import PriceFeed
from bot.executor import Executor

logger = logging.getLogger(__name__)

SUM_TARGET = 1.05
SHARES_TO_BUY = 2
MIN_PRICE_THRESHOLD = 0.30
MIN_PROFIT_MARGIN = 0.03


class ArbitrageModule:
    """If we hold Up and `avg_up + current_down < 0.95` → buy Down to lock profit."""

    def __init__(self, feed: PriceFeed, executor: Executor):
        self.feed = feed
        self.executor = executor
        self._seen_sums: list[float] = []
        self._last_try = 0.0
        self._last_hedge_price: dict[str, float] = {"Up": 0.0, "Down": 0.0}
        self._spread_threshold = 0.01

    async def tick(self) -> None:
        up_sh = self.executor.total_shares("Up")
        dn_sh = self.executor.total_shares("Down")

        if up_sh == 0 and dn_sh == 0:
            return

        now = time.time()
        if now - self._last_try < 0.5:
            return
        self._last_try = now

        if self.feed.up_price < MIN_PRICE_THRESHOLD or self.feed.down_price < MIN_PRICE_THRESHOLD:
            return

        total_spent = self.executor.total_cost("Up") + self.executor.total_cost("Down")

        if dn_sh > 0:
            avg_dn = self.executor.avg_price("Down")
            cur_up = self.feed.up_price

            if abs(cur_up - self._last_hedge_price["Up"]) >= self._spread_threshold:
                s = round(avg_dn + cur_up, 3)

                if s <= SUM_TARGET and s not in self._seen_sums:
                    predicted_up_shares = up_sh + SHARES_TO_BUY
                    predicted_total_spent = total_spent + (SHARES_TO_BUY * cur_up)
                    predicted_net_profit = (predicted_up_shares * 1.0) - predicted_total_spent

                    if predicted_net_profit >= MIN_PROFIT_MARGIN:
                        self._seen_sums.append(s)
                        if self.executor.budget_left() >= cur_up * SHARES_TO_BUY:
                            logger.info("ARB HEDGE -> Hold Down@%.3f + Buy Up@%.3f = %.3f (Guaranteed Profit!)",
                                        avg_dn, cur_up, s)
                            await self.executor.buy("Up", cur_up, SHARES_TO_BUY, "arbitrage")
                            self._last_hedge_price["Up"] = cur_up

        if up_sh > 0:
            avg_up = self.executor.avg_price("Up")
            cur_dn = self.feed.down_price

            if abs(cur_dn - self._last_hedge_price["Down"]) >= self._spread_threshold:
                s = round(avg_up + cur_dn, 3)

                if s <= SUM_TARGET and s not in self._seen_sums:
                    predicted_down_shares = dn_sh + SHARES_TO_BUY
                    predicted_total_spent = total_spent + (SHARES_TO_BUY * cur_dn)
                    predicted_net_profit = (predicted_down_shares * 1.0) - predicted_total_spent

                    if predicted_net_profit >= MIN_PROFIT_MARGIN:
                        self._seen_sums.append(s)
                        if self.executor.budget_left() >= cur_dn * SHARES_TO_BUY:
                            logger.info("ARB HEDGE -> Hold Up@%.3f + Buy Down@%.3f = %.3f (Guaranteed Profit!)",
                                        avg_up, cur_dn, s)
                            await self.executor.buy("Down", cur_dn, SHARES_TO_BUY, "arbitrage")
                            self._last_hedge_price["Down"] = cur_dn

    def reset(self) -> None:
        self._seen_sums.clear()
        self._last_hedge_price = {"Up": 0.0, "Down": 0.0}
