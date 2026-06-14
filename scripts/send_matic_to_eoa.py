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
logger = logging.getLogger("send_matic_to_eoa")

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

    eoa = relayer.signer.address()
    logger.info("Sending 0.5 POL to EOA: %s", eoa)

    nonce = str(relayer.get_nonce(relayer.signer.address(), TransactionType.WALLET.value)["nonce"])
    # Transfer 0.5 POL = 500000000000000000 wei
    call = DepositWalletCall(target=eoa, value=str(200_000_000_000_000_000), data="0x")

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

    logger.info("MATIC sent to EOA!")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
