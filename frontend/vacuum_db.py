import sqlite3
print("Vacuuming...")
conn.execute("VACUUM")
conn.close()
print("Done!")
