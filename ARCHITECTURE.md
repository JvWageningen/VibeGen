# VibeGen Architecture

## Overview

VibeGen is a Python CLI tool that generates complete, production-quality Python projects from a plain-English specification using LLM providers (Claude or Ollama).

It works by orchestrating:
- **Spec parsing** — Extract project metadata from Markdown
- **Project scaffolding** — Initialize uv project with git and dependencies
- **LLM-driven generation** — Call Claude API or Ollama to write source code and tests
- **Iterative fixing** — Run tests, parse failures, re-prompt for fixes
- **Quality validation** — Format with ruff, type-check with mypy, check security with bandit

```
spec.md  →  vibegen create  →  LLM (Claude/Ollama)  →  Generated project
                |                      |
                |  (spec parsing)      |  (planning + code gen)
                |  project init        |  (test generation)
                |  template setup      |  (test fixing loop)
                |                      |
                +────────────────────────┐
                                         v
                              .venv/ + src/ + tests/
                              pyproject.toml configured
                              git history recorded
```

---

## Directory Structure

### Core CLI

```
src/vibegen/
├── __init__.py              Entry point
├── __main__.py              Script entry point
├── cli.py                   Main CLI logic (generate, create subcommands)
├── ollama_client.py         Ollama HTTP API wrapper
└── prompts/                 LLM prompt templates
    ├── system.txt           System prompt (context for LLM)
    ├── plan.txt             Planning phase prompt
    ├── generate_code.txt    Source code generation prompt
    ├── write_tests.txt      Test generation prompt
    └── fix_tests.txt        Test fixing prompt
```

### Generated Projects

```
<project-name>/
├── .venv/                   Virtual environment (uv-managed)
├── .vscode/
│   └── settings.json        Format-on-save, Ruff, Pylance strict
├── .pre-commit-config.yaml  Auto-runs ruff on commit
├── .gitignore + .gitattributes
├── CLAUDE.md                Project context for Claude Code (auto-generated)
├── README.md                Documentation (auto-generated from spec)
├── pyproject.toml           Dependencies + ruff/pytest/mypy config
├── uv.lock                  Locked dependencies
├── src/<package>/
│   ├── __init__.py
│   └── *.py                 Auto-generated modules
└── tests/
    ├── conftest.py
    └── test_*.py            Auto-generated tests
```

---

## Generation Pipeline

Triggered by: `vibegen create spec.md`

### Phase 1: Initialization (no LLM calls)

```
Step 1   Parse spec.md
         Extract: project name, package name, description, modules list
         
Step 2   uv init <package-name>
         Create virtual environment + pyproject.toml
         
Step 3   uv add <dependencies>
         Install base dependencies from spec
         
Step 4   git init
         Create .gitattributes, .gitignore
         Commit: "Initial scaffold"
         
Step 5   Setup .vscode/settings.json
         Configure Ruff, Pylance, format-on-save
         
Step 6   Generate CLAUDE.md
         Project context from spec (auto-generated, no LLM)
         
Step 7   Configure pyproject.toml
         Add ruff, pytest, mypy, bandit configuration
         
Step 8   Setup pre-commit hooks
         Install .pre-commit-config.yaml
         Commit: "Configuration complete"
```

### Phase 2: LLM-Driven Code Generation

#### Sub-phase 2a: Planning

```
Step 9   Planning prompt to LLM
         "Here's the spec. Plan the module structure:"
         LLM response: Architecture overview
         
         Commit: "Planning phase"
```

#### Sub-phase 2b: Source Code Generation

```
Step 10  Code generation prompt to LLM
         "Generate the source modules according to the plan"
         LLM response: Markdown with ```python code blocks
         
         Parse: Extract file:path and code blocks
         Write: Generate src/<package>/*.py files
         Format: ruff check --fix (auto-format)
         
         Commit: "Generated source code"
```

#### Sub-phase 2c: Test Generation

```
Step 11  Test generation prompt to LLM
         "Generate pytest tests for each module"
         LLM response: tests/*.py with test functions
         
         Parse: Extract test modules
         Write: Generate tests/test_*.py
         Format: ruff auto-fix
         
         Commit: "Generated tests"
```

### Phase 3: Iterative Test Fixing (up to max attempts)

```
Step 12  Run pytest
         Get failure output
         
         If all pass: Proceed to Step 14
         
         If failures exist and attempts remain:
           Step 12a  ruff --fix (auto-fix formatting/lint)
           Step 12b  Re-run pytest
           
           If still failing:
             Step 12c  Trim pytest output to relevant lines
             Step 12d  Send fix prompt to LLM with failures
             Step 12e  Parse LLM response, update test files
             Step 12f  ruff --fix again
             Step 12g  Commit: "Fix attempt N"
             Step 12h  Loop to Step 12 (max attempts configurable)
```

### Phase 4: Quality Checks (non-blocking, warnings only)

```
Step 13  Run diagnostic tools
         - ruff check       (lint)
         - mypy             (type checking)
         - bandit           (security)
         - radon cc         (complexity)
         
         Generate report (don't fail on warnings)
         Commit: "Quality checks complete"
```

### Phase 5: README Generation (no LLM call)

```
Step 14  Generate README.md from spec + generated structure
         Include: overview, installation, usage examples, dev guide
         
         Commit: "Documentation"
```

### Phase 6: Final Status

```
Step 15  Print summary
         - Project location
         - Modules created
         - Tests created
         - Pass/fail status
         - Quality warnings (if any)
         - Next steps (code ., test, etc.)
```

---

## LLM Integration

### Supported Providers

| Provider | Model | Setup |
|----------|-------|-------|
| Claude | `claude-sonnet-4-5-20250929` | `export ANTHROPIC_API_KEY="..."` |
| Ollama | `qwen2.5-coder:14b` | Run `ollama serve`, then pull model |

### API Calls

Three HTTP/CLI paths to invoke LLM:

1. **Claude API** — Direct HTTPS to Anthropic
2. **Ollama HTTP** — Local HTTP endpoint (default: http://localhost:11434)
3. **Claude CLI** — Shell subprocess (fallback, less preferred)

Code path: `_run_llm(prompt, model, provider)` in `cli.py`

### Prompt Templates

Located in `src/vibegen/prompts/`:

| File | Purpose | LLM Input |
|------|---------|-----------|
| `system.txt` | System context | Loaded into every call |
| `plan.txt` | Architecture planning | Loaded with spec + context |
| `generate_code.txt` | Source code generation | Spec + module list |
| `write_tests.txt` | Test generation | Generated code + spec |
| `fix_tests.txt` | Test failure fixing | Failure output + code |

All templates use `{...}` placeholders for dynamic substitution.

### File Format Parsing

**Input**: LLM response with Markdown code blocks

```
Some explanation...
--- file: src/package/module.py ---

```python
def my_func():
    pass
```

More explanation...
```

**Output**: Parsed into `Dict[str, str]` keyed by filepath

**Parser logic** in `_parse_generated_files()`:
- Look for `--- file: <path> ---` delimiters
- Extract code between ``` fences
- Stop parsing at closing fence (ignore narrative after)
- Clean markdown formatting

---

## Key Design Decisions

### 1. Template-based prompts

Prompts are Markdown files stored in the package, not hardcoded in Python. This allows:
- Easy iteration on prompt wording without code changes
- Same prompts reusable across CLI and VS Code
- Clear separation of LLM logic from project logic

### 2. Delimiter-based file parsing

Use `--- file: path ---` instead of JSON or structured output because:
- Works across multiple LLM models (Claude and Ollama)
- Handles narrative text gracefully (stop at closing ```)
- Natural to read in Markdown responses

### 3. Iterative test fixing with ruff pre-pass

Run `ruff --fix` before each Claude fix attempt because:
- Many test failures are pure formatting issues
- Auto-fix resolves them without spending an LLM call
- Reduces API usage

### 4. No "repair mode" in Python version

The initial Python version generates new projects only. Repair/improvement of existing
projects can be done manually with Claude Code in VS Code, or added later if needed.

### 5. LLM provider abstraction

Support both Claude and Ollama through the same interface (`_run_llm`):
- Users can switch providers per-run with `--provider` flag
- Ollama allows offline iteration (qwen2.5-coder is fast locally)
- Claude for production quality

---

## Dependencies

### Core Dependencies

- `requests` — HTTP client for Ollama API

### Dev Dependencies

- `ruff` — Linting and formatting (installed in every generated project)
- `pytest` — Test framework (installed in every generated project)
- `pytest-cov` — Code coverage (installed in every generated project)
- `mypy` — Type checking (installed in every generated project)
- `radon` — Complexity metrics (installed in every generated project)
- `bandit` — Security checking (optional in generated projects)

---

## Testing & Development

### Run Tests

```bash
uv run pytest
```

### Format & Lint

```bash
uv run ruff check . --fix
uv run ruff format .
```

### Type Check

```bash
uv run mypy src/
```

### Generate Test Project

```bash
vibegen create test-projects/spec-example-word-counter.md
cd word-counter
uv run pytest
```
