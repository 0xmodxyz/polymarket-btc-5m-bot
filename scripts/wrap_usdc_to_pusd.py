#!/usr/bin/env python3
"""Wrap Circle USDC to pUSD via CollateralOnramp using relayer."""

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
logger = logging.getLogger("wrap_usdc_to_pusd")

CIRCLE_USDC = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
PUSD = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
ONRAMP = "0x93070a847efEf7F70739046A929D47a521F5B8ee"
COLLATERAL_OFFRAMP = "0x2957922Eb93258b93368531d39fAcCA3B4dC5854"


def _approve_calldata(spender: str) -> str:
    amount = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    spender_hex = spender[2:].lower().zfill(64)
    return f"0x095ea7b3{spender_hex}{amount}"


def _wrap_calldata(asset: str, to: str, amount_hex: str) -> str:
    """Build calldata for onramp.wrap(address _asset, address _to, uint256 _amount)."""
    selector = "0x62355638"
    asset_hex = asset[2:].lower().zfill(64)
    to_hex = to[2:].lower().zfill(64)
    amount_padded = amount_hex[2:].zfill(64)
    return f"{selector}{asset_hex}{to_hex}{amount_padded}"


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

    # Step 1: Check Circle USDC balance
    from web3 import Web3
    from polymarket.environments import PRODUCTION
    w3 = Web3(Web3.HTTPProvider(PRODUCTION.rpc_url))
    usdc = w3.eth.contract(address=CIRCLE_USDC, abi=[{
        "constant": True, "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }])
    balance = usdc.functions.balanceOf(dw).call()
    logger.info("Circle USDC balance in deposit wallet: %s", balance)

    if balance == 0:
        logger.error("No Circle USDC in deposit wallet")
        return 1

    # Step 2: Approve Circle USDC for CollateralOnramp
    logger.info("Step 1/2: Approving Circle USDC for CollateralOnramp...")

    approve_call = DepositWalletCall(
        target=CIRCLE_USDC,
        value="0",
        data=_approve_calldata(ONRAMP),
    )

    nonce_payload = relayer.get_nonce(
        relayer.signer.address(),
        TransactionType.WALLET.value,
    )
    wallet_nonce = str(nonce_payload["nonce"])

    response = relayer.execute_deposit_wallet_batch(
        calls=[approve_call],
        wallet_address=dw,
        nonce=wallet_nonce,
        deadline=str(int(time.time()) + 600),
    )
    logger.info("Approval submitted! Tx ID: %s", response.transaction_id)

    confirmed = relayer.poll_until_state(
        response.transaction_id,
        states=["STATE_CONFIRMED"],
        fail_state="STATE_FAILED",
        max_polls=60,
        poll_frequency=3000,
    )
    if not confirmed:
        logger.error("Approval failed or timed out")
        return 1
    logger.info("Circle USDC approved for CollateralOnramp")

    # Step 3: Wrap Circle USDC to pUSD
    logger.info("Step 2/2: Wrapping Circle USDC -> pUSD...")

    amount_hex = hex(balance)
    wrap_call = DepositWalletCall(
        target=ONRAMP,
        value="0",
        data=_wrap_calldata(CIRCLE_USDC, dw, amount_hex),
    )

    nonce_payload2 = relayer.get_nonce(
        relayer.signer.address(),
        TransactionType.WALLET.value,
    )
    wallet_nonce2 = str(nonce_payload2["nonce"])

    response2 = relayer.execute_deposit_wallet_batch(
        calls=[wrap_call],
        wallet_address=dw,
        nonce=wallet_nonce2,
        deadline=str(int(time.time()) + 600),
    )
    logger.info("Wrap submitted! Tx ID: %s", response2.transaction_id)

    confirmed2 = relayer.poll_until_state(
        response2.transaction_id,
        states=["STATE_CONFIRMED"],
        fail_state="STATE_FAILED",
        max_polls=60,
        poll_frequency=3000,
    )
    if not confirmed2:
        logger.error("Wrap failed or timed out")
        return 1

    logger.info("Successfully wrapped Circle USDC -> pUSD!")

    # Verify pUSD balance
    pusd = w3.eth.contract(address=PUSD, abi=[{
        "constant": True, "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }])
    pusd_bal = pusd.functions.balanceOf(dw).call()
    logger.info("pUSD balance in deposit wallet: %s", pusd_bal)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
