"""
Test that ensures no hardcoded /tmp paths exist in test files.

This prevents Unix-only path assumptions and encourages use of
tempfile.gettempdir() or pytest's tmp_path fixture instead.
"""

import re
from pathlib import Path

# Files that are allowed to reference /tmp for legitimate reasons:
# - conftest.py: macOS TMPDIR override is intentional
# - test_path_traversal_security.py: tests security function behavior with known paths
# - test_docker_*: Docker config paths are platform-specific by design
# - test_no_hardcoded_tmp.py: this file itself references /tmp in its allowlist
ALLOWED_FILES = {
    "conftest.py",
    "test_path_traversal_security.py",
    "test_docker_claude_desktop_integration.py",
    "test_no_hardcoded_tmp.py",
}

# Pattern to match hardcoded /tmp paths (quoted or in f-strings)
TMP_PATTERN = re.compile(r'["\']\/tmp[\/"\']')


class TestNoHardcodedTmp:
    """Ensure test files use tempfile.gettempdir() instead of hardcoded /tmp."""

    def test_no_hardcoded_tmp_in_test_files(self):
        """Scan all test files for hardcoded /tmp references."""
        tests_dir = Path(__file__).parent
        violations = []

        for test_file in sorted(tests_dir.glob("*.py")):
            if test_file.name in ALLOWED_FILES:
                continue

            content = test_file.read_text()
            for i, line in enumerate(content.splitlines(), 1):
                # Skip comments
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if TMP_PATTERN.search(line):
                    violations.append(f"{test_file.name}:{i}: {line.strip()}")

        assert not violations, (
            "Found hardcoded /tmp paths in test files. "
            "Use tempfile.gettempdir() or pytest's tmp_path fixture instead:\n" + "\n".join(violations)
        )
