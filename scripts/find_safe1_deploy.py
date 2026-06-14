from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
w3 = Web3(Web3.HTTPProvider("https://polygon.drpc.org"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

factory = Web3.to_checksum_address("0xa6B71E26C5e0845f74c812102Ca7114b6a896AB2")
safe1 = Web3.to_checksum_address("0xde9C54c6D3faa7e7Cc0eDe3D21257c8775cE8397")
proxy_creation_topic = Web3.keccak(text="ProxyCreation(address,address)")

latest = w3.eth.block_number
logs = w3.eth.get_logs({
    "address": factory,
    "fromBlock": latest - 5000,
    "toBlock": "latest",
    "topics": [proxy_creation_topic.hex()]
})
print(f"Found {len(logs)} ProxyCreation events in last 5000 blocks")
for log in logs:
    proxy = Web3.to_checksum_address("0x" + log["topics"][1].hex()[-40:])
    singleton = Web3.to_checksum_address("0x" + log["topics"][2].hex()[-40:])
    if proxy == safe1:
        print(f"FOUND Safe1! Singleton: {singleton}")
        print(f"Block: {log['blockNumber']}")
        tx_hash = log["transactionHash"].hex()
        print(f"Tx: {tx_hash}")
        # Check the tx input to see setup data
        tx = w3.eth.get_transaction(tx_hash)
        print(f"Input: {tx['input'][:200]}...")
        break
