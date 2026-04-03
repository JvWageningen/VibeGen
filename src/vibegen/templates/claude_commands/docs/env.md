## Scope
Document environment variables and configuration for this project.
Do NOT modify source code — documentation only.

## Anchor
Search all source files for `os.environ`, `os.getenv`, dotenv references, and config loading patterns.

## Outcome
Create or update `docs/ENV.md` with a table for each variable:

| Variable | Description | Required | Default | Example |
|----------|-------------|----------|---------|---------|
| DATABASE_URL | PostgreSQL connection string | yes | — | postgres://user:pass@host/db |

Flag any hardcoded values found in source code that should be environment variables.
