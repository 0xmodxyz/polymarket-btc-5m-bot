from __future__ import annotations

import logging, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web3 import Web3
from eth_abi import encode
from eth_abi.packed import encode_packed
from eth_account.messages import encode_defunct
from polymarket.environments import PRODUCTION as PROD
from bot.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("approve_safe")

PUSD = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
SAFE_ADDRESS = "0x53cac4079f996a4caa76db02f7320ef806d924b6"
EXCHANGES = [
    "0xE111180000d2663C0091e4f400237545B87B996B",
    "0xe2222d279d744050d28e00520010520000310F59",
    "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
]

SAFE_ABI = [
    {"inputs":[{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"bytes","name":"data","type":"bytes"},{"internalType":"uint8","name":"operation","type":"uint8"},{"internalType":"uint256","name":"safeTxGas","type":"uint256"},{"internalType":"uint256","name":"baseGas","type":"uint256"},{"internalType":"uint256","name":"gasPrice","type":"uint256"},{"internalType":"address","name":"gasToken","type":"address"},{"internalType":"address payable","name":"refundReceiver","type":"address"},{"internalType":"bytes","name":"signatures","type":"bytes"}],"name":"execTransaction","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"payable","type":"function"},
    {"inputs":[],"name":"nonce","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
]

def _approve_calldata(spender: str) -> str:
    return f"0x095ea7b3{spender[2:].lower().zfill(64)}{'ff' * 32}"

def _eip712_hash(types, values) -> bytes:
    """Compute keccak256(abi.encode(...)) matching Solidity's abi.encode"""
    return Web3.keccak(encode(types, values))

def _packed_hash(types, values) -> bytes:
    """Compute keccak256(abi.encodePacked(...))"""
    return Web3.keccak(encode_packed(types, values))

def main() -> int:
    settings = load_settings()
    w3 = Web3(Web3.HTTPProvider(PROD.rpc_url))
    acct = w3.eth.account.from_key(settings.private_key)
    safe_addr = Web3.to_checksum_address(SAFE_ADDRESS)
    safe = w3.eth.contract(address=safe_addr, abi=SAFE_ABI)
    chain_id = w3.eth.chain_id
    null_addr = Web3.to_checksum_address("0x0000000000000000000000000000000000000000")
    pusd_checksum = Web3.to_checksum_address(PUSD)

    DOMAIN_SEPARATOR_TYPEHASH = Web3.keccak(text="EIP712Domain(uint256 chainId,address verifyingContract)")
    SAFE_TX_TYPEHASH = Web3.keccak(text="SafeTx(address to,uint256 value,bytes data,uint8 operation,uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,address gasToken,address refundReceiver,uint256 nonce)")

    safe_nonce = safe.functions.nonce().call()
    logger.info("Safe nonce: %s", safe_nonce)

    for ex in EXCHANGES:
        spender = Web3.to_checksum_address(ex)
        call_data = _approve_calldata(ex)

        domain_separator = _eip712_hash(
            ["bytes32", "uint256", "address"],
            [DOMAIN_SEPARATOR_TYPEHASH, chain_id, safe_addr]
        )
        safe_tx_hash = _eip712_hash(
            ["bytes32", "address", "uint256", "bytes32", "uint8", "uint256", "uint256", "uint256", "address", "address", "uint256"],
            [SAFE_TX_TYPEHASH, pusd_checksum, 0, Web3.keccak(hexstr=call_data), 0, 0, 0, 0, null_addr, null_addr, safe_nonce]
        )
        tx_hash = _packed_hash(
            ["bytes1", "bytes1", "bytes32", "bytes32"],
            [b"\x19", b"\x01", domain_separator, safe_tx_hash]
        )

        logger.info("Approving %s... (nonce=%s)", ex, safe_nonce)
        msg = encode_defunct(hexstr=tx_hash.hex())
        sig = acct.sign_message(msg)
        sig_bytes = sig.r.to_bytes(32, "big") + sig.s.to_bytes(32, "big") + bytes([sig.v + 4])

        tx = safe.functions.execTransaction(
            pusd_checksum, 0, call_data, 0, 0, 0, 0,
            null_addr, null_addr, sig_bytes
        ).build_transaction({
            "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address),
            "gas": 200000, "gasPrice": w3.eth.gas_price, "chainId": chain_id,
        })
        signed = acct.sign_transaction(tx)
        tx_hash_sent = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash_sent, timeout=120)
        logger.info("Approved %s: %s (tx: %s)", ex, receipt["status"] == 1, tx_hash_sent.hex())
        safe_nonce += 1

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
