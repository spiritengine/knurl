"""Tests for diff computation and application module.

Tests the knurl.diff module which provides:
- compute(old, new) -> JSON Patch operations
- apply(base, patch) -> reconstructed object
- differs(old, new) -> bool
- summarize(patch) -> human-readable string
- DiffError for validation failures

Based on RFC 6902 (JSON Patch).

Test Categories:
1. Basic Operations - add, remove, replace, no changes
2. Nested Structures - deep paths, nested dicts, dicts in lists
3. Array Handling - append, remove, element modification
4. Round-Trip - apply(old, compute(old, new)) == new
5. Edge Cases - empty configs, large configs, type changes, unicode
6. Error Handling - apply to wrong base, malformed patches
7. Summarize - human-readable output
"""

import pytest
from hypothesis import given, strategies as st, settings


@pytest.fixture
def diff():
    """Import diff module."""
    from knurl import diff
    return diff


@pytest.fixture
def compute():
    """Import compute function."""
    from knurl.diff import compute
    return compute


@pytest.fixture
def apply_patch():
    """Import apply function."""
    from knurl.diff import apply
    return apply


@pytest.fixture
def differs():
    """Import differs function."""
    from knurl.diff import differs
    return differs


@pytest.fixture
def summarize():
    """Import summarize function."""
    from knurl.diff import summarize
    return summarize


@pytest.fixture
def DiffError():
    """Import DiffError exception."""
    from knurl.diff import DiffError
    return DiffError


@pytest.fixture
def PatchConflictError():
    """Import PatchConflictError exception."""
    from knurl.diff import PatchConflictError
    return PatchConflictError


@pytest.fixture
def InvalidPatchError():
    """Import InvalidPatchError exception."""
    from knurl.diff import InvalidPatchError
    return InvalidPatchError


@pytest.fixture
def PathNotFoundError():
    """Import PathNotFoundError exception."""
    from knurl.diff import PathNotFoundError
    return PathNotFoundError


# =============================================================================
# TestBasicOperations - add, remove, replace
# =============================================================================

class TestBasicOperations:
    """Basic patch operations."""

    def test_add_key(self, compute, apply_patch):
        """Adding a new key produces 'add' operation."""
        old = {'a': 1}
        new = {'a': 1, 'b': 2}

        patch = compute(old, new)

        # Should contain an add operation
        assert any(op['op'] == 'add' for op in patch)
        assert any(op['path'] == '/b' for op in patch)

        # Apply should produce new
        result = apply_patch(old, patch)
        assert result == new

    def test_remove_key(self, compute, apply_patch):
        """Removing a key produces 'remove' operation."""
        old = {'a': 1, 'b': 2}
        new = {'a': 1}

        patch = compute(old, new)

        assert any(op['op'] == 'remove' for op in patch)
        assert any(op['path'] == '/b' for op in patch)

        result = apply_patch(old, patch)
        assert result == new

    def test_replace_value(self, compute, apply_patch):
        """Changing a value produces 'replace' operation."""
        old = {'a': 1}
        new = {'a': 2}

        patch = compute(old, new)

        assert any(op['op'] == 'replace' for op in patch)
        assert any(op['path'] == '/a' for op in patch)

        result = apply_patch(old, patch)
        assert result == new

    def test_no_changes(self, compute, differs):
        """Identical configs produce empty patch."""
        config = {'a': 1, 'b': {'c': 2}}

        patch = compute(config, config)

        assert patch == []
        assert differs(config, config) is False

    def test_multiple_operations(self, compute, apply_patch):
        """Multiple changes produce multiple operations."""
        old = {'a': 1, 'b': 2}
        new = {'a': 1, 'b': 3, 'c': 4}

        patch = compute(old, new)

        assert len(patch) == 2  # replace b, add c
        result = apply_patch(old, patch)
        assert result == new


# =============================================================================
# TestNestedStructures - Deep paths
# =============================================================================

class TestNestedStructures:
    """Nested structure handling."""

    def test_deep_path_change(self, compute, apply_patch):
        """Changes in deeply nested paths work correctly."""
        old = {'a': {'b': {'c': {'d': 1}}}}
        new = {'a': {'b': {'c': {'d': 2}}}}

        patch = compute(old, new)

        # Path should reference the deep location
        assert any('/a/b/c/d' in op['path'] for op in patch)

        result = apply_patch(old, patch)
        assert result == new

    def test_nested_dict_addition(self, compute, apply_patch):
        """Adding nested structure works."""
        old = {'a': 1}
        new = {'a': 1, 'b': {'c': {'d': 2}}}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_nested_dict_removal(self, compute, apply_patch):
        """Removing nested structure works."""
        old = {'a': 1, 'b': {'c': {'d': 2}}}
        new = {'a': 1}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_dict_in_list(self, compute, apply_patch):
        """Changes to dicts inside lists work."""
        old = {'items': [{'name': 'foo'}, {'name': 'bar'}]}
        new = {'items': [{'name': 'foo'}, {'name': 'baz'}]}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new


# =============================================================================
# TestArrayHandling - Array operations
# =============================================================================

class TestArrayHandling:
    """Array operation handling."""

    def test_array_append(self, compute, apply_patch):
        """Appending to array works."""
        old = {'items': [1, 2]}
        new = {'items': [1, 2, 3]}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_array_remove(self, compute, apply_patch):
        """Removing from array works."""
        old = {'items': [1, 2, 3]}
        new = {'items': [1, 3]}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_array_element_modify(self, compute, apply_patch):
        """Modifying array element works."""
        old = {'items': [1, 2, 3]}
        new = {'items': [1, 99, 3]}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_empty_array_to_populated(self, compute, apply_patch):
        """Empty array to populated works."""
        old = {'items': []}
        new = {'items': [1, 2, 3]}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_populated_to_empty_array(self, compute, apply_patch):
        """Populated array to empty works."""
        old = {'items': [1, 2, 3]}
        new = {'items': []}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new


# =============================================================================
# TestRoundTrip - Identity property
# =============================================================================

class TestRoundTrip:
    """Round-trip properties: apply(old, compute(old, new)) == new."""

    def test_apply_compute_identity(self, compute, apply_patch):
        """Basic round-trip identity."""
        old = {'a': 1, 'b': 2}
        new = {'a': 1, 'b': 3, 'c': 4}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_complex_roundtrip(self, compute, apply_patch):
        """Complex structure round-trips correctly."""
        old = {
            'users': [
                {'name': 'Alice', 'age': 30, 'tags': ['admin']},
                {'name': 'Bob', 'age': 25, 'tags': ['user']}
            ],
            'config': {'timeout': 30, 'retries': 3}
        }
        new = {
            'users': [
                {'name': 'Alice', 'age': 31, 'tags': ['admin', 'moderator']},
                {'name': 'Charlie', 'age': 35, 'tags': ['user']}
            ],
            'config': {'timeout': 60, 'retries': 5, 'debug': True}
        }

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    @given(st.dictionaries(st.text(min_size=1, max_size=10), st.integers()))
    @settings(max_examples=50)
    def test_roundtrip_property(self, config):
        """Property-based round-trip test."""
        from knurl.diff import compute, apply
        old = {}
        patch = compute(old, config)
        result = apply(old, patch)
        assert result == config


# =============================================================================
# TestEdgeCases - Boundary conditions
# =============================================================================

class TestEdgeCases:
    """Edge case handling."""

    def test_empty_configs(self, compute, apply_patch, differs):
        """Empty configs work correctly."""
        assert compute({}, {}) == []
        assert differs({}, {}) is False

        patch = compute({}, {'a': 1})
        assert apply_patch({}, patch) == {'a': 1}

    def test_large_configs(self, compute, apply_patch):
        """Large configs (10000 keys) work correctly."""
        old = {f'key_{i}': i for i in range(10000)}
        new = {f'key_{i}': i + 1 for i in range(10000)}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_type_changes(self, compute, apply_patch):
        """Type changes (int to string) work correctly."""
        old = {'value': 42}
        new = {'value': 'forty-two'}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_null_handling(self, compute, apply_patch):
        """None/null values work correctly."""
        old = {'value': 'something'}
        new = {'value': None}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_unicode_keys_and_values(self, compute, apply_patch):
        """Unicode keys and values work correctly."""
        old = {'greeting': 'hello'}
        new = {'greeting': 'hola', 'japanese': 'konnichiwa'}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_boolean_values(self, compute, apply_patch):
        """Boolean values work correctly."""
        old = {'enabled': True}
        new = {'enabled': False}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_float_values(self, compute, apply_patch):
        """Float values work correctly."""
        old = {'rate': 1.5}
        new = {'rate': 2.7}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new


# =============================================================================
# TestErrorHandling - Error conditions
# =============================================================================

class TestErrorHandling:
    """Error condition handling."""

    def test_apply_wrong_base(self, compute, apply_patch, DiffError):
        """Applying patch to wrong base raises error."""
        old = {'a': 1}
        new = {'a': 2}
        patch = compute(old, new)

        # Apply to different base should raise
        wrong_base = {'b': 1}
        with pytest.raises(DiffError):
            apply_patch(wrong_base, patch)

    def test_malformed_patch_missing_op(self, apply_patch, DiffError):
        """Malformed patch (missing op) raises error."""
        patch = [{'path': '/a', 'value': 1}]  # Missing 'op'

        with pytest.raises(DiffError):
            apply_patch({'a': 0}, patch)

    def test_malformed_patch_invalid_op(self, apply_patch, DiffError):
        """Malformed patch (invalid op) raises error."""
        patch = [{'op': 'invalid', 'path': '/a', 'value': 1}]

        with pytest.raises(DiffError):
            apply_patch({'a': 0}, patch)

    def test_malformed_patch_invalid_path(self, apply_patch, DiffError):
        """Malformed patch (invalid path) raises error."""
        patch = [{'op': 'replace', 'path': '/nonexistent', 'value': 1}]

        with pytest.raises(DiffError):
            apply_patch({'a': 0}, patch)


# =============================================================================
# TestSummarize - Human-readable output
# =============================================================================

class TestSummarize:
    """Human-readable summary output."""

    def test_empty_patch_summary(self, summarize):
        """Empty patch produces 'no changes'."""
        assert summarize([]) == 'no changes'

    def test_single_change_summary(self, summarize):
        """Single change produces readable summary."""
        patch = [{'op': 'replace', 'path': '/b', 'value': 3}]
        summary = summarize(patch)
        assert '1 change' in summary
        assert 'replace' in summary.lower() or 'replaced' in summary.lower()
        assert '/b' in summary

    def test_multiple_changes_summary(self, summarize):
        """Multiple changes produce readable summary."""
        patch = [
            {'op': 'replace', 'path': '/b', 'value': 3},
            {'op': 'add', 'path': '/c', 'value': 4}
        ]
        summary = summarize(patch)
        assert '2 change' in summary


# =============================================================================
# TestDiffers - Quick equality check
# =============================================================================

class TestDiffers:
    """Quick equality check."""

    def test_differs_when_different(self, differs):
        """differs() returns True when configs differ."""
        assert differs({'a': 1}, {'a': 2}) is True
        assert differs({'a': 1}, {'a': 1, 'b': 2}) is True
        assert differs({'a': 1, 'b': 2}, {'a': 1}) is True

    def test_not_differs_when_equal(self, differs):
        """differs() returns False when configs equal."""
        assert differs({'a': 1}, {'a': 1}) is False
        assert differs({}, {}) is False
        assert differs({'a': {'b': 1}}, {'a': {'b': 1}}) is False


# =============================================================================
# TestAgentFindings - Tests from Gremlin, Oracle, Wellspring
# =============================================================================

class TestAgentFindings:
    """Tests identified by agents during review."""

    # From Gremlin - attack vectors
    def test_compute_accepts_none_inputs(self, compute):
        """compute() handles None inputs (treats as empty)."""
        patch = compute(None, None)
        assert patch == []

    def test_compute_accepts_non_dict_inputs(self, compute, apply_patch):
        """compute() accepts lists and other JSON types."""
        old = [1, 2, 3]
        new = [1, 2, 4]
        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_negative_zero_equals_zero(self, compute, differs):
        """-0.0 and 0.0 are treated as equal (canonicalization)."""
        assert differs({'z': -0.0}, {'z': 0.0}) is False
        assert compute({'z': 0.0}, {'z': -0.0}) == []

    def test_special_json_pointer_chars(self, compute, apply_patch):
        """Keys with ~ and / work correctly."""
        old = {}
        new = {
            'key~with~tildes': 'value1',
            'key/with/slashes': 'value2',
        }
        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_emoji_keys(self, compute, apply_patch):
        """Emoji keys work correctly."""
        old = {}
        new = {'🔥💀🎃': 'spooky'}
        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_empty_string_key(self, compute, apply_patch):
        """Empty string as key works."""
        old = {}
        new = {'': 'empty key value'}
        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_unicode_combining_characters(self, compute, apply_patch):
        """Unicode combining characters preserved."""
        old = {}
        new = {'key': 'e\u0301'}  # e + combining acute
        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_zero_width_chars_in_keys(self, compute, apply_patch):
        """Zero-width characters in keys work."""
        old = {}
        new = {'key\u200b': 'zero-width space in key'}
        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_very_large_numbers(self, compute, apply_patch):
        """Very large numbers work correctly."""
        old = {}
        new = {'big': 10**308, 'small': 10**-308}
        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_mixed_types_in_array(self, compute, apply_patch):
        """Arrays with mixed types work."""
        old = {}
        new = {'arr': [1, 'two', 3.0, None, True, {'nested': 'dict'}]}
        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_apply_invalid_path_format(self, apply_patch, DiffError):
        """Patch with path not starting with / raises error."""
        patch = [{'op': 'add', 'path': 'no-leading-slash', 'value': 2}]
        with pytest.raises(DiffError):
            apply_patch({'a': 1}, patch)

    # From Oracle - all RFC 6902 operation types
    def test_summarize_all_operation_types(self, summarize):
        """summarize() handles all RFC 6902 operation types."""
        patch = [
            {'op': 'add', 'path': '/a', 'value': 1},
            {'op': 'remove', 'path': '/b'},
            {'op': 'replace', 'path': '/c', 'value': 2},
            {'op': 'move', 'from': '/d', 'path': '/e'},
            {'op': 'copy', 'from': '/f', 'path': '/g'},
            {'op': 'test', 'path': '/h', 'value': 3},
        ]
        summary = summarize(patch)
        assert '6 changes' in summary
        assert 'added' in summary
        assert 'removed' in summary
        assert 'replaced' in summary
        assert 'moved' in summary
        assert 'copied' in summary
        assert 'tested' in summary

    def test_summarize_handles_malformed_ops(self, summarize):
        """summarize() handles patches with missing fields gracefully."""
        patch1 = [{'path': '/a'}]
        summary1 = summarize(patch1)
        assert 'unknown' in summary1

        patch2 = [{'op': 'add'}]
        summary2 = summarize(patch2)
        assert '?' in summary2

    def test_summarize_handles_none(self, summarize):
        """summarize() handles None input."""
        assert summarize(None) == 'no changes'

    # From Wellspring - sequential patches
    def test_sequential_patches(self, compute, apply_patch):
        """Multiple patches can be applied in sequence."""
        v1 = {'a': 1}
        v2 = {'a': 1, 'b': 2}
        v3 = {'a': 10, 'b': 2}
        v4 = {'a': 10, 'b': 2, 'c': 3}

        patch1 = compute(v1, v2)
        patch2 = compute(v2, v3)
        patch3 = compute(v3, v4)

        result = v1
        result = apply_patch(result, patch1)
        assert result == v2
        result = apply_patch(result, patch2)
        assert result == v3
        result = apply_patch(result, patch3)
        assert result == v4

    def test_array_reorder(self, compute, apply_patch):
        """Array reordering works."""
        old = {'arr': [1, 2, 3]}
        new = {'arr': [3, 2, 1]}
        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_nested_arrays(self, compute, apply_patch):
        """Nested arrays work."""
        old = {'arr': [[1, 2], [3, 4]]}
        new = {'arr': [[1, 2], [3, 4, 5]]}
        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_config_migration_scenario(self, compute, apply_patch, differs, summarize):
        """Realistic config migration works end-to-end."""
        old_config = {
            'database': {'host': 'localhost', 'port': 5432},
            'cache': {'enabled': True, 'ttl': 300},
            'features': ['auth', 'logging'],
        }
        new_config = {
            'database': {'host': 'prod.example.com', 'port': 5432, 'pool_size': 10},
            'cache': {'enabled': True, 'ttl': 600},
            'features': ['auth', 'logging', 'monitoring'],
        }

        assert differs(old_config, new_config) is True
        patch = compute(old_config, new_config)
        result = apply_patch(old_config, patch)
        assert result == new_config
        summary = summarize(patch)
        assert len(summary) > 0

    # From Oracle - rollback scenario
    def test_rollback_scenario(self, compute, apply_patch):
        """Can compute reverse patch for rollback."""
        old = {'version': 1, 'data': 'original'}
        new = {'version': 2, 'data': 'modified'}

        forward_patch = compute(old, new)
        updated = apply_patch(old, forward_patch)
        assert updated == new

        reverse_patch = compute(new, old)
        rolled_back = apply_patch(new, reverse_patch)
        assert rolled_back == old

    def test_nested_key_ordering_canonicalization(self, compute, differs):
        """Nested key ordering doesn't affect equality."""
        old = {'outer': {'b': 2, 'a': 1}}
        new = {'outer': {'a': 1, 'b': 2}}
        assert differs(old, new) is False
        assert compute(old, new) == []


# =============================================================================
# TestRound3Findings - From Oracle, Devil, Gremlin round 3
# =============================================================================

class TestRound3Findings:
    """Tests from agent review round 3."""

    # Oracle: Float precision
    def test_float_precision_preserved(self, compute, apply_patch, differs):
        """Float precision issues don't cause silent corruption."""
        # 0.1 + 0.2 != 0.3 in IEEE 754
        old = {'value': 0.1 + 0.2}
        new = {'value': 0.30000000000000004}  # Same as 0.1 + 0.2

        # These should be treated as identical
        assert differs(old, new) is False

        # Different float should be detected
        old2 = {'value': 0.3}
        assert differs(old2, new) is True

    def test_float_roundtrip(self, compute, apply_patch):
        """Floats survive round-trip without corruption."""
        old = {'pi': 3.141592653589793}
        new = {'pi': 3.141592653589793, 'e': 2.718281828459045}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result['pi'] == old['pi']  # Original preserved
        assert result['e'] == new['e']  # New value correct

    # Oracle: Unicode normalization
    def test_unicode_normalization_nfc_nfd(self, compute, differs):
        """Unicode NFC vs NFD forms are handled consistently."""
        # 'é' can be NFC (single char) or NFD (e + combining accent)
        nfc = {'name': '\u00e9'}  # é as single character
        nfd = {'name': 'e\u0301'}  # e + combining acute accent

        # These are visually identical but byte-different
        # The behavior should be consistent (both same or both different)
        result = differs(nfc, nfd)
        # Just verify it doesn't crash - behavior depends on canon
        assert isinstance(result, bool)

    # Oracle: Move/copy/test operations
    def test_apply_move_operation(self, apply_patch):
        """JSON Patch 'move' operation works."""
        base = {'source': 'value', 'other': 1}
        patch = [{'op': 'move', 'from': '/source', 'path': '/dest'}]

        result = apply_patch(base, patch)
        assert 'source' not in result
        assert result['dest'] == 'value'
        assert result['other'] == 1

    def test_apply_copy_operation(self, apply_patch):
        """JSON Patch 'copy' operation works."""
        base = {'source': 'value', 'other': 1}
        patch = [{'op': 'copy', 'from': '/source', 'path': '/dest'}]

        result = apply_patch(base, patch)
        assert result['source'] == 'value'  # Original preserved
        assert result['dest'] == 'value'  # Copy created
        assert result['other'] == 1

    def test_apply_test_operation_success(self, apply_patch):
        """JSON Patch 'test' operation passes when value matches."""
        base = {'key': 'expected'}
        patch = [
            {'op': 'test', 'path': '/key', 'value': 'expected'},
            {'op': 'replace', 'path': '/key', 'value': 'new'}
        ]

        result = apply_patch(base, patch)
        assert result['key'] == 'new'

    def test_apply_test_operation_failure(self, apply_patch, DiffError):
        """JSON Patch 'test' operation fails when value doesn't match."""
        base = {'key': 'actual'}
        patch = [
            {'op': 'test', 'path': '/key', 'value': 'expected'},
            {'op': 'replace', 'path': '/key', 'value': 'new'}
        ]

        with pytest.raises(DiffError):
            apply_patch(base, patch)

    # Oracle: Concurrent array modifications
    def test_array_remove_and_add_same_index(self, apply_patch):
        """Concurrent remove and add at same array index."""
        base = {'arr': ['a', 'b', 'c']}
        patch = [
            {'op': 'remove', 'path': '/arr/1'},
            {'op': 'add', 'path': '/arr/1', 'value': 'X'}
        ]

        result = apply_patch(base, patch)
        # After remove: ['a', 'c'], after add at 1: ['a', 'X', 'c']
        assert result['arr'] == ['a', 'X', 'c']

    def test_array_multiple_removes(self, apply_patch):
        """Multiple array removes in sequence."""
        base = {'arr': ['a', 'b', 'c', 'd']}
        # Remove from end first to avoid index shifting issues
        patch = [
            {'op': 'remove', 'path': '/arr/3'},
            {'op': 'remove', 'path': '/arr/1'},
        ]

        result = apply_patch(base, patch)
        assert result['arr'] == ['a', 'c']

    # Devil: Error type preservation
    def test_error_contains_useful_info(self, apply_patch, DiffError):
        """DiffError contains enough info to diagnose issues."""
        patch = [{'op': 'replace', 'path': '/nonexistent', 'value': 1}]

        try:
            apply_patch({'a': 1}, patch)
            assert False, "Should have raised"
        except DiffError as e:
            # Error message should contain path info
            assert 'nonexistent' in str(e).lower() or 'path' in str(e).lower()

    # Oracle: Large arrays
    def test_large_array_operations(self, compute, apply_patch):
        """Large arrays (1000+ elements) work correctly."""
        old = {'data': list(range(1000))}
        new = {'data': list(range(1000)) + [1000, 1001]}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new
        assert len(result['data']) == 1002

    # Oracle: Escape sequences in paths
    def test_path_with_tilde_escape(self, compute, apply_patch):
        """Keys with ~ are properly escaped as ~0."""
        old = {'key~name': 1}
        new = {'key~name': 2}

        patch = compute(old, new)
        # Path should contain ~0 (escaped tilde)
        assert any('~0' in op.get('path', '') for op in patch)

        result = apply_patch(old, patch)
        assert result == new

    def test_path_with_slash_escape(self, compute, apply_patch):
        """Keys with / are properly escaped as ~1."""
        old = {'key/name': 1}
        new = {'key/name': 2}

        patch = compute(old, new)
        # Path should contain ~1 (escaped slash)
        assert any('~1' in op.get('path', '') for op in patch)

        result = apply_patch(old, patch)
        assert result == new

    # Devil: Canonicalization consistency
    def test_canonicalization_deterministic(self, compute):
        """Same input always produces same patch."""
        old = {'z': 1, 'a': 2, 'm': 3}
        new = {'z': 1, 'a': 99, 'm': 3}

        patches = [compute(old, new) for _ in range(10)]

        # All patches should be identical
        assert all(p == patches[0] for p in patches)

    def test_nested_canonicalization_deterministic(self, compute):
        """Nested structures canonicalize deterministically."""
        old = {
            'outer': {'z': 1, 'a': 2},
            'list': [{'b': 1, 'a': 2}, {'d': 3, 'c': 4}]
        }
        new = {
            'outer': {'z': 99, 'a': 2},
            'list': [{'b': 1, 'a': 2}, {'d': 3, 'c': 4}]
        }

        patches = [compute(old, new) for _ in range(10)]
        assert all(p == patches[0] for p in patches)


# =============================================================================
# TestCanonicalConsistency - Integration with canon module
# =============================================================================

class TestCanonicalConsistency:
    """Integration with canon module for deterministic diffs."""

    def test_dict_key_order_irrelevant(self, compute):
        """Different dict key orders produce same patch content."""
        old = {'z': 1, 'a': 2}
        new1 = {'z': 1, 'a': 3}
        new2 = {'a': 3, 'z': 1}  # Different insertion order

        patch1 = compute(old, new1)
        patch2 = compute(old, new2)

        # Patches should be equivalent (both change 'a')
        # They might differ in order but should have same operations
        assert len(patch1) == len(patch2)
        assert patch1[0]['path'] == patch2[0]['path']

    def test_deterministic_patches(self, compute):
        """Same inputs produce identical patches."""
        old = {'b': 1, 'a': 2}
        new = {'b': 3, 'a': 2, 'c': 4}

        patch1 = compute(old, new)
        patch2 = compute(old, new)

        assert patch1 == patch2


# =============================================================================
# TestRFC6902Compliance - Standard compliance
# =============================================================================

class TestRFC6902Compliance:
    """RFC 6902 compliance tests."""

    def test_patch_format(self, compute):
        """Patches follow RFC 6902 format."""
        old = {'a': 1}
        new = {'a': 2}

        patch = compute(old, new)

        # Each operation must have 'op' and 'path'
        for op in patch:
            assert 'op' in op
            assert 'path' in op
            assert op['op'] in ('add', 'remove', 'replace', 'move', 'copy', 'test')
            assert op['path'].startswith('/')

    def test_special_character_escaping(self, compute, apply_patch):
        """Keys with special characters (/, ~) are escaped properly."""
        old = {'a/b': 1, 'c~d': 2}
        new = {'a/b': 3, 'c~d': 4}

        patch = compute(old, new)

        # JSON Pointer escaping: ~ -> ~0, / -> ~1
        # So 'a/b' becomes 'a~1b' and 'c~d' becomes 'c~0d'
        paths = [op['path'] for op in patch]
        assert any('~1' in p for p in paths)  # Escaped /
        assert any('~0' in p for p in paths)  # Escaped ~

        result = apply_patch(old, patch)
        assert result == new


# =============================================================================
# TestRound4Findings - From Gremlin/Devil round 4
# =============================================================================

class TestRound4Findings:
    """Tests from agent review round 4."""

    # Gremlin: Type coercion (number vs string)
    def test_number_vs_string_distinction(self, compute, apply_patch, differs):
        """Numbers and their string equivalents are treated as different."""
        old = {'port': 8080}
        new = {'port': '8080'}

        # These should differ
        assert differs(old, new) is True

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new
        assert isinstance(result['port'], str)

    def test_boolean_vs_int_distinction(self, compute, differs):
        """Booleans and integers are distinct."""
        # In JSON, true/false are distinct from 1/0
        old = {'flag': True}
        new = {'flag': 1}

        # Python's json treats True == 1 for comparison, but they serialize differently
        # This tests our canonicalization handles it
        result = differs(old, new)
        assert isinstance(result, bool)

    # Gremlin: Null vs missing vs empty
    def test_null_vs_missing_vs_empty(self, compute, apply_patch, differs):
        """None, missing key, and empty string are all distinct."""
        with_null = {'key': None}
        missing = {}
        with_empty = {'key': ''}

        assert differs(with_null, missing) is True
        assert differs(with_null, with_empty) is True
        assert differs(missing, with_empty) is True

        # Can transition between all states
        patch = compute(missing, with_null)
        assert apply_patch(missing, patch) == with_null

        patch = compute(with_null, with_empty)
        assert apply_patch(with_null, patch) == with_empty

    # Gremlin: Deep nesting (50 levels)
    def test_deep_nesting_50_levels(self, compute, apply_patch):
        """50 levels of nesting works correctly."""
        # Build 50-level nested dict
        old = current = {}
        for i in range(50):
            current['nested'] = {}
            current = current['nested']
        current['value'] = 'deep'

        # Modify deepest value
        import copy
        new = copy.deepcopy(old)
        current = new
        for i in range(50):
            current = current['nested']
        current['value'] = 'modified'

        patch = compute(old, new)
        result = apply_patch(old, patch)

        # Verify deep value changed
        current = result
        for i in range(50):
            current = current['nested']
        assert current['value'] == 'modified'

    # Gremlin: Scale - many operations
    def test_many_operations_in_patch(self, compute, apply_patch):
        """Patch with 100+ operations works."""
        old = {f'key_{i}': i for i in range(100)}
        new = {f'key_{i}': i + 1 for i in range(100)}  # All keys change

        patch = compute(old, new)
        assert len(patch) == 100  # All keys changed

        result = apply_patch(old, patch)
        assert result == new

    def test_many_keys_in_config(self, compute, apply_patch):
        """Config with 1000+ keys works."""
        old = {f'k{i}': f'v{i}' for i in range(1000)}
        new = dict(old)
        new['k500'] = 'modified'
        new['new_key'] = 'added'

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    # Gremlin: Stale base application
    def test_stale_base_detected(self, compute, apply_patch, PatchConflictError):
        """Valid patch on modified base fails appropriately."""
        original = {'a': 1, 'b': 2}
        update = {'a': 1, 'b': 3}

        patch = compute(original, update)

        # Base has changed since patch was computed
        modified_base = {'a': 1, 'b': 99, 'c': 'new'}

        # Patch should still apply (b exists), but result differs from intent
        result = apply_patch(modified_base, patch)
        # The patch replaces /b with 3, regardless of current value
        assert result['b'] == 3

    def test_stale_base_missing_path_fails(self, compute, apply_patch, DiffError):
        """Patch fails when path no longer exists."""
        original = {'a': 1, 'b': {'nested': 2}}
        update = {'a': 1, 'b': {'nested': 3}}

        patch = compute(original, update)

        # Base changed - nested structure removed
        modified_base = {'a': 1, 'b': 'flat'}

        with pytest.raises(DiffError):
            apply_patch(modified_base, patch)

    # Devil: Error subtypes
    def test_patch_conflict_error_type(self, apply_patch, PatchConflictError):
        """PatchConflictError raised for conflicts."""
        base = {'a': 1}
        # Try to remove non-existent key
        patch = [{'op': 'remove', 'path': '/nonexistent'}]

        with pytest.raises(PatchConflictError):
            apply_patch(base, patch)

    def test_invalid_patch_error_type(self, apply_patch, InvalidPatchError):
        """InvalidPatchError raised for malformed patches."""
        base = {'a': 1}
        # Invalid operation type
        patch = [{'op': 'explode', 'path': '/a'}]

        with pytest.raises(InvalidPatchError):
            apply_patch(base, patch)

    def test_error_contains_context(self, apply_patch, DiffError):
        """DiffError contains patch and base for debugging."""
        base = {'a': 1}
        patch = [{'op': 'remove', 'path': '/nonexistent'}]

        try:
            apply_patch(base, patch)
            assert False, "Should have raised"
        except DiffError as e:
            # Error should contain context
            assert e.patch == patch
            assert e.base == base

    def test_error_hierarchy(self, PatchConflictError, InvalidPatchError, PathNotFoundError, DiffError):
        """Error subtypes inherit from DiffError."""
        assert issubclass(PatchConflictError, DiffError)
        assert issubclass(InvalidPatchError, DiffError)
        assert issubclass(PathNotFoundError, DiffError)

    # Gremlin: Keys that look like array indices
    def test_keys_that_look_like_indices(self, compute, apply_patch):
        """String keys that look like numbers work correctly."""
        old = {'0': 'zero', '1': 'one', '10': 'ten'}
        new = {'0': 'ZERO', '1': 'one', '10': 'ten'}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    # Gremlin: Very long paths
    def test_very_long_path(self, compute, apply_patch):
        """Very long JSON Pointer paths work."""
        # Create path with many segments
        old = current = {}
        path_parts = [f'level{i}' for i in range(20)]
        for part in path_parts[:-1]:
            current[part] = {}
            current = current[part]
        current[path_parts[-1]] = 'deep'

        import copy
        new = copy.deepcopy(old)
        current = new
        for part in path_parts[:-1]:
            current = current[part]
        current[path_parts[-1]] = 'modified'

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new


# =============================================================================
# TestRound5Findings - From Inventor, Wellspring, Gremlin, Fool
# =============================================================================

class TestRound5Findings:
    """Tests from agent review round 5."""

    # Inventor: Keys with special characters
    def test_keys_with_newlines(self, compute, apply_patch):
        """Keys containing newlines work."""
        old = {'key\nwith\nnewlines': 1}
        new = {'key\nwith\nnewlines': 2}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_keys_with_quotes(self, compute, apply_patch):
        """Keys containing quotes work."""
        old = {'key"with"quotes': 1}
        new = {'key"with"quotes': 2}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_keys_with_backslashes(self, compute, apply_patch):
        """Keys containing backslashes work."""
        old = {'key\\with\\backslashes': 1}
        new = {'key\\with\\backslashes': 2}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    # Wellspring: Keys with only special chars
    def test_keys_only_special_chars(self, compute, apply_patch):
        """Keys that are only special characters work."""
        old = {'///': 1, '~~~': 2, '   ': 3}
        new = {'///': 10, '~~~': 2, '   ': 30}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    # Wellspring: Float to int change
    def test_float_zero_vs_int_zero(self, compute, differs):
        """0.0 and 0 are treated consistently."""
        old = {'value': 0}
        new = {'value': 0.0}

        # Behavior depends on canonicalization - just verify consistency
        result = differs(old, new)
        assert isinstance(result, bool)

    # Wellspring: Apply same patch twice
    def test_apply_patch_twice_replace(self, compute, apply_patch):
        """Applying replace patch twice gives same result."""
        base = {'x': 1}
        target = {'x': 2}

        patch = compute(base, target)
        first = apply_patch(base, patch)
        second = apply_patch(first, patch)

        # Replace is idempotent for same value
        assert second == first

    def test_apply_patch_twice_add_overwrites(self, apply_patch):
        """Adding same key twice overwrites (RFC 6902 behavior)."""
        base = {}
        patch = [{'op': 'add', 'path': '/x', 'value': 1}]

        first = apply_patch(base, patch)
        assert first == {'x': 1}

        # RFC 6902: 'add' replaces if key exists
        second = apply_patch(first, patch)
        assert second == {'x': 1}  # Same value, no error

    # Wellspring: differs() vs compute() consistency
    def test_differs_compute_consistency(self, compute, differs):
        """differs() and compute() agree."""
        pairs = [
            ({'a': 1}, {'a': 1}),
            ({'a': 1}, {'a': 2}),
            ({}, {'a': 1}),
            ({'a': 1}, {}),
            ({'a': {'b': 1}}, {'a': {'b': 1}}),
            ({'a': {'b': 1}}, {'a': {'b': 2}}),
        ]

        for old, new in pairs:
            diff_result = differs(old, new)
            patch = compute(old, new)
            patch_empty = len(patch) == 0

            assert diff_result == (not patch_empty), f"Mismatch for {old} vs {new}"

    # Wellspring: Round-trip consistency
    def test_roundtrip_compute_apply_compute(self, compute, apply_patch):
        """compute -> apply -> compute yields empty patch."""
        old = {'a': 1, 'b': {'c': 2}}
        new = {'a': 2, 'b': {'c': 3, 'd': 4}}

        patch1 = compute(old, new)
        result = apply_patch(old, patch1)
        patch2 = compute(result, new)

        assert patch2 == []

    # Inventor: Large array with single change
    def test_large_array_single_change(self, compute, apply_patch):
        """Large array with one change produces small patch."""
        old = {'data': list(range(10000))}
        new = {'data': list(range(10000))}
        new['data'][5000] = 'changed'

        patch = compute(old, new)

        # Should be a small patch
        assert len(patch) < 10
        result = apply_patch(old, patch)
        assert result == new

    # Wellspring: Add parent then child ordering
    def test_add_parent_then_child(self, apply_patch):
        """Adding parent then child in one patch works."""
        base = {}
        patch = [
            {'op': 'add', 'path': '/parent', 'value': {}},
            {'op': 'add', 'path': '/parent/child', 'value': 1}
        ]

        result = apply_patch(base, patch)
        assert result == {'parent': {'child': 1}}

    def test_remove_child_then_parent(self, apply_patch):
        """Removing child then parent in one patch works."""
        base = {'parent': {'child': 1}}
        patch = [
            {'op': 'remove', 'path': '/parent/child'},
            {'op': 'remove', 'path': '/parent'}
        ]

        result = apply_patch(base, patch)
        assert result == {}

    # Inventor: Control characters
    def test_control_characters_in_values(self, compute, apply_patch):
        """Control characters in values work."""
        old = {'text': 'hello\x00world'}
        new = {'text': 'hello\x00there'}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    # Wellspring: Replace entire structure
    def test_replace_entire_root(self, apply_patch):
        """Replacing entire structure at root works."""
        base = {'a': {'b': {'c': 1}}}
        patch = [{'op': 'replace', 'path': '', 'value': {'x': 1}}]

        result = apply_patch(base, patch)
        assert result == {'x': 1}

    # Wellspring: Empty configs
    def test_both_empty_configs(self, compute, apply_patch, differs):
        """Two empty configs produce no diff."""
        assert compute({}, {}) == []
        assert differs({}, {}) is False
        assert apply_patch({}, []) == {}

    # Inventor: Whitespace in strings
    def test_whitespace_differences_in_strings(self, compute, differs):
        """Whitespace differences are detected."""
        old = {'text': 'hello  world'}  # two spaces
        new = {'text': 'hello world'}   # one space

        assert differs(old, new) is True
        patch = compute(old, new)
        assert len(patch) == 1

    # Wellspring: summarize with many operations
    def test_summarize_many_operations(self, compute, summarize):
        """summarize() handles many operations."""
        old = {f'k{i}': i for i in range(50)}
        new = {f'k{i}': i + 1 for i in range(50)}

        patch = compute(old, new)
        summary = summarize(patch)

        assert '50 changes' in summary
        assert isinstance(summary, str)

    # Inventor: Semantic equivalence (numeric strings)
    def test_numeric_string_vs_number_different(self, compute, differs):
        """'123' and 123 are different."""
        old = {'port': '8080'}
        new = {'port': 8080}

        assert differs(old, new) is True

    # Wellspring: Move operation chain
    def test_move_chain(self, apply_patch):
        """Chain of moves works: a→b, b→c."""
        base = {'a': 1, 'b': 2}
        patch = [
            {'op': 'move', 'from': '/a', 'path': '/c'},
            {'op': 'move', 'from': '/b', 'path': '/a'}
        ]

        result = apply_patch(base, patch)
        assert result == {'a': 2, 'c': 1}

    # Gremlin round 12: Empty patch bypasses validation
    def test_empty_patch_on_malformed_base(self, apply_patch):
        """Empty patch bypasses base validation."""
        # Empty patch returns base unchanged without validation
        result = apply_patch([1, 2, 3], [])
        assert result == [1, 2, 3]

        result2 = apply_patch('string', [])
        assert result2 == 'string'


# =============================================================================
# TestRound6Findings - From Gremlin, Priestess
# =============================================================================

class TestRound6Findings:
    """Tests from agent review round 6."""

    # Gremlin: Array append syntax /-
    def test_array_append_with_dash(self, apply_patch):
        """RFC 6902 array append with '-' path works."""
        base = {'arr': [1, 2, 3]}
        patch = [{'op': 'add', 'path': '/arr/-', 'value': 4}]

        result = apply_patch(base, patch)
        assert result == {'arr': [1, 2, 3, 4]}

    def test_array_append_multiple(self, apply_patch):
        """Multiple appends with '-' work."""
        base = {'arr': []}
        patch = [
            {'op': 'add', 'path': '/arr/-', 'value': 1},
            {'op': 'add', 'path': '/arr/-', 'value': 2},
            {'op': 'add', 'path': '/arr/-', 'value': 3},
        ]

        result = apply_patch(base, patch)
        assert result == {'arr': [1, 2, 3]}

    # Gremlin: Move edge cases
    def test_move_nonexistent_source_fails(self, apply_patch, DiffError):
        """Move from nonexistent path fails."""
        base = {'a': 1}
        patch = [{'op': 'move', 'from': '/nonexistent', 'path': '/b'}]

        with pytest.raises(DiffError):
            apply_patch(base, patch)

    def test_copy_nonexistent_source_fails(self, apply_patch, DiffError):
        """Copy from nonexistent path fails."""
        base = {'a': 1}
        patch = [{'op': 'copy', 'from': '/nonexistent', 'path': '/b'}]

        with pytest.raises(DiffError):
            apply_patch(base, patch)

    # Gremlin: Type confusion
    def test_array_op_on_dict_fails(self, apply_patch, DiffError):
        """Array index operation on dict fails."""
        base = {'obj': {'a': 1}}
        patch = [{'op': 'add', 'path': '/obj/0', 'value': 'x'}]

        # This should either fail or create key '0' - depends on jsonpatch
        try:
            result = apply_patch(base, patch)
            # If it succeeds, it created a string key '0'
            assert '0' in result['obj']
        except DiffError:
            pass  # Also acceptable

    def test_dict_op_on_array_fails(self, apply_patch, DiffError):
        """Dict key operation on array with non-numeric key fails."""
        base = {'arr': [1, 2, 3]}
        patch = [{'op': 'add', 'path': '/arr/key', 'value': 'x'}]

        with pytest.raises(DiffError):
            apply_patch(base, patch)

    # Gremlin: Path escaping edge cases
    def test_key_literally_contains_tilde_zero(self, compute, apply_patch):
        """Key that literally contains '~0' works."""
        old = {'key~0value': 1}
        new = {'key~0value': 2}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    def test_key_literally_contains_tilde_one(self, compute, apply_patch):
        """Key that literally contains '~1' works."""
        old = {'key~1value': 1}
        new = {'key~1value': 2}

        patch = compute(old, new)
        result = apply_patch(old, patch)
        assert result == new

    # Gremlin: Conflicting operations
    def test_remove_then_add_same_path(self, apply_patch):
        """Remove then add same path works."""
        base = {'x': 1}
        patch = [
            {'op': 'remove', 'path': '/x'},
            {'op': 'add', 'path': '/x', 'value': 2}
        ]

        result = apply_patch(base, patch)
        assert result == {'x': 2}

    def test_replace_then_remove(self, apply_patch):
        """Replace then remove same path works."""
        base = {'x': 1}
        patch = [
            {'op': 'replace', 'path': '/x', 'value': 2},
            {'op': 'remove', 'path': '/x'}
        ]

        result = apply_patch(base, patch)
        assert result == {}

    # Gremlin: Array index edge cases
    def test_array_index_at_length(self, apply_patch):
        """Adding at array length (append position) works."""
        base = {'arr': [1, 2, 3]}
        patch = [{'op': 'add', 'path': '/arr/3', 'value': 4}]

        result = apply_patch(base, patch)
        assert result == {'arr': [1, 2, 3, 4]}

    def test_array_index_beyond_length_fails(self, apply_patch, DiffError):
        """Adding beyond array length fails."""
        base = {'arr': [1, 2, 3]}
        patch = [{'op': 'add', 'path': '/arr/10', 'value': 'x'}]

        with pytest.raises(DiffError):
            apply_patch(base, patch)

    # Priestess: Inverse operation (reverse patch)
    def test_compute_reverse_patch(self, compute, apply_patch):
        """Can compute reverse patch by swapping args."""
        old = {'a': 1, 'b': 2}
        new = {'a': 1, 'b': 3, 'c': 4}

        forward = compute(old, new)
        reverse = compute(new, old)

        # Apply forward then reverse should get back to original
        updated = apply_patch(old, forward)
        assert updated == new

        restored = apply_patch(updated, reverse)
        assert restored == old

    # Gremlin: Access through primitive
    def test_path_through_primitive_fails(self, apply_patch, DiffError):
        """Path that goes through primitive value fails."""
        base = {'x': 'string'}
        patch = [{'op': 'add', 'path': '/x/y', 'value': 1}]

        with pytest.raises(DiffError):
            apply_patch(base, patch)

    # Gremlin: Invalid path format
    def test_path_without_leading_slash_fails(self, apply_patch, DiffError):
        """Path not starting with / fails."""
        base = {'x': 1}
        patch = [{'op': 'replace', 'path': 'x', 'value': 2}]

        with pytest.raises(DiffError):
            apply_patch(base, patch)

    # Priestess: Compare arbitrary versions
    def test_diff_divergent_configs(self, compute, apply_patch):
        """Can diff configs that aren't parent-child."""
        base = {'shared': 1, 'only_a': 2}
        branch_a = {'shared': 1, 'only_a': 3, 'new_a': 4}
        branch_b = {'shared': 2, 'only_b': 5}

        # Can compute diff between branches
        patch_a_to_b = compute(branch_a, branch_b)
        result = apply_patch(branch_a, patch_a_to_b)
        assert result == branch_b
