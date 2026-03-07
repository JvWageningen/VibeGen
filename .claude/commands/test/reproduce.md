Generate a minimal reproducing test for: $ARGUMENTS

1. Read relevant source files
2. Write the smallest pytest test that: sets up minimum state, triggers the bug, asserts incorrect behavior (test MUST FAIL with bug present)
3. Run: uv run pytest <test_file> -x --tb=short to confirm it fails; add to the appropriate test file