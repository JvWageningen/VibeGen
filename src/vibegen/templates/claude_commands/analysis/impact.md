think hard

## Scope
Show what breaks if this changes: $ARGUMENTS
Do NOT make any changes — assess impact only.

## Anchor
Run `cymbal impact $ARGUMENTS` for transitive callers. Fallback: list exported names, find all import sites.
Assess: direct callers (signature changes), indirect callers (type errors), test coverage.

## Outcome
| File | Symbol | Impact Type | Severity | Update Required |
|------|--------|-------------|----------|-----------------|
| path/to/file.py | caller_fn | signature change | Breaking | yes — update call site |

Impact Type: signature / type / behavior / import
Severity: Breaking / Non-breaking
