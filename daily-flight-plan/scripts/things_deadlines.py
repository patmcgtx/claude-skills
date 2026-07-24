#!/usr/bin/env python3
"""
Pulls today's "Time-sensitive" to-dos out of the Things (culturedcode.com)
SQLite database: open to-dos with a real deadline set that is today or
earlier (overdue). Not the same query as things-report's backlog view --
this deliberately only looks at the *deadline* field, not the "when"/start
date, since a to-do can be scheduled for Today without ever being marked
deadline-sensitive.

Reuses the same safety measures as ~/.claude/skills/things-report/scripts/things_query.py:
the live database is locked while Things.app runs, and recent edits may only
exist in the -wal file, so a staged copy (main.sqlite + -wal + -shm) is opened
instead of the live path. Recurring-task template rows are excluded (they
carry a fake deadline that decodes to a nonsense date, not a real one).

Usage:
    python3 things_deadlines.py [--db /path/to/main.sqlite] [--end YYYY-MM-DD]

Prints one JSON array to stdout: [{title, deadline, project}, ...]
sorted with overdue items first (oldest deadline first), then today's.
"""

import argparse
import glob
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone

TYPE_TODO = 0
STATUS_OPEN = 0

NOT_A_TEMPLATE = "rt1_recurrenceRule IS NULL"

# Same bit layout as things_query.py -- verified against thingsapi/things.py.
Y_MASK, M_MASK, D_MASK = 0b111111111110000000000000000, 0b1111000000000000, 0b111110000000


def decode_thingsdate(value):
    if value is None:
        return None
    year = (value & Y_MASK) >> 16
    month = (value & M_MASK) >> 12
    day = (value & D_MASK) >> 7
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def find_db_candidates():
    patterns = [
        os.path.expanduser(
            "~/Library/Group Containers/*.com.culturedcode.ThingsMac/*/Things Database.thingsdatabase/main.sqlite"
        ),
        os.path.expanduser(
            "~/Library/Containers/com.culturedcode.ThingsMac/Data/Library/Group Containers/*.com.culturedcode.ThingsMac/*/Things Database.thingsdatabase/main.sqlite"
        ),
    ]
    found = []
    for pattern in patterns:
        found.extend(glob.glob(pattern))
    return found


def resolve_db_path(explicit_path):
    if explicit_path:
        return explicit_path
    candidates = find_db_candidates()
    if not candidates:
        sys.exit(
            "Could not find a Things database under ~/Library/Group Containers. "
            "Pass --db /path/to/main.sqlite explicitly, or check that Things is installed."
        )
    return max(candidates, key=os.path.getmtime)


def stage_db_copy(source_path, workdir):
    dest = os.path.join(workdir, "main.sqlite")
    shutil.copy2(source_path, dest)
    for suffix in ("-wal", "-shm"):
        side = source_path + suffix
        if os.path.exists(side):
            shutil.copy2(side, dest + suffix)
    return dest


def connect(db_path):
    workdir = tempfile.mkdtemp(prefix="things_deadlines_")
    staged = stage_db_copy(db_path, workdir)
    conn = sqlite3.connect(staged)
    conn.row_factory = sqlite3.Row
    return conn


def get_excluded_uuids(conn):
    """Areas/projects/to-dos tagged 'Exclude' -- the user's explicit, durable
    opt-out (see things-report's SKILL.md). Honored here too: if something is
    kept out of productivity reporting on purpose, it shouldn't surface in the
    daily journal plan either."""
    excluded_areas = {
        r[0]
        for r in conn.execute(
            """
            SELECT at.areas FROM TMAreaTag at
            JOIN TMTag tg ON at.tags = tg.uuid
            WHERE tg.title = 'Exclude'
            """
        ).fetchall()
    }
    excluded_tasks = {
        r[0]
        for r in conn.execute(
            """
            SELECT tt.tasks FROM TMTaskTag tt
            JOIN TMTag tg ON tt.tags = tg.uuid
            WHERE tg.title = 'Exclude'
            """
        ).fetchall()
    }
    return excluded_areas, excluded_tasks


def query_deadline_todos(conn, end_date):
    excluded_areas, excluded_tasks = get_excluded_uuids(conn)
    rows = conn.execute(
        """
        SELECT t.uuid, t.title, t.deadline, t.area, t.project,
               proj.title AS project_title, proj.area AS proj_area
        FROM TMTask t
        LEFT JOIN TMTask proj ON t.project = proj.uuid
        WHERE t.type = ? AND t.status = ? AND t.trashed = 0 AND t.{not_template}
          AND t.deadline IS NOT NULL
        """.format(not_template=NOT_A_TEMPLATE),
        (TYPE_TODO, STATUS_OPEN),
    ).fetchall()

    end_iso = end_date.date().isoformat()
    out = []
    for r in rows:
        if r["uuid"] in excluded_tasks:
            continue
        effective_area = r["area"] or r["proj_area"]
        if effective_area in excluded_areas:
            continue
        deadline_iso = decode_thingsdate(r["deadline"])
        if deadline_iso is None or deadline_iso > end_iso:
            continue
        out.append(
            {
                "title": r["title"],
                "deadline": deadline_iso,
                "project": r["project_title"],
                "overdue": deadline_iso < end_iso,
            }
        )

    out.sort(key=lambda x: x["deadline"])
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None, help="Explicit path to main.sqlite.")
    parser.add_argument("--end", default=None, help="ISO date to treat as 'today' (default: today).")
    args = parser.parse_args()

    end = (
        datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
        if args.end
        else datetime.now(timezone.utc)
    )

    db_path = resolve_db_path(args.db)
    conn = connect(db_path)
    result = query_deadline_todos(conn, end)
    conn.close()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
