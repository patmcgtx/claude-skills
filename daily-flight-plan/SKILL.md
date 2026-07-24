---
name: daily-flight-plan
description: Builds today's "🚀 Daily Flight Plan" journal entry by combining today's macOS Calendar agenda and every item in Things.app's Today list (sorted into sections by tag), then creates it in Day One via the dayone CLI. Use whenever the user asks to plan their day, build/create/write their daily plan or flight plan, wants their agenda and to-dos put into Day One, or asks to sync Calendar/Things into their journal. Trigger even if they just say "do my daily plan" or "set up today's flight plan" without naming Calendar, Things, or Day One explicitly.
---

# Daily Flight Plan

Composes the user's personal Day One template — "🚀 Daily Flight Plan" — by
pulling live data from two other local apps, then creates the entry with
Day One's CLI. Three local data sources, one write, all on-disk/local —
no network APIs involved.

## Why this needs bundled scripts rather than ad-hoc queries

Each of the three apps involved has a sharp edge that isn't obvious until you
hit it:

1. **Calendar.app via AppleScript is a dead end.** Filtering events with a
   `whose` clause (the obvious approach) can hang indefinitely rather than
   erroring, especially once more than a couple of calendars are involved.
   `scripts/calendar_agenda` uses EventKit instead (the same framework
   Calendar.app and Day One itself use) and returns in well under a second.
2. **Things' SQLite database is locked while Things is running**, and recent
   edits may only exist in the `-wal` sidecar — `scripts/things_today.py`
   stages a safe copy before querying, same pattern as the `things-report`
   skill.
3. **The `dayone` CLI can only create entries, never edit or search them.**
   Running this skill twice in a day would otherwise silently produce two
   "🚀 Daily Flight Plan" entries with no way to fix it from the CLI —
   `scripts/check_existing_plan.py` checks for that first.

## Step 1: Check for an existing plan today

```bash
python3 scripts/check_existing_plan.py
```

Prints `{"exists": bool, "matches": [{"title_line", "created", "journal"}]}`.
If `exists` is true, **stop and ask the user** whether to still create
another entry — show them the existing match(es) (created time is enough,
don't need to say anything else about their content). Don't silently skip
and don't silently duplicate; this is the one step in the whole skill that
needs a judgment call from the user rather than a script.

Pass `--date YYYY-MM-DD` if the user asks for a day other than today.

## Step 2: Pull today's Calendar agenda

```bash
scripts/calendar_agenda --date YYYY-MM-DD   # defaults to today if omitted
```

Prints a JSON array of `{title, start, end, isAllDay, calendar}` (ISO 8601
timestamps, local time zone), sorted by start time.

**If this fails** with "Calendar access not granted": this is a one-time
setup step only the user can do (compiled binaries don't get the normal
permission popup). Tell them to add
`~/.claude/skills/daily-flight-plan/scripts/calendar_agenda` under
**System Settings → Privacy & Security → Calendars** via the "+" button,
then try again. Don't try to work around it (no fallback to AppleScript —
see above for why).

All events feed the Agenda section together, regardless of which calendar
they're on — including the `Work` calendar. The template's Work section is
untouched scaffold (its own fixed checklist items only); don't split events
out to it.

## Step 3: Pull and sort today's Things Today list

```bash
python3 scripts/things_today.py   # --end YYYY-MM-DD for a different day
```

Prints one JSON object keyed by template section name — every item
currently in Things' Today list (open to-dos scheduled for today or
earlier), already sorted into the section its tags map to and subgrouped by
project/area. This is **all** of today's Things items, not a deadline-only
subset — see the script's docstring for the exact tag → section priority
order (🚨Important → Time-sensitive; Molly/Claire/Mom/Social → People &
phone; Learning → Professional Growth; tag name matching a heading → that
heading; anything left over → Other). Don't recompute this mapping by hand
from the raw to-do list — the priority order and project-subgrouping logic
are intricate enough that they live in the script specifically so they're
applied consistently every run.

## Step 4: Compose the entry text

Read `references/daily_flight_plan_template.md` — it has the exact template
text (confirmed headings vs. bold, checkboxes vs. plain bullets against a
real entry) with the placeholders and formatting rules for each, including
how to render `things_today.py`'s grouped output as sub-headings (area
groups as `## `, project groups as `### `). Fill those in from steps 2-3;
leave Basics and Inboxes exactly as written in the reference — those are the
user's own daily-habit checklist, not data-driven, and shouldn't be touched.

One placeholder, `{{DAY_SUMMARY}}`, is prose rather than a checklist — a
short 1-3 sentence read of the day based only on Time-sensitive and Agenda,
written fresh each time rather than templated. See the reference file for
tone/length examples; this is the one part of the entry that calls for
actual composition rather than mechanical formatting of script output.

Section order is fixed: **Time-sensitive, Agenda, Basics, Inboxes**, then
the rest, exactly as laid out in the reference file. Fill placeholders into
that template in place rather than generating sections separately and
concatenating them — that guarantees the order every time regardless of
which sections have data on a given day.

## Step 5: Create the entry

```bash
cat entry.md | "/Applications/Day One.app/Contents/MacOS/dayone" -j "📆Daily" new
```

Write the composed text to a file first and pipe it in via stdin (the CLI's
default input mode when no text argument is given) rather than passing it as
a command-line argument — the entry contains quotes, backticks, and markdown
links, which are painful and error-prone to escape correctly inside a shell
argument. Notes:

- The journal is always **`📆Daily`** — that's where the user's existing
  Daily Flight Plan entries live; don't ask each time.
- Don't pass `--date`/`--isoDate` unless the user is explicitly backfilling a
  past day — omitting it defaults to now, which is correct for "plan my
  day" run in the morning.
- The `dayone` binary isn't on `PATH` by default; use the full path above (or
  `dayone2` if the user has separately run Day One's "Install Command Line
  Tools" and it resolves on `PATH`).

After creating it, tell the user it's done and briefly summarize counts per
section that actually got data (e.g. "5 calendar events, 2 time-sensitive,
6 work items, 3 in Other" — skip sections that ended up empty) — no need to
restate every line back to them, they can just open Day One.
