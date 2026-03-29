# vibegen

Cross-platform Python project generator powered by Claude Code.
Given a Markdown spec file describing your project, vibegen scaffolds
a complete Python package with source code, tests, CI, and Claude Code
integration — all generated via LLM.

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

## Usage

```bash
# Generate a project from a spec file
vibegen create spec.md

# Specify output directory
vibegen create spec.md --output ~/projects/my-app

# Use Ollama instead of Claude
vibegen create spec.md --provider ollama

# Run inside a Docker sandbox
vibegen create spec.md --sandbox

# Resume a previous run (skips scaffold if spec unchanged)
vibegen create spec.md --resume

# Control fix attempts and agent turns
vibegen create spec.md --max-fix-attempts 5 --max-turns 40
```

### Repair mode

Re-run generation on an existing project without re-scaffolding:

```bash
vibegen create spec.md --repair --output ./existing-project
```

## Spec Format

Specs are Markdown files with `## Sections`. See `examples/spec.md`
for a full template. Key sections:

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
├── cli.py                   CLI entry point
├── _analysis.py             Spec parsing, dependency graph, error context
├── _io.py                   Console output helpers, subprocess runner
├── _llm.py                  LLM dispatch (Claude sessions, Ollama, prompts)
├── _output_parser.py        Parse LLM responses into files
├── _pipeline.py             Code/test generation and fix loop
├── _plan.py                 Task planning
├── _scaffold.py             Project scaffolding and config generation
├── _session.py              Session persistence for --resume
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
