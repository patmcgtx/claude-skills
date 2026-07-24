# "Daily Flight Plan" skill — design notes

A Claude Code skill that reads today's Calendar events and Things to-dos, and
writes a daily plan entry into Day One using the "🚀 Daily Flight Plan"
template.

## Decisions so far

- **Things scope**: "Today" list to-dos, plus anything still open with a past
  deadline/when-date (overdue) — so nothing slips silently. Follows the same
  safe-query pattern as the existing `things-report` skill (stages a copy of
  `main.sqlite` + WAL/SHM before reading, excludes recurring-task template
  rows).
- **Re-run behavior**: the Day One CLI can only *create* entries (no
  edit/upsert). If the skill is run twice in one day, it should check Day
  One's local database for an existing plan entry for today and confirm with
  the user before adding a duplicate, rather than silently creating a second
  entry or silently skipping.
- **Day One format**: written into the "🚀 Daily Flight Plan" template.
  - This is a custom template (not in Day One's built-in gallery — closest
    built-in is a generic "Daily Plan"), so its structure needs to come
    directly from the user (pasted) rather than assumed.
  - The `dayone` CLI has no `--template` flag, so the skill can't invoke the
    template by name — it needs to replicate the template's text structure
    itself and pass fully-formed markdown text to `dayone new`.
- **Calendar access**: AppleScript's `whose`-clause filtering against
  Calendar.app is a dead end — tested and it hung indefinitely rather than
  erroring, a known limitation of Calendar's AppleScript dictionary,
  especially with multiple/subscribed calendars.
  - The reliable approach is Apple's EventKit framework via a small compiled
    Swift helper binary (`swiftc` is available on this Mac). This is fast
    (near-instant) and is the same framework Day One itself uses internally
    for calendar features.
  - Because it's a standalone binary (not a signed app bundle with a usage
    description string), macOS won't show the normal permission popup.
    One-time manual step required: **System Settings → Privacy & Security →
    Calendars → "+"** → browse to the compiled helper binary and add it.
    Same workaround long used by tools like `icalBuddy`.
  - User confirmed: build the helper now, grant the permission later before
    first real use.

## Technical building blocks confirmed working

- **Things**: reuse the pattern from `~/.claude/skills/things-report/scripts/things_query.py`
  (stage DB copy, filter `rt1_recurrenceRule IS NULL`, exclude trashed/areas).
- **Day One CLI**: `/Applications/Day One.app/Contents/MacOS/dayone` (not on
  PATH by default). Relevant flags: `new` (reads stdin by default), `-j/--journal`,
  `-d/--date` or `--isoDate`, `-t/--tags`, `-s/--starred`. Markdown checkboxes
  (`- [ ]`) render as interactive checklists in the app.
- **Calendar**: EventKit via compiled Swift binary
  (`store.requestFullAccessToEvents` + `predicateForEvents(withStart:end:calendars:)`)
  — confirmed to run fast once permission is granted; confirmed the
  AppleScript alternative is unusably slow.

## Final decisions (confirmed with user)

- **Section mapping**: "Agenda" = today's Calendar events (personal
  calendars, time order). "Time-sensitive" = Things to-dos with a real
  deadline set that's today or overdue — a stricter subset than the whole
  Today list; to-dos scheduled for today without a deadline don't land
  anywhere in the entry (that's intentional, per the user).
- **Work calendar**: named exactly `Work` in the macOS Calendar app sidebar.
  It *is* visible to EventKit (not a separate inaccessible system) — its
  events should populate the "Work work" section specifically, separate
  from the personal-calendar "Agenda" section.
- **Everything else in the template** (Basics, Inboxes, Physical, People &
  phone, Laptop, Home, Professional Growth): reproduced verbatim/untouched
  each day — no data source, just scaffold.
- **Day One journal name**: confirmed as `📆Daily` (found via the
  duplicate-check script below — two real entries titled "🚀 Daily Flight
  Plan" already exist there from earlier today).

## Progress: skill built at ~/.claude/skills/daily-flight-plan/

- `scripts/calendar_agenda.swift` (+ compiled `calendar_agenda` binary) —
  EventKit-based, prints JSON events for a date. Compiles clean, fails with a
  clear message until Calendar access is granted (see below).
- `scripts/things_deadlines.py` — open Things to-dos with a deadline today or
  earlier, honors the "Exclude" tag convention from `things-report`. Tested
  against the real Things DB: runs fine (returned `[]`, no deadline items
  right now).
- `scripts/check_existing_plan.py` — checks Day One's real local DB
  (`~/Library/Group Containers/*.dayoneapp*/Data/Documents/DayOne.sqlite`)
  for an existing plan entry on a given date, without printing full entry
  text (only first line + timestamp + journal name, for duplicate
  detection). Tested against the real DB — works, found today's 2 existing
  entries.

## Remaining steps (not yet done)

1. **Grant Calendar permission** (user action, whenever ready): System
   Settings → Privacy & Security → Calendars → "+" → add
   `~/.claude/skills/daily-flight-plan/scripts/calendar_agenda` (the compiled
   binary, not the `.swift` source).
2. Write `references/daily_flight_plan_template.md` with the pasted template
   text as the literal scaffold to fill in.
3. Write `SKILL.md` tying the three scripts together: run
   `things_deadlines.py` + `calendar_agenda` (split Agenda vs. Work work by
   calendar name `Work`) + `check_existing_plan.py` (warn/confirm before
   duplicating), compose the filled-in template text, call
   `dayone new -j "📆Daily" -- ` with that text on stdin.
4. Test end-to-end once Calendar permission is granted (steps 1-3 are done
   or ready; this is the only remaining blocker).
