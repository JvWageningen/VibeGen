# Contributing to VibeGen

## Claude Code configuration

VibeGen ships with a committed `.claude/settings.json` that configures Claude Code for all contributors. Personal overrides go in `.claude/settings.local.json`, which is gitignored.

### Default configuration explained

| Setting | Value | Rationale |
|---|---|---|
| `model` | `claude-opus-4-6` | Strongest reasoning for architecture and planning phases |
| `MAX_THINKING_TOKENS` | `10000` | Extended thinking budget for complex multi-step tasks |
| `CLAUDE_CODE_SUBAGENT_MODEL` | `claude-haiku-4-5-20251001` | Fast, cheap model for subagent/parallel tasks |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | `50` | Compact context at 50% to prevent mid-task truncation |

### Override for cost-conscious development

If you want to reduce API costs during local iteration, add a `settings.local.json`:

```json
{
  "model": "claude-sonnet-4-6"
}
```

This overrides the committed default without affecting other contributors.

## Context management

Three mechanisms keep Claude Code's context window healthy during long sessions:

1. **`read_once.py` hook** — Blocks re-reading files that haven't changed since the last read. Automatically invalidates cache entries when a file's mtime advances, so edits are always visible. State resets after 6 hours.

2. **Autocompact at 50%** — `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50` triggers context compaction when the window reaches 50% capacity, well before the model starts losing early context.

3. **cymbal CLI** — Index-based code navigation. Instead of reading whole files, Claude uses `cymbal investigate`, `cymbal search`, and `cymbal outline` to navigate symbols directly.

   ```bash
   pip install cymbal
   cymbal index .       # build initial index (< 1 s)
   cymbal structure     # overview of the codebase
   ```

   Run `cymbal index .` after significant refactors to refresh the index.
