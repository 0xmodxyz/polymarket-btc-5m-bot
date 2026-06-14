#!/usr/bin/env python3
"""Approve trading contracts from deposit wallet via relayer batch."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from py_builder_relayer_client.client import RelayClient
from py_builder_relayer_client.models import DepositWalletCall, TransactionType
from py_builder_signing_sdk.config import BuilderApiKeyCreds, BuilderConfig

from bot.config import load_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("approve_deposit_wallet")

# Polygon mainnet contract addresses (CTF v2 / CLOB v2)
CTF_EXCHANGE = "0xE111180000d2663C0091e4f400237545B87B996B"
NEG_RISK_EXCHANGE = "0xe2222d279d744050d28e00520010520000310F59"
NEG_RISK_ADAPTER = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
CONDITIONAL_TOKEN = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"

MAX_U256 = "115792089237316195423570985008687907853269984665640564039457584007913129639935"


def _approve_calldata(spender: str) -> str:
    amount_hex = hex(int(MAX_U256))[2:].zfill(64)
    spender_hex = spender[2:].lower().zfill(64)
    return f"0x095ea7b3{spender_hex}{amount_hex}"


def main() -> int:
    settings = load_settings()

    if not settings.builder_creds:
        logger.error("BUILDER_API_KEY, BUILDER_SECRET, BUILDER_PASSPHRASE must be set")
        return 1

    dw = settings.deposit_wallet_address
    if not dw:
        logger.error("DEPOSIT_WALLET_ADDRESS must be set in .env")
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

    nonce_payload = relayer.get_nonce(
        relayer.signer.address(),
        TransactionType.WALLET.value,
    )
    wallet_nonce = str(nonce_payload["nonce"])

    calls = [
        DepositWalletCall(
            target=settings.pusd_address,
            value="0",
            data=_approve_calldata(CTF_EXCHANGE),
        ),
        DepositWalletCall(
            target=settings.pusd_address,
            value="0",
            data=_approve_calldata(NEG_RISK_EXCHANGE),
        ),
        DepositWalletCall(
            target=settings.pusd_address,
            value="0",
            data=_approve_calldata(NEG_RISK_ADAPTER),
        ),
    ]

    deadline = str(int(time.time()) + 600)

    logger.info("Approving pUSD from deposit wallet %s ...", dw)
    logger.info("Contracts: CTF Exchange, Neg Risk Exchange, Neg Risk Adapter")

    try:
        response = relayer.execute_deposit_wallet_batch(
            calls=calls,
            wallet_address=dw,
            nonce=wallet_nonce,
            deadline=deadline,
        )
        logger.info("Approval batch submitted! Tx ID: %s", response.transaction_id)

        confirmed = relayer.poll_until_state(
            response.transaction_id,
            states=["STATE_CONFIRMED"],
            fail_state="STATE_FAILED",
            max_polls=30,
            poll_frequency=3000,
        )
        if confirmed:
            logger.info("All approvals set successfully!")
            return 0
        else:
            logger.error("Approval batch failed or timed out")
            return 1
    except Exception as exc:
        logger.exception("Approval error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
