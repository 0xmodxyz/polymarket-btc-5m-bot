"""Trade executor with buy/sell, chunking, and real CLOB support."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MIN_SHARES = 1


@dataclass
class SimTrade:
    side: str
    price: float
    shares: int
    cost: float
    timestamp: float
    module: str
    realized_pnl: float = 0.0


class Executor:
    def __init__(self, simulation: bool = True, max_budget: float = 50.0):
        self.simulation = simulation
        self.trades: list[SimTrade] = []
        self.positions: dict[str, list[SimTrade]] = {"Up": [], "Down": []}
        self.closed_positions: list[SimTrade] = []
        self.client = None
        self.max_budget = max_budget
        self._budget_spent = 0.0

        self.initial_budget = max_budget
        self.current_cash = max_budget

    @property
    def budget_spent(self) -> float:
        return self._budget_spent

    def set_client(self, client) -> None:
        self.client = client

    def reset_window(self) -> None:
        self.positions = {"Up": [], "Down": []}
        self._budget_spent = 0.0

    def _max_affordable(self, price: float) -> int:
        if self.current_cash <= 0:
            return 0
        return min(int(self.current_cash / price), 100)

    async def buy(self, side: str, price: float, shares: int, module: str, skip_live: bool = False) -> SimTrade | None:
        shares = min(shares, self._max_affordable(price))
        if shares < MIN_SHARES:
            return None

        cost = shares * price
        if cost > self.current_cash:
            shares = int(self.current_cash / price)
            if shares < MIN_SHARES:
                return None
            cost = shares * price

        t = SimTrade(side=side, price=price, shares=shares, cost=cost,
                     timestamp=time.time(), module=module)
        self.trades.append(t)
        self.positions[side].append(t)

        self._budget_spent += cost
        self.current_cash -= cost

        logger.info("BUY %s %dsh @ %.3f = $%.2f [%s] | Kalan Nakit: $%.2f",
                    side, shares, price, cost, module, self.current_cash)

        if not self.simulation and self.client and not skip_live:
            ok = await self._real_buy(side, price, shares)
            if not ok:
                self._rollback_last_buy(side)
                return None

        return t

    async def sell(self, side: str, price: float, shares: int, module: str) -> SimTrade | None:
        available = self.total_shares(side)
        shares = min(shares, available)
        if shares < MIN_SHARES:
            return None

        proceeds = shares * price
        cost_basis = self._cost_of_oldest(side, shares)
        realized = proceeds - cost_basis

        t = SimTrade(side=f"SOLD_{side}", price=price, shares=shares,
                     cost=proceeds, timestamp=time.time(), module=module,
                     realized_pnl=round(realized, 2))
        self.trades.append(t)
        self.closed_positions.append(t)
        self._remove_shares(side, shares)

        self._budget_spent -= cost_basis
        self.current_cash += proceeds

        logger.info("SELL %s %dsh @ %.3f = $%.2f | PnL: $%.2f [%s]",
                    side, shares, price, proceeds, realized, module)

        if not self.simulation and self.client:
            await self._real_sell(side, price, shares)

        return t

    def _cost_of_oldest(self, side: str, shares: int) -> float:
        taken = 0
        cost = 0.0
        for t in self.positions[side]:
            take = min(t.shares, shares - taken)
            cost += take * t.price
            taken += take
            if taken >= shares:
                break
        return cost

    def _remove_shares(self, side: str, shares: int) -> None:
        remaining = shares
        new_list = []
        for t in self.positions[side]:
            if remaining <= 0:
                new_list.append(t)
            elif t.shares <= remaining:
                remaining -= t.shares
            else:
                leftover = t.shares - remaining
                new_list.append(SimTrade(side=t.side, price=t.price, shares=leftover,
                                         cost=t.cost * leftover / t.shares,
                                         timestamp=t.timestamp, module=t.module))
                remaining = 0
        self.positions[side] = new_list

    async def _real_buy(self, side: str, price: float, shares: int) -> bool:
        try:
            from bot.markets import fetch_market
            from bot.orders import async_place_limit_buy_fak
            from bot.markets import OutcomeToken

            market = fetch_market()
            token = market.up if side == "Up" else market.down
            token_with_price = OutcomeToken(
                outcome=token.outcome,
                token_id=token.token_id,
                price=price,
            )

            resp = await async_place_limit_buy_fak(self.client, token_with_price, price, shares)
            logger.info("FAK ORDER result: %s", resp)

            status = resp.get("status", "") if resp else ""
            if status == "matched" and self.trades:
                last = self.trades[-1]
                last.shares = shares
                last.cost = round(shares * price, 2)
                last.price = price
                logger.info("FAK FILL: %d shares @ $%.4f = $%.2f",
                            shares, price, last.cost)
                return True
            else:
                logger.info("FAK not matched (no seller at %.4f) — skip", price)
                return False
        except Exception as exc:
            logger.error("FAK order failed: %s", exc)
            return False

    async def _real_sell(self, side: str, price: float, shares: int) -> None:
        try:
            from bot.markets import fetch_market
            from bot.orders import async_place_market_sell, async_get_best_bid

            market = fetch_market()
            token = market.up if side == "Up" else market.down

            try:
                best_bid = await async_get_best_bid(token.token_id)
                if best_bid < price * 0.8:
                    logger.warning("CLOB bid too low (%.4f vs target %.4f), holding", best_bid, price)
                    return
            except Exception:
                logger.warning("No bids on CLOB, holding position")
                return

            amount_usd = shares * price
            resp = await async_place_market_sell(self.client, token, amount_usd)
            logger.info("REAL SELL placed: %s", resp)
        except Exception as exc:
            logger.error("Real sell failed: %s", exc)

    async def limit_buy(self, side: str, price: float, shares: int, module: str) -> str | None:
        cost = shares * price
        if cost > self.current_cash:
            logger.warning("Insufficient budget for limit order.")
            return None

        logger.info("LIMIT BUY ORDER: %s %dsh @ %.3f = $%.2f [%s]", side, shares, price, cost, module)

        if not self.simulation and self.client:
            order_id = await self._real_limit_buy(side, price, shares)
            return order_id

        t = SimTrade(side=side, price=price, shares=shares, cost=cost,
                     timestamp=time.time(), module=module)
        self.trades.append(t)
        self.positions[side].append(t)

        self._budget_spent += cost
        self.current_cash -= cost

        logger.info("SIM FILL: %s limit order matched virtually. | Remaining Cash: $%.2f", side, self.current_cash)
        return f"sim_order_id_{int(time.time() * 1000)}"

    async def _real_limit_buy(self, side: str, price: float, shares: int) -> str | None:
        try:
            from bot.markets import fetch_market
            from bot.orders import async_place_limit_buy_shares
            from bot.markets import OutcomeToken

            market = fetch_market()
            token = market.up if side == "Up" else market.down
            token_with_price = OutcomeToken(
                outcome=token.outcome,
                token_id=token.token_id,
                price=price,
            )

            resp = await async_place_limit_buy_shares(self.client, token_with_price, price, shares)
            return resp.get("orderID")
        except Exception as exc:
            logger.error("Real limit order failed: %s", exc)
            return None

    def _rollback_last_buy(self, side: str) -> None:
        if not self.trades:
            return
        last = self.trades.pop()
        self._budget_spent -= last.cost
        self.current_cash += last.cost
        pos = self.positions.get(side, [])
        if pos and pos[-1] is last:
            pos.pop()

    def redeem(self, up_price: float, down_price: float) -> float:
        resolved = False
        winner = ""
        if up_price >= 0.99 and down_price <= 0.01:
            winner = "Up"
            resolved = True
        elif down_price >= 0.99 and up_price <= 0.01:
            winner = "Down"
            resolved = True

        if not resolved:
            return 0.0

        if self.total_shares("Up") == 0 and self.total_shares("Down") == 0:
            return 0.0

        total_redeemed = 0.0
        total_window_cost = 0.0

        logger.info("==================================================")
        logger.info("       MATURITY SETTLEMENT")
        logger.info("==================================================")

        for side in ["Up", "Down"]:
            sh = self.total_shares(side)
            cost = self.total_cost(side)
            total_window_cost += cost

            if sh == 0:
                continue

            if side == winner:
                value = sh * 1.0
                total_redeemed += value
                logger.info("REDEEM %s %dsh -> $%.2f (cost $%.2f, pnl $%.2f)", side, sh, value, cost, value - cost)
            else:
                logger.info("REDEEM %s %dsh -> $0.00 (lost, cost $%.2f)", side, sh, cost)

        self.current_cash += total_redeemed

        net_pnl = total_redeemed - total_window_cost
        self.closed_positions.append(SimTrade(
            side=f"REDEEM_{winner}", price=1.0, shares=int(total_redeemed),
            cost=total_window_cost, timestamp=time.time(),
            module="Redeem", realized_pnl=round(net_pnl, 2),
        ))

        logger.info("==================================================")
        logger.info("              FINAL PORTFOLIO SUMMARY             ")
        logger.info("==================================================")
        logger.info("  Total Spent Cost   : $%.2f", total_window_cost)
        logger.info("  Settlement Payout  : $%.2f", total_redeemed)
        logger.info("  Net P/L            : %+.2f", net_pnl)
        logger.info("  New Balance        : $%.2f", self.current_cash)
        logger.info("==================================================")

        self.reset_window()
        return total_redeemed

    def total_shares(self, side: str) -> int:
        return sum(t.shares for t in self.positions[side])

    def total_cost(self, side: str) -> float:
        return sum(t.cost for t in self.positions[side])

    def avg_price(self, side: str) -> float:
        s = self.total_shares(side)
        return self.total_cost(side) / s if s > 0 else 0.0

    def total_realized_pnl(self) -> float:
        return sum(t.realized_pnl for t in self.closed_positions)

    def budget_left(self) -> float:
        return self.current_cash
