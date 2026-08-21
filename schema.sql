-- DOCATHON database schema
-- Source of truth for a fresh database.
-- Existing databases should be upgraded with the migration scripts.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS sports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    has_scores INTEGER NOT NULL DEFAULT 0 CHECK (has_scores IN (0, 1))
);

CREATE TABLE IF NOT EXISTS rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    round_type TEXT NOT NULL CHECK (round_type IN (
        'GROUP', 'KNOCKOUT', 'QUARTER_FINAL', 'SEMI_FINAL', 'FINAL'
    )),
    FOREIGN KEY (sport_id) REFERENCES sports(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    UNIQUE (sport_id, name)
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id INTEGER NOT NULL,
    round_id INTEGER NOT NULL,
    class1_id INTEGER NOT NULL,
    class2_id INTEGER NOT NULL,
    winner_id INTEGER,
    result_details TEXT,
    status TEXT NOT NULL DEFAULT 'UPCOMING'
        CHECK (status IN ('UPCOMING', 'LIVE', 'COMPLETED')),
    match_time TEXT NOT NULL,
    notes TEXT,
    scorecard_url TEXT,
    live_match_state TEXT,
    FOREIGN KEY (sport_id) REFERENCES sports(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (round_id) REFERENCES rounds(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (class1_id) REFERENCES classes(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (class2_id) REFERENCES classes(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (winner_id) REFERENCES classes(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CHECK (class1_id <> class2_id),
    CHECK (winner_id IS NULL OR winner_id = class1_id OR winner_id = class2_id),
    CHECK (status <> 'COMPLETED' OR winner_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS score_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    points_scored INTEGER NOT NULL DEFAULT 0,
    event_type TEXT NOT NULL,
    counts_as_ball INTEGER NOT NULL DEFAULT 0 CHECK (counts_as_ball IN (0, 1)),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES classes(id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS point_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL,
    points INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (class_id) REFERENCES classes(id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    author TEXT,
    image_filename TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    photo_filename TEXT
);

CREATE INDEX IF NOT EXISTS idx_matches_round_id ON matches(round_id);
CREATE INDEX IF NOT EXISTS idx_matches_sport_id ON matches(sport_id);
CREATE INDEX IF NOT EXISTS idx_matches_class1_id ON matches(class1_id);
CREATE INDEX IF NOT EXISTS idx_matches_class2_id ON matches(class2_id);
CREATE INDEX IF NOT EXISTS idx_matches_winner_id ON matches(winner_id);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);
CREATE INDEX IF NOT EXISTS idx_score_log_match_id ON score_log(match_id);
CREATE INDEX IF NOT EXISTS idx_score_log_team_id ON score_log(team_id);
CREATE INDEX IF NOT EXISTS idx_score_log_created_at ON score_log(created_at);
CREATE INDEX IF NOT EXISTS idx_point_adjustments_class_id ON point_adjustments(class_id);
CREATE INDEX IF NOT EXISTS idx_point_adjustments_created_at ON point_adjustments(created_at);
CREATE INDEX IF NOT EXISTS idx_stories_created_at ON stories(created_at);