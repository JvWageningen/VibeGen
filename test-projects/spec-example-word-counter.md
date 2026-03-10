# Project Spec

## Name
word-counter

## Description
A CLI tool that reads a text file and reports word frequency statistics:
total words, unique words, and the top N most common words.

## Python Version
3.12

## Input

- Path to a text file (CLI argument)
- Optional: `--top N` number of most common words to show (default: 10)
- Optional: `--ignore-case` flag to treat "Word" and "word" as the same

## Output

- Printed table: rank, word, count, percentage of total
- Summary line: total words, unique words
- Exit code 0 on success, 1 on file-not-found

## Requirements

- Read and parse plain text files
- Count word frequencies (strip punctuation, split on whitespace)
- Sort by frequency descending, then alphabetically for ties
- CLI interface built with Typer
- Structured logging with loguru
- All data models use Pydantic for validation

## Dependencies
typer, loguru, pydantic

## Example Usage
```bash
# Count words in a file
word-counter report notes.txt

# Show top 5 words, case-insensitive
word-counter report notes.txt --top 5 --ignore-case
```

## Edge Cases

- Empty file should print "No words found" and exit 0
- File not found should print a clear error and exit 1
- Words with only punctuation (e.g. "---") should be excluded
- Very large files (>10MB) should stream line by line, not load all at once

## Documentation
<!-- Optional: put paths to reference docs, API specs, or examples here -->
<!-- These files will be fed to Claude as additional context -->
