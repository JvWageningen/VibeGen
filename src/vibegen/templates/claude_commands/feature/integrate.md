Integrate external API or service: $ARGUMENTS

1. Read relevant source files
2. Create a dedicated module with: typed client class, Pydantic models for request/response, network/API error handling, loguru logging
3. Write tests mocking the external service; export from __init__.py
4. Run: uv run ruff check . --fix && uv run ruff format .
5. Run: uv run pytest -x --tb=short