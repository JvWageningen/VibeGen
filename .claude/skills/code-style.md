# Code Style Rules

- Type hints on all signatures; Google-style docstrings on all public API
- Use loguru (not print); Pydantic models for structured data
- Early returns over nesting; functions under 30 lines
- Absolute imports: `from vibegen.module import ...`
- `from __future__ import annotations` at top of every module
- snake_case files/functions, PascalCase classes, UPPER_SNAKE_CASE constants
- Prefix private with `_`; `# noqa: BLE001` on intentional broad catches
- Console via `_print_step/ok/warn/err`; subprocess via `_run_cmd()`
- No bare `except:`; no mutable defaults; no `print()`
