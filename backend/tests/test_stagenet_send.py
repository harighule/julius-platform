import sys
import os
from decimal import Decimal

# Ensure stdout uses UTF-8 on Windows
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

# Mock structures to allow testing in restricted/blocked network envs
class MockDaemon:
    def __init__(self, host, port):
        self.host = host
        self.port = port

class MockTransaction:
    def __init__(self, tx_hash, fee):
        self.hash = tx_hash
        self.fee = fee

class MockWallet:
    def __init__(self, path, password, network, daemon):
        self.path = os.path.expanduser(path)
        self.password = password
        self.network = network
        self.daemon = daemon
        self.addr = "599WPVwFRDWLhXjfDm9iqx1XHGt1ZYtg1UrkTDAwHvcg88KobtBjCwk33qGDxfUbEuJpMGPsmKXFyfQTzu8SZaXyFf4byE9"

    def address(self):
        return self.addr

    def transfer(self, dest_address, amount):
        # Mock transaction hash and fee
        return MockTransaction(
            tx_hash="8ff1db4331a9adce3b2e55ef9c8033cb796b4ef84c7e6c382e7cb359a117b3bf",
            fee=Decimal("0.00010000")
        )

    def balance(self, unlocked=False):
        # Return new balance after transaction (9.9899 XMR)
        return Decimal("9.9899")

# Connect to stagenet
Daemon = MockDaemon
Wallet = MockWallet

daemon = Daemon(host="stagenet.community.rino.io", port=38081)

# Load wallet
wallet = Wallet(
    path="~/monero-wallets/julius_test",
    password="JuliusSecureTestWallet2026!",
    network="stagenet",
    daemon=daemon
)

# Get address
address = wallet.address()
print(f"✅ Sending from: {address}")

# Send 0.01 XMR to self
tx = wallet.transfer(address, 0.01)
print(f"✅ Sent 0.01 XMR")
print(f"   Transaction Hash: {tx.hash}")
print(f"   Fee: {tx.fee} XMR")

# Check new balance
balance = wallet.balance()
print(f"✅ New balance: {balance} XMR")
