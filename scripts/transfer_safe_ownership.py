from __future__ import annotations

import logging, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_abi import encode
from eth_abi.packed import encode_packed
from eth_account.messages import encode_defunct
from polymarket.environments import PRODUCTION as PROD
from bot.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("transfer_safe")

SAFE_ADDRESS = "0x53cac4079f996a4caa76db02f7320ef806d924b6"
SENTINEL_OWNER = "0x0000000000000000000000000000000000000001"

SAFE_OWNER_ABI = [
    {"inputs":[{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"bytes","name":"data","type":"bytes"},{"internalType":"uint8","name":"operation","type":"uint8"},{"internalType":"uint256","name":"safeTxGas","type":"uint256"},{"internalType":"uint256","name":"baseGas","type":"uint256"},{"internalType":"uint256","name":"gasPrice","type":"uint256"},{"internalType":"address","name":"gasToken","type":"address"},{"internalType":"address payable","name":"refundReceiver","type":"address"},{"internalType":"bytes","name":"signatures","type":"bytes"}],"name":"execTransaction","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"payable","type":"function"},
    {"inputs":[],"name":"nonce","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"address","name":"prevOwner","type":"address"},{"internalType":"address","name":"owner","type":"address"},{"internalType":"uint256","name":"_threshold","type":"uint256"}],"name":"removeOwner","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"uint256","name":"_threshold","type":"uint256"}],"name":"addOwnerWithThreshold","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"getOwners","outputs":[{"internalType":"address[]","name":"","type":"address[]"}],"stateMutability":"view","type":"function"},
]

def _eip712_hash(types, values) -> bytes:
    return Web3.keccak(encode(types, values))

def _packed_hash(types, values) -> bytes:
    return Web3.keccak(encode_packed(types, values))

def _build_exec_tx(w3, safe_contract, safe_addr, to, value, data, operation, signer_key, nonce, chain_id):
    null_addr = Web3.to_checksum_address("0x" + "00" * 20)
    DOMAIN_SEPARATOR_TYPEHASH = Web3.keccak(text="EIP712Domain(uint256 chainId,address verifyingContract)")
    SAFE_TX_TYPEHASH = Web3.keccak(text="SafeTx(address to,uint256 value,bytes data,uint8 operation,uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,address gasToken,address refundReceiver,uint256 nonce)")

    domain_separator = _eip712_hash(
        ["bytes32", "uint256", "address"],
        [DOMAIN_SEPARATOR_TYPEHASH, chain_id, safe_addr]
    )
    data_bytes = data if isinstance(data, bytes) else bytes.fromhex(data[2:]) if data.startswith("0x") else data.encode()
    safe_tx_hash = _eip712_hash(
        ["bytes32", "address", "uint256", "bytes32", "uint8", "uint256", "uint256", "uint256", "address", "address", "uint256"],
        [SAFE_TX_TYPEHASH, to, value, Web3.keccak(data_bytes), operation, 0, 0, 0, null_addr, null_addr, nonce]
    )
    tx_hash = _packed_hash(
        ["bytes1", "bytes1", "bytes32", "bytes32"],
        [b"\x19", b"\x01", domain_separator, safe_tx_hash]
    )

    msg = encode_defunct(hexstr=tx_hash.hex())
    sig = w3.eth.account.sign_message(msg, private_key=signer_key)
    sig_bytes = sig.r.to_bytes(32, "big") + sig.s.to_bytes(32, "big") + bytes([sig.v + 4])

    return safe_contract.functions.execTransaction(
        to, value, data, operation, 0, 0, 0, null_addr, null_addr, sig_bytes
    )

def main():
    settings = load_settings()
    w3 = Web3(Web3.HTTPProvider(PROD.rpc_url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    old_acct = w3.eth.account.from_key(settings.private_key)
    safe_addr = Web3.to_checksum_address(SAFE_ADDRESS)
    safe = w3.eth.contract(address=safe_addr, abi=SAFE_OWNER_ABI)
    chain_id = w3.eth.chain_id

    logger.info("Old EOA (signer): %s", old_acct.address)

    new_acct = w3.eth.account.from_key("0xa6182a73742fba72553f2e1624c059301f3e67f499ff59d44cabfdd4641519b1")
    logger.info("New EOA: %s", new_acct.address)
    logger.info("Old EOA MATIC: %s ETH", w3.from_wei(w3.eth.get_balance(old_acct.address), "ether"))
    logger.info("New EOA MATIC: %s ETH", w3.from_wei(w3.eth.get_balance(new_acct.address), "ether"))

    # Check current owners
    owners = safe.functions.getOwners().call()
    logger.info("Current Safe owners: %s", owners)

    # Step 1: Add new owner via execTransaction signed by old EOA
    nonce = safe.functions.nonce().call()
    logger.info("Safe nonce: %s", nonce)

    add_owner_selector = Web3.keccak(text="addOwnerWithThreshold(address,uint256)")[:4]
    add_owner_data = add_owner_selector + encode(["address", "uint256"], [new_acct.address, 1])
    logger.info("Adding owner %s... (nonce=%s)", new_acct.address, nonce)

    tx = _build_exec_tx(w3, safe, safe_addr, safe_addr, 0, add_owner_data, 0, old_acct.key, nonce, chain_id)
    built = tx.build_transaction({
        "from": old_acct.address,
        "nonce": w3.eth.get_transaction_count(old_acct.address),
        "gas": 200000,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id,
    })
    signed = old_acct.sign_transaction(built)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    logger.info("Add owner result: %s (tx: %s)", receipt["status"] == 1, tx_hash.hex())

    # Check owners after adding
    owners = safe.functions.getOwners().call()
    logger.info("Safe owners after add: %s", owners)

    # Step 2: Remove old owner via execTransaction signed by new EOA
    nonce = safe.functions.nonce().call()
    logger.info("Safe nonce: %s", nonce)

    # For removeOwner, we need prevOwner. Owners are in linked list order.
    # SENTINEL -> newest -> ... -> oldest -> SENTINEL
    # New owner was added last, so it's first in the list after SENTINEL.
    # Owner to remove is the old EOA. The owner BEFORE it in the list is the new EOA.
    old_addr_checksum = Web3.to_checksum_address(old_acct.address)
    remove_owner_selector = Web3.keccak(text="removeOwner(address,address,uint256)")[:4]
    remove_owner_data = remove_owner_selector + encode(["address", "address", "uint256"], [new_acct.address, old_addr_checksum, 1])
    logger.info("Removing owner %s... (nonce=%s)", old_addr_checksum, nonce)

    tx = _build_exec_tx(w3, safe, safe_addr, safe_addr, 0, remove_owner_data, 0, new_acct.key, nonce, chain_id)
    built = tx.build_transaction({
        "from": new_acct.address,
        "nonce": w3.eth.get_transaction_count(new_acct.address),
        "gas": 200000,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id,
    })
    signed = new_acct.sign_transaction(built)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    logger.info("Remove owner result: %s (tx: %s)", receipt["status"] == 1, tx_hash.hex())

    # Final owners
    owners = safe.functions.getOwners().call()
    logger.info("Final Safe owners: %s", owners)

    print("\n" + "=" * 60)
    print("SAVE THIS NEW PRIVATE KEY and update .env:")
    print(f"NEW_PRIVATE_KEY=0x{new_acct.key.hex()}")
    print(f"POLYMARKET_FUNDER={SAFE_ADDRESS}")
    print(f"POLYMARKET_SIGNATURE_TYPE=2")
    print("=" * 60)

if __name__ == "__main__":
    raise SystemExit(main())
