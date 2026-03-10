# vibegen

Cross-platform Python project generator powered by Claude Code.

## Installation

```bash
git clone https://github.com/<user>/vibegen
cd vibegen
uv sync
```

## Usage

See the documentation for usage details.

## Development

```bash
uv run pytest              # run tests
uv run ruff check . --fix  # lint and auto-fix
uv run ruff format .       # format code
uv run mypy src/           # type check
```

## Project Structure

```
src/vibegen/
  - `vibegen\__main__.py`
  - `vibegen\_analysis.py`
  - `vibegen\_io.py`
  - `vibegen\_llm.py`
  - `vibegen\_output_parser.py`
  - `vibegen\_pipeline.py`
  - `vibegen\_plan.py`
  - `vibegen\_scaffold.py`
  - `vibegen\_session.py`
  - `vibegen\cli.py`
  - `vibegen\ollama_client.py`
  - `vibegen\sandbox.py`
  - `vibegen\web_search.py`
tests/
```

## License

MIT
