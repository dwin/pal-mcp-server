"""
Tests verifying that dead code identified in issue #23 has been removed.

These tests serve as guardrails to prevent re-introduction of unused functions
and deprecated patterns.
"""

import inspect


class TestFileTypesDeadCodeRemoved:
    """Verify unused functions were removed from utils/file_types.py."""

    def test_is_code_file_removed(self):
        """is_code_file() had zero references — should be removed."""
        import utils.file_types as ft

        assert not hasattr(ft, "is_code_file"), "Dead function is_code_file still exists in file_types.py"

    def test_is_binary_file_removed(self):
        """is_binary_file() had zero references — should be removed."""
        import utils.file_types as ft

        assert not hasattr(ft, "is_binary_file"), "Dead function is_binary_file still exists in file_types.py"

    def test_get_file_category_removed(self):
        """get_file_category() had zero references — should be removed."""
        import utils.file_types as ft

        assert not hasattr(ft, "get_file_category"), "Dead function get_file_category still exists in file_types.py"

    def test_file_categories_dict_removed(self):
        """FILE_CATEGORIES dict was only used by get_file_category — should be removed."""
        import utils.file_types as ft

        assert not hasattr(ft, "FILE_CATEGORIES"), "Dead constant FILE_CATEGORIES still exists in file_types.py"

    def test_kept_functions_still_exist(self):
        """Functions that ARE used must still exist."""
        import utils.file_types as ft

        assert hasattr(ft, "is_text_file")
        assert hasattr(ft, "get_token_estimation_ratio")
        assert hasattr(ft, "get_image_mime_type")


class TestClientInfoDeadCodeRemoved:
    """Verify unused functions were removed from utils/client_info.py."""

    def test_get_client_friendly_name_removed(self):
        """get_client_friendly_name() had zero external callers — should be removed."""
        import utils.client_info as ci

        assert not hasattr(
            ci, "get_client_friendly_name"
        ), "Dead function get_client_friendly_name still exists in client_info.py"

    def test_log_client_info_removed(self):
        """log_client_info() had zero callers — should be removed."""
        import utils.client_info as ci

        assert not hasattr(ci, "log_client_info"), "Dead function log_client_info still exists in client_info.py"

    def test_kept_functions_still_exist(self):
        """Functions that ARE used must still exist."""
        import utils.client_info as ci

        assert hasattr(ci, "get_client_info_from_context")
        assert hasattr(ci, "format_client_info")
        assert hasattr(ci, "get_cached_client_info")
        assert hasattr(ci, "get_friendly_name")


class TestFileUtilsDeadCodeRemoved:
    """Verify dead code was removed from utils/file_utils.py."""

    def test_is_builtin_custom_models_config_removed(self):
        """_is_builtin_custom_models_config() had zero callers — should be removed."""
        import utils.file_utils as fu

        assert not hasattr(
            fu, "_is_builtin_custom_models_config"
        ), "Dead function _is_builtin_custom_models_config still exists in file_utils.py"


class TestProviderInfoExtraction:
    """Verify provider info extraction is consolidated (not duplicated)."""

    def test_extract_provider_name_exists(self):
        """A shared _extract_provider_name utility should exist in tools/simple/base.py."""
        from tools.simple.base import SimpleTool

        assert hasattr(
            SimpleTool, "_extract_provider_name"
        ), "Missing _extract_provider_name — provider name extraction should be consolidated"

    def test_extract_provider_name_handles_string(self):
        """_extract_provider_name should handle string provider values."""
        from tools.simple.base import SimpleTool

        result = SimpleTool._extract_provider_name("openai")
        assert result == "openai"

    def test_extract_provider_name_handles_none(self):
        """_extract_provider_name should handle None."""
        from tools.simple.base import SimpleTool

        result = SimpleTool._extract_provider_name(None)
        assert result is None

    def test_extract_provider_name_handles_provider_object(self):
        """_extract_provider_name should handle provider objects with get_provider_type()."""
        from unittest.mock import Mock

        from providers.shared import ProviderType
        from tools.simple.base import SimpleTool

        mock_provider = Mock()
        mock_provider.get_provider_type.return_value = ProviderType.OPENAI
        result = SimpleTool._extract_provider_name(mock_provider)
        assert result == "openai"

    def test_extract_provider_name_handles_object_without_get_provider_type(self):
        """_extract_provider_name should fall back to str() for unknown objects."""
        from tools.simple.base import SimpleTool

        class FakeProvider:
            def __str__(self):
                return "custom-provider"

        result = SimpleTool._extract_provider_name(FakeProvider())
        assert result == "custom-provider"


class TestCodereviewConfidenceExcluded:
    """Verify confidence field is excluded from CodeReviewRequest serialization."""

    def test_confidence_excluded_from_serialization(self):
        """The confidence field should be excluded from model_dump output."""
        from tools.codereview import CodeReviewRequest

        request = CodeReviewRequest(
            step="test",
            step_number=2,
            total_steps=2,
            next_step_required=False,
            findings="test",
        )
        dumped = request.model_dump()
        assert "confidence" not in dumped, "confidence should be excluded from CodeReviewRequest serialization"

    def test_deprecated_comment_removed(self):
        """The 'deprecated' wording should be cleaned up."""
        import inspect

        from tools.codereview import CodeReviewRequest

        source = inspect.getsource(CodeReviewRequest)
        assert "Deprecated confidence" not in source


class TestTodoMarkersResolved:
    """Verify unfinished TODO markers were resolved."""

    def test_model_context_todo_resolved(self):
        """The TODO for model-specific tokenizers should be resolved or cleaned up."""
        import utils.model_context

        source = inspect.getsource(utils.model_context)
        assert (
            "TODO: Integrate model-specific tokenizers" not in source
        ), "Unfinished TODO still present in model_context.py"
