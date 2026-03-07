Show what breaks if this changes: $ARGUMENTS

1. List all exported names in the file; find all import sites across the codebase
2. Assess impact: direct callers (signature changes), indirect callers (type errors), tests covering this code
3. Output a prioritized list of files needing updates