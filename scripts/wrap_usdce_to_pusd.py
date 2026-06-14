#!/usr/bin/env python3
"""Wrap existing USDC.e to pUSD via relayer."""

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
from web3 import Web3
from polymarket.environments import PRODUCTION

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("wrap_usdce")

USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
PUSD = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
ONRAMP = "0x93070a847efEf7F70739046A929D47a521F5B8ee"

def main():
    settings = load_settings()
    dw = settings.deposit_wallet_address
    if not dw or not settings.builder_creds:
        logger.error("Missing config"); return 1

    builder_config = BuilderConfig(local_builder_creds=BuilderApiKeyCreds(
        key=settings.builder_creds.api_key, secret=settings.builder_creds.secret,
        passphrase=settings.builder_creds.passphrase,
    ))
    relayer = RelayClient(settings.relayer_url, settings.chain_id, settings.private_key, builder_config)

    w3 = Web3(Web3.HTTPProvider(PRODUCTION.rpc_url))
    erc20 = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]

    # Check USDC.e balance
    usdce = w3.eth.contract(address=USDC_E, abi=erc20)
    bal = usdce.functions.balanceOf(dw).call()
    logger.info("USDC.e balance: %s", bal)

    if bal == 0:
        logger.error("No USDC.e"); return 1

    # Approve USDC.e for onramp
    spender_hex = ONRAMP[2:].lower().zfill(64)
    amount = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    approve_data = f"0x095ea7b3{spender_hex}{amount}"

    # Wrap calldata
    selector = "0x62355638"
    asset_hex = USDC_E[2:].lower().zfill(64)
    to_hex = dw[2:].lower().zfill(64)
    amount_padded = hex(bal)[2:].zfill(64)
    wrap_data = f"{selector}{asset_hex}{to_hex}{amount_padded}"

    # Get nonce
    nonce = str(relayer.get_nonce(relayer.signer.address(), TransactionType.WALLET.value)["nonce"])

    approve_call = DepositWalletCall(target=USDC_E, value="0", data=approve_data)
    wrap_call = DepositWalletCall(target=ONRAMP, value="0", data=wrap_data)

    logger.info("Approving USDC.e for Onramp + wrapping %s USDC.e -> pUSD...", bal)

    response = relayer.execute_deposit_wallet_batch(
        calls=[approve_call, wrap_call], wallet_address=dw,
        nonce=nonce, deadline=str(int(time.time()) + 600),
    )
    logger.info("Batch submitted! Tx ID: %s", response.transaction_id)

    confirmed = relayer.poll_until_state(
        response.transaction_id, states=["STATE_CONFIRMED"],
        fail_state="STATE_FAILED", max_polls=60, poll_frequency=3000,
    )
    if not confirmed:
        logger.error("Wrap failed"); return 1

    logger.info("Wrap successful!")
    pusd = w3.eth.contract(address=PUSD, abi=erc20)
    pbal = pusd.functions.balanceOf(dw).call()
    logger.info("pUSD balance: %s", pbal)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
