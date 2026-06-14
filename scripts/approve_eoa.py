from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web3 import Web3
from polymarket.environments import PRODUCTION as PROD
from bot.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("approve_eoa")

PUSD = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
EXCHANGES = [
    "0xE111180000d2663C0091e4f400237545B87B996B",
    "0xe2222d279d744050d28e00520010520000310F59",
    "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
]

def main() -> int:
    settings = load_settings()
    w3 = Web3(Web3.HTTPProvider(PROD.rpc_url))
    acct = w3.eth.account.from_key(settings.private_key)
    logger.info("Signer: %s", acct.address)

    pusd = w3.eth.contract(
        address=Web3.to_checksum_address(PUSD),
        abi=[{"constant":False,"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"}],
    )

    for ex in EXCHANGES:
        spender = Web3.to_checksum_address(ex)
        tx = pusd.functions.approve(spender, 2**256 - 1).build_transaction({
            "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address),
            "gas": 100000, "gasPrice": w3.eth.gas_price, "chainId": 137,
        })
        signed = acct.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        logger.info("Approved %s: %s", ex, receipt["status"] == 1)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
