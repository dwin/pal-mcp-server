"""Schema-related tests for ConsensusTool."""

from tools.consensus import ConsensusTool


def test_consensus_models_field_includes_available_models(monkeypatch):
    """Consensus schema should surface available model guidance like single-model tools."""

    tool = ConsensusTool()

    monkeypatch.setattr(
        "tools.shared.model_utils.get_ranked_model_summaries",
        lambda limit=5: (["gemini-3.1-pro-preview (score 100, 1.0M ctx, thinking)"], 1, False),
    )
    monkeypatch.setattr("tools.shared.model_utils.get_restriction_note", lambda: None)

    schema = tool.get_input_schema()
    models_field_description = schema["properties"]["models"]["description"]

    assert "listmodels" in models_field_description
    assert "Top models" in models_field_description
