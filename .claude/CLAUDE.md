# vibegen

## Project

Cross-platform Python project generator powered by Claude Code.

See `.claude/skills/` for code style, tech stack, and project layout rules.

## Directory Map

- `src/vibegen/` — main package
- `tests/` — test suite (mirrors src structure)
- `docs/reference/` — ARCHITECTURE.md, CHANGELOG.md

## Commands

- `uv run pytest` — run tests
- `uv run ruff check . --fix` and `uv run ruff format .` — lint and format
- `uv run mypy src/` — type check
- `uv run bandit -r src/` and `uv run pip-audit` — security checks
- `uv run radon cc src/ -mi C` — complexity | `uv run vulture src/` — dead code
- `cymbal index .` — (re)index codebase for cymbal

## Code Exploration Policy

Use `cymbal` CLI for code navigation — prefer it over Read, Grep, Glob, or Bash.

- `cymbal structure` — entry points, hotspots, central packages
- `cymbal investigate <symbol>` — source, callers, impact, or members
- `cymbal trace <symbol>` — call graph downward
- `cymbal impact <symbol>` — call graph upward
- `cymbal outline <file>` / `cymbal show <file:L1-L2>` — before reading
- `cymbal search <query>` (symbols) / `cymbal search <query> --text` (grep)
- `cymbal ls` / `cymbal ls --stats` — explore structure

## Verification

After any code change:

1. `uv run ruff check . --fix` and `uv run ruff format .`
2. `uv run pytest -x`
3. `uv run mypy src/`

## Workflow Rules

- After implementing a feature or fixing a bug, run Verification before stopping
- When writing new functions, always write tests in the same session
- Before committing, ensure `/quality:ship` passes

## Things to Avoid

- Never `pip install`; always `uv add`
- No bare `except:`; no mutable defaults; no `print()`
- Commit style: `feat:`, `fix:`, `chore:`, `test:`, `docs:`
