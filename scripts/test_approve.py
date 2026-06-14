#!/usr/bin/env python3
"""Test if relayer allows approve to Uniswap router."""

from __future__ import annotations

import logging, sys, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from py_builder_relayer_client.client import RelayClient
from py_builder_relayer_client.models import DepositWalletCall, TransactionType
from py_builder_signing_sdk.config import BuilderApiKeyCreds, BuilderConfig

from bot.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("test_approve")

CIRCLE_USDC = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
UNI_SWAP_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"

def main():
    settings = load_settings()
    dw = settings.deposit_wallet_address
    builder_config = BuilderConfig(local_builder_creds=BuilderApiKeyCreds(
        key=settings.builder_creds.api_key, secret=settings.builder_creds.secret,
        passphrase=settings.builder_creds.passphrase,
    ))
    relayer = RelayClient(settings.relayer_url, settings.chain_id, settings.private_key, builder_config)

    nonce = str(relayer.get_nonce(relayer.signer.address(), TransactionType.WALLET.value)["nonce"])
    amount = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    spender_hex = UNI_SWAP_ROUTER[2:].lower().zfill(64)
    data = f"0x095ea7b3{spender_hex}{amount}"

    call = DepositWalletCall(target=CIRCLE_USDC, value="0", data=data)
    response = relayer.execute_deposit_wallet_batch(
        calls=[call], wallet_address=dw,
        nonce=nonce, deadline=str(int(time.time()) + 600),
    )
    logger.info("Submitted! Tx ID: %s", response.transaction_id)
    confirmed = relayer.poll_until_state(
        response.transaction_id, states=["STATE_CONFIRMED"],
        fail_state="STATE_FAILED", max_polls=60, poll_frequency=3000,
    )
    if confirmed:
        logger.info("Approve succeeded!")
    else:
        logger.error("Approve failed")

if __name__ == "__main__":
    main()
