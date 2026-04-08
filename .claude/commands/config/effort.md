## Scope

Toggle between min, default, and max effort modes in `.claude/settings.json`.

## Argument

$ARGUMENTS — must be `min`, `default`, or `max`. If empty, report the current mode.

## Rules

Read `.claude/settings.json` and parse the `env` object and `model` field.

**Current mode detection:**

- If `CLAUDE_CODE_SUBAGENT_MODEL` is absent from `env`: **max** mode (all opus)
- If `CLAUDE_CODE_SUBAGENT_MODEL` is `claude-sonnet-4-6` and `model` is `opusplan`: **default** mode
- If `CLAUDE_CODE_SUBAGENT_MODEL` is `claude-haiku-4-5-20251001` and `model` is `sonnet`: **min** mode

If no argument given: report the current mode and exit.

**Mode configurations:**

| Mode | `model` | `CLAUDE_CODE_SUBAGENT_MODEL` | Use case |
|------|---------|------------------------------|----------|
| `max` | (unchanged) | (remove key) | Complex architecture, deep debugging |
| `default` | `opusplan` | `claude-sonnet-4-6` | Daily development (best cost/quality) |
| `min` | `sonnet` | `claude-haiku-4-5-20251001` | Simple tasks, lint fixes, boilerplate |

Write back `.claude/settings.json` with 2-space indentation. Report what changed.
