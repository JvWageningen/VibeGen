think

## Scope
Map all dependencies for: $ARGUMENTS
Do NOT modify any code.

## Anchor
Run `cymbal importers $ARGUMENTS` and `cymbal investigate $ARGUMENTS`. Fallback: read the module, trace imports manually.

## Outcome
| Source Module | Target Module | Import Type | Symbols Used |
|---------------|---------------|-------------|--------------|
| vibegen/_pipeline.py | vibegen/_llm.py | direct | _run_claude, _load_prompt_template |

Import Type: direct / transitive / conditional
Also note: external packages used and key data flows.
