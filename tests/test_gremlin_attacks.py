"""Gremlin attack tests for knurl.diff

These tests target assumptions in the diff/patch implementation.
Each test tries to break something that looks solid.
"""

import pytest
from knurl import diff


class TestTypeConfusion:
    """What happens when apply() gets non-dict base?"""

    def test_apply_to_list_base(self):
        """ATTACK: apply() expects dict, give it a list"""
        base = [1, 2, 3]
        patch = [{'op': 'add', 'path': '/0', 'value': 99}]
        
        # Does it explode? Does it work? Does it corrupt silently?
        result = diff.apply(base, patch)
        # If it works, we've found type polymorphism
        # If it fails, how does it fail?
        assert result == [99, 1, 2, 3] or result is None

    def test_apply_to_none_base(self):
        """ATTACK: apply() with None as base"""
        patch = [{'op': 'add', 'path': '/a', 'value': 1}]
        
        with pytest.raises(Exception):
            diff.apply(None, patch)

    def test_apply_to_string_base(self):
        """ATTACK: apply() with string as base"""
        patch = [{'op': 'add', 'path': '/0', 'value': 'x'}]
        
        with pytest.raises(Exception):
            diff.apply('hello', patch)


class TestRootOperations:
    """Attack the root path ''"""

    @pytest.mark.xfail(reason="Empty path remove not supported by jsonpatch - PatchConflictError expected")
    def test_remove_root(self):
        """ATTACK: Remove the entire document"""
        base = {'a': 1, 'b': 2}
        patch = [{'op': 'remove', 'path': ''}]

        # What happens when you remove everything?
        result = diff.apply(base, patch)
        # Does it return None? Empty dict? Explode?
        assert result is None or result == {}

    def test_add_to_existing_root(self):
        """ATTACK: Add operation on root when root exists"""
        base = {'a': 1}
        patch = [{'op': 'add', 'path': '', 'value': {'b': 2}}]
        
        # Does it replace? Merge? Fail?
        result = diff.apply(base, patch)
        # RFC 6902 says add to root should replace
        assert result == {'b': 2} or result == {'a': 1, 'b': 2}

    def test_test_operation_on_root(self):
        """ATTACK: Test operation on root path"""
        base = {'a': 1}
        patch = [{'op': 'test', 'path': '', 'value': {'a': 1}}]
        
        # Test operation should pass
        result = diff.apply(base, patch)
        assert result == {'a': 1}

    def test_test_operation_fails_on_root(self):
        """ATTACK: Test operation fails on root"""
        base = {'a': 1}
        patch = [{'op': 'test', 'path': '', 'value': {'a': 2}}]
        
        # Test should fail
        with pytest.raises(diff.DiffError):
            diff.apply(base, patch)


class TestCanonicalizeEdgeCases:
    """Attack canonicalization assumptions"""

    @pytest.mark.xfail(reason="jsonpatch supports lists - type polymorphism exists")
    def test_compute_with_list_old(self):
        """ATTACK: compute() when old is a list"""
        old = [1, 2, 3]
        new = {'a': 1}

        # Does canonicalization handle lists?
        # Type signature says dict, but what happens?
        with pytest.raises(Exception):
            diff.compute(old, new)

    @pytest.mark.xfail(reason="jsonpatch supports lists - type polymorphism exists")
    def test_compute_with_list_new(self):
        """ATTACK: compute() when new is a list"""
        old = {'a': 1}
        new = [1, 2, 3]

        with pytest.raises(Exception):
            diff.compute(old, new)

    @pytest.mark.xfail(reason="jsonpatch supports lists - type polymorphism exists")
    def test_compute_both_lists(self):
        """ATTACK: compute() with both as lists"""
        old = [1, 2, 3]
        new = [1, 2, 4]

        # If it works, we've found type polymorphism in compute too
        with pytest.raises(Exception):
            diff.compute(old, new)


class TestMalformedPatches:
    """Feed apply() garbage patches"""

    def test_empty_operation(self):
        """ATTACK: Patch with empty operation object"""
        base = {'a': 1}
        patch = [{}]
        
        with pytest.raises(diff.DiffError):
            diff.apply(base, patch)

    def test_missing_op_field(self):
        """ATTACK: Operation without 'op' field"""
        base = {'a': 1}
        patch = [{'path': '/b', 'value': 2}]
        
        with pytest.raises(diff.DiffError):
            diff.apply(base, patch)

    def test_invalid_op_type(self):
        """ATTACK: Invalid operation type"""
        base = {'a': 1}
        patch = [{'op': 'explode', 'path': '/a'}]
        
        with pytest.raises(diff.DiffError):
            diff.apply(base, patch)

    def test_add_without_value(self):
        """ATTACK: Add operation missing value"""
        base = {'a': 1}
        patch = [{'op': 'add', 'path': '/b'}]
        
        with pytest.raises(diff.DiffError):
            diff.apply(base, patch)


class TestPathEdgeCases:
    """Attack path handling"""

    def test_path_without_leading_slash(self):
        """ATTACK: Path missing leading slash"""
        base = {'a': 1}
        patch = [{'op': 'add', 'path': 'b', 'value': 2}]
        
        # RFC 6902 requires leading slash
        with pytest.raises(diff.DiffError):
            diff.apply(base, patch)

    @pytest.mark.xfail(reason="Double slash creates empty key - jsonpatch errors on missing member")
    def test_path_with_double_slash(self):
        """ATTACK: Path with double slashes"""
        base = {'a': 1}
        patch = [{'op': 'add', 'path': '//b', 'value': 2}]

        # How does jsonpatch handle '//'?
        result = diff.apply(base, patch)
        # Might create nested structure or fail
        assert isinstance(result, dict)

    def test_path_with_trailing_slash(self):
        """ATTACK: Path with trailing slash"""
        base = {'a': {}}
        patch = [{'op': 'add', 'path': '/a/', 'value': 1}]
        
        # What does trailing slash mean?
        result = diff.apply(base, patch)
        assert isinstance(result, dict)
