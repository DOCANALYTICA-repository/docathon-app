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
            CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                author TEXT,
                image_filename TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        columns = {row[1] for row in conn.execute('PRAGMA table_info(stories)')}
        if 'image_filename' not in columns:
            conn.execute('ALTER TABLE stories ADD COLUMN image_filename TEXT')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_stories_created_at ON stories(created_at)')
        conn.commit()
        print('Migration 004 applied successfully.')
        return True
    except (sqlite3.Error, OSError) as exc:
        if conn is not None:
            conn.rollback()
        print(f'Migration 004 failed: {exc}')
        return False
    finally:
        if conn is not None:
            conn.close()


if __name__ == '__main__':
    raise SystemExit(0 if apply_migration() else 1)
