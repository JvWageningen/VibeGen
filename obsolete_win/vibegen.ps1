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

    [ValidateSet("claude","ollama")]
    [string]$ModelProvider = "claude",

    [string]$Model = "claude-sonnet-4-6",

    [switch]$SkipPermissions,

    [switch]$ShowOutput,

    [switch]$Help
)

$ErrorActionPreference = "Stop"

# Script root folder (used when resolving paths to bundled templates and helper scripts)
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$OriginalPath = $env:PATH

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
    -OutputDir <path>         Where to create the project (default: <spec-dir>\<project-name>)
    -MaxFixAttempts <n>       Max test-fix iterations (default: 3)
    -MaxTurns <n>             Max agent turns per step (default: 30)
    -ModelProvider <claude|ollama>  Which LLM provider to use (default: claude)
    -Model <model>            Model name to use (e.g. claude-sonnet-4-6 or llama2)
    -SkipPermissions          Use --dangerously-skip-permissions (containers only!)
    -ShowOutput               Show full LLM output
    -Help                     Show this help

REPAIR OPTIONS:
    -RepoPath <path>          Path to the repo to repair (default: current directory)
    -MaxFixAttempts <n>       Max test-fix iterations (default: 3)
    -MaxTurns <n>             Max agent turns per step (default: 30)
    -ModelProvider <claude|ollama>  Which LLM provider to use (default: claude)
    -Model <model>            Model name to use (e.g. claude-sonnet-4-6 or llama2)
    -ShowOutput               Show full LLM output

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

$effectiveModelProvider = $ModelProvider
$effectiveModel = $Model
if ($Model -match '^(?<provider>claude|ollama):(?<model>.+)$') {
    $effectiveModelProvider = $Matches['provider']
    $effectiveModel = $Matches['model']
}

$requiredTools = @("uv", "git")
switch ($effectiveModelProvider.ToLower()) {
    "claude" { $requiredTools += "claude" }
    "ollama" { $requiredTools += "python" }
    default {
        Write-Err "Unknown model provider '$effectiveModelProvider'. Use -ModelProvider claude|ollama or prefix model with 'claude:' or 'ollama:'."
        exit 1
    }
}

foreach ($cmd in $requiredTools) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Err "'$cmd' is not installed or not in PATH. Run setup-vibegen.ps1 first."
        exit 1
    }
}

Write-Ok "All required tools found ($($requiredTools -join ', '))"

if ($effectiveModelProvider.ToLower() -eq 'ollama') {
    try {
        & python -c "import requests" 2>$null
    } catch {
        Write-Err "Python package 'requests' is required for Ollama API access. Install it using 'uv add requests' or 'pip install requests'."
        exit 1
    }
}

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
    # Default: place the new project next to the spec file (not the cwd)
    $OutputDir = Join-Path (Split-Path -Parent $SpecFile) $projectName
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

# Remove UTF-8 BOM from a file (PowerShell 5.1 Set-Content -Encoding UTF8 always adds BOM,
# but Python's tomllib rejects BOM, so strip it from .toml and .py files after every write)
function Remove-Bom {
    param([Parameter(Mandatory)][string]$Path)
    # Resolve to absolute path using PS location (not .NET working dir, which may differ after Set-Location)
    $absPath = if ([System.IO.Path]::IsPathRooted($Path)) { $Path } else {
        Join-Path (Get-Location).Path $Path
    }
    if (-not (Test-Path $absPath)) { return }
    $bytes = [System.IO.File]::ReadAllBytes($absPath)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        [System.IO.File]::WriteAllBytes($absPath, $bytes[3..($bytes.Length - 1)])
    }
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

# Render a template file using {{var}} placeholders (simple, non-recursive)
function Render-Template {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [hashtable]$Values
    )

    $template = Get-Content $Path -Raw -Encoding UTF8
    foreach ($key in $Values.Keys) {
        # Use literal string replacement to avoid regex replacement interpretation
        # (scriptblock replacement is PS7+ only; -replace with string is PS5.1 compatible
        #  but $ in replacement strings is interpreted as backreferences - so use .Replace())
        $template = $template.Replace("{{$key}}", $Values[$key].ToString())
    }
    return $template
}

# Extract the final result text from a claude stream-json transcript (or return raw for ollama).
function Get-AssistantText {
    param([string]$Output)
    $resultText = ""
    foreach ($line in ($Output -split "`n")) {
        $trimmed = $line.Trim()
        if (-not $trimmed.StartsWith('{')) { continue }
        try {
            $ev = $trimmed | ConvertFrom-Json -ErrorAction Stop
            if ($ev.type -eq "result" -and $ev.result) {
                $resultText = $ev.result
            } elseif ($ev.type -eq "assistant") {
                foreach ($block in $ev.message.content) {
                    if ($block.type -eq "text") { $resultText = $block.text }
                }
            }
        } catch { }
    }
    # If no stream-json found (ollama), return the full output as-is
    if ($resultText) { return $resultText }
    return $Output
}

# Collect a simple tree of the current repository, for context in prompts.
function Get-RepoTree {
    $root = (Get-Location).Path
    $files = Get-ChildItem -Recurse -File | ForEach-Object {
        $_.FullName.Substring($root.Length + 1).Replace('\', '/')
    }
    return ($files | Sort-Object) -join "`n"
}

# Generate an indented ASCII directory tree (excludes .venv, .git, caches)
function Get-DirectoryTree {
    param([string]$Root = "", [int]$MaxDepth = 5)

    $rootPath = if ($Root) { $Root } else { (Get-Location).Path }
    $excludeDirs = @(".venv", ".git", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build")

    function _TreeLines {
        param([string]$DirPath, [string]$Prefix, [int]$Depth)
        if ($Depth -gt $MaxDepth) { return @() }
        $items = Get-ChildItem $DirPath -ErrorAction SilentlyContinue |
            Where-Object { $excludeDirs -notcontains $_.Name -and $_.Name -notmatch '\.egg-info$' }
        $dirs  = @($items | Where-Object {  $_.PSIsContainer } | Sort-Object Name)
        $files = @($items | Where-Object { -not $_.PSIsContainer } | Sort-Object Name)
        $ordered = $dirs + $files
        $out = @()
        for ($i = 0; $i -lt $ordered.Count; $i++) {
            $item = $ordered[$i]
            $isLast    = ($i -eq $ordered.Count - 1)
            $connector = if ($isLast) { "└── " } else { "├── " }
            $childPfx  = if ($isLast) { "    " } else { "│   " }
            if ($item.PSIsContainer) {
                $out += "$Prefix$connector$($item.Name)/"
                $out += _TreeLines -DirPath $item.FullName -Prefix "$Prefix$childPfx" -Depth ($Depth + 1)
            } else {
                $out += "$Prefix$connector$($item.Name)"
            }
        }
        return $out
    }

    $rootName = Split-Path $rootPath -Leaf
    $lines = @("$rootName/") + (_TreeLines -DirPath $rootPath -Prefix "" -Depth 1)
    return $lines -join "`n"
}

# Parse intra-package Python imports and return a formatted dependency graph string.
function Get-PythonDependencyGraph {
    param([string]$PackageName = "", [string]$SrcDir = "src")

    $srcPath = if ([System.IO.Path]::IsPathRooted($SrcDir)) { $SrcDir } else {
        Join-Path (Get-Location).Path $SrcDir
    }
    if (-not (Test-Path $srcPath)) { return "" }

    $pyFiles = Get-ChildItem $srcPath -Recurse -Filter "*.py" -ErrorAction SilentlyContinue
    if ($pyFiles.Count -eq 0) { return "" }

    $graph = [ordered]@{}
    foreach ($file in $pyFiles) {
        $relPath = $file.FullName.Substring($srcPath.Length + 1).Replace('\', '/')
        $content = Get-Content $file.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if (-not $content) { continue }

        $imports = @()
        foreach ($line in ($content -split "`n")) {
            $trimmed = $line.Trim()
            # Match intra-package imports: from package.X import ... or import package.X
            if ($trimmed -match "^from\s+($([regex]::Escape($PackageName))[\w\.]*)\s+import" -or
                $trimmed -match "^import\s+($([regex]::Escape($PackageName))[\w\.]*)") {
                $mod = $Matches[1]
                if ($mod -ne $PackageName) { $imports += $mod }
            }
        }

        if ($imports.Count -gt 0) {
            $graph[$relPath] = ($imports | Select-Object -Unique)
        }
    }

    if ($graph.Count -eq 0) { return "" }

    $lines = @("Intra-package import graph:")
    foreach ($entry in $graph.GetEnumerator()) {
        $lines += "  $($entry.Key):"
        foreach ($dep in $entry.Value) { $lines += "    imports $dep" }
    }
    return $lines -join "`n"
}

# Try to parse a JSON object from model output text.
function Parse-ModelJson {
    param([string]$Text)

    # Normalize line endings and remove markdown fences from the output
    $lines = ($Text -replace "`r", "") -split "`n" | Where-Object { $_.TrimStart() -notmatch '^```' }

    # First attempt: parse file blocks in the output.
    $files = @{}
    $currentPath = $null
    $currentContent = @()

    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if ($trimmed -match '^---\s*file:\s*(.+?)\s*---$') {
            if ($currentPath) {
                $files[$currentPath] = ($currentContent -join "`n").TrimEnd("`n")
            }
            $currentPath = $Matches[1].Trim()
            $currentContent = @()
            continue
        }
        if ($currentPath) {
            $currentContent += $line
        }
    }

    if ($currentPath) {
        $files[$currentPath] = ($currentContent -join "`n").TrimEnd("`n")
    }

    if ($files.Count -gt 0) {
        return [pscustomobject]@{ files = $files }
    }

    # Second attempt: parse JSON from the output by trying all line spans.
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].TrimStart().StartsWith('{')) {
            for ($j = $i; $j -lt $lines.Count; $j++) {
                $candidate = $lines[$i..$j] -join "`n"
                try {
                    return $candidate | ConvertFrom-Json -ErrorAction Stop
                } catch {
                    # continue trying more lines
                }
            }
        }
    }

    return $null
}

# Write files described in a model-generated JSON object.
function Write-FilesFromModel {
    param(
        [Parameter(Mandatory)] [psobject]$ModelOutput,
        [string]$Label = "model-output"
    )

    if (-not $ModelOutput.PSObject.Properties.Name -contains 'files') {
        Write-Warn "[$Label] Model output did not include a 'files' key."
        return
    }

    $files = $ModelOutput.files
    if (-not $files) {
        Write-Warn "[$Label] 'files' object was empty."
        return
    }

    # Hash tables in PowerShell expose metadata properties like Count/Keys,
    # so iterate entries directly when possible.
    if ($files -is [System.Collections.IDictionary]) {
        $entries = $files.GetEnumerator()
    } else {
        $entries = $files.PSObject.Properties
    }

    foreach ($entry in $entries) {
        if ($entry -is [System.Collections.DictionaryEntry]) {
            $relPath = $entry.Key
            $content = $entry.Value
        } else {
            $relPath = $entry.Name
            $content = $entry.Value
        }

        if (-not [string]::IsNullOrEmpty($relPath)) {
            $dest = Join-Path (Get-Location) $relPath
            $dir  = Split-Path $dest
            if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
            $content | Set-Content -Path $dest -Encoding UTF8
            # Strip BOM from TOML files — Python's tomllib rejects UTF-8 BOM
            if ($relPath -match '\.toml$') { Remove-Bom $dest }
            Write-Host "  [$Label] Wrote: $relPath" -ForegroundColor DarkGray
        }
    }
}

# Helper function to call the configured LLM (Claude or Ollama) non-interactively
function Invoke-Claude {
    param(
        [Parameter(Mandatory)][string]$Prompt,
        [string]$Label = "Claude",
        [string]$WorkingDirectory = "",
        [int]$Turns = 0
    )

    $effectiveTurns = if ($Turns -gt 0) { $Turns } else { $MaxTurns }

    # Support syntax: "ollama:<model>" or "claude:<model>" in the -Model arg.
    $effectiveModelProvider = $ModelProvider
    $effectiveModel = $Model
    if ($Model -match '^(?<provider>claude|ollama):(?<model>.+)$') {
        $effectiveModelProvider = $Matches['provider']
        $effectiveModel = $Matches['model']
    }

    $startTime = Get-Date
    Write-Host "  [$effectiveModelProvider/$Label] Starting..." -ForegroundColor DarkCyan

    # Use a temp file for the prompt to avoid escaping issues
    $promptFile = [IO.Path]::GetTempFileName()
    Set-Content $promptFile -Value $Prompt -Encoding UTF8

    $lines    = [System.Collections.Generic.List[string]]::new()
    $lastText = ""
    $proc     = $null

    try {
        $psi                       = [Diagnostics.ProcessStartInfo]::new()
        $psi.RedirectStandardInput = $true
        $psi.RedirectStandardOutput= $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute       = $false
        $psi.CreateNoWindow        = $false
        if ($WorkingDirectory) { $psi.WorkingDirectory = $WorkingDirectory }

        switch ($effectiveModelProvider.ToLower()) {
            "claude" {
                # Unset nested-session guards
                $savedClaudeCode = $env:CLAUDECODE
                $savedEntrypoint = $env:CLAUDE_CODE_ENTRYPOINT
                Remove-Item Env:CLAUDECODE             -ErrorAction SilentlyContinue
                Remove-Item Env:CLAUDE_CODE_ENTRYPOINT -ErrorAction SilentlyContinue

                $psi.FileName  = (Get-Command claude -ErrorAction Stop).Source
                $allArgs       = @("-p", "--verbose", "--model", $effectiveModel, "--max-turns", $effectiveTurns,
                                   "--output-format", "stream-json", "--include-partial-messages") + $permFlags
                $psi.Arguments = ($allArgs -join " ")
            }
            "ollama" {
                # Use the Ollama HTTP API via a minimal helper script to avoid CLI quoting/interactive issues.
                # Use the system Python (outside the project venv) to avoid broken venvs.
                $oldPath = $env:PATH
                $env:PATH = $OriginalPath
                try {
                    $pythonExe = (Get-Command python -ErrorAction Stop).Source
                } finally {
                    $env:PATH = $oldPath
                }
                $psi.FileName = $pythonExe

                $script = Join-Path $ScriptRoot "scripts\ollama_client.py"
                $systemPromptPath = Join-Path $ScriptRoot "prompts\system.txt"
                $systemPrompt = ""
                if (Test-Path $systemPromptPath) {
                    $systemPrompt = Get-Content $systemPromptPath -Raw -Encoding UTF8
                }

                # Use temp files to safely pass multi-line prompts to the helper.
                $systemPromptFile = [IO.Path]::GetTempFileName()
                Set-Content $systemPromptFile -Value $systemPrompt -Encoding UTF8
                $userPromptFile   = [IO.Path]::GetTempFileName()
                Set-Content $userPromptFile -Value $Prompt -Encoding UTF8

                $quote = { param($s) '"' + $s.Replace('"','\"') + '"' }
                $allArgs = @(
                    $script,
                    "--model", $effectiveModel,
                    "--system-file", $systemPromptFile,
                    "--user-file", $userPromptFile
                )
                $psi.Arguments = ($allArgs | ForEach-Object { & $quote $_ }) -join " "
            }
            default {
                Write-Err "Unknown model provider '$effectiveModelProvider'. Use -ModelProvider claude|ollama or prefix model with 'claude:' or 'ollama:'."
                exit 1
            }
        }

        $proc = [Diagnostics.Process]::new()
        $proc.StartInfo = $psi

        if (-not $proc.Start()) {
            Write-Err "Failed to start process: $($psi.FileName) $($psi.Arguments)"
            return ""
        }

        if ($effectiveModelProvider.ToLower() -eq "claude") {
            # Write prompt and immediately close stdin so claude knows input is done
            $proc.StandardInput.Write($Prompt)
            $proc.StandardInput.Close()

            # Read stdout line-by-line and display stream-json events in real time
            while ($true) {
                $line = $proc.StandardOutput.ReadLine()
                if ($null -eq $line) { break }
                $lines.Add($line)
                try {
                    $ev = $line | ConvertFrom-Json -ErrorAction Stop
                    switch ($ev.type) {
                        "assistant" {
                            foreach ($block in $ev.message.content) {
                                if ($block.type -eq "text") {
                                    $newText = $block.text
                                    if ($newText.Length -gt $lastText.Length) {
                                        Write-Host $newText.Substring($lastText.Length) -ForegroundColor DarkGray -NoNewline
                                        $lastText = $newText
                                    }
                                } elseif ($block.type -eq "tool_use") {
                                    if ($lastText) { Write-Host "" }
                                    $lastText = ""
                                    $detail = switch ($block.name) {
                                        "Write" { " → $($block.input.file_path)" }
                                        "Edit"  { " → $($block.input.file_path)" }
                                        "Bash"  { " → $($block.input.command.Substring(0,[Math]::Min(70,$block.input.command.Length)))" }
                                        "Read"  { " → $($block.input.file_path)" }
                                        default { "" }
                                    }
                                    Write-Host "  [Tool: $($block.name)$detail]" -ForegroundColor DarkYellow
                                }
                            }
                        }
                        "result" { if ($lastText) { Write-Host ""; $lastText = "" } }
                    }
                } catch {
                    # Suppress raw JSON/verbose debug lines; only show plain-text error messages
                    $trimmed = $line.Trim()
                    if ($trimmed -and -not $trimmed.StartsWith('{') -and $trimmed -match '(?i)error|warn|fail') {
                        Write-Host "  $trimmed" -ForegroundColor Red
                    }
                }
            }
        } else {
            # ollama_client.py reads from --user-file, not stdin — close immediately to avoid pipe deadlock
            $proc.StandardInput.Close()

            # Read stdout/stderr asynchronously to avoid blocking indefinitely.
            $stdOutTask = $proc.StandardOutput.ReadToEndAsync()
            $stdErrTask = $proc.StandardError.ReadToEndAsync()

            # Wait with a timeout (ms)
            $timeoutMs = 180000
            $waitAll = [System.Threading.Tasks.Task]::WaitAll(@($stdOutTask, $stdErrTask), $timeoutMs)
            if (-not $waitAll) {
                Write-Warn "[$effectiveModelProvider/$Label] no response within $($timeoutMs/1000)s; killing process."
                if (-not $proc.HasExited) { $proc.Kill() }
            }

            $output = ""
            $errorOutput = ""
            if ($stdOutTask.IsCompleted) { $output = $stdOutTask.Result }
            if ($stdErrTask.IsCompleted) { $errorOutput = $stdErrTask.Result }

            if ($output) {
                $output -split "`n" | ForEach-Object {
                    $lines.Add($_)
                    Write-Host $_ -ForegroundColor DarkGray
                }
            }
            if ($errorOutput) {
                $errorOutput -split "`n" | ForEach-Object {
                    if ($_.Trim()) { Write-Host "[stderr] $_" -ForegroundColor Red }
                }
            }

            if (-not $proc.HasExited) {
                if (-not $proc.WaitForExit(5000)) {
                    Write-Warn "[$effectiveModelProvider/$Label] process still running after timeout; killing."
                    $proc.Kill()
                }
            }

            $exitCode = $proc.ExitCode
        }
    } catch {
        Write-Err "Invoke-Claude failed: $($_.Exception.Message)"
        Write-Err "Full exception: $($_.Exception.ToString())"
        throw
    } finally {
        if ($proc -and -not $proc.HasExited) { $proc.Kill() }
        if ($effectiveModelProvider.ToLower() -eq "claude") {
            if ($null -ne $savedClaudeCode)  { $env:CLAUDECODE             = $savedClaudeCode }
            if ($null -ne $savedEntrypoint)  { $env:CLAUDE_CODE_ENTRYPOINT = $savedEntrypoint }
        }

        foreach ($f in @($promptFile, $systemPromptFile, $userPromptFile)) {
            if ($f -and (Test-Path $f)) { Remove-Item $f -Force -ErrorAction SilentlyContinue }
        }
    }

    $elapsed = [int](New-TimeSpan -Start $startTime -End (Get-Date)).TotalSeconds
    if ($exitCode -ne 0) {
        Write-Warn "[$effectiveModelProvider/$Label] exited with code $exitCode after ${elapsed}s"
    } else {
        Write-Host "  [$effectiveModelProvider/$Label] Done (${elapsed}s)" -ForegroundColor DarkCyan
    }
    return ($lines -join "`n")
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

    # Add venv Scripts to PATH so tools can be called directly (avoids sequential uv run bug)
    $repairVenvScripts = Join-Path (Get-Location) ".venv\Scripts"
    if (Test-Path $repairVenvScripts) {
        $env:PATH = "$repairVenvScripts;$env:PATH"
    }

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
    $null = & ruff check . --fix 2>&1   # auto-fix what ruff can handle immediately
    $null = & ruff format . 2>&1
    $ruffViolations = & ruff check . --output-format=concise 2>&1 | Out-String
    $radonFindings   = & radon cc src/ -mi C 2>&1 | Out-String          # grade C+ (CC >= 11)
    $vultureFindings = & vulture src/ --min-confidence 80 2>&1 | Out-String
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
3. After making changes: run uv run ruff check . --fix && ruff format .
4. Do NOT remove any existing functionality.
5. Report a summary of what was changed.
"@

    Invoke-Claude -Prompt $repairStructurePrompt -Label "repair-structure" -WorkingDirectory $repoLocation
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
6. Run: uv run ruff check tests/ --fix && ruff format tests/
7. Run: uv run pytest -x --tb=short and report results.
"@

    Invoke-Claude -Prompt $repairTestsPrompt -Label "repair-tests" -WorkingDirectory $repoLocation
    & git add -A
    & git commit -q -m "test: vibegen test coverage improvements" --allow-empty
    Write-Ok "Phase 2 complete"

    # ── Repair Step 4: Test fix loop ──────────────────────────────────────────
    Write-Step "Running tests and fixing failures (up to $MaxFixAttempts attempts)..."

    for ($attempt = 1; $attempt -le $MaxFixAttempts; $attempt++) {
        Write-Info "Test attempt $attempt/$MaxFixAttempts"

        $ErrorActionPreference = "SilentlyContinue"
        $testOutput = & pytest -x --tb=short 2>&1 | Out-String
        $ErrorActionPreference = "Stop"
        $testPassed = ($testOutput -match "\d+ passed") -and ($testOutput -notmatch "\d+ failed") -and ($testOutput -notmatch "\d+ error")

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
        $null = & ruff check . --fix 2>&1
        $null = & ruff format . 2>&1
        $ruffTestOutput = & pytest -x --tb=short 2>&1 | Out-String
        $ErrorActionPreference = "Stop"

        if (($ruffTestOutput -match "\d+ passed") -and ($ruffTestOutput -notmatch "\d+ failed") -and ($ruffTestOutput -notmatch "\d+ error")) {
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
4. Run: uv run ruff check . --fix && ruff format .
5. Run: uv run pytest -x --tb=short
6. Report the results.
"@

        Invoke-Claude -Prompt $fixPrompt -Label "repair-fix-$attempt" -WorkingDirectory $repoLocation
        & git add -A
        & git commit -q -m "fix: repair test failures (attempt $attempt)" --allow-empty
    }

    # ── Repair Step 5: Final code quality pass ────────────────────────────────
    Write-Step "Phase 3/3 - Final code quality pass..."

    # Pre-run tools and inject actual output so Claude skips discovery turns
    $ErrorActionPreference = "SilentlyContinue"
    $null = & ruff check . --fix 2>&1
    $null = & ruff format . 2>&1
    $finalRuffIssues  = & ruff check . --output-format=concise 2>&1 | Out-String
    $finalMypyOutput  = & mypy src/ 2>&1 | Out-String
    $finalBanditOutput = & bandit -c pyproject.toml -r src/ -f txt 2>&1 | Out-String
    $finalAuditOutput  = & pip-audit 2>&1 | Out-String
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
3. Run: uv run ruff check . --fix && ruff format .
4. Run: uv run pytest -x --tb=short to confirm tests still pass.
5. Report a summary of changes made.
"@

    Invoke-Claude -Prompt $repairCodePrompt -Label "repair-code" -WorkingDirectory $repoLocation

    $ErrorActionPreference = "SilentlyContinue"
    $null = & ruff check . --fix 2>&1
    $null = & ruff format . 2>&1
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
    Write-Warn "Directory exists. Removing $OutputDir..."
    Remove-Item $OutputDir -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $OutputDir) {
        Write-Warn "Force remove incomplete (files in use). Clearing contents instead..."
        Get-ChildItem $OutputDir -Recurse -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
}

& uv init $OutputDir --lib --python $pythonVersion
Set-Location $OutputDir
# Capture the resolved absolute path so child processes get the correct working directory
$projectDir = (Get-Location).Path
# Clear any inherited virtual environment so uv always uses this project's own .venv
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue

# Python stdlib modules that cannot be installed via uv/pip
$stdlibModules = @(
    'abc','ast','asyncio','base64','binascii','builtins','calendar','cgi','cgitb',
    'chunk','cmath','cmd','code','codecs','codeop','colorsys','compileall',
    'concurrent','configparser','contextlib','contextvars','copy','copyreg',
    'csv','ctypes','curses','dataclasses','datetime','dbm','decimal','difflib',
    'dis','doctest','email','encodings','enum','errno','faulthandler','fcntl',
    'filecmp','fileinput','fnmatch','fractions','ftplib','functools','gc',
    'getopt','getpass','gettext','glob','grp','gzip','hashlib','heapq','hmac',
    'html','http','idlelib','imaplib','importlib','inspect','io','ipaddress',
    'itertools','json','keyword','lib2to3','linecache','locale','logging',
    'lzma','mailbox','marshal','math','mimetypes','mmap','modulefinder',
    'multiprocessing','netrc','nis','nntplib','numbers','operator','optparse',
    'os','ossaudiodev','pathlib','pdb','pickle','pickletools','pipes','pkgutil',
    'platform','plistlib','poplib','posix','posixpath','pprint','profile',
    'pstats','pty','pwd','py_compile','pyclbr','pydoc','queue','quopri',
    'random','re','readline','reprlib','resource','rlcompleter','runpy',
    'sched','secrets','select','selectors','shelve','shlex','shutil','signal',
    'site','smtpd','smtplib','sndhdr','socket','socketserver','spwd','sqlite3',
    'sre_compile','sre_constants','sre_parse','ssl','stat','statistics',
    'string','stringprep','struct','subprocess','sunau','symtable','sys',
    'sysconfig','syslog','tabnanny','tarfile','telnetlib','tempfile','termios',
    'test','textwrap','threading','time','timeit','tkinter','token','tokenize',
    'tomllib','trace','traceback','tracemalloc','tty','turtle','turtledemo',
    'types','typing','unicodedata','unittest','urllib','uu','uuid','venv',
    'warnings','wave','weakref','webbrowser','winreg','winsound','wsgiref',
    'xdrlib','xml','xmlrpc','zipapp','zipfile','zipimport','zlib','zoneinfo',
    '_thread','__future__'
)

# Collect runtime deps (filter stdlib modules)
$installDeps = @()
if (-not [string]::IsNullOrEmpty($dependencies)) {
    $deps = $dependencies -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
    foreach ($dep in $deps) {
        $baseName = ($dep -split '[>=<!\[]')[0].Trim().ToLower() -replace '-','_'
        if ($stdlibModules -contains $baseName) {
            Write-Warn "Skipping '$dep' — Python standard library module (no install needed)"
        } else {
            $installDeps += $dep
        }
    }
}

# Write all deps into pyproject.toml upfront, then run a single uv sync.
# This avoids the Windows deadlock caused by multiple sequential uv add calls
# competing for the uv.lock file.
Write-Info "Configuring pyproject.toml with all dependencies..."
$pyproject = Get-Content "pyproject.toml" -Raw -Encoding UTF8

# Inject runtime deps into [project] dependencies = []
if ($installDeps.Count -gt 0) {
    $runtimeLines = ($installDeps | ForEach-Object { "    `"$_`"" }) -join ",`n"
    $pyproject = $pyproject -replace 'dependencies = \[\]', "dependencies = [`n$runtimeLines,`n]"
}

# Append [dependency-groups] dev section (uv 0.10+ format)
$devTools = @("bandit", "mypy", "pip-audit", "pre-commit", "pytest", "pytest-cov", "radon", "ruff", "vulture")
$devLines  = ($devTools | ForEach-Object { "    `"$_`"" }) -join ",`n"
$pyproject += "`n[dependency-groups]`ndev = [`n$devLines,`n]`n"

Set-Content "pyproject.toml" -Value $pyproject -Encoding UTF8
Remove-Bom "pyproject.toml"

Write-Info "Installing all dependencies with uv sync (this may take a minute)..."
& uv sync
if ($LASTEXITCODE -ne 0) { Write-Warn "Some dependencies failed to install" }

# Add venv Scripts to PATH so tools can be called directly without 'uv run'.
# This avoids the Windows bug where sequential uv invocations silently no-op.
$venvScripts = Join-Path (Get-Location) ".venv\Scripts"
$env:PATH = "$venvScripts;$env:PATH"

Write-Ok "Project scaffolded"

# Ensure the package directory matches the spec name (uv uses the output dir name by default).
$srcDir = Join-Path (Get-Location) "src"
$expectedPkgDir = Join-Path $srcDir $packageName
if (-not (Test-Path $expectedPkgDir)) {
    $existingPkgs = Get-ChildItem $srcDir -Directory -ErrorAction SilentlyContinue
    if ($existingPkgs.Count -eq 1) {
        $scaffoldPkg = $existingPkgs[0]
        if ($scaffoldPkg.Name -ne $packageName) {
            Write-Info "Renaming scaffolded package '$($scaffoldPkg.Name)' to '$packageName' (from spec)."
            Move-Item $scaffoldPkg.FullName $expectedPkgDir
        }
    } else {
        New-Item -ItemType Directory -Force -Path $expectedPkgDir | Out-Null
    }
}

# Ensure __init__.py exists so the package is importable
$initPy = Join-Path $expectedPkgDir "__init__.py"
if (-not (Test-Path $initPy)) {
    "# $packageName package" | Set-Content $initPy -Encoding UTF8
}

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
    Remove-Bom "pyproject.toml"
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

# Note: pre-commit install is intentionally skipped here — it contacts GitHub
# to validate hook revisions and can hang on slow/corporate networks.
# Run manually after generation: uv run pre-commit install
Write-Info "Run 'uv run pre-commit install' to activate git hooks"

Write-Ok "Pre-commit hooks configured"

# ── Checkpoint ────────────────────────────────────────────────────────────────
& git add -A
& git commit -q -m "chore: add workflow config (CLAUDE.md, vscode, slash commands, pre-commit)"

# ── Step 9: Planning phase ────────────────────────────────────────────────────
Write-Step "Planning implementation (module design phase)..."

# Remove auto-generated stub files from `uv init` so the model can write them freely
Get-ChildItem "src\$packageName" -File | Remove-Item -Force -ErrorAction SilentlyContinue

$scaffoldTree = Get-DirectoryTree
$constraints = @"
- Use type hints on every function signature.
- Use Google-style docstrings on public functions and classes.
- Use Pydantic models for any structured data.
- Use loguru for logging (never print()).
- Handle all edge cases mentioned in the spec.
- Keep functions focused and under 30 lines.
- Use absolute imports: from $packageName.module import ...
- Do NOT modify pyproject.toml dependencies.
"@

$planPrompt = Render-Template (Join-Path $ScriptRoot "prompts\plan.txt") @{
    spec        = $specContent;
    repo_tree   = $scaffoldTree;
    constraints = $constraints;
    package     = $packageName
}

$planOutput = Invoke-Claude -Prompt $planPrompt -Label "planning" -WorkingDirectory $projectDir -Turns 5
$implementationPlan = Get-AssistantText $planOutput

if ($ShowOutput) {
    $planOutput | Set-Content "MODEL_OUTPUT_planning.txt" -Encoding UTF8
    Write-Info "Saved planning output to MODEL_OUTPUT_planning.txt"
}
Write-Ok "Planning complete"

# ── Step 10: Generate source code and tests ───────────────────────────────────
Write-Step "Generating source code and tests with Claude Code (this may take a few minutes)..."

$repoTree = Get-DirectoryTree

$codePrompt = Render-Template (Join-Path $ScriptRoot "prompts\generate_code.txt") @{
    spec        = $specContent;
    repo_tree   = $repoTree;
    constraints = $constraints;
    package     = $packageName;
    plan        = $implementationPlan
}

# Snapshot files that must not be overwritten by the model
$pyprojectBackup = Get-Content "pyproject.toml" -Raw -Encoding UTF8
$protectedFiles = @("pyproject.toml", "README.md", ".vscode\settings.json", ".gitignore",
                    ".gitattributes", ".pre-commit-config.yaml", "CLAUDE.md")

$codeOutput = Invoke-Claude -Prompt $codePrompt -Label "code+test-generation" -WorkingDirectory $projectDir -Turns 50

if ($ShowOutput) {
    $codeOutput | Set-Content "MODEL_OUTPUT_code_generation.txt" -Encoding UTF8
    Write-Info "Saved raw model output to MODEL_OUTPUT_code_generation.txt"
}

$codeJson = Parse-ModelJson $codeOutput
if ($null -ne $codeJson) {
    Write-FilesFromModel -ModelOutput $codeJson -Label "code+test-generation"
} else {
    $codeOutput | Set-Content "MODEL_OUTPUT_code_generation.txt" -Encoding UTF8
    Write-Warn "Code generation output was not valid JSON. Saved raw output to MODEL_OUTPUT_code_generation.txt"
}

# Restore any protected files the model may have overwritten
$pyprojectCurrent = Get-Content "pyproject.toml" -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
if ($pyprojectCurrent -ne $pyprojectBackup) {
    Write-Warn "Model overwrote pyproject.toml — restoring original."
    $pyprojectBackup | Set-Content "pyproject.toml" -Encoding UTF8
    Remove-Bom "pyproject.toml"
}

# Verify source files were created
$generatedPyFiles = Get-ChildItem "src" -Recurse -Filter "*.py" -ErrorAction SilentlyContinue
if ($generatedPyFiles.Count -eq 0) {
    Write-Warn "Code generation may have failed — no .py files were created. Check the model output in MODEL_OUTPUT_code_generation.txt."
} else {
    Write-Info "Created $($generatedPyFiles.Count) source files: $($generatedPyFiles.Name -join ', ')"
}

# Ensure tests exist; if not, ask the model to generate them.
$testFiles = Get-ChildItem "tests" -Recurse -Filter "test_*.py" -ErrorAction SilentlyContinue
if ($testFiles.Count -eq 0) {
    Write-Info "No tests found; generating pytest tests from the generated source files..."

    $sourceModules = Get-ChildItem "src\$packageName" -Recurse -Filter "*.py" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne '__init__.py' }

    foreach ($module in $sourceModules) {
        $modulePath = $module.FullName.Substring((Get-Location).Path.Length + 1).Replace('\', '/')

        $testPrompt = Render-Template (Join-Path $ScriptRoot "prompts\write_tests.txt") @{ 
            module_path = $modulePath;
            spec = $specContent;
            constraints = $constraints;
        }

        $testOutput = Invoke-Claude -Prompt $testPrompt -Label "write-tests-$($module.BaseName)" -WorkingDirectory $projectDir -Turns 25
        if ($ShowOutput) {
            $testOutput | Add-Content "MODEL_OUTPUT_code_generation.txt" -Encoding UTF8
        }

        $testJson = Parse-ModelJson $testOutput
        if ($null -ne $testJson) {
            Write-FilesFromModel -ModelOutput $testJson -Label "write-tests-$($module.BaseName)"
        }
    }

    $testFiles = Get-ChildItem "tests" -Recurse -Filter "test_*.py" -ErrorAction SilentlyContinue
    if ($testFiles.Count -eq 0) {
        Write-Warn "No test files were generated. Check the model output in MODEL_OUTPUT_code_generation.txt."
    } else {
        Write-Info "Generated $($testFiles.Count) test files: $($testFiles.Name -join ', ')"
    }
}

# Run ruff natively — guaranteed cleanup regardless of whether the model ran it
$ErrorActionPreference = "SilentlyContinue"
$null = & ruff check . --fix 2>&1
$null = & ruff format . 2>&1
$ErrorActionPreference = "Stop"

& git add -A
& git commit -q -m "feat: generate source code and tests from spec" --allow-empty
Write-Ok "Source code and tests generated and committed"

# ── Step 11: Run tests and iterate ────────────────────────────────────────────
Write-Step "Running tests and fixing failures (up to $MaxFixAttempts attempts)..."

for ($attempt = 1; $attempt -le $MaxFixAttempts; $attempt++) {
    Write-Info "Test attempt $attempt/$MaxFixAttempts"

    $ErrorActionPreference = "SilentlyContinue"
    $testOutput = & pytest -x --tb=short 2>&1 | Out-String
    $ErrorActionPreference = "Stop"
    $testPassed = ($testOutput -match "\d+ passed") -and ($testOutput -notmatch "\d+ failed") -and ($testOutput -notmatch "\d+ error")

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
    $null = & ruff check . --fix 2>&1
    $null = & ruff format . 2>&1
    $ruffTestOutput = & pytest -x --tb=short 2>&1 | Out-String
    $ErrorActionPreference = "Stop"

    if (($ruffTestOutput -match "\d+ passed") -and ($ruffTestOutput -notmatch "\d+ failed") -and ($ruffTestOutput -notmatch "\d+ error")) {
        Write-Ok "Ruff auto-fix resolved failures (attempt $attempt)"
        & git add -A
        & git commit -q -m "fix: ruff auto-fix resolved test failures" --allow-empty
        break
    }
    $testOutput = $ruffTestOutput  # Use post-ruff output for Claude

    Write-Warn "Tests failing. Asking Claude to fix (attempt $attempt)..."

    $fixSummary = Get-TestFailureSummary $testOutput
    $depGraph   = Get-PythonDependencyGraph -PackageName $packageName -SrcDir "src"
    $fixTree    = Get-DirectoryTree

    if ($ModelProvider.ToLower() -eq "ollama") {
        # Ollama has no file tools — collect source + test content and inline it in the prompt
        $sourceContext = ""
        Get-ChildItem -Path "src","tests" -Recurse -Include "*.py" -ErrorAction SilentlyContinue | ForEach-Object {
            $relPath = $_.FullName.Substring((Get-Location).Path.Length + 1).Replace('\', '/')
            $fileContent = Get-Content $_.FullName -Raw -Encoding UTF8
            $sourceContext += "--- file: $relPath ---`n$fileContent`n`n"
        }
        $fixPrompt = Render-Template (Join-Path $ScriptRoot "prompts\fix_tests.txt") @{
            error_log  = $fixSummary
            source     = $sourceContext
            dep_graph  = $depGraph
            repo_tree  = $fixTree
        }
        $fixOutput = Invoke-Claude -Prompt $fixPrompt -Label "test-fix-$attempt" -WorkingDirectory $projectDir
        $fixJson = Parse-ModelJson $fixOutput
        if ($null -ne $fixJson) {
            Write-FilesFromModel -ModelOutput $fixJson -Label "test-fix-$attempt"
        }
    } else {
        $depGraphSection = if ($depGraph) { "`n`nDEPENDENCY GRAPH`n$depGraph" } else { "" }
        $fixPrompt = @"
The tests are failing. Here is the pytest output:

``````
$fixSummary
``````

PROJECT STRUCTURE
$fixTree
$depGraphSection

INSTRUCTIONS:
1. Read the failing test files AND the source files they test.
2. Determine if the bug is in the source code or the test code.
3. Fix the actual bugs - do NOT just make tests pass by weakening assertions.
4. If a test expectation is wrong (doesn't match the spec), fix the test.
5. If the source code doesn't match the spec, fix the source code.
6. Run: uv run ruff check . --fix && ruff format .
7. Run: uv run pytest -x --tb=short
8. Report the results.
"@
        Invoke-Claude -Prompt $fixPrompt -Label "test-fix-$attempt" -WorkingDirectory $projectDir
    }

    & git add -A
    & git commit -q -m "fix: test fixes (attempt $attempt)" --allow-empty
}

# ── Step 12: Final quality checks ─────────────────────────────────────────────
Write-Step "Running final quality checks (ruff, mypy, bandit, pip-audit, radon, vulture)..."

$ErrorActionPreference = "SilentlyContinue"
$null = & ruff check . --fix 2>&1
$null = & ruff format . 2>&1
$ErrorActionPreference = "Stop"

# mypy (with timeout — first run downloads type stubs)
$mypyJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    $env:PATH = $using:env:PATH
    & mypy src/ 2>&1 | Out-String
}
$mypyDone = Wait-Job $mypyJob -Timeout 60
if ($mypyDone) {
    $mypyOutput = Receive-Job $mypyJob
    if ($mypyOutput -match "error:") {
        Write-Warn "mypy found type errors (non-blocking):"
        ($mypyOutput -split "`n") | Where-Object { $_ -match "error:" } | Select-Object -First 10 | ForEach-Object { Write-Host $_ }
    } else {
        Write-Ok "mypy: no type errors"
    }
} else {
    Stop-Job $mypyJob
    Write-Warn "mypy timed out (60s) — run 'mypy src/' manually to check types"
}
Remove-Job $mypyJob -Force -ErrorAction SilentlyContinue

# bandit — security
$ErrorActionPreference = "SilentlyContinue"
$banditOutput = & bandit -c pyproject.toml -r src/ -f txt 2>&1 | Out-String
$ErrorActionPreference = "Stop"
if ($banditOutput -match "Severity: (Medium|High)") {
    Write-Warn "bandit found security issues (non-blocking):"
    ($banditOutput -split "`n") | Where-Object { $_ -match "Severity:|Issue:|Location:" } | Select-Object -First 15 | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Ok "bandit: no medium/high security issues"
}

# pip-audit — dependency vulnerabilities (runs with timeout; may be slow on restricted networks)
$auditJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    $env:PATH = $using:env:PATH
    & pip-audit 2>&1 | Out-String
}
$auditDone = Wait-Job $auditJob -Timeout 30
if ($auditDone) {
    $auditOutput = Receive-Job $auditJob
    if ($auditOutput -match "vulnerability|GHSA|CVE") {
        Write-Warn "pip-audit found vulnerable dependencies:"
        ($auditOutput -split "`n") | Where-Object { $_ -match "vulnerability|GHSA|CVE|Name" } | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" }
    } else {
        Write-Ok "pip-audit: no known vulnerabilities"
    }
} else {
    Stop-Job $auditJob
    Write-Warn "pip-audit timed out (30s) — run 'pip-audit' manually to check for vulnerabilities"
}
Remove-Job $auditJob -Force -ErrorAction SilentlyContinue

# radon — cyclomatic complexity (grade C+ = CC >= 11)
$ErrorActionPreference = "SilentlyContinue"
$radonOutput = & radon cc src/ -mi C 2>&1 | Out-String
$ErrorActionPreference = "Stop"
if ($radonOutput.Trim()) {
    Write-Warn "radon: complex functions detected (consider refactoring):"
    ($radonOutput -split "`n") | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Ok "radon: all functions within complexity limits"
}

# vulture — unused code
$ErrorActionPreference = "SilentlyContinue"
$vultureOutput = & vulture src/ --min-confidence 80 2>&1 | Out-String
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

