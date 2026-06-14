from __future__ import annotations
import logging, sys, time
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from bot.config import load_settings
from py_builder_relayer_client.client import RelayClient
from py_builder_signing_sdk.config import BuilderConfig
from py_builder_signing_sdk.sdk_types import BuilderApiKeyCreds
from py_builder_relayer_client.models import DepositWalletCall, TransactionType

logging.basicConfig(level=logging.INFO)
settings = load_settings()
creds = settings.builder_creds
bc = BuilderApiKeyCreds(key=creds.api_key, secret=creds.secret, passphrase=creds.passphrase)
builder_config = BuilderConfig(local_builder_creds=bc)
relayer = RelayClient(settings.relayer_url, settings.chain_id, settings.private_key, builder_config)

dw = settings.deposit_wallet_address
new_eoa = "0xb802951782bF31D2256479717DDF185De0902054"
logger = logging.getLogger("send_matic")

from web3 import Web3
w3 = Web3()
matic_amount = str(w3.to_wei(0.02, "ether"))
logger.info("Deposit wallet: %s", dw)
logger.info("Sending 0.5 MATIC (%s) to new EOA %s...", matic_amount, new_eoa)

nonce_payload = relayer.get_nonce(relayer.signer.address(), TransactionType.WALLET.value)
nonce = str(nonce_payload["nonce"])
deadline = str(int(time.time()) + 600)

call = DepositWalletCall(target=new_eoa, value=matic_amount, data="0x")
response = relayer.execute_deposit_wallet_batch([call], dw, nonce, deadline)
logger.info("Submitted: %s", response.transaction_id)
confirmed = relayer.poll_until_state(response.transaction_id, ["CONFIRMED"], "FAILED", max_polls=60, poll_frequency=5000)
if confirmed:
    logger.info("MATIC sent!")
else:
    logger.error("Failed!")
