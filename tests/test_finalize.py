"""Match finalization, walkovers and undo workflows."""

from utils.db import get_db_connection
from tests.conftest import create_round_and_match


def _score(admin_client, match_id, team_id, points, event_type, counts_as_ball=1):
    return admin_client.post('/admin/matches/add-score', json={
        'match_id': match_id, 'team_id': team_id,
        'points': points, 'event_type': event_type, 'counts_as_ball': counts_as_ball,
    })


def _point(admin_client, match_id, team_id):
    return admin_client.post('/admin/matches/add-score-set', json={
        'match_id': match_id, 'team_id': team_id,
        'points': 1, 'event_type': 'Point', 'counts_as_ball': 0,
    })


def _end_set(admin_client, match_id):
    return admin_client.post('/admin/matches/end-set', data={'match_id': match_id})


def _match_row(match_id):
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM matches WHERE id = ?', (match_id,)).fetchone()
    conn.close()
    return row


# ---------------------------------------------------------------------------
# Points format
# ---------------------------------------------------------------------------

def test_finalize_points_match(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B')
    conn.close()

    for _ in range(6):
        _score(admin_client, match_id, c1, 2, 'Shot', 0)   # 12
    for _ in range(5):
        _score(admin_client, match_id, c2, 1, 'Freethrow', 0)  # 5

    r = admin_client.post(f'/admin/matches/{match_id}/finalize')
    assert r.status_code == 302

    row = _match_row(match_id)
    assert row['status'] == 'COMPLETED'
    assert row['winner_id'] == c1
    assert row['result_details'] == '1 BCOM A won 12-5'


def test_finalize_points_tie_rejected(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B')
    conn.close()

    _score(admin_client, match_id, c1, 2, 'Shot', 0)
    _score(admin_client, match_id, c1, 2, 'Shot', 0)
    _score(admin_client, match_id, c2, 2, 'Shot', 0)
    _score(admin_client, match_id, c2, 2, 'Shot', 0)

    r = admin_client.post(f'/admin/matches/{match_id}/finalize', follow_redirects=True)
    assert b'no clear winner' in r.get_data().lower()

    row = _match_row(match_id)
    assert row['status'] == 'LIVE'
    assert row['winner_id'] is None


def test_finalize_empty_points_match_rejected(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B')
    conn.close()

    r = admin_client.post(f'/admin/matches/{match_id}/finalize', follow_redirects=True)
    assert b'no clear winner' in r.get_data().lower()
    assert _match_row(match_id)['status'] == 'UPCOMING'


def test_finalize_idempotent(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B')
    conn.close()

    _score(admin_client, match_id, c1, 2, 'Shot', 0)
    r = admin_client.post(f'/admin/matches/{match_id}/finalize')
    assert r.status_code == 302

    r = admin_client.post(f'/admin/matches/{match_id}/finalize', follow_redirects=True)
    assert b'already completed' in r.get_data().lower()


# ---------------------------------------------------------------------------
# Sets format
# ---------------------------------------------------------------------------

def test_finalize_sets_match(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Volleyball', '1 BCOM A', '1 BCOM B')
    conn.close()

    # Set 1: 25-20 to c1
    for _ in range(25):
        _point(admin_client, match_id, c1)
    for _ in range(20):
        _point(admin_client, match_id, c2)
    _end_set(admin_client, match_id)

    # Set 2: 25-18 to c1
    for _ in range(25):
        _point(admin_client, match_id, c1)
    for _ in range(18):
        _point(admin_client, match_id, c2)
    _end_set(admin_client, match_id)

    r = admin_client.post(f'/admin/matches/{match_id}/finalize')
    assert r.status_code == 302

    row = _match_row(match_id)
    assert row['status'] == 'COMPLETED'
    assert row['winner_id'] == c1
    assert row['result_details'] == '1 BCOM A won 2-0 (25-20, 25-18)'


def test_finalize_sets_match_with_partial_set(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Throwball', '1 BCOM A', '1 BCOM B')
    conn.close()

    # c1 wins set 1; set 2 still in progress (10-5) when finalizing
    for _ in range(15):
        _point(admin_client, match_id, c1)
    for _ in range(10):
        _point(admin_client, match_id, c2)
    _end_set(admin_client, match_id)

    for _ in range(10):
        _point(admin_client, match_id, c1)
    for _ in range(5):
        _point(admin_client, match_id, c2)

    r = admin_client.post(f'/admin/matches/{match_id}/finalize')
    assert r.status_code == 302

    row = _match_row(match_id)
    assert row['winner_id'] == c1
    assert '2-0' in row['result_details']
    assert '(15-10, 10-5)' in row['result_details']


def test_finalize_sets_tie_rejected(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Volleyball', '1 BCOM A', '1 BCOM B')
    conn.close()

    # 1 set each
    for _ in range(25):
        _point(admin_client, match_id, c1)
    for _ in range(20):
        _point(admin_client, match_id, c2)
    _end_set(admin_client, match_id)

    for _ in range(20):
        _point(admin_client, match_id, c1)
    for _ in range(25):
        _point(admin_client, match_id, c2)
    _end_set(admin_client, match_id)

    r = admin_client.post(f'/admin/matches/{match_id}/finalize', follow_redirects=True)
    assert b'no clear winner' in r.get_data().lower()
    assert _match_row(match_id)['status'] == 'LIVE'


# ---------------------------------------------------------------------------
# Walkover
# ---------------------------------------------------------------------------

def test_walkover_declaration(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Badminton', '1 BCOM A', '1 BCOM B')
    conn.close()

    r = admin_client.post(f'/admin/matches/{match_id}/walkover', data={'loser_id': c2})
    assert r.status_code == 302

    row = _match_row(match_id)
    assert row['status'] == 'COMPLETED'
    assert row['winner_id'] == c1
    assert 'Walkover' in row['result_details']

    conn = get_db_connection()
    adj = conn.execute('SELECT points FROM point_adjustments WHERE class_id = ?', (c2,)).fetchone()
    conn.close()
    assert adj['points'] == -3


def test_walkover_invalid_loser(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Badminton', '1 BCOM A', '1 BCOM B')
    conn.close()

    r = admin_client.post(f'/admin/matches/{match_id}/walkover', data={'loser_id': 9999}, follow_redirects=True)
    assert b'not part of this match' in r.get_data().lower()
    assert _match_row(match_id)['status'] == 'UPCOMING'


def test_walkover_on_completed_match_blocked(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Badminton', '1 BCOM A', '1 BCOM B')
    conn.close()

    admin_client.post(f'/admin/matches/{match_id}/walkover', data={'loser_id': c2})
    r = admin_client.post(f'/admin/matches/{match_id}/walkover', data={'loser_id': c1}, follow_redirects=True)
    assert b'already completed' in r.get_data().lower()
    assert _match_row(match_id)['winner_id'] == c1


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------

def test_undo_last_event(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B')
    conn.close()

    _score(admin_client, match_id, c1, 2, 'Shot', 0)
    _score(admin_client, match_id, c1, 3, 'Shot', 0)
    _score(admin_client, match_id, c2, 1, 'Freethrow', 0)

    admin_client.post(f'/admin/matches/{match_id}/undo')
    conn = get_db_connection()
    scores = conn.execute('SELECT points_scored, team_id FROM score_log WHERE match_id = ? ORDER BY id', (match_id,)).fetchall()
    conn.close()
    assert [(s['team_id'], s['points_scored']) for s in scores] == [(c1, 2), (c1, 3)]


def test_undo_blocked_on_completed(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B')
    conn.close()

    _score(admin_client, match_id, c1, 2, 'Shot', 0)
    admin_client.post(f'/admin/matches/{match_id}/finalize')

    r = admin_client.post(f'/admin/matches/{match_id}/undo', follow_redirects=True)
    assert b'Cannot undo events on a completed match' in r.get_data()

    conn = get_db_connection()
    count = conn.execute('SELECT COUNT(*) AS n FROM score_log WHERE match_id = ?', (match_id,)).fetchone()['n']
    conn.close()
    assert count == 1
