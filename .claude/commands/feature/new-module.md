Create `src/{{PACKAGE_NAME}}/$ARGUMENTS.py` with a module docstring, absolute imports from {{PACKAGE_NAME}}, type-hinted stubs, and Google-style docstrings on all public members.
Create `tests/test_$ARGUMENTS.py` with at least one test per public function.

Run: uv run ruff check . --fix && uv run ruff format . && uv run pytest -x --tb=short