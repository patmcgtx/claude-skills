#!/usr/bin/env python3
"""
Pulls every item in Things' "Today" list and sorts it into Daily Flight Plan
template sections by tag, subgrouped by project/area.

What "Today" means here: open to-dos with start=1 (the Anytime bucket) whose
startDate decodes to today or earlier. This deliberately excludes to-dos that
carry a leftover startDate but sit in Someday (start=2) -- checked against
this user's real data, a chunk of those have startDate values years in the
past (2019, 2021...), clearly stale remnants from before the to-do was
demoted to Someday, not things Things' own Today perspective would ever
show. Filtering to start=1 only matches what the app actually displays.

Three more orphan traps, same root cause as the trashed-project issue
documented in the things-report skill (trashed=0 doesn't cascade to children
in this schema):
  - A recurring to-do's generated instances point back at their template row
    via rt1_repeatingTemplate. If the user deletes/trashes the recurring
    template itself, already-generated instance rows can be left behind with
    trashed=0 and status=0 forever -- confirmed on this user's real data: a
    "Take Vitamin B12" template trashed back in ~2019 left 15 such ghost
    instances sitting open, 3 of which had startDate <= today and would
    otherwise show up as real Today items every single day indefinitely.
    Excluded via `tmpl.trashed = 0`.
  - A to-do's project can itself be trashed (moved to the Trash in Things)
    while the to-do's own `trashed` column stays 0 -- confirmed on this
    user's real data: the project "🎹Get my piano tuned" is in the Trash,
    but its child to-do "Set up appt" was still showing up as a live Today
    item. Excluded via `proj.trashed = 0`. This is the exact same bug
    things-report's schema notes describe for its own report queries; it
    just hadn't been hit here yet when this script was first written.
  - Similarly, a to-do's own status can stay open even after its parent
    project is marked completed or canceled -- excluded via `proj.status = 0`
    (no matches on this user's data yet, but the shape of the bug is
    identical, so it's excluded defensively rather than waiting to hit it).

Section mapping, in priority order (an item can carry tags matching more
than one rule -- first match wins, so the order here is the actual policy,
not just an implementation detail):
  1. tag "🚨Important"                        -> Time-sensitive
  2. tag Molly / Claire / Mom / Social         -> People & phone
  3. tag Learning                              -> Professional Growth
  4. tag name matches a template heading       -> that heading (e.g. "Laptop" -> Laptop)
  5. nothing matched                           -> Other

Within a section, items are subgrouped by their project title (or area
title if the to-do has no project) so a section with a lot going on doesn't
read as a flat wall of checkboxes. Items with neither a project nor an area
are listed first, ungrouped.

Usage:
    python3 things_today.py [--db /path/to/main.sqlite] [--end YYYY-MM-DD]

Prints one JSON object: {"section name": [{"title", "group"}, ...], ...}
-- only sections with at least one item are present. "group" is null for
ungrouped items.
"""

import argparse
import glob
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone

TYPE_TODO = 0
STATUS_OPEN = 0
START_ANYTIME = 1

NOT_A_TEMPLATE = "rt1_recurrenceRule IS NULL"

Y_MASK, M_MASK, D_MASK = 0b111111111110000000000000000, 0b1111000000000000, 0b111110000000

# The full set of Daily Flight Plan headings a tag can generally match by
# name (see references/daily_flight_plan_template.md). Compared against tag
# names with emoji/punctuation stripped, so "Physical" matches "Physical 💪🏻".
TEMPLATE_SECTIONS = [
    "Time-sensitive", "Agenda", "Basics", "Inboxes", "People & phone", "Work",
    "Professional Growth", "Physical", "Laptop", "Home",
]

PEOPLE_TAGS = {"molly", "claire", "mom", "social"}


def normalize(s):
    """Lowercase, strip emoji/punctuation, collapse whitespace -- so tag
    names and heading text compare on words alone."""
    s = re.sub(r"[^\w\s&]", "", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip().lower()


NORMALIZED_SECTIONS = {normalize(s): s for s in TEMPLATE_SECTIONS}


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
    workdir = tempfile.mkdtemp(prefix="things_today_")
    staged = stage_db_copy(db_path, workdir)
    conn = sqlite3.connect(staged)
    conn.row_factory = sqlite3.Row
    return conn


def target_section(tags):
    tagset = set(tags)
    if "🚨Important" in tagset:
        return "Time-sensitive"
    if {t for t in tagset if t.lower() in PEOPLE_TAGS}:
        return "People & phone"
    if "Learning" in tagset:
        return "Professional Growth"
    for t in tags:
        section = NORMALIZED_SECTIONS.get(normalize(t))
        if section:
            return section
    return "Other"


def query_today_items(conn, end_date):
    rows = conn.execute(
        """
        SELECT t.uuid, t.title, t.startDate,
               proj.title AS project_title, area.title AS area_title,
               proj.status AS project_status, tmpl.trashed AS template_trashed
        FROM TMTask t
        LEFT JOIN TMTask proj ON t.project = proj.uuid
        LEFT JOIN TMArea area ON COALESCE(t.area, proj.area) = area.uuid
        LEFT JOIN TMTask tmpl ON t.rt1_repeatingTemplate = tmpl.uuid
        WHERE t.type = ? AND t.status = ? AND t.trashed = 0 AND t.{not_template}
          AND t.start = ? AND t.startDate IS NOT NULL
          AND (t.rt1_repeatingTemplate IS NULL OR tmpl.trashed = 0)
          AND (proj.uuid IS NULL OR (proj.status = 0 AND proj.trashed = 0))
        """.format(not_template=NOT_A_TEMPLATE),
        (TYPE_TODO, STATUS_OPEN, START_ANYTIME),
    ).fetchall()

    end_iso = end_date.date().isoformat()
    sections = defaultdict(lambda: {"__ungrouped__": []})

    for r in rows:
        deadline_iso = decode_thingsdate(r["startDate"])
        if deadline_iso is None or deadline_iso > end_iso:
            continue
        tags = [
            row[0]
            for row in conn.execute(
                "SELECT tg.title FROM TMTaskTag tt JOIN TMTag tg ON tt.tags = tg.uuid WHERE tt.tasks = ?",
                (r["uuid"],),
            ).fetchall()
        ]
        section = target_section(tags)
        group = r["project_title"] or r["area_title"]
        bucket = sections[section]
        if group:
            bucket.setdefault(group, []).append(r["title"])
        else:
            bucket["__ungrouped__"].append(r["title"])

    out = OrderedDict()
    for section in TEMPLATE_SECTIONS + ["Other"]:
        if section not in sections:
            continue
        bucket = sections[section]
        items = [{"title": t, "group": None} for t in bucket["__ungrouped__"]]
        for group in sorted(k for k in bucket if k != "__ungrouped__"):
            for t in bucket[group]:
                items.append({"title": t, "group": group})
        if items:
            out[section] = items
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
    result = query_today_items(conn, end)
    conn.close()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
