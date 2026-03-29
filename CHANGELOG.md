# Changelog

All notable changes to VibeGen will be documented in this file.

## [0.2.0] - 2026-03-29

### Added

- **Claude Code session-based generation**: Single continuous Claude session
  across planning, code generation, test generation, error fixing, and
  spec review. All phases share context for higher quality output.
- **Scaffold `.claude/settings.local.json`**: Generated projects include
  Claude Code permissions (allow/deny/ask rules) out of the box.
- **Scaffold `.claude/commands/`**: 43 pre-built slash-command templates
  (analysis, docs, feature, quality, test) bundled as package data.
- **Scaffold `tests/conftest.py`**: Minimal shared fixtures generated
  for new projects.
- **Scaffold `.github/workflows/ci.yml`**: GitHub Actions CI workflow
  running ruff, pytest, and mypy on push/PR.
- **Automatic versioning**: `scripts/release.py` bumps semver, updates
  `pyproject.toml`, `VERSION`, `__init__.py`, and generates SHA-256
  manifest in `versions/`.
- **CI/CD version bump**: `.github/workflows/version-bump.yml` auto-bumps
  on push to main. Commit message flags `[major]`, `[minor]`, `[patch]`
  override auto-detection.
- **Repair with generation**: `vibegen --repair` can now accept a spec
  file to run the full code generation pipeline after re-applying scaffold
  files.
- **High-effort mode**: Claude sessions use `--effort high` for thorough
  implementation.

### Changed

- **Claude provider uses `acceptEdits` permission mode**: Claude writes
  files directly via its own tools instead of outputting text for parsing.
- **Output parser handles unfenced code**: `_clean_file_content` now keeps
  raw code when no markdown fences are present (Ollama fallback).
- **Prompts tell Claude to extend scaffold files**: Instead of ignoring
  scaffold files, Claude is told they exist and can be added to.
- **Code generation retries** (Ollama path): Up to 3 attempts when the
  LLM doesn't return parseable file blocks.

### Fixed

- **Windows charmap encoding error**: Added `encoding="utf-8"` to all
  `subprocess.run` calls and `sys.stdout.reconfigure(encoding="utf-8")`
  at CLI startup.
- **Dev dependencies**: Added `bandit`, `vulture`, `pip-audit` to
  `pyproject.toml` (referenced in CLAUDE.md but previously missing).

## [0.1.0] - 2026-03-18

### Added

- Initial release of VibeGen as a Python CLI tool.
- Spec-driven project generation from markdown files.
- Multi-provider LLM support: Claude CLI and Ollama.
- Automated project scaffolding with `uv init`.
- Generated project files: CLAUDE.md, .vscode/settings.json, .gitignore,
  .gitattributes, .pre-commit-config.yaml, pyproject.toml tool configs.
- Task planning with progress tracking.
- Session persistence for resumable generation.
- Multi-provider web search for error context enrichment.
- Spec compliance reviewer pass.
- Docker sandbox support for isolated execution.
- Test generation with iterative fix loop (up to N attempts).
- README generation from spec.
