from __future__ import annotations
import logging, sys, time
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from bot.config import load_settings
from py_builder_relayer_client.client import RelayClient
from py_builder_signing_sdk.config import BuilderConfig
from py_builder_signing_sdk.sdk_types import BuilderApiKeyCreds

logging.basicConfig(level=logging.INFO)

settings = load_settings()
creds = settings.builder_creds
bc = BuilderApiKeyCreds(key=creds.api_key, secret=creds.secret, passphrase=creds.passphrase)
builder_config = BuilderConfig(local_builder_creds=bc)
relayer = RelayClient(settings.relayer_url, settings.chain_id, settings.private_key, builder_config)

rsafe = relayer.get_expected_safe()
print(f"Expected Safe: {rsafe}")

deployed = relayer.get_deployed(rsafe)
print(f"Deployed (relayer): {deployed}")

txs = relayer.get_transactions()
for tx in txs:
    tid = tx.get("id")
    state = tx.get("state")
    proxy = tx.get("proxyAddress")
    print(f"  ID: {tid} | State: {state} | Proxy: {proxy} | TX: {tx.get('transactionHash')}")

# Also check on-chain
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
w3 = Web3(Web3.HTTPProvider("https://polygon.drpc.org"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
code = w3.eth.get_code(Web3.to_checksum_address(rsafe))
print(f"On-chain code length at {rsafe}: {len(code)}")
