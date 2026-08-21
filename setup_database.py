import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_FOLDER = BASE_DIR / 'db'
DB_PATH = DB_FOLDER / 'docathon.db'
SCHEMA_PATH = BASE_DIR / 'schema.sql'

REQUIRED_TABLES = {
    'classes', 'sports', 'rounds', 'matches', 'score_log',
    'point_adjustments', 'stories', 'team_members',
}

REQUIRED_COLUMNS = {
    'classes': {'id', 'name'},
    'sports': {'id', 'name', 'has_scores'},
    'rounds': {'id', 'sport_id', 'name', 'round_type'},
    'matches': {
        'id', 'sport_id', 'round_id', 'class1_id', 'class2_id',
        'winner_id', 'result_details', 'status', 'match_time', 'notes',
        'scorecard_url', 'live_match_state',
    },
    'score_log': {
        'id', 'match_id', 'team_id', 'points_scored', 'event_type',
        'counts_as_ball', 'created_at',
    },
    'point_adjustments': {'id', 'class_id', 'points', 'reason', 'created_at'},
    'stories': {'id', 'title', 'content', 'author', 'image_filename', 'created_at'},
    'team_members': {'id', 'name', 'role', 'photo_filename'},
}


def verify_database(conn):
    cursor = conn.cursor()
    actual_tables = {
        row[0] for row in cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    missing_tables = REQUIRED_TABLES - actual_tables
    if missing_tables:
        raise RuntimeError(
            'Database is missing required tables: '
            + ', '.join(sorted(missing_tables))
        )

    missing_columns = {}
    for table, expected in REQUIRED_COLUMNS.items():
        actual = {
            row[1] for row in cursor.execute(f'PRAGMA table_info("{table}")')
        }
        missing = expected - actual
        if missing:
            missing_columns[table] = sorted(missing)
    if missing_columns:
        details = '; '.join(
            f'{table}: {", ".join(columns)}'
            for table, columns in sorted(missing_columns.items())
        )
        raise RuntimeError(f'Database is missing required columns: {details}')

    if cursor.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
        raise RuntimeError('SQLite foreign-key enforcement is not enabled.')
    if cursor.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise RuntimeError('SQLite integrity check failed.')
    foreign_key_errors = cursor.execute('PRAGMA foreign_key_check').fetchall()
    if foreign_key_errors:
        raise RuntimeError(
            'SQLite foreign-key check failed: ' + repr(foreign_key_errors[:10])
        )


def setup_database():
    DB_FOLDER.mkdir(parents=True, exist_ok=True)
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f'Schema file not found: {SCHEMA_PATH}')

    db_existed = DB_PATH.exists()
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('PRAGMA foreign_keys = ON')
        conn.executescript(SCHEMA_PATH.read_text(encoding='utf-8'))
        verify_database(conn)
        conn.commit()
        print(f'Database setup completed: {DB_PATH}')
        return True
    except (sqlite3.Error, OSError, RuntimeError) as exc:
        if conn is not None:
            conn.rollback()
        print(f'Database setup failed: {exc}')
        if db_existed:
            print('Run migrations for an older existing database.')
        return False
    finally:
        if conn is not None:
            conn.close()


if __name__ == '__main__':
    raise SystemExit(0 if setup_database() else 1)
