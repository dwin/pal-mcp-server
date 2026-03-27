<#
.SYNOPSIS
    Code quality checks script for PAL MCP server on Windows (via uv).
#>
#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipLinting,
    [switch]$VerboseOutput
)

$ErrorActionPreference = "Stop"

function Write-ColorText {
    param([string]$Text, [string]$Color = "White")
    Write-Host $Text -ForegroundColor $Color
}

function Write-Emoji {
    param([string]$Emoji, [string]$Text, [string]$Color = "White")
    Write-Host "$Emoji " -NoNewline
    Write-ColorText $Text -Color $Color
}

Write-Emoji "🔍" "Running Code Quality Checks for PAL MCP Server (via uv)" -Color Cyan
Write-ColorText "=================================================" -Color Cyan

if (!(Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Emoji "❌" "uv not found! Please run .\run-server.ps1 to setup environment." -Color Red
    exit 1
}

# Sync
Write-Emoji "🔄" "Ensuring environment is up to date..." -Color Cyan
$env:UV_PROJECT_ENVIRONMENT = ".pal_venv"
try {
    uv sync
} catch {
    Write-Warning "uv sync encountered an issue, continuing..."
}

Write-Host ""

# Step 1: Linting
if (!$SkipLinting) {
    Write-Emoji "📋" "Step 1: Running Linting and Formatting Checks" -Color Cyan
    
    try {
        Write-Emoji "🔧" "Running ruff linting with auto-fix..." -Color Yellow
        uv run ruff check --fix --exclude test_simulation_files --exclude .pal_venv
        if ($LASTEXITCODE -ne 0) { throw "Ruff failed" }

        Write-Emoji "🎨" "Running black code formatting..." -Color Yellow
        uv run black . --exclude=\"test_simulation_files/\" --exclude=\".pal_venv/\"
        if ($LASTEXITCODE -ne 0) { throw "Black failed" }

        Write-Emoji "📦" "Running import sorting with isort..." -Color Yellow
        uv run isort . --skip-glob=\".pal_venv/*\" --skip-glob=\"test_simulation_files/*\"
        if ($LASTEXITCODE -ne 0) { throw "Isort failed" }

        Write-Emoji "✅" "Verifying all linting passes..." -Color Yellow
        uv run ruff check --exclude test_simulation_files --exclude .pal_venv
        if ($LASTEXITCODE -ne 0) { throw "Ruff verify failed" }

        Write-Emoji "✅" "Step 1 Complete: All checks passed!" -Color Green
    } catch {
        Write-Emoji "❌" "Step 1 Failed: $_" -Color Red
        exit 1
    }
} else {
    Write-Emoji "⏭️" "Skipping linting" -Color Yellow
}

Write-Host ""

# Step 2: Tests
if (!$SkipTests) {
    Write-Emoji "🧪" "Step 2: Running Unit Tests" -Color Cyan
    try {
        $args = @("tests/", "-v", "-x", "-m", "not integration")
        if ($VerboseOutput) { $args += "--verbose" }
        
        uv run pytest @args
        if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
        Write-Emoji "✅" "Step 2 Complete: Tests passed!" -Color Green
    } catch {
        Write-Emoji "❌" "Step 2 Failed: $_" -Color Red
        exit 1
    }
}

Write-Host ""
Write-Emoji "🎉" "All Code Quality Checks Passed!" -Color Green