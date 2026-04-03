## Scope
Audit project dependencies for vulnerabilities and maintenance issues.
Do NOT upgrade packages without confirming compatibility.

## Anchor
Run `uv run pip-audit` for CVEs. Run `uv tree` for dependency tree. Read pyproject.toml.

## Outcome
| Package | Current Version | Status | Action |
|---------|-----------------|--------|--------|
| requests | 2.28.0 | CVE-2023-xxxxx | uv add requests@latest |
| old-lib | 1.0.0 | abandoned (no release 2yr) | consider replacement |

Flag unpinned packages, abandoned packages (no releases 2+ years, archived repo).
