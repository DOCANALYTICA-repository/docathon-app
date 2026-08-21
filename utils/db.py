import sqlite3
import os

# Get the absolute path to the directory where this file (db.py) is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Construct the full path to the database file
DB_PATH = os.path.join(BASE_DIR, '..', 'db', 'docathon.db')

def get_db_connection():
    """Establishes a connection to the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON')
    # This allows you to access columns by name (like a dictionary)
    conn.row_factory = sqlite3.Row
    return conn