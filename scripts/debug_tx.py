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

settings = load_settings()
w3 = Web3(Web3.HTTPProvider("https://polygon.drpc.org"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
acct = w3.eth.account.from_key(settings.private_key)
new_eoa = acct.address
chain_id = w3.eth.chain_id
safe1 = Web3.to_checksum_address("0xde9C54c6D3faa7e7Cc0eDe3D21257c8775cE8397")
null_addr = Web3.to_checksum_address("0x" + "00" * 20)

DOMAIN_SEPARATOR_TYPEHASH = Web3.keccak(text="EIP712Domain(uint256 chainId,address verifyingContract)")
SAFE_TX_TYPEHASH = Web3.keccak(text="SafeTx(address to,uint256 value,bytes data,uint8 operation,uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,address gasToken,address refundReceiver,uint256 nonce)")

nonce = 3
value = w3.to_wei(0.01, "ether")
data_bytes = b""

ds = Web3.keccak(encode(["bytes32", "uint256", "address"], [DOMAIN_SEPARATOR_TYPEHASH, chain_id, safe1]))
sth = Web3.keccak(encode(
    ["bytes32", "address", "uint256", "bytes32", "uint8", "uint256", "uint256", "uint256", "address", "address", "uint256"],
    [SAFE_TX_TYPEHASH, new_eoa, value, Web3.keccak(data_bytes), 0, 0, 0, 0, null_addr, null_addr, nonce]
))
txh = Web3.keccak(encode_packed(["bytes1", "bytes1", "bytes32", "bytes32"], [b"\x19", b"\x01", ds, sth]))
msg = encode_defunct(hexstr=txh.hex())
sig = w3.eth.account.sign_message(msg, private_key=acct.key)
sig_bytes = sig.r.to_bytes(32, "big") + sig.s.to_bytes(32, "big") + bytes([sig.v + 4])

# Build execTransaction calldata
SAFE_ABI = '[{"inputs":[{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"bytes","name":"data","type":"bytes"},{"internalType":"uint8","name":"operation","type":"uint8"},{"internalType":"uint256","name":"safeTxGas","type":"uint256"},{"internalType":"uint256","name":"baseGas","type":"uint256"},{"internalType":"uint256","name":"gasPrice","type":"uint256"},{"internalType":"address","name":"gasToken","type":"address"},{"internalType":"address payable","name":"refundReceiver","type":"address"},{"internalType":"bytes","name":"signatures","type":"bytes"}],"name":"execTransaction","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"payable","type":"function"}]'
safe_contract = w3.eth.contract(address=safe1, abi=SAFE_ABI)

calldata = safe_contract.functions.execTransaction(new_eoa, value, data_bytes, 0, 0, 0, 0, null_addr, null_addr, sig_bytes)._encode_transaction_data()

print(f"Calldata: {calldata[:100]}...")
print(f"Value in tx: {value}")
print(f"EOA balance: {w3.from_wei(w3.eth.get_balance(new_eoa), 'ether')}")

# Simulate via eth_call
try:
    r = w3.eth.call({
        "from": new_eoa,
        "to": safe1,
        "data": calldata,
        "value": 0,
        "gas": 150000,
        "gasPrice": int(w3.eth.gas_price * 0.8),
    }, "latest")
    print(f"Simulation success: {r.hex()}")
except Exception as e:
    print(f"Simulation failed: {e}")
    # Try to decode revert reason
    err_msg = str(e)
    print(f"Error: {err_msg[:500]}")
