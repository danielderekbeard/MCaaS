import sqlite3

conn = sqlite3.connect("/var/ossec/api/configuration/security/rbac.db")
cursor = conn.cursor()

# List all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print("Tables:", tables)

# For each table, show columns and rows
for table in tables:
    if table.startswith("sqlite_"):
        continue
    cursor.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cursor.fetchall()]
    print(f"\n--- {table} ---")
    print("Columns:", cols)
    cursor.execute(f"SELECT * FROM {table}")
    rows = cursor.fetchall()
    for row in rows:
        print(row)

conn.close()
