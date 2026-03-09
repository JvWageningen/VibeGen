# vibegen — Fully Automatic Python Project Generator (cross-platform)

Generate complete, tested Python projects from a plain-English specification,
then continue developing them with Claude Code in VS Code.

---

## Prerequisites

You need three things:

- **Git** — install from https://git-scm.com/downloads
- **Claude Code CLI** — install via the native installer (no Node.js required)
- **uv** — Python package and project manager (`pip install uv` or `uv install`)

> **Windows note:** Claude Code uses Git Bash internally, so a Git for Windows installation is recommended.

---

## Installation

### Recommended (pip / pipx)

From the repository root:

```bash
python -m pip install --upgrade pip
pip install .
```

If you use `pipx`:

```bash
pipx install .
```

This installs a cross-platform `vibegen` CLI that works on Windows, macOS, and Linux.

### Legacy (Windows PowerShell installer)

If you prefer the original PowerShell installer (Windows only):

1. Download all four files into a folder (e.g., `C:\Users\you\vibegen\`):
   - `setup-vibegen.ps1`
   - `vibegen.ps1`
   - `spec.example.md`
   - this README

2. Open PowerShell and run:

```powershell
cd C:\Users\you\vibegen
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
.\setup-vibegen.ps1
```

3. Restart your terminal. The `vibegen` command is now available globally.

---

## Usage: Generate a Project

```powershell
# 1. Copy the spec template
copy $env:USERPROFILE\.vibegen\templates\spec.template.md .\spec.md

# 2. Edit it with your requirements
code spec.md

# 3. Generate
vibegen spec.md

# 4. Open in VS Code and keep building
cd my-project
code .
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `-OutputDir <path>` | `.\<project-name>` | Where to create the project |
| `-MaxFixAttempts <n>` | `3` | How many test-fix iterations |
| `-MaxTurns <n>` | `30` | Max Claude agent turns per step |
| `-Model <model>` | `claude-sonnet-4-5-20250929` | Claude model |
| `-SkipPermissions` | off | Bypass safety prompts (containers only) |
| `-Verbose` | off | Show full Claude output |

### Examples

```powershell
# Basic
vibegen spec.md

# Custom output and more fix attempts
vibegen spec.md -OutputDir C:\projects\my-tool -MaxFixAttempts 5

# Use the strongest model for complex projects
vibegen spec.md -Model claude-opus-4-6

# See everything Claude does
vibegen spec.md -Verbose
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

```powershell
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

```powershell
uv run ruff check . --fix
uv run ruff format .
uv run pytest -x
uv run mypy src/
```

Or just type `/fix` in Claude Code and let it handle everything.

---

## Windows-Specific Notes

### Path separators

Python and uv handle forward slashes on Windows, so paths in `pyproject.toml`
and code will work fine. The `.vscode/settings.json` uses the Windows Python
path (`Scripts/python.exe` instead of `bin/python`).

### Line endings

The generated `.vscode/settings.json` sets `"files.eol": "\n"` so all Python
files use Unix-style line endings. This prevents issues with tools like Ruff
and pytest that expect `\n`.

### Claude Code and Git Bash

Claude Code on Windows uses Git Bash internally to run shell commands. This
means bash commands in Claude's output (like `&&` chains) work correctly.
You don't need to run PowerShell as Administrator.

### Python interpreter

The `.vscode/settings.json` points to `.venv/Scripts/python.exe` (the Windows
path). If VS Code can't find the interpreter, run `uv sync` once to recreate
the virtual environment, then reload the window (`Ctrl+Shift+P` → "Reload Window").

### Execution Policy

If PowerShell blocks the script with a red error, run this once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

This allows locally-created scripts to run while still blocking unsigned
scripts downloaded from the internet.

---

## Tips

**Iterate on your spec before generating.** A 10-minute investment in a
detailed spec saves an hour of post-generation fixes.

**Use `-Verbose` the first time.** Seeing Claude's full output helps you
understand what it's doing and spot issues early.

**Check the git log after generation.** Every step is a separate commit.
Run `git log --oneline` to see the history, `git diff HEAD~2` to review
recent changes, or `git reset --hard HEAD~1` to undo the last step.

**Update CLAUDE.md as you go.** When Claude makes a mistake during manual
development, add a rule to `CLAUDE.md` so it doesn't happen again. Press `#`
in Claude Code to quickly append a note.

**Use `/compact` in long sessions.** When the Claude Code context window fills
up, run `/compact Focus on the API changes` to summarize and free up space.
