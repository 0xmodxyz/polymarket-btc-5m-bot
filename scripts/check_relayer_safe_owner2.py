from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
w3 = Web3(Web3.HTTPProvider("https://polygon.drpc.org"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
addr = Web3.to_checksum_address("0x064CDf9327F1aE973bDbe12316799960067Be069")

# Try VERSION
data = w3.keccak(text="VERSION()")[:4]
try:
    r = w3.eth.call({"to": addr, "data": data}, "latest")
    print(f"VERSION: {bytes.fromhex(r.hex()[2:]).decode('utf-8').rstrip(chr(0))}")
except Exception as e:
    print(f"VERSION failed: {e}")

# Try getOwners (correct selector: 0x2d54d5fa)
try:
    r = w3.eth.call({"to": addr, "data": "0x2d54d5fa"}, "latest")
    print(f"getOwners raw: {r.hex()}")
    # Parse as array of addresses
    offset = int(r[2:2+64], 16)
    length = int(r[2+offset*2:2+offset*2+64], 16)
    print(f"  length: {length}")
    decoded = []
    for i in range(length):
        addr_hex = r[2+offset*2+64+i*64:2+offset*2+64+(i+1)*64]
        decoded.append(Web3.to_checksum_address(addr_hex[-40:]))
    print(f"  owners: {decoded}")
except Exception as e:
    print(f"getOwners failed: {e}")

# Try getThreshold
data = w3.keccak(text="getThreshold()")[:4]
try:
    r = w3.eth.call({"to": addr, "data": data}, "latest")
    print(f"getThreshold: {int(r.hex(), 16)}")
except Exception as e:
    print(f"getThreshold failed: {e}")

# Check if jetfadil's safe works with same approach
jf = Web3.to_checksum_address("0xe0229E10A858860218B6132F4234602C47bD6603")
try:
    r = w3.eth.call({"to": jf, "data": "0x2d54d5fa"}, "latest")
    print(f"\nJetfadil getOwners raw: {r.hex()}")
    offset = int(r[2:2+64], 16)
    length = int(r[2+offset*2:2+offset*2+64], 16)
    decoded = []
    for i in range(length):
        addr_hex = r[2+offset*2+64+i*64:2+offset*2+64+(i+1)*64]
        decoded.append(Web3.to_checksum_address(addr_hex[-40:]))
    print(f"  owners: {decoded}")
except Exception as e:
    print(f"Jetfadil getOwners failed: {e}")
