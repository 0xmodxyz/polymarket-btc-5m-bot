#!/usr/bin/env python3
"""Swap Circle USDC -> USDC.e on Uniswap V3, then wrap USDC.e -> pUSD via relayer."""

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("swap_and_wrap")

CIRCLE_USDC = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
PUSD = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
ONRAMP = "0x93070a847efEf7F70739046A929D47a521F5B8ee"
UNI_SWAP_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"


def _approve_calldata(spender: str) -> str:
    amount = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    spender_hex = spender[2:].lower().zfill(64)
    return f"0x095ea7b3{spender_hex}{amount}"


def _swap_calldata(recipient: str, amount_in: int) -> str:
    selector = "0x414bf389"  # exactInputSingle
    token_in = CIRCLE_USDC[2:].lower().zfill(64)
    token_out = USDC_E[2:].lower().zfill(64)
    fee = hex(100)[2:].zfill(64)  # 0.01% fee tier
    rec = recipient[2:].lower().zfill(64)
    deadline = hex(int(time.time()) + 600)[2:].zfill(64)
    amount = hex(amount_in)[2:].zfill(64)
    min_out = hex(int(amount_in * 999 / 1000))[2:].zfill(64)  # 0.1% slippage
    price_limit = "0" * 64
    return f"{selector}{token_in}{token_out}{fee}{rec}{deadline}{amount}{min_out}{price_limit}"


def _wrap_calldata(asset: str, to: str, amount_hex: str) -> str:
    selector = "0x62355638"
    asset_hex = asset[2:].lower().zfill(64)
    to_hex = to[2:].lower().zfill(64)
    amount_padded = amount_hex[2:].zfill(64)
    return f"{selector}{asset_hex}{to_hex}{amount_padded}"


def _batch(relayer, calls, dw, wallet_nonce):
    response = relayer.execute_deposit_wallet_batch(
        calls=calls, wallet_address=dw,
        nonce=wallet_nonce, deadline=str(int(time.time()) + 600),
    )
    logger.info("Batch submitted! Tx ID: %s", response.transaction_id)
    confirmed = relayer.poll_until_state(
        response.transaction_id, states=["STATE_CONFIRMED"],
        fail_state="STATE_FAILED", max_polls=60, poll_frequency=3000,
    )
    if not confirmed:
        logger.error("Batch failed or timed out")
        return False
    return True


def main() -> int:
    settings = load_settings()
    if not settings.builder_creds:
        logger.error("BUILDER_API_KEY must be set"); return 1
    dw = settings.deposit_wallet_address
    if not dw:
        logger.error("DEPOSIT_WALLET_ADDRESS must be set"); return 1

    builder_config = BuilderConfig(local_builder_creds=BuilderApiKeyCreds(
        key=settings.builder_creds.api_key,
        secret=settings.builder_creds.secret,
        passphrase=settings.builder_creds.passphrase,
    ))
    relayer = RelayClient(settings.relayer_url, settings.chain_id, settings.private_key, builder_config)

    # Step 1: Approve Circle USDC for Uniswap router + swap
    logger.info("Step 1/3: Approve Circle USDC for Uniswap + swap to USDC.e...")
    nonce1 = str(relayer.get_nonce(relayer.signer.address(), TransactionType.WALLET.value)["nonce"])

    approve_uni = DepositWalletCall(target=CIRCLE_USDC, value="0", data=_approve_calldata(UNI_SWAP_ROUTER))
    swap_call = DepositWalletCall(target=UNI_SWAP_ROUTER, value="0", data=_swap_calldata(dw, 1000000))

    if not _batch(relayer, [approve_uni, swap_call], dw, nonce1):
        return 1
    logger.info("Swap Circle USDC -> USDC.e done!")

    # Step 2: Approve USDC.e for Onramp + wrap
    logger.info("Step 2/3: Approve USDC.e for Onramp + wrap to pUSD...")
    nonce2 = str(relayer.get_nonce(relayer.signer.address(), TransactionType.WALLET.value)["nonce"])

    approve_onramp = DepositWalletCall(target=USDC_E, value="0", data=_approve_calldata(ONRAMP))
    wrap_call = DepositWalletCall(target=ONRAMP, value="0", data=_wrap_calldata(USDC_E, dw, hex(1000000)))

    if not _batch(relayer, [approve_onramp, wrap_call], dw, nonce2):
        return 1
    logger.info("Wrap USDC.e -> pUSD done!")

    # Verify
    from web3 import Web3
    from polymarket.environments import PRODUCTION as PROD
    w3 = Web3(Web3.HTTPProvider(PROD.rpc_url))
    pusd = w3.eth.contract(address=PUSD, abi=[{"constant": True, "inputs": [{"name":"_owner","type":"address"}], "name":"balanceOf", "outputs":[{"name":"balance","type":"uint256"}], "type":"function"}])
    bal = pusd.functions.balanceOf(dw).call()
    logger.info("pUSD balance in deposit wallet: %s", bal)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
