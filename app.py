# Final version for deployment
# --- IMPORTS ---
from flask import Flask, render_template, session, redirect, url_for, request, flash, jsonify
from utils.auth import admin_required
from utils.db import get_db_connection
from utils.scoring import (
    get_score_format,
    get_live_scores,
    get_set_scores,
    compute_match_scores,
    match_scores_to_json,
    determine_winner,
    log_set_end,
    compute_leaderboard,
    is_sets_format,
    NON_BALL_EVENTS,
)
import datetime
import os
from werkzeug.utils import secure_filename

# --- APP SETUP ---
app = Flask(__name__)
app.config.from_pyfile('config.py')
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(APP_ROOT, 'static', 'uploads')


# --- CONFIGURATION & HELPERS ---

# SPORT_CONFIG (scoring formats/rules) lives in utils/scoring.py so the public
# pages, admin finalizer and JSON APIs all share the exact same rules.

SPORT_BUTTON_CONFIG = {
    'Cricket Boys': [
        {'label': '+0', 'points': 0, 'type': 'Dot Ball', 'counts_as_ball': 1, 'isComplex': False},
        {'label': '+1', 'points': 1, 'type': 'Run', 'counts_as_ball': 1, 'isComplex': False},
        {'label': '+2', 'points': 2, 'type': 'Runs', 'counts_as_ball': 1, 'isComplex': False},
        {'label': '+3', 'points': 3, 'type': 'Runs', 'counts_as_ball': 1, 'isComplex': False},
        {'label': '+4', 'points': 4, 'type': 'Boundary', 'counts_as_ball': 1, 'isComplex': False},
        {'label': '+6', 'points': 6, 'type': 'Boundary', 'counts_as_ball': 1, 'isComplex': False},
        {'label': 'Wd', 'points': 1, 'type': 'Wide', 'counts_as_ball': 0, 'isComplex': True},
        {'label': 'Nb', 'points': 1, 'type': 'No-Ball', 'counts_as_ball': 0, 'isComplex': True},
        {'label': 'W', 'points': 0, 'type': 'Wicket', 'counts_as_ball': 1, 'isComplex': True},
    ],
    'Cricket Girls': [
        {'label': '+0', 'points': 0, 'type': 'Dot Ball', 'counts_as_ball': 1, 'isComplex': False},
        {'label': '+1', 'points': 1, 'type': 'Run', 'counts_as_ball': 1, 'isComplex': False},
        {'label': '+2', 'points': 2, 'type': 'Runs', 'counts_as_ball': 1, 'isComplex': False},
        {'label': '+3', 'points': 3, 'type': 'Runs', 'counts_as_ball': 1, 'isComplex': False},
        {'label': '+4', 'points': 4, 'type': 'Boundary', 'counts_as_ball': 1, 'isComplex': False},
        {'label': '+6', 'points': 6, 'type': 'Boundary', 'counts_as_ball': 1, 'isComplex': False},
        {'label': 'Wd', 'points': 1, 'type': 'Wide', 'counts_as_ball': 0, 'isComplex': True},
        {'label': 'Nb', 'points': 1, 'type': 'No-Ball', 'counts_as_ball': 0, 'isComplex': True},
        {'label': 'W', 'points': 0, 'type': 'Wicket', 'counts_as_ball': 1, 'isComplex': True},
    ],
    'Basketball (B)': [
        {'label': '+1', 'points': 1, 'type': 'Freethrow', 'counts_as_ball': 0, 'isComplex': False},
        {'label': '+2', 'points': 2, 'type': 'Shot', 'counts_as_ball': 0, 'isComplex': False},
        {'label': '+3', 'points': 3, 'type': 'Shot', 'counts_as_ball': 0, 'isComplex': False},
    ],
    'Basketball (G)': [
        {'label': '+1', 'points': 1, 'type': 'Freethrow', 'counts_as_ball': 0, 'isComplex': False},
        {'label': '+2', 'points': 2, 'type': 'Shot', 'counts_as_ball': 0, 'isComplex': False},
        {'label': '+3', 'points': 3, 'type': 'Shot', 'counts_as_ball': 0, 'isComplex': False},
    ],
}

# --- PUBLIC ROUTES ---

@app.route('/gallery')
def gallery():
    return render_template('public/gallery.html', page_title='Gallery')

@app.route('/')
def home():
    """Renders a dynamic public landing page."""
    conn = get_db_connection()
    top_teams = compute_leaderboard(conn, limit=3)

    today_str = datetime.date.today().strftime('%Y-%m-%d')
    todays_matches_query = """
        SELECT
            m.id, m.status, m.result_details, m.match_time, s.name AS sport_name,
            c1.name AS class1_name, c2.name AS class2_name
        FROM matches m
        JOIN sports s ON m.sport_id = s.id
        JOIN classes c1 ON m.class1_id = c1.id
        JOIN classes c2 ON m.class2_id = c2.id
        WHERE date(m.match_time) = ?
        ORDER BY m.match_time ASC
    """
    todays_matches = conn.execute(todays_matches_query, (today_str,)).fetchall()
    conn.close()
    return render_template('public/index.html', top_teams=top_teams, todays_matches=todays_matches)

@app.route('/leaderboard')
def leaderboard():
    conn = get_db_connection()
    standings = compute_leaderboard(conn)
    conn.close()
    return render_template('public/leaderboard.html', standings=standings, page_title="Leaderboard")

@app.route('/matches')
def matches():
    conn = get_db_connection()
    sport_filter = request.args.get('sport_id', None)
    class_filter = request.args.get('class_id', None)
    query = """
        SELECT
            m.id, m.status, m.result_details, m.match_time,
            s.name AS sport_name, r.name AS round_name,
            c1.name AS class1_name, c2.name AS class2_name
        FROM matches m
        JOIN sports s ON m.sport_id = s.id
        JOIN rounds r ON m.round_id = r.id
        JOIN classes c1 ON m.class1_id = c1.id
        JOIN classes c2 ON m.class2_id = c2.id
    """
    conditions = []
    params = []
    if sport_filter:
        conditions.append("m.sport_id = ?")
        params.append(sport_filter)
    if class_filter:
        conditions.append("(m.class1_id = ? OR m.class2_id = ?)")
        params.extend([class_filter, class_filter])
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY m.match_time DESC"
    all_matches = conn.execute(query, params).fetchall()
    sports = conn.execute('SELECT id, name FROM sports ORDER BY name').fetchall()
    classes = conn.execute('SELECT id, name FROM classes ORDER BY name').fetchall()
    conn.close()
    return render_template('public/matches.html', all_matches=all_matches, 
                           sports=sports, classes=classes, 
                           page_title="Match Schedule")

@app.route('/matches/<int:match_id>')
def match_details(match_id):
    conn = get_db_connection()
    match = conn.execute("""
        SELECT m.*, s.name as sport_name, r.name as round_name, c1.name as class1_name, c2.name as class2_name
        FROM matches m
        JOIN sports s ON m.sport_id = s.id
        JOIN rounds r ON m.round_id = r.id
        JOIN classes c1 ON m.class1_id = c1.id
        JOIN classes c2 ON m.class2_id = c2.id
        WHERE m.id = ?
    """, (match_id,)).fetchone()
    if match is None:
        flash('Match not found!', 'danger')
        return redirect(url_for('matches'))
    scores = {}
    is_cricket = 'Cricket' in match['sport_name']
    score_format = get_score_format(match['sport_name'])

    if match['status'] in ('LIVE', 'COMPLETED'):
        scores = compute_match_scores(conn, match_id) or {}

    score_log = conn.execute("""
        SELECT sl.*, c.name as team_name
        FROM score_log sl
        JOIN classes c ON sl.team_id = c.id
        WHERE sl.match_id = ?
        ORDER BY sl.created_at DESC
    """, (match_id,)).fetchall()
    conn.close()
    return render_template('public/match_details.html', match=match, score_log=score_log, scores=scores, is_cricket=is_cricket, score_format=score_format, page_title="Match Details")

@app.route('/api/match-scores/<int:match_id>')
def get_match_scores_api(match_id):
    """Live score endpoint used for near-real-time updates.

    Returns format-aware scores:
      points format -> {'format': 'points', <team_id>: {score, wickets, overs, balls}, ...}
      sets format   -> {'format': 'sets_detailed', 'current_set_scores': {...},
                        'sets_won': {...}, 'completed_sets': [...]}
    Team-id keys are also kept at the top level for backwards compatibility.
    """
    conn = get_db_connection()
    scores = compute_match_scores(conn, match_id)
    conn.close()
    if scores is None:
        return jsonify({'error': 'Match not found'}), 404
    return jsonify(match_scores_to_json(scores))


@app.route('/api/leaderboard')
def leaderboard_api():
    """Ranked standings for the public leaderboard, refreshed live by the client."""
    conn = get_db_connection()
    standings = compute_leaderboard(conn)
    conn.close()
    return jsonify({'standings': standings, 'updated_at': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')})


@app.route('/api/matches')
def matches_api():
    """JSON schedule/result feed for near-real-time match & result updates."""
    conn = get_db_connection()
    sport_filter = request.args.get('sport_id')
    class_filter = request.args.get('class_id')
    status_filter = request.args.get('status')
    query = """
        SELECT
            m.id, m.status, m.result_details, m.match_time, m.winner_id,
            s.id AS sport_id, s.name AS sport_name, r.name AS round_name,
            c1.id AS class1_id, c1.name AS class1_name,
            c2.id AS class2_id, c2.name AS class2_name
        FROM matches m
        JOIN sports s ON m.sport_id = s.id
        JOIN rounds r ON m.round_id = r.id
        JOIN classes c1 ON m.class1_id = c1.id
        JOIN classes c2 ON m.class2_id = c2.id
    """
    conditions, params = [], []
    if sport_filter:
        conditions.append('m.sport_id = ?')
        params.append(sport_filter)
    if class_filter:
        conditions.append('(m.class1_id = ? OR m.class2_id = ?)')
        params.extend([class_filter, class_filter])
    if status_filter:
        conditions.append('m.status = ?')
        params.append(status_filter)
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    query += ' ORDER BY m.match_time ASC'
    matches = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify({
        'matches': [dict(row) for row in matches],
        'updated_at': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
    })

@app.route('/brackets')
def list_brackets():
    conn = get_db_connection()
    sports_with_rounds = conn.execute("SELECT DISTINCT s.id, s.name FROM sports s JOIN rounds r ON s.id = r.sport_id ORDER BY s.name").fetchall()
    conn.close()
    return render_template('public/list_brackets.html', sports=sports_with_rounds, page_title="Tournament Brackets")

@app.route('/brackets/<int:sport_id>')
def view_bracket(sport_id):
    conn = get_db_connection()
    sport = conn.execute('SELECT name FROM sports WHERE id = ?', (sport_id,)).fetchone()
    if sport is None:
        return redirect(url_for('list_brackets'))
    query = """
        SELECT r.name as round_name, c1.name as class1_name, c2.name as class2_name, w.name as winner_name
        FROM matches m
        JOIN rounds r ON m.round_id = r.id
        JOIN classes c1 ON m.class1_id = c1.id
        JOIN classes c2 ON m.class2_id = c2.id
        LEFT JOIN classes w ON m.winner_id = w.id
        WHERE m.sport_id = ? ORDER BY r.id, m.id
    """
    matches = conn.execute(query, (sport_id,)).fetchall()
    rounds = {}
    for match in matches:
        round_name = match['round_name']
        if round_name not in rounds:
            rounds[round_name] = []
        rounds[round_name].append(match)
    conn.close()
    return render_template('public/brackets.html', sport_name=sport['name'], rounds=rounds, page_title=f"{sport['name']} Bracket")

@app.route('/about')
def about():
    conn = get_db_connection()
    members = conn.execute('SELECT * FROM team_members ORDER BY name').fetchall()
    conn.close()
    return render_template('public/about.html', members=members, page_title="About Us")

@app.route('/stories')
def list_stories():
    conn = get_db_connection()
    stories = conn.execute('SELECT id, title, content, author, image_filename FROM stories ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('public/list_stories.html', stories=stories, page_title="Trending Stories")

@app.route('/stories/<int:story_id>')
def view_story(story_id):
    conn = get_db_connection()
    story = conn.execute('SELECT id, title, content, author, image_filename FROM stories WHERE id = ?', (story_id,)).fetchone()
    conn.close()
    if story is None:
        return redirect(url_for('list_stories'))
    return render_template('public/view_story.html', story=story, page_title=story['title'])

@app.route('/class-log/<int:class_id>')
def class_points_log(class_id):
    conn = get_db_connection()
    class_info = conn.execute('SELECT name FROM classes WHERE id = ?', (class_id,)).fetchone()
    if class_info is None:
        return redirect(url_for('leaderboard'))
    tournament_events = conn.execute("""
        SELECT * FROM (
            SELECT s.name as sport_name, r.round_type,
                CASE
                    WHEN m.winner_id = ? AND r.round_type = 'FINAL' THEN 5
                    WHEN m.winner_id != ? AND r.round_type = 'FINAL' THEN 4
                    WHEN m.winner_id != ? AND r.round_type = 'SEMI_FINAL' THEN 3
                    WHEN m.winner_id != ? AND r.round_type = 'QUARTER_FINAL' THEN 2
                    ELSE 0
                END AS points,
                CASE WHEN m.winner_id = ? THEN 'Won' ELSE 'Lost' END AS outcome
            FROM matches m
            JOIN rounds r ON m.round_id = r.id
            JOIN sports s ON m.sport_id = s.id
            WHERE (m.class1_id = ? OR m.class2_id = ?) AND m.status = 'COMPLETED'
              AND r.round_type IN ('FINAL', 'SEMI_FINAL', 'QUARTER_FINAL')
        ) WHERE points > 0
    """, (class_id, class_id, class_id, class_id, class_id, class_id, class_id)).fetchall()
    participation_events = conn.execute("""
        SELECT DISTINCT s.name as sport_name
        FROM matches m
        JOIN sports s ON m.sport_id = s.id
        WHERE (m.class1_id = ? OR m.class2_id = ?) AND m.status = 'COMPLETED'
    """, (class_id, class_id)).fetchall()
    adjustments = conn.execute(
        'SELECT points, reason FROM point_adjustments WHERE class_id = ? ORDER BY created_at DESC', (class_id,)
    ).fetchall()
    win_points_events = conn.execute("""
        SELECT s.name as sport_name, c2.name as opponent_name
        FROM matches m
        JOIN sports s ON m.sport_id = s.id
        JOIN classes c2 ON m.class2_id = c2.id
        WHERE m.winner_id = ? AND m.class1_id = ?
          AND m.result_details IS NOT NULL AND m.result_details != ''
          AND m.result_details NOT LIKE '%Walkover%'
        UNION ALL
        SELECT s.name as sport_name, c1.name as opponent_name
        FROM matches m
        JOIN sports s ON m.sport_id = s.id
        JOIN classes c1 ON m.class1_id = c1.id
        WHERE m.winner_id = ? AND m.class2_id = ?
          AND m.result_details IS NOT NULL AND m.result_details != ''
          AND m.result_details NOT LIKE '%Walkover%'
    """, (class_id, class_id, class_id, class_id)).fetchall()
    conn.close()
    return render_template('public/class_points_log.html',
                           class_name=class_info['name'],
                           tournament_events=tournament_events,
                           participation_events=participation_events,
                           adjustments=adjustments,
                           win_points_events=win_points_events,
                           page_title=f"Points Log for {class_info['name']}")


# --- ADMIN AUTH & DASHBOARD ---

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        passcode = request.form.get('passcode')
        if passcode == app.config['ADMIN_PASSCODE']:
            session['role'] = 'admin'
            flash('Login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Incorrect passcode.', 'danger')
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('role', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin/dashboard.html')


# --- ADMIN CONTENT MANAGEMENT ---

@app.route('/admin/team')
@admin_required
def admin_list_members():
    conn = get_db_connection()
    members = conn.execute('SELECT * FROM team_members ORDER BY name').fetchall()
    conn.close()
    return render_template('admin/list_members_admin.html', members=members)

@app.route('/admin/team/new', methods=['GET', 'POST'])
@admin_required
def create_member():
    if request.method == 'POST':
        name = request.form.get('name')
        role = request.form.get('role')
        photo_file = request.files.get('photo')
        photo_filename = None
        if photo_file and photo_file.filename != '':
            photo_filename = secure_filename(photo_file.filename)
            photo_file.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_filename))
        conn = get_db_connection()
        conn.execute('INSERT INTO team_members (name, role, photo_filename) VALUES (?, ?, ?)', (name, role, photo_filename))
        conn.commit()
        conn.close()
        flash('Team member added successfully!', 'success')
        return redirect(url_for('admin_list_members'))
    return render_template('admin/member_form.html', form_title="Add New Member")

@app.route('/admin/team/<int:member_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_member(member_id):
    conn = get_db_connection()
    if request.method == 'POST':
        name = request.form.get('name')
        role = request.form.get('role')
        photo_file = request.files.get('photo')
        current_filename = conn.execute('SELECT photo_filename FROM team_members WHERE id = ?', (member_id,)).fetchone()['photo_filename']
        photo_filename = current_filename
        if photo_file and photo_file.filename != '':
            photo_filename = secure_filename(photo_file.filename)
            photo_file.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_filename))
        conn.execute('UPDATE team_members SET name = ?, role = ?, photo_filename = ? WHERE id = ?', (name, role, photo_filename, member_id))
        conn.commit()
        conn.close()
        flash('Team member updated successfully!', 'success')
        return redirect(url_for('admin_list_members'))
    member = conn.execute('SELECT * FROM team_members WHERE id = ?', (member_id,)).fetchone()
    conn.close()
    return render_template('admin/member_form.html', member=member, form_title="Edit Team Member")

@app.route('/admin/team/<int:member_id>/delete', methods=['POST'])
@admin_required
def delete_member(member_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM team_members WHERE id = ?', (member_id,))
    conn.commit()
    conn.close()
    flash('Team member deleted successfully!', 'success')
    return redirect(url_for('admin_list_members'))

@app.route('/admin/stories')
@admin_required
def admin_list_stories():
    conn = get_db_connection()
    stories = conn.execute('SELECT id, title, author FROM stories ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin/list_stories_admin.html', stories=stories)

@app.route('/admin/stories/new', methods=['GET', 'POST'])
@admin_required
def create_story():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        author = request.form.get('author')
        image_file = request.files.get('image')
        image_filename = None
        if image_file and image_file.filename != '':
            image_filename = secure_filename(image_file.filename)
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
        conn = get_db_connection()
        conn.execute('INSERT INTO stories (title, content, author, image_filename) VALUES (?, ?, ?, ?)', (title, content, author, image_filename))
        conn.commit()
        conn.close()
        flash('Story created successfully!', 'success')
        return redirect(url_for('admin_list_stories'))
    return render_template('admin/story_form.html', form_title="Create New Story")

@app.route('/admin/stories/<int:story_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_story(story_id):
    conn = get_db_connection()
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        author = request.form.get('author')
        image_file = request.files.get('image')
        current_filename = conn.execute('SELECT image_filename FROM stories WHERE id = ?', (story_id,)).fetchone()['image_filename']
        image_filename = current_filename
        if image_file and image_file.filename != '':
            image_filename = secure_filename(image_file.filename)
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
        conn.execute('UPDATE stories SET title = ?, content = ?, author = ?, image_filename = ? WHERE id = ?', (title, content, author, image_filename, story_id))
        conn.commit()
        conn.close()
        flash('Story updated successfully!', 'success')
        return redirect(url_for('admin_list_stories'))
    story = conn.execute('SELECT * FROM stories WHERE id = ?', (story_id,)).fetchone()
    conn.close()
    return render_template('admin/story_form.html', story=story, form_title="Edit Story")

@app.route('/admin/stories/<int:story_id>/delete', methods=['POST'])
@admin_required
def delete_story(story_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM stories WHERE id = ?', (story_id,))
    conn.commit()
    conn.close()
    flash('Story deleted successfully.', 'success')
    return redirect(url_for('admin_list_stories'))

@app.route('/admin/rounds')
@admin_required
def list_rounds():
    conn = get_db_connection()
    rounds = conn.execute("""
        SELECT r.id, r.name, r.round_type, s.name as sport_name
        FROM rounds r
        JOIN sports s ON r.sport_id = s.id
        ORDER BY s.name, r.id
    """).fetchall()
    conn.close()
    return render_template('admin/list_rounds.html', rounds=rounds)

@app.route('/admin/rounds/new', methods=['GET', 'POST'])
@admin_required
def create_round():
    conn = get_db_connection()
    if request.method == 'POST':
        sport_id = request.form.get('sport_id')
        name = request.form.get('name')
        round_type = request.form.get('round_type')
        if not all([sport_id, name, round_type]):
            flash('All fields are required.', 'danger')
            return redirect(url_for('create_round'))
        conn.execute('INSERT INTO rounds (sport_id, name, round_type) VALUES (?, ?, ?)', (sport_id, name, round_type))
        conn.commit()
        conn.close()
        flash('Round created successfully!', 'success')
        return redirect(url_for('list_rounds'))
    sports = conn.execute('SELECT * FROM sports ORDER BY name').fetchall()
    conn.close()
    return render_template('admin/round_form.html', sports=sports, form_title="Create New Round")

@app.route('/admin/rounds/<int:round_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_round(round_id):
    conn = get_db_connection()
    if request.method == 'POST':
        name = request.form.get('name')
        round_type = request.form.get('round_type')
        conn.execute('UPDATE rounds SET name = ?, round_type = ? WHERE id = ?', (name, round_type, round_id))
        conn.commit()
        conn.close()
        flash('Round updated successfully!', 'success')
        return redirect(url_for('list_rounds'))
    round_data = conn.execute('SELECT * FROM rounds WHERE id = ?', (round_id,)).fetchone()
    sports = conn.execute('SELECT * FROM sports ORDER BY name').fetchall()
    conn.close()
    if round_data is None:
        flash('Round not found!', 'danger')
        return redirect(url_for('list_rounds'))
    return render_template('admin/round_form.html', round=round_data, sports=sports, form_title="Edit Round")

@app.route('/admin/rounds/<int:round_id>/delete', methods=['POST'])
@admin_required
def delete_round(round_id):
    conn = get_db_connection()
    matches = conn.execute('SELECT id FROM matches WHERE round_id = ?', (round_id,)).fetchone()
    if matches:
        flash('Cannot delete this round because matches are already attached to it.', 'danger')
    else:
        conn.execute('DELETE FROM rounds WHERE id = ?', (round_id,))
        conn.commit()
        flash('Round deleted successfully.', 'success')
    conn.close()
    return redirect(url_for('list_rounds'))

@app.route('/admin/matches')
@admin_required
def list_matches():
    conn = get_db_connection()
    query = """
        SELECT m.id, s.name as sport_name, c1.name as class1_name, c2.name as class2_name,
               m.result_details, m.status, m.match_time
        FROM matches m
        JOIN sports s ON m.sport_id = s.id
        JOIN classes c1 ON m.class1_id = c1.id
        JOIN classes c2 ON m.class2_id = c2.id
        ORDER BY m.match_time DESC
    """
    matches = conn.execute(query).fetchall()
    conn.close()
    return render_template('admin/list_matches.html', matches=matches)

@app.route('/admin/matches/new', methods=['GET', 'POST'])
@admin_required
def create_match():
    conn = get_db_connection()
    if request.method == 'POST':
        round_id = request.form.get('round_id')
        class1_id = request.form.get('class1_id')
        class2_id = request.form.get('class2_id')
        match_time_str = request.form.get('match_time')
        if not all([round_id, class1_id, class2_id, match_time_str]):
            flash('All fields are required.', 'danger')
            return redirect(url_for('create_match'))
        if class1_id == class2_id:
            flash('A class cannot play against itself. Please select two different teams.', 'danger')
            rounds = conn.execute("SELECT r.id, r.name, s.name as sport_name FROM rounds r JOIN sports s ON r.sport_id = s.id ORDER BY s.name, r.id").fetchall()
            classes = conn.execute('SELECT * FROM classes ORDER BY name').fetchall()
            conn.close()
            default_time = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M')
            return render_template('admin/match_form.html', rounds=rounds, classes=classes, default_time=default_time, form_title="Create New Match")
        sport_id = conn.execute('SELECT sport_id FROM rounds WHERE id = ?', (round_id,)).fetchone()['sport_id']
        conn.execute(
            'INSERT INTO matches (sport_id, round_id, class1_id, class2_id, match_time, status) VALUES (?, ?, ?, ?, ?, ?)',
            (sport_id, round_id, class1_id, class2_id, match_time_str, 'UPCOMING')
        )
        conn.commit()
        conn.close()
        flash('Match created successfully!', 'success')
        return redirect(url_for('list_matches'))
    rounds = conn.execute("SELECT r.id, r.name, s.name as sport_name FROM rounds r JOIN sports s ON r.sport_id = s.id ORDER BY s.name, r.id").fetchall()
    classes = conn.execute('SELECT * FROM classes ORDER BY name').fetchall()
    conn.close()
    default_time = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M')
    return render_template('admin/match_form.html', rounds=rounds, classes=classes, default_time=default_time, form_title="Create New Match")

@app.route('/admin/matches/<int:match_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_match(match_id):
    conn = get_db_connection()
    if request.method == 'POST':
        status = request.form.get('status')
        result_details = request.form.get('result_details')
        winner_id = request.form.get('winner_id')
        notes = request.form.get('notes')
        scorecard_url = request.form.get('scorecard_url')
        if status == 'COMPLETED' and not winner_id:
            flash('You must select a winner for a completed match.', 'danger')
            return redirect(url_for('edit_match', match_id=match_id))
        if status != 'COMPLETED':
            winner_id = None
        conn.execute(
            'UPDATE matches SET status = ?, winner_id = ?, notes = ?, result_details = ?, scorecard_url = ? WHERE id = ?',
            (status, winner_id, notes, result_details, scorecard_url, match_id)
        )
        conn.commit()
        conn.close()
        flash('Match updated successfully!', 'success')
        return redirect(url_for('list_matches'))
    match = conn.execute("""
        SELECT m.*, s.name as sport_name, c1.name as class1_name, c2.name as class2_name
        FROM matches m
        JOIN sports s ON m.sport_id = s.id
        JOIN classes c1 ON m.class1_id = c1.id
        JOIN classes c2 ON m.class2_id = c2.id
        WHERE m.id = ?
    """, (match_id,)).fetchone()
    conn.close()
    if match is None:
        flash('Match not found!', 'danger')
        return redirect(url_for('list_matches'))
    uses_live_finalizer = is_sets_format(match['sport_name'])
    return render_template('admin/match_form.html', match=match, form_title="Edit Match", uses_live_finalizer=uses_live_finalizer)

@app.route('/admin/matches/<int:match_id>/delete', methods=['POST'])
@admin_required
def delete_match(match_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM score_log WHERE match_id = ?', (match_id,))
    conn.execute('DELETE FROM matches WHERE id = ?', (match_id,))
    conn.commit()
    conn.close()
    flash('Match has been deleted successfully.', 'success')
    return redirect(url_for('list_matches'))

@app.route('/admin/matches/<int:match_id>/walkover', methods=['POST'])
@admin_required
def declare_walkover(match_id):
    loser_id = request.form.get('loser_id')
    if not loser_id:
        flash('Invalid request for walkover.', 'danger')
        return redirect(url_for('list_matches'))
    conn = get_db_connection()
    match = conn.execute('SELECT * FROM matches WHERE id = ?', (match_id,)).fetchone()
    if match is None:
        conn.close()
        flash('Match not found!', 'danger')
        return redirect(url_for('list_matches'))
    if match['status'] == 'COMPLETED':
        conn.close()
        flash('This match is already completed.', 'warning')
        return redirect(url_for('list_matches'))
    loser_id = int(loser_id)
    if loser_id not in (match['class1_id'], match['class2_id']):
        conn.close()
        flash('The selected losing team is not part of this match.', 'danger')
        return redirect(url_for('list_matches'))
    winner_id = match['class2_id'] if loser_id == match['class1_id'] else match['class1_id']
    winner_name = conn.execute('SELECT name FROM classes WHERE id = ?', (winner_id,)).fetchone()['name']
    loser_name = conn.execute('SELECT name FROM classes WHERE id = ?', (loser_id,)).fetchone()['name']
    sport_name = conn.execute('SELECT name FROM sports WHERE id = ?', (match['sport_id'],)).fetchone()['name']
    result_details = f"{winner_name} won by Walkover"
    conn.execute(
        'UPDATE matches SET status = ?, winner_id = ?, result_details = ? WHERE id = ?',
        ('COMPLETED', winner_id, result_details, match_id)
    )
    reason = f"Walkover in {sport_name} vs {winner_name}"
    conn.execute(
        'INSERT INTO point_adjustments (class_id, points, reason) VALUES (?, ?, ?)',
        (loser_id, -3, reason)
    )
    conn.commit()
    conn.close()
    flash(f"{loser_name} recorded with a walkover. -3 points applied.", 'success')
    return redirect(url_for('list_matches'))

@app.route('/admin/adjustments', methods=['GET', 'POST'])
@admin_required
def point_adjustments():
    """Page to manually add or subtract points for any class."""
    conn = get_db_connection()

    if request.method == 'POST':
        class_id = request.form.get('class_id')
        points = request.form.get('points')
        reason = request.form.get('reason')

        if not all([class_id, points, reason]):
            flash('All fields are required.', 'danger')
        elif not points.lstrip('-').isdigit():
            flash('Points must be a valid number.', 'danger')
        else:
            conn.execute(
                'INSERT INTO point_adjustments (class_id, points, reason) VALUES (?, ?, ?)',
                (class_id, int(points), reason)
            )
            conn.commit()
            flash('Point adjustment saved successfully!', 'success')
        
        return redirect(url_for('point_adjustments'))

    # GET request: Fetch data for the form and the log
    classes = conn.execute('SELECT * FROM classes ORDER BY name').fetchall()
    # CORRECTED: Added pa.id to the SELECT statement
    adjustments = conn.execute("""
        SELECT pa.id, pa.points, pa.reason, pa.created_at, c.name as class_name
        FROM point_adjustments pa
        JOIN classes c ON pa.class_id = c.id
        ORDER BY pa.created_at DESC
    """).fetchall()
    
    conn.close()
    
    return render_template('admin/adjustments_form.html', classes=classes, adjustments=adjustments)

@app.route('/admin/adjustments/<int:adjustment_id>/delete', methods=['POST'])
@admin_required
def delete_adjustment(adjustment_id):
    """Deletes a specific manual point adjustment."""
    conn = get_db_connection()
    conn.execute('DELETE FROM point_adjustments WHERE id = ?', (adjustment_id,))
    conn.commit()
    conn.close()
    flash('Point adjustment deleted successfully.', 'success')
    return redirect(url_for('point_adjustments'))

@app.route('/admin/announcement', methods=['GET', 'POST'])
@admin_required
def manage_announcement():
    announcement_file = os.path.join(APP_ROOT, 'announcement.txt')
    if request.method == 'POST':
        content = request.form.get('content') or ''
        with open(announcement_file, 'w', encoding='utf-8') as f:
            f.write(content)
        flash('Announcement updated successfully!', 'success')
        return redirect(url_for('manage_announcement'))
    content = ""
    if os.path.exists(announcement_file):
        with open(announcement_file, 'r', encoding='utf-8') as f:
            content = f.read()
    return render_template('admin/announcement_form.html', content=content)

# --- ADMIN LIVE SCORING ---

@app.route('/admin/matches/<int:match_id>/live')
@admin_required
def live_score_editor(match_id):
    conn = get_db_connection()
    match = conn.execute("SELECT m.*, s.name as sport_name, r.name as round_name, c1.name as class1_name, c2.name as class2_name FROM matches m JOIN sports s ON m.sport_id = s.id JOIN rounds r ON m.round_id = r.id JOIN classes c1 ON m.class1_id = c1.id JOIN classes c2 ON m.class2_id = c2.id WHERE m.id = ?", (match_id,)).fetchone()
    if not match:
        flash('Match not found!', 'danger')
        return redirect(url_for('list_matches'))

    sport_name = match['sport_name']
    score_format = get_score_format(sport_name)

    scores = compute_match_scores(conn, match_id) or {}

    # CORRECTED: Provide an empty list [] as a default if no buttons are defined
    buttons = SPORT_BUTTON_CONFIG.get(sport_name, [])
    conn.close()
    
    is_cricket = 'Cricket' in sport_name
    
    return render_template('admin/live_score_form.html', match=match, scores=scores, buttons=buttons, is_cricket=is_cricket, score_format=score_format)

@app.route('/admin/matches/end-set', methods=['POST'])
@admin_required
def end_set():
    """Logs the end of a set from the HTML form (FK-safe, validated)."""
    match_id = request.form.get('match_id')
    if not match_id:
        flash('Invalid request: missing match id.', 'danger')
        return redirect(url_for('list_matches'))
    conn = get_db_connection()
    ok, message = log_set_end(conn, int(match_id))
    conn.close()
    flash(message, 'success' if ok else 'danger')
    return redirect(url_for('live_score_editor', match_id=match_id))


def _match_team_ids(conn, match_id):
    """Returns (sport_name, class1_id, class2_id, status) or (None, None, None, None)."""
    match = conn.execute(
        'SELECT m.sport_id, m.class1_id, m.class2_id, m.status, s.name AS sport_name '
        'FROM matches m JOIN sports s ON m.sport_id = s.id WHERE m.id = ?',
        (match_id,)
    ).fetchone()
    if match is None:
        return None, None, None, None, None
    return match['sport_name'], match['class1_id'], match['class2_id'], match['status'], match['sport_id']


def is_cricket_name(sport_name):
    """Returns True for cricket sports (used to gate complex ball-by-ball events)."""
    return 'Cricket' in (sport_name or '')


def _ensure_match_live(conn, match_id):
    """Marks an UPCOMING match as LIVE the first time a score is entered."""
    status = conn.execute('SELECT status FROM matches WHERE id = ?', (match_id,)).fetchone()['status']
    if status == 'UPCOMING':
        conn.execute("UPDATE matches SET status = 'LIVE' WHERE id = ?", (match_id,))
        conn.commit()
        return True
    return False


def _score_event_payload(data, allowed_event_types):
    """Validates & normalises a score event sent by the client.

    Returns (match_id, team_id, points, event_type, counts_as_ball) or a
    (None, error_message) tuple on failure.
    """
    if not isinstance(data, dict):
        return None, 'Invalid JSON payload.'
    match_id = data.get('match_id')
    team_id = data.get('team_id')
    points = data.get('points')
    event_type = data.get('event_type')
    counts_as_ball = data.get('counts_as_ball', 0)

    if match_id is None or team_id is None:
        return None, 'match_id and team_id are required.'
    try:
        match_id = int(match_id)
        team_id = int(team_id)
    except (TypeError, ValueError):
        return None, 'match_id and team_id must be integers.'
    try:
        points = int(points or 0)
    except (TypeError, ValueError):
        return None, 'points must be an integer.'
    if counts_as_ball not in (0, 1):
        try:
            counts_as_ball = int(counts_as_ball)
        except (TypeError, ValueError):
            counts_as_ball = 0
    if counts_as_ball not in (0, 1):
        return None, 'counts_as_ball must be 0 or 1.'
    if not event_type:
        return None, 'event_type is required.'
    if allowed_event_types and event_type not in allowed_event_types:
        return None, f'event_type {event_type!r} is not allowed here.'

    # Cricket: wides & no-balls never count as legal deliveries, regardless of
    # what the client sends (runs scored off them ride the same ball).
    if event_type in NON_BALL_EVENTS:
        counts_as_ball = 0

    return (match_id, team_id, points, event_type, counts_as_ball), None


@app.route('/admin/matches/add-score', methods=['POST'])
@admin_required
def add_score():
    """AJAX endpoint for simple, point-based scoring events."""
    data = request.get_json(silent=True)
    payload, error = _score_event_payload(data, None)
    if error:
        return jsonify({'success': False, 'error': error}), 400
    match_id, team_id, points, event_type, counts_as_ball = payload

    conn = get_db_connection()
    sport_name, class1_id, class2_id, status, _ = _match_team_ids(conn, match_id)
    if sport_name is None:
        conn.close()
        return jsonify({'success': False, 'error': 'Match not found.'}), 404
    if is_sets_format(sport_name):
        conn.close()
        return jsonify({'success': False, 'error': 'Use the set-scoring endpoint for this sport.'}), 400
    if status == 'COMPLETED':
        conn.close()
        return jsonify({'success': False, 'error': 'Cannot score a completed match.'}), 400
    if team_id not in (class1_id, class2_id):
        conn.close()
        return jsonify({'success': False, 'error': 'team_id is not part of this match.'}), 400

    _ensure_match_live(conn, match_id)
    conn.execute(
        'INSERT INTO score_log (match_id, team_id, points_scored, event_type, counts_as_ball) '
        'VALUES (?, ?, ?, ?, ?)',
        (match_id, team_id, points, event_type, counts_as_ball)
    )
    conn.commit()
    new_stats = get_live_scores(conn, match_id, team_id)
    conn.close()

    return jsonify({
        'success': True, 'team_id': team_id,
        'new_total': new_stats['score'], 'new_wickets': new_stats['wickets'],
        'new_overs': new_stats['overs'], 'new_balls': new_stats['balls']
    })

@app.route('/admin/matches/add-score-set', methods=['POST'])
@admin_required
def add_score_set():
    """AJAX endpoint for adding a point in a set-based match."""
    data = request.get_json(silent=True)
    payload, error = _score_event_payload(data, {'Point'})
    if error:
        return jsonify({'success': False, 'error': error}), 400
    match_id, team_id, _, _, _ = payload

    conn = get_db_connection()
    sport_name, class1_id, class2_id, status, _ = _match_team_ids(conn, match_id)
    if sport_name is None:
        conn.close()
        return jsonify({'success': False, 'error': 'Match not found.'}), 404
    if not is_sets_format(sport_name):
        conn.close()
        return jsonify({'success': False, 'error': 'This sport does not use set scoring.'}), 400
    if status == 'COMPLETED':
        conn.close()
        return jsonify({'success': False, 'error': 'Cannot score a completed match.'}), 400
    if team_id not in (class1_id, class2_id):
        conn.close()
        return jsonify({'success': False, 'error': 'team_id is not part of this match.'}), 400

    _ensure_match_live(conn, match_id)
    conn.execute(
        "INSERT INTO score_log (match_id, team_id, points_scored, event_type, counts_as_ball) "
        "VALUES (?, ?, 1, 'Point', 0)",
        (match_id, team_id)
    )
    conn.commit()
    new_scores = get_set_scores(conn, match_id, class1_id, class2_id)
    conn.close()

    return jsonify({'success': True, 'new_scores': new_scores})

@app.route('/admin/matches/log-complex-event', methods=['POST'])
@admin_required
def log_complex_event():
    """Logs a complex, two-part event like a wide + runs for cricket.

    Cricket correctness: runs off a Wide / No-Ball must not be counted as a
    legal delivery, so their counts_as_ball is forced to 0 server-side.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'error': 'Invalid JSON payload.'}), 400

    base_event = data.get('base_event')
    if not isinstance(base_event, dict):
        return jsonify({'success': False, 'error': 'base_event is required.'}), 400

    payload, error = _score_event_payload({
        'match_id': data.get('match_id'),
        'team_id': data.get('team_id'),
        'points': base_event.get('points'),
        'event_type': base_event.get('type'),
        'counts_as_ball': base_event.get('counts_as_ball', 0),
    }, None)
    if error:
        return jsonify({'success': False, 'error': error}), 400
    match_id, team_id, points, event_type, counts_as_ball = payload

    extra_runs = data.get('extra_runs') or {}
    try:
        extra_points = int(extra_runs.get('points', 0) or 0)
    except (TypeError, ValueError):
        extra_points = 0
    if extra_points < 0:
        return jsonify({'success': False, 'error': 'extra_runs.points cannot be negative.'}), 400

    conn = get_db_connection()
    sport_name, class1_id, class2_id, status, _ = _match_team_ids(conn, match_id)
    if sport_name is None:
        conn.close()
        return jsonify({'success': False, 'error': 'Match not found.'}), 404
    if not is_cricket_name(sport_name):
        conn.close()
        return jsonify({'success': False, 'error': 'Complex events are only supported for cricket.'}), 400
    if status == 'COMPLETED':
        conn.close()
        return jsonify({'success': False, 'error': 'Cannot score a completed match.'}), 400
    if team_id not in (class1_id, class2_id):
        conn.close()
        return jsonify({'success': False, 'error': 'team_id is not part of this match.'}), 400

    _ensure_match_live(conn, match_id)
    conn.execute(
        'INSERT INTO score_log (match_id, team_id, points_scored, event_type, counts_as_ball) '
        'VALUES (?, ?, ?, ?, ?)',
        (match_id, team_id, points, event_type, counts_as_ball)
    )
    if extra_points > 0:
        # Wides & no-balls: the runs added do not consume an extra delivery.
        extra_counts_as_ball = 0 if event_type in NON_BALL_EVENTS else 1
        conn.execute(
            'INSERT INTO score_log (match_id, team_id, points_scored, event_type, counts_as_ball) '
            'VALUES (?, ?, ?, ?, ?)',
            (match_id, team_id, extra_points, 'Runs', extra_counts_as_ball)
        )
    conn.commit()
    new_stats = get_live_scores(conn, match_id, team_id)
    conn.close()

    return jsonify({
        'success': True, 'team_id': team_id, 'new_total': new_stats['score'],
        'new_wickets': new_stats['wickets'], 'new_overs': new_stats['overs'], 'new_balls': new_stats['balls']
    })

@app.route('/admin/matches/<int:match_id>/log-event', methods=['POST'])
@admin_required
def log_manual_event(match_id):
    """Logs a manual, non-scoring event from the HTML form."""
    team_id = request.form.get('team_id')
    event_description = request.form.get('event_description')
    if not all([team_id, event_description]):
        flash('Team and event description are required.', 'danger')
    else:
        conn = get_db_connection()
        sport_name, class1_id, class2_id, status, _ = _match_team_ids(conn, match_id)
        if sport_name is None:
            conn.close()
            flash('Match not found!', 'danger')
        elif status == 'COMPLETED':
            conn.close()
            flash('Cannot log events on a completed match.', 'warning')
        elif int(team_id) not in (class1_id, class2_id):
            conn.close()
            flash('Selected team is not part of this match.', 'danger')
        else:
            _ensure_match_live(conn, match_id)
            conn.execute(
                'INSERT INTO score_log (match_id, team_id, points_scored, event_type, counts_as_ball) VALUES (?, ?, ?, ?, ?)',
                (match_id, int(team_id), 0, event_description, 0)
            )
            conn.commit()
            conn.close()
            flash('Event logged successfully!', 'success')
    return redirect(url_for('live_score_editor', match_id=match_id))

@app.route('/admin/matches/<int:match_id>/finalize', methods=['POST'])
@admin_required
def finalize_match(match_id):
    """Finalises a match: decides the winner + result text from the score_log.

    Refuses to finalise when there is no clear winner (tied points or tied
    sets), and is idempotent for already-completed matches.
    """
    conn = get_db_connection()
    match = conn.execute('SELECT * FROM matches WHERE id = ?', (match_id,)).fetchone()
    if match is None:
        conn.close()
        flash('Match not found!', 'danger')
        return redirect(url_for('list_matches'))
    if match['status'] == 'COMPLETED':
        conn.close()
        flash('This match is already completed.', 'info')
        return redirect(url_for('list_matches'))

    winner_id, result_details_for_db = determine_winner(conn, match_id)
    if winner_id is None:
        conn.close()
        flash('Cannot finalize: no clear winner (tied score/sets). Please score more or edit the result manually.', 'danger')
        return redirect(url_for('live_score_editor', match_id=match_id))

    conn.execute(
        'UPDATE matches SET status = ?, winner_id = ?, result_details = ? WHERE id = ?',
        ('COMPLETED', winner_id, result_details_for_db, match_id)
    )
    conn.commit()
    conn.close()

    flash("Match finalized successfully.", 'success')
    return redirect(url_for('list_matches'))

@app.route('/admin/matches/<int:match_id>/undo', methods=['POST'])
@admin_required
def undo_last_event(match_id):
    conn = get_db_connection()
    status = conn.execute('SELECT status FROM matches WHERE id = ?', (match_id,)).fetchone()
    if status is None:
        conn.close()
        flash('Match not found!', 'danger')
        return redirect(url_for('list_matches'))
    if status['status'] == 'COMPLETED':
        conn.close()
        flash('Cannot undo events on a completed match.', 'warning')
        return redirect(url_for('live_score_editor', match_id=match_id))
    last_event = conn.execute(
        'SELECT id FROM score_log WHERE match_id = ? ORDER BY created_at DESC, id DESC LIMIT 1',
        (match_id,)
    ).fetchone()
    if last_event:
        conn.execute('DELETE FROM score_log WHERE id = ?', (last_event['id'],))
        conn.commit()
        flash('Last event has been undone.', 'success')
    else:
        flash('No event to undo.', 'warning')
    conn.close()
    return redirect(url_for('live_score_editor', match_id=match_id))

# --- CONTEXT PROCESSOR ---
@app.context_processor
def inject_announcement():
    """Injects the announcement text into all templates."""
    announcement_file = os.path.join(APP_ROOT, 'announcement.txt')
    announcement = ""
    if os.path.exists(announcement_file):
        with open(announcement_file, 'r') as f:
            announcement = f.read().strip()
    return dict(announcement=announcement)


# --- ERROR HANDLERS ---
@app.errorhandler(404)
def handle_404(e):
    """Renders a custom 404 Not Found page."""
    return render_template('public/404.html'), 404

@app.errorhandler(500)
def handle_500(e):
    """Renders a custom 500 Internal Server Error page."""
    return render_template('public/500.html'), 500

if __name__ == '__main__':
    app.run(debug=True)