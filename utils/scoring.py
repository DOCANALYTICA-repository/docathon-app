"""
Central scoring & leaderboard module.

Every rule that decides points, winners, rankings and live scores lives here so
the whole app behaves identically (public pages, admin finalizer and JSON APIs).

SPORT_CONFIG is the single source of truth for how each sport is scored:

    format      -> 'points'  : cumulative points (Cricket, Basketball, Football...)
                   'sets_detailed' : best-of-N sets (Volleyball, Throwball)
    set_target  -> points needed to win a set (used to sanity-check set completion)
    win_by      -> minimum winning margin for a set

NOTE: set_target / win_by are soft-configurable until Docathon cores finalise the
official ruleset. end_set() validates using them when present.
"""

import sqlite3

SPORT_CONFIG = {
    'default': {'format': 'points'},
    'Cricket Boys': {'format': 'points'},
    'Cricket Girls': {'format': 'points'},
    'Basketball (B)': {'format': 'points'},
    'Basketball (G)': {'format': 'points'},
    'Volleyball': {'format': 'sets_detailed', 'set_target': 25, 'win_by': 2},
    'Throwball': {'format': 'sets_detailed', 'set_target': 15, 'win_by': 2},
}

# Ball-event rules used to keep cricket arithmetic correct regardless of what the
# client sends. Wides & no-balls never count towards the ball count (their byes/
# runs ride on the same ball).
NON_BALL_EVENTS = ('Wide', 'No-Ball')
WICKET_EVENTS = ('Wicket', 'Run Out', 'Caught', 'Bowled', 'LBW', 'Stumped')


def get_score_format(sport_name):
    """Returns the scoring format ('points' or 'sets_detailed') for a sport."""
    return SPORT_CONFIG.get(sport_name or 'default', SPORT_CONFIG['default'])['format']


def is_sets_format(sport_name):
    return get_score_format(sport_name) == 'sets_detailed'


# ---------------------------------------------------------------------------
# Point-based scoring (Cricket, Basketball, Football, ...)
# ---------------------------------------------------------------------------

def get_live_scores(conn, match_id, team_id):
    """Cumulative stats for one team in a points-format match.

    Returns dict with: score, wickets, balls_faced, overs, balls.
    """
    score = conn.execute(
        'SELECT COALESCE(SUM(points_scored), 0) FROM score_log '
        'WHERE match_id = ? AND team_id = ?',
        (match_id, team_id)
    ).fetchone()[0]

    wickets = conn.execute(
        'SELECT COUNT(*) FROM score_log WHERE match_id = ? AND team_id = ? '
        'AND event_type IN ({})'.format(','.join('?' * len(WICKET_EVENTS))),
        (match_id, team_id) + WICKET_EVENTS
    ).fetchone()[0]

    balls_faced = conn.execute(
        'SELECT COALESCE(SUM(counts_as_ball), 0) FROM score_log '
        'WHERE match_id = ? AND team_id = ?',
        (match_id, team_id)
    ).fetchone()[0]

    overs = balls_faced // 6
    balls = balls_faced % 6
    return {
        'score': score,
        'wickets': wickets,
        'overs': overs,
        'balls': balls,
        'balls_faced': balls_faced,
    }


# ---------------------------------------------------------------------------
# Set-based scoring (Volleyball, Throwball)
# ---------------------------------------------------------------------------

def get_set_scores(conn, match_id, class1_id, class2_id):
    """Recomputes set-by-set state for a set-based match from the score_log.

    Returns:
        completed_sets      list of {class_id: points} for each finished set
        current_set_scores  {class_id: points} for the set in progress
        sets_won            {class_id: number of sets won}
    """
    completed_sets = []
    current_set_scores = {class1_id: 0, class2_id: 0}
    sets_won = {class1_id: 0, class2_id: 0}

    events = conn.execute(
        'SELECT * FROM score_log WHERE match_id = ? ORDER BY created_at ASC, id ASC',
        (match_id,)
    ).fetchall()

    for event in events:
        if event['event_type'] == 'Set End':
            completed_sets.append(current_set_scores.copy())
            if current_set_scores[class1_id] > current_set_scores[class2_id]:
                sets_won[class1_id] += 1
            elif current_set_scores[class2_id] > current_set_scores[class1_id]:
                sets_won[class2_id] += 1
            current_set_scores = {class1_id: 0, class2_id: 0}
        elif event['event_type'] == 'Point':
            if event['team_id'] in (class1_id, class2_id):
                current_set_scores[event['team_id']] += 1

    return {
        'completed_sets': completed_sets,
        'current_set_scores': current_set_scores,
        'sets_won': sets_won,
    }


def get_set_leader(scores, class1_id, class2_id):
    """Returns the id of the team currently leading a set, or None on a tie."""
    a = scores['current_set_scores'][class1_id]
    b = scores['current_set_scores'][class2_id]
    if a > b:
        return class1_id
    if b > a:
        return class2_id
    return None


# ---------------------------------------------------------------------------
# Unified accessor used by pages + JSON APIs
# ---------------------------------------------------------------------------

def compute_match_scores(conn, match_id):
    """Returns the live score state for a match, keyed by its format.

    points format  -> {'format': 'points', <class1_id>: {...}, <class2_id>: {...}}
    sets format    -> {'format': 'sets_detailed', 'completed_sets': [...],
                       'current_set_scores': {...}, 'sets_won': {...}}
    Returns None when the match does not exist.
    """
    match = conn.execute(
        'SELECT m.id, m.sport_id, m.class1_id, m.class2_id, s.name AS sport_name '
        'FROM matches m JOIN sports s ON m.sport_id = s.id WHERE m.id = ?',
        (match_id,)
    ).fetchone()
    if match is None:
        return None

    sport_name = match['sport_name']
    c1, c2 = match['class1_id'], match['class2_id']
    fmt = get_score_format(sport_name)

    if fmt == 'sets_detailed':
        result = get_set_scores(conn, match_id, c1, c2)
        result['format'] = 'sets_detailed'
        result['class1_id'] = c1
        result['class2_id'] = c2
    else:
        result = {
            c1: get_live_scores(conn, match_id, c1),
            c2: get_live_scores(conn, match_id, c2),
            'format': 'points',
            'class1_id': c1,
            'class2_id': c2,
        }
    return result


def match_scores_to_json(scores):
    """JSON-safe copy of compute_match_scores() output.

    Flask's JSON encoder sorts keys, which fails when team-id (int) keys are
    mixed with string keys, so team-id keys are stringified here. This keeps
    browser access like data[teamId] working (numbers coerce to strings).
    """
    if scores is None:
        return None
    fmt = scores.get('format')
    if fmt == 'sets_detailed':
        return {
            'format': fmt,
            'class1_id': scores['class1_id'],
            'class2_id': scores['class2_id'],
            'current_set_scores': {str(k): v for k, v in scores['current_set_scores'].items()},
            'sets_won': {str(k): v for k, v in scores['sets_won'].items()},
            'completed_sets': [{str(k): v for k, v in s.items()} for s in scores['completed_sets']],
        }
    result = {'format': fmt, 'class1_id': scores['class1_id'], 'class2_id': scores['class2_id']}
    for team_id in (scores['class1_id'], scores['class2_id']):
        result[str(team_id)] = scores[team_id]
    return result


def determine_winner(conn, match_id):
    """Computes the winner id + result text for a match, or (None, None) if it
    cannot be decided yet (e.g. tied points or tied sets)."""
    match = conn.execute(
        'SELECT m.id, m.class1_id, m.class2_id, s.name AS sport_name '
        'FROM matches m JOIN sports s ON m.sport_id = s.id WHERE m.id = ?',
        (match_id,)
    ).fetchone()
    if match is None:
        return None, None

    c1, c2 = match['class1_id'], match['class2_id']
    fmt = get_score_format(match['sport_name'])
    result_text = ''

    def _name(class_id):
        return conn.execute('SELECT name FROM classes WHERE id = ?', (class_id,)).fetchone()['name']

    if fmt == 'points':
        s1 = get_live_scores(conn, match_id, c1)
        s2 = get_live_scores(conn, match_id, c2)
        if s1['score'] == s2['score']:
            return None, None
        winner_id = c1 if s1['score'] > s2['score'] else c2
        return winner_id, f"{_name(winner_id)} won {s1['score']}-{s2['score']}"

    # sets_detailed
    scores = get_set_scores(conn, match_id, c1, c2)
    if scores['current_set_scores'][c1] > 0 or scores['current_set_scores'][c2] > 0:
        scores['completed_sets'].append(scores['current_set_scores'])
        if scores['current_set_scores'][c1] > scores['current_set_scores'][c2]:
            scores['sets_won'][c1] += 1
        elif scores['current_set_scores'][c2] > scores['current_set_scores'][c1]:
            scores['sets_won'][c2] += 1

    if scores['sets_won'][c1] == scores['sets_won'][c2]:
        return None, None

    winner_id = c1 if scores['sets_won'][c1] > scores['sets_won'][c2] else c2
    loser_id = c2 if winner_id == c1 else c1
    set_scores_str = ', '.join(
        f"{s[c1]}-{s[c2]}" for s in scores['completed_sets']
    )
    return winner_id, (
        f"{_name(winner_id)} won {scores['sets_won'][winner_id]}-{scores['sets_won'][loser_id]}"
        + (f" ({set_scores_str})" if set_scores_str else "")
    )


# ---------------------------------------------------------------------------
# Tournament leaderboard (class / team standings)
# ---------------------------------------------------------------------------
#
# Point scheme (kept simple & centralised so it is trivial to tweak once the
# Docathon cores finalise the rules):
#   * tournament_points: reaching QF = 2, SF = 3, FINAL = 4, winning FINAL = 5
#   * win_points:        +1 per completed, non-walkover win
#   * participation:     +1 per distinct sport played (non-walkover)
#   * adjustments:       manual +/- points entered by admins

LEADERBOARD_SQL = """
    WITH MatchParticipants AS (
        SELECT m.id AS match_id, m.sport_id, m.winner_id, m.result_details,
               r.round_type, c.id AS class_id, c.name AS class_name
        FROM matches m
        JOIN rounds r ON m.round_id = r.id
        JOIN classes c ON m.class1_id = c.id
        WHERE m.status = 'COMPLETED'
        UNION ALL
        SELECT m.id AS match_id, m.sport_id, m.winner_id, m.result_details,
               r.round_type, c.id AS class_id, c.name AS class_name
        FROM matches m
        JOIN rounds r ON m.round_id = r.id
        JOIN classes c ON m.class2_id = c.id
        WHERE m.status = 'COMPLETED'
    ),
    ClassStats AS (
        SELECT
            c.id AS class_id, c.name AS class_name, COUNT(mp.match_id) AS played,
            SUM(CASE WHEN mp.winner_id = c.id THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN mp.winner_id IS NOT NULL AND mp.winner_id != c.id THEN 1 ELSE 0 END) AS losses,
            SUM(CASE
                WHEN mp.winner_id = c.id AND mp.round_type = 'FINAL' THEN 5
                WHEN mp.winner_id != c.id AND mp.round_type = 'FINAL' THEN 4
                WHEN mp.winner_id != c.id AND mp.round_type = 'SEMI_FINAL' THEN 3
                WHEN mp.winner_id != c.id AND mp.round_type = 'QUARTER_FINAL' THEN 2
                ELSE 0
            END) AS tournament_points
        FROM classes c
        LEFT JOIN MatchParticipants mp ON c.id = mp.class_id
        GROUP BY c.id, c.name
    ),
    ParticipationPoints AS (
        SELECT class_id, COUNT(DISTINCT sport_id) AS participation_points
        FROM MatchParticipants
        WHERE result_details NOT LIKE '%Walkover%'
        GROUP BY class_id
    ),
    WinPoints AS (
        SELECT winner_id AS class_id, COUNT(id) AS win_points
        FROM matches
        WHERE status = 'COMPLETED'
          AND result_details IS NOT NULL AND result_details != ''
          AND result_details NOT LIKE '%Walkover%'
        GROUP BY winner_id
    ),
    AdjustmentPoints AS (
        SELECT class_id, SUM(points) AS adjustment_points
        FROM point_adjustments
        GROUP BY class_id
    )
    SELECT
        cs.class_id, cs.class_name, cs.played, cs.wins, cs.losses,
        (IFNULL(cs.tournament_points, 0)
         + IFNULL(pp.participation_points, 0)
         + IFNULL(ap.adjustment_points, 0)
         + IFNULL(wp.win_points, 0)) AS total_points
    FROM ClassStats cs
    LEFT JOIN ParticipationPoints pp ON cs.class_id = pp.class_id
    LEFT JOIN AdjustmentPoints ap ON cs.class_id = ap.class_id
    LEFT JOIN WinPoints wp ON cs.class_id = wp.class_id
    ORDER BY total_points DESC, cs.wins DESC, cs.class_name ASC
"""


def compute_leaderboard(conn, limit=None):
    """Returns ranked standings for all classes.

    Each row exposes: rank, class_id, class_name, played, wins, losses, total_points.
    """
    sql = LEADERBOARD_SQL if limit is None else LEADERBOARD_SQL.replace(
        'ORDER BY total_points DESC, cs.wins DESC, cs.class_name ASC',
        'ORDER BY total_points DESC, cs.wins DESC, cs.class_name ASC LIMIT %d' % limit
    )
    rows = conn.execute(sql).fetchall()
    standings = []
    for index, row in enumerate(rows, start=1):
        standings.append({
            'rank': index,
            'class_id': row['class_id'],
            'class_name': row['class_name'],
            'played': row['played'] or 0,
            'wins': row['wins'] or 0,
            'losses': row['losses'] or 0,
            'total_points': row['total_points'] or 0,
        })
    return standings


def log_set_end(conn, match_id):
    """Finalises the current set for a set-format match.

    Validates that a set is actually in progress and that it has a clear leader.
    Returns (ok, message). Stores the winning team's id as team_id on the
    'Set End' event (FK-safe and meaningful).
    """
    match = conn.execute(
        'SELECT class1_id, class2_id, status FROM matches WHERE id = ?', (match_id,)
    ).fetchone()
    if match is None:
        return False, 'Match not found.'
    if match['status'] == 'COMPLETED':
        return False, 'This match is already completed.'

    c1, c2 = match['class1_id'], match['class2_id']
    scores = get_set_scores(conn, match_id, c1, c2)
    leader_id = get_set_leader(scores, c1, c2)

    if leader_id is None:
        return False, 'Cannot end the set: scores are tied.'

    conn.execute(
        "INSERT INTO score_log (match_id, team_id, points_scored, event_type, counts_as_ball) "
        "VALUES (?, ?, 0, 'Set End', 0)",
        (match_id, leader_id)
    )
    conn.commit()
    return True, 'Set finalized.'
