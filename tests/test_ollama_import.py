#!/usr/bin/env python
"""Simple test of ollama_client with proper path setup."""

import subprocess
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Test direct import first
try:
    from vibegen.ollama_client import main
    print("✓ Direct import of ollama_client successful")
    
    # Test with argv
    result = main([
        "--model", "qwen2.5-coder:14b",
        "--user", "Say hello",
        "--verbose"
    ])
    print(f"Return code: {result}")
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
