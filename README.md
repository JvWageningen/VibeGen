# vibegen — Fully Automatic Python Project Generator (cross-platform)

Generate complete, tested Python projects from a plain-English specification,
then continue developing them with Claude Code in VS Code.

---

## Prerequisites

You need three things:

- **Python 3.8+** — install from https://www.python.org/downloads
- **Git** — install from https://git-scm.com/downloads
- **uv** — Python package and project manager (`pip install uv`)

---

## Installation

Clone the repository and install:

```bash
git clone https://github.com/JvWageningen/VibeGen.git
cd VibeGen
python -m pip install --upgrade pip
pip install .
```

The `vibegen` command is now available globally on Windows, macOS, and Linux.

You'll also need an LLM provider:
- **Claude Code CLI** — install from https://console.anthropic.com/dashboard (for Claude models)
- **Ollama** — install from https://ollama.com (for open models like qwen2.5-coder:14b)

---

## Usage: Generate a Project

```bash
# 1. Create a project specification
echo '# My Project\n\n## Overview\nA command-line tool that...\n\n## Modules\n- module1: description\n- module2: description' > spec.md

# 2. Generate the project
vibegen create spec.md

# 3. Open in VS Code and continue developing
cd my-project
code .
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output <path>` | `./<project-name>` | Where to create the project |
| `--model <model>` | `claude-sonnet-4-5-20250929` | LLM model to use |
| `--provider <provider>` | `claude` | LLM provider: `claude` or `ollama` |
| `--verbose` | off | Show detailed output |

### Examples

```bash
# Basic usage
vibegen create spec.md

# Custom output directory
vibegen create spec.md --output ./projects/my-tool

# Use Ollama with local model
vibegen create spec.md --provider ollama --model qwen2.5-coder:14b

# See detailed generation progress
vibegen create spec.md --verbose
```

---

## Development (uv, ruff, pytest, mypy, radon)

Install dev dependencies:

```bash
uv add -d ruff pytest pytest-cov mypy radon
```

Run lint/format:

```bash
uv run ruff check . --fix
uv run ruff format .
```

Run tests:

```bash
uv run pytest
```

Run type checking:

```bash
uv run mypy src/
```

Run cyclomatic complexity report:

```bash
uv run radon cc src/ -mi C
```

---

## What Gets Generated

After vibegen finishes, your project looks like this:

```
my-project/
├── .claude/
│   └── commands/              ← Slash commands for manual workflow
│       ├── review.md          ← /review — full code review
│       ├── test.md            ← /test <module> — generate tests
│       ├── new-module.md      ← /new-module <name> — scaffold module + tests
│       ├── fix.md             ← /fix — run all checks and fix failures
│       └── refactor.md        ← /refactor <file> — improve structure
├── .vscode/
│   └── settings.json          ← Format-on-save, Ruff, Pylance strict
├── .pre-commit-config.yaml    ← Auto-runs ruff on every commit
├── CLAUDE.md                  ← Project context for Claude Code
├── README.md                  ← Auto-generated documentation
├── pyproject.toml             ← Dependencies + ruff/pytest/mypy config
├── uv.lock
├── src/
│   └── my_project/
│       ├── __init__.py
│       └── ...                ← Your modules (generated from spec)
└── tests/
    ├── conftest.py
    └── test_*.py              ← One test file per source module
```

Everything is already configured for both fully automatic (vibegen) and
semi-automatic (VS Code + Claude Code) workflows.

---

## After Generation: The Hybrid Workflow

This is where the two workflows merge. After vibegen creates the project,
you open it in VS Code and switch to the semi-automatic workflow.

### Open the project

```bash
cd my-project
code .
```

Claude Code automatically reads `CLAUDE.md` when you open the sidebar — it
already knows your project's structure, conventions, and commands.

### Use slash commands for common tasks

In the Claude Code sidebar, type:

- `/review` — full code review with lint, test, and type check
- `/test api` — generate tests for `src/my_project/api.py`
- `/new-module cache` — create `cache.py` with stubs + matching test file
- `/fix` — run all checks and fix every failure automatically
- `/refactor services/api.py` — improve structure of a specific file

### Let Claude handle big changes

Describe what you want in natural language:

> "Add a caching layer that stores API responses in a local SQLite database.
> Cache entries should expire after 1 hour. Add a --no-cache flag to bypass it."

Claude will plan the changes, show inline diffs, and wait for your approval.
Use **Plan Mode** (toggle in the Claude panel) for complex changes — Claude
shows the full plan before touching any code.

### Write code yourself when you prefer

Just edit files normally. On save, Ruff auto-formats and fixes imports.
Claude is available in the sidebar for questions:

- Select code → `Alt+K` → "What's the time complexity of this?"
- "Why does this test fail when I pass an empty list?"
- "What's the best way to handle this edge case?"

### Before committing

The pre-commit hooks run Ruff automatically on `git commit`. For the full check:

```bash
uv run ruff check . --fix
uv run ruff format .
uv run pytest -x
uv run mypy src/
```

Or just type `/fix` in Claude Code and let it handle everything.

---

## Platform Notes

### Python Interpreter

The generated `.vscode/settings.json` points to the local virtual environment Python
interpreter. If VS Code can't find it, run `uv sync` to recreate the `.venv`
directory and reload VS Code (`Ctrl+Shift+P` → "Reload Window").

### Line Endings

The generated `.vscode/settings.json` sets `"files.eol": "\n"` to ensure
Unix-style line endings across all platforms. This prevents compatibility issues
with linting and testing tools.

### LLM Provider Setup

**For Claude models:**
```bash
export ANTHROPIC_API_KEY="your-api-key"
```

**For Ollama models:**
```bash
# Make sure Ollama is running
ollama pull qwen2.5-coder:14b
```

---

## Tips

**Write a detailed specification.** A clear, well-structured spec with concrete examples improves code quality. Include:
- Overview of what the tool does
- List of modules and their responsibilities
- Key functions/classes for each module
- Any external dependencies or APIs
- Example usage or typical workflows

**Use `--verbose` for debugging.** If generated code has issues, run with `--verbose` to see full LLM responses and understand what went wrong.

**Review generated code immediately.** Open the project and skim generated files right after creation. Fix obvious issues in the spec for the next run.

**Build iteratively.** Start with a simple spec, generate, review the output, then refine the spec and regenerate. This is much faster than trying to get the spec perfect on the first try.

**Check the git history.** Every generation step creates a commit:
```bash
git log --oneline
git diff HEAD~5  # Review last 5 steps
git reset --hard HEAD~1  # Undo if needed
```

**Update CLAUDE.md during manual development.** When fixing bugs or adding features manually, update `CLAUDE.md` with project-specific rules so Claude Code follows your conventions in future edits.

**Mix LLM providers.** Use Ollama for fast iteration and Claude for complex problems. Just change the `--provider` and `--model` flags between runs.
