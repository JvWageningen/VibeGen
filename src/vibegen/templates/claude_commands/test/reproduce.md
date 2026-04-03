think

## Scope
Generate a minimal reproducing test for: $ARGUMENTS (bug description or error message)
The test MUST FAIL with the bug present — do NOT write a passing test.

## Anchor
Read relevant source files. Trace how the bug is triggered.

## Outcome
A minimal pytest test that:

- **Steps to Reproduce**: minimum setup required
- **Expected Behavior**: what should happen
- **Actual Behavior**: what currently happens (how the test fails)
- **Root Cause**: brief diagnosis of why it fails
- **Reproducing Test**: the test function (run to confirm it fails; add to appropriate test file)
