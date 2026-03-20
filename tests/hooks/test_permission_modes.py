"""Integration tests for permission mode detection across all bypass modes.

Tests the permission mode helpers in _common.py that determine when to skip
permission prompts based on Claude Code's permission_mode setting.
"""
import sys
import os

# Bootstrap path to _common.py and hooks
sys.path.insert(0, os.path.expanduser("~/.claude/hooks"))
sys.path.insert(0, os.path.expanduser("~/.claude"))

from _common import (
    is_bypass_mode,
    is_edit_bypass_mode,
    _get_permission_mode,
    BYPASS_MODES,
    EDIT_BYPASS_MODES,
)


class TestPermissionModeConstants:
    """Test that the mode constants are correctly defined."""

    def test_bypass_modes_contains_expected_values(self):
        """BYPASS_MODES should contain bypasspermissions and dontask."""
        assert "bypasspermissions" in BYPASS_MODES
        assert "dontask" in BYPASS_MODES
        assert len(BYPASS_MODES) == 2

    def test_edit_bypass_modes_contains_expected_values(self):
        """EDIT_BYPASS_MODES should contain bypasspermissions, dontask, and acceptedits."""
        assert "bypasspermissions" in EDIT_BYPASS_MODES
        assert "dontask" in EDIT_BYPASS_MODES
        assert "acceptedits" in EDIT_BYPASS_MODES
        assert len(EDIT_BYPASS_MODES) == 3

    def test_bypass_modes_is_subset_of_edit_bypass_modes(self):
        """BYPASS_MODES should be a subset of EDIT_BYPASS_MODES."""
        assert BYPASS_MODES.issubset(EDIT_BYPASS_MODES)


class TestGetPermissionMode:
    """Test the _get_permission_mode normalization function."""

    def test_normalizes_bypasspermissions(self):
        """Should normalize bypassPermissions to lowercase."""
        data = {"permission_mode": "bypassPermissions"}
        assert _get_permission_mode(data) == "bypasspermissions"

    def test_normalizes_dontask(self):
        """Should normalize dontAsk to lowercase."""
        data = {"permission_mode": "dontAsk"}
        assert _get_permission_mode(data) == "dontask"

    def test_normalizes_acceptedits(self):
        """Should normalize acceptEdits to lowercase."""
        data = {"permission_mode": "acceptEdits"}
        assert _get_permission_mode(data) == "acceptedits"

    def test_normalizes_plan(self):
        """Should normalize plan mode."""
        data = {"permission_mode": "plan"}
        assert _get_permission_mode(data) == "plan"

    def test_normalizes_uppercase(self):
        """Should handle all uppercase input."""
        data = {"permission_mode": "BYPASSPERMISSIONS"}
        assert _get_permission_mode(data) == "bypasspermissions"

    def test_strips_whitespace(self):
        """Should strip leading and trailing whitespace."""
        data = {"permission_mode": "  dontAsk  "}
        assert _get_permission_mode(data) == "dontask"

    def test_handles_mixed_case_with_whitespace(self):
        """Should handle both case normalization and whitespace stripping."""
        data = {"permission_mode": "  AcceptEdits  "}
        assert _get_permission_mode(data) == "acceptedits"

    def test_handles_none_value(self):
        """Should return empty string when permission_mode is None."""
        data = {"permission_mode": None}
        assert _get_permission_mode(data) == ""

    def test_handles_empty_string(self):
        """Should return empty string when permission_mode is empty."""
        data = {"permission_mode": ""}
        assert _get_permission_mode(data) == ""

    def test_handles_missing_key(self):
        """Should return empty string when permission_mode key is missing."""
        data = {"other_key": "value"}
        assert _get_permission_mode(data) == ""

    def test_handles_empty_dict(self):
        """Should return empty string for empty dict."""
        data = {}
        assert _get_permission_mode(data) == ""

    def test_handles_non_dict_input_none(self):
        """Should return empty string when input is None."""
        assert _get_permission_mode(None) == ""

    def test_handles_non_dict_input_string(self):
        """Should return empty string when input is a string."""
        assert _get_permission_mode("bypassPermissions") == ""

    def test_handles_non_dict_input_list(self):
        """Should return empty string when input is a list."""
        assert _get_permission_mode(["bypassPermissions"]) == ""

    def test_handles_non_dict_input_int(self):
        """Should return empty string when input is an int."""
        assert _get_permission_mode(42) == ""


class TestIsBypassMode:
    """Test is_bypass_mode for all permission modes."""

    def test_bypasspermissions_is_bypass(self):
        """bypassPermissions mode should return True."""
        data = {"permission_mode": "bypassPermissions"}
        assert is_bypass_mode(data) is True

    def test_dontask_is_bypass(self):
        """dontAsk mode should return True."""
        data = {"permission_mode": "dontAsk"}
        assert is_bypass_mode(data) is True

    def test_acceptedits_is_not_bypass(self):
        """acceptEdits mode should return False for is_bypass_mode."""
        data = {"permission_mode": "acceptEdits"}
        assert is_bypass_mode(data) is False

    def test_plan_is_not_bypass(self):
        """plan mode should return False."""
        data = {"permission_mode": "plan"}
        assert is_bypass_mode(data) is False

    def test_default_mode_is_not_bypass(self):
        """Default mode (empty string) should return False."""
        data = {"permission_mode": ""}
        assert is_bypass_mode(data) is False

    def test_missing_mode_is_not_bypass(self):
        """Missing permission_mode key should return False."""
        data = {}
        assert is_bypass_mode(data) is False

    def test_unknown_mode_is_not_bypass(self):
        """Unknown mode values should return False."""
        data = {"permission_mode": "unknownMode"}
        assert is_bypass_mode(data) is False

    def test_none_input_is_not_bypass(self):
        """None input should return False."""
        assert is_bypass_mode(None) is False

    def test_non_dict_input_is_not_bypass(self):
        """Non-dict input should return False."""
        assert is_bypass_mode("bypassPermissions") is False
        assert is_bypass_mode(["dontAsk"]) is False
        assert is_bypass_mode(42) is False


class TestIsEditBypassMode:
    """Test is_edit_bypass_mode for all permission modes."""

    def test_bypasspermissions_is_edit_bypass(self):
        """bypassPermissions mode should return True for edit bypass."""
        data = {"permission_mode": "bypassPermissions"}
        assert is_edit_bypass_mode(data) is True

    def test_dontask_is_edit_bypass(self):
        """dontAsk mode should return True for edit bypass."""
        data = {"permission_mode": "dontAsk"}
        assert is_edit_bypass_mode(data) is True

    def test_acceptedits_is_edit_bypass(self):
        """acceptEdits mode should return True for edit bypass."""
        data = {"permission_mode": "acceptEdits"}
        assert is_edit_bypass_mode(data) is True

    def test_plan_is_not_edit_bypass(self):
        """plan mode should return False for edit bypass."""
        data = {"permission_mode": "plan"}
        assert is_edit_bypass_mode(data) is False

    def test_default_mode_is_not_edit_bypass(self):
        """Default mode (empty string) should return False for edit bypass."""
        data = {"permission_mode": ""}
        assert is_edit_bypass_mode(data) is False

    def test_missing_mode_is_not_edit_bypass(self):
        """Missing permission_mode key should return False for edit bypass."""
        data = {}
        assert is_edit_bypass_mode(data) is False

    def test_unknown_mode_is_not_edit_bypass(self):
        """Unknown mode values should return False for edit bypass."""
        data = {"permission_mode": "unknownMode"}
        assert is_edit_bypass_mode(data) is False

    def test_none_input_is_not_edit_bypass(self):
        """None input should return False for edit bypass."""
        assert is_edit_bypass_mode(None) is False

    def test_non_dict_input_is_not_edit_bypass(self):
        """Non-dict input should return False for edit bypass."""
        assert is_edit_bypass_mode("acceptEdits") is False
        assert is_edit_bypass_mode(["bypassPermissions"]) is False
        assert is_edit_bypass_mode(42) is False


class TestPermissionModeIntegration:
    """Integration tests combining all permission mode functions."""

    def test_all_bypass_modes_are_edit_bypass(self):
        """All modes that trigger is_bypass_mode should also trigger is_edit_bypass_mode."""
        for mode in ["bypassPermissions", "dontAsk"]:
            data = {"permission_mode": mode}
            assert is_bypass_mode(data) is True
            assert is_edit_bypass_mode(data) is True

    def test_acceptedits_only_edit_bypass(self):
        """acceptEdits should only trigger edit bypass, not general bypass."""
        data = {"permission_mode": "acceptEdits"}
        assert is_bypass_mode(data) is False
        assert is_edit_bypass_mode(data) is True

    def test_non_bypass_modes_trigger_neither(self):
        """Non-bypass modes should not trigger either function."""
        for mode in ["plan", "", "default", "unknownMode"]:
            data = {"permission_mode": mode}
            assert is_bypass_mode(data) is False
            assert is_edit_bypass_mode(data) is False

    def test_case_insensitive_detection_all_modes(self):
        """All modes should be detected case-insensitively."""
        modes = [
            ("bypassPermissions", "BYPASSPERMISSIONS", "bypasspermissions"),
            ("dontAsk", "DONTASK", "dontask"),
            ("acceptEdits", "ACCEPTEDITS", "acceptedits"),
        ]
        for mode_variations in modes:
            for mode in mode_variations:
                data = {"permission_mode": mode}
                result = _get_permission_mode(data)
                assert result == mode_variations[2]  # normalized lowercase

    def test_whitespace_handling_all_modes(self):
        """All modes should handle whitespace correctly."""
        test_cases = [
            "  bypassPermissions  ",
            "\tdontAsk\t",
            "\nacceptEdits\n",
            "  plan  ",
        ]
        for mode in test_cases:
            data = {"permission_mode": mode}
            result = _get_permission_mode(data)
            assert result == mode.strip().lower()
            assert not result.startswith(" ")
            assert not result.endswith(" ")


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_permission_mode_with_special_characters(self):
        """Should handle special characters in permission_mode."""
        data = {"permission_mode": "bypass-permissions"}
        assert _get_permission_mode(data) == "bypass-permissions"
        assert is_bypass_mode(data) is False  # not a valid mode

    def test_permission_mode_numeric_string(self):
        """Should handle numeric strings."""
        data = {"permission_mode": "12345"}
        assert _get_permission_mode(data) == "12345"
        assert is_bypass_mode(data) is False

    def test_permission_mode_with_newlines(self):
        """Should strip newlines from permission_mode."""
        data = {"permission_mode": "\nbypassPermissions\n"}
        assert _get_permission_mode(data) == "bypasspermissions"
        assert is_bypass_mode(data) is True

    def test_permission_mode_with_tabs(self):
        """Should strip tabs from permission_mode."""
        data = {"permission_mode": "\tdontAsk\t"}
        assert _get_permission_mode(data) == "dontask"
        assert is_bypass_mode(data) is True

    def test_dict_with_multiple_keys(self):
        """Should correctly extract permission_mode from dict with other keys."""
        data = {
            "permission_mode": "acceptEdits",
            "other_key": "other_value",
            "session_id": "test-session",
        }
        assert _get_permission_mode(data) == "acceptedits"
        assert is_edit_bypass_mode(data) is True

    def test_none_value_in_dict(self):
        """Should handle None value for permission_mode."""
        data = {"permission_mode": None, "other_key": "value"}
        assert _get_permission_mode(data) == ""
        assert is_bypass_mode(data) is False
        assert is_edit_bypass_mode(data) is False

    def test_boolean_false_in_dict(self):
        """Should handle boolean False value (treated as falsy, returns empty string)."""
        data = {"permission_mode": False}
        result = _get_permission_mode(data)
        # False is falsy, so (data.get("permission_mode") or "") returns ""
        assert result == ""
        assert is_bypass_mode(data) is False

    def test_empty_nested_structures(self):
        """Should handle nested empty structures gracefully."""
        test_cases = [
            {},
            {"permission_mode": ""},
            {"permission_mode": None},
            {"other": {}},
        ]
        for data in test_cases:
            assert is_bypass_mode(data) is False
            assert is_edit_bypass_mode(data) is False


class TestRealWorldScenarios:
    """Test real-world usage scenarios from hook implementations."""

    def test_bash_hook_bypass_scenario(self):
        """Test scenario: bash command in bypassPermissions mode."""
        hook_input = {
            "permission_mode": "bypassPermissions",
            "tool": "Bash",
            "command": "git status",
        }
        # Should bypass permission prompts
        assert is_bypass_mode(hook_input) is True
        assert is_edit_bypass_mode(hook_input) is True

    def test_edit_hook_acceptedits_scenario(self):
        """Test scenario: file edit in acceptEdits mode."""
        hook_input = {
            "permission_mode": "acceptEdits",
            "tool": "Edit",
            "file_path": "/path/to/file.py",
        }
        # Should bypass edit prompts but not bash prompts
        assert is_bypass_mode(hook_input) is False
        assert is_edit_bypass_mode(hook_input) is True

    def test_plan_mode_requires_confirmation(self):
        """Test scenario: plan mode requires user confirmation."""
        hook_input = {
            "permission_mode": "plan",
            "tool": "Write",
            "file_path": "/path/to/new_file.py",
        }
        # Should not bypass any prompts
        assert is_bypass_mode(hook_input) is False
        assert is_edit_bypass_mode(hook_input) is False

    def test_default_mode_requires_confirmation(self):
        """Test scenario: default mode (no bypass) requires confirmation."""
        hook_input = {
            "tool": "Bash",
            "command": "rm -rf /",
        }
        # Missing permission_mode should not bypass
        assert is_bypass_mode(hook_input) is False
        assert is_edit_bypass_mode(hook_input) is False

    def test_dontask_mode_skips_all_prompts(self):
        """Test scenario: dontAsk mode skips all permission prompts."""
        hook_input = {
            "permission_mode": "dontAsk",
            "tool": "Bash",
            "command": "npm install",
        }
        # Should bypass all prompts
        assert is_bypass_mode(hook_input) is True
        assert is_edit_bypass_mode(hook_input) is True

    def test_mixed_case_from_real_hook_data(self):
        """Test scenario: real hook data with mixed case (common from Claude Code)."""
        hook_input = {
            "permission_mode": "AcceptEdits",  # Mixed case from UI
            "tool": "MultiEdit",
            "edits": [],
        }
        assert _get_permission_mode(hook_input) == "acceptedits"
        assert is_edit_bypass_mode(hook_input) is True


class TestComprehensiveModeMatrix:
    """Comprehensive test matrix for all 5 modes across both functions."""

    def test_mode_matrix(self):
        """Test all 5 modes with expected results for both functions."""
        # (mode, expected_is_bypass_mode, expected_is_edit_bypass_mode)
        test_matrix = [
            ("bypassPermissions", True, True),
            ("dontAsk", True, True),
            ("acceptEdits", False, True),
            ("plan", False, False),
            ("", False, False),  # default/empty
        ]

        for mode, expected_bypass, expected_edit_bypass in test_matrix:
            data = {"permission_mode": mode}

            # Test is_bypass_mode
            actual_bypass = is_bypass_mode(data)
            assert actual_bypass == expected_bypass, (
                f"Mode '{mode}': is_bypass_mode expected {expected_bypass}, got {actual_bypass}"
            )

            # Test is_edit_bypass_mode
            actual_edit_bypass = is_edit_bypass_mode(data)
            assert actual_edit_bypass == expected_edit_bypass, (
                f"Mode '{mode}': is_edit_bypass_mode expected {expected_edit_bypass}, got {actual_edit_bypass}"
            )

    def test_mode_matrix_case_variations(self):
        """Test mode matrix with various case combinations."""
        base_modes = [
            ("bypassPermissions", True, True),
            ("dontAsk", True, True),
            ("acceptEdits", False, True),
            ("plan", False, False),
        ]

        for base_mode, expected_bypass, expected_edit_bypass in base_modes:
            # Test uppercase, lowercase, and mixed case
            case_variations = [
                base_mode.upper(),
                base_mode.lower(),
                base_mode,
            ]

            for mode_variant in case_variations:
                data = {"permission_mode": mode_variant}

                assert is_bypass_mode(data) == expected_bypass, (
                    f"Mode '{mode_variant}' (from '{base_mode}'): "
                    f"is_bypass_mode expected {expected_bypass}"
                )

                assert is_edit_bypass_mode(data) == expected_edit_bypass, (
                    f"Mode '{mode_variant}' (from '{base_mode}'): "
                    f"is_edit_bypass_mode expected {expected_edit_bypass}"
                )
