import sqlite3
import os

dbs = ['settlement', 'onboarding', 'discovery', 'metrics', 'detector', 'julius', 'referral']
base = 'backend/database'

print("=" * 60)
print("SQLite Database Health Check")
print("=" * 60)

for name in dbs:
    path = f'{base}/{name}.db'
    if os.path.exists(path):
        size = os.path.getsize(path)
        try:
            conn = sqlite3.connect(path)
            cur = conn.cursor()
            cur.execute('PRAGMA integrity_check;')
            result = cur.fetchone()[0]
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cur.fetchall()]
            conn.close()
            status = 'OK' if result == 'ok' else f'FAIL: {result}'
            print(f'\n[{status}] {name}.db')
            print(f'  Size   : {size:,} bytes')
            print(f'  Tables : {tables}')
        except Exception as e:
            print(f'\n[ERROR] {name}.db - {e}')
    else:
        print(f'\n[MISSING] {name}.db not found at {path}')

print("\n" + "=" * 60)
print("Check complete.")
print("=" * 60)
