Add Google-style docstrings to: $ARGUMENTS

1. Read the source file
2. Add docstrings to all public APIs missing them: one-line summary, Args (with types), Returns, Raises, Example (where helpful)
3. Run: uv run ruff check . --fix && uv run ruff format .