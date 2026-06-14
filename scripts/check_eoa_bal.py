from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
w3 = Web3(Web3.HTTPProvider("https://polygon.drpc.org"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
new = Web3.to_checksum_address("0xb802951782bF31D2256479717DDF185De0902054")
old = Web3.to_checksum_address("0x6D4D486180261273536530483e48c86fBCC20E1c")
print(f"New EOA: {w3.from_wei(w3.eth.get_balance(new), 'ether')} ETH")
print(f"Old EOA: {w3.from_wei(w3.eth.get_balance(old), 'ether')} ETH")
