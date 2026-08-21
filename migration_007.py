import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'db' / 'docathon.db'


def apply_migration():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('BEGIN')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                photo_filename TEXT
            )
        ''')
        columns = {row[1] for row in conn.execute('PRAGMA table_info(team_members)')}
        if 'photo_filename' not in columns:
            conn.execute('ALTER TABLE team_members ADD COLUMN photo_filename TEXT')
        conn.commit()
        print('Migration 007 applied successfully.')
        return True
    except (sqlite3.Error, OSError) as exc:
        if conn is not None:
            conn.rollback()
        print(f'Migration 007 failed: {exc}')
        return False
    finally:
        if conn is not None:
            conn.close()


if __name__ == '__main__':
    raise SystemExit(0 if apply_migration() else 1)
