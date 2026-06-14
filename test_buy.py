#!/usr/bin/env python3
"""Test: $1 FAK limit buy on Polymarket CLOB."""

import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from bot.config import load_settings
from bot.client import build_deposit_wallet_client
from bot.markets import fetch_market, seconds_until_window_end
from bot.orders import async_place_limit_buy_fak
from bot.markets import OutcomeToken

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("test_buy")


async def main():
    load_settings()
    settings = load_settings()

    market = fetch_market()
    logger.info("Market: %s", market.title)
    logger.info("Window ends in %.0fs", seconds_until_window_end())

    client = build_deposit_wallet_client(settings)
    logger.info("CLOB client ready")

    # Prompt user for side and price
    side = input("Side (Up/Down): ").strip().lower()
    if side not in ("up", "down"):
        logger.error("Invalid side")
        return 1
    side_cap = side.capitalize()

    price_str = input(f"Price for {side_cap} (e.g. 0.40): ").strip()
    try:
        price = float(price_str)
    except ValueError:
        logger.error("Invalid price")
        return 1

    token = market.up if side_cap == "Up" else market.down
    token_with_price = OutcomeToken(
        outcome=token.outcome,
        token_id=token.token_id,
        price=price,
    )

    # Calculate shares worth $1
    shares = max(1, int(1.0 / price))
    cost = round(shares * price, 2)

    logger.info(f"Attempting: {side_cap} {shares}sh @ ${price:.4f} = ${cost:.2f}")

    try:
        resp = await async_place_limit_buy_fak(client, token_with_price, price, shares)
        status = resp.get("status", "") if resp else ""
        if status == "matched":
            logger.info("✓ FILLED: %d %s @ $%.4f = $%.2f", shares, side_cap, price, cost)
        else:
            logger.info("✗ NOT FILLED: no seller at $%.4f", price)
    except Exception as e:
        logger.error("Order failed: %s", e)

    logger.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
