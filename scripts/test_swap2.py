#!/usr/bin/env python3
"""Test Uniswap V3 swap with correct router."""

from web3 import Web3
from polymarket.environments import PRODUCTION
import time

w3 = Web3(Web3.HTTPProvider(PRODUCTION.rpc_url))

ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
CIRCLE_USDC = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
DEPOSIT = "0xEF805F1b048E803b96dacB80828ab1Da0e139fA7"

# Check USDC allowance from deposit wallet
usdc_abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"type":"function"}]
usdc = w3.eth.contract(address=CIRCLE_USDC, abi=usdc_abi)
allowance = usdc.functions.allowance(DEPOSIT, ROUTER).call()
print(f"Deposit wallet allowance for router: {allowance}")

if allowance == 0:
    print("Need to approve first!")
else:
    token_in = CIRCLE_USDC[2:].lower().zfill(64)
    token_out = USDC_E[2:].lower().zfill(64)
    fee = hex(100)[2:].zfill(64)
    rec = DEPOSIT[2:].lower().zfill(64)
    deadline = hex(int(time.time()) + 600)[2:].zfill(64)
    amount = hex(1000000)[2:].zfill(64)
    min_out = '0' * 64
    price_limit = '0' * 64

    calldata = f"0x414bf389{token_in}{token_out}{fee}{rec}{deadline}{amount}{min_out}{price_limit}"

    tx = {"from": DEPOSIT, "to": ROUTER, "data": calldata}
    try:
        result = w3.eth.call(tx)
        print(f"Swap succeeds! Output: {int(result.hex(), 16)}")
    except Exception as e:
        print(f"Swap simulation failed: {e}")
