Audit for security vulnerabilities: $ARGUMENTS (or whole codebase if omitted)

1. Run automated scanners first:
   `uv run bandit -c pyproject.toml -r src/ -f txt; uv run pip-audit`
2. Review bandit findings: fix all Medium and High severity issues
3. Review pip-audit findings: upgrade vulnerable packages with `uv add <pkg>@latest`
4. Manually check for issues bandit cannot detect: hardcoded secrets, unsanitized user input, path traversal, insecure deserialization, missing auth checks
5. For each issue: describe the vulnerability, severity, and apply the fix
