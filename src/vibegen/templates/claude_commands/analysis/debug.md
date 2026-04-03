think hard

## Scope
Find bugs and logic errors in: $ARGUMENTS
Do NOT fix the bugs — report only.
Check: off-by-one, edge cases (empty/None/zero/negative/boundary), swallowed exceptions, logic errors in conditionals, type mismatches between callers and callees.

## Anchor
Run `cymbal investigate $ARGUMENTS` and `cymbal trace $ARGUMENTS`. Read the file and its tests.

## Outcome
For each bug found, output a row in this table:

| File | Line | Bug Description | Severity | Trigger Condition | Fix |
|------|------|-----------------|----------|-------------------|-----|
| path/to/file.py | 42 | off-by-one in loop | High | list length = 0 | change `<` to `<=` |

Severity: Critical / High / Medium / Low
