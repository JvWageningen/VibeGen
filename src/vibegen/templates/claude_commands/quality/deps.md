Audit project dependencies.

1. Run: `uv run pip-audit` to scan for known CVEs and vulnerabilities
2. Run: `uv tree` to show the full dependency tree
3. For vulnerable packages shown by pip-audit: run `uv add <package>@latest` to upgrade
4. Read pyproject.toml; identify unpinned or loosely-pinned packages and suggest pins
5. Flag abandoned packages (no releases in 2+ years, archived repo)
