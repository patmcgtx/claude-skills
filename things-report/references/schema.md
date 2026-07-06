# Things.app SQLite schema notes

Reference for writing custom queries beyond what `scripts/things_query.py` covers.
Verified by hand against a real database and cross-checked against the
[things.py](https://github.com/thingsapi/things.py) library's decode logic.

## Locating the database

Things Mac stores its data under a Group Container, keyed by a per-install hash
directory (e.g. `ThingsData-K9KLJ`) that varies by machine:

```
~/Library/Group Containers/*.com.culturedcode.ThingsMac/*/Things Database.thingsdatabase/main.sqlite
```

The live file has `-wal` and `-shm` sidecars. Things holds a lock on `main.sqlite`
whenever the app is running, and recent changes may live only in the WAL file, so
always copy all three files (`main.sqlite`, `main.sqlite-wal`, `main.sqlite-shm`)
to a scratch directory before opening — never query the live path directly.
`scripts/things_query.py` already does this.

There are also dated backups under `.../ThingsData-*/Backups/*.thingsdatabase/main.sqlite`
if you ever need historical state (e.g. "what did my backlog look like a month ago").

## Key tables

- `TMTask` — every to-do, project, and heading is a row here (see `type` below).
- `TMArea` — top-level areas (`uuid`, `title`).
- `TMTag` / `TMTaskTag` — tags and their join table.
- `TMChecklistItem` — sub-checklist items within a to-do.

## `TMTask` field semantics

| Field | Meaning |
|---|---|
| `type` | `0` = to-do, `1` = project, `2` = heading (a sub-group inside a project) |
| `status` | `0` = open/incomplete, `2` = canceled, `3` = completed |
| `trashed` | `1` if in Trash — exclude these from basically everything. **Trashing a project does not trash its children**: a to-do's `trashed` stays `0` even after its parent project is trashed, so `WHERE trashed = 0` alone lets these orphans leak into any count. Always also check the parent project's own `trashed` (`t.project IS NULL OR proj.trashed = 0`) when the query joins through a project. |
| `start` | Which list an open item lives in: `0` = Inbox, `1` = Anytime, `2` = Someday |
| `project` | uuid of the parent project (row in this same table, `type=1`), or NULL |
| `area` | uuid of the parent `TMArea`, or NULL (a task can hang directly off an area with no project) |
| `heading` | uuid of a parent heading row (`type=2`), or NULL |
| `creationDate`, `stopDate`, `userModificationDate` | Plain Unix epoch seconds (not Core Data reference dates) — use directly with `strftime`/`datetime.fromtimestamp`. `stopDate` is set when a task is completed or canceled. |
| `deadline`, `startDate` | **Bit-packed dates**, not epoch seconds — see decoding below. |
| `rt1_recurrenceRule` | Non-null **only** on the master template row of a repeating to-do. |
| `rt1_repeatingTemplate` | On generated instances, points back at the uuid of their template row. |

### Recurring-task templates are a trap

A repeating to-do's template is stored as its own ordinary-looking `TMTask` row —
same `type=0`, usually `status=0` (open) forever, often parked with `start=2`
(Someday). It is **not a real actionable item**; Things generates real dated
instances from it. Its `deadline`/`startDate` hold scheduling offsets, not real
calendar dates, which is why decoding them produces nonsense years like 1953.

**Always filter these out** when querying open or completed to-dos:

```sql
WHERE type = 0 AND rt1_recurrenceRule IS NULL
```

Forgetting this filter inflates backlog counts (in one real database, by ~15%)
and can produce garbage "overdue" dates.

### Decoding `deadline` / `startDate`

These integers pack a date as `YYYYYYYYYYYMMMMDDDDD0000000` in binary. In SQL:

```sql
printf('%d-%02d-%02d',
  (deadline & 134152192) >> 16,
  (deadline & 61440) >> 12,
  (deadline & 3968) >> 7)
```

In Python (see `scripts/things_query.py:decode_thingsdate`):

```python
Y_MASK, M_MASK, D_MASK = 0b111111111110000000000000000, 0b1111000000000000, 0b111110000000
year  = (value & Y_MASK) >> 16
month = (value & M_MASK) >> 12
day   = (value & D_MASK) >> 7
```

Sanity-check any decoded date — a template row slipping through the
`rt1_recurrenceRule` filter will decode to an implausible year.

## Useful joins

Get a task's area even when it's filed directly under a project (not directly
under the area):

```sql
LEFT JOIN TMTask proj ON t.project = proj.uuid
LEFT JOIN TMArea area ON COALESCE(t.area, proj.area) = area.uuid
```

Count a project's completion:

```sql
SELECT status, COUNT(*) FROM TMTask
WHERE type = 0 AND trashed = 0 AND project = ? AND rt1_recurrenceRule IS NULL
GROUP BY status
```
