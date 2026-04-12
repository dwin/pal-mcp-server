"""Standalone model listing and selection helpers extracted from BaseTool.

These functions encapsulate model discovery, ranking, formatting, and
validation logic so that callers do not need a BaseTool instance.
"""

import logging
from typing import Any, Callable, Optional

from providers import ModelProviderRegistry
from shared_types import ToolModelCategory
from utils.env import get_env

logger = logging.getLogger(__name__)


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

    from providers.registry import ModelProviderRegistry

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


def get_ranked_model_summaries(tool_name: str, limit: int = 5) -> tuple[list[str], int, bool]:
    """Return formatted, ranked model summaries and restriction status.

    Args:
        tool_name: Name of the tool requesting summaries (unused in logic but
            kept for interface parity; callers may log it).
        limit: Maximum number of summaries to return.

    Returns:
        A tuple of (summary strings, total filtered count, has_restrictions).
    """

    ranked = collect_ranked_capabilities()

    # Build allowlist map (provider -> lowercase names) when restrictions are active
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

    return "Policy allows only \u2192 " + "; ".join(notes)


def format_available_models_list(tool_name: str) -> str:
    """Return a human-friendly list of available models or guidance when none found.

    Args:
        tool_name: Name of the tool requesting the list.
    """

    summaries, total, has_restrictions = get_ranked_model_summaries(tool_name)
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


def build_model_unavailable_message(model_name: str, tool_name: str, tool_category: ToolModelCategory) -> str:
    """Compose a consistent error message for unavailable model scenarios.

    Args:
        model_name: The model that was requested but is not available.
        tool_name: Name of the tool that encountered the issue.
        tool_category: The tool's model category for fallback suggestions.
    """

    suggested_model = ModelProviderRegistry.get_preferred_fallback_model(tool_category)
    available_models_text = format_available_models_list(tool_name)

    return (
        f"Model '{model_name}' is not available with current API keys. "
        f"Available models: {available_models_text}. "
        f"Suggested model for {tool_name}: '{suggested_model}' "
        f"(category: {tool_category.value}). If the user explicitly requested a model, you MUST use that exact name or report this error back\u2014do not substitute another model."
    )


def build_auto_mode_required_message(tool_name: str, tool_category: ToolModelCategory) -> str:
    """Compose the auto-mode prompt when an explicit model selection is required.

    Args:
        tool_name: Name of the tool requiring model selection.
        tool_category: The tool's model category for fallback suggestions.
    """

    suggested_model = ModelProviderRegistry.get_preferred_fallback_model(tool_category)
    available_models_text = format_available_models_list(tool_name)

    return (
        "Model parameter is required in auto mode. "
        f"Available models: {available_models_text}. "
        f"Suggested model for {tool_name}: '{suggested_model}' "
        f"(category: {tool_category.value}). When the user names a model, relay that exact name\u2014never swap in another option."
    )


def should_require_model_selection(model_name: str) -> bool:
    """Check if we should require the CLI to select a model at runtime.

    Args:
        model_name: The model name from the request or DEFAULT_MODEL.

    Returns:
        True if we should require model selection.
    """

    # Case 1: Model is explicitly "auto"
    if model_name.lower() == "auto":
        return True

    # Case 2: Requested model is not available
    from providers.registry import ModelProviderRegistry

    provider = ModelProviderRegistry.get_provider_for_model(model_name)
    if not provider:
        logger.warning(f"Model '{model_name}' is not available with current API keys. Requiring model selection.")
        return True

    return False


def get_available_models(
    openrouter_registry_getter: Callable[[], Any],
    custom_registry_getter: Callable[[], Any],
) -> list[str]:
    """Get list of models available from enabled providers.

    Only returns models from providers that have valid API keys configured.

    Args:
        openrouter_registry_getter: Callable that returns an OpenRouter model
            registry instance (e.g. ``BaseTool._get_openrouter_registry``).
        custom_registry_getter: Callable that returns a custom-endpoint model
            registry instance (e.g. ``BaseTool._get_custom_registry``).

    Returns:
        List of model names from enabled providers only.
    """

    from providers.registry import ModelProviderRegistry

    # Get models from enabled providers only (those with valid API keys)
    all_models = ModelProviderRegistry.get_available_model_names()

    # Add OpenRouter models and their aliases when OpenRouter is configured
    openrouter_key = get_env("OPENROUTER_API_KEY")
    if openrouter_key and openrouter_key != "your_openrouter_api_key_here":
        try:
            registry = openrouter_registry_getter()

            for alias in registry.list_aliases():
                if alias not in all_models:
                    all_models.append(alias)
        except Exception as exc:  # pragma: no cover - logged for observability
            logging.debug(f"Failed to add OpenRouter models to enum: {exc}")

    # Add custom models (and their aliases) when a custom endpoint is available
    custom_url = get_env("CUSTOM_API_URL")
    if custom_url:
        try:
            registry = custom_registry_getter()
            for alias in registry.list_aliases():
                if alias not in all_models:
                    all_models.append(alias)
        except Exception as exc:  # pragma: no cover - logged for observability
            logging.debug(f"Failed to add custom models to enum: {exc}")

    # Remove duplicates while preserving insertion order
    seen: set[str] = set()
    unique_models: list[str] = []
    for model in all_models:
        if model not in seen:
            seen.add(model)
            unique_models.append(model)

    return unique_models
