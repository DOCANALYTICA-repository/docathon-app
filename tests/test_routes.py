"""Route-level smoke tests for critical public and admin routes."""

from utils.db import get_db_connection
from tests.conftest import create_round_and_match


PUBLIC_ROUTES = [
    '/', '/leaderboard', '/matches', '/brackets', '/about', '/stories',
    '/admin/login',
]


def test_public_routes_200(client):
    for route in PUBLIC_ROUTES:
        r = client.get(route)
        assert r.status_code == 200, f'{route} -> {r.status_code}'


def test_frontend_gallery_route_200(client):
    r = client.get('/gallery')
    assert r.status_code == 200
    assert b'DOCATHON GALLERY' in r.get_data()


def test_admin_routes_require_login(client):
    for route in ['/admin/dashboard', '/admin/matches', '/admin/team', '/admin/stories',
                  '/admin/rounds', '/admin/adjustments', '/admin/announcement']:
        r = client.get(route)
        assert r.status_code == 302, f'{route} not protected: {r.status_code}'
        assert '/admin/login' in r.headers['Location']


def test_admin_routes_200_when_logged_in(admin_client):
    for route in ['/admin/dashboard', '/admin/matches', '/admin/team', '/admin/stories',
                  '/admin/rounds', '/admin/adjustments', '/admin/announcement',
                  '/admin/team/new', '/admin/stories/new', '/admin/rounds/new', '/admin/matches/new']:
        r = admin_client.get(route)
        assert r.status_code == 200, f'{route} -> {r.status_code}'


def test_admin_child_pages_link_back_to_dashboard(admin_client):
    response = admin_client.get('/admin/matches')
    assert response.status_code == 200
    assert b'Back to Admin Panel' in response.get_data()
    assert b'/admin/dashboard' in response.get_data()

    public_response = admin_client.get('/leaderboard')
    assert b'Back to Admin Panel' not in public_response.get_data()


def test_admin_login_wrong_passcode(client):
    r = client.post('/admin/login', data={'passcode': 'wrong'}, follow_redirects=True)
    assert b'Incorrect passcode' in r.get_data()


def test_match_detail_pages(admin_client):
    conn = get_db_connection()
    _, _, m_points, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B')
    _, _, m_sets, c3, c4 = create_round_and_match(conn, 'Volleyball', '1 BCOM C', '5 BCOM A')
    conn.close()

    # score both matches so they're LIVE
    admin_client.post('/admin/matches/add-score', json={
        'match_id': m_points, 'team_id': c1, 'points': 2, 'event_type': 'Shot', 'counts_as_ball': 0})
    admin_client.post('/admin/matches/add-score-set', json={
        'match_id': m_sets, 'team_id': c3, 'points': 1, 'event_type': 'Point', 'counts_as_ball': 0})

    for m in (m_points, m_sets):
        r = admin_client.get(f'/matches/{m}')
        assert r.status_code == 200, f'/matches/{m} -> {r.status_code}'
        r = admin_client.get(f'/admin/matches/{m}/live')
        assert r.status_code == 200, f'/admin/matches/{m}/live -> {r.status_code}'

    # live editor has both team controls
    r = admin_client.get(f'/admin/matches/{m_points}/live')
    assert b'Score for 1 BCOM A' in r.get_data()
    assert b'Score for 1 BCOM B' in r.get_data()


def test_live_editor_set_format_buttons(admin_client):
    conn = get_db_connection()
    _, _, m_sets, c3, c4 = create_round_and_match(conn, 'Volleyball', '1 BCOM C', '5 BCOM A')
    conn.close()
    r = admin_client.get(f'/admin/matches/{m_sets}/live')
    assert b'Finalize Current Set' in r.get_data()


def test_404_and_match_not_found(admin_client):
    r = admin_client.get('/does-not-exist')
    assert r.status_code == 404

    r = admin_client.get('/matches/99999', follow_redirects=True)
    assert b'Match not found' in r.get_data()


def test_brackets_and_stories_pages_with_data(admin_client):
    conn = get_db_connection()
    _, _, m_points, c1, c2 = create_round_and_match(conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B')
    conn.close()

    r = admin_client.get('/brackets')
    assert r.status_code == 200
    r = admin_client.get('/brackets/2')  # Basketball (B)
    assert r.status_code == 200
    assert b'1 BCOM A' in r.get_data()


def test_class_points_log_page(admin_client):
    conn = get_db_connection()
    _, _, match_id, c1, c2 = create_round_and_match(
        conn, 'Basketball (B)', '1 BCOM A', '1 BCOM B', round_type='QUARTER_FINAL')
    conn.close()
    admin_client.post('/admin/matches/add-score', json={
        'match_id': match_id, 'team_id': c1, 'points': 2, 'event_type': 'Shot', 'counts_as_ball': 0})
    admin_client.post(f'/admin/matches/{match_id}/finalize')

    r = admin_client.get(f'/class-log/{c1}')
    assert r.status_code == 200
    assert b'1 BCOM A' in r.get_data()

    # unknown class redirects to leaderboard
    r = admin_client.get('/class-log/99999', follow_redirects=True)
    assert r.status_code == 200


def test_session_ends_after_logout(admin_client):
    admin_client.get('/admin/logout')
    r = admin_client.get('/admin/dashboard')
    assert r.status_code == 302
