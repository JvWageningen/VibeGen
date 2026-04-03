think

## Scope
Generate integration tests for: $ARGUMENTS
Focus on subprocess interactions — mock external tools, not internal logic.
Do NOT modify source code — write tests only.

## Anchor
Read the target source file. Identify all `subprocess.run`, `_run_cmd`, and shell-out calls.
Read existing test patterns in `tests/` for mocking conventions (patch `_run_cmd`, `subprocess.run`).

## Outcome
| Function | External Tool | Mock Strategy | Test Names |
|----------|---------------|---------------|------------|

Per subprocess call, test:
- Success path (returncode=0, expected stdout)
- Failure path (returncode!=0, CalledProcessError)
- Timeout path where applicable
Use `tmp_path` fixture for filesystem side effects. `uv run pytest -x` passes.
