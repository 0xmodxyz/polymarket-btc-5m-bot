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
from polymarket.environments import PRODUCTION as PROD
from bot.config import load_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("send_matic")

settings = load_settings()
w3 = Web3(Web3.HTTPProvider(PROD.rpc_url))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
acct = w3.eth.account.from_key(settings.private_key)
chain_id = w3.eth.chain_id

OLD_SAFE = "0x53cac4079f996a4caa76db02f7320ef806d924b6"
relayer_safe = "0x064CDf9327F1aE973bDbe12316799960067Be069"

SAFE_ABI = [
    {"inputs":[{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"bytes","name":"data","type":"bytes"},{"internalType":"uint8","name":"operation","type":"uint8"},{"internalType":"uint256","name":"safeTxGas","type":"uint256"},{"internalType":"uint256","name":"baseGas","type":"uint256"},{"internalType":"uint256","name":"gasPrice","type":"uint256"},{"internalType":"address","name":"gasToken","type":"address"},{"internalType":"address payable","name":"refundReceiver","type":"address"},{"internalType":"bytes","name":"signatures","type":"bytes"}],"name":"execTransaction","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"payable","type":"function"},
    {"inputs":[],"name":"nonce","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
]

DOMAIN_SEPARATOR_TYPEHASH = Web3.keccak(text="EIP712Domain(uint256 chainId,address verifyingContract)")
SAFE_TX_TYPEHASH = Web3.keccak(text="SafeTx(address to,uint256 value,bytes data,uint8 operation,uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,address gasToken,address refundReceiver,uint256 nonce)")

def build_exec_tx(safe_contract, safe_addr, to, value, data, operation, signer_key, nonce, chain_id):
    null = Web3.to_checksum_address("0x" + "00" * 20)
    ds = Web3.keccak(encode(["bytes32", "uint256", "address"], [DOMAIN_SEPARATOR_TYPEHASH, chain_id, safe_addr]))
    data_bytes = data if isinstance(data, bytes) else bytes.fromhex(data[2:]) if data.startswith("0x") else b""
    sth = Web3.keccak(encode(
        ["bytes32", "address", "uint256", "bytes32", "uint8", "uint256", "uint256", "uint256", "address", "address", "uint256"],
        [SAFE_TX_TYPEHASH, to, value, Web3.keccak(data_bytes), operation, 0, 0, 0, null, null, nonce]
    ))
    txh = Web3.keccak(encode_packed(["bytes1", "bytes1", "bytes32", "bytes32"], [b"\x19", b"\x01", ds, sth]))
    msg = encode_defunct(hexstr=txh.hex())
    sig = w3.eth.account.sign_message(msg, private_key=signer_key)
    sig_bytes = sig.r.to_bytes(32, "big") + sig.s.to_bytes(32, "big") + bytes([sig.v + 4])
    return safe_contract.functions.execTransaction(to, value, data_bytes, operation, 0, 0, 0, null, null, sig_bytes)

safe_addr = Web3.to_checksum_address(OLD_SAFE)
new_eoa = acct.address
relayer = Web3.to_checksum_address(relayer_safe)
safe = w3.eth.contract(address=safe_addr, abi=SAFE_ABI)
nonce = safe.functions.nonce().call()
null_addr = Web3.to_checksum_address("0x" + "00" * 20)

logger.info("Old Safe nonce: %s", nonce)
logger.info("Old Safe MATIC: %s ETH", w3.from_wei(w3.eth.get_balance(safe_addr), "ether"))

# Send 0.015 MATIC from old Safe to new EOA
value = w3.to_wei(0.015, "ether")
logger.info("Sending 0.015 MATIC to new EOA...")

tx = build_exec_tx(safe, safe_addr, new_eoa, value, b"", 0, acct.key, nonce, chain_id)
gp = w3.eth.gas_price
logger.info(f"Gas price: {w3.from_wei(gp, 'gwei')} gwei")
logger.info(f"EOA balance: {w3.from_wei(w3.eth.get_balance(new_eoa), 'ether')} ETH")

built = tx.build_transaction({
    "from": new_eoa, "nonce": w3.eth.get_transaction_count(new_eoa),
    "gas": 120000, "gasPrice": int(gp * 0.5), "chainId": chain_id
})
logger.info(f"Max cost: {w3.from_wei(built['gas'] * built['gasPrice'], 'ether')} ETH")

signed = acct.sign_transaction(built)
h = w3.eth.send_raw_transaction(signed.raw_transaction)
r = w3.eth.wait_for_transaction_receipt(h, timeout=120)
logger.info(f"Sent: {h.hex()} (status={r['status'] == 1})")
logger.info(f"New EOA now: {w3.from_wei(w3.eth.get_balance(new_eoa), 'ether')} ETH")

# Now send MATIC from new EOA to relayer Safe
logger.info("\nSending 0.01 MATIC from EOA to relayer Safe...")
tx2 = {"to": relayer, "value": w3.to_wei(0.01, "ether"), "gas": 21000, "gasPrice": int(gp * 0.5), "nonce": w3.eth.get_transaction_count(new_eoa), "chainId": chain_id}
signed2 = acct.sign_transaction(tx2)
h2 = w3.eth.send_raw_transaction(signed2.raw_transaction)
r2 = w3.eth.wait_for_transaction_receipt(h2, timeout=120)
logger.info(f"Sent: {h2.hex()} (status={r2['status'] == 1})")
logger.info(f"Relayer Safe MATIC: {w3.from_wei(w3.eth.get_balance(relayer), 'ether')} ETH")
