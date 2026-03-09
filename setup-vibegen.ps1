# setup-vibegen.ps1 — One-time setup for the vibegen project generator (Windows)
#
# Run from PowerShell:  .\setup-vibegen.ps1

$ErrorActionPreference = "Stop"

# ── Helpers ───────────────────────────────────────────────────────────────────
function Write-Step  ($msg) { Write-Host "[STEP]  $msg" -ForegroundColor Blue }
function Write-Ok    ($msg) { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Warn  ($msg) { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Write-Err   ($msg) { Write-Host "[ERR]   $msg" -ForegroundColor Red }
function Write-Info  ($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }

Write-Host ""
Write-Host "  vibegen setup - automatic Python project generator (Windows)" -ForegroundColor Cyan
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Check prerequisites ───────────────────────────────────────────────
Write-Step "Checking prerequisites..."

# Check Git for Windows (required by Claude Code)
$gitPath = Get-Command git -ErrorAction SilentlyContinue
if ($gitPath) {
    Write-Ok "git: $(git --version)"
} else {
    Write-Err "Git for Windows is not installed."
    Write-Info "Download from: https://git-scm.com/download/win"
    Write-Info "Claude Code requires Git for Windows (it uses Git Bash internally)."
    exit 1
}

# Check that Git Bash exists (Claude Code needs it)
$gitBashPath = Join-Path (Split-Path (Split-Path $gitPath.Source)) "bin\bash.exe"
if (-not (Test-Path $gitBashPath)) {
    # Try common locations
    $gitBashPath = "C:\Program Files\Git\bin\bash.exe"
}
if (Test-Path $gitBashPath) {
    Write-Ok "Git Bash found: $gitBashPath"
} else {
    Write-Warn "Git Bash not found at expected location. Claude Code may prompt you to configure it."
}

# ── Step 2: Install/check uv ─────────────────────────────────────────────────
Write-Step "Checking for uv..."

$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCmd) {
    Write-Ok "uv: $(uv --version)"
} else {
    Write-Info "Installing uv..."
    try {
        irm https://astral.sh/uv/install.ps1 | iex
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
        if ($uvCmd) {
            Write-Ok "uv installed: $(uv --version)"
        } else {
            Write-Warn "uv installed but not in PATH yet. Restart your terminal after setup."
        }
    } catch {
        Write-Err "uv installation failed. Install manually: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    }
}

# ── Step 3: Install/check Claude Code CLI ─────────────────────────────────────
Write-Step "Checking for Claude Code CLI..."

$claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
if ($claudeCmd) {
    Write-Ok "Claude Code CLI found"
} else {
    Write-Info "Installing Claude Code CLI (native installer)..."
    try {
        # Use the native installer (no Node.js required)
        irm https://claude.ai/install.ps1 | iex

        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        $claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
        if ($claudeCmd) {
            Write-Ok "Claude Code CLI installed"
        } else {
            Write-Warn "Claude Code installed but not in PATH yet."
            Write-Info "Add $env:USERPROFILE\.local\bin to your PATH, then restart your terminal."
        }
    } catch {
        Write-Err "Claude Code installation failed."
        Write-Info "Install manually from PowerShell:"
        Write-Info "  irm https://claude.ai/install.ps1 | iex"
        Write-Info "Then authenticate: claude auth login"
        exit 1
    }
}

# ── Step 4: Install vibegen files ─────────────────────────────────────────────
Write-Step "Installing vibegen..."

$installDir = Join-Path $env:USERPROFILE ".local\bin"
$vibegenDir = Join-Path $env:USERPROFILE ".vibegen"
$templatesDir = Join-Path $vibegenDir "templates"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Create directories
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
New-Item -ItemType Directory -Force -Path $templatesDir | Out-Null

# Copy vibegen.ps1
$srcScript = Join-Path $scriptDir "vibegen.ps1"
$destScript = Join-Path $installDir "vibegen.ps1"
if (Test-Path $srcScript) {
    Copy-Item $srcScript $destScript -Force
    Write-Ok "Installed vibegen.ps1 to $installDir"
} else {
    Write-Err "vibegen.ps1 not found in $scriptDir"
    Write-Info "Make sure vibegen.ps1 is in the same directory as this setup script."
    exit 1
}

# Copy prompts/ directory (vibegen.ps1 reads prompts relative to $ScriptRoot)
$promptsSrc  = Join-Path $scriptDir "prompts"
$promptsDest = Join-Path $installDir "prompts"
if (Test-Path $promptsSrc) {
    if (Test-Path $promptsDest) { Remove-Item $promptsDest -Recurse -Force }
    Copy-Item $promptsSrc $promptsDest -Recurse -Force
    $promptCount = (Get-ChildItem $promptsDest -Filter "*.txt").Count
    Write-Ok "Copied $promptCount prompt templates to $promptsDest"
} else {
    Write-Warn "prompts/ directory not found in $scriptDir"
}

# Copy scripts/ directory (ollama_client.py, etc.)
$scriptsSrc  = Join-Path $scriptDir "scripts"
$scriptsDest = Join-Path $installDir "scripts"
if (Test-Path $scriptsSrc) {
    if (Test-Path $scriptsDest) { Remove-Item $scriptsDest -Recurse -Force }
    Copy-Item $scriptsSrc $scriptsDest -Recurse -Force
    Write-Ok "Copied helper scripts to $scriptsDest"
}

# Create a launcher batch file so "vibegen" works from CMD/PowerShell
$launcherPath = Join-Path $installDir "vibegen.cmd"
@"
@echo off
powershell -ExecutionPolicy Bypass -File "%USERPROFILE%\.local\bin\vibegen.ps1" %*
"@ | Set-Content $launcherPath -Encoding ASCII
Write-Ok "Created vibegen.cmd launcher"

# Copy templates
$srcExample = Join-Path $scriptDir "spec.example.md"
if (Test-Path $srcExample) {
    Copy-Item $srcExample (Join-Path $templatesDir "spec.example.md") -Force
}

# Copy .claude/commands (slash command templates, preserving category subdirectories)
$commandsSrcDir = Join-Path $scriptDir ".claude\commands"
$commandsDestDir = Join-Path $vibegenDir "commands"
New-Item -ItemType Directory -Force -Path $commandsDestDir | Out-Null
if (Test-Path $commandsSrcDir) {
    Get-ChildItem $commandsSrcDir -Recurse -Filter "*.md" | ForEach-Object {
        $relPath = $_.FullName.Substring($commandsSrcDir.Length + 1)
        $destPath = Join-Path $commandsDestDir $relPath
        New-Item -ItemType Directory -Force -Path (Split-Path $destPath) | Out-Null
        Copy-Item $_.FullName $destPath -Force
    }
    $cmdCount = (Get-ChildItem $commandsDestDir -Recurse -Filter *.md).Count
    Write-Ok "Copied $cmdCount slash commands to $commandsDestDir"
} else {
    Write-Warn ".claude/commands not found in $scriptDir"
}

# Copy .claude/settings.local.json
$settingsSrc = Join-Path $scriptDir ".claude\settings.local.json"
if (Test-Path $settingsSrc) {
    Copy-Item $settingsSrc (Join-Path $vibegenDir "settings.local.json") -Force
    Write-Ok "Copied settings.local.json to $vibegenDir"
} else {
    Write-Warn ".claude/settings.local.json not found in $scriptDir"
}

# ── Step 5: Create default spec template ──────────────────────────────────────
Write-Step "Creating spec template..."

$templateContent = @"
# Project Spec

## Name
my-project

## Description
A brief description of what this project does and why it exists.

## Python Version
3.12

## Input
- Describe what goes into your program (CLI args, files, API calls, etc.)

## Output
- Describe what comes out (files, stdout, return values, side effects, etc.)

## Requirements
- Requirement 1: Be specific about behavior
- Requirement 2: Include error handling expectations
- Requirement 3: Mention any protocols or standards to follow

## Dependencies
package1, package2, package3

## Example Usage
``````bash
# Show concrete examples of how the tool/library should be used
my-project do-something --flag value
``````

## Edge Cases
- What happens with empty input?
- What happens with invalid input?
- What happens when external services are unavailable?

## Documentation
<!-- Optional: paths to reference docs relative to this spec file -->
<!-- docs/api-reference.md -->
<!-- docs/data-format.md -->
"@

$templateContent | Set-Content (Join-Path $templatesDir "spec.template.md") -Encoding UTF8
Write-Ok "Spec template created at $templatesDir\spec.template.md"

# ── Step 6: Ensure PATH ──────────────────────────────────────────────────────
Write-Step "Checking PATH..."

$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -like "*$installDir*") {
    Write-Ok "$installDir is already in PATH"
} else {
    [System.Environment]::SetEnvironmentVariable("Path", "$userPath;$installDir", "User")
    $env:Path = "$env:Path;$installDir"
    Write-Ok "Added $installDir to user PATH"
    Write-Info "Restart your terminal for PATH changes to take full effect."
}

# ── Step 7: Configure global CLAUDE.md ────────────────────────────────────────
Write-Step "Setting up global Claude Code preferences..."

$globalClaudeDir = Join-Path $env:USERPROFILE ".claude"
New-Item -ItemType Directory -Force -Path $globalClaudeDir | Out-Null

$globalClaudeMd = Join-Path $globalClaudeDir "CLAUDE.md"
if (-not (Test-Path $globalClaudeMd)) {
    @"
## Global Preferences
- Always use type hints on function signatures
- Use Google-style docstrings
- Prefer early returns over deep nesting
- Never use bare except: - always catch specific exceptions
- Use loguru for logging, never print()
- Use uv for package management, never pip
- Use ruff for linting and formatting
- Use absolute imports
"@ | Set-Content $globalClaudeMd -Encoding UTF8
    Write-Ok "Created global CLAUDE.md at $globalClaudeMd"
} else {
    Write-Info "Global CLAUDE.md already exists - not overwriting"
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "  ===============" -ForegroundColor Green
Write-Host ""
Write-Host "  Installed:" -ForegroundColor Cyan
Write-Host "    vibegen          -> $installDir\vibegen.ps1"
Write-Host "    vibegen.cmd      -> $installDir\vibegen.cmd  (use from any terminal)"
Write-Host "    spec template    -> $templatesDir\spec.template.md"
Write-Host ""
Write-Host "  Quick start:" -ForegroundColor Cyan
Write-Host ""
Write-Host "    # 1. Copy the spec template to your working directory"
Write-Host "    copy $templatesDir\spec.template.md .\spec.md"
Write-Host ""
Write-Host "    # 2. Edit the spec with your project requirements"
Write-Host "    code spec.md"
Write-Host ""
Write-Host "    # 3. Generate the project"
Write-Host "    vibegen spec.md"
Write-Host ""
Write-Host "    # 4. Or generate into a specific directory"
Write-Host "    vibegen spec.md --output-dir C:\Users\$env:USERNAME\projects\my-tool"
Write-Host ""
Write-Host "  Note: Restart your terminal if 'vibegen' is not found." -ForegroundColor Yellow
Write-Host ""
