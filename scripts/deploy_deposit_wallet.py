#!/usr/bin/env python3
"""Deploy a deposit wallet via Polymarket relayer."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from py_builder_relayer_client.client import RelayClient
from py_builder_signing_sdk.config import BuilderApiKeyCreds, BuilderConfig

from bot.config import load_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("deploy_deposit_wallet")


def main() -> int:
    settings = load_settings()

    if not settings.builder_creds:
        logger.error("BUILDER_API_KEY, BUILDER_SECRET, BUILDER_PASSPHRASE must be set in .env")
        logger.error("Get them from: https://polymarket.com/settings?tab=builder")
        return 1

    builder_config = BuilderConfig(
        local_builder_creds=BuilderApiKeyCreds(
            key=settings.builder_creds.api_key,
            secret=settings.builder_creds.secret,
            passphrase=settings.builder_creds.passphrase,
        )
    )

    relayer = RelayClient(
        settings.relayer_url,
        settings.chain_id,
        settings.private_key,
        builder_config,
    )

    expected = relayer.get_expected_deposit_wallet()
    logger.info("Expected deposit wallet address: %s", expected)

    try:
        response = relayer.deploy_deposit_wallet()
        logger.info("Deploy submitted! Transaction ID: %s", response.transaction_id)
        logger.info("Transaction hash: %s", response.transaction_hash)

        confirmed = relayer.poll_until_state(
            response.transaction_id,
            states=["STATE_CONFIRMED"],
            fail_state="STATE_FAILED",
            max_polls=30,
            poll_frequency=3000,
        )
        if confirmed:
            logger.info("Deposit wallet deployed successfully!")
            logger.info("=== IMPORTANT ===")
            logger.info("Add this to your .env file:")
            logger.info("  DEPOSIT_WALLET_ADDRESS=%s", expected)
            logger.info("  POLYMARKET_SIGNATURE_TYPE=3")
            logger.info("  POLYMARKET_FUNDER=%s", expected)
            return 0
        else:
            logger.error("Deployment failed or timed out")
            return 1
    except Exception as exc:
        if "already deployed" in str(exc).lower():
            logger.info("Deposit wallet already deployed at: %s", expected)
            logger.info("Add DEPOSIT_WALLET_ADDRESS=%s to your .env", expected)
            return 0
        logger.exception("Deployment error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
