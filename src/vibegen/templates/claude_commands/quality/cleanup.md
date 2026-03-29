Remove dead code, unused imports, and duplicate utilities.

1. Run automated scanners: `uv run ruff check . --fix && uv run ruff format .; uv run vulture src/ --min-confidence 80`
2. Review vulture findings: remove confirmed unused functions, classes, and variables
3. Find duplicate utilities across modules; consolidate into one canonical location
4. Verify: `uv run pytest -x --tb=short`
