"""Create or remove deterministic local demo data for the Docathon UI.

Usage from the backend directory:
    python seed/mock_data.py
    python seed/mock_data.py --clear

Only rows marked with MOCK_MARKER are created or removed by this script.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "docathon.db"
MOCK_MARKER = "[MOCK-DOCATHON]"

CLASS_NAMES = [
    "Demo Commerce A",
    "Demo Commerce B",
    "Demo Commerce C",
    "Demo Commerce D",
]
SPORTS = {
    "Basketball (B)": 1,
    "Cricket Boys": 1,
    "Volleyball": 1,
}


def _now(offset_hours: int = 0) -> str:
    return (dt.datetime.now().replace(microsecond=0) + dt.timedelta(hours=offset_hours)).isoformat(sep=" ")


def _get_or_create_id(conn: sqlite3.Connection, table: str, name: str, has_scores: int | None = None) -> int:
    row = conn.execute(f"SELECT id FROM {table} WHERE name = ?", (name,)).fetchone()
    if row:
        return row[0]
    if table == "sports":
        cursor = conn.execute("INSERT INTO sports (name, has_scores) VALUES (?, ?)", (name, has_scores or 0))
    else:
        cursor = conn.execute(f"INSERT INTO {table} (name) VALUES (?)", (name,))
    return cursor.lastrowid


def _round_id(conn: sqlite3.Connection, sport_id: int, round_type: str) -> int:
    name = f"{MOCK_MARKER} {round_type.replace('_', ' ').title()}"
    row = conn.execute(
        "SELECT id FROM rounds WHERE sport_id = ? AND name = ?",
        (sport_id, name),
    ).fetchone()
    if row:
        return row[0]
    cursor = conn.execute(
        "INSERT INTO rounds (sport_id, name, round_type) VALUES (?, ?, ?)",
        (sport_id, name, round_type),
    )
    return cursor.lastrowid


def _match(
    conn: sqlite3.Connection,
    sport_id: int,
    round_id: int,
    class1_id: int,
    class2_id: int,
    match_time: str,
    status: str,
    winner_id: int | None = None,
    result: str | None = None,
) -> int:
    row = conn.execute(
        "SELECT id FROM matches WHERE notes = ? AND sport_id = ? AND round_id = ? AND class1_id = ? AND class2_id = ?",
        (MOCK_MARKER, sport_id, round_id, class1_id, class2_id),
    ).fetchone()
    if row:
        match_id = row[0]
        conn.execute(
            "UPDATE matches SET sport_id = ?, round_id = ?, match_time = ?, status = ?, winner_id = ?, result_details = ? WHERE id = ?",
            (sport_id, round_id, match_time, status, winner_id, result, match_id),
        )
        return match_id
    cursor = conn.execute(
        """INSERT INTO matches
        (sport_id, round_id, class1_id, class2_id, match_time, status, winner_id, result_details, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (sport_id, round_id, class1_id, class2_id, match_time, status, winner_id, result, MOCK_MARKER),
    )
    return cursor.lastrowid


def _replace_score_log(conn: sqlite3.Connection, match_id: int, events: list[tuple[int, int, str, int]]) -> None:
    conn.execute("DELETE FROM score_log WHERE match_id = ?", (match_id,))
    conn.executemany(
        "INSERT INTO score_log (match_id, team_id, points_scored, event_type, counts_as_ball) VALUES (?, ?, ?, ?, ?)",
        [(match_id, team_id, points, event_type, counts) for team_id, points, event_type, counts in events],
    )


def _set_events(team_id: int, opponent_id: int, winning_sets: int = 2) -> list[tuple[int, int, str, int]]:
    events: list[tuple[int, int, str, int]] = []
    for set_index in range(winning_sets):
        for _ in range(25):
            events.append((team_id, 1, "Point", 0))
        for _ in range(20):
            events.append((opponent_id, 1, "Point", 0))
        events.append((team_id, 0, "Set End", 0))
    return events


def clear_mock_data(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM score_log WHERE match_id IN (SELECT id FROM matches WHERE notes = ?)", (MOCK_MARKER,))
    conn.execute("DELETE FROM matches WHERE notes = ?", (MOCK_MARKER,))
    conn.execute("DELETE FROM rounds WHERE name LIKE ?", (f"{MOCK_MARKER}%",))
    conn.execute("DELETE FROM point_adjustments WHERE reason LIKE ?", (f"{MOCK_MARKER}%",))
    conn.execute("DELETE FROM stories WHERE title LIKE ?", (f"{MOCK_MARKER}%",))
    conn.execute("DELETE FROM team_members WHERE role LIKE ?", (f"{MOCK_MARKER}%",))
    conn.commit()


def seed_mock_data(db_path: Path | str = DB_PATH) -> dict[str, int]:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        classes = {name: _get_or_create_id(conn, "classes", name) for name in CLASS_NAMES}
        sports = {
            name: _get_or_create_id(conn, "sports", name, has_scores)
            for name, has_scores in SPORTS.items()
        }

        basketball_qf = _round_id(conn, sports["Basketball (B)"], "QUARTER_FINAL")
        basketball_sf = _round_id(conn, sports["Basketball (B)"], "SEMI_FINAL")
        basketball_final = _round_id(conn, sports["Basketball (B)"], "FINAL")
        cricket_group = _round_id(conn, sports["Cricket Boys"], "GROUP")
        volleyball_group = _round_id(conn, sports["Volleyball"], "GROUP")
        volleyball_final = _round_id(conn, sports["Volleyball"], "FINAL")

        upcoming = _match(
            conn, sports["Volleyball"], volleyball_group,
            classes[CLASS_NAMES[1]], classes[CLASS_NAMES[2]], _now(24), "UPCOMING",
        )
        live = _match(
            conn, sports["Cricket Boys"], cricket_group,
            classes[CLASS_NAMES[0]], classes[CLASS_NAMES[3]], _now(-1), "LIVE",
            result="Live score: Demo Commerce A 42/2, Demo Commerce D 37/3",
        )
        _replace_score_log(conn, live, [
            (classes[CLASS_NAMES[0]], 4, "Boundary", 1),
            (classes[CLASS_NAMES[0]], 1, "Run", 1),
            (classes[CLASS_NAMES[0]], 6, "Boundary", 1),
            (classes[CLASS_NAMES[0]], 0, "Wicket", 1),
            (classes[CLASS_NAMES[0]], 31, "Runs", 1),
            (classes[CLASS_NAMES[3]], 6, "Boundary", 1),
            (classes[CLASS_NAMES[3]], 1, "Run", 1),
            (classes[CLASS_NAMES[3]], 30, "Runs", 1),
            (classes[CLASS_NAMES[3]], 0, "Wicket", 1),
        ])

        qf1 = _match(
            conn, sports["Basketball (B)"], basketball_qf,
            classes[CLASS_NAMES[0]], classes[CLASS_NAMES[1]], _now(-96), "COMPLETED",
            classes[CLASS_NAMES[0]], "Demo Commerce A won 68-61",
        )
        qf2 = _match(
            conn, sports["Basketball (B)"], basketball_qf,
            classes[CLASS_NAMES[2]], classes[CLASS_NAMES[3]], _now(-90), "COMPLETED",
            classes[CLASS_NAMES[2]], "Demo Commerce C won 59-52",
        )
        sf = _match(
            conn, sports["Basketball (B)"], basketball_sf,
            classes[CLASS_NAMES[0]], classes[CLASS_NAMES[2]], _now(-48), "COMPLETED",
            classes[CLASS_NAMES[0]], "Demo Commerce A won 74-70",
        )
        final = _match(
            conn, sports["Basketball (B)"], basketball_final,
            classes[CLASS_NAMES[0]], classes[CLASS_NAMES[2]], _now(-24), "COMPLETED",
            classes[CLASS_NAMES[0]], "Demo Commerce A won 81-76",
        )
        for match_id, winner_id, loser_id, winner_score, loser_score in [
            (qf1, classes[CLASS_NAMES[0]], classes[CLASS_NAMES[1]], 68, 61),
            (qf2, classes[CLASS_NAMES[2]], classes[CLASS_NAMES[3]], 59, 52),
            (sf, classes[CLASS_NAMES[0]], classes[CLASS_NAMES[2]], 74, 70),
            (final, classes[CLASS_NAMES[0]], classes[CLASS_NAMES[2]], 81, 76),
        ]:
            _replace_score_log(conn, match_id, [
                (winner_id, winner_score, "Points", 0),
                (loser_id, loser_score, "Points", 0),
            ])

        sets_match = _match(
            conn, sports["Volleyball"], volleyball_final,
            classes[CLASS_NAMES[2]], classes[CLASS_NAMES[1]], _now(-12), "COMPLETED",
            classes[CLASS_NAMES[2]], "Demo Commerce C won 2-0 in sets",
        )
        _replace_score_log(conn, sets_match, _set_events(classes[CLASS_NAMES[2]], classes[CLASS_NAMES[1]]))

        adjustment_reason = f"{MOCK_MARKER} Sportsmanship bonus"
        if not conn.execute(
            "SELECT 1 FROM point_adjustments WHERE reason = ?",
            (adjustment_reason,),
        ).fetchone():
            conn.execute(
                "INSERT INTO point_adjustments (class_id, points, reason) VALUES (?, ?, ?)",
                (classes[CLASS_NAMES[1]], 3, adjustment_reason),
            )
        for name, role in [
            ("Dr. Maya Demo", "{0} Faculty Coordinator"),
            ("Aarav Demo", "{0} Student Coordinator"),
            ("Ishita Demo", "{0} Events Lead"),
        ]:
            demo_role = role.format(MOCK_MARKER)
            if not conn.execute(
                "SELECT 1 FROM team_members WHERE name = ? AND role = ?",
                (name, demo_role),
            ).fetchone():
                conn.execute(
                    "INSERT INTO team_members (name, role, photo_filename) VALUES (?, ?, NULL)",
                    (name, demo_role),
                )
        stories = [
            ("Matchday one sets the tone", "The first mock matchday brought close finishes, strong teamwork and a packed schedule.", "Docathon Staff"),
            ("Commerce classes prepare for finals", "Teams are building momentum across the bracket as the tournament moves toward its final round.", "Sports Desk"),
        ]
        for title, content, author in stories:
            demo_title = f"{MOCK_MARKER} {title}"
            if not conn.execute(
                "SELECT 1 FROM stories WHERE title = ?",
                (demo_title,),
            ).fetchone():
                conn.execute(
                    "INSERT INTO stories (title, content, author, image_filename) VALUES (?, ?, ?, NULL)",
                    (demo_title, content, author),
                )
        conn.commit()
        return {
            "classes": len(classes),
            "sports": len(sports),
            "matches": 7,
            "stories": len(stories),
            "team_members": 3,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed or clear local Docathon mock data.")
    parser.add_argument("--clear", action="store_true", help="Remove only rows created by this script.")
    args = parser.parse_args()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        if args.clear:
            clear_mock_data(conn)
            print("Mock data cleared.")
        else:
            print(seed_mock_data(DB_PATH))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
