from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
w3 = Web3(Web3.HTTPProvider("https://polygon.drpc.org"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
addr = Web3.to_checksum_address("0x064CDf9327F1aE973bDbe12316799960067Be069")

# Check singleton (storage slot 0)
singleton_raw = w3.eth.get_storage_at(addr, 0)
singleton = Web3.to_checksum_address(singleton_raw[-20:].hex())
print(f"Singleton: {singleton}")

# Check owners via singleton's getOwners() - need to simulate call
from eth_abi import encode
# The singleton address
singleton_code = w3.eth.get_code(singleton)
print(f"Singleton code size: {len(singleton_code)} bytes")

# Try calling getOwners and getThreshold via delegatecall simulation
get_owners_data = "0x2d54d5fa"  # getOwners() selector
try:
    result = w3.eth.call({"to": addr, "data": get_owners_data}, "latest")
    print(f"getOwners result: {result.hex()}")
except Exception as e:
    print(f"getOwners failed: {e}")

get_threshold_data = "0x595313b6"  # getThreshold() selector  
try:
    result = w3.eth.call({"to": addr, "data": get_threshold_data}, "latest")
    print(f"getThreshold result: {int(result.hex(), 16)}")
except Exception as e:
    print(f"getThreshold failed: {e}")

get_nonce_data = "0xaffed0e0"  # nonce() selector
try:
    result = w3.eth.call({"to": addr, "data": get_nonce_data}, "latest")
    print(f"nonce: {int(result.hex(), 16)}")
except Exception as e:
    print(f"nonce failed: {e}")
