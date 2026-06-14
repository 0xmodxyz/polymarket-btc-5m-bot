"""Transfer pUSD from relayer Safe to deposit wallet."""
from __future__ import annotations
import logging, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_abi import encode
from eth_abi.packed import encode_packed
from eth_account.messages import encode_defunct
from bot.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("transfer_to_dw")

settings = load_settings()
SAFE = Web3.to_checksum_address(settings.funder)  # relayer Safe
DW = Web3.to_checksum_address(settings.deposit_wallet_address)
PUSD = Web3.to_checksum_address(settings.pusd_address)

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
    data_bytes = data if isinstance(data, bytes) else bytes.fromhex(data[2:]) if data.startswith("0x") else b""
    sth = eip712_hash(
        ["bytes32", "address", "uint256", "bytes32", "uint8", "uint256", "uint256", "uint256", "address", "address", "uint256"],
        [SAFE_TX_TYPEHASH, to, value, Web3.keccak(data_bytes), operation, 0, 0, 0, null, null, nonce]
    )
    txh = packed_hash(["bytes1", "bytes1", "bytes32", "bytes32"], [b"\x19", b"\x01", ds, sth])
    msg = encode_defunct(hexstr=txh.hex())
    sig = w3.eth.account.sign_message(msg, private_key=signer_key)
    sig_bytes = sig.r.to_bytes(32, "big") + sig.s.to_bytes(32, "big") + bytes([sig.v + 4])
    return safe_contract.functions.execTransaction(to, value, data_bytes, operation, 0, 0, 0, null, null, sig_bytes)

def main():
    w3 = Web3(Web3.HTTPProvider("https://polygon.drpc.org"))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    acct = w3.eth.account.from_key(settings.private_key)
    chain_id = w3.eth.chain_id

    safe_contract = w3.eth.contract(address=SAFE, abi=SAFE_ABI)
    null_addr = Web3.to_checksum_address("0x" + "00" * 20)

    # Check pUSD balance of relayer Safe
    bal_selector = Web3.keccak(text="balanceOf(address)")[:4]
    bal_data = bal_selector + encode(["address"], [SAFE])
    safe_pusd = int(w3.eth.call({"to": PUSD, "data": bal_data}).hex(), 16)
    logger.info("Relayer Safe pUSD balance: %s", safe_pusd)

    if safe_pusd == 0:
        logger.info("No pUSD to transfer")
        return 0

    # Transfer pUSD from Safe to deposit wallet
    transfer_selector = Web3.keccak(text="transfer(address,uint256)")[:4]
    transfer_data = transfer_selector + encode(["address", "uint256"], [DW, safe_pusd])
    nonce = safe_contract.functions.nonce().call()
    logger.info("Transferring %s pUSD to deposit wallet %s (nonce=%s)...", safe_pusd, DW, nonce)

    tx = build_exec_tx(w3, safe_contract, SAFE, PUSD, 0, transfer_data, 0, acct.key, nonce, chain_id)
    built = tx.build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": 200000,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id,
    })
    signed = acct.sign_transaction(built)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    r = w3.eth.wait_for_transaction_receipt(h, timeout=120)
    logger.info("pUSD transferred: %s (status=%s)", h.hex(), r["status"] == 1)

    print("\n=== DONE ===")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
