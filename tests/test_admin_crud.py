"""Admin CRUD workflows against the repaired model."""

from utils.db import get_db_connection
from tests.conftest import create_round_and_match


# ---------------------------------------------------------------------------
# Rounds
# ---------------------------------------------------------------------------

def test_round_crud(admin_client):
    conn = get_db_connection()
    sport_id = conn.execute("SELECT id FROM sports WHERE name = 'Basketball (B)'").fetchone()['id']
    conn.close()

    # create
    r = admin_client.post('/admin/rounds/new', data={'sport_id': sport_id, 'name': 'QF 1', 'round_type': 'QUARTER_FINAL'}, follow_redirects=True)
    assert b'Round created successfully' in r.get_data()

    conn = get_db_connection()
    row = conn.execute("SELECT * FROM rounds WHERE name = 'QF 1'").fetchone()
    assert row['round_type'] == 'QUARTER_FINAL'
    round_id = row['id']
    conn.close()

    # edit
    r = admin_client.post(f'/admin/rounds/{round_id}/edit', data={'name': 'QF 1x', 'round_type': 'SEMI_FINAL'}, follow_redirects=True)
    assert b'Round updated successfully' in r.get_data()
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM rounds WHERE id = ?', (round_id,)).fetchone()
    conn.close()
    assert row['name'] == 'QF 1x' and row['round_type'] == 'SEMI_FINAL'

    # delete (no matches attached)
    r = admin_client.post(f'/admin/rounds/{round_id}/delete', follow_redirects=True)
    assert b'Round deleted successfully' in r.get_data()
    conn = get_db_connection()
    assert conn.execute('SELECT COUNT(*) AS n FROM rounds WHERE id = ?', (round_id,)).fetchone()['n'] == 0
    conn.close()


def test_round_create_validation(admin_client):
    r = admin_client.post('/admin/rounds/new', data={'sport_id': '', 'name': '', 'round_type': ''}, follow_redirects=True)
    assert b'All fields are required' in r.get_data()


def test_delete_round_with_matches_blocked(admin_client):
    conn = get_db_connection()
    _, round_id, match_id, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B')
    conn.close()

    r = admin_client.post(f'/admin/rounds/{round_id}/delete', follow_redirects=True)
    assert b'Cannot delete this round because matches are already attached' in r.get_data()

    conn = get_db_connection()
    assert conn.execute('SELECT COUNT(*) AS n FROM rounds WHERE id = ?', (round_id,)).fetchone()['n'] == 1
    conn.close()


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------

def test_create_match_validation(admin_client):
    conn = get_db_connection()
    sport_id = conn.execute("SELECT id FROM sports WHERE name = 'Basketball (B)'").fetchone()['id']
    c1 = conn.execute("SELECT id FROM classes WHERE name = '1 BCOM A'").fetchone()['id']
    conn.close()

    r = admin_client.post('/admin/rounds/new', data={'sport_id': sport_id, 'name': 'Group A', 'round_type': 'GROUP'}, follow_redirects=True)
    assert b'Round created successfully' in r.get_data()

    # same class vs itself -> rejected
    r = admin_client.post('/admin/matches/new', data={
        'round_id': 1, 'class1_id': c1, 'class2_id': c1, 'match_time': '2026-08-16T10:00'
    }, follow_redirects=True)
    assert b'A class cannot play against itself' in r.get_data()

    # missing fields -> rejected
    r = admin_client.post('/admin/matches/new', data={'round_id': '', 'class1_id': '', 'class2_id': '', 'match_time': ''}, follow_redirects=True)
    assert b'All fields are required' in r.get_data()


def test_edit_match_and_delete_cascades(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B')
    conn.close()

    # score it
    admin_client.post('/admin/matches/add-score', json={
        'match_id': match_id, 'team_id': c1, 'points': 2, 'event_type': 'Shot', 'counts_as_ball': 0})

    # edit: complete with winner
    r = admin_client.post(f'/admin/matches/{match_id}/edit', data={
        'status': 'COMPLETED', 'winner_id': c1, 'result_details': '1 BCOM A won', 'notes': '', 'scorecard_url': ''
    }, follow_redirects=True)
    assert b'Match updated successfully' in r.get_data()

    conn = get_db_connection()
    row = conn.execute('SELECT * FROM matches WHERE id = ?', (match_id,)).fetchone()
    conn.close()
    assert row['status'] == 'COMPLETED' and row['winner_id'] == c1 and row['result_details'] == '1 BCOM A won'

    # completed edit without winner -> rejected
    r = admin_client.post(f'/admin/matches/{match_id}/edit', data={
        'status': 'COMPLETED', 'winner_id': '', 'result_details': '', 'notes': '', 'scorecard_url': ''
    }, follow_redirects=True)
    assert b'You must select a winner for a completed match' in r.get_data()

    # delete cascades score_log
    admin_client.post(f'/admin/matches/{match_id}/delete')
    conn = get_db_connection()
    assert conn.execute('SELECT COUNT(*) AS n FROM matches WHERE id = ?', (match_id,)).fetchone()['n'] == 0
    assert conn.execute('SELECT COUNT(*) AS n FROM score_log WHERE match_id = ?', (match_id,)).fetchone()['n'] == 0
    conn.close()


def test_edit_match_sets_format_hides_result_field(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(conn, 'Volleyball', '1 BCOM A', '1 BCOM B')
    conn.close()
    r = admin_client.get(f'/admin/matches/{match_id}/edit')
    # sets-format matches use the live finalizer, so no manual result box
    assert b'Result Details' not in r.get_data()


# ---------------------------------------------------------------------------
# Team members (About page)
# ---------------------------------------------------------------------------

def test_team_member_crud(admin_client):
    r = admin_client.post('/admin/team/new', data={'name': 'Coach X', 'role': 'Head Coach'}, follow_redirects=True)
    assert b'Team member added successfully' in r.get_data()

    conn = get_db_connection()
    member = conn.execute("SELECT * FROM team_members WHERE name = 'Coach X'").fetchone()
    member_id = member['id']
    conn.close()

    r = admin_client.post(f'/admin/team/{member_id}/edit', data={'name': 'Coach Y', 'role': 'Assistant'}, follow_redirects=True)
    assert b'Team member updated successfully' in r.get_data()

    conn = get_db_connection()
    member = conn.execute('SELECT * FROM team_members WHERE id = ?', (member_id,)).fetchone()
    conn.close()
    assert member['name'] == 'Coach Y' and member['role'] == 'Assistant'

    r = admin_client.post(f'/admin/team/{member_id}/delete', follow_redirects=True)
    assert b'Team member deleted successfully' in r.get_data()
    conn = get_db_connection()
    assert conn.execute('SELECT COUNT(*) AS n FROM team_members WHERE id = ?', (member_id,)).fetchone()['n'] == 0
    conn.close()


# ---------------------------------------------------------------------------
# Stories
# ---------------------------------------------------------------------------

def test_story_crud(admin_client):
    r = admin_client.post('/admin/stories/new', data={
        'title': 'Great Match', 'content': 'What a game!', 'author': 'DOCAnalytics'
    }, follow_redirects=True)
    assert b'Story created successfully' in r.get_data()

    conn = get_db_connection()
    story = conn.execute("SELECT * FROM stories WHERE title = 'Great Match'").fetchone()
    story_id = story['id']
    conn.close()

    r = admin_client.post(f'/admin/stories/{story_id}/edit', data={
        'title': 'Great Match 2', 'content': 'Even better!', 'author': 'DOCAnalytics'
    }, follow_redirects=True)
    assert b'Story updated successfully' in r.get_data()

    conn = get_db_connection()
    story = conn.execute('SELECT * FROM stories WHERE id = ?', (story_id,)).fetchone()
    conn.close()
    assert story['title'] == 'Great Match 2'

    r = admin_client.post(f'/admin/stories/{story_id}/delete', follow_redirects=True)
    assert b'Story deleted successfully' in r.get_data()
    conn = get_db_connection()
    assert conn.execute('SELECT COUNT(*) AS n FROM stories WHERE id = ?', (story_id,)).fetchone()['n'] == 0
    conn.close()


# ---------------------------------------------------------------------------
# Announcement
# ---------------------------------------------------------------------------

def test_announcement_crud(admin_client, monkeypatch, tmp_path):
    import app as app_module
    target = tmp_path / 'announcement.txt'
    monkeypatch.setattr(app_module, 'APP_ROOT', str(tmp_path))

    r = admin_client.post('/admin/announcement', data={'content': 'Welcome to DOCathon!'}, follow_redirects=True)
    assert b'Announcement updated successfully' in r.get_data()
    assert target.read_text() == 'Welcome to DOCathon!'

    r = admin_client.get('/')
    assert b'Welcome to DOCathon!' in r.get_data()
