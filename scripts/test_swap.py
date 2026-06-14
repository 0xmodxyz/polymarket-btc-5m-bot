#!/usr/bin/env python3
"""Test Uniswap V3 swap calldata directly."""

from web3 import Web3
from polymarket.environments import PRODUCTION
import time

w3 = Web3(Web3.HTTPProvider(PRODUCTION.rpc_url))

CIRCLE_USDC = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
ROUTER = "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
POOL = "0xD36ec33c8bed5a9F7B6630855f1533455b98a418"

# Check pool liquidity
pool_abi = [{"inputs":[],"name":"liquidity","outputs":[{"name":"","type":"uint128"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"slot0","outputs":[{"name":"sqrtPriceX96","type":"uint160"},{"name":"tick","type":"int24"},{"name":"observationIndex","type":"uint16"},{"name":"observationCardinality","type":"uint16"},{"name":"observationCardinalityNext","type":"uint16"},{"name":"feeProtocol","type":"uint8"},{"name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"}]
pool = w3.eth.contract(address=POOL, abi=pool_abi)
try:
    liq = pool.functions.liquidity().call()
    slot0 = pool.functions.slot0().call()
    print(f"Liquidity: {liq}")
    print(f"sqrtPriceX96: {slot0[0]}")
    print(f"tick: {slot0[1]}")
except Exception as e:
    print(f"Pool error: {e}")

# Build swap calldata and estimate gas
token_in = CIRCLE_USDC[2:].lower().zfill(64)
token_out = USDC_E[2:].lower().zfill(64)
fee = hex(100)[2:].zfill(64)
recipient = "0xEF805F1b048E803b96dacB80828ab1Da0e139fA7"
rec = recipient[2:].lower().zfill(64)
deadline = hex(int(time.time()) + 600)[2:].zfill(64)
amount = hex(1000000)[2:].zfill(64)
min_out = hex(999000)[2:].zfill(64)
price_limit = "0" * 64

calldata = f"0x414bf389{token_in}{token_out}{fee}{rec}{deadline}{amount}{min_out}{price_limit}"
print(f"Calldata length: {len(calldata)} hex chars = {(len(calldata)-2)//2} bytes")

# Try to call via eth_call (simulate)
tx = {
    "from": "0x6D4D486180261273536530483e48c86fBCC20E1c",
    "to": ROUTER,
    "data": calldata,
}
try:
    result = w3.eth.call(tx)
    print(f"Swap succeeds! Output: {int(result.hex(), 16)}")
except Exception as e:
    print(f"Swap simulation failed: {e}")
