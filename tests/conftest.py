"""Pytest fixtures: fresh temp SQLite DB + seeded Flask app per test.

The DB is built from schema.sql + the same DDL the migrations apply, so tests
are self-contained and never touch the dev database.
"""

import os
import sqlite3

import pytest

import utils.db as db
import app as app_module

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(ROOT, 'schema.sql')) as f:
    BASE_SCHEMA = f.read()

SEED_CLASSES = ['1 BCOM A', '1 BCOM B', '1 BCOM C', '5 BCOM A', 'MCOM']
SEED_SPORTS = [
    ('Cricket Boys', 1), ('Basketball (B)', 1), ('Volleyball', 1),
    ('Throwball', 1), ('Football', 1), ('Badminton', 0),
]


def build_database(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA foreign_keys = ON')
    conn.executescript(BASE_SCHEMA)
    conn.commit()
    conn.close()


def seed_database(db_path):
    conn = db.get_db_connection()
    for name in SEED_CLASSES:
        conn.execute('INSERT INTO classes (name) VALUES (?)', (name,))
    for name, has_scores in SEED_SPORTS:
        conn.execute('INSERT INTO sports (name, has_scores) VALUES (?, ?)', (name, has_scores))
    conn.commit()
    conn.close()


def get_ids(conn, sport_name, class1_name, class2_name):
    sport_id = conn.execute('SELECT id FROM sports WHERE name = ?', (sport_name,)).fetchone()['id']
    c1 = conn.execute('SELECT id FROM classes WHERE name = ?', (class1_name,)).fetchone()['id']
    c2 = conn.execute('SELECT id FROM classes WHERE name = ?', (class2_name,)).fetchone()['id']
    return sport_id, c1, c2


def create_round_and_match(conn, sport_name, class1_name, class2_name,
                           round_type='GROUP', round_name='R1',
                           match_time='2026-08-15 10:00:00'):
    """Creates a round + UPCOMING match; returns (sport_id, round_id, match_id, c1, c2)."""
    sport_id, c1, c2 = get_ids(conn, sport_name, class1_name, class2_name)
    unique_round_name = f'{round_name}-{round_type}'
    conn.execute(
        'INSERT OR IGNORE INTO rounds (sport_id, name, round_type) VALUES (?, ?, ?)',
        (sport_id, unique_round_name, round_type)
    )
    round_id = conn.execute(
        'SELECT id FROM rounds WHERE sport_id = ? AND name = ?',
        (sport_id, unique_round_name)
    ).fetchone()['id']
    conn.execute(
        'INSERT INTO matches (sport_id, round_id, class1_id, class2_id, match_time, status) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (sport_id, round_id, c1, c2, match_time, 'UPCOMING')
    )
    match_id = conn.execute('SELECT last_insert_rowid() AS id').fetchone()['id']
    conn.commit()
    return sport_id, round_id, match_id, c1, c2


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'test.db')
    monkeypatch.setattr(db, 'DB_PATH', db_path)
    build_database(db_path)
    seed_database(db_path)

    app_module.app.config['TESTING'] = True
    return app_module.app.test_client()


@pytest.fixture()
def admin_client(client):
    r = client.post('/admin/login', data={'passcode': app_module.app.config['ADMIN_PASSCODE']})
    assert r.status_code == 302
    return client


@pytest.fixture()
def conn():
    """Direct DB connection to the same temp DB the client fixture uses."""
    return db.get_db_connection()
