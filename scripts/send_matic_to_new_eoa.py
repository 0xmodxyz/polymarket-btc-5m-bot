from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
w3 = Web3(Web3.HTTPProvider("https://polygon.drpc.org"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

OLD_PK = "0x6a90c9de864eea2aef2a5d348a37579541a3be423d73053586e9d3ccfbaa8514"
old_acct = w3.eth.account.from_key(OLD_PK)
new_eoa = Web3.to_checksum_address("0xb802951782bF31D2256479717DDF185De0902054")

print(f"Old EOA: {old_acct.address}")
print(f"Sending 0.5 MATIC to new EOA...")

tx = {"to": new_eoa, "value": w3.to_wei(0.5, "ether"), "gas": 21000, "gasPrice": w3.eth.gas_price, "nonce": w3.eth.get_transaction_count(old_acct.address), "chainId": w3.eth.chain_id}
signed = old_acct.sign_transaction(tx)
h = w3.eth.send_raw_transaction(signed.raw_transaction)
r = w3.eth.wait_for_transaction_receipt(h, timeout=120)
print(f"Sent: {h.hex()} (status={r['status'] == 1})")
print(f"New EOA now: {w3.from_wei(w3.eth.get_balance(new_eoa), 'ether')} ETH")
