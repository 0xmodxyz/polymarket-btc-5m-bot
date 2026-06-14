from __future__ import annotations

import logging, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_abi import encode
from eth_account.messages import encode_defunct
from polymarket.environments import PRODUCTION as PROD
from bot.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("deploy_safe_l2")

# Jetfadil's singleton (GnosisSafeL2)
SAFE_SINGLETON = "0xe51abdf814f8854941b9fe8e3a4f65cab4e7a4a8"
SAFE_FACTORY = "0xa6B71E26C5e0845f74c812102Ca7114b6a896AB2"
FALLBACK_HANDLER = "0xf48f2B2d2a534e402487b3ee7C18c33Aec0Fe5e4"

FACTORY_ABI = [{
    "inputs": [
        {"internalType": "address", "name": "_singleton", "type": "address"},
        {"internalType": "bytes", "name": "initializer", "type": "bytes"},
        {"internalType": "uint256", "name": "saltNonce", "type": "uint256"}
    ],
    "name": "createProxyWithNonce",
    "outputs": [{"internalType": "contract GnosisSafeProxy", "name": "proxy", "type": "address"}],
    "stateMutability": "nonpayable",
    "type": "function"
}, {
    "inputs": [
        {"internalType": "address", "name": "_singleton", "type": "address"},
        {"internalType": "bytes", "name": "initializer", "type": "bytes"},
        {"internalType": "uint256", "name": "saltNonce", "type": "uint256"}
    ],
    "name": "createChainSpecificProxyWithNonce",
    "outputs": [{"internalType": "contract GnosisSafeProxy", "name": "proxy", "type": "address"}],
    "stateMutability": "nonpayable",
    "type": "function"
}]

def main():
    settings = load_settings()
    w3 = Web3(Web3.HTTPProvider(PROD.rpc_url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    acct = w3.eth.account.from_key(settings.private_key)
    chain_id = w3.eth.chain_id

    factory = w3.eth.contract(address=Web3.to_checksum_address(SAFE_FACTORY), abi=FACTORY_ABI)
    singleton = Web3.to_checksum_address(SAFE_SINGLETON)
    fallback = Web3.to_checksum_address(FALLBACK_HANDLER)

    new_owner = acct.address  # the new EOA
    logger.info("Deploying Safe for owner: %s", new_owner)
    logger.info("Using singleton (GnosisSafeL2): %s", singleton)

    # Build setup data using eth_abi.encode
    setup_selector = Web3.keccak(text="setup(address[],uint256,address,bytes,address,address,uint256,address)")[:4]
    null_addr = "0x0000000000000000000000000000000000000000"
    setup_data = setup_selector + encode(
        ["address[]", "uint256", "address", "bytes", "address", "address", "uint256", "address"],
        [[new_owner], 1, Web3.to_checksum_address(null_addr), b"", fallback, Web3.to_checksum_address(null_addr), 0, Web3.to_checksum_address(null_addr)]
    )

    salt_nonce = 42  # deterministic
    tx = factory.functions.createProxyWithNonce(singleton, setup_data, salt_nonce).build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": 500000,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id,
    })
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    logger.info("Deploy tx: %s (status=%s)", tx_hash.hex(), receipt["status"] == 1)

    # Find the ProxyCreation event
    proxy_created_topic = Web3.keccak(text="ProxyCreation(address,address)")
    safe_address = None
    for log in receipt.logs:
        if proxy_created_topic in log.topics:
            safe_address = Web3.to_checksum_address("0x" + log.topics[1].hex()[-40:])
            break

    if not safe_address:
        logger.error("Could not find ProxyCreation event")
        return 1

    logger.info("New Safe deployed at: %s", safe_address)
    logger.info("Owner: %s", new_owner)

    # Verify singleton via storage slot 0
    stored_singleton = w3.eth.get_storage_at(safe_address, 0)
    logger.info("Deployed singleton: 0x%s", stored_singleton.hex()[-40:])

    # Transfer pUSD from old Safe to new Safe via old Safe execTransaction
    old_safe = "0x53cac4079f996a4caa76db02f7320ef806d924b6"
    pusd = Web3.to_checksum_address("0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB")

    logger.info("\nUse old Safe execTransaction to transfer pUSD to new Safe")
    logger.info("Old Safe: %s", old_safe)
    logger.info("New Safe: %s", safe_address)

    print("\n" + "=" * 60)
    print("NEW SAFE: %s" % safe_address)
    print("OWNER PK: 0x%s" % acct.key.hex())
    print("UPDATE .env:")
    print("  POLYMARKET_FUNDER=%s" % safe_address)
    print("  POLYMARKET_SIGNATURE_TYPE=2")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
