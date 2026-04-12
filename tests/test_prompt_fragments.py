"""
Tests for systemprompts/fragments.py – verify shared fragments are correctly
composed into every prompt that uses them.

Each test imports the final prompt constant and asserts that the corresponding
fragment string is present verbatim.  This catches accidental drift if a prompt
is edited to inline its own copy instead of referencing the shared fragment.
"""

from systemprompts.analyze_prompt import ANALYZE_PROMPT
from systemprompts.chat_prompt import CHAT_PROMPT
from systemprompts.codereview_prompt import CODEREVIEW_PROMPT
from systemprompts.consensus_prompt import CONSENSUS_PROMPT
from systemprompts.debug_prompt import DEBUG_ISSUE_PROMPT
from systemprompts.fragments import (
    CRITICAL_LINE_NUMBER_INSTRUCTIONS,
    CRITICAL_LINE_NUMBER_INSTRUCTIONS_BRIEF,
    FILES_REQUIRED_JSON,
    FOCUSED_REVIEW_REQUIRED_JSON,
    SCOPE_CONTROL,
    SEVERITY_DEFINITIONS,
)
from systemprompts.planner_prompt import PLANNER_PROMPT
from systemprompts.precommit_prompt import PRECOMMIT_PROMPT
from systemprompts.refactor_prompt import REFACTOR_PROMPT
from systemprompts.secaudit_prompt import SECAUDIT_PROMPT
from systemprompts.testgen_prompt import TESTGEN_PROMPT
from systemprompts.thinkdeep_prompt import THINKDEEP_PROMPT
from systemprompts.tracer_prompt import TRACER_PROMPT


class TestCriticalLineNumberInstructions:
    """Every prompt that references CRITICAL_LINE_NUMBER_INSTRUCTIONS (full)
    must contain it verbatim."""

    def test_analyze_prompt(self):
        assert CRITICAL_LINE_NUMBER_INSTRUCTIONS in ANALYZE_PROMPT

    def test_chat_prompt(self):
        assert CRITICAL_LINE_NUMBER_INSTRUCTIONS in CHAT_PROMPT

    def test_consensus_prompt(self):
        assert CRITICAL_LINE_NUMBER_INSTRUCTIONS in CONSENSUS_PROMPT

    def test_debug_prompt(self):
        assert CRITICAL_LINE_NUMBER_INSTRUCTIONS in DEBUG_ISSUE_PROMPT

    def test_planner_prompt(self):
        assert CRITICAL_LINE_NUMBER_INSTRUCTIONS in PLANNER_PROMPT

    def test_refactor_prompt(self):
        assert CRITICAL_LINE_NUMBER_INSTRUCTIONS in REFACTOR_PROMPT

    def test_secaudit_prompt(self):
        assert CRITICAL_LINE_NUMBER_INSTRUCTIONS in SECAUDIT_PROMPT

    def test_testgen_prompt(self):
        assert CRITICAL_LINE_NUMBER_INSTRUCTIONS in TESTGEN_PROMPT

    def test_thinkdeep_prompt(self):
        assert CRITICAL_LINE_NUMBER_INSTRUCTIONS in THINKDEEP_PROMPT

    def test_tracer_prompt(self):
        assert CRITICAL_LINE_NUMBER_INSTRUCTIONS in TRACER_PROMPT


class TestCriticalLineNumberInstructionsBrief:
    """Prompts that use the brief variant."""

    def test_codereview_prompt(self):
        assert CRITICAL_LINE_NUMBER_INSTRUCTIONS_BRIEF in CODEREVIEW_PROMPT

    def test_precommit_prompt(self):
        assert CRITICAL_LINE_NUMBER_INSTRUCTIONS_BRIEF in PRECOMMIT_PROMPT


class TestFilesRequiredJSON:
    """The files_required_to_continue JSON block must appear in every prompt
    that offers the 'more info needed' escape hatch."""

    def test_analyze_prompt(self):
        assert FILES_REQUIRED_JSON in ANALYZE_PROMPT

    def test_chat_prompt(self):
        assert FILES_REQUIRED_JSON in CHAT_PROMPT

    def test_codereview_prompt(self):
        assert FILES_REQUIRED_JSON in CODEREVIEW_PROMPT

    def test_consensus_prompt(self):
        assert FILES_REQUIRED_JSON in CONSENSUS_PROMPT

    def test_debug_prompt(self):
        assert FILES_REQUIRED_JSON in DEBUG_ISSUE_PROMPT

    def test_planner_prompt(self):
        assert FILES_REQUIRED_JSON in PLANNER_PROMPT

    def test_precommit_prompt(self):
        assert FILES_REQUIRED_JSON in PRECOMMIT_PROMPT

    def test_refactor_prompt(self):
        assert FILES_REQUIRED_JSON in REFACTOR_PROMPT

    def test_secaudit_prompt(self):
        assert FILES_REQUIRED_JSON in SECAUDIT_PROMPT

    def test_testgen_prompt(self):
        assert FILES_REQUIRED_JSON in TESTGEN_PROMPT

    def test_thinkdeep_prompt(self):
        assert FILES_REQUIRED_JSON in THINKDEEP_PROMPT

    def test_tracer_prompt(self):
        assert FILES_REQUIRED_JSON in TRACER_PROMPT


class TestSeverityDefinitions:
    """SEVERITY_DEFINITIONS must appear in prompts that define the 4-level scale."""

    def test_codereview_prompt(self):
        assert SEVERITY_DEFINITIONS in CODEREVIEW_PROMPT


class TestScopeControl:
    """SCOPE_CONTROL must appear in prompts that restrict scope."""

    def test_refactor_prompt(self):
        assert SCOPE_CONTROL in REFACTOR_PROMPT


class TestFocusedReviewRequiredJSON:
    """The focused_review_required JSON must appear in review-type prompts."""

    def test_codereview_prompt(self):
        assert FOCUSED_REVIEW_REQUIRED_JSON in CODEREVIEW_PROMPT

    def test_precommit_prompt(self):
        assert FOCUSED_REVIEW_REQUIRED_JSON in PRECOMMIT_PROMPT


class TestFragmentConsistency:
    """Verify fragments are well-formed and non-empty."""

    def test_fragments_are_nonempty(self):
        assert len(CRITICAL_LINE_NUMBER_INSTRUCTIONS) > 100
        assert len(CRITICAL_LINE_NUMBER_INSTRUCTIONS_BRIEF) > 100
        assert len(FILES_REQUIRED_JSON) > 50
        assert len(SEVERITY_DEFINITIONS) > 50
        assert len(SCOPE_CONTROL) > 50
        assert len(FOCUSED_REVIEW_REQUIRED_JSON) > 50

    def test_files_required_json_is_valid_json_template(self):
        assert '"status": "files_required_to_continue"' in FILES_REQUIRED_JSON
        assert '"mandatory_instructions"' in FILES_REQUIRED_JSON
        assert '"files_needed"' in FILES_REQUIRED_JSON

    def test_focused_review_json_is_valid_json_template(self):
        assert '"status": "focused_review_required"' in FOCUSED_REVIEW_REQUIRED_JSON
        assert '"reason"' in FOCUSED_REVIEW_REQUIRED_JSON
        assert '"suggestion"' in FOCUSED_REVIEW_REQUIRED_JSON

    def test_severity_definitions_has_all_levels(self):
        assert "CRITICAL" in SEVERITY_DEFINITIONS
        assert "HIGH" in SEVERITY_DEFINITIONS
        assert "MEDIUM" in SEVERITY_DEFINITIONS
        assert "LOW" in SEVERITY_DEFINITIONS
