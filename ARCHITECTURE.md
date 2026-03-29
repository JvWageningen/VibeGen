# VibeGen Architecture

## Overview

VibeGen is a Python CLI tool that generates complete, production-quality Python projects from a plain-English Markdown specification using LLM providers (Claude or Ollama).

It works by orchestrating:
- **Spec parsing** — Extract project metadata, dependencies, and documentation references from Markdown
- **Project scaffolding** — Initialize a uv project with git, dependencies, CI, and Claude Code commands
- **Session-based LLM generation** — Multi-turn Claude sessions (or Ollama calls) for planning, code generation, and test generation
- **Iterative fixing** — Run tests, parse failures, re-prompt for fixes with full session context
- **Quality validation** — Format with ruff, type-check with mypy, check security with bandit

```
spec.md  →  vibegen create  →  LLM (Claude session / Ollama)  →  Generated project
                |                      |
                |  (spec parsing)      |  (planning + code gen)
                |  project scaffold    |  (test generation)
                |  template setup      |  (iterative fix loop)
                |  doc copying         |
                +──────────────────────┐
                                       v
                            .venv/ + src/ + tests/
                            pyproject.toml configured
                            .claude/ commands bundled
                            git history recorded
```

---

## Module Map

```
src/vibegen/
├── __init__.py              Package version
├── __main__.py              Script entry point
├── cli.py                   CLI argument parsing, orchestrates scaffold + pipeline
├── _analysis.py             Spec parsing, AST-based dependency graph, error context
├── _io.py                   Console output helpers (_print_step/ok/warn/err), _run_cmd
├── _llm.py                  LLM dispatch: Claude CLI, Claude sessions, Ollama, prompt templates
├── _output_parser.py        Parse LLM responses into file:content mappings
├── _pipeline.py             Code gen, test gen, iterative fix loop (Claude & Ollama paths)
├── _plan.py                 TaskPlan dataclass and default plan builder
├── _scaffold.py             Project directory layout, config files, git init, doc copying
├── _session.py              Persistent session state (resume support)
├── ollama_client.py         Ollama HTTP API wrapper
├── sandbox.py               Docker sandbox config for subprocess isolation
├── web_search.py            Multi-provider web search for error context enrichment
├── prompts/                 LLM prompt templates (system, plan, generate_code, etc.)
└── templates/
    └── claude_commands/     43 slash command templates bundled into generated projects
```

---

## Generation Pipeline

Triggered by: `vibegen create spec.md`

### Phase 1: Initialization (no LLM calls)

1. Parse `spec.md` — extract project name, Python version, dependencies, description, doc file references
2. `uv init` — create virtual environment + pyproject.toml
3. `uv add` — install base dependencies from spec
4. `git init` — create .gitattributes, .gitignore
5. Setup .vscode/settings.json, .pre-commit-config.yaml
6. Generate CLAUDE.md (project context from spec, no LLM)
7. Configure pyproject.toml (ruff, pytest, mypy, bandit tool sections)
8. Write `.claude/settings.local.json` with permission rules
9. Copy Claude command templates into `.claude/commands/`
10. Copy documentation files/directories from `## Documentation` section
11. Write `tests/conftest.py` and `.github/workflows/ci.yml`

### Phase 2: LLM-Driven Code Generation

Two provider-specific paths:

**Claude path** (`_generate_code_claude`):
- Opens a multi-turn Claude Code session
- Pass 1: Planning — Claude reads spec.md and CLAUDE.md, writes PLAN.md
- Pass 2: Implementation — Claude reads PLAN.md, implements source code, formats with ruff
- Session ID preserved for later test generation and fixing

**Ollama path** (`_generate_code_ollama`):
- Single-shot prompt with spec + plan context
- Response parsed via `_parse_generated_files()` (delimiter-based file extraction)
- Files written and formatted with ruff

### Phase 3: Test Generation

- Claude: continues the existing session, generates tests with full project context
- Ollama: single-shot prompt with generated source code as context
- Tests written to `tests/test_*.py`, formatted with ruff

### Phase 4: Iterative Test Fixing (up to max attempts)

1. Run pytest, capture failure output
2. If all pass → proceed to Phase 5
3. Run `ruff --fix` (many failures are pure formatting)
4. Re-run pytest
5. If still failing: prompt LLM with error context (+ optional web search enrichment)
6. Parse fixes, update files, commit, loop

### Phase 5: Quality Checks & README

- Run ruff, mypy, bandit, radon (non-blocking, warnings only)
- Generate README.md from spec + generated structure

### Phase 6: Final Status

- Print summary: project location, modules/tests created, pass/fail, quality warnings

---

## Session Persistence

VibeGen stores a `.vibegen/session.json` inside each generated project containing:
- Spec hash (SHA-256), project/package name, model/provider used
- Attempt count, last status, Claude session ID

This enables `--resume` to skip scaffold/generate and jump to the fix loop when the spec hasn't changed, and preserves the Claude session for continued multi-turn context.

---

## LLM Integration

### Supported Providers

| Provider | Model | Setup |
|----------|-------|-------|
| Claude | Claude Code CLI session | Claude Code installed and authenticated |
| Ollama | `qwen2.5-coder:14b` | Run `ollama serve`, then pull model |

### Prompt Templates

Located in `src/vibegen/prompts/`:

| File | Purpose |
|------|---------|
| `system.txt` | System context (loaded into every call) |
| `plan.txt` | Architecture planning |
| `generate_code.txt` | Source code generation |
| `write_tests.txt` | Test generation |
| `fix_errors.txt` | Test/lint failure fixing |
| `fix_tests.txt` | Legacy test fixing |
| `plan_tests.txt` | Test planning |

All templates use `{{key}}` placeholders for dynamic substitution.

---

## Key Design Decisions

### 1. Session-based Claude workflows
Multi-turn Claude Code sessions maintain full project context across planning, code generation, test generation, and fixing — enabling holistic improvements rather than isolated per-file fixes.

### 2. Template-based prompts
Prompts are Markdown/text files stored in the package, not hardcoded. Easy to iterate without code changes.

### 3. Delimiter-based file parsing
Use `--- file: path ---` for LLM responses because it works across models and handles narrative text gracefully.

### 4. Iterative test fixing with ruff pre-pass
Run `ruff --fix` before each LLM fix attempt to resolve formatting issues without spending an LLM call.

### 5. Dual provider support
Claude for production quality (session-based), Ollama for offline iteration (fast, local). Same interface via `--provider` flag.

### 6. Documentation section in specs
The `## Documentation` section in spec files supports HTML comments, markdown lists, and bare paths — referencing files or entire directories that get copied into the generated project's `docs/` folder for LLM context.

---

## Dependencies

### Core
- `requests` — HTTP client for Ollama API and web search

### Dev
- `ruff` — Linting and formatting
- `pytest` / `pytest-cov` — Testing and coverage
- `mypy` — Type checking
- `radon` — Complexity metrics
- `bandit` — Security checking
- `vulture` — Dead code detection
- `pip-audit` — Dependency vulnerability checking
