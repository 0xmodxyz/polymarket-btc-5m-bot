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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate")

OLD_SAFE = "0x53cac4079f996a4caa76db02f7320ef806d924b6"
NEW_SAFE = "0xde9C54c6D3faa7e7Cc0eDe3D21257c8775cE8397"
PUSD = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
EXCHANGES = [
    "0xE111180000d2663C0091e4f400237545B87B996B",
    "0xe2222d279d744050d28e00520010520000310F59",
    "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
]

OWNER_PK = "0xa6182a73742fba72553f2e1624c059301f3e67f499ff59d44cabfdd4641519b1"

SAFE_ABI = [
    {"inputs":[{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"bytes","name":"data","type":"bytes"},{"internalType":"uint8","name":"operation","type":"uint8"},{"internalType":"uint256","name":"safeTxGas","type":"uint256"},{"internalType":"uint256","name":"baseGas","type":"uint256"},{"internalType":"uint256","name":"gasPrice","type":"uint256"},{"internalType":"address","name":"gasToken","type":"address"},{"internalType":"address payable","name":"refundReceiver","type":"address"},{"internalType":"bytes","name":"signatures","type":"bytes"}],"name":"execTransaction","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"payable","type":"function"},
    {"inputs":[],"name":"nonce","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
]

DOMAIN_SEPARATOR_TYPEHASH = Web3.keccak(text="EIP712Domain(uint256 chainId,address verifyingContract)")
SAFE_TX_TYPEHASH = Web3.keccak(text="SafeTx(address to,uint256 value,bytes data,uint8 operation,uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,address gasToken,address refundReceiver,uint256 nonce)")

def eip712_hash(types, values):
    return Web3.keccak(encode(types, values))

def packed_hash(types, values):
    return Web3.keccak(encode_packed(types, values))

def build_exec_tx(w3, safe_contract, safe_addr, to, value, data, operation, signer_key, nonce, chain_id):
    null = Web3.to_checksum_address("0x" + "00" * 20)
    ds = eip712_hash(["bytes32", "uint256", "address"], [DOMAIN_SEPARATOR_TYPEHASH, chain_id, safe_addr])
    sth = eip712_hash(
        ["bytes32", "address", "uint256", "bytes32", "uint8", "uint256", "uint256", "uint256", "address", "address", "uint256"],
        [SAFE_TX_TYPEHASH, to, value, Web3.keccak(data) if isinstance(data, bytes) else Web3.keccak(hexstr=data), operation, 0, 0, 0, null, null, nonce]
    )
    txh = packed_hash(["bytes1", "bytes1", "bytes32", "bytes32"], [b"\x19", b"\x01", ds, sth])
    msg = encode_defunct(hexstr=txh.hex())
    sig = w3.eth.account.sign_message(msg, private_key=signer_key)
    sig_bytes = sig.r.to_bytes(32, "big") + sig.s.to_bytes(32, "big") + bytes([sig.v + 4])
    return safe_contract.functions.execTransaction(to, value, data, operation, 0, 0, 0, null, null, sig_bytes)

def main():
    w3 = Web3(Web3.HTTPProvider(PROD.rpc_url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    acct = w3.eth.account.from_key(OWNER_PK)
    chain_id = w3.eth.chain_id

    old_safe = Web3.to_checksum_address(OLD_SAFE)
    new_safe = Web3.to_checksum_address(NEW_SAFE)
    pusd = Web3.to_checksum_address(PUSD)

    old_contract = w3.eth.contract(address=old_safe, abi=SAFE_ABI)
    new_contract = w3.eth.contract(address=new_safe, abi=SAFE_ABI)

    # Get pUSD balance
    bal_data = "0x70a08231" + old_safe.lower()[2:].zfill(64)
    bal = int(w3.eth.call({"to": pusd, "data": bal_data}).hex(), 16)
    logger.info("Old Safe pUSD: %s", bal)

    # Step 1: Send MATIC from old Safe to new Safe
    matic_amount = w3.to_wei(0.05, "ether")
    nonce = old_contract.functions.nonce().call()
    logger.info("Sending %s MATIC to new Safe (nonce=%s)...", w3.from_wei(matic_amount, "ether"), nonce)
    tx = build_exec_tx(w3, old_contract, old_safe, new_safe, matic_amount, b"", 0, acct.key, nonce, chain_id)
    built = tx.build_transaction({"from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address), "gas": 200000, "gasPrice": w3.eth.gas_price, "chainId": chain_id})
    signed = acct.sign_transaction(built)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    r = w3.eth.wait_for_transaction_receipt(h, timeout=120)
    logger.info("MATIC sent: %s (status=%s)", h.hex(), r["status"] == 1)

    # Step 2: Transfer pUSD from old Safe to new Safe
    transfer_selector = Web3.keccak(text="transfer(address,uint256)")[:4]
    transfer_data = transfer_selector + encode(["address", "uint256"], [new_safe, bal])
    nonce = old_contract.functions.nonce().call()
    logger.info("Transferring %s pUSD to new Safe (nonce=%s)...", bal, nonce)
    tx = build_exec_tx(w3, old_contract, old_safe, pusd, 0, transfer_data, 0, acct.key, nonce, chain_id)
    built = tx.build_transaction({"from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address), "gas": 200000, "gasPrice": w3.eth.gas_price, "chainId": chain_id})
    signed = acct.sign_transaction(built)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    r = w3.eth.wait_for_transaction_receipt(h, timeout=120)
    logger.info("pUSD transferred: %s (status=%s)", h.hex(), r["status"] == 1)

    # Step 3: Approve exchanges from new Safe
    for ex in EXCHANGES:
        spender = Web3.to_checksum_address(ex)
        approve_data = "0x095ea7b3" + spender.lower()[2:].zfill(64) + "ff" * 32
        nonce = new_contract.functions.nonce().call()
        logger.info("Approving %s from new Safe (nonce=%s)...", ex, nonce)
        tx = build_exec_tx(w3, new_contract, new_safe, pusd, 0, approve_data, 0, acct.key, nonce, chain_id)
        built = tx.build_transaction({"from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address), "gas": 200000, "gasPrice": w3.eth.gas_price, "chainId": chain_id})
        signed = acct.sign_transaction(built)
        h = w3.eth.send_raw_transaction(signed.raw_transaction)
        r = w3.eth.wait_for_transaction_receipt(h, timeout=120)
        logger.info("Approved %s: %s (status=%s)", ex, h.hex(), r["status"] == 1)

    logger.info("Migration complete!")
    print("\nUPDATE .env:")
    print("  POLYMARKET_PRIVATE_KEY=0x%s" % acct.key.hex())
    print("  POLYMARKET_FUNDER=%s" % new_safe)
    print("  POLYMARKET_SIGNATURE_TYPE=2")

if __name__ == "__main__":
    raise SystemExit(main())
