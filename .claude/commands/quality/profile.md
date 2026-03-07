Identify performance bottlenecks in: $ARGUMENTS

1. Run: `uv run radon cc $ARGUMENTS -mi B` to get cyclomatic complexity (grade B+ = CC >= 6); high-complexity functions are prime candidates
2. Read the module; identify: nested loops on large data, repeated computations in hot paths, unnecessary object copies, blocking I/O in async contexts, missing caching opportunities
3. Suggest specific optimizations with code examples: functools.cache, generators, bulk operations, lazy evaluation
4. If measurable, write a benchmark using timeit or pytest-benchmark to quantify the improvement
