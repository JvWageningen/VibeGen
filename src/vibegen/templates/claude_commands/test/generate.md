Generate tests for: $ARGUMENTS

1. Read the source file; create or update the matching test file in tests/
2. Test every public function: happy path, edge cases, error handling; use fixtures and parametrize
3. Mock external dependencies (network, file I/O, APIs)
4. Use specific exception types in pytest.raises() - never bare Exception; name tests test_<function>_<scenario>
5. Run: uv run pytest -x --tb=short && uv run ruff check tests/ --fix && uv run ruff format tests/