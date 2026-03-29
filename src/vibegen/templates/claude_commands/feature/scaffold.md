Scaffold boilerplate for: $ARGUMENTS

Examples: typer CLI command, FastAPI endpoint, Pydantic model, pytest fixture, async task, background worker

1. Read relevant existing code to match project patterns
2. Generate the scaffold with type hints, Google-style docstrings, loguru logging
3. Place in the appropriate module; export from __init__.py if public
4. Run: uv run ruff check . --fix && uv run ruff format .