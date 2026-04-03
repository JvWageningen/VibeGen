#!/usr/bin/env python3
"""PostToolUse hook: auto-lint .py files after Write or Edit."""
from __future__ import annotations

import json
import os
import subprocess
import sys


def main() -> None:
    data = json.load(sys.stdin)
    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path.endswith(".py") or not os.path.isfile(file_path):
        return
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    for cmd in (
        ["uv", "run", "ruff", "check", "--fix", file_path],
        ["uv", "run", "ruff", "format", file_path],
    ):
        try:
            subprocess.run(cmd, cwd=project_root, capture_output=True, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass


if __name__ == "__main__":
    main()
