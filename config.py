"""
Configuration and constants for PAL MCP Server

This module centralizes all configuration settings for the PAL MCP Server.
It defines model configurations, token limits, temperature defaults, and other
constants used throughout the application.

Configuration values can be overridden by environment variables where appropriate.
"""

from utils.env import get_env

# Version and metadata
# These values are used in server responses and for tracking releases
# IMPORTANT: This is the single source of truth for version and author info
# Semantic versioning: MAJOR.MINOR.PATCH
__version__ = "9.8.2"
# Last update date in ISO format
__updated__ = "2025-12-15"
# Primary maintainer
__author__ = "Fahad Gilani"

# Model configuration
# DEFAULT_MODEL: The default model used for all AI operations
# This should be a stable, high-performance model suitable for code analysis
# Can be overridden by setting DEFAULT_MODEL environment variable
# Special value "auto" means Claude should pick the best model for each task
DEFAULT_MODEL = get_env("DEFAULT_MODEL", "auto") or "auto"

# Auto mode detection - when DEFAULT_MODEL is "auto", Claude picks the model
IS_AUTO_MODE = DEFAULT_MODEL.lower() == "auto"

# Each provider (gemini.py, openai.py, xai.py, dial.py, openrouter.py, custom.py, azure_openai.py)
# defines its own MODEL_CAPABILITIES
# with detailed descriptions. Tools use ModelProviderRegistry.get_available_model_names()
# to get models only from enabled providers (those with valid API keys).
#
# This architecture ensures:
# - No namespace collisions (models only appear when their provider is enabled)
# - API key-based filtering (prevents wrong models from being shown to Claude)
# - Proper provider routing (models route to the correct API endpoint)
# - Clean separation of concerns (providers own their model definitions)


# Default temperature for all tools.
# NOTE: Gemini 3.0 Pro notes suggest temperature should be set at 1.0
# in most cases. Lowering it can affect the models 'reasoning' abilities.
# Newer models / inference stacks are able to handle their randomness better.
DEFAULT_TEMPERATURE = 1.0

# Thinking Mode Defaults
# DEFAULT_THINKING_MODE_THINKDEEP: Default thinking depth for extended reasoning tool
# Higher modes use more computational budget but provide deeper analysis
DEFAULT_THINKING_MODE_THINKDEEP = get_env("DEFAULT_THINKING_MODE_THINKDEEP", "high") or "high"

# Consensus Tool Defaults
# Consensus timeout and rate limiting settings
DEFAULT_CONSENSUS_TIMEOUT = 120.0  # 2 minutes per model
DEFAULT_CONSENSUS_MAX_INSTANCES_PER_COMBINATION = 2

# NOTE: Consensus tool now uses sequential processing for MCP compatibility
# Concurrent processing was removed to avoid async pattern violations

# MCP Protocol Transport Limits
#
# IMPORTANT: This limit ONLY applies to the Claude CLI ↔ MCP Server transport boundary.
# It does NOT limit internal MCP Server operations like system prompts, file embeddings,
# conversation history, or content sent to external models (Gemini/OpenAI/OpenRouter).
#
# MCP Protocol Architecture:
# Claude CLI ←→ MCP Server ←→ External Model (Gemini/OpenAI/etc.)
#     ↑                              ↑
#     │                              │
# MCP transport                Internal processing
# (token limit from MAX_MCP_OUTPUT_TOKENS)    (No MCP limit - can be 1M+ tokens)
#
# MCP_PROMPT_SIZE_LIMIT: Maximum character size for USER INPUT crossing MCP transport
# The MCP protocol has a combined request+response limit controlled by MAX_MCP_OUTPUT_TOKENS.
# To ensure adequate space for MCP Server → Claude CLI responses, we limit user input
# to roughly 60% of the total token budget converted to characters. Larger user prompts
# must be sent as prompt.txt files to bypass MCP's transport constraints.
#
# Token to character conversion ratio: ~4 characters per token (average for code/text)
# Default allocation: 60% of tokens for input, 40% for response
#
# What IS limited by this constant:
# - request.prompt field content (user input from Claude CLI)
# - prompt.txt file content (alternative user input method)
# - Any other direct user input fields
#
# What is NOT limited by this constant:
# - System prompts added internally by tools
# - File content embedded by tools
# - Conversation history loaded from storage
# - Web search instructions or other internal additions
# - Complete prompts sent to external models (managed by model-specific token limits)
#
# This ensures MCP transport stays within protocol limits while allowing internal
# processing to use full model context windows (200K-1M+ tokens).


def _calculate_mcp_prompt_limit() -> int:
    """Calculate MCP prompt size limit based on MAX_MCP_OUTPUT_TOKENS.

    Allocates 60% of the token budget for input, at ~4 chars/token.
    Falls back to 60 000 characters (~15k tokens of a 25k total budget).
    """
    try:
        return int(int(get_env("MAX_MCP_OUTPUT_TOKENS")) * 0.6) * 4
    except (ValueError, TypeError):
        return 60_000


MCP_PROMPT_SIZE_LIMIT = _calculate_mcp_prompt_limit()

# Language/Locale Configuration
# LOCALE: Language/locale specification for AI responses
# When set, all AI tools will respond in the specified language while
# maintaining their analytical capabilities
# Examples: "fr-FR", "en-US", "zh-CN", "zh-TW", "ja-JP", "ko-KR", "es-ES",
# "de-DE", "it-IT", "pt-PT"
# Leave empty for default language (English)
LOCALE = get_env("LOCALE", "") or ""

# Threading configuration
# Simple in-memory conversation threading for stateless MCP environment
# Conversations persist only during the Claude session
