---
name: daily-flight-plan
description: Builds today's "🚀 Daily Flight Plan" journal entry by combining today's macOS Calendar agenda and Things.app deadline items, then creates it in Day One via the dayone CLI. Use whenever the user asks to plan their day, build/create/write their daily plan or flight plan, wants their agenda and to-dos put into Day One, or asks to sync Calendar/Things into their journal. Trigger even if they just say "do my daily plan" or "set up today's flight plan" without naming Calendar, Things, or Day One explicitly.
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
   edits may only exist in the `-wal` sidecar — `scripts/things_deadlines.py`
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

Split the results by `calendar`: events where `calendar == "Work"` feed the
template's Work work section; everything else feeds Agenda. This split is
specific to this user's setup (their work calendar is literally named
"Work" in Calendar.app) — if a future user's calendar is named differently,
ask rather than assume.

## Step 3: Pull today's deadline-bearing Things to-dos

```bash
python3 scripts/things_deadlines.py   # --end YYYY-MM-DD for a different day
```

Prints a JSON array of `{title, deadline, project, overdue}`, sorted
soonest-first. This is deliberately narrower than "everything in Things'
Today list" — only to-dos with a real deadline set (today or earlier) go
into the plan's Time-sensitive section. A to-do merely *scheduled* for today
without a deadline doesn't appear here (that's an intentional choice the
user made, not a bug to fix).

## Step 4: Compose the entry text

Read `references/daily_flight_plan_template.md` — it has the exact template
text (confirmed headings vs. bold, checkboxes vs. plain bullets against a
real entry) with three placeholders (`{{TIME_SENSITIVE}}`, `{{AGENDA}}`,
`{{WORK_AGENDA}}`) and the formatting rules for each. Fill those three in
from steps 2-3; leave every other line exactly as written in the
reference — those sections are the user's own daily-habit checklist, not
data-driven, and shouldn't be touched.

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

After creating it, tell the user it's done and briefly summarize what went
into Agenda/Work work/Time-sensitive (counts are enough — "3 meetings, 2 work
events, 1 deadline item" — no need to restate every line back to them, they
can just open Day One).
