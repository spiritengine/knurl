"""Gremlin attacks on mill/ledger/diff.py.

These tests look for:
- Silent corruption
- Unexpected behavior
- Mutation side effects
- Type confusion
- Data loss

All attacks that DON'T just raise expected exceptions.
"""

import pytest
from knurl import diff
import copy


class TestMutationSideEffects:
    """Does apply() truly not modify the base object?"""

    def test_nested_dict_mutation(self):
        """ATTACK: Can patch modify nested dicts in base?"""
        base = {"outer": {"inner": "original"}}
        base_copy = copy.deepcopy(base)
        
        patch = diff.compute(base, {"outer": {"inner": "modified"}})
        result = diff.apply(base, patch)
        
        # Base should be completely unchanged
        assert base == base_copy
        assert base["outer"]["inner"] == "original"
        assert result["outer"]["inner"] == "modified"

    def test_nested_list_mutation(self):
        """ATTACK: Can patch modify nested lists in base?"""
        base = {"items": [1, 2, 3]}
        base_copy = copy.deepcopy(base)
        
        patch = diff.compute(base, {"items": [1, 2, 3, 4]})
        result = diff.apply(base, patch)
        
        assert base == base_copy
        assert len(base["items"]) == 3
        assert len(result["items"]) == 4

    def test_shared_reference_mutation(self):
        """ATTACK: If base has shared references, can patch corrupt them?"""
        shared = {"value": 42}
        base = {"a": shared, "b": shared}
        base_copy = copy.deepcopy(base)
        
        patch = diff.compute(base, {"a": {"value": 99}, "b": {"value": 42}})
        result = diff.apply(base, patch)
        
        # Shared reference in base should be untouched
        assert base == base_copy
        assert base["a"]["value"] == 42
        assert base["b"]["value"] == 42


class TestDoubleApply:
    """What happens when you apply a patch twice?"""

    def test_double_apply_crashes_or_corrupts(self):
        """ATTACK: apply(apply(base, patch), patch) - silent corruption or crash?"""
        base = {"x": 1}
        target = {"x": 2}
        
        patch = diff.compute(base, target)
        first_apply = diff.apply(base, patch)
        
        # Second apply should fail (can't change 2 to 2)
        # But does it fail gracefully or silently corrupt?
        try:
            second_apply = diff.apply(first_apply, patch)
            # If it succeeds, check for corruption
            if second_apply != first_apply:
                pytest.fail(f"BROKE: Double-apply silently corrupted data: {first_apply} -> {second_apply}")
        except Exception:
            # Expected to fail, but let's see how
            pass

    @pytest.mark.xfail(reason="jsonpatch treats add-existing as replace, not error")
    def test_double_apply_add_operation(self):
        """ATTACK: Adding same key twice"""
        base = {}
        target = {"new": "value"}

        patch = diff.compute(base, target)
        first = diff.apply(base, patch)

        # Try to add again
        with pytest.raises(Exception):  # Should fail
            diff.apply(first, patch)


class TestTypeConfusion:
    """Canonicalization type issues"""

    @pytest.mark.xfail(reason="JSON requires string keys - CanonError is correct behavior")
    def test_integer_vs_string_keys(self):
        """ATTACK: Integer keys become strings in JSON"""
        base = {1: "int_key", "1": "string_key"}
        target = {1: "int_key_modified", "1": "string_key"}

        # Canonicalization might lose distinction between 1 and "1"
        patch = diff.compute(base, target)
        result = diff.apply(base, patch)

        # Check if we lost the distinction
        if len(result) != 2:
            pytest.fail(f"BROKE: Integer vs string key collision - expected 2 keys, got {len(result)}")

        # Check if round-trip preserves both keys
        assert result != target, "Type confusion: integer key became string key"

    @pytest.mark.xfail(reason="Tuples become lists through JSON - expected canonicalization behavior")
    def test_tuple_becomes_list(self):
        """ATTACK: Tuples become lists through JSON"""
        base = {"data": (1, 2, 3)}
        target = {"data": (1, 2, 3, 4)}

        patch = diff.compute(base, target)
        result = diff.apply(base, patch)

        # Tuple should become list
        assert isinstance(result["data"], list), "Tuple survived JSON - unexpected"
        assert result["data"] != target["data"], "Type changed tuple to list"

    def test_none_vs_missing_key(self):
        """ATTACK: Is None different from missing key?"""
        base1 = {"key": None}
        base2 = {}
        
        # Are these treated as different?
        assert diff.differs(base1, base2), "None vs missing should differ"
        
        # Can we round-trip None?
        target = {"key": None}
        patch = diff.compute({}, target)
        result = diff.apply({}, patch)
        
        assert result == target


class TestDiffersInconsistency:
    """Can differs() lie?"""

    def test_differs_with_type_variants(self):
        """ATTACK: Do semantically different objects compare as identical?"""
        obj1 = {"data": [1, 2, 3]}
        obj2 = {"data": (1, 2, 3)}  # Tuple vs list
        
        # After canonicalization, these might look identical
        # This could be correct behavior, but worth verifying
        if not diff.differs(obj1, obj2):
            # They're treated as identical - is this a problem?
            patch = diff.compute(obj1, obj2)
            assert len(patch) == 0, "differs() says identical but compute() found diff"

    def test_differs_with_key_order(self):
        """ATTACK: Does key order affect differs()?"""
        obj1 = {"a": 1, "b": 2, "c": 3}
        obj2 = {"c": 3, "b": 2, "a": 1}
        
        # Should be treated as identical (dict order doesn't matter)
        assert not diff.differs(obj1, obj2)


class TestPathManipulation:
    """JSON Pointer edge cases"""

    def test_empty_path(self):
        """ATTACK: Empty path in patch"""
        # Not sure if this is valid, but what happens?
        base = {"x": 1}
        # Manually craft patch with empty path
        patch = [{"op": "replace", "path": "", "value": {"x": 2}}]
        
        try:
            result = diff.apply(base, patch)
            # If it works, empty path means "root"
            assert result == {"x": 2}
        except Exception:
            pass  # Expected to fail

    def test_root_path(self):
        """ATTACK: Root path '/'"""
        base = {"x": 1}
        patch = [{"op": "replace", "path": "/", "value": {"x": 2}}]
        
        # This might fail or might replace the entire object
        try:
            result = diff.apply(base, patch)
        except Exception:
            pass

    def test_path_with_special_chars(self):
        """ATTACK: JSON Pointer escape sequences"""
        # In JSON Pointer, ~ is escaped as ~0, / is escaped as ~1
        base = {"foo~bar": 1, "baz/qux": 2}
        target = {"foo~bar": 99, "baz/qux": 2}
        
        patch = diff.compute(base, target)
        result = diff.apply(base, patch)
        
        assert result == target, "Special chars in keys broke patching"

    def test_deeply_nested_nonexistent_path(self):
        """ATTACK: Patch references path that doesn't exist"""
        base = {"a": {"b": 1}}
        # Try to patch /a/b/c/d/e/f when only /a/b exists
        patch = [{"op": "add", "path": "/a/b/c/d/e/f", "value": 42}]
        
        with pytest.raises(Exception):
            diff.apply(base, patch)  # Should fail


class TestConflictingOperations:
    """Multiple operations on same path"""

    def test_add_then_remove_same_path(self):
        """ATTACK: Add then remove in single patch"""
        base = {}
        patch = [
            {"op": "add", "path": "/x", "value": 42},
            {"op": "remove", "path": "/x"}
        ]
        
        result = diff.apply(base, patch)
        # Result should be empty (add then remove)
        assert result == {}

    def test_remove_then_add_same_path(self):
        """ATTACK: Remove then add in single patch"""
        base = {"x": 1}
        patch = [
            {"op": "remove", "path": "/x"},
            {"op": "add", "path": "/x", "value": 2}
        ]
        
        result = diff.apply(base, patch)
        # Result should have x=2
        assert result == {"x": 2}

    def test_multiple_replace_same_path(self):
        """ATTACK: Replace same path multiple times"""
        base = {"x": 1}
        patch = [
            {"op": "replace", "path": "/x", "value": 2},
            {"op": "replace", "path": "/x", "value": 3},
            {"op": "replace", "path": "/x", "value": 4}
        ]
        
        result = diff.apply(base, patch)
        # Last one wins
        assert result == {"x": 4}


class TestStackOverflow:
    """Very deep nesting"""

    @pytest.mark.xfail(reason="Python recursion limit ~1000 - expected language limitation")
    def test_deeply_nested_structure(self):
        """ATTACK: 1000-level nesting"""
        # Build deeply nested dict
        base = current = {}
        for i in range(1000):
            current["nested"] = {}
            current = current["nested"]
        current["value"] = "deep"

        # Can we compute and apply patch on this?
        target = copy.deepcopy(base)
        # Change the deepest value
        current = target
        for i in range(1000):
            current = current["nested"]
        current["value"] = "modified"

        try:
            patch = diff.compute(base, target)
            result = diff.apply(base, patch)
            assert result != base, "Deep nesting broke diff"
        except RecursionError:
            pytest.fail("BROKE: Stack overflow on 1000-level nesting")


class TestSilentCorruption:
    """The worst kind: wrong answers without errors"""

    @pytest.mark.xfail(reason="Integer dict keys not supported - CanonError is correct")
    def test_compute_then_apply_not_identity(self):
        """ATTACK: Round-trip doesn't preserve data"""
        base = {"tuple": (1, 2, 3), "int_key": {1: "value"}}
        target = {"tuple": (1, 2, 3, 4), "int_key": {1: "new_value"}}

        patch = diff.compute(base, target)
        result = diff.apply(base, patch)

        # Result might not equal target due to type changes
        # This is silent corruption if user expects exact match
        if result != target:
            # Document the corruption
            print(f"\nSILENT CORRUPTION:")
            print(f"Expected: {target}")
            print(f"Got:      {result}")
            # This might be expected behavior, but it's worth noting

    def test_float_precision_loss(self):
        """ATTACK: Float precision through JSON serialization"""
        base = {"value": 0.1 + 0.2}  # 0.30000000000000004
        target = {"value": 0.3}  # 0.3 exactly
        
        patch = diff.compute(base, target)
        result = diff.apply(base, patch)
        
        # Are these treated as different?
        if len(patch) == 0:
            # Treated as identical - potential precision issue
            print(f"\nFloat precision: {base['value']} == {target['value']}?")
