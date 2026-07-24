# Daily Flight Plan template

This is the user's actual Day One template, confirmed against a real entry's
raw markdown (the `dayone` CLI has no way to invoke a saved template by name,
so the skill reproduces this text directly). Confirmed formatting: `#`/`##`
are true Day One headings (not just bold text), and every bullet is a
checkbox (`- [ ] `, not a plain `-`).

Every section except Basics and Inboxes can receive data-driven content —
Agenda from Calendar, everything else from `things_today.py`'s tag-based
sort of the Things Today list (see that script's docstring for the mapping
rules and priority order). Basics and Inboxes are always reproduced exactly
as-is, untouched — pure daily-habit checklists with no data source.

**Section order is fixed and always: Time-sensitive, Agenda, Basics,
Inboxes, then everything else in the order shown below.** Fill each
section's content in place within this template rather than reassembling
the document from parts — that way the order can't drift no matter what
data is or isn't present on a given day.

```markdown
# 🚀 Daily Flight Plan
*What is today's purpose? Who do I want to be?*

{{DAY_SUMMARY}}

## Time-sensitive

{{TIME_SENSITIVE}}

## Agenda

{{AGENDA}}

## Basics

- [ ] Breakfast -
- [ ] Lunch -
- [ ] Dinner -
- [ ] Exercise -

## Inboxes

- [ ] Photos groomed
- [ ] ❗️Email zero inbox
- [ ] [YNAB](https://app.ynab.com) done
- [ ] ❗️Things zero inbox
- [ ] ❗️Snail mail done
- [ ]

## People & phone

{{PEOPLE_AND_PHONE}}

## Work

{{WORK}}
- [ ] Catch up work Reminders®
- [ ] Work email zero inbox

## Professional Growth

{{PROFESSIONAL_GROWTH}}
- [ ] Do [hackerrank](https://www.hackerrank.com/) or leetcode.com

## Physical 💪🏻

{{PHYSICAL}}
- [ ] Walk
- [ ] Sprint + box, balance ball, yoga, swim, bike
- [ ] ❗️Plantar fasciitis PT
- [ ] Or runner's yoga

## Laptop

{{LAPTOP}}

## Home

{{HOME}}

## Other

{{OTHER}}
```

`## Other` is a new section, not part of the user's original template — it
exists purely as the catch-all for Things Today items whose tags don't map
anywhere else (see `things_today.py`), so nothing from today's list silently
disappears. If it ends up empty most days, that's fine; leave it in rather
than only adding it conditionally, so the structure stays predictable.

## Filling the placeholders

### `{{DAY_SUMMARY}}`

Unlike every other placeholder, this one isn't a checklist — it's a short
plain-text paragraph (1-3 sentences, no heading, no bullets) giving a quick
read of the day at a glance, right under the "What is today's purpose?"
prompt. Base it only on the **Time-sensitive** items and the **Agenda**
(calendar) — don't summarize People & phone, Work, Laptop, Home, Other, or
any of the fixed scaffold sections; the point is a fast read of what's
urgent and what's scheduled, not a recap of the whole entry.

Write it fresh each day from that day's actual data rather than a fixed
template sentence — vary the phrasing naturally rather than always starting
the same way. Mention counts and specifics that matter (a tight morning, a
deadline item, a packed afternoon), not a mechanical restatement of every
line. If both are empty, a single honest sentence is fine (e.g. "Nothing
time-sensitive and nothing on the calendar today — a clear one."). Examples
of the right length/tone:

- "One time-sensitive item (plantar fasciitis PT) and a full day on the
  calendar — three work meetings between 9:30 and 3:30, plus picking up
  Claire's PC this evening."
- "Nothing time-sensitive today. Light calendar — just Andrew's birthday
  and the standup this morning."
- "Two deadline items to watch, and back-to-back meetings from 10 to 2 — a
  tighter day than usual."

Run `scripts/things_today.py` — it returns one JSON object keyed by section
name (`"Time-sensitive"`, `"People & phone"`, `"Work"`, `"Professional
Growth"`, `"Physical"`, `"Laptop"`, `"Home"`, `"Other"`), already sorted and
subgrouped by project/area, with ungrouped items first. Only sections with
at least one item are present in the output — a missing key means empty,
not an error.

For each of those eight section keys, render its items like this:

- Items with `"group": null` — plain `- [ ] {title}` lines, no label, listed
  first.
- Items with a non-null `"group"` — group consecutive items under a heading
  line for the group name, blank line before each new group. The heading
  level depends on `"group_kind"`: **`"area"` → `## {group}`** (Heading 2),
  **`"project"` → `### {group}`** (Heading 3) — matches Things' own
  hierarchy (an area can contain projects, so its label outranks one):
  ```
  ## {area group}
  - [ ] {title}

  ### {project group}
  - [ ] {title}
  ```
- If a section has **no** Things items and no fixed scaffold lines of its
  own (Time-sensitive, People & phone, Laptop, Home, Other), use a single
  line: `- [ ] Nothing here today` — otherwise the heading would be bare
  with nothing under it.
- Don't put a blank line between the section's own `## Heading` and the
  first group heading right under it (e.g. `## Time-sensitive` immediately
  followed by `### Some Project`, no gap) — only *between* groups, and
  between the last group and the next section. An extra blank line there is
  a easy copy-paste mistake that reads as a stray empty line in Day One.
- Work, Professional Growth, and Physical always have their own fixed
  scaffold lines regardless of Things data (see the template above) — if
  `things_today.py` has no items for one of them, just omit the placeholder
  entirely and let the fixed lines stand alone. Don't add a "Nothing here
  today" line on top of an already-non-empty section.

`{{AGENDA}}` is the one placeholder **not** driven by `things_today.py` — it
comes from `scripts/calendar_agenda` instead (see SKILL.md step 2). One
`- [ ] ` line per event, **all calendars merged together** (including the
`Work` calendar — don't split it out), sorted by start time (the script
already sorts). Format: `- [ ] {start time}–{end time} {title}` (e.g.
`- [ ] 9:00 AM–9:30 AM Standup`) for timed events, or `- [ ] All day:
{title}` when `isAllDay` is true. If there are none, use `- [ ] Nothing on
the calendar today`. Times in the user's local time zone, 12-hour clock, no
leading zero (`9:00 AM`, not `09:00`).

Note the Work, Professional Growth, and Physical sections each mix
data-driven items *and* fixed scaffold lines in the same section — put the
Things items first, then the section's fixed lines below them (already
reflected in the template above).
