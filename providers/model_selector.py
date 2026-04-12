"""Centralised model selection and resolution.

This module provides a single entry-point for all model selection decisions
made by the MCP server.  Prior to this consolidation the same fallback logic
was duplicated across ``server.py`` (5 call-sites) and ``tools/shared/base_tool.py``.

Typical usage::

    from providers.model_selector import ModelSelector

    # Resolve auto-mode or validate an explicit model name
    model_name, provider = ModelSelector.resolve_and_validate(
        model_name, tool_category, tool_name,
    )

    # Simple fallback for conversation reconstruction
    fallback = ModelSelector.resolve_fallback(tool_category)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from shared_types import ToolModelCategory

if TYPE_CHECKING:
    from .base import ModelProvider

logger = logging.getLogger(__name__)


class ModelSelector:
    """Single source of truth for model resolution and fallback logic.

    Every method is a classmethod so the selector can be used without
    instantiation, mirroring the existing ``ModelProviderRegistry`` API style.
    """

    # ------------------------------------------------------------------
    # Core resolution
    # ------------------------------------------------------------------

    @classmethod
    def resolve_fallback(
        cls,
        tool_category: ToolModelCategory | None = None,
    ) -> str | None:
        """Return the best available model for *tool_category*.

        This consolidates the repeated pattern from ``server.py`` where
        ``get_preferred_fallback_model()`` is called, and on failure the
        first available model name is used as a last resort.

        Returns:
            A model name string, or ``None`` when no provider is configured.
        """
        from .registry import ModelProviderRegistry

        try:
            return ModelProviderRegistry.get_preferred_fallback_model(tool_category)
        except Exception:  # pragma: no cover - defensive
            logger.debug("get_preferred_fallback_model raised; trying first available model")

        available = ModelProviderRegistry.get_available_model_names()
        if available:
            return available[0]

        return None

    @classmethod
    def resolve_and_validate(
        cls,
        model_name: str,
        tool_category: ToolModelCategory | None = None,
        tool_name: str | None = None,
    ) -> tuple[str, ModelProvider]:
        """Resolve *model_name* to a concrete model and its provider.

        Handles:
        * ``"auto"`` → delegates to :meth:`resolve_fallback`
        * Explicit model → validates via ``get_provider_for_model``
        * Unavailable model → raises ``ValueError`` with suggestion

        Returns:
            ``(resolved_model_name, provider)`` tuple.

        Raises:
            ValueError: when the model cannot be resolved.
        """
        from .registry import ModelProviderRegistry

        # Auto-mode resolution
        if model_name.lower() == "auto":
            resolved = cls.resolve_fallback(tool_category)
            if resolved is None:
                raise ValueError("Auto mode failed: no models available from any provider.")
            logger.info(
                "Auto mode resolved to %s for %s (category: %s)",
                resolved,
                tool_name or "unknown",
                (tool_category or ToolModelCategory.BALANCED).value,
            )
            provider = ModelProviderRegistry.get_provider_for_model(resolved)
            if provider is None:  # pragma: no cover - should not happen after resolve_fallback
                raise ValueError(f"Auto mode resolved to '{resolved}' but no provider accepted it.")
            return resolved, provider

        # Explicit model validation
        provider = ModelProviderRegistry.get_provider_for_model(model_name)
        if provider is not None:
            return model_name, provider

        # Model not available – build a helpful error
        available_models = list(ModelProviderRegistry.get_available_models(respect_restrictions=True).keys())
        suggested = cls.resolve_fallback(tool_category)
        tool_label = tool_name or "this tool"

        raise ValueError(
            f"Model '{model_name}' is not available with current API keys. "
            f"Available models: {', '.join(available_models)}. "
            f"Suggested model for {tool_label}: '{suggested}' "
            f"(category: {(tool_category or ToolModelCategory.BALANCED).value})"
        )

    # ------------------------------------------------------------------
    # Helpers for conversation reconstruction
    # ------------------------------------------------------------------

    @classmethod
    def resolve_for_context_reconstruction(
        cls,
        model_name: str | None,
        tool_category: ToolModelCategory | None = None,
    ) -> str:
        """Resolve a model suitable for rebuilding conversation context.

        This replaces the three near-identical fallback blocks that appeared
        in ``server.py``'s ``_reconstruct_conversation_context``.

        Args:
            model_name: The model from the previous turn (may be stale/unavailable).
            tool_category: Category hint for fallback selection.

        Returns:
            A valid model name string.

        Raises:
            ValueError: when no model can be resolved at all.
        """
        from .registry import ModelProviderRegistry

        # If we already have a valid model, verify it's still available
        if model_name:
            provider = ModelProviderRegistry.get_provider_for_model(model_name)
            if provider is not None:
                return model_name

            logger.debug(
                "Model '%s' unavailable for context reconstruction; resolving fallback",
                model_name,
            )

        # Try category-aware fallback
        fallback = cls.resolve_fallback(tool_category)
        if fallback is not None:
            return fallback

        if model_name:
            raise ValueError(
                f"Conversation continuation failed: model '{model_name}' is not available "
                "with current API keys and no fallback models are configured."
            )
        raise ValueError("Conversation continuation failed: no available models detected for context reconstruction.")
