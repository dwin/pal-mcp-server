"""
Model utility functions extracted from BaseTool.

This module contains model discovery, formatting, and schema generation utilities
that were previously methods on BaseTool. Extracting them reduces BaseTool's method
count and separates model management concerns from the core tool interface.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

from providers import ModelProviderRegistry
from utils.env import get_env

if TYPE_CHECKING:
    from tools.models import ToolModelCategory

logger = logging.getLogger(__name__)

# Class-level cache for registries (shared across all callers)
_openrouter_registry_cache = None
_custom_registry_cache = None


def _get_openrouter_registry():
    """Get cached OpenRouter registry instance, creating if needed."""
    global _openrouter_registry_cache
    if _openrouter_registry_cache is None:
        from providers.registries.openrouter import OpenRouterModelRegistry

        _openrouter_registry_cache = OpenRouterModelRegistry()
        logger.debug("Created cached OpenRouter registry instance")
    return _openrouter_registry_cache


def _get_custom_registry():
    """Get cached custom-endpoint registry instance."""
    global _custom_registry_cache
    if _custom_registry_cache is None:
        from providers.registries.custom import CustomEndpointModelRegistry

        _custom_registry_cache = CustomEndpointModelRegistry()
        logger.debug("Created cached Custom registry instance")
    return _custom_registry_cache


def get_available_models() -> list[str]:
    """
    Get list of models available from enabled providers.

    Only returns models from providers that have valid API keys configured.
    """
    all_models = ModelProviderRegistry.get_available_model_names()

    # Add OpenRouter models
    openrouter_key = get_env("OPENROUTER_API_KEY")
    if openrouter_key and openrouter_key != "your_openrouter_api_key_here":
        try:
            registry = _get_openrouter_registry()
            for alias in registry.list_aliases():
                if alias not in all_models:
                    all_models.append(alias)
        except Exception as exc:
            logging.debug(f"Failed to add OpenRouter models to enum: {exc}")

    # Add custom models
    custom_url = get_env("CUSTOM_API_URL")
    if custom_url:
        try:
            registry = _get_custom_registry()
            for alias in registry.list_aliases():
                if alias not in all_models:
                    all_models.append(alias)
        except Exception as exc:
            logging.debug(f"Failed to add custom models to enum: {exc}")

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for model in all_models:
        if model not in seen:
            seen.add(model)
            unique.append(model)
    return unique


def format_context_window(tokens: int) -> Optional[str]:
    """Convert a raw context window into a short display string."""
    if not tokens or tokens <= 0:
        return None

    if tokens >= 1_000_000:
        if tokens % 1_000_000 == 0:
            return f"{tokens // 1_000_000}M ctx"
        return f"{tokens / 1_000_000:.1f}M ctx"

    if tokens >= 1_000:
        if tokens % 1_000 == 0:
            return f"{tokens // 1_000}K ctx"
        return f"{tokens / 1_000:.1f}K ctx"

    return f"{tokens} ctx"


def normalize_model_identifier(name: str) -> str:
    """Normalize model names for deduplication across providers."""
    normalized = name.lower()
    if ":" in normalized:
        normalized = normalized.split(":", 1)[0]
    if "/" in normalized:
        normalized = normalized.split("/", 1)[-1]
    return normalized


def collect_ranked_capabilities() -> list[tuple[int, str, Any]]:
    """Gather available model capabilities sorted by capability rank."""
    ranked: list[tuple[int, str, Any]] = []
    available = ModelProviderRegistry.get_available_models(respect_restrictions=True)

    for model_name, provider_type in available.items():
        provider = ModelProviderRegistry.get_provider(provider_type)
        if not provider:
            continue
        try:
            capabilities = provider.get_capabilities(model_name)
        except ValueError:
            continue
        rank = capabilities.get_effective_capability_rank()
        ranked.append((rank, model_name, capabilities))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked


def get_restriction_note() -> Optional[str]:
    """Return a string describing active per-provider allowlists, if any."""
    env_labels = {
        "OPENAI_ALLOWED_MODELS": "OpenAI",
        "GOOGLE_ALLOWED_MODELS": "Google",
        "XAI_ALLOWED_MODELS": "X.AI",
        "OPENROUTER_ALLOWED_MODELS": "OpenRouter",
        "DIAL_ALLOWED_MODELS": "DIAL",
    }

    notes: list[str] = []
    for env_var, label in env_labels.items():
        raw = get_env(env_var)
        if not raw:
            continue
        models = sorted({token.strip() for token in raw.split(",") if token.strip()})
        if not models:
            continue
        notes.append(f"{label}: {', '.join(models)}")

    if not notes:
        return None
    return "Policy allows only → " + "; ".join(notes)


def get_ranked_model_summaries(limit: int = 5) -> tuple[list[str], int, bool]:
    """Return formatted, ranked model summaries and restriction status."""
    ranked = collect_ranked_capabilities()

    # Build allowlist map
    allowed_map: dict[Any, set[str]] = {}
    try:
        from utils.model_restrictions import get_restriction_service

        restriction_service = get_restriction_service()
        if restriction_service:
            from providers.shared import ProviderType

            for provider_type in ProviderType:
                allowed = restriction_service.get_allowed_models(provider_type)
                if allowed:
                    allowed_map[provider_type] = {name.lower() for name in allowed if name}
    except Exception:
        allowed_map = {}

    filtered: list[tuple[int, str, Any]] = []
    seen_normalized: set[str] = set()

    for rank, model_name, capabilities in ranked:
        canonical_name = getattr(capabilities, "model_name", model_name)
        canonical_lower = canonical_name.lower()
        alias_lower = model_name.lower()
        provider_type = getattr(capabilities, "provider", None)

        if allowed_map:
            if provider_type not in allowed_map:
                continue
            allowed_set = allowed_map[provider_type]
            if canonical_lower not in allowed_set and alias_lower not in allowed_set:
                continue

        normalized = normalize_model_identifier(canonical_name)
        if normalized in seen_normalized:
            continue

        seen_normalized.add(normalized)
        filtered.append((rank, canonical_name, capabilities))

    summaries: list[str] = []
    for rank, canonical_name, capabilities in filtered[:limit]:
        details: list[str] = []

        context_str = format_context_window(capabilities.context_window)
        if context_str:
            details.append(context_str)

        if capabilities.supports_extended_thinking:
            details.append("thinking")

        if capabilities.allow_code_generation:
            details.append("code-gen")

        base = f"{canonical_name} (score {rank}"
        if details:
            base = f"{base}, {', '.join(details)}"
        summaries.append(f"{base})")

    return summaries, len(filtered), bool(allowed_map)


def format_available_models_list() -> str:
    """Return a human-friendly list of available models or guidance when none found."""
    summaries, total, has_restrictions = get_ranked_model_summaries()
    if not summaries:
        return (
            "No models detected. Configure provider credentials or set DEFAULT_MODEL to a valid option. "
            "If the user requested a specific model, respond with this notice instead of substituting another model."
        )
    display = "; ".join(summaries)
    remainder = total - len(summaries)
    if remainder > 0:
        display = f"{display}; +{remainder} more (use the `listmodels` tool for the full roster)"
    return display


def build_model_unavailable_message(tool_name: str, model_name: str, tool_category: "ToolModelCategory") -> str:
    """Compose a consistent error message for unavailable model scenarios."""
    suggested_model = ModelProviderRegistry.get_preferred_fallback_model(tool_category)
    available_models_text = format_available_models_list()

    return (
        f"Model '{model_name}' is not available with current API keys. "
        f"Available models: {available_models_text}. "
        f"Suggested model for {tool_name}: '{suggested_model}' "
        f"(category: {tool_category.value}). If the user explicitly requested a model, you MUST use that exact name or report this error back—do not substitute another model."
    )


def build_auto_mode_required_message(tool_name: str, tool_category: "ToolModelCategory") -> str:
    """Compose the auto-mode prompt when an explicit model selection is required."""
    suggested_model = ModelProviderRegistry.get_preferred_fallback_model(tool_category)
    available_models_text = format_available_models_list()

    return (
        "Model parameter is required in auto mode. "
        f"Available models: {available_models_text}. "
        f"Suggested model for {tool_name}: '{suggested_model}' "
        f"(category: {tool_category.value}). When the user names a model, relay that exact name—never swap in another option."
    )


def build_model_field_schema(tool) -> dict[str, Any]:
    """
    Generate the model field schema based on auto mode configuration.

    Args:
        tool: A tool instance with get_name(), is_effective_auto_mode(), and get_model_category() methods
    """
    from config import DEFAULT_MODEL

    if tool.is_effective_auto_mode():
        description = (
            "Currently in auto model selection mode. CRITICAL: When the user names a model, you MUST use that exact name unless the server rejects it. "
            "If no model is provided, you may use the `listmodels` tool to review options and select an appropriate match."
        )
        summaries, total, restricted = get_ranked_model_summaries()
        remainder = max(0, total - len(summaries))
        if summaries:
            top_line = "; ".join(summaries)
            label = "Allowed models" if restricted else "Top models"
            if remainder > 0:
                top_line = f"{label}: {top_line}; +{remainder} more via `listmodels`."
            else:
                top_line = f"{label}: {top_line}."
            description = f"{description} {top_line}"

        restriction_note = get_restriction_note()
        if restriction_note and (remainder > 0 or not summaries):
            description = f"{description} {restriction_note}."
        return {"type": "string", "description": description}

    description = (
        f"The default model is '{DEFAULT_MODEL}'. Override only when the user explicitly requests a different model, and use that exact name. "
        "If the requested model fails validation, surface the server error instead of substituting another model. When unsure, use the `listmodels` tool for details."
    )
    summaries, total, restricted = get_ranked_model_summaries()
    remainder = max(0, total - len(summaries))
    if summaries:
        top_line = "; ".join(summaries)
        label = "Allowed models" if restricted else "Preferred alternatives"
        if remainder > 0:
            top_line = f"{label}: {top_line}; +{remainder} more via `listmodels`."
        else:
            top_line = f"{label}: {top_line}."
        description = f"{description} {top_line}"

    restriction_note = get_restriction_note()
    if restriction_note and (remainder > 0 or not summaries):
        description = f"{description} {restriction_note}."

    return {"type": "string", "description": description}
