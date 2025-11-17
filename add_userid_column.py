import sqlite3

db_path = 'instance/expenses.db'  # CHANGE this if your location differs

conn = sqlite3.connect(db_path)
cur = conn.cursor()
try:
    cur.execute("PRAGMA foreign_keys = OFF;")
    cur.execute("ALTER TABLE expense ADD COLUMN user_id INTEGER;")
    conn.commit()
    print("Column added successfully.")
except Exception as e:
    print("Error:", e)
finally:
    conn.close()
