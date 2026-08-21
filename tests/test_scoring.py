"""Live-scoring correctness for points (cricket/basketball) and sets formats."""

import json

from utils.db import get_db_connection
from utils.scoring import compute_match_scores, get_set_scores
from tests.conftest import create_round_and_match


def score(admin_client, match_id, team_id, points, event_type, counts_as_ball=1):
    return admin_client.post('/admin/matches/add-score', json={
        'match_id': match_id, 'team_id': team_id,
        'points': points, 'event_type': event_type, 'counts_as_ball': counts_as_ball,
    })


# ---------------------------------------------------------------------------
# Basketball (simple points)
# ---------------------------------------------------------------------------

def test_basketball_scoring_and_auto_live(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B')
    conn.close()

    # First score must auto-flip the match to LIVE
    r = score(admin_client, match_id, c1, 2, 'Shot', 0)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.json['new_total'] == 2

    conn = get_db_connection()
    status = conn.execute('SELECT status FROM matches WHERE id = ?', (match_id,)).fetchone()['status']
    conn.close()
    assert status == 'LIVE'

    r = score(admin_client, match_id, c1, 3, 'Shot', 0)
    assert r.json['new_total'] == 5
    r = score(admin_client, match_id, c2, 1, 'Freethrow', 0)
    assert r.json['new_total'] == 1


def test_basketball_scores_via_api(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B')
    conn.close()

    score(admin_client, match_id, c1, 2, 'Shot', 0)
    score(admin_client, match_id, c1, 2, 'Shot', 0)
    score(admin_client, match_id, c1, 3, 'Shot', 0)
    score(admin_client, match_id, c2, 1, 'Freethrow', 0)

    r = admin_client.get(f'/api/match-scores/{match_id}')
    assert r.status_code == 200
    data = r.json
    assert data['format'] == 'points'
    assert data[str(c1)]['score'] == 7
    assert data[str(c2)]['score'] == 1
    assert data['class1_id'] == c1 and data['class2_id'] == c2


# ---------------------------------------------------------------------------
# Cricket (ball-aware arithmetic)
# ---------------------------------------------------------------------------

def test_cricket_run_ball_and_overs(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Cricket Boys', '1 BCOM A', '1 BCOM B')
    conn.close()

    # 6, 4, 0 (3 balls)
    score(admin_client, match_id, c1, 6, 'Boundary')
    score(admin_client, match_id, c1, 4, 'Boundary')
    score(admin_client, match_id, c1, 0, 'Dot Ball')

    r = score(admin_client, match_id, c1, 1, 'Run')
    assert r.json['new_total'] == 11
    assert r.json['new_overs'] == 0
    assert r.json['new_balls'] == 4

    # add 2 more balls -> 0.6 (6 balls = 1 over)
    score(admin_client, match_id, c1, 1, 'Run')
    r = score(admin_client, match_id, c1, 1, 'Run')
    assert r.json['new_overs'] == 1
    assert r.json['new_balls'] == 0
    assert r.json['new_total'] == 13


def test_cricket_wide_and_no_ball_do_not_count_as_delivery(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Cricket Boys', '1 BCOM A', '1 BCOM B')
    conn.close()

    score(admin_client, match_id, c1, 1, 'Run')          # 1 legal ball
    r = admin_client.post('/admin/matches/add-score', json={
        'match_id': match_id, 'team_id': c1, 'points': 1,
        'event_type': 'Wide', 'counts_as_ball': 1,       # client bug: sends 1
    })
    assert r.status_code == 200
    # server must force counts_as_ball to 0 for wides
    assert r.json['new_total'] == 2
    assert r.json['new_balls'] == 1


def test_cricket_wicket_counts_as_delivery(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Cricket Boys', '1 BCOM A', '1 BCOM B')
    conn.close()

    r = admin_client.post('/admin/matches/add-score', json={
        'match_id': match_id, 'team_id': c1, 'points': 0,
        'event_type': 'Wicket', 'counts_as_ball': 1,
    })
    assert r.json['new_wickets'] == 1
    assert r.json['new_balls'] == 1


def test_cricket_wide_with_runs_via_complex_event(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Cricket Boys', '1 BCOM A', '1 BCOM B')
    conn.close()

    # Wide + 2 runs: 3 runs total, no legal delivery consumed
    r = admin_client.post('/admin/matches/log-complex-event', json={
        'match_id': match_id, 'team_id': c1,
        'base_event': {'label': 'Wd', 'points': 1, 'type': 'Wide', 'counts_as_ball': 0},
        'extra_runs': {'label': '+2', 'points': 2, 'type': 'Runs', 'counts_as_ball': 1},
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.json['new_total'] == 3
    assert r.json['new_balls'] == 0
    assert r.json['new_overs'] == 0

    # No-Ball + 4: 5 runs, still no legal delivery
    r = admin_client.post('/admin/matches/log-complex-event', json={
        'match_id': match_id, 'team_id': c1,
        'base_event': {'label': 'Nb', 'points': 1, 'type': 'No-Ball', 'counts_as_ball': 0},
        'extra_runs': {'label': '+4', 'points': 4, 'type': 'Runs', 'counts_as_ball': 1},
    })
    assert r.json['new_total'] == 8
    assert r.json['new_balls'] == 0

    # A normal boundary still consumes a delivery
    r = score(admin_client, match_id, c1, 4, 'Boundary')
    assert r.json['new_total'] == 12
    assert r.json['new_balls'] == 1


def test_complex_event_only_for_cricket(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B')
    conn.close()

    r = admin_client.post('/admin/matches/log-complex-event', json={
        'match_id': match_id, 'team_id': c1,
        'base_event': {'points': 1, 'type': 'Wide', 'counts_as_ball': 0},
    })
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Sets format (Volleyball / Throwball)
# ---------------------------------------------------------------------------

def _start_set_match(conn):
    return create_round_and_match(conn, 'Volleyball', '1 BCOM A', '1 BCOM B')


def test_volleyball_sets_scoring_and_end_set(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = _start_set_match(conn)
    conn.close()

    def point(team):
        return admin_client.post('/admin/matches/add-score-set', json={
            'match_id': match_id, 'team_id': team,
            'points': 1, 'event_type': 'Point', 'counts_as_ball': 0,
        })

    for _ in range(25):
        point(c1)
    for _ in range(20):
        point(c2)
    r = point(c1)
    assert r.status_code == 200
    assert r.json['new_scores']['current_set_scores'][str(c1)] == 26
    assert r.json['new_scores']['current_set_scores'][str(c2)] == 20

    # End the set
    r = admin_client.post('/admin/matches/end-set', data={'match_id': match_id})
    assert r.status_code == 302

    conn = get_db_connection()
    scores = get_set_scores(conn, match_id, c1, c2)
    conn.close()
    assert scores['sets_won'][c1] == 1
    assert scores['sets_won'][c2] == 0
    assert len(scores['completed_sets']) == 1
    assert scores['completed_sets'][0][c1] == 26


def test_end_set_rejected_on_tie(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = _start_set_match(conn)
    conn.close()

    for team in (c1, c2):
        for _ in range(10):
            admin_client.post('/admin/matches/add-score-set', json={
                'match_id': match_id, 'team_id': team,
                'points': 1, 'event_type': 'Point', 'counts_as_ball': 0,
            })

    r = admin_client.post('/admin/matches/end-set', data={'match_id': match_id}, follow_redirects=True)
    assert b'Cannot end the set: scores are tied' in r.get_data()


def test_end_set_rejected_on_empty_set(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = _start_set_match(conn)
    conn.close()
    r = admin_client.post('/admin/matches/end-set', data={'match_id': match_id}, follow_redirects=True)
    assert b'Cannot end the set: scores are tied' in r.get_data()


def test_sets_match_scores_api(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = _start_set_match(conn)
    conn.close()

    admin_client.post('/admin/matches/add-score-set', json={
        'match_id': match_id, 'team_id': c1, 'points': 1, 'event_type': 'Point', 'counts_as_ball': 0})
    admin_client.post('/admin/matches/add-score-set', json={
        'match_id': match_id, 'team_id': c1, 'points': 1, 'event_type': 'Point', 'counts_as_ball': 0})
    admin_client.post('/admin/matches/add-score-set', json={
        'match_id': match_id, 'team_id': c2, 'points': 1, 'event_type': 'Point', 'counts_as_ball': 0})

    r = admin_client.get(f'/api/match-scores/{match_id}')
    assert r.status_code == 200
    data = r.json
    assert data['format'] == 'sets_detailed'
    assert data['current_set_scores'][str(c1)] == 2
    assert data['current_set_scores'][str(c2)] == 1
    assert data['sets_won'][str(c1)] == 0


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def test_add_score_validation(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B')
    conn.close()

    # team not part of match
    r = admin_client.post('/admin/matches/add-score', json={
        'match_id': match_id, 'team_id': 9999, 'points': 2, 'event_type': 'Shot', 'counts_as_ball': 0})
    assert r.status_code == 400
    assert 'not part of this match' in r.json['error']

    # bad points
    r = admin_client.post('/admin/matches/add-score', json={
        'match_id': match_id, 'team_id': c1, 'points': 'abc', 'event_type': 'Shot', 'counts_as_ball': 0})
    assert r.status_code == 400

    # missing payload
    r = admin_client.post('/admin/matches/add-score', json=None)
    assert r.status_code == 400


def test_add_score_rejected_after_completion(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B')
    conn.close()

    score(admin_client, match_id, c1, 2, 'Shot', 0)
    score(admin_client, match_id, c2, 0, 'Shot', 0)
    r = admin_client.post(f'/admin/matches/{match_id}/finalize')
    assert r.status_code == 302

    r = score(admin_client, match_id, c1, 2, 'Shot', 0)
    assert r.status_code == 400
    assert 'completed' in r.json['error'].lower()


def test_match_scores_404(admin_client):
    r = admin_client.get('/api/match-scores/99999')
    assert r.status_code == 404
