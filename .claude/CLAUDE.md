# vibegen

## Project

Cross-platform Python project generator powered by Claude Code.

## Tech Stack

- Python 3.11, managed by `uv`
- Ruff for linting and formatting
- pytest for testing
- mypy for type checking

## Directory Map

- `src/vibegen/` - main package
- `tests/` - test suite (mirrors src structure)
- `docs/reference/` - repo information reference docs (ARCHITECTURE.md, CHANGELOG.md)

## Commands

- `uv run pytest` - run tests
- `uv run ruff check . --fix` and `uv run ruff format .` - lint and format
- `uv run mypy src/` - type check
- `uv run bandit -r src/` and `uv run pip-audit` - security checks
- `uv run radon cc src/ -mi C` - complexity | `uv run vulture src/` - dead code
- `cymbal index .` - (re)index codebase for cymbal

## Code Style Rules

- Type hints on all signatures; Google-style docstrings on all public API
- Use loguru (not print); Pydantic models for structured data
- Early returns over nesting; functions under 30 lines
- Absolute imports: `from vibegen.module import ...`
- `from __future__ import annotations` at top of every module
- snake_case files/functions, PascalCase classes, UPPER_SNAKE_CASE constants
- Prefix private with `_`; `# noqa: BLE001` on intentional broad catches
- Console via `_print_step/ok/warn/err`; subprocess via `_run_cmd()`

## Documentation First Rule

For complex features or refactors:

1. First update or create reference docs in `docs/reference/`
2. Then implement code changes

## Efficiency

- Read specific line ranges (offset/limit), not whole files. Use Grep before Read.
- Batch independent tool calls into single messages.
- Use /compact at logical breakpoints. Never let context exceed ~200K.

## Code Exploration Policy

Use `cymbal` CLI for code navigation — prefer it over Read, Grep, Glob, or Bash for code exploration.

- **New to a repo?**: `cymbal structure` — entry points, hotspots, central packages. Start here.
- **To understand a symbol**: `cymbal investigate <symbol>` — returns source, callers, impact, or members based on what the symbol is.
- **To understand multiple symbols**: `cymbal investigate Foo Bar Baz` — batch mode, one invocation.
- **To trace an execution path**: `cymbal trace <symbol>` — follows the call graph downward (what does X call, what do those call).
- **To assess change risk**: `cymbal impact <symbol>` — follows the call graph upward (what breaks if X changes).
- Before reading a file: `cymbal outline <file>` or `cymbal show <file:L1-L2>`
- Before searching: `cymbal search <query>` (symbols) or `cymbal search <query> --text` (grep)
- Before exploring structure: `cymbal ls` (tree) or `cymbal ls --stats` (overview)
- To disambiguate: `cymbal show path/to/file.py:SymbolName` or `cymbal investigate file.py:Symbol`
- First run: `cymbal index .` to build the initial index (<1s). After that, queries auto-refresh — no manual reindexing needed.
- All commands support `--json` for structured output.

## Verification

After any code change:

1. `uv run ruff check . --fix` and `uv run ruff format .`
2. `uv run pytest -x`
3. `uv run mypy src/`

## Things to Avoid

- Never `pip install`; always `uv add`
- No bare `except:`; no mutable defaults; no `print()`
- Commit style: `feat:`, `fix:`, `chore:`, `test:`, `docs:`
