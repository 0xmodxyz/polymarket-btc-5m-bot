#!/usr/bin/env python3
"""Verify API auth, balance, and place a small test market buy (~$1)."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from py_clob_client_v2 import BalanceAllowanceParams, AssetType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.client import build_client, build_deposit_wallet_client
from bot.config import load_settings
from bot.markets import fetch_market, seconds_until_window_end
from bot.orders import pick_cheaper_outcome, place_market_buy_usd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("test_connection")


def main() -> int:
    settings = load_settings()

    is_dw = settings.signature_type == 3
    if is_dw:
        client = build_deposit_wallet_client(settings)
        logger.info("Using deposit wallet (POLY_1271): %s", settings.funder)
    else:
        client = build_client(settings)
        logger.info("Using proxy wallet (sig type %s): %s", settings.signature_type, settings.funder)

    try:
        if is_dw:
            logger.info("Syncing balance allowance for deposit wallet...")
            client.update_balance_allowance(
                BalanceAllowanceParams(
                    asset_type=AssetType.COLLATERAL,
                    signature_type=settings.signature_type,
                )
            )
        params = BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
            signature_type=settings.signature_type,
        )
        bal = client.get_balance_allowance(params)
        logger.info("USDC balance/allowance: %s", json.dumps(bal, indent=2))
    except Exception as exc:
        logger.warning("Could not fetch balance (non-fatal): %s", exc)

    market = fetch_market()
    secs = seconds_until_window_end()
    logger.info("Market: %s", market.title)
    logger.info("Slug: %s | ends in %.0fs", market.slug, secs)
    logger.info(
        "Prices — Up: %s | Down: %s",
        market.up.price,
        market.down.price,
    )

    outcome = pick_cheaper_outcome(market)
    amount = settings.test_order_usd
    logger.info(
        "Placing TEST market buy: $%.2f on %s",
        amount,
        outcome.outcome,
    )

    if secs < 15:
        logger.error("Window closes in <15s — skip test to avoid failed FOK.")
        return 1

    resp = place_market_buy_usd(client, outcome, amount)
    print("\n=== ORDER RESPONSE ===")
    print(json.dumps(resp, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logger.exception("Test failed: %s", exc)
        raise SystemExit(1) from exc
