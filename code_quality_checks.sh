#!/bin/bash
set -e

echo "🔍 Running Code Quality Checks for PAL MCP Server (via uv)"
echo "================================================="

# Ensure uv
if ! command -v uv &> /dev/null; then
    echo "❌ uv not found! Please run ./run-server.sh to setup environment or install uv."
    exit 1
fi

# Sync dev dependencies just in case
echo "🔄 Ensuring environment is up to date..."
export UV_PROJECT_ENVIRONMENT=".pal_venv"
uv sync > /dev/null 2>&1 || echo "⚠️ uv sync warning (continuing...)"

# Step 1: Linting
echo "📋 Step 1: Running Linting and Formatting Checks"
echo "🔧 Running ruff linting with auto-fix..."
uv run ruff check --fix --exclude test_simulation_files --exclude .pal_venv

echo "🎨 Running black code formatting..."
uv run black . --exclude="test_simulation_files/" --exclude=".pal_venv/"

echo "📦 Running import sorting with isort..."
uv run isort . --skip-glob=".pal_venv/*" --skip-glob="test_simulation_files/*"

echo "✅ Verifying all linting passes..."
uv run ruff check --exclude test_simulation_files --exclude .pal_venv

echo "✅ Step 1 Complete: All linting and formatting checks passed!"
echo ""

# Step 2: Tests
echo "🧪 Step 2: Running Complete Unit Test Suite"
echo "🏃 Running unit tests (excluding integration tests)..."
uv run pytest tests/ -v -x -m "not integration"

echo "✅ Step 2 Complete: All unit tests passed!"
echo ""

echo "🎉 All Code Quality Checks Passed!"
