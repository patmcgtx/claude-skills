# claude-skills

Personal [Claude Code](https://claude.com/claude-code) skills. Each subdirectory is a skill: a `SKILL.md` with the instructions Claude reads, plus any scripts or reference docs it calls out to.

## Installing

Claude Code loads skills from `~/.claude/skills/`. Clone this repo there directly, or symlink it in:

```sh
git clone git@github.com:patmcgtx/claude-skills.git ~/.claude/skills
```

New skills added here are picked up automatically — no restart needed.

## Skills

| Skill | Description |
|---|---|
| [things-report](things-report/SKILL.md) | Reports on a Things.app to-do database: completed-work summaries, backlog health, velocity trends, per-project breakdowns, and stale/aging-project callouts. |

## Layout

```
<skill-name>/
  SKILL.md          # instructions Claude reads when the skill triggers
  scripts/          # helper scripts the skill shells out to
  references/       # supplementary docs Claude reads on demand
```
