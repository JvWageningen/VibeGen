Improve test coverage for: $ARGUMENTS

1. Run: uv run pytest --cov=src --cov-report=term-missing -x
2. Read the coverage report and source file to identify uncovered paths
3. Add tests for uncovered lines and branches; re-run to confirm improvement
4. Run: uv run ruff check tests/ --fix && uv run ruff format tests/