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
logger = logging.getLogger("transfer_to_eoa")

PUSD = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"

def _transfer_calldata(to: str, amount: int) -> str:
    selector = "0xa9059cbb"
    to_hex = to[2:].lower().zfill(64)
    amt_hex = hex(amount)[2:].zfill(64)
    return f"{selector}{to_hex}{amt_hex}"

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

    # Get pUSD balance first
    from web3 import Web3
    from polymarket.environments import PRODUCTION as PROD
    w3 = Web3(Web3.HTTPProvider(PROD.rpc_url))
    pusd = w3.eth.contract(address=PUSD, abi=[{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}])
    bal = pusd.functions.balanceOf(dw).call()
    logger.info("pUSD balance in deposit wallet: %s", bal)

    if bal == 0:
        logger.info("No pUSD to transfer")
        return 0

    eoa = relayer.signer.address()
    logger.info("Transferring %s pUSD to EOA: %s", bal, eoa)

    nonce = str(relayer.get_nonce(relayer.signer.address(), TransactionType.WALLET.value)["nonce"])
    call = DepositWalletCall(target=PUSD, value="0", data=_transfer_calldata(eoa, bal))

    response = relayer.execute_deposit_wallet_batch(
        calls=[call], wallet_address=dw,
        nonce=nonce, deadline=str(int(time.time()) + 600),
    )
    logger.info("Transfer submitted! Tx ID: %s", response.transaction_id)
    confirmed = relayer.poll_until_state(
        response.transaction_id, states=["STATE_CONFIRMED"],
        fail_state="STATE_FAILED", max_polls=60, poll_frequency=3000,
    )
    if not confirmed:
        logger.error("Transfer failed or timed out")
        return 1

    bal2 = pusd.functions.balanceOf(dw).call()
    eoa_bal = pusd.functions.balanceOf(eoa).call()
    logger.info("Deposit wallet pUSD: %s", bal2)
    logger.info("EOA pUSD: %s", eoa_bal)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
