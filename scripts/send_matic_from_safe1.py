from __future__ import annotations
import logging, sys, time
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_abi import encode
from eth_abi.packed import encode_packed
from eth_account.messages import encode_defunct
from bot.config import load_settings

logging.basicConfig(level=logging.INFO)
settings = load_settings()

w3 = Web3(Web3.HTTPProvider("https://polygon.drpc.org"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
acct = w3.eth.account.from_key(settings.private_key)
new_eoa = acct.address
chain_id = w3.eth.chain_id

safe1 = Web3.to_checksum_address("0xde9C54c6D3faa7e7Cc0eDe3D21257c8775cE8397")
null_addr = Web3.to_checksum_address("0x" + "00" * 20)

SAFE_ABI = [{"inputs":[{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"bytes","name":"data","type":"bytes"},{"internalType":"uint8","name":"operation","type":"uint8"},{"internalType":"uint256","name":"safeTxGas","type":"uint256"},{"internalType":"uint256","name":"baseGas","type":"uint256"},{"internalType":"uint256","name":"gasPrice","type":"uint256"},{"internalType":"address","name":"gasToken","type":"address"},{"internalType":"address payable","name":"refundReceiver","type":"address"},{"internalType":"bytes","name":"signatures","type":"bytes"}],"name":"execTransaction","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"payable","type":"function"},{"inputs":[],"name":"nonce","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]
safe1_contract = w3.eth.contract(address=safe1, abi=SAFE_ABI)

DOMAIN_SEPARATOR_TYPEHASH = Web3.keccak(text="EIP712Domain(uint256 chainId,address verifyingContract)")
SAFE_TX_TYPEHASH = Web3.keccak(text="SafeTx(address to,uint256 value,bytes data,uint8 operation,uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,address gasToken,address refundReceiver,uint256 nonce)")

nonce = safe1_contract.functions.nonce().call()
print(f"Safe1 nonce: {nonce}")
print(f"New EOA: {new_eoa}")
print(f"New EOA balance: {w3.from_wei(w3.eth.get_balance(new_eoa), 'ether')} ETH")

# Build execTransaction to send 0.01 MATIC to new EOA
ds = Web3.keccak(encode(["bytes32", "uint256", "address"], [DOMAIN_SEPARATOR_TYPEHASH, chain_id, safe1]))
data_bytes = b""
value = w3.to_wei(0.01, "ether")
sth = Web3.keccak(encode(
    ["bytes32", "address", "uint256", "bytes32", "uint8", "uint256", "uint256", "uint256", "address", "address", "uint256"],
    [SAFE_TX_TYPEHASH, new_eoa, value, Web3.keccak(data_bytes), 0, 0, 0, 0, null_addr, null_addr, nonce]
))
txh = Web3.keccak(encode_packed(["bytes1", "bytes1", "bytes32", "bytes32"], [b"\x19", b"\x01", ds, sth]))
msg = encode_defunct(hexstr=txh.hex())
sig = w3.eth.account.sign_message(msg, private_key=acct.key)
sig_bytes = sig.r.to_bytes(32, "big") + sig.s.to_bytes(32, "big") + bytes([sig.v + 4])

gp = w3.eth.gas_price
print(f"Gas price: {w3.from_wei(gp, 'gwei')} gwei")

built = safe1_contract.functions.execTransaction(new_eoa, value, data_bytes, 0, 0, 0, 0, null_addr, null_addr, sig_bytes).build_transaction({
    "from": new_eoa, "nonce": w3.eth.get_transaction_count(new_eoa),
    "gas": 80000, "gasPrice": gp, "chainId": chain_id
})

tx_cost = built["gas"] * built["gasPrice"] + value
print(f"Max tx cost: {w3.from_wei(tx_cost, 'ether')} ETH")
print(f"Current balance: {w3.from_wei(w3.eth.get_balance(new_eoa), 'ether')} ETH")

if w3.eth.get_balance(new_eoa) < tx_cost:
    print("Insufficient! Trying with lower gas price...")
    gp = int(gp * 0.6)  # 60% of current
    print(f"Using gas price: {w3.from_wei(gp, 'gwei')} gwei")
    built = safe1_contract.functions.execTransaction(new_eoa, value, data_bytes, 0, 0, 0, 0, null_addr, null_addr, sig_bytes).build_transaction({
        "from": new_eoa, "nonce": w3.eth.get_transaction_count(new_eoa),
        "gas": 80000, "gasPrice": gp, "chainId": chain_id
    })
    tx_cost = built["gas"] * built["gasPrice"] + value
    print(f"New max tx cost: {w3.from_wei(tx_cost, 'ether')} ETH")

if w3.eth.get_balance(new_eoa) >= tx_cost:
    signed = acct.sign_transaction(built)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    r = w3.eth.wait_for_transaction_receipt(h, timeout=120)
    print(f"Sent: {h.hex()} (status={r['status'] == 1})")
    print(f"New EOA now: {w3.from_wei(w3.eth.get_balance(new_eoa), 'ether')} ETH")
else:
    print("Still insufficient!")
