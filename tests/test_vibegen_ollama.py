#!/usr/bin/env python
"""Test vibegen with Ollama code generation."""

from src.vibegen.cli import main
import sys

sys.exit(main([
    'test-projects/spec-example-word-counter.md',
    '--output-dir', 'test-output',
    '--model-provider', 'ollama',
    '--model', 'qwen2.5-coder:14b'
]))
