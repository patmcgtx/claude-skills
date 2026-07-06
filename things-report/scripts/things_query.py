#!/usr/bin/env python3
"""
Pulls a structured JSON snapshot out of the Things (culturedcode.com) SQLite
database: completed-work summary, backlog health, velocity vs. the prior
period, and per-project stats.

Why a script instead of ad-hoc SQL each time: the deadline/startDate fields
are bit-packed integers (see references/schema.md), and the live database
file is locked while Things.app is running. Getting both of those wrong
silently produces plausible-looking-but-wrong numbers, so it's worth writing
once and reusing.

Usage:
    python3 things_query.py [--days 30] [--db /path/to/main.sqlite] [--end YYYY-MM-DD]

Prints one JSON object to stdout.
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

STATUS_OPEN, STATUS_CANCELED, STATUS_COMPLETE = 0, 2, 3
TYPE_TODO, TYPE_PROJECT, TYPE_HEADING = 0, 1, 2
START_INBOX, START_ANYTIME, START_SOMEDAY = 0, 1, 2

# A recurring to-do's *template* row (the thing you actually edit when you edit
# a repeating task) sits in the table looking like a normal open to-do, but it's
# not an actionable item -- Things spawns real instances from it. It's the only
# row with a non-null rt1_recurrenceRule, and its deadline/startDate are
# scheduling offsets rather than real dates, so it must be excluded everywhere
# we filter on type = TYPE_TODO.
NOT_A_TEMPLATE = "rt1_recurrenceRule IS NULL"

# Bit layout for `deadline` / `startDate`: YYYYYYYYYYYMMMMDDDDD0000000
# Verified against things.py (thingsapi/things.py) convert_thingsdate_*.
Y_MASK, M_MASK, D_MASK = 0b111111111110000000000000000, 0b1111000000000000, 0b111110000000

# User preference: projects filed under these areas -- or whose own name
# reads as a generic idea-dump backlog or an evergreen recurring bucket -- are
# personal/relationship tracking, "someday maybe" piles, or Weekly/Monthly/
# Yearly-style buckets that never reach "done", not "get it done" work, so
# they're excluded from every part of the report (completed, canceled,
# backlog, projects).
def is_excluded_area(area_title):
    if not area_title:
        return False
    lowered = area_title.lower()
    return any(keyword in lowered for keyword in ("people", "girlz", "backlog", "recurring"))


def is_excluded_project_title(project_title):
    if not project_title:
        return False
    lowered = project_title.lower()
    return any(keyword in lowered for keyword in ("backlog", "recurring"))


def get_excluded_project_uuids(conn):
    """Projects to drop from every part of the report: trashed projects (their
    to-dos keep trashed=0 even after the parent project is trashed, so they'd
    otherwise leak into completed/canceled/backlog counts as orphans), plus
    the user's standing area/name exclusions."""
    rows = conn.execute(
        """
        SELECT p.uuid, p.title, p.trashed, a.title AS area_title FROM TMTask p
        LEFT JOIN TMArea a ON p.area = a.uuid
        WHERE p.type = ?
        """,
        (TYPE_PROJECT,),
    ).fetchall()
    return {
        r[0]
        for r in rows
        if r[2] == 1 or is_excluded_area(r[3]) or is_excluded_project_title(r[1])
    }


def project_exclusion_clause(excluded_uuids, column):
    """Returns a SQL fragment + params excluding rows whose `column` (a project
    uuid) is in excluded_uuids. Safe to AND into any WHERE clause."""
    if not excluded_uuids:
        return "1=1", []
    placeholders = ",".join(["?"] * len(excluded_uuids))
    return f"({column} IS NULL OR {column} NOT IN ({placeholders}))", list(excluded_uuids)


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


def stage_db_copy(source_path, workdir):
    """Copy the db plus its -wal/-shm sidecars so uncommitted WAL data is included,
    and so we never touch the live file Things has open."""
    dest = os.path.join(workdir, "main.sqlite")
    shutil.copy2(source_path, dest)
    for suffix in ("-wal", "-shm"):
        side = source_path + suffix
        if os.path.exists(side):
            shutil.copy2(side, dest + suffix)
    return dest


def resolve_db_path(explicit_path):
    if explicit_path:
        return explicit_path
    candidates = find_db_candidates()
    if not candidates:
        sys.exit(
            "Could not find a Things database under ~/Library/Group Containers. "
            "Pass --db /path/to/main.sqlite explicitly, or check that Things is installed."
        )
    # Prefer the most recently modified if multiple installs are found.
    return max(candidates, key=os.path.getmtime)


def connect(db_path):
    workdir = tempfile.mkdtemp(prefix="things_query_")
    staged = stage_db_copy(db_path, workdir)
    conn = sqlite3.connect(staged)
    conn.row_factory = sqlite3.Row
    return conn


def query_stopped(conn, status, period_start, period_end, excluded_project_uuids):
    """Shared shape for anything with a stopDate in range: completed or canceled."""
    exclusion_sql, exclusion_params = project_exclusion_clause(excluded_project_uuids, "t.project")
    rows = conn.execute(
        """
        SELECT t.uuid, t.title, t.stopDate,
               proj.title AS project_title
        FROM TMTask t
        LEFT JOIN TMTask proj ON t.project = proj.uuid
        WHERE t.type = ? AND t.status = ? AND t.trashed = 0 AND t.{not_template}
          AND t.stopDate >= ? AND t.stopDate < ?
          AND {exclusion}
        ORDER BY t.stopDate DESC
        """.format(not_template=NOT_A_TEMPLATE, exclusion=exclusion_sql),
        (TYPE_TODO, status, period_start.timestamp(), period_end.timestamp(), *exclusion_params),
    ).fetchall()

    # Areas aren't tracked as their own reporting dimension -- they never
    # "complete", so grouping by area would imply a target that doesn't exist.
    # Projects are the completable unit; group by project only.
    by_project = {}
    for r in rows:
        proj = r["project_title"] or "(no project)"
        by_project[proj] = by_project.get(proj, 0) + 1

    tag_rows = conn.execute(
        """
        SELECT tg.title, COUNT(*) FROM TMTask t
        JOIN TMTaskTag tt ON tt.tasks = t.uuid
        JOIN TMTag tg ON tt.tags = tg.uuid
        WHERE t.type = ? AND t.status = ? AND t.trashed = 0 AND t.{not_template}
          AND t.stopDate >= ? AND t.stopDate < ?
          AND {exclusion}
        GROUP BY tg.title
        """.format(not_template=NOT_A_TEMPLATE, exclusion=exclusion_sql),
        (TYPE_TODO, status, period_start.timestamp(), period_end.timestamp(), *exclusion_params),
    ).fetchall()

    return {
        "total": len(rows),
        "by_project": sorted(
            [{"title": k, "count": v} for k, v in by_project.items()],
            key=lambda x: -x["count"],
        ),
        # A task can carry multiple tags, so these counts don't sum to `total`.
        "by_tag": sorted(
            [{"tag": r[0], "count": r[1]} for r in tag_rows], key=lambda x: -x["count"]
        ),
        "titles": [r["title"] for r in rows],
    }


def query_backlog(conn, today, excluded_project_uuids):
    exclusion_sql, exclusion_params = project_exclusion_clause(excluded_project_uuids, "t.project")
    rows = conn.execute(
        """
        SELECT t.uuid, t.title, t.start, t.deadline, t.creationDate,
               proj.title AS project_title, area.title AS area_title
        FROM TMTask t
        LEFT JOIN TMTask proj ON t.project = proj.uuid
        LEFT JOIN TMArea area ON COALESCE(t.area, proj.area) = area.uuid
        WHERE t.type = ? AND t.status = ? AND t.trashed = 0 AND t.{not_template}
          AND {exclusion}
        """.format(not_template=NOT_A_TEMPLATE, exclusion=exclusion_sql),
        (TYPE_TODO, STATUS_OPEN, *exclusion_params),
    ).fetchall()

    inbox = anytime = someday = 0
    overdue, due_soon = [], []
    stale = []
    today_iso = today.date().isoformat()
    soon_cutoff = (today + timedelta(days=7)).date().isoformat()
    stale_cutoff = today - timedelta(days=90)

    for r in rows:
        if r["start"] == START_INBOX:
            inbox += 1
        elif r["start"] == START_ANYTIME:
            anytime += 1
        elif r["start"] == START_SOMEDAY:
            someday += 1

        deadline_iso = decode_thingsdate(r["deadline"])
        if deadline_iso:
            entry = {
                "title": r["title"],
                "deadline": deadline_iso,
                "project": r["project_title"],
            }
            if deadline_iso < today_iso:
                overdue.append(entry)
            elif deadline_iso <= soon_cutoff:
                due_soon.append(entry)

        if r["creationDate"] and datetime.fromtimestamp(
            r["creationDate"], tz=timezone.utc
        ) < stale_cutoff.replace(tzinfo=timezone.utc):
            stale.append(
                {
                    "title": r["title"],
                    "created": datetime.fromtimestamp(
                        r["creationDate"], tz=timezone.utc
                    ).date().isoformat(),
                    "project": r["project_title"],
                    "area": r["area_title"],
                }
            )

    stale.sort(key=lambda x: x["created"])
    overdue.sort(key=lambda x: x["deadline"])
    due_soon.sort(key=lambda x: x["deadline"])

    tag_rows = conn.execute(
        """
        SELECT tg.title, COUNT(*) FROM TMTask t
        JOIN TMTaskTag tt ON tt.tasks = t.uuid
        JOIN TMTag tg ON tt.tags = tg.uuid
        WHERE t.type = ? AND t.status = ? AND t.trashed = 0 AND t.{not_template}
          AND {exclusion}
        GROUP BY tg.title
        """.format(not_template=NOT_A_TEMPLATE, exclusion=exclusion_sql),
        (TYPE_TODO, STATUS_OPEN, *exclusion_params),
    ).fetchall()

    return {
        "total_open": len(rows),
        "inbox": inbox,
        "anytime": anytime,
        "someday": someday,
        "overdue": overdue,
        "due_soon": due_soon,
        "stale_oldest_20": stale[:20],
        "stale_total": len(stale),
        # A task can carry multiple tags, so these counts don't sum to total_open.
        # Tags like "Waiting" are worth watching here -- a growing pile means
        # things stuck on someone else, not on you.
        "by_tag": sorted(
            [{"tag": r[0], "count": r[1]} for r in tag_rows], key=lambda x: -x["count"]
        ),
    }


def query_projects(conn):
    projects = conn.execute(
        """
        SELECT p.uuid, p.title, p.status, p.trashed, area.title AS area_title
        FROM TMTask p
        LEFT JOIN TMArea area ON p.area = area.uuid
        WHERE p.type = ? AND p.trashed = 0
        """,
        (TYPE_PROJECT,),
    ).fetchall()

    result = []
    for p in projects:
        if is_excluded_area(p["area_title"]) or is_excluded_project_title(p["title"]):
            continue
        counts = conn.execute(
            """
            SELECT status, COUNT(*) FROM TMTask
            WHERE type = ? AND trashed = 0 AND project = ? AND {not_template}
            GROUP BY status
            """.format(not_template=NOT_A_TEMPLATE),
            (TYPE_TODO, p["uuid"]),
        ).fetchall()
        tally = {row[0]: row[1] for row in counts}
        open_n = tally.get(STATUS_OPEN, 0)
        done_n = tally.get(STATUS_COMPLETE, 0)
        canceled_n = tally.get(STATUS_CANCELED, 0)
        total = open_n + done_n  # canceled excluded from completion-% denominator
        result.append(
            {
                "title": p["title"],
                "area": p["area_title"],
                "active": p["status"] == STATUS_OPEN,
                "open_count": open_n,
                "completed_count": done_n,
                "canceled_count": canceled_n,
                "pct_done": round(100 * done_n / total, 1) if total else None,
            }
        )
    return sorted(result, key=lambda x: -x["open_count"])


def repeatedly_canceled(canceled_titles, min_count=3, limit=15):
    """A recurring to-do's template spawns a fresh instance each cycle; if the
    *same* title gets canceled repeatedly within one period, that's not several
    independent decisions not to do something -- it's one repeating prompt the
    user keeps waving off. Surface these as candidates to just turn off,
    separate from one-off cancellations."""
    from collections import Counter

    counts = Counter(canceled_titles)
    return sorted(
        [{"title": t, "count": n} for t, n in counts.items() if n >= min_count],
        key=lambda x: -x["count"],
    )[:limit]


def worth_closing_out(projects, max_open=10, min_pct=80, limit=15):
    """Active projects that are mostly done and have only a few items left --
    these are worth pushing over the finish line rather than left to linger."""
    candidates = [
        p
        for p in projects
        if p["active"] and p["pct_done"] is not None and p["pct_done"] >= min_pct
        and 0 < p["open_count"] <= max_open
    ]
    return sorted(candidates, key=lambda x: -x["pct_done"])[:limit]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30, help="Length of the report period.")
    parser.add_argument("--db", default=None, help="Explicit path to main.sqlite.")
    parser.add_argument(
        "--end", default=None, help="ISO date the period ends on (default: today)."
    )
    args = parser.parse_args()

    end = (
        datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
        if args.end
        else datetime.now(timezone.utc)
    )
    start = end - timedelta(days=args.days)
    prior_start = start - timedelta(days=args.days)

    db_path = resolve_db_path(args.db)
    conn = connect(db_path)

    excluded_project_uuids = get_excluded_project_uuids(conn)

    completed = query_stopped(conn, STATUS_COMPLETE, start, end, excluded_project_uuids)
    completed_prior = query_stopped(conn, STATUS_COMPLETE, prior_start, start, excluded_project_uuids)
    canceled = query_stopped(conn, STATUS_CANCELED, start, end, excluded_project_uuids)
    canceled_prior = query_stopped(conn, STATUS_CANCELED, prior_start, start, excluded_project_uuids)
    canceled["repeatedly_canceled"] = repeatedly_canceled(canceled["titles"])
    projects = query_projects(conn)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_db": db_path,
        "period": {"start": start.date().isoformat(), "end": end.date().isoformat(), "days": args.days},
        "completed": completed,
        "completed_prior_period": {"total": completed_prior["total"]},
        "canceled": canceled,
        "canceled_prior_period": {"total": canceled_prior["total"]},
        "backlog": query_backlog(conn, end, excluded_project_uuids),
        "projects": projects,
        "projects_worth_closing_out": worth_closing_out(projects),
    }
    conn.close()
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
