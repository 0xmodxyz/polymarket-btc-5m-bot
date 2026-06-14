from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
w3 = Web3(Web3.HTTPProvider("https://polygon.drpc.org"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
addr = Web3.to_checksum_address("0x8053Ba862A432216c5ecD359851180f8B67a4E17")
bal = w3.eth.get_balance(addr)
print(f"0x8053Ba... on Polygon: {w3.from_wei(bal, 'ether')} MATIC")

# Also check old EOA
old = Web3.to_checksum_address("0x6D4D486180261273536530483e48c86fBCC20E1c")
bal2 = w3.eth.get_balance(old)
print(f"0x6D4D48... on Polygon: {w3.from_wei(bal2, 'ether')} MATIC")
