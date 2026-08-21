import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'db' / 'docathon.db'


def column_names(cursor, table_name):
    cursor.execute(f'PRAGMA table_info("{table_name}")')
    return {row[1] for row in cursor.fetchall()}


def table_exists(cursor, table_name):
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def apply_migration():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('BEGIN')
        cursor = conn.cursor()
        missing = [
            table for table in ('classes', 'matches')
            if not table_exists(cursor, table)
        ]
        if missing:
            raise RuntimeError(
                'Missing base table(s): ' + ', '.join(missing)
                + '. Run setup_database.py or restore the base schema first.'
            )

        if not table_exists(cursor, 'score_log'):
            cursor.execute('''
                CREATE TABLE score_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id INTEGER NOT NULL,
                    team_id INTEGER NOT NULL,
                    points_scored INTEGER NOT NULL DEFAULT 0,
                    event_type TEXT NOT NULL,
                    counts_as_ball INTEGER NOT NULL DEFAULT 0
                        CHECK (counts_as_ball IN (0, 1)),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (match_id) REFERENCES matches(id)
                        ON UPDATE CASCADE ON DELETE CASCADE,
                    FOREIGN KEY (team_id) REFERENCES classes(id)
                        ON UPDATE CASCADE ON DELETE RESTRICT
                )
            ''')
        else:
            columns = column_names(cursor, 'score_log')
            if 'counts_as_ball' not in columns:
                cursor.execute(
                    'ALTER TABLE score_log ADD COLUMN counts_as_ball '
                    'INTEGER NOT NULL DEFAULT 0 CHECK (counts_as_ball IN (0, 1))'
                )
            if 'points_scored' not in columns:
                cursor.execute(
                    'ALTER TABLE score_log ADD COLUMN points_scored '
                    'INTEGER NOT NULL DEFAULT 0'
                )

        if 'live_match_state' not in column_names(cursor, 'matches'):
            cursor.execute('ALTER TABLE matches ADD COLUMN live_match_state TEXT')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_score_log_match_id ON score_log(match_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_score_log_team_id ON score_log(team_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_score_log_created_at ON score_log(created_at)')
        conn.commit()
        print('Migration 001 applied successfully.')
        return True
    except (sqlite3.Error, OSError, RuntimeError) as exc:
        if conn is not None:
            conn.rollback()
        print(f'Migration 001 failed: {exc}')
        return False
    finally:
        if conn is not None:
            conn.close()


if __name__ == '__main__':
    raise SystemExit(0 if apply_migration() else 1)
