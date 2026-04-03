#!/usr/bin/env bash
# Stop hook: verify ruff+pytest+mypy before Claude finishes its turn.
# Exits non-zero to force Claude to continue and fix any failures.
set -uo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Skip if no Python files changed (avoids running suite on analysis-only sessions)
changed=$(
    git diff --name-only HEAD 2>/dev/null
    git diff --name-only --cached 2>/dev/null
    git ls-files --others --exclude-standard '*.py' 2>/dev/null
)
if ! echo "$changed" | grep -q '\.py$'; then
    exit 0
fi

errors=""
ruff_out=$(uv run ruff check . --output-format=concise 2>&1) || errors+="RUFF:\n$ruff_out\n\n"
pytest_out=$(uv run pytest -x --tb=line -q 2>&1) || errors+="PYTEST:\n$pytest_out\n\n"
mypy_out=$(uv run mypy src/ --no-error-summary 2>&1) || errors+="MYPY:\n$mypy_out\n\n"

if [ -n "$errors" ]; then
    echo "=== VERIFICATION FAILED ==="
    printf "%b" "$errors"
    echo "Fix the above before finishing."
    exit 1
fi
exit 0
