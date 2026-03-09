#!/usr/bin/env python
"""Test ollama client directly."""

from src.vibegen.ollama_client import main
import sys

# Test with a simple prompt
sys.exit(main([
    '--model', 'qwen2.5-coder:14b',
    '--user', 'Output a simple Python function in this format:\n--- file: example.py ---\ndef hello():\n    return "hello"'
]))
