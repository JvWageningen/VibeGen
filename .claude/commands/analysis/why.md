think hard

## Scope
Explain the root cause of: $ARGUMENTS
Do NOT apply fixes — explain only.

## Anchor
Run `cymbal trace` and `cymbal investigate` to follow the execution path from the error source. Fallback: search for code that raises/produces this error, trace manually.

## Outcome
Produce structured markdown with these sections:

- **Symptom**: what the user observes (error message, wrong output, crash)
- **Root Cause**: the underlying code defect or wrong assumption
- **Evidence**: file:line citations tracing from symptom back to cause
- **Recommended Fix**: the minimal change that addresses the root cause
