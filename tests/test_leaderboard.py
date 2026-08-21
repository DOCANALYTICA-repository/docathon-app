"""Leaderboard / point calculations, point adjustments and public APIs."""

from utils.db import get_db_connection
from utils.scoring import compute_leaderboard
from tests.conftest import create_round_and_match


def _complete_match(conn, sport_name, a, b, winner_idx, round_type='GROUP'):
    _, _, match_id, c1, c2 = create_round_and_match(conn, sport_name, a, b, round_type=round_type)
    winner = c1 if winner_idx == 0 else c2
    conn.execute(
        "UPDATE matches SET status = 'COMPLETED', winner_id = ?, result_details = 'X won' WHERE id = ?",
        (winner, match_id)
    )
    conn.commit()
    return match_id


def _leaderboard_dict(standings):
    return {s['class_id']: s for s in standings}


def test_leaderboard_tournament_points(admin_client):
    conn = get_db_connection()
    # A beats B (QF), A beats C (SF), A beats D (FINAL)
    _complete_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B', 0, 'QUARTER_FINAL')
    _complete_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM C', 0, 'SEMI_FINAL')
    _complete_match(conn, 'Basketball (B)', '1 BCOM A', '5 BCOM A', 0, 'FINAL')
    conn.close()

    conn = get_db_connection()
    standings = compute_leaderboard(conn)
    conn.close()
    lb = _leaderboard_dict(standings)

    # A: 5 (final win) + 3 win points + 1 participation = 9
    assert lb[1]['total_points'] == 9
    assert lb[1]['wins'] == 3
    # D lost the final -> 4 + 1 participation = 5
    assert lb[4]['total_points'] == 5
    # C lost SF -> 3 + 1 = 4
    assert lb[3]['total_points'] == 4
    # B lost QF -> 2 + 1 = 3
    assert lb[2]['total_points'] == 3

    ranks = {s['class_name']: s['rank'] for s in standings}
    assert ranks['1 BCOM A'] < ranks['5 BCOM A'] < ranks['1 BCOM C'] < ranks['1 BCOM B']


def test_leaderboard_participation_and_ties(admin_client):
    conn = get_db_connection()
    # A beats B in the basketball final, C beats D in the badminton final
    _complete_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B', 0, 'FINAL')
    _complete_match(conn, 'Badminton', '1 BCOM C', '5 BCOM A', 0, 'FINAL')
    conn.close()

    conn = get_db_connection()
    standings = compute_leaderboard(conn)
    conn.close()
    lb = _leaderboard_dict(standings)
    # winners: 5 (final win) + 1 win + 1 participation = 7
    assert lb[1]['total_points'] == 7
    assert lb[3]['total_points'] == 7
    # runners-up: 4 + 0 + 1 = 5
    assert lb[2]['total_points'] == 5
    assert lb[4]['total_points'] == 5


def test_point_adjustments_applied(admin_client):
    conn = get_db_connection()
    _complete_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B', 0, 'QUARTER_FINAL')
    conn.close()

    admin_client.post('/admin/adjustments', data={'class_id': 2, 'points': -3, 'reason': 'Walkover penalty'})
    admin_client.post('/admin/adjustments', data={'class_id': 2, 'points': 5, 'reason': 'Re-evaluation'})

    conn = get_db_connection()
    standings = compute_leaderboard(conn)
    conn.close()
    lb = _leaderboard_dict(standings)
    assert lb[2]['total_points'] == 5  # 2 (QF loss) + 1 (participation) - 3 + 5


def test_adjustment_validation(admin_client):
    r = admin_client.post('/admin/adjustments', data={'class_id': 1, 'points': 'abc', 'reason': 'x'}, follow_redirects=True)
    assert b'Points must be a valid number' in r.get_data()

    r = admin_client.post('/admin/adjustments', data={'class_id': 1, 'points': '', 'reason': 'x'}, follow_redirects=True)
    assert b'All fields are required' in r.get_data()


def test_delete_adjustment(admin_client):
    conn = get_db_connection()
    _complete_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B', 0, 'QUARTER_FINAL')
    conn.close()
    admin_client.post('/admin/adjustments', data={'class_id': 2, 'points': -3, 'reason': 'Walkover penalty'})

    conn = get_db_connection()
    adj_id = conn.execute('SELECT id FROM point_adjustments LIMIT 1').fetchone()['id']
    conn.close()

    admin_client.post(f'/admin/adjustments/{adj_id}/delete')
    conn = get_db_connection()
    count = conn.execute('SELECT COUNT(*) AS n FROM point_adjustments').fetchone()['n']
    conn.close()
    assert count == 0


def test_leaderboard_api(admin_client):
    conn = get_db_connection()
    _complete_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B', 0, 'QUARTER_FINAL')
    conn.close()

    r = admin_client.get('/api/leaderboard')
    assert r.status_code == 200
    data = r.json
    assert 'standings' in data and 'updated_at' in data
    lb = {s['class_id']: s for s in data['standings']}
    # QF winner A: 1 win + 1 participation = 2
    assert lb[1]['class_name'] == '1 BCOM A'
    assert lb[1]['total_points'] == 2
    # QF loser B: 2 placement + 1 participation = 3 (reaching a round is rewarded)
    assert lb[2]['class_name'] == '1 BCOM B'
    assert lb[2]['total_points'] == 3
    assert set(lb[1].keys()) >= {'rank', 'class_id', 'class_name', 'played', 'wins', 'losses', 'total_points'}


def test_matches_api_filters(admin_client):
    conn = get_db_connection()
    _, _, m1, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B', round_type='QUARTER_FINAL')
    conn.close()

    r = admin_client.get('/api/matches')
    assert r.status_code == 200
    assert len(r.json['matches']) == 1
    assert r.json['matches'][0]['id'] == m1

    r = admin_client.get('/api/matches?status=UPCOMING')
    assert len(r.json['matches']) == 1
    r = admin_client.get('/api/matches?status=COMPLETED')
    assert len(r.json['matches']) == 0

    r = admin_client.get(f'/api/matches?class_id={c1}')
    assert len(r.json['matches']) == 1
    r = admin_client.get('/api/matches?class_id=9999')
    assert len(r.json['matches']) == 0
