from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
w3 = Web3(Web3.HTTPProvider("https://polygon.drpc.org"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
dw = Web3.to_checksum_address("0xEF805F1b048E803b96dacB80828ab1Da0e139fA7")
new_eoa = Web3.to_checksum_address("0xb802951782bF31D2256479717DDF185De0902054")
print(f"Deposit wallet: {w3.from_wei(w3.eth.get_balance(dw), 'ether')} ETH")
print(f"New EOA: {w3.from_wei(w3.eth.get_balance(new_eoa), 'ether')} ETH")
