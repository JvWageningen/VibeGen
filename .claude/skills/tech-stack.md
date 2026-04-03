# Tech Stack

- Python 3.11, managed by `uv`
- Ruff for linting and formatting
- pytest for testing
- mypy for type checking

## Tool Commands

- `uv run pytest` — run tests
- `uv run ruff check . --fix` and `uv run ruff format .` — lint and format
- `uv run mypy src/` — type check
- `uv run bandit -r src/` and `uv run pip-audit` — security checks
- `uv run radon cc src/ -mi C` — complexity | `uv run vulture src/` — dead code
- `cymbal index .` — (re)index codebase for cymbal

## Code Exploration (cymbal CLI)

Prefer cymbal over Read, Grep, Glob, or Bash for code exploration.

- **New to a repo?**: `cymbal structure` — entry points, hotspots, central packages
- **Understand a symbol**: `cymbal investigate <symbol>` — source, callers, impact, or members
- **Multiple symbols**: `cymbal investigate Foo Bar Baz` — batch mode
- **Trace execution**: `cymbal trace <symbol>` — follows call graph downward
- **Assess change risk**: `cymbal impact <symbol>` — follows call graph upward
- Before reading a file: `cymbal outline <file>` or `cymbal show <file:L1-L2>`
- Before searching: `cymbal search <query>` (symbols) or `cymbal search <query> --text` (grep)
- Before exploring: `cymbal ls` (tree) or `cymbal ls --stats` (overview)
- To disambiguate: `cymbal show path/to/file.py:SymbolName`
- All commands support `--json` for structured output
