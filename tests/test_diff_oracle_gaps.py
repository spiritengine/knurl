"""Small gap tests identified by Oracle edge case analysis.

Most edge cases were already covered in test_diff.py. These tests fill
the remaining small gaps around escaping combinations and type coercion.
"""

import pytest
from knurl.diff import compute, apply, DiffError


class TestEscapingCombinations:
    """Test JSON Pointer escaping when special chars appear together."""

    def test_tilde_and_slash_together(self):
        """Key containing both ~ and / gets double-escaped."""
        old = {}
        new = {"~/": "value"}

        patch = compute(old, new)
        assert len(patch) == 1
        assert patch[0]["op"] == "add"
        assert "~0~1" in patch[0]["path"]

        result = apply(old, patch)
        assert result == new

    def test_multiple_tildes_and_slashes(self):
        """Key with multiple special chars: ~0/~1."""
        old = {}
        new = {"~0/~1": "value"}

        patch = compute(old, new)
        result = apply(old, patch)
        assert result == new

    def test_special_char_combinations_in_nested_paths(self):
        """Nested paths with special char combinations."""
        old = {"parent": {}}
        new = {"parent": {"~/key": "value"}}

        patch = compute(old, new)
        result = apply(old, patch)
        assert result == new


class TestTypeCoercionEdgeCases:
    """Test that Python's True == 1 doesn't cause issues."""

    def test_true_vs_one_are_different(self):
        """True and 1 should be treated as different values."""
        old = {"value": True}
        new = {"value": 1}

        patch = compute(old, new)
        assert len(patch) == 1
        assert patch[0]["op"] == "replace"

        result = apply(old, patch)
        assert result == new
        assert result["value"] is 1
        assert result["value"] is not True

    def test_false_vs_zero_are_different(self):
        """False and 0 should be treated as different values."""
        old = {"value": False}
        new = {"value": 0}

        patch = compute(old, new)
        assert len(patch) == 1
        assert patch[0]["op"] == "replace"

        result = apply(old, patch)
        assert result == new
        assert result["value"] is 0
        assert result["value"] is not False

    def test_bool_int_round_trip(self):
        """Changing bool → int → bool preserves types."""
        start = {"enabled": True}
        middle = {"enabled": 1}
        end = {"enabled": False}

        patch1 = compute(start, middle)
        patch2 = compute(middle, end)

        step1 = apply(start, patch1)
        assert step1["enabled"] is 1

        step2 = apply(step1, patch2)
        assert step2["enabled"] is False


class TestErrorMessageQuality:
    """Test that error messages provide useful context."""

    def test_patch_conflict_includes_path(self):
        """PatchConflictError should mention the problematic path."""
        base = {"a": 1}
        patch = [{"op": "remove", "path": "/nonexistent"}]

        with pytest.raises(DiffError) as exc_info:
            apply(base, patch)

        error_msg = str(exc_info.value)
        assert "nonexistent" in error_msg or "/nonexistent" in error_msg

    def test_invalid_patch_describes_problem(self):
        """Invalid patch error should describe what's wrong."""
        base = {"a": 1}
        patch = [{"op": "invalid_operation", "path": "/a"}]

        with pytest.raises(DiffError) as exc_info:
            apply(base, patch)

        error_msg = str(exc_info.value)
        assert "invalid" in error_msg.lower() or "unknown" in error_msg.lower()

    def test_malformed_patch_missing_required_field(self):
        """Patch missing required field gives clear error."""
        base = {"a": 1}
        patch = [{"op": "add"}]

        with pytest.raises(DiffError) as exc_info:
            apply(base, patch)

        error_msg = str(exc_info.value)
        assert "path" in error_msg.lower() or "invalid" in error_msg.lower()


class TestArrayAppendEdgeCases:
    """Additional array "-" index edge cases."""

    def test_multiple_appends_in_single_patch(self):
        """Multiple append operations in one patch should work sequentially."""
        old = {"arr": [1, 2]}
        patch = [
            {"op": "add", "path": "/arr/-", "value": 3},
            {"op": "add", "path": "/arr/-", "value": 4}
        ]

        result = apply(old, patch)
        assert result == {"arr": [1, 2, 3, 4]}

    def test_append_to_empty_array(self):
        """Appending to empty array with - index."""
        old = {"arr": []}
        patch = [{"op": "add", "path": "/arr/-", "value": "first"}]

        result = apply(old, patch)
        assert result == {"arr": ["first"]}

    def test_mixed_array_operations_with_append(self):
        """Mix of remove, add, and append operations."""
        old = {"arr": ["a", "b", "c"]}
        patch = [
            {"op": "remove", "path": "/arr/1"},
            {"op": "add", "path": "/arr/-", "value": "d"}
        ]

        result = apply(old, patch)
        assert result == {"arr": ["a", "c", "d"]}
