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

## Commands
- `uv run pytest` - run tests
- `uv run ruff check . --fix` - lint and fix
- `uv run ruff format .` - format
- `uv run mypy src/` - type check
- `uv run bandit -r src/` - security check
- `uv run pip-audit` - dependency vulnerability check
- `uv run radon cc src/ -mi C` - complexity report
- `uv run vulture src/` - unused code detection

## Code Style Rules
- Always add type hints to function signatures
- Use Google-style docstrings on every public function and class
- Use loguru for logging, never print()
- Use Pydantic models for structured data
- Prefer early returns over deep nesting
- Keep functions under 30 lines; extract helpers if longer
- Use absolute imports: `from vibegen.module import ...`
- snake_case for files, modules, functions, variables
- PascalCase for classes
- UPPER_SNAKE_CASE for constants
- Prefix internal/private modules and functions with `_` (e.g. `_pipeline.py`, `_run_cmd`)
- Add `from __future__ import annotations` at the top of every module
- Use `# noqa: BLE001` on broad `except Exception` catches where intentional
- All console output goes through `_print_step`, `_print_ok`, `_print_warn`, `_print_err`
- All subprocess calls go through `_run_cmd()` (supports transparent Docker sandbox)

## Commit Message Style

Follow Conventional Commits:

- `feat:` new feature
- `fix:` bug fix
- `chore:` maintenance (scaffold, config, tooling)
- `test:` test changes
- `docs:` documentation only

## Verification
After any code change, always:
1. Run: `uv run ruff check . --fix` and `uv run ruff format .`
2. Run: `uv run pytest -x`
3. Run: `uv run mypy src/`

## Things to Avoid
- Never use pip install directly; always `uv add`
- Never use bare `except:` - catch specific exceptions
- Never use mutable default arguments
- No `print()` statements - use loguru
