from __future__ import annotations

import logging, sys, json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web3 import Web3
from polymarket.environments import PRODUCTION as PROD
from bot.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("deploy_safe")

SAFE_FACTORY = "0xa6B71E26C5e0845f74c812102Ca7114b6a896AB2"
SAFE_SINGLETON = "0xd9Db270c1B5E3Bd161E8c8503c55cEABeE709552"
FALLBACK_HANDLER = "0xf48f2B2d2a534e402487b3ee7C18c33Aec0Fe5e4"

FACTORY_ABI = [
    {"inputs":[{"internalType":"address","name":"_singleton","type":"address"},{"internalType":"bytes","name":"initializer","type":"bytes"},{"internalType":"uint256","name":"saltNonce","type":"uint256"}],"name":"createProxyWithNonce","outputs":[{"internalType":"contract GnosisSafeProxy","name":"proxy","type":"address"}],"stateMutability":"nonpayable","type":"function"},
    {"anonymous":False,"inputs":[{"indexed":False,"internalType":"address","name":"proxy","type":"address"},{"indexed":False,"internalType":"address","name":"singleton","type":"address"}],"name":"ProxyCreation","type":"event"}
]

SAFE_ABI = [
    {"inputs":[{"internalType":"address[]","name":"_owners","type":"address[]"},{"internalType":"uint256","name":"_threshold","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"bytes","name":"data","type":"bytes"},{"internalType":"address","name":"fallbackHandler","type":"address"},{"internalType":"address","name":"paymentToken","type":"address"},{"internalType":"uint256","name":"payment","type":"uint256"},{"internalType":"address payable","name":"paymentReceiver","type":"address"}],"name":"setup","outputs":[],"stateMutability":"nonpayable","type":"function"}
]

def main() -> int:
    settings = load_settings()
    w3 = Web3(Web3.HTTPProvider(PROD.rpc_url))
    acct = w3.eth.account.from_key(settings.private_key)
    logger.info("Deployer: %s", acct.address)

    factory = w3.eth.contract(address=Web3.to_checksum_address(SAFE_FACTORY), abi=FACTORY_ABI)
    safe_contract = w3.eth.contract(abi=SAFE_ABI)

    owners = [Web3.to_checksum_address(acct.address)]
    threshold = 1
    to_addr = "0x0000000000000000000000000000000000000001"
    handler = Web3.to_checksum_address(FALLBACK_HANDLER)
    null_addr = "0x0000000000000000000000000000000000000000"

    setup_data = safe_contract.encode_abi(
        "setup",
        [owners, threshold, Web3.to_checksum_address(to_addr), b"",
         handler, Web3.to_checksum_address(null_addr), 0,
         Web3.to_checksum_address(null_addr)]
    )

    salt_nonce = int(time.time())
    logger.info("Deploying Gnosis Safe...")

    tx = factory.functions.createProxyWithNonce(
        Web3.to_checksum_address(SAFE_SINGLETON),
        Web3.to_hex(Web3.to_bytes(hexstr=setup_data)),
        salt_nonce
    ).build_transaction({
        "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": 2000000, "gasPrice": w3.eth.gas_price, "chainId": 137,
    })
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    logger.info("Deploy tx: %s, status: %s", tx_hash.hex(), receipt["status"] == 1)

    safe_address = None
    for log in receipt["logs"]:
        if log["address"].lower() == SAFE_FACTORY.lower():
            # data: proxy(32 bytes) + singleton(32 bytes)
            proxy_bytes = log["data"][12:32]  # skip 12 zero bytes + get 20 bytes
            safe_address = "0x" + proxy_bytes.hex()
            break

    if safe_address:
        logger.info("Safe deployed at: %s", safe_address)
        print(f"\nSAFE_ADDRESS={safe_address}")
    else:
        logger.error("Could not find Safe address in logs")
        return 1

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
