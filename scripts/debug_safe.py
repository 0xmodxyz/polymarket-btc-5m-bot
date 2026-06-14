from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
w3 = Web3(Web3.HTTPProvider("https://polygon.drpc.org"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

addr = Web3.to_checksum_address("0xde9C54c6D3faa7e7Cc0eDe3D21257c8775cE8397")
singleton_raw = w3.eth.get_storage_at(addr, 0)
singleton = Web3.to_checksum_address(singleton_raw[-20:].hex())
print(f"Safe: {addr}")
print(f"Singleton (slot 0): {singleton}")
print(f"MATIC: {w3.from_wei(w3.eth.get_balance(addr), 'ether')} ETH")

# Try nonce
try:
    r = w3.eth.call({"to": addr, "data": "0xaffed0e0"}, "latest")
    print(f"nonce: {int(r.hex(), 16)}")
except Exception as e:
    print(f"nonce failed: {e}")

# Try VERSION
try:
    r = w3.eth.call({"to": addr, "data": w3.keccak(text="VERSION()")[:4]}, "latest")
    print(f"VERSION: {r.hex()}")
except Exception as e:
    print(f"VERSION failed: {e}")

# Check old relayer Safe
rsafe = Web3.to_checksum_address("0x064CDf9327F1aE973bDbe12316799960067Be069")
rsingleton_raw = w3.eth.get_storage_at(rsafe, 0)
rsingleton = Web3.to_checksum_address(rsingleton_raw[-20:].hex())
print(f"\nRelayer Safe: {rsafe}")
print(f"Relayer Singleton (slot 0): {rsingleton}")
print(f"Relayer MATIC: {w3.from_wei(w3.eth.get_balance(rsafe), 'ether')} ETH")

# Try nonce on relayer Safe
try:
    r = w3.eth.call({"to": rsafe, "data": "0xaffed0e0"}, "latest")
    print(f"Relayer nonce: {int(r.hex(), 16)}")
except Exception as e:
    print(f"Relayer nonce failed: {e}")
