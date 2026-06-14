import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web3 import Web3

w3 = Web3(Web3.HTTPProvider('https://polygon.drpc.org'))
addr = Web3.to_checksum_address('0xb114b0FF356CBa34585F0D67Bd12eB0b253213fC')

abi = '[{"constant":true,"inputs":[{"name":"who","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"}]'

for label, token in [
    ('pUSD', '0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB'),
    ('USDC.e', '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'),
    ('Circle USDC', '0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359'),
]:
    c = w3.eth.contract(address=Web3.to_checksum_address(token), abi=json.loads(abi))
    bal = c.functions.balanceOf(addr).call()
    print(f'{label}: {bal} = ${bal/1e6}')

matic = w3.eth.get_balance(addr)
print(f'MATIC: {matic} = {matic/1e18} POL')
