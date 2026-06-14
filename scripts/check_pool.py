#!/usr/bin/env python3
"""Check Uniswap V3 pool for Circle USDC / USDC.e and find DEX addresses."""

from web3 import Web3
from polymarket.environments import PRODUCTION

w3 = Web3(Web3.HTTPProvider(PRODUCTION.rpc_url))

CIRCLE_USDC = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
UNI_V3_FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"

factory_abi = [{"inputs":[{"internalType":"address","name":"","type":"address"},{"internalType":"address","name":"","type":"address"},{"internalType":"uint24","name":"","type":"uint24"}],"name":"getPool","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}]
factory = w3.eth.contract(address=UNI_V3_FACTORY, abi=factory_abi)

# Check various fee tiers for stable pools
for fee in [100, 500, 3000, 10000]:
    pool = factory.functions.getPool(CIRCLE_USDC, USDC_E, fee).call()
    print(f"Fee {fee}: pool={pool}")

# Also swap token order
for fee in [100, 500, 3000, 10000]:
    pool = factory.functions.getPool(USDC_E, CIRCLE_USDC, fee).call()
    print(f"Fee {fee} (reversed): pool={pool}")
