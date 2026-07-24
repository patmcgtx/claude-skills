#!/usr/bin/env python3
"""
Checks Day One's local database for an existing "Daily Flight Plan" entry on
a given date, so the skill can warn before creating a duplicate -- the
`dayone` CLI can only create entries, it has no edit/upsert, so running the
skill twice in a day would otherwise silently produce two entries.

Deliberately prints only the first line (title) and metadata of any match,
never the full entry text -- this script's job is duplicate *detection*, not
reading the user's journal content.

Usage:
    python3 check_existing_plan.py [--db /path/to/DayOne.sqlite] [--date YYYY-MM-DD]

Prints one JSON object: {"exists": bool, "matches": [{"title_line", "created", "journal"}]}
"""

import argparse
import glob
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

# Core Data's reference date is 2001-01-01T00:00:00Z, not the Unix epoch --
# ZCREATIONDATE etc. are seconds since that reference date.
CORE_DATA_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)

# The template always opens with this exact line (see references/
# daily_flight_plan_template.md) -- used as the duplicate-detection marker
# rather than matching on ZTEMPLATE's row id, since that id isn't known
# ahead of time and titles/first lines are stable.
MARKER = "🚀 Daily Flight Plan"


def find_db_candidates():
    return glob.glob(
        os.path.expanduser(
            "~/Library/Group Containers/*.dayoneapp*/Data/Documents/DayOne.sqlite"
        )
    )


def resolve_db_path(explicit_path):
    if explicit_path:
        return explicit_path
    candidates = find_db_candidates()
    if not candidates:
        sys.exit(
            "Could not find a Day One database under ~/Library/Group Containers. "
            "Pass --db /path/to/DayOne.sqlite explicitly, or check that Day One is installed."
        )
    return max(candidates, key=os.path.getmtime)


def stage_db_copy(source_path, workdir):
    dest = os.path.join(workdir, "DayOne.sqlite")
    shutil.copy2(source_path, dest)
    for suffix in ("-wal", "-shm"):
        side = source_path + suffix
        if os.path.exists(side):
            shutil.copy2(side, dest + suffix)
    return dest


def connect(db_path):
    workdir = tempfile.mkdtemp(prefix="dayone_check_")
    staged = stage_db_copy(db_path, workdir)
    conn = sqlite3.connect(staged)
    conn.row_factory = sqlite3.Row
    return conn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None, help="Explicit path to DayOne.sqlite.")
    parser.add_argument("--date", default=None, help="ISO date to check (default: today).")
    args = parser.parse_args()

    target = (
        datetime.fromisoformat(args.date).date()
        if args.date
        else datetime.now().date()
    )

    db_path = resolve_db_path(args.db)
    conn = connect(db_path)

    rows = conn.execute(
        """
        SELECT e.ZMARKDOWNTEXT, e.ZCREATIONDATE, j.ZNAME
        FROM ZENTRY e
        LEFT JOIN ZJOURNAL j ON e.ZJOURNAL = j.Z_PK
        WHERE e.ZGREGORIANYEAR = ? AND e.ZGREGORIANMONTH = ? AND e.ZGREGORIANDAY = ?
        """,
        (target.year, target.month, target.day),
    ).fetchall()
    conn.close()

    matches = []
    for r in rows:
        text = r["ZMARKDOWNTEXT"] or ""
        if MARKER not in text:
            continue
        first_line = text.strip().splitlines()[0] if text.strip() else ""
        created = None
        if r["ZCREATIONDATE"] is not None:
            created = (CORE_DATA_EPOCH + timedelta(seconds=r["ZCREATIONDATE"])).isoformat()
        matches.append({"title_line": first_line, "created": created, "journal": r["ZNAME"]})

    print(json.dumps({"exists": len(matches) > 0, "matches": matches}, indent=2))


if __name__ == "__main__":
    main()
