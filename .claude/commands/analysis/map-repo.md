think

## Scope
Generate an architecture overview of the repository.
Do NOT modify any code.

## Anchor
Run `cymbal structure` for entry points, hotspots, central packages. Read CLAUDE.md, README.md, docs/reference/.

## Outcome
Produce structured markdown with these sections:

- **Module List**: each file under src/ with a one-line purpose
- **Dependency Graph**: which modules import which (ascii or markdown)
- **Data Flow**: how data moves through the system (input → processing → output)
- **Entry Points / Public API**: CLI commands and importable public symbols
- **Key Design Patterns**: recurring patterns (e.g. plugin system, pipeline, factory)
