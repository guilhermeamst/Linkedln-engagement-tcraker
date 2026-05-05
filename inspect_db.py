import sqlite3

db_path = "linkedin_engagement.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables in database:")
for table in tables:
    print(f"  - {table[0]}")

# Get schema for each table
print("\n" + "="*60)
for table in tables:
    print(f"\nTable: {table[0]}")
    cursor.execute(f"PRAGMA table_info({table[0]})")
    columns = cursor.fetchall()
    for col in columns:
        print(f"  {col[1]} ({col[2]})")

conn.close()
