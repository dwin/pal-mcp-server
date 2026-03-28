"""
Schema snapshot tests for workflow tools.

These tests capture the current MCP input schema for each workflow tool and
assert that refactoring does not inadvertently change the schema structure,
property names, required fields, or field types. Description text changes
are allowed (and expected during consolidation), but structural changes
are flagged.
"""

import pytest


def _get_tool_instance(tool_name):
    """Instantiate a workflow tool by name."""
    tool_map = {
        "debug": ("tools.debug", "DebugIssueTool"),
        "codereview": ("tools.codereview", "CodeReviewTool"),
        "refactor": ("tools.refactor", "RefactorTool"),
        "precommit": ("tools.precommit", "PrecommitTool"),
        "analyze": ("tools.analyze", "AnalyzeTool"),
        "docgen": ("tools.docgen", "DocgenTool"),
        "planner": ("tools.planner", "PlannerTool"),
        "secaudit": ("tools.secaudit", "SecauditTool"),
        "testgen": ("tools.testgen", "TestGenTool"),
        "tracer": ("tools.tracer", "TracerTool"),
        "thinkdeep": ("tools.thinkdeep", "ThinkDeepTool"),
        "consensus": ("tools.consensus", "ConsensusTool"),
    }
    module_path, class_name = tool_map[tool_name]
    import importlib

    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls()


# Expected schema structure per tool: required fields and property names.
# Captured from actual tool output before consolidation refactor.
EXPECTED_SCHEMAS = {
    "debug": {
        "required": ["findings", "model", "next_step_required", "step", "step_number", "total_steps"],
        "properties": {
            "confidence",
            "continuation_id",
            "files_checked",
            "findings",
            "hypothesis",
            "images",
            "issues_found",
            "model",
            "next_step_required",
            "relevant_context",
            "relevant_files",
            "step",
            "step_number",
            "temperature",
            "thinking_mode",
            "total_steps",
            "use_assistant_model",
        },
    },
    "codereview": {
        "required": ["findings", "model", "next_step_required", "step", "step_number", "total_steps"],
        "properties": {
            "confidence",
            "continuation_id",
            "files_checked",
            "findings",
            "focus_on",
            "hypothesis",
            "images",
            "issues_found",
            "model",
            "next_step_required",
            "relevant_context",
            "relevant_files",
            "review_type",
            "review_validation_type",
            "severity_filter",
            "standards",
            "step",
            "step_number",
            "temperature",
            "thinking_mode",
            "total_steps",
            "use_assistant_model",
        },
    },
    "refactor": {
        "required": ["findings", "model", "next_step_required", "step", "step_number", "total_steps"],
        "properties": {
            "confidence",
            "continuation_id",
            "files_checked",
            "findings",
            "focus_areas",
            "hypothesis",
            "images",
            "issues_found",
            "model",
            "next_step_required",
            "refactor_type",
            "relevant_context",
            "relevant_files",
            "step",
            "step_number",
            "style_guide_examples",
            "temperature",
            "thinking_mode",
            "total_steps",
            "use_assistant_model",
        },
    },
    "precommit": {
        "required": ["findings", "model", "next_step_required", "step", "step_number", "total_steps"],
        "properties": {
            "compare_to",
            "confidence",
            "continuation_id",
            "files_checked",
            "findings",
            "focus_on",
            "hypothesis",
            "images",
            "include_staged",
            "include_unstaged",
            "issues_found",
            "model",
            "next_step_required",
            "path",
            "precommit_type",
            "relevant_context",
            "relevant_files",
            "severity_filter",
            "step",
            "step_number",
            "temperature",
            "thinking_mode",
            "total_steps",
            "use_assistant_model",
        },
    },
    "analyze": {
        "required": ["findings", "model", "next_step_required", "step", "step_number", "total_steps"],
        "properties": {
            "analysis_type",
            "confidence",
            "continuation_id",
            "files_checked",
            "findings",
            "images",
            "issues_found",
            "model",
            "next_step_required",
            "output_format",
            "relevant_context",
            "relevant_files",
            "step",
            "step_number",
            "temperature",
            "thinking_mode",
            "total_steps",
            "use_assistant_model",
        },
    },
    "docgen": {
        "required": [
            "comments_on_complex_logic",
            "document_complexity",
            "document_flow",
            "findings",
            "next_step_required",
            "num_files_documented",
            "step",
            "step_number",
            "total_files_to_document",
            "total_steps",
            "update_existing",
        ],
        "properties": {
            "comments_on_complex_logic",
            "continuation_id",
            "document_complexity",
            "document_flow",
            "findings",
            "issues_found",
            "next_step_required",
            "num_files_documented",
            "relevant_context",
            "relevant_files",
            "step",
            "step_number",
            "total_files_to_document",
            "total_steps",
            "update_existing",
            "use_assistant_model",
        },
    },
    "planner": {
        "required": ["model", "next_step_required", "step", "step_number", "total_steps"],
        "properties": {
            "branch_from_step",
            "branch_id",
            "continuation_id",
            "is_branch_point",
            "is_step_revision",
            "model",
            "more_steps_needed",
            "next_step_required",
            "revises_step_number",
            "step",
            "step_number",
            "total_steps",
            "use_assistant_model",
        },
    },
    "secaudit": {
        "required": ["findings", "model", "next_step_required", "step", "step_number", "total_steps"],
        "properties": {
            "audit_focus",
            "compliance_requirements",
            "confidence",
            "continuation_id",
            "files_checked",
            "findings",
            "hypothesis",
            "images",
            "issues_found",
            "model",
            "next_step_required",
            "relevant_context",
            "relevant_files",
            "security_scope",
            "severity_filter",
            "step",
            "step_number",
            "temperature",
            "thinking_mode",
            "threat_level",
            "total_steps",
            "use_assistant_model",
        },
    },
    "testgen": {
        "required": ["findings", "model", "next_step_required", "step", "step_number", "total_steps"],
        "properties": {
            "confidence",
            "continuation_id",
            "files_checked",
            "findings",
            "hypothesis",
            "images",
            "issues_found",
            "model",
            "next_step_required",
            "relevant_context",
            "relevant_files",
            "step",
            "step_number",
            "temperature",
            "thinking_mode",
            "total_steps",
            "use_assistant_model",
        },
    },
    "tracer": {
        "required": [
            "findings",
            "model",
            "next_step_required",
            "step",
            "step_number",
            "target_description",
            "total_steps",
            "trace_mode",
        ],
        "properties": {
            "confidence",
            "continuation_id",
            "files_checked",
            "findings",
            "images",
            "model",
            "next_step_required",
            "relevant_context",
            "relevant_files",
            "step",
            "step_number",
            "target_description",
            "total_steps",
            "trace_mode",
            "use_assistant_model",
        },
    },
    "thinkdeep": {
        "required": ["findings", "model", "next_step_required", "step", "step_number", "total_steps"],
        "properties": {
            "confidence",
            "continuation_id",
            "files_checked",
            "findings",
            "focus_areas",
            "hypothesis",
            "images",
            "issues_found",
            "model",
            "next_step_required",
            "problem_context",
            "relevant_context",
            "relevant_files",
            "step",
            "step_number",
            "temperature",
            "thinking_mode",
            "total_steps",
            "use_assistant_model",
        },
    },
    "consensus": {
        "required": ["findings", "next_step_required", "step", "step_number", "total_steps"],
        "properties": {
            "continuation_id",
            "current_model_index",
            "findings",
            "images",
            "model_responses",
            "models",
            "next_step_required",
            "relevant_files",
            "step",
            "step_number",
            "total_steps",
            "use_assistant_model",
        },
    },
}


@pytest.mark.parametrize("tool_name", list(EXPECTED_SCHEMAS.keys()))
def test_schema_properties_match(tool_name):
    """Assert that each tool's schema has the expected property names."""
    tool = _get_tool_instance(tool_name)
    schema = tool.get_input_schema()
    actual_props = set(schema.get("properties", {}).keys())
    expected_props = EXPECTED_SCHEMAS[tool_name]["properties"]
    assert actual_props == expected_props, (
        f"{tool_name} schema properties mismatch.\n"
        f"  Missing: {expected_props - actual_props}\n"
        f"  Extra: {actual_props - expected_props}"
    )


@pytest.mark.parametrize("tool_name", list(EXPECTED_SCHEMAS.keys()))
def test_schema_required_fields_match(tool_name):
    """Assert that each tool's schema has the expected required fields.

    The 'model' field is conditionally required based on provider configuration,
    so we exclude it from comparison to avoid environment-dependent failures.
    """
    tool = _get_tool_instance(tool_name)
    schema = tool.get_input_schema()
    # Exclude 'model' from comparison — it's conditionally required based on env config
    actual_required = sorted(f for f in schema.get("required", []) if f != "model")
    expected_required = sorted(f for f in EXPECTED_SCHEMAS[tool_name]["required"] if f != "model")
    assert actual_required == expected_required, (
        f"{tool_name} required fields mismatch (excluding 'model').\n"
        f"  Expected: {expected_required}\n"
        f"  Actual: {actual_required}"
    )


@pytest.mark.parametrize("tool_name", list(EXPECTED_SCHEMAS.keys()))
def test_schema_field_types_preserved(tool_name):
    """Assert that schema field types have not changed."""
    tool = _get_tool_instance(tool_name)
    schema = tool.get_input_schema()
    props = schema.get("properties", {})

    # Check core workflow field types that must not change
    type_checks = {
        "step": "string",
        "step_number": "integer",
        "total_steps": "integer",
        "next_step_required": "boolean",
        "findings": "string",
    }

    for field_name, expected_type in type_checks.items():
        if field_name in props:
            actual_type = props[field_name].get("type")
            assert (
                actual_type == expected_type
            ), f"{tool_name}.{field_name}: expected type '{expected_type}', got '{actual_type}'"
