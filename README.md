# vibegen

Cross-platform Python project generator powered by Claude Code.
Describe your project in plain English or a Markdown spec — vibegen
scaffolds a complete Python package with source code, tests, CI, and
Claude Code integration, all generated via LLM.

## Installation

```bash
git clone https://github.com/<user>/vibegen
cd vibegen
uv sync
```

To make the `vibegen` command available globally, add the venv to your PATH:

```bash
export PATH="$(pwd)/.venv/bin:$PATH"
```

## Commands

### `vibegen design` — Interactive project design

Describe your idea and Claude asks targeted questions until it has
enough information to generate a complete spec. The same Claude session
carries over into project generation for full context continuity.

```bash
# Provide a description upfront
vibegen design --description "A CLI tool that counts word frequencies"

# Or get prompted interactively
vibegen design

# Generate the spec only (review before generating)
vibegen design --description "A REST API for bookmarks" --spec-only
```

### `vibegen <spec.md>` — Generate from spec

```bash
# Generate a project from a spec file
vibegen spec.md

# Specify output directory
vibegen spec.md --output ~/projects/my-app

# Use Ollama instead of Claude
vibegen spec.md --provider ollama

# Run inside a Docker sandbox
vibegen spec.md --sandbox

# Resume a previous run (skips scaffold if spec unchanged)
vibegen spec.md --resume

# Control fix attempts and agent turns
vibegen spec.md --max-fix-attempts 5 --max-turns 40
```

### `vibegen init` — Initialize tooling

Set up VibeGen dev tooling (ruff, pytest, mypy, CLAUDE.md, CI, etc.)
on any existing Python project — no spec file needed. Merges into
existing config files rather than overwriting. Uses Claude to
intelligently update the README.

```bash
vibegen init ./my-existing-project
```

### `vibegen improve` — Iterative improvement

Run a Claude-driven improvement loop on an existing project with a
web dashboard for monitoring and control.

```bash
# Fix all tests and improve coverage
vibegen improve ./my-project --task "fix all failing tests"

# With iteration limit and auto-merge
vibegen improve ./my-project --task "improve type coverage" \
  --max-iterations 10 --auto-merge

# Polling mode (wait for external process)
vibegen improve ./my-project --task "optimize performance" \
  --mode polling --poll-flag ./done.flag
```

The web dashboard runs at `http://localhost:8089` with charts,
iteration history, log viewer, and pause/resume/stop/merge controls.

### Repair mode

Re-run scaffold + generation on an existing project:

```bash
vibegen spec.md --repair --output ./existing-project
```

## Spec Format

Specs are Markdown files with `## Sections`. Use `vibegen design` to
generate one interactively, or write it manually.
See `examples/spec.md` for a full template. Key sections:

- **Name** — project name (used for directory and package)
- **Description** — what the project does
- **Python Version** — target Python version (default: 3.12)
- **Input / Output** — what goes in, what comes out
- **Requirements** — specific behavioral requirements
- **Dependencies** — comma-separated pip package names
- **Example Usage** — concrete CLI/API examples
- **Edge Cases** — error handling expectations
- **Documentation** — paths to reference docs (files or directories)
  copied into the generated project for LLM context

## Project Structure

```
src/vibegen/
├── cli.py                   CLI entry point (design, init, improve, create)
├── _design.py               Interactive spec generation via Claude Q&A
├── _analysis.py             Spec parsing, dependency graph, error context
├── _io.py                   Console output helpers, subprocess runner
├── _llm.py                  LLM dispatch (Claude sessions, Ollama, prompts)
├── _output_parser.py        Parse LLM responses into files
├── _pipeline.py             Code/test generation and fix loop
├── _plan.py                 Task planning
├── _scaffold.py             Project scaffolding and config generation
├── _session.py              Session persistence for --resume
├── _improve_loop.py         Iterative improvement engine
├── _improve_state.py        Improvement loop state management
├── _improve_metrics.py      Verification runner (pytest, ruff, mypy)
├── _improve_webui.py        Web dashboard for improvement loop
├── ollama_client.py         Ollama HTTP API wrapper
├── sandbox.py               Docker sandbox support
├── web_search.py            Web search for error context
├── prompts/                 LLM prompt templates
└── templates/               Claude command templates for generated projects
```

## Development

```bash
uv run pytest              # run tests
uv run ruff check . --fix  # lint and auto-fix
uv run ruff format .       # format code
uv run mypy src/           # type check
uv run bandit -r src/      # security check
uv run vulture src/        # dead code detection
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | API key for Claude (when not using CLI) |
| `OLLAMA_HOST` | Ollama server URL (default: `http://localhost:11434`) |

## License

MIT
