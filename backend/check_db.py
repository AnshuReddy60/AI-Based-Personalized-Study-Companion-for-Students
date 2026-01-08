import sqlite3
import pandas as pd

# Connect to your SQLite database
conn = sqlite3.connect('users.db')

# Get all table names
tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", conn)
print("Tables in database:", tables['name'].tolist())

# Function to display table neatly
def show_table(table_name):
    print(f"\nData in table: {table_name}")
    try:
        df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
        if df.empty:
            print("Table is empty.")
        else:
            print(df)
    except Exception as e:
        print("Error:", e)

# Example: show all tables
for table in tables['name']:
    show_table(table)

# Close the connection
conn.close()
