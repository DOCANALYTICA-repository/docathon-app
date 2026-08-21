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
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        missing = {'sports', 'classes', 'matches'} - tables
        if missing:
            raise RuntimeError(
                'Missing base tables: ' + ', '.join(sorted(missing))
            )

        conn.execute('''
            CREATE TABLE IF NOT EXISTS rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sport_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                round_type TEXT NOT NULL CHECK (round_type IN (
                    'GROUP', 'KNOCKOUT', 'QUARTER_FINAL', 'SEMI_FINAL', 'FINAL'
                )),
                FOREIGN KEY (sport_id) REFERENCES sports(id)
                    ON UPDATE CASCADE ON DELETE RESTRICT,
                UNIQUE (sport_id, name)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS point_adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id INTEGER NOT NULL,
                points INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (class_id) REFERENCES classes(id)
                    ON UPDATE CASCADE ON DELETE RESTRICT
            )
        ''')
        columns = {row[1] for row in conn.execute('PRAGMA table_info(matches)')}
        if 'round_id' not in columns:
            conn.execute('ALTER TABLE matches ADD COLUMN round_id INTEGER')
        if 'scorecard_url' not in columns:
            conn.execute('ALTER TABLE matches ADD COLUMN scorecard_url TEXT')
        if 'live_match_state' not in columns:
            conn.execute('ALTER TABLE matches ADD COLUMN live_match_state TEXT')

        # Older matches have no round association. Put them in one stable
        # migrated group round per sport so the application's required JOIN
        # to rounds does not hide existing match data.
        legacy_matches = conn.execute(
            'SELECT DISTINCT sport_id FROM matches WHERE round_id IS NULL'
        ).fetchall()
        for (sport_id,) in legacy_matches:
            conn.execute(
                'INSERT OR IGNORE INTO rounds (sport_id, name, round_type) '
                "VALUES (?, 'Migrated', 'GROUP')",
                (sport_id,)
            )
            round_id = conn.execute(
                'SELECT id FROM rounds WHERE sport_id = ? AND name = ?',
                (sport_id, 'Migrated')
            ).fetchone()[0]
            conn.execute(
                'UPDATE matches SET round_id = ? '
                'WHERE sport_id = ? AND round_id IS NULL',
                (round_id, sport_id)
            )

        conn.execute('CREATE INDEX IF NOT EXISTS idx_matches_round_id ON matches(round_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_point_adjustments_class_id ON point_adjustments(class_id)')
        conn.commit()
        print('Migration 003 applied successfully.')
        return True
    except (sqlite3.Error, OSError, RuntimeError) as exc:
        if conn is not None:
            conn.rollback()
        print(f'Migration 003 failed: {exc}')
        return False
    finally:
        if conn is not None:
            conn.close()


if __name__ == '__main__':
    raise SystemExit(0 if apply_migration() else 1)
