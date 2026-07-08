# private_key = '9b114fd15bbabb88cd49be2c5672bb4047c416654f595e1ef566b09059184b72'
# manager_wallet = '9b114fd15bbabb88cd49be2c5672bb4047c416654f595e1ef566b09059184b72'
# USDT_CONTRACT = '9b114fd15bbabb88cd49be2c5672bb4047c416654f595e1ef566b09059184b72'
from web3 import Web3
from eth_account import Account
import json
import sqlite3
from datetime import datetime

# Configuration
private_key = '9b114fd15bbabb88cd49be2c5672bb4047c416654f595e1ef566b09059184b72'
manager_wallet = '0x3C0Cb0810f981DE369f4afE1b33b6eeed7E9E5B1'  # CORRECT ADDRESS
USDT_CONTRACT = '0x55d398326f99059fF775485246999027B3197955'

# USDT ABI
USDT_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]

print('='*60)
print('💰 FINAL TRANSFER (Gas Fee Deducted)')
print('='*60)

# 1. Get revenue from database
conn = sqlite3.connect('E:/JULIUS/data/julius.db')
conn.row_factory = sqlite3.Row

row = conn.execute("SELECT COALESCE(SUM(amount_usd), 0) as total FROM revenue_transactions").fetchone()
total_revenue = row['total'] if row else 0

print(f'\n📊 Revenue: ${total_revenue:.2f}')

if total_revenue <= 0:
    print('❌ No revenue found')
    exit()

# 2. Calculate gas fee (~$0.60 in BNB)
gas_fee_usd = 0.60
amount_to_send = total_revenue - gas_fee_usd

print(f'💸 Gas Fee (deducted): ${gas_fee_usd:.2f}')
print(f'💵 Amount to send to manager: ${amount_to_send:.2f}')

# 3. Connect to BSC
w3 = Web3(Web3.HTTPProvider('https://bsc-dataseed.binance.org/'))
w3.ens = None

account = Account.from_key(private_key)
sender_address = account.address

print(f'\n📍 Sender Address: {sender_address}')
print(f'📍 Manager Address: {manager_wallet}')

# 4. USDT contract
usdt = w3.eth.contract(address=Web3.to_checksum_address(USDT_CONTRACT), abi=USDT_ABI)

# 5. Check USDT balance
balance_usdt = usdt.functions.balanceOf(Web3.to_checksum_address(sender_address)).call()
balance_usdt_formatted = balance_usdt / 10**18

print(f'\n📈 USDT Balance: {balance_usdt_formatted:.2f} USDT')

if balance_usdt < amount_to_send:
    print(f'\n❌ Insufficient USDT')
    print(f'   Have: {balance_usdt_formatted:.2f} USDT')
    print(f'   Need: {amount_to_send:.2f} USDT')
    print('\n💡 Solution:')
    print('   1. Open Trust Wallet')
    print('   2. Tap "Swap"')
    print('   3. Select BNB → USDT')
    print('   4. Swap BNB to USDT')
    print('   5. Run this script again')
    exit()

# 6. Send USDT
amount_wei = int(amount_to_send * 10**18)
nonce = w3.eth.get_transaction_count(sender_address)
gas_price = w3.eth.gas_price
gas_estimate = usdt.functions.transfer(Web3.to_checksum_address(manager_wallet), amount_wei).estimate_gas({'from': sender_address})

tx = {
    'nonce': nonce,
    'to': Web3.to_checksum_address(USDT_CONTRACT),
    'data': usdt.encodeABI('transfer', args=[Web3.to_checksum_address(manager_wallet), amount_wei]),
    'gas': gas_estimate,
    'gasPrice': gas_price,
    'chainId': 56
}

print(f'\n🚀 Sending {amount_to_send:.2f} USDT to manager...')
signed_tx = account.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
tx_hash_hex = tx_hash.hex()

print(f'\n✅ TRANSACTION COMPLETE!')
print(f'   TX Hash: 0x{tx_hash_hex}')
print(f'   Explorer: https://bscscan.com/tx/0x{tx_hash_hex}')
print(f'   Amount sent: ${amount_to_send:.2f}')
print(f'   Gas fee: ${gas_fee_usd:.2f} (deducted from revenue)')

# 7. Record in database
conn.execute("""
    INSERT INTO revenue_transactions (transaction_type, amount_usd, complexity, scaling_multiplier, destination, created_at)
    VALUES ('final_transfer_to_manager', ?, 1.0, 1.0, 'manager_wallet', ?)
""", (amount_to_send, datetime.now().isoformat()))

conn.commit()
conn.close()

print('\n' + '='*60)
print('✅ 100% COMPLETE!')
print('='*60)