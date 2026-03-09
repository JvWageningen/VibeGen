#!/usr/bin/env python
"""Simple test of ollama_client."""

import subprocess
import sys

cmd = [
    sys.executable, "-m", "vibegen.ollama_client",
    "--model", "qwen2.5-coder:14b",
    "--user", "Say hello",
    "--verbose"
]

print(f"Running: {' '.join(cmd)}")
print()

proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

print(f"Return code: {proc.returncode}")
print(f"Stdout length: {len(proc.stdout)}")
print(f"Stderr length: {len(proc.stderr)}")
print()

if proc.stdout:
    print("STDOUT:")
    print(proc.stdout[:500])

if proc.stderr:
    print("\nSTDERR:")
    print(proc.stderr[:500])
