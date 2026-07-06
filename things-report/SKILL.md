---
name: things-report
description: Analyzes the user's Things.app (culturedcode.com to-do manager) SQLite database to report what they've completed and what's left open — completed-work summaries, backlog health, velocity trends, and per-project breakdowns. Use this whenever the user asks for a review of their to-dos, tasks, or projects in Things, mentions "Things app", asks what they've gotten done recently, wants a weekly/monthly review, asks about their backlog or open projects, or wants a productivity/GTD-style report. Trigger even if they don't say "Things" explicitly but describe wanting a review of their task list or personal projects and mention things like Inbox, Someday, Areas, or Anytime.
---

# Things.app report

Things stores everything — to-dos, projects, areas, tags — in a local SQLite
database. This skill queries it directly to build a report on what got done
and what's still outstanding. No API or export step is needed; the data is
already sitting on disk.

## Why go through the bundled script rather than writing SQL from scratch

Two things about this database bite people who query it fresh each time:

1. **It's usually locked.** Things holds `main.sqlite` open while running, and
   recent edits may only exist in the `-wal` sidecar file. Querying the live
   path directly can fail or silently miss recent changes.
2. **Recurring-task templates masquerade as real open to-dos.** Every repeating
   to-do has a template row that looks like a normal open item forever, parked
   in the Someday list. Counting it inflates the backlog and can produce
   nonsense dates (its `deadline` field isn't a real date, just a scheduling
   offset).
3. **Trashing a project doesn't trash its to-dos.** A to-do's own `trashed`
   flag stays `0` even after its parent project is trashed, so filtering only
   on `t.trashed = 0` lets these orphans leak into completed/canceled/backlog
   counts as if they were still live. The project itself correctly disappears
   from the `projects` list (that query does filter on the project's own
   `trashed`), which makes the orphaned children easy to miss on a read-through.

`scripts/things_query.py` handles all three: it stages a safe copy of the
database (main file + WAL + SHM) before opening it, filters out template rows
throughout, and folds trashed projects into the same exclusion set described
below. Use it rather than reimplementing these queries — it's easy to get
subtly wrong data by skipping any of these steps.

It also excludes, everywhere (completed, canceled, backlog, projects), any
project that is (a) trashed, (b) filed under an area with "people", "Girlz",
"backlog", or "recurring" in its name, or (c) has "backlog" or "recurring" in
its own project name — case-insensitive substring match for (b) and (c). (a)
is a data-integrity fix (see point 3 above); (b) and (c) are the user's
standing preference that personal/relationship-tracking, generic idea-dump
piles, and evergreen recurring buckets (e.g. an area or project literally
named "Recurring & long term", or a "Weekly"/"Monthly"/"Yearly" bucket living
in one) aren't "get it done" work and shouldn't clutter a productivity
report — they never reach "done" by design, so counting them as backlog or
open-project noise is misleading. (c) caught things like "IG story Backlog"
and "Apps to try backlog" that lived in otherwise-normal areas and slipped
through the area-only rule.
This is a hardcoded exclusion (`is_excluded_area` / `is_excluded_project_title`
/ `get_excluded_project_uuids` in the script), not a per-run flag — if the
user ever wants a report that includes them, or wants to exclude a different
area, edit that function rather
than trying to filter the JSON output after the fact.

## Running it

```bash
python3 scripts/things_query.py --days 30
```

- `--days N` — length of the report period, ending today. **Default to 30**
  unless the user asks for a different window (a week, a specific date range,
  "since January", etc.). If they give a custom range, pass `--end YYYY-MM-DD`
  and `--days` to bound it, or just compute the two dates and query directly.
- `--db /path/to/main.sqlite` — only needed if auto-detection fails (multiple
  Things installs, or a non-standard location). The script searches
  `~/Library/Group Containers/*.com.culturedcode.ThingsMac/` automatically.

It prints one JSON object to stdout with everything needed for the report:

- `completed` — total count, breakdown by project and **tag** (`by_tag`), and
  the list of titles, for the requested period. A task can carry multiple
  tags, so `by_tag` counts don't sum to `total` — that's expected, not a bug.
  There's deliberately no area breakdown: areas never reach "done," so
  reporting on them as if they were a completable unit alongside projects
  would be misleading. Projects are the unit that gets reported on; area only
  shows up as a label on a project (see `projects` below), not its own
  dimension.
- `completed_prior_period.total` — same count for the immediately preceding
  period of equal length, for a velocity comparison.
- `canceled` — same shape as `completed` (total, by_project, by_tag, titles),
  for to-dos marked canceled rather than done. Things distinguishes "I did
  this" from "I decided not to" — track it as its own metric alongside
  completed, not folded into "done" and not just a footnote. A high
  cancel-to-complete ratio in one project/tag is worth calling out (it can
  mean overcommitment or a stale project worth reviewing), and each project's
  `canceled_count` in the `projects` list supports that per-project.
  `canceled.repeatedly_canceled` is precomputed: titles canceled 3+ times
  within the period, sorted by count descending. A recurring to-do's template
  spawns a fresh instance each cycle, so the same title getting canceled
  repeatedly isn't several independent "decided not to do this" calls — it's
  one repeating prompt being waved off every time it fires. Always surface
  this list (when non-empty) as "consider turning these off" candidates,
  distinct from ordinary one-off cancellations.
- `canceled_prior_period.total` — same comparison as completed, for trend.
- `backlog` — everything currently open: counts by list (`inbox`/`anytime`/
  `someday`), `overdue` and `due_soon` (items with real deadlines, next 7
  days), `stale_oldest_20` (open items untouched for 90+ days, oldest first)
  plus `stale_total`, and `by_tag` (open items per tag — watch for a tag like
  "Waiting" piling up, since that means things stuck on someone else, not on
  the user).
- `projects` — every non-trashed project with its area, open/completed/
  canceled counts, and `pct_done` (completed ÷ (completed + open), canceled
  excluded from the denominator since abandoning items shouldn't count against
  completion rate).
- `projects_worth_closing_out` — active projects that are ≥80% done with 10 or
  fewer items left, already sorted by `pct_done` descending. This is
  precomputed rather than left to filter ad hoc from `projects`, so use it
  directly for the "worth closing out" callout instead of re-deriving it.

Read `references/schema.md` if the user asks for something the script doesn't
cover (e.g. filtering to one specific area or tag in isolation) — it has the
full field reference and the deadline-decoding formula, so you can write a
one-off query instead of extending the script.

## Building the report

Turn the JSON into a markdown report in chat (don't write it to a file unless
asked). Use this shape, adapting emphasis to what the user actually asked
about — if they only asked "what have I finished," don't force the backlog
and project sections in at full length, but a reasonable default report
covers all five:

```markdown
# Things Review: {period.start} to {period.end}

## Completed
{total} to-dos completed ({+/- N vs. the prior {days}-day period}).
Top projects by volume. A few notable or representative items —
don't just dump the full title list, pull out ones worth calling out.
Mention the top tag or two from `by_tag` if a particular kind of work
(a person, a context like "Laptop" vs "Out & about") dominated the period.

## Canceled
{total} to-dos canceled ({+/- N vs. the prior period}) — these are things you
decided not to do, distinct from "done." Top projects by volume, same
as above. If a project or tag shows up heavily here (especially
relative to its completed count — compare the two `by_tag`/`by_project`
lists), flag it — it can mean overcommitment or a project worth
reconsidering rather than continuing to carry.

If `canceled.repeatedly_canceled` is non-empty, call it out explicitly as its
own callout (e.g. "Repeated reminders worth dropping"): list each title with
its count. These are recurring to-dos that fire and get dismissed almost
every cycle — frame it as "this keeps getting created and waved off, consider
turning the recurrence off" rather than as a productivity failure.

## Backlog health
{total_open} open items — {inbox} in Inbox, {anytime} in Anytime, {someday} in
Someday. Call out anything that looks like a problem: a big Inbox (should be
near zero — it means unprocessed items), a lot of `stale_oldest_20` entries
(things that have sat untouched for 90+ days — are they still relevant?),
`overdue` items if any exist, or a tag like "Waiting" building up in
`backlog.by_tag` (items stuck on someone else rather than on the user).

## Velocity
Completed and canceled, each vs. their prior period — trending up, flat, or
down, and by how much. One or two sentences, not a chart, unless the user
wants a longer history.

## Projects
The handful of projects with the most open items, or the ones closest to
done, depending what's more useful. Don't list all of them if there are
dozens — surface what's actionable: projects that have been accumulating
open items without progress belong here.

### Worth closing out
List `projects_worth_closing_out` directly (already filtered and sorted) —
these are the projects sitting at 80%+ done with only a handful of items
left. Frame it as a nudge: finishing these clears real backlog for very
little remaining work, unlike starting something new.
```

Ground every number in the JSON — don't estimate or round in ways that misrepresent
it. If `backlog.overdue` and `backlog.due_soon` are both empty, say plainly that
no open items currently have deadlines set, rather than skipping the section
silently or implying there's nothing to worry about.

## Notes on interpretation

- A large Someday count isn't inherently bad (it's an intentional "not now"
  pile), but a large **Inbox** count means unprocessed items — that's the one
  worth flagging.
- `stale_oldest_20` items aren't necessarily neglected — some are genuinely
  low-priority somedays. Frame it as "worth a look," not as a failure.
- If `projects` includes ones with `open_count: 0, completed_count: 0` (a
  project with no to-dos in it, maybe just notes or a heading structure),
  it's fine to leave these out of the report entirely.
