import sqlite3

from seed import mock_data
from tests.conftest import build_database


def test_mock_seed_populates_required_demo_records(tmp_path):
    db_path = tmp_path / 'mock.db'
    build_database(str(db_path))

    summary = mock_data.seed_mock_data(db_path)
    assert summary['matches'] == 6

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    assert conn.execute("SELECT COUNT(*) FROM matches WHERE notes = ?", (mock_data.MOCK_MARKER,)).fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM score_log").fetchone()[0] > 0
    assert conn.execute("SELECT COUNT(*) FROM stories WHERE title LIKE ?", (f'{mock_data.MOCK_MARKER}%',)).fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM team_members WHERE role LIKE ?", (f'{mock_data.MOCK_MARKER}%',)).fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM point_adjustments WHERE reason LIKE ?", (f'{mock_data.MOCK_MARKER}%',)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM rounds WHERE name LIKE ? AND round_type = 'FINAL'", (f'{mock_data.MOCK_MARKER}%',)).fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM matches WHERE notes = ? AND status = 'COMPLETED' AND winner_id IS NOT NULL", (mock_data.MOCK_MARKER,)).fetchone()[0] == 4
    conn.close()


def test_mock_seed_is_idempotent_and_clear_is_selective(tmp_path):
    db_path = tmp_path / 'mock.db'
    build_database(str(db_path))
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO stories (title, content, author) VALUES ('Keep this story', 'Existing content', 'Tester')")
    conn.commit()
    conn.close()

    mock_data.seed_mock_data(db_path)
    mock_data.seed_mock_data(db_path)

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM matches WHERE notes = ?", (mock_data.MOCK_MARKER,)).fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM stories WHERE title LIKE ?", (f'{mock_data.MOCK_MARKER}%',)).fetchone()[0] == 2
    conn.close()

    conn = sqlite3.connect(db_path)
    mock_data.clear_mock_data(conn)
    assert conn.execute("SELECT COUNT(*) FROM matches WHERE notes = ?", (mock_data.MOCK_MARKER,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM stories WHERE title LIKE ?", (f'{mock_data.MOCK_MARKER}%',)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM stories WHERE title = 'Keep this story'").fetchone()[0] == 1
    conn.close()
