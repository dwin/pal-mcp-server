"""
Reusable system-prompt fragments.

Shared instruction blocks that appear across multiple tool prompts are defined
here once so that every prompt composes from a single source of truth.  To use
a fragment, import the constant and concatenate it into your prompt string.
"""

# ---------------------------------------------------------------------------
# Line-number reference instructions
# ---------------------------------------------------------------------------

CRITICAL_LINE_NUMBER_INSTRUCTIONS = (
    "CRITICAL LINE NUMBER INSTRUCTIONS\n"
    'Code is presented with line number markers "LINE│ code". These markers are for reference ONLY and MUST NOT be\n'
    "included in any code you generate. Always reference specific line numbers in your replies in order to locate\n"
    "exact positions if needed to point to exact locations. Include a very short code excerpt alongside for clarity.\n"
    "Include context_start_text and context_end_text as backup references. Never include "
    '"LINE│" markers in generated code\n'
    "snippets."
)

CRITICAL_LINE_NUMBER_INSTRUCTIONS_BRIEF = (
    "CRITICAL LINE NUMBER INSTRUCTIONS\n"
    'Code is presented with line number markers "LINE│ code". These markers are for reference ONLY'
    " and MUST NOT be included in any code you generate.\n"
    "Always reference specific line numbers in your replies to locate exact positions."
    " Include a very short code excerpt alongside each finding for clarity.\n"
    'Never include "LINE│" markers in generated code snippets.'
)

# ---------------------------------------------------------------------------
# "More information needed" JSON template
# ---------------------------------------------------------------------------

FILES_REQUIRED_JSON = """{
  "status": "files_required_to_continue",
  "mandatory_instructions": "<your critical instructions for the agent>",
  "files_needed": ["[file name here]", "[or some folder/]"]
}"""

# ---------------------------------------------------------------------------
# Severity scale (emoji legend)
# ---------------------------------------------------------------------------

SEVERITY_DEFINITIONS = (
    "SEVERITY DEFINITIONS\n"
    "🔴 CRITICAL: Security flaws, defects that cause crashes, data loss, or undefined behavior"
    " (e.g., race conditions).\n"
    "🟠 HIGH: Bugs, performance bottlenecks, or anti-patterns that significantly impair usability,"
    " scalability, or reliability.\n"
    "🟡 MEDIUM: Maintainability concerns, code smells, test gaps, or non-idiomatic code that"
    " increases cognitive load.\n"
    "🟢 LOW: Style nits, minor improvements, or opportunities for code clarification."
)

# ---------------------------------------------------------------------------
# Scope-control boilerplate
# ---------------------------------------------------------------------------

SCOPE_CONTROL = (
    "SCOPE CONTROL\n"
    "Stay strictly within the provided codebase. Do NOT invent features, suggest major architectural"
    " changes beyond current\n"
    "structure, recommend external libraries not in use, or create speculative ideas outside project scope."
)

# ---------------------------------------------------------------------------
# "Scope too large" JSON template
# ---------------------------------------------------------------------------

FOCUSED_REVIEW_REQUIRED_JSON = """{
  "status": "focused_review_required",
  "reason": "<brief explanation of why the scope is too large>",
  "suggestion": "<e.g., 'Review authentication module (auth.py, login.py)' or 'Focus on data layer (models/)' or 'Review payment processing functionality'>"
 }"""
