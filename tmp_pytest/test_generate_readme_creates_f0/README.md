# MyTool

A handy CLI tool.

## Installation

```bash
git clone https://github.com/<user>/mytool
cd mytool
uv sync
```

## Usage

Run `mytool --help`

## Development

```bash
uv run pytest              # run tests
uv run ruff check . --fix  # lint and auto-fix
uv run ruff format .       # format code
uv run mypy src/           # type check
```

## Project Structure

```
src/mytool/
  - (generated source files)
tests/
```

## License

MIT
