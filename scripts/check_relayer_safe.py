from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
w3 = Web3(Web3.HTTPProvider("https://polygon.drpc.org"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
addr = Web3.to_checksum_address("0x064CDf9327F1aE973bDbe12316799960067Be069")
code = w3.eth.get_code(addr)
print(f"Code length: {len(code)} bytes")
bal = w3.eth.get_balance(addr)
print(f"MATIC: {w3.from_wei(bal, 'ether')} ETH")
pusd = Web3.to_checksum_address("0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB")
bal_p = w3.eth.call({"to": pusd, "data": "0x70a08231" + addr.lower()[2:].zfill(64)})
print(f"pUSD: {int(bal_p.hex(), 16)}")
