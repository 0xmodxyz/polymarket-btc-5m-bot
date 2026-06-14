from __future__ import annotations

import logging, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web3 import Web3
from polymarket.environments import PRODUCTION as PROD
from bot.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("transfer_pusd_back")

PUSD = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"

def main() -> int:
    settings = load_settings()
    w3 = Web3(Web3.HTTPProvider(PROD.rpc_url))
    acct = w3.eth.account.from_key(settings.private_key)

    dw = settings.deposit_wallet_address
    logger.info("EOA: %s", acct.address)
    logger.info("Deposit wallet: %s", dw)

    bal_abi = [{"constant":True,"inputs":[{"name":"who","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"}]
    bal_contract = w3.eth.contract(address=Web3.to_checksum_address(PUSD), abi=bal_abi)
    bal = bal_contract.functions.balanceOf(acct.address).call()
    logger.info("EOA pUSD balance: %s", bal)

    pusd = w3.eth.contract(
        address=Web3.to_checksum_address(PUSD),
        abi=[{"constant":False,"inputs":[{"name":"to","type":"address"},{"name":"value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function"}],
    )

    if bal == 0:
        logger.info("Nothing to transfer")
        return 0

    tx = pusd.functions.transfer(Web3.to_checksum_address(dw), bal).build_transaction({
        "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": 100000, "gasPrice": w3.eth.gas_price, "chainId": 137,
    })
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    logger.info("Transfer done! Tx: %s, status: %s", tx_hash.hex(), receipt["status"] == 1)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
