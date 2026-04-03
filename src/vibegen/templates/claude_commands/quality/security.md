think hard

## Scope
Audit for security vulnerabilities: $ARGUMENTS (or whole codebase if omitted)
Do NOT introduce new logic while fixing — targeted fixes only.

## Anchor
Run `uv run bandit -c pyproject.toml -r src/ -f txt; uv run pip-audit`.
Manually check: hardcoded secrets, unsanitized input, path traversal, insecure deserialization, missing auth.

## Outcome
| File | Line | Vulnerability Type | Severity | Description | Fix |
|------|------|--------------------|----------|-------------|-----|
| src/pkg/api.py | 42 | SQL injection | High | f-string in query | use parameterized query |

Severity: Critical / High / Medium / Low
Fix Medium+ bandit findings. Upgrade vulnerable packages with `uv add <pkg>@latest`.
