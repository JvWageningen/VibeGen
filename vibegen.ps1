# vibegen.ps1 — Fully automatic Python project generator powered by Claude Code (Windows)
#
# Usage: vibegen.ps1 <spec-file> [--output-dir <path>] [--max-fix-attempts <n>] [--skip-permissions]

param(
    [Parameter(Position=0)]
    [string]$SpecFile,

    [string]$OutputDir = "",

    [switch]$Repair,

    [string]$RepoPath = "",

    [int]$MaxFixAttempts = 3,

    [int]$MaxTurns = 30,

    [string]$Model = "claude-sonnet-4-5-20250929",

    [switch]$SkipPermissions,

    [switch]$ShowOutput,

    [switch]$Help
)

$ErrorActionPreference = "Stop"

# ── Helpers ───────────────────────────────────────────────────────────────────
function Write-Step  ($msg) { Write-Host "[STEP]  $msg" -ForegroundColor Blue }
function Write-Ok    ($msg) { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Warn  ($msg) { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Write-Err   ($msg) { Write-Host "[ERR]   $msg" -ForegroundColor Red }
function Write-Info  ($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }

# ── Install-ClaudeFiles helper ──────────────────────────────────────────────
function Install-ClaudeFiles {
    param([string]$PkgName)
    $vibegenDir = Join-Path $env:USERPROFILE ".vibegen"
    $commandsSrc = Join-Path $vibegenDir "commands"
    $settingsSrc = Join-Path $vibegenDir "settings.local.json"

    New-Item -ItemType Directory -Force -Path ".claude\commands" | Out-Null

    if (-not (Test-Path $commandsSrc)) {
        Write-Warn "Vibegen commands not found at $commandsSrc. Run setup-vibegen.ps1 first."
        return
    }

    Get-ChildItem $commandsSrc -Recurse -Filter "*.md" | ForEach-Object {
        $relPath = $_.FullName.Substring($commandsSrc.Length + 1)
        $destPath = ".claude\commands\$relPath"
        New-Item -ItemType Directory -Force -Path (Split-Path $destPath) | Out-Null
        $content = Get-Content $_.FullName -Raw -Encoding UTF8
        if ($_.Name -eq "new-module.md") {
            $content = $content -replace '{{PACKAGE_NAME}}', $PkgName
        }
        $content | Set-Content $destPath -Encoding UTF8
    }

    if (Test-Path $settingsSrc) {
        Copy-Item $settingsSrc ".claude\settings.local.json" -Force
    }
}

# ── Help ──────────────────────────────────────────────────────────────────────
if ($Help -or $SpecFile -eq '--help' -or $SpecFile -eq '-help' -or ([string]::IsNullOrEmpty($SpecFile) -and -not $Repair)) {
    Write-Host @"

vibegen.ps1 - Generate or repair Python projects powered by Claude Code

GENERATE MODE  (create a new project from a spec)
    vibegen.ps1 <spec-file> [OPTIONS]

REPAIR MODE  (improve an existing repo's structure, tests, and code quality)
    vibegen.ps1 -Repair [-RepoPath <path>]

GENERATE OPTIONS:
    -OutputDir <path>         Where to create the project (default: .\<project-name>)
    -MaxFixAttempts <n>       Max test-fix iterations (default: 3)
    -MaxTurns <n>             Max Claude agent turns per step (default: 30)
    -Model <model>            Claude model to use (default: claude-sonnet-4-5-20250929)
    -SkipPermissions          Use --dangerously-skip-permissions (containers only!)
    -ShowOutput               Show full Claude output
    -Help                     Show this help

REPAIR OPTIONS:
    -RepoPath <path>          Path to the repo to repair (default: current directory)
    -MaxFixAttempts <n>       Max test-fix iterations (default: 3)
    -MaxTurns <n>             Max Claude agent turns per step (default: 30)
    -Model <model>            Claude model to use
    -ShowOutput               Show full Claude output

EXAMPLES:
    vibegen.ps1 spec.md
    vibegen.ps1 spec.md -OutputDir C:\projects\my-tool -MaxFixAttempts 5
    vibegen.ps1 spec.md -Model claude-opus-4-6
    vibegen.ps1 -Repair
    vibegen.ps1 -Repair -RepoPath C:\projects\my-tool

"@
    exit 0
}

if ($Repair -and -not [string]::IsNullOrEmpty($SpecFile) -and [string]::IsNullOrEmpty($RepoPath)) {
    $RepoPath = $SpecFile
    $SpecFile = ""
}

if (-not $Repair) {
    if (-not (Test-Path $SpecFile)) {
        Write-Err "Spec file not found: $SpecFile"
        exit 1
    }
    # Resolve to absolute path now, before any Set-Location changes the working directory
    $SpecFile = (Resolve-Path $SpecFile).Path
}

# ── Preflight checks ─────────────────────────────────────────────────────────
Write-Step "Running preflight checks..."

foreach ($cmd in @("claude", "uv", "git")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Err "'$cmd' is not installed or not in PATH. Run setup-vibegen.ps1 first."
        exit 1
    }
}
Write-Ok "All required tools found (claude, uv, git)"

# ── Parse spec ────────────────────────────────────────────────────────────────
if (-not $Repair) {
Write-Step "Parsing spec file: $SpecFile"

$specContent = Get-Content $SpecFile -Raw -Encoding UTF8
$specLines = Get-Content $SpecFile -Encoding UTF8

# Extract project name from ## Name section
$projectName = ""
$inName = $false
foreach ($line in $specLines) {
    if ($line -match "^## Name") { $inName = $true; continue }
    if ($inName -and $line -match "^## ") { break }
    if ($inName -and $line.Trim() -ne "") {
        $projectName = $line.Trim()
        break
    }
}

if ([string]::IsNullOrEmpty($projectName)) {
    Write-Err "Could not find '## Name' section in spec file."
    exit 1
}

# Convert to valid Python package name
$packageName = $projectName.ToLower() -replace '-', '_'

# Extract Python version (default 3.12)
$pythonVersion = "3.12"
$inPyVer = $false
foreach ($line in $specLines) {
    if ($line -match "^## Python Version") { $inPyVer = $true; continue }
    if ($inPyVer -and $line -match "^## ") { break }
    if ($inPyVer -and $line.Trim() -ne "") {
        $pythonVersion = $line.Trim()
        break
    }
}

# Extract dependencies
$dependencies = ""
$inDeps = $false
foreach ($line in $specLines) {
    if ($line -match "^## Dependencies") { $inDeps = $true; continue }
    if ($inDeps -and $line -match "^## ") { break }
    if ($inDeps -and $line.Trim() -ne "") {
        $dependencies = $line.Trim()
        break
    }
}

# Extract documentation file paths
$docFiles = @()
foreach ($line in $specLines) {
    if ($line -match '<!-- (docs/[^\s]+) -->') {
        $docFiles += $Matches[1]
    }
}

# Extract Usage/Examples section for README
$usageSection = ""
$inUsage = $false
foreach ($line in $specLines) {
    if ($line -match "^## (Usage|Examples|CLI|Interface|API)") { $inUsage = $true; continue }
    if ($inUsage -and $line -match "^## ") { break }
    if ($inUsage) { $usageSection += $line + "`n" }
}
$usageSection = $usageSection.TrimEnd()
if ([string]::IsNullOrEmpty($usageSection)) {
    $usageSection = "See ``src/$packageName/`` for the public API."
}

if ([string]::IsNullOrEmpty($OutputDir)) {
    $OutputDir = Join-Path "." $projectName
}

Write-Ok "Project: $projectName (package: $packageName)"
Write-Ok "Python:  $pythonVersion"
Write-Ok "Output:  $OutputDir"
}

# ── Build permission flags ────────────────────────────────────────────────────
$permFlags = @()
if ($SkipPermissions) {
    $permFlags = @("--dangerously-skip-permissions")
    Write-Warn "Running with --dangerously-skip-permissions (all safety checks bypassed)"
} else {
    $permFlags = @("--allowedTools", "Read", "Write", "Edit", "Bash", "Glob", "Grep")
    Write-Info "Running with explicit tool permissions"
}

# Trim pytest output to relevant failure lines only (reduces Claude input tokens)
function Get-TestFailureSummary {
    param([string]$Output)
    $lines = $Output -split "`n"
    $relevant = $lines | Where-Object {
        $_ -match "FAILED|ERROR|error:|AssertionError|Exception|Traceback|short test summary|_ ERROR|collected|passed|failed"
    }
    if ($relevant.Count -eq 0) { return ($lines | Select-Object -First 60) -join "`n" }
    return ($relevant | Select-Object -First 80) -join "`n"
}

# Helper function to call claude non-interactively
function Invoke-Claude {
    param(
        [Parameter(Mandatory)][string]$Prompt,
        [string]$Label = "Claude"
    )

    $allArgs = @("-p", "--model", $Model, "--max-turns", $MaxTurns) + $permFlags

    if ($ShowOutput) {
        $Prompt | & claude @allArgs 2>&1 | Tee-Object -Variable claudeOutput
        return ($claudeOutput -join "`n")
    } else {
        $output = $Prompt | & claude @allArgs 2>&1
        return ($output -join "`n")
    }
}

# ── Repair mode ──────────────────────────────────────────────────────────────
if ($Repair) {
    if (-not [string]::IsNullOrEmpty($RepoPath)) {
        if (-not (Test-Path $RepoPath)) {
            Write-Err "Repo path not found: $RepoPath"
            exit 1
        }
        Set-Location $RepoPath
    }
    Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue

    $repoLocation = (Get-Location).Path
    Write-Step "Repairing repo: $repoLocation"

    # ── Repair Step 1: Install/update slash commands and settings ──────────────
    Write-Info "Installing Claude Code slash commands and settings..."

    # Detect package name from pyproject.toml for command templates
    $repairPackageName = ""
    if (Test-Path "pyproject.toml") {
        $pt = Get-Content "pyproject.toml" -Raw -Encoding UTF8
        if ($pt -match 'name\s*=\s*"([^"]+)"') {
            $repairPackageName = $Matches[1] -replace '-', '_'
        }
    }
    if ([string]::IsNullOrEmpty($repairPackageName)) { $repairPackageName = "src" }

    Install-ClaudeFiles -PkgName $repairPackageName
    Write-Ok "Slash commands and settings installed"

    # ── Repair Step 2: Improve structure ─────────────────────────────────────
    Write-Step "Phase 1/3 - Improving project structure..."

    # Pre-run tools to collect current findings — Claude gets them as context, skipping discovery turns
    $ErrorActionPreference = "SilentlyContinue"
    $null = & uv run ruff check . --fix 2>&1   # auto-fix what ruff can handle immediately
    $null = & uv run ruff format . 2>&1
    $ruffViolations = & uv run ruff check . --output-format=concise 2>&1 | Out-String
    $radonFindings   = & uv run radon cc src/ -mi C 2>&1 | Out-String          # grade C+ (CC >= 11)
    $vultureFindings = & uv run vulture src/ --min-confidence 80 2>&1 | Out-String
    $ErrorActionPreference = "Stop"

    $ruffContext = if ($ruffViolations.Trim()) {
        "`n`nRemaining ruff violations after auto-fix (these need manual fixes):`n``````$ruffViolations``````"
    } else { "" }
    $radonContext = if ($radonFindings.Trim()) {
        "`n`nHigh-complexity functions (grade C+, CC >= 11) — extract helpers or simplify:`n``````$radonFindings``````"
    } else { "" }
    $vultureContext = if ($vultureFindings.Trim()) {
        "`n`nUnused code detected by vulture (>= 80% confidence) — remove if truly dead:`n``````$vultureFindings``````"
    } else { "" }

    $repairStructurePrompt = @"
You are improving the structure and code quality of an existing Python project.
Ruff has already been run with --fix. Focus on issues ruff cannot fix automatically.$ruffContext$radonContext$vultureContext

INSTRUCTIONS:
1. Read pyproject.toml and list all source files in src/.
2. Fix structural issues ruff cannot handle:
   - Missing or empty __init__.py files (add proper exports)
   - Missing type hints on function signatures
   - Missing Google-style docstrings on public functions and classes
   - print() statements (replace with loguru logger)
   - Bare except: clauses (replace with specific exception types)
   - Mutable default arguments (replace with None + guard pattern)
   - Functions longer than 30 lines (extract helpers)
   - Deep nesting (replace with early returns)
3. After making changes: run uv run ruff check . --fix && uv run ruff format .
4. Do NOT remove any existing functionality.
5. Report a summary of what was changed.
"@

    $claudeOutput = Invoke-Claude -Prompt $repairStructurePrompt -Label "repair-structure"
    & git add -A
    & git commit -q -m "refactor: vibegen structure and code quality improvements" --allow-empty
    Write-Ok "Phase 1 complete"

    # ── Repair Step 3: Improve tests ─────────────────────────────────────────
    Write-Step "Phase 2/3 - Improving test coverage..."

    $repairTestsPrompt = @"
You are improving the test suite of an existing Python project.

INSTRUCTIONS:
1. Read ALL source files in src/ to understand the full public API.
2. Read existing test files in tests/ to understand what is already tested.
3. Identify coverage gaps:
   - Public functions and methods not tested at all
   - Edge cases not covered (empty input, None, boundary values, negative numbers)
   - Error handling paths not tested
4. Add missing tests:
   - Add to existing test files if the module already has tests
   - Create new test_<module>.py files for untested modules
   - Ensure tests/conftest.py exists with shared fixtures
5. Always use specific exception types in pytest.raises() - never bare Exception or BaseException.
6. Run: uv run ruff check tests/ --fix && uv run ruff format tests/
7. Run: uv run pytest -x --tb=short and report results.
"@

    $claudeOutput = Invoke-Claude -Prompt $repairTestsPrompt -Label "repair-tests"
    & git add -A
    & git commit -q -m "test: vibegen test coverage improvements" --allow-empty
    Write-Ok "Phase 2 complete"

    # ── Repair Step 4: Test fix loop ──────────────────────────────────────────
    Write-Step "Running tests and fixing failures (up to $MaxFixAttempts attempts)..."

    for ($attempt = 1; $attempt -le $MaxFixAttempts; $attempt++) {
        Write-Info "Test attempt $attempt/$MaxFixAttempts"

        $ErrorActionPreference = "SilentlyContinue"
        $testOutput = & uv run pytest -x --tb=short 2>&1 | Out-String
        $ErrorActionPreference = "Stop"
        $testPassed = ($testOutput -match "passed") -and ($testOutput -notmatch "failed|error|ERROR")

        if ($testPassed) {
            Write-Ok "All tests passing!"
            ($testOutput -split "`n") | Select-Object -Last 5 | ForEach-Object { Write-Host $_ }
            break
        }

        if ($attempt -ge $MaxFixAttempts) {
            Write-Warn "Max fix attempts reached. Some tests may still be failing."
            ($testOutput -split "`n") | Select-Object -Last 20 | ForEach-Object { Write-Host $_ }
            break
        }

        # Pre-run ruff — may resolve failures without a Claude call
        $ErrorActionPreference = "SilentlyContinue"
        $null = & uv run ruff check . --fix 2>&1
        $null = & uv run ruff format . 2>&1
        $ruffTestOutput = & uv run pytest -x --tb=short 2>&1 | Out-String
        $ErrorActionPreference = "Stop"

        if (($ruffTestOutput -match "passed") -and ($ruffTestOutput -notmatch "failed|error|ERROR")) {
            Write-Ok "Ruff auto-fix resolved failures (attempt $attempt)"
            & git add -A
            & git commit -q -m "fix: ruff auto-fix resolved test failures" --allow-empty
            break
        }
        $testOutput = $ruffTestOutput

        Write-Warn "Tests failing. Asking Claude to fix (attempt $attempt)..."

        $fixSummary = Get-TestFailureSummary $testOutput
        $fixPrompt = @"
The tests are failing. Here is the pytest output:

``````
$fixSummary
``````

INSTRUCTIONS:
1. Read the failing test files AND the source files they test.
2. Determine if the bug is in the source code or the test code.
3. Fix the actual bugs - do NOT weaken assertions to make tests pass.
4. Run: uv run ruff check . --fix && uv run ruff format .
5. Run: uv run pytest -x --tb=short
6. Report the results.
"@

        $claudeOutput = Invoke-Claude -Prompt $fixPrompt -Label "repair-fix-$attempt"
        & git add -A
        & git commit -q -m "fix: repair test failures (attempt $attempt)" --allow-empty
    }

    # ── Repair Step 5: Final code quality pass ────────────────────────────────
    Write-Step "Phase 3/3 - Final code quality pass..."

    # Pre-run tools and inject actual output so Claude skips discovery turns
    $ErrorActionPreference = "SilentlyContinue"
    $null = & uv run ruff check . --fix 2>&1
    $null = & uv run ruff format . 2>&1
    $finalRuffIssues  = & uv run ruff check . --output-format=concise 2>&1 | Out-String
    $finalMypyOutput  = & uv run mypy src/ 2>&1 | Out-String
    $finalBanditOutput = & uv run bandit -c pyproject.toml -r src/ -f txt 2>&1 | Out-String
    $finalAuditOutput  = & uv run pip-audit 2>&1 | Out-String
    $ErrorActionPreference = "Stop"

    $finalRuffCtx = if ($finalRuffIssues.Trim()) {
        "`n`nRemaining ruff issues:`n``````$finalRuffIssues``````"
    } else { "`n`nRuff: no remaining issues." }

    $finalMypyCtx = if ($finalMypyOutput -match "error:") {
        "`n`nMypy type errors:`n``````$finalMypyOutput``````"
    } else { "`n`nMypy: no type errors." }

    $finalBanditCtx = if ($finalBanditOutput -match "Severity: (Medium|High)") {
        "`n`nBandit security findings (fix Medium/High severity):`n``````$finalBanditOutput``````"
    } else { "`n`nBandit: no medium/high security issues." }

    $finalAuditCtx = if ($finalAuditOutput -match "vulnerability|GHSA|CVE") {
        "`n`nDependency vulnerabilities (run 'uv add <pkg>@latest' to fix):`n``````$finalAuditOutput``````"
    } else { "" }

    $repairCodePrompt = @"
You are doing a final code quality pass on an existing Python project.
Ruff, mypy, bandit, and pip-audit have already been run. Here are the current findings:
$finalRuffCtx
$finalMypyCtx
$finalBanditCtx
$finalAuditCtx

INSTRUCTIONS:
1. Read source files in src/ that have reported issues above.
2. Fix remaining issues:
   - Add missing type hints to function signatures
   - Add missing Google-style docstrings to public APIs
   - Replace any remaining print() with loguru
   - Replace any remaining bare except: with specific exception types
   - Fix mypy type errors shown above
   - Fix bandit security issues shown above (Medium/High severity)
   - For vulnerable dependencies: run uv add <package>@latest to upgrade
   - Simplify any remaining complex functions (>30 lines, deep nesting)
3. Run: uv run ruff check . --fix && uv run ruff format .
4. Run: uv run pytest -x --tb=short to confirm tests still pass.
5. Report a summary of changes made.
"@

    $claudeOutput = Invoke-Claude -Prompt $repairCodePrompt -Label "repair-code"

    $ErrorActionPreference = "SilentlyContinue"
    $null = & uv run ruff check . --fix 2>&1
    $null = & uv run ruff format . 2>&1
    $ErrorActionPreference = "Stop"

    & git add -A
    & git commit -q -m "chore: vibegen final quality pass" --allow-empty
    Write-Ok "Phase 3 complete"

    # ── Repair summary ────────────────────────────────────────────────────────
    $fullPath = Resolve-Path "."
    Write-Host ""
    Write-Host "  Repair complete!" -ForegroundColor Green
    Write-Host "  ================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Location: $fullPath" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Git log:" -ForegroundColor Blue
    & git log --oneline | Select-Object -First 10 | ForEach-Object { Write-Host "    $_" }
    Write-Host ""
    exit 0
}

# ── Step 1: Scaffold project ─────────────────────────────────────────────────
Write-Step "Scaffolding project with uv..."

if (Test-Path $OutputDir) {
    $backupName = "$OutputDir.backup.$(Get-Date -Format 'yyyyMMddHHmmss')"
    Write-Warn "Directory exists. Creating backup at $backupName"
    Rename-Item $OutputDir $backupName
}

& uv init $OutputDir --lib --python $pythonVersion
Set-Location $OutputDir
# Clear any inherited virtual environment so uv always uses this project's own .venv
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue

# Add dependencies
if (-not [string]::IsNullOrEmpty($dependencies)) {
    Write-Info "Installing dependencies: $dependencies"
    $deps = $dependencies -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
    foreach ($dep in $deps) {
        $ErrorActionPreference = "SilentlyContinue"
        $null = & uv add $dep 2>&1
        $uvExit = $LASTEXITCODE
        $ErrorActionPreference = "Stop"
        if ($uvExit -ne 0) { Write-Warn "Failed to add: $dep" }
    }
}

# Dev dependencies
Write-Info "Installing dev dependencies..."
$ErrorActionPreference = "SilentlyContinue"
$null = & uv add --dev pytest pytest-cov ruff mypy pre-commit bandit pip-audit radon vulture 2>&1
$uvExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($uvExit -ne 0) { Write-Warn "Failed to install dev dependencies" }

Write-Ok "Project scaffolded"

# ── Step 2: Initialize git ───────────────────────────────────────────────────
Write-Step "Initializing git repository..."

& git init -q
& git config core.safecrlf false

@"
__pycache__/
*.py[cod]
*`$py.class
.venv/
dist/
build/
*.egg-info/
.mypy_cache/
.pytest_cache/
.ruff_cache/
*.log
.env
.env.*
"@ | Set-Content ".gitignore" -Encoding UTF8

@"
* text=auto eol=lf
"@ | Set-Content ".gitattributes" -Encoding UTF8

& git add -A
& git commit -q -m "chore: initial scaffold from vibegen"
Write-Ok "Git initialized"

# ── Step 3: Copy documentation files ─────────────────────────────────────────
$specDir = Split-Path -Parent $SpecFile
$docContext = ""

if ($docFiles.Count -gt 0) {
    Write-Step "Loading reference documentation..."
    New-Item -ItemType Directory -Force -Path "docs" | Out-Null
    foreach ($docFile in $docFiles) {
        $fullPath = Join-Path $specDir $docFile
        if (Test-Path $fullPath) {
            Copy-Item $fullPath "docs\" -Force
            $docContent = Get-Content $fullPath -Raw -Encoding UTF8
            $docContext += "`n`n--- REFERENCE DOCUMENT: $docFile ---`n$docContent`n--- END $docFile ---"
            Write-Ok "Loaded: $docFile"
        } else {
            Write-Warn "Documentation file not found: $fullPath"
        }
    }
}

# ── Step 4: Generate CLAUDE.md ────────────────────────────────────────────────
Write-Step "Generating CLAUDE.md..."

# Extract description from spec
$description = ""
$inDesc = $false
foreach ($line in $specLines) {
    if ($line -match "^## Description") { $inDesc = $true; continue }
    if ($inDesc -and $line -match "^## ") { break }
    if ($inDesc -and $line.Trim() -ne "") {
        $description += $line.Trim() + " "
    }
}
$description = $description.Trim()

@"
# $projectName

## Project
$description

## Tech Stack
- Python $pythonVersion, managed by ``uv``
- Ruff for linting and formatting
- pytest for testing
- mypy for type checking

## Directory Map
- ``src/$packageName/`` - main package
- ``tests/`` - test suite (mirrors src structure)

## Commands
- ``uv run pytest`` - run tests
- ``uv run ruff check . --fix`` - lint and fix
- ``uv run ruff format .`` - format
- ``uv run mypy src/`` - type check
- ``uv run bandit -r src/`` - security check
- ``uv run pip-audit`` - dependency vulnerability check
- ``uv run radon cc src/ -mi C`` - complexity report (flags grade C+ functions)
- ``uv run vulture src/`` - unused code detection

## Code Style Rules
- Always add type hints to function signatures
- Use Google-style docstrings on every public function and class
- Use loguru for logging, never print()
- Use Pydantic models for structured data
- Prefer early returns over deep nesting
- Keep functions under 30 lines; extract helpers if longer
- Use absolute imports: ``from $packageName.module import ...``
- snake_case for files, modules, functions, variables
- PascalCase for classes
- UPPER_SNAKE_CASE for constants

## Verification
After any code change, always:
1. Run: ``uv run ruff check . --fix`` and ``uv run ruff format .``
2. Run: ``uv run pytest -x``
3. Run: ``uv run mypy src/``

## Things to Avoid
- Never use pip install directly; always ``uv add``
- Never use bare ``except:`` - catch specific exceptions
- Never use mutable default arguments
- No ``print()`` statements - use loguru
"@ | Set-Content "CLAUDE.md" -Encoding UTF8

Write-Ok "CLAUDE.md created"

# ── Step 5: Create .vscode/settings.json (semi-auto workflow) ────────────────
Write-Step "Setting up VS Code integration..."

New-Item -ItemType Directory -Force -Path ".vscode" | Out-Null

@"
{
    "python.defaultInterpreterPath": "`${workspaceFolder}/.venv/Scripts/python.exe",
    "python.analysis.typeCheckingMode": "strict",
    "[python]": {
        "editor.defaultFormatter": "charliermarsh.ruff",
        "editor.formatOnSave": true,
        "editor.codeActionsOnSave": {
            "source.fixAll.ruff": "explicit",
            "source.organizeImports.ruff": "explicit"
        }
    },
    "ruff.lint.args": ["--config=pyproject.toml"],
    "files.trimTrailingWhitespace": true,
    "files.insertFinalNewline": true,
    "files.eol": "\n"
}
"@ | Set-Content ".vscode\settings.json" -Encoding UTF8

Write-Ok ".vscode/settings.json created (format-on-save, Ruff, Pylance strict)"

# ── Step 6: Install .claude/ files (slash commands + settings) ───────────────
Write-Step "Installing Claude Code slash commands and settings..."

Install-ClaudeFiles -PkgName $packageName

Write-Ok "Slash commands and settings installed"

# ── Step 7: Configure pyproject.toml ──────────────────────────────────────────
Write-Step "Configuring pyproject.toml (ruff, pytest, mypy)..."

$pyprojectContent = Get-Content "pyproject.toml" -Raw -Encoding UTF8

if ($pyprojectContent -notmatch "\[tool\.ruff\]") {
    @"

# -- Ruff -------------------------------------------------------
[tool.ruff]
line-length = 88
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "N"]

[tool.ruff.format]
docstring-code-format = true

# -- Pytest ------------------------------------------------------
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q --strict-markers --tb=short"

# -- Mypy --------------------------------------------------------
[tool.mypy]
strict = true
warn_return_any = true
disallow_untyped_defs = true

# -- Bandit ------------------------------------------------------
[tool.bandit]
exclude_dirs = ["tests", ".venv"]
skips = ["B101"]

# -- Vulture -----------------------------------------------------
[tool.vulture]
min_confidence = 80
paths = ["src/"]
"@ | Add-Content "pyproject.toml" -Encoding UTF8
}

Write-Ok "Tool configuration added"

# ── Step 8: Create pre-commit config ──────────────────────────────────────────
Write-Step "Creating pre-commit configuration..."

@"
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: bandit
        name: bandit security check
        entry: uv run bandit
        args: ["-c", "pyproject.toml", "-r", "src/"]
        language: system
        types: [python]
        pass_filenames: false
      - id: vulture
        name: vulture dead code
        entry: uv run vulture
        args: ["src/", "--min-confidence", "80"]
        language: system
        types: [python]
        pass_filenames: false
"@ | Set-Content ".pre-commit-config.yaml" -Encoding UTF8

# Install hooks (non-fatal if it fails)
$ErrorActionPreference = "SilentlyContinue"
$null = & uv run pre-commit install 2>&1
$uvExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($uvExit -ne 0) { Write-Warn "pre-commit install failed (you can run 'uv run pre-commit install' later)" }

Write-Ok "Pre-commit hooks configured"

# ── Checkpoint ────────────────────────────────────────────────────────────────
& git add -A
& git commit -q -m "chore: add workflow config (CLAUDE.md, vscode, slash commands, pre-commit)"

# ── Step 9: Generate source code ──────────────────────────────────────────────
Write-Step "Generating source code with Claude Code (this may take a few minutes)..."

$codePrompt = @"
You are building a Python project from a specification. The project is already scaffolded with uv in the current directory. The package is at src/$packageName/.

Here is the full project specification:

$specContent
$docContext

INSTRUCTIONS:
1. Read the existing project structure first.
2. Create ALL source files inside src/$packageName/ following the spec exactly.
3. Create a proper __init__.py that exports the public API.
4. Use type hints on every function signature.
5. Use Google-style docstrings on every public function and class.
6. Use Pydantic models for any structured data.
7. Use loguru for logging (never print).
8. Handle all edge cases mentioned in the spec.
9. Keep functions focused and under 30 lines.
10. Use absolute imports: from $packageName.module import ...
11. Do NOT create tests yet - only source code.
12. Do NOT modify pyproject.toml dependencies - they are already installed.
"@

$claudeOutput = Invoke-Claude -Prompt $codePrompt -Label "code-generation"

# Run ruff natively — guaranteed cleanup regardless of whether Claude ran it
$ErrorActionPreference = "SilentlyContinue"
$null = & uv run ruff check . --fix 2>&1
$null = & uv run ruff format . 2>&1
$ErrorActionPreference = "Stop"

& git add -A
& git commit -q -m "feat: generate source code from spec" --allow-empty
Write-Ok "Source code generated and committed"

# ── Step 10: Generate tests ──────────────────────────────────────────────────
Write-Step "Generating test suite with Claude Code..."

$testPrompt = @"
You are adding tests to an existing Python project. The source code is in src/$packageName/.

Here is the project specification for context:

$specContent

INSTRUCTIONS:
1. Read ALL source files in src/$packageName/ to understand what was implemented.
2. Create comprehensive tests in the tests/ directory.
3. Create tests/conftest.py with shared fixtures.
4. Create one test file per source module (test_<module>.py).
5. Test every public function and class method.
6. Test all edge cases listed in the spec.
7. Test error handling paths (invalid input, network failures, etc.).
8. Use pytest fixtures, parametrize where appropriate.
9. Mock external dependencies (network calls, file I/O where needed).
10. Each test should have a descriptive name: test_<function>_<scenario>.
11. Always use specific exception types in pytest.raises() - never bare Exception or BaseException.
12. After creating all test files, run: uv run ruff check tests/ --fix && uv run ruff format tests/
13. Then run: uv run pytest -x --tb=short
14. Report the test results.
"@

$claudeOutput = Invoke-Claude -Prompt $testPrompt -Label "test-generation"

& git add -A
& git commit -q -m "test: generate test suite from spec" --allow-empty
Write-Ok "Test suite generated and committed"

# ── Step 11: Run tests and iterate ────────────────────────────────────────────
Write-Step "Running tests and fixing failures (up to $MaxFixAttempts attempts)..."

for ($attempt = 1; $attempt -le $MaxFixAttempts; $attempt++) {
    Write-Info "Test attempt $attempt/$MaxFixAttempts"

    $ErrorActionPreference = "SilentlyContinue"
    $testOutput = & uv run pytest -x --tb=short 2>&1 | Out-String
    $ErrorActionPreference = "Stop"
    $testPassed = ($testOutput -match "passed") -and ($testOutput -notmatch "failed|error|ERROR")

    if ($testPassed) {
        Write-Ok "All tests passing!"
        ($testOutput -split "`n") | Select-Object -Last 5 | ForEach-Object { Write-Host $_ }
        break
    }

    if ($attempt -ge $MaxFixAttempts) {
        Write-Warn "Max fix attempts reached. Some tests may still be failing."
        ($testOutput -split "`n") | Select-Object -Last 20 | ForEach-Object { Write-Host $_ }
        break
    }

    # Pre-run ruff — may resolve failures caused by import/lint issues without a Claude call
    $ErrorActionPreference = "SilentlyContinue"
    $null = & uv run ruff check . --fix 2>&1
    $null = & uv run ruff format . 2>&1
    $ruffTestOutput = & uv run pytest -x --tb=short 2>&1 | Out-String
    $ErrorActionPreference = "Stop"

    if (($ruffTestOutput -match "passed") -and ($ruffTestOutput -notmatch "failed|error|ERROR")) {
        Write-Ok "Ruff auto-fix resolved failures (attempt $attempt)"
        & git add -A
        & git commit -q -m "fix: ruff auto-fix resolved test failures" --allow-empty
        break
    }
    $testOutput = $ruffTestOutput  # Use post-ruff output for Claude

    Write-Warn "Tests failing. Asking Claude to fix (attempt $attempt)..."

    $fixSummary = Get-TestFailureSummary $testOutput
    $fixPrompt = @"
The tests are failing. Here is the pytest output:

``````
$fixSummary
``````

INSTRUCTIONS:
1. Read the failing test files AND the source files they test.
2. Determine if the bug is in the source code or the test code.
3. Fix the actual bugs - do NOT just make tests pass by weakening assertions.
4. If a test expectation is wrong (doesn't match the spec), fix the test.
5. If the source code doesn't match the spec, fix the source code.
6. Run: uv run ruff check . --fix && uv run ruff format .
7. Run: uv run pytest -x --tb=short
8. Report the results.
"@

    $claudeOutput = Invoke-Claude -Prompt $fixPrompt -Label "test-fix-$attempt"

    & git add -A
    & git commit -q -m "fix: test fixes (attempt $attempt)" --allow-empty
}

# ── Step 12: Final quality checks ─────────────────────────────────────────────
Write-Step "Running final quality checks (ruff, mypy, bandit, pip-audit, radon, vulture)..."

$ErrorActionPreference = "SilentlyContinue"
$null = & uv run ruff check . --fix 2>&1
$null = & uv run ruff format . 2>&1
$ErrorActionPreference = "Stop"

# mypy
$mypyOutput = & uv run mypy src/ 2>&1 | Out-String
if ($mypyOutput -match "error:") {
    Write-Warn "mypy found type errors (non-blocking):"
    ($mypyOutput -split "`n") | Where-Object { $_ -match "error:" } | Select-Object -First 10 | ForEach-Object { Write-Host $_ }
} else {
    Write-Ok "mypy: no type errors"
}

# bandit — security
$ErrorActionPreference = "SilentlyContinue"
$banditOutput = & uv run bandit -c pyproject.toml -r src/ -f txt 2>&1 | Out-String
$ErrorActionPreference = "Stop"
if ($banditOutput -match "Severity: (Medium|High)") {
    Write-Warn "bandit found security issues (non-blocking):"
    ($banditOutput -split "`n") | Where-Object { $_ -match "Severity:|Issue:|Location:" } | Select-Object -First 15 | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Ok "bandit: no medium/high security issues"
}

# pip-audit — dependency vulnerabilities
$ErrorActionPreference = "SilentlyContinue"
$auditOutput = & uv run pip-audit 2>&1 | Out-String
$ErrorActionPreference = "Stop"
if ($auditOutput -match "vulnerability|GHSA|CVE") {
    Write-Warn "pip-audit found vulnerable dependencies:"
    ($auditOutput -split "`n") | Where-Object { $_ -match "vulnerability|GHSA|CVE|Name" } | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Ok "pip-audit: no known vulnerabilities"
}

# radon — cyclomatic complexity (grade C+ = CC >= 11)
$ErrorActionPreference = "SilentlyContinue"
$radonOutput = & uv run radon cc src/ -mi C 2>&1 | Out-String
$ErrorActionPreference = "Stop"
if ($radonOutput.Trim()) {
    Write-Warn "radon: complex functions detected (consider refactoring):"
    ($radonOutput -split "`n") | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Ok "radon: all functions within complexity limits"
}

# vulture — unused code
$ErrorActionPreference = "SilentlyContinue"
$vultureOutput = & uv run vulture src/ --min-confidence 80 2>&1 | Out-String
$ErrorActionPreference = "Stop"
if ($vultureOutput.Trim()) {
    Write-Warn "vulture: unused code detected:"
    ($vultureOutput -split "`n") | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Ok "vulture: no unused code detected"
}

& git add -A
& git commit -q -m "chore: final lint and format pass" --allow-empty

# ── Step 13: Generate README ──────────────────────────────────────────────────
Write-Step "Generating README.md..."

# Build project structure listing from actual generated files
$srcPyFiles = Get-ChildItem "src\$packageName" -Recurse -Filter "*.py" -ErrorAction SilentlyContinue |
    ForEach-Object { "  " + $_.FullName.Substring((Join-Path (Get-Location).Path "src\").Length) }
$srcStructure = if ($srcPyFiles) { ($srcPyFiles -join "`n") } else { "  (generated source files)" }

# Determine install command (use project name for clone URL placeholder)
$repoSlug = $projectName.ToLower() -replace '[^a-z0-9-]', '-'

@"
# $projectName

$description

## Installation

```bash
git clone https://github.com/<user>/$repoSlug
cd $repoSlug
uv sync
```

## Usage

$usageSection

## Development

```bash
uv run pytest              # run tests
uv run ruff check . --fix  # lint and auto-fix
uv run ruff format .       # format code
uv run mypy src/           # type check
```

## Project Structure

```
src/$packageName/
$srcStructure
tests/
```

## License

MIT
"@ | Set-Content "README.md" -Encoding UTF8

& git add -A
& git commit -q -m "docs: generate README" --allow-empty

# ── Summary ───────────────────────────────────────────────────────────────────
$fullPath = Resolve-Path "."

Write-Host ""
Write-Host "  Project generated successfully!" -ForegroundColor Green
Write-Host "  ===============================" -ForegroundColor Green
Write-Host ""
Write-Host "  Location:    $fullPath" -ForegroundColor Cyan
Write-Host "  Package:     $packageName" -ForegroundColor Cyan
Write-Host "  Python:      $pythonVersion" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Get started:" -ForegroundColor Blue
Write-Host "    cd $OutputDir"
Write-Host "    uv run pytest              # run tests"
Write-Host "    uv run ruff check .        # lint"
Write-Host "    uv run mypy src/           # type check"
Write-Host "    code .                     # open in VS Code"
Write-Host ""
Write-Host "  In VS Code with Claude Code:" -ForegroundColor Blue
Write-Host "    /review                    # review recent changes"
Write-Host "    /test <module>             # generate tests for a module"
Write-Host "    /new-module <name>         # scaffold a new module + tests"
Write-Host "    /fix                       # run all checks and fix failures"
Write-Host "    /refactor <file>           # improve code structure"
Write-Host ""
Write-Host "  Git log:" -ForegroundColor Blue
& git log --oneline | Select-Object -First 10 | ForEach-Object { Write-Host "    $_" }
Write-Host ""
