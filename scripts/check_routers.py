from web3 import Web3
from polymarket.environments import PRODUCTION
w3 = Web3(Web3.HTTPProvider(PRODUCTION.rpc_url))

# Check various known routers on Polygon
routers = {
    "SwapRouter02": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
    "V3SwapRouter": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
    "UniversalRouter": "0x3bD12C95FeDc2cB03b6F8EaE3b1036c9fE65D3C1",
    "UniversalRouter_v2": "0x4C60051384bd2d3C01bfc845Cf5F4b44bcbE9de5",
}

selectors = [
    ("exactInputSingle", "0x414bf389"),
    ("exactInput", "0xc04b8d59"),
    ("multicall", "0xac9650d8"),
    ("swap", "0x7c025200"),
]

for name, addr in routers.items():
    code = w3.eth.get_code(addr)
    print(f"{name} ({addr}): {len(code)} bytes")
    for sel_name, sel in selectors:
        found = sel[2:] in code.hex()
        print(f"  {sel_name} ({sel}): {'YES' if found else 'no'}")
    print()
