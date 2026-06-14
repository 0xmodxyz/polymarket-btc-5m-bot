from web3 import Web3
from eth_account.messages import encode_defunct

w3 = Web3(Web3.HTTPProvider('https://polygon.drpc.org'))

# Safe v1.3.0 typehashes
DOMAIN_SEPARATOR_TYPEHASH = '0x47e79534a245952e8b16893a336b85a3d9ea9fa8c573f3d803afb92a79469218'
SAFE_TX_TYPEHASH = Web3.keccak(text='SafeTx(address to,uint256 value,bytes data,uint8 operation,uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,address gasToken,address refundReceiver,uint256 nonce)')
print(f'safe_tx_typehash: {SAFE_TX_TYPEHASH.hex()}')

safe = Web3.to_checksum_address('0x53cac4079f996a4caa76db02f7320ef806d924b6')
chain_id = 137

# domainSeparator = keccak256(abi.encode(DOMAIN_SEPARATOR_TYPEHASH, chainId, verifyingContract))
domain_separator = Web3.solidity_keccak(
    ['bytes32', 'uint256', 'address'],
    [Web3.to_bytes(hexstr=DOMAIN_SEPARATOR_TYPEHASH), chain_id, safe]
)
print(f'domain_separator: {domain_separator.hex()}')

# Set up a test execTransaction
to = Web3.to_checksum_address('0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB')  # pUSD
value = 0
data = '0x095ea7b3000000000000000000000000e111180000d2663c0091e4f400237545b87b996bffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'
operation = 0
safe_tx_gas = 0
base_gas = 0
gas_price = 0
gas_token = '0x0000000000000000000000000000000000000000'
refund_receiver = '0x0000000000000000000000000000000000000000'
nonce = 0

# txHashData = keccak256(abi.encode(SAFE_TX_TYPEHASH, to, value, keccak256(data), operation, safeTxGas, baseGas, gasPrice, gasToken, refundReceiver, nonce))
keccak_data = Web3.keccak(hexstr=data)
print(f'keccak(data): {keccak_data.hex()}')

tx_hash_data = Web3.solidity_keccak(
    ['bytes32', 'address', 'uint256', 'bytes32', 'uint8', 'uint256', 'uint256', 'uint256', 'address', 'address', 'uint256'],
    [Web3.to_bytes(hexstr=SAFE_TX_TYPEHASH.hex()), to, value, keccak_data, operation, safe_tx_gas, base_gas, gas_price, Web3.to_checksum_address(gas_token), Web3.to_checksum_address(refund_receiver), nonce]
)
print(f'tx_hash_data: {tx_hash_data.hex()}')

# safeTxHash = keccak256(abi.encodePacked(byte(0x19), byte(0x01), domainSeparator, txHashData))
safe_tx_hash = Web3.solidity_keccak(
    ['bytes', 'bytes', 'bytes', 'bytes'],
    [b'\x19\x01', domain_separator, tx_hash_data]
)
print(f'safe_tx_hash: {safe_tx_hash.hex()}')

# Now sign it
key = 'YOUR_PRIVATE_KEY_HERE'
# Use the actual key from .env
import os
from dotenv import load_dotenv
load_dotenv()
key = os.getenv('PRIVATE_KEY')
if not key:
    print('No PRIVATE_KEY in .env')
    exit()

account = w3.eth.account.from_key(key)
print(f'Signer: {account.address}')

# Sign the safe_tx_hash using personal_sign format
message = encode_defunct(safe_tx_hash)
signed = w3.eth.account.sign_message(message, private_key=key)
print(f'\nStandard signature:')
print(f'  v = {signed.v}')
print(f'  r = 0x{signed.r.to_bytes(32, \"big\").hex()}')
print(f'  s = 0x{signed.s.to_bytes(32, \"big\").hex()}')

# For Safe format, add 4 to v
v_safe = signed.v + 4
print(f'\nSafe format signature:')
print(f'  v = {v_safe}')
print(f'  r = 0x{signed.r.to_bytes(32, \"big\").hex()}')
print(f'  s = 0x{signed.s.to_bytes(32, \"big\").hex()}')
print(f'  signatures = 0x{signed.r.to_bytes(32, \"big\").hex()}{signed.s.to_bytes(32, \"big\").hex()}{v_safe.to_bytes(1, \"big\").hex().zfill(64)}')

# Verify recovery
from eth_account.messages import _hash_eip191_message
message_hash = _hash_eip191_message(message)
recovered = w3.eth.account.recover_message(message, signature=signed.signature)
print(f'\nRecovered (standard): {recovered}')
print(f'Matches signer: {recovered == account.address}')

# Check if we need to adjust v somewhere
# The Safe does: ecrecover(messageHash, v - 4, r, s)
# So if v=31, v-4=27 which is correct for ecrecover
print(f'\nSafe ecrecover check: v-4 = {v_safe - 4} (should be 27 or 28)')
