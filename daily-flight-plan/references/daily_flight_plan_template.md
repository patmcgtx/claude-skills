# Daily Flight Plan template

This is the user's actual Day One template, confirmed against a real entry's
raw markdown (the `dayone` CLI has no way to invoke a saved template by name,
so the skill reproduces this text directly). Confirmed formatting: `#`/`##`
are true Day One headings (not just bold text), and every bullet is a
checkbox (`- [ ] `, not a plain `-`).

Three sections get data-driven content each day; every other section is
reproduced exactly as-is, untouched, for the user to fill in by hand later
(that's the existing daily ritual — don't try to be clever and auto-fill
Breakfast/Lunch/Dinner, People & phone, Laptop, or Home).

```markdown
# 🚀 Daily Flight Plan
*What is today's purpose? Who do I want to be?*

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

- [ ] TODO

## Work work

{{WORK_AGENDA}}
- [ ] Catch up work Reminders®
- [ ] Work email zero inbox

## Professional Growth

- [ ] Do [hackerrank](https://www.hackerrank.com/) or leetcode.com

## Physical 💪🏻

- [ ] Walk
- [ ] Sprint + box, balance ball, yoga, swim, bike
- [ ] ❗️Plantar fasciitis PT
- [ ] Or runner's yoga

## Laptop

- [ ] TODO

## Home

- [ ] TODO
```

## Filling the three placeholders

- **`{{TIME_SENSITIVE}}`** — one `- [ ] ` line per item from
  `things_deadlines.py`'s output. Format: `- [ ] {title} ({project})` if the
  to-do has a project, else `- [ ] {title}`; prefix with `⚠️ ` when
  `"overdue": true`. If the list is empty, use a single line:
  `- [ ] Nothing with a deadline today`.
- **`{{AGENDA}}`** — one `- [ ] ` line per event from `calendar_agenda`
  whose `calendar` is **not** `"Work"`, sorted by start time (the script
  already sorts). Format: `- [ ] {start time}–{end time} {title}` (e.g.
  `- [ ] 9:00 AM–9:30 AM Standup`) for timed events, or `- [ ] All day: {title}`
  when `isAllDay` is true. If there are none, use
  `- [ ] Nothing on the calendar today`.
- **`{{WORK_AGENDA}}`** — same formatting as Agenda, but only events whose
  `calendar` **is** `"Work"`. This replaces the template's normal fixed
  "Update here from work calendar" line — if there are no work events, keep
  a single line `- [ ] No work events today` rather than leaving it blank,
  so the checklist item count in Day One still makes sense.

Times should be formatted in the user's local time zone, 12-hour clock, no
leading zero (e.g. `9:00 AM`, not `09:00`) — match the ambient style of the
rest of the template rather than defaulting to 24-hour or ISO time.
