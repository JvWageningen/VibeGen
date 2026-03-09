# VibeGen Architecture

## Overview

VibeGen is a Windows PowerShell automation layer that orchestrates Claude Code to
generate complete, production-quality Python projects from a plain-English spec file,
or to repair and improve existing Python repositories.

It works by running `claude -p` (non-interactive pipeline mode) with carefully
constructed prompts, with algorithmic pre-processing done in PowerShell to minimize
the number of Claude turns and API calls required.

```
spec.md  -->  vibegen.ps1  -->  claude -p  -->  Generated project
                 |                                      |
                 |  (algorithmic pre-processing)        |
                 |  ruff, mypy, bandit, radon,          |
                 |  vulture, pip-audit                  |
                 |                                      |
                 +--------------------------------------+
                           .claude/commands/
                           settings.local.json
```

---

## Files

| File | Purpose |
|------|---------|
| `vibegen.ps1` | Main entry point — generate and repair modes |
| `setup-vibegen.ps1` | One-time installer: installs dependencies, PATH, templates |
| `spec.example.md` | Annotated example spec file (weather alerter) |
| `.claude/commands/` | 43 slash command templates installed into generated projects |
| `.claude/settings.local.json` | Claude Code permission rules copied to generated projects |

---

## vibegen.ps1 — Generate Mode

Triggered by: `vibegen spec.md`

The spec file is parsed algorithmically in PowerShell before Claude is invoked.
Extracted fields:

| Spec section | Variable | Used for |
|---|---|---|
| `## Name` | `$projectName`, `$packageName` | Directory name, Python package name |
| `## Python Version` | `$pythonVersion` | `uv init --python` |
| `## Dependencies` | `$dependencies` | `uv add` |
| `## Usage/Examples/CLI/API` | `$usageSection` | README generation |
| `<!-- docs/... -->` comments | `$docFiles` | Reference docs passed to Claude |

### Steps

```
Step 1   uv init + uv add (deps + dev-deps)
Step 2   git init, .gitignore, .gitattributes
Step 3   Copy reference documentation files
Step 4   Generate CLAUDE.md (from spec data, no Claude call)
Step 5   Generate .vscode/settings.json (hardcoded template)
Step 6   Install .claude/commands/ + settings.local.json
Step 7   Append tool config to pyproject.toml (ruff/pytest/mypy/bandit/vulture)
Step 8   Generate .pre-commit-config.yaml + install hooks
         ---- checkpoint commit ----
Step 9   Claude: generate source code in src/<package>/
         -> ruff auto-fix run natively after Claude returns
Step 10  Claude: generate test suite in tests/
Step 11  Fix loop (up to MaxFixAttempts):
           - ruff auto-fix -> re-run pytest -> if pass: done (no Claude call)
           - else: Claude fixes with trimmed failure output
Step 12  Final quality checks (all non-blocking, reported as warnings):
           ruff, mypy, bandit, pip-audit, radon cc, vulture
Step 13  README.md generated from spec data (no Claude call)
```

### Claude calls in generate mode

| Step | Claude call | Can be skipped? |
|------|-------------|-----------------|
| 9 | Source code generation | Never |
| 10 | Test suite generation | Never |
| 11 | Test fix (per attempt) | Yes — if ruff auto-fix resolves failures |

---

## vibegen.ps1 — Repair Mode

Triggered by: `vibegen -Repair [-RepoPath <path>]`

Improves an existing Python project in three phases, with algorithmic pre-processing
before each Claude call so Claude starts with the full diagnostic picture.

```
Phase 1/3 — Structure
  Pre-run: ruff --fix, ruff check (remaining), radon cc -mi C, vulture
  Claude: fixes type hints, docstrings, complexity, dead code

Phase 2/3 — Tests
  Claude: reads source, adds missing tests and coverage

Fix loop (up to MaxFixAttempts):
  ruff auto-fix -> re-run pytest -> Claude if still failing

Phase 3/3 — Final quality
  Pre-run: ruff check, mypy, bandit, pip-audit
  Claude: fixes type errors, security issues, upgrades vulnerable deps
  Native ruff run after Claude returns
```

---

## Algorithmic Pre-processing (key design decision)

Rather than asking Claude to discover issues by running tools, VibeGen runs the
tools first in PowerShell and injects the output into Claude's prompt. This means:

- Claude reads only files that have reported issues (not all files blindly)
- No tool-discovery turns are spent — Claude goes straight to fixing
- ruff auto-fix runs before every Claude fix call; if it resolves all failures,
  the Claude call is skipped entirely
- pytest output is trimmed to failure-relevant lines only before being sent

Tools run natively before prompting Claude:

| Tool | When | Injected into prompt? |
|------|------|-----------------------|
| ruff --fix | Before every Claude call | No (applied, then residual injected) |
| ruff check | Repair Phase 1 and 3 | Yes — remaining violations |
| mypy | Repair Phase 3 | Yes — all type errors |
| bandit | Repair Phase 3 | Yes — Medium/High findings only |
| pip-audit | Repair Phase 3 | Yes — if CVEs found |
| radon cc | Repair Phase 1 | Yes — grade C+ functions (CC >= 11) |
| vulture | Repair Phase 1 | Yes — >= 80% confidence unused code |

---

## Install-ClaudeFiles Helper

Called in both generate and repair modes. Copies from `~/.vibegen/` into the
target project's `.claude/` directory:

- All `commands/**/*.md` files (preserving category subdirectory structure)
- `settings.local.json` (Claude Code permission rules)
- Substitutes `{{PACKAGE_NAME}}` in `feature/new-module.md`

Source of truth: `.claude/commands/` in this repo → `setup-vibegen.ps1` copies
to `~/.vibegen/commands/` at install time → `Install-ClaudeFiles` copies from
there to each generated project.

---

## Slash Commands — Category Structure

43 command files, callable as `/category:command` in Claude Code.

```
analysis/    (10)  debug, explain, find, impact, map, map-repo, search, trace, where, why
docs/         (6)  adr, changelog, doc, doc-repo, env, index
feature/      (7)  add, extend, implement, integrate, new-module, plan, scaffold
quality/     (16)  cleanup, dedupe, deps, fix, migrate, profile, refactor, refactor-module,
                   refactor-repo, rename, review, security, ship, simplify, standardize, type-fix
test/         (4)  coverage, edge, generate, reproduce
```

All commands follow the "batch diagnostics first" pattern:
- Run tools upfront in one step to get the full picture
- Apply auto-fixes before reading files
- Read only files with reported issues

---

## Generated Project Structure

```
<project-name>/
+-- .claude/
|   +-- commands/          <- 43 slash commands (5 categories)
|   +-- settings.local.json
+-- .vscode/
|   +-- settings.json      <- Format-on-save, Ruff, Pylance strict
+-- .pre-commit-config.yaml <- ruff + bandit + vulture hooks
+-- CLAUDE.md              <- Project context (tech stack, commands, style rules)
+-- README.md              <- Generated from spec data
+-- pyproject.toml         <- ruff + pytest + mypy + bandit + vulture config
+-- src/<package>/
|   +-- __init__.py + modules
+-- tests/
    +-- conftest.py
    +-- test_*.py
```

### Dev dependencies installed in every generated project

`pytest`, `pytest-cov`, `ruff`, `mypy`, `pre-commit`, `bandit`, `pip-audit`,
`radon`, `vulture`

---

## settings.local.json — Permission Model

Copied into every generated project. Defines Claude Code tool permissions:

- **Allow**: `Bash(*)` — all bash commands permitted by default
- **Ask**: destructive or risky operations (rm, mv, git reset/clean/checkout, pip install, docker)
- **Deny**: catastrophic operations (rm -rf /, sudo, shutdown, dd, mkfs)

---

## Data Flow

```
spec.md
  |
  v
vibegen.ps1 (PowerShell)
  |  parse: name, python version, deps, usage section, doc refs
  |
  +-> uv init + uv add          (Step 1 — scaffold)
  +-> git init                   (Step 2)
  +-> CLAUDE.md                  (Step 4 — template, no Claude)
  +-> .vscode/settings.json      (Step 5 — template, no Claude)
  +-> .claude/ files             (Step 6 — copied from ~/.vibegen/)
  +-> pyproject.toml config      (Step 7 — appended, no Claude)
  +-> pre-commit config          (Step 8 — template, no Claude)
  |
  +-> claude -p "$codePrompt"    (Step 9 — source generation)
  |     +-> ruff --fix (native)
  |
  +-> claude -p "$testPrompt"    (Step 10 — test generation)
  |
  +-> Fix loop x MaxFixAttempts  (Step 11)
  |     +-> ruff --fix + pytest
  |     +-> [if still failing] claude -p "$fixPrompt"
  |
  +-> ruff + mypy + bandit + pip-audit + radon + vulture (Step 12 — report)
  |
  +-> README.md                  (Step 13 — from spec data, no Claude)
```

---

## Key Design Decisions

**Copy vs hardcode commands**: Command files live as `.md` files in the repo
and are copied at install/generate time. Hardcoding them in `vibegen.ps1` would
duplicate ~700 lines across generate and repair modes with no single source of truth.

**Algorithmic pre-processing**: Running ruff, mypy, bandit, radon, and vulture
before Claude calls eliminates tool-discovery turns. Claude receives the output
directly and can immediately read affected files and apply fixes.

**ruff before fix loop iterations**: Running `ruff --fix` before each Claude
fix attempt means some failures that are pure lint/formatting issues get resolved
without spending a Claude call.

**README without Claude**: The spec already contains project name, description,
Python version, and a usage section. Generating README from this data saves one
full Claude call per project without reducing documentation quality.

**Permission model via settings.local.json**: Rather than passing permission
flags on every `claude -p` invocation, the project-level `settings.local.json`
encodes a safe default policy that also applies to manual Claude Code sessions in VS Code.
