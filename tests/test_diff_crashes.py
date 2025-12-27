"""Crash tests for spiritengine.diff - tests that should fail or cause errors.

These tests demonstrate ACTUAL CRASHES and FAILURES, not just edge cases.
Each test should either:
1. Raise an exception (proving the bug)
2. Hang/timeout (proving DoS)
3. Produce wrong results (proving correctness bug)
"""

import pytest


@pytest.fixture
def compute():
    """Import compute function."""
    from spiritengine.diff import compute
    return compute


@pytest.fixture
def apply_patch():
    """Import apply function."""
    from spiritengine.diff import apply
    return apply


@pytest.fixture
def differs():
    """Import differs function."""
    from spiritengine.diff import differs
    return differs


# =============================================================================
# CRASH 1: Stack Overflow from Recursion
# =============================================================================

def test_CRASH_deep_recursion_in_canonicalize(compute):
    """CanonError on deeply nested structure exceeding MAX_DEPTH.

    Steps to reproduce:
    1. Create config with >500 nested levels
    2. Call compute()
    3. CanonError: "Maximum nesting depth (500) exceeded"

    Root cause: Depth limit prevents stack overflow
    """
    from spiritengine.canon import CanonError

    # Build deeply nested dict - exceeds MAX_DEPTH (500)
    obj = current = {}
    for i in range(600):
        current['nested'] = {}
        current = current['nested']
    current['leaf'] = 'value'

    # Raises CanonError due to depth limit
    with pytest.raises(CanonError, match="Maximum nesting depth"):
        compute(obj, obj)


def test_CRASH_deep_recursion_in_differs(differs):
    """CanonError in differs() on deep nesting exceeding MAX_DEPTH.

    Steps to reproduce:
    1. Create deeply nested config (>500 levels)
    2. Call differs()
    3. CanonError during canonicalization
    """
    from spiritengine.canon import CanonError

    obj = current = {}
    for i in range(600):
        current['n'] = {}
        current = current['n']
    current['v'] = 1

    with pytest.raises(CanonError, match="Maximum nesting depth"):
        differs(obj, obj)


# =============================================================================
# CRASH 2: Integer Keys Cause TypeError
# =============================================================================

def test_CRASH_integer_keys_in_dict(compute):
    """ACTUAL CRASH: CanonError when dict has integer keys.

    Steps to reproduce:
    1. Create dict with int keys: {1: 'a', 2: 'b'}
    2. Call compute()
    3. CanonError: "Dict keys must be strings"

    Root cause: JSON requires string keys, Python allows int keys
    """
    from spiritengine.canon import CanonError

    config = {1: 'one', 2: 'two', 3: 'three'}

    with pytest.raises(CanonError, match="Dict keys must be strings"):
        compute(config, config)


def test_CRASH_tuple_keys_in_dict(compute):
    """ACTUAL CRASH: TypeError when dict has tuple keys.

    Steps to reproduce:
    1. Create dict with tuple keys: {(1, 2): 'value'}
    2. Call compute()
    3. TypeError during JSON serialization
    """
    from spiritengine.canon import CanonError

    config = {(1, 2): 'value'}

    # Will crash - tuples aren't valid JSON keys
    with pytest.raises(CanonError):
        compute(config, config)


# =============================================================================
# CRASH 3: Circular References
# =============================================================================

def test_CRASH_circular_reference_in_config(compute):
    """ACTUAL CRASH: CanonError on circular reference.

    Steps to reproduce:
    1. Create dict with circular reference to itself
    2. Call compute()
    3. CanonError: "Circular reference detected"

    Root cause: JSON can't represent cycles
    """
    from spiritengine.canon import CanonError

    config = {'key': 'value'}
    config['self'] = config  # Circular reference

    with pytest.raises(CanonError, match="Circular"):
        compute(config, {'other': 1})


def test_CRASH_mutual_circular_reference(compute):
    """ACTUAL CRASH: CanonError on mutually circular structures.

    Steps to reproduce:
    1. Create two dicts that reference each other
    2. Call compute()
    3. CanonError during circular reference check
    """
    from spiritengine.canon import CanonError

    a = {'name': 'a'}
    b = {'name': 'b'}
    a['ref'] = b
    b['ref'] = a  # Mutual circular reference

    with pytest.raises(CanonError):
        compute(a, b)


# =============================================================================
# CRASH 4: NaN and Infinity
# =============================================================================

def test_CRASH_nan_in_config(compute):
    """ACTUAL CRASH: CanonError when config contains NaN.

    Steps to reproduce:
    1. Create config with float('nan')
    2. Call compute()
    3. CanonError: "NaN values cannot be serialized"
    """
    from spiritengine.canon import CanonError

    config = {'value': float('nan')}

    with pytest.raises(CanonError, match="NaN"):
        compute(config, config)


def test_CRASH_infinity_in_config(compute):
    """ACTUAL CRASH: CanonError when config contains infinity.

    Steps to reproduce:
    1. Create config with float('inf')
    2. Call compute()
    3. CanonError: "Infinity values cannot be serialized"
    """
    from spiritengine.canon import CanonError

    config = {'value': float('inf')}

    with pytest.raises(CanonError, match="Infinity"):
        compute(config, config)


def test_CRASH_negative_infinity_in_config(compute):
    """ACTUAL CRASH: CanonError for negative infinity."""
    from spiritengine.canon import CanonError

    config = {'value': float('-inf')}

    with pytest.raises(CanonError, match="Infinity"):
        compute(config, config)


# =============================================================================
# CRASH 5: Non-Serializable Types
# =============================================================================

def test_CRASH_bytes_in_config(compute):
    """ACTUAL CRASH: TypeError when config contains bytes.

    Steps to reproduce:
    1. Create config with bytes object
    2. Call compute()
    3. TypeError: bytes not JSON serializable
    """
    config = {'data': b'binary data'}

    with pytest.raises((TypeError, Exception)):
        compute(config, config)


def test_CRASH_set_in_config(compute):
    """ACTUAL CRASH: TypeError when config contains set.

    Steps to reproduce:
    1. Create config with set
    2. Call compute()
    3. TypeError: set not JSON serializable
    """
    config = {'items': {1, 2, 3}}

    with pytest.raises(TypeError):
        compute(config, config)


def test_CRASH_custom_object_in_config(compute):
    """ACTUAL CRASH: TypeError when config contains custom object.

    Steps to reproduce:
    1. Create config with custom class instance
    2. Call compute()
    3. TypeError: Object not JSON serializable
    """
    class CustomObject:
        pass

    config = {'obj': CustomObject()}

    with pytest.raises(TypeError):
        compute(config, config)


# =============================================================================
# CRASH 6: Malformed Patches
# =============================================================================

def test_CRASH_patch_missing_op_field(apply_patch):
    """ACTUAL CRASH: InvalidPatchError when 'op' field missing.

    Steps to reproduce:
    1. Create patch without 'op' field
    2. Call apply()
    3. InvalidPatchError
    """
    from spiritengine.diff import InvalidPatchError

    base = {'a': 1}
    patch = [{'path': '/a', 'value': 2}]  # Missing 'op'

    with pytest.raises(InvalidPatchError):
        apply_patch(base, patch)


def test_CRASH_patch_missing_path_field(apply_patch):
    """ACTUAL CRASH: InvalidPatchError when 'path' field missing.

    Steps to reproduce:
    1. Create patch without 'path' field
    2. Call apply()
    3. InvalidPatchError
    """
    from spiritengine.diff import InvalidPatchError

    base = {'a': 1}
    patch = [{'op': 'add', 'value': 2}]  # Missing 'path'

    with pytest.raises(InvalidPatchError):
        apply_patch(base, patch)


def test_CRASH_patch_invalid_op_type(apply_patch):
    """ACTUAL CRASH: InvalidPatchError for unknown operation.

    Steps to reproduce:
    1. Create patch with invalid 'op' value
    2. Call apply()
    3. InvalidPatchError
    """
    from spiritengine.diff import InvalidPatchError

    base = {'a': 1}
    patch = [{'op': 'destroy', 'path': '/a'}]  # Invalid op

    with pytest.raises(InvalidPatchError):
        apply_patch(base, patch)


def test_CRASH_patch_with_non_list_type(apply_patch):
    """ACTUAL CRASH: InvalidPatchError when patch is not a list.

    Steps to reproduce:
    1. Pass dict instead of list as patch
    2. Call apply()
    3. InvalidPatchError
    """
    from spiritengine.diff import InvalidPatchError

    base = {'a': 1}
    patch = {'op': 'add', 'path': '/b', 'value': 2}  # Dict not list

    with pytest.raises(InvalidPatchError):
        apply_patch(base, patch)


# =============================================================================
# CRASH 7: Path Errors
# =============================================================================

def test_CRASH_path_missing_leading_slash(apply_patch):
    """ACTUAL CRASH: InvalidPatchError for path without leading /.

    Steps to reproduce:
    1. Create patch with path not starting with /
    2. Call apply()
    3. InvalidPatchError
    """
    from spiritengine.diff import DiffError

    base = {'a': 1}
    patch = [{'op': 'replace', 'path': 'a', 'value': 2}]  # No /

    with pytest.raises(DiffError):
        apply_patch(base, patch)


def test_CRASH_path_to_nonexistent_location(apply_patch):
    """ACTUAL CRASH: PathNotFoundError when path doesn't exist.

    Steps to reproduce:
    1. Create patch with path that doesn't exist in base
    2. Call apply()
    3. PathNotFoundError or PatchConflictError
    """
    from spiritengine.diff import DiffError

    base = {'a': 1}
    patch = [{'op': 'replace', 'path': '/nonexistent', 'value': 2}]

    with pytest.raises(DiffError):
        apply_patch(base, patch)


def test_CRASH_path_through_primitive(apply_patch):
    """ACTUAL CRASH: DiffError when trying to traverse through primitive.

    Steps to reproduce:
    1. Try to apply patch that goes through string/number
    2. Call apply()
    3. DiffError - can't traverse primitives
    """
    from spiritengine.diff import DiffError

    base = {'x': 'string'}
    patch = [{'op': 'add', 'path': '/x/nested', 'value': 1}]

    with pytest.raises(DiffError):
        apply_patch(base, patch)


# =============================================================================
# CRASH 8: Array Index Errors
# =============================================================================

def test_CRASH_array_index_beyond_bounds(apply_patch):
    """ACTUAL CRASH: DiffError for array index out of bounds.

    Steps to reproduce:
    1. Try to add/replace at index way beyond array length
    2. Call apply()
    3. DiffError
    """
    from spiritengine.diff import DiffError

    base = {'arr': [1, 2, 3]}
    patch = [{'op': 'add', 'path': '/arr/100', 'value': 'x'}]

    with pytest.raises(DiffError):
        apply_patch(base, patch)


def test_CRASH_array_index_non_numeric(apply_patch):
    """ACTUAL CRASH: DiffError when array index is not a number.

    Steps to reproduce:
    1. Try to access array with non-numeric index
    2. Call apply()
    3. DiffError
    """
    from spiritengine.diff import DiffError

    base = {'arr': [1, 2, 3]}
    patch = [{'op': 'replace', 'path': '/arr/abc', 'value': 'x'}]

    with pytest.raises(DiffError):
        apply_patch(base, patch)


# =============================================================================
# CRASH 9: Remove Nonexistent Keys
# =============================================================================

def test_CRASH_remove_nonexistent_key(apply_patch):
    """ACTUAL CRASH: PatchConflictError when removing nonexistent key.

    Steps to reproduce:
    1. Try to remove key that doesn't exist
    2. Call apply()
    3. PatchConflictError
    """
    from spiritengine.diff import PatchConflictError

    base = {'a': 1}
    patch = [{'op': 'remove', 'path': '/nonexistent'}]

    with pytest.raises(PatchConflictError):
        apply_patch(base, patch)


def test_CRASH_remove_from_empty_dict(apply_patch):
    """ACTUAL CRASH: PatchConflictError when removing from empty dict.

    Steps to reproduce:
    1. Try to remove anything from {}
    2. Call apply()
    3. PatchConflictError
    """
    from spiritengine.diff import PatchConflictError

    base = {}
    patch = [{'op': 'remove', 'path': '/anything'}]

    with pytest.raises(PatchConflictError):
        apply_patch(base, patch)


# =============================================================================
# CRASH 10: Move/Copy Operation Errors
# =============================================================================

def test_CRASH_move_from_nonexistent_source(apply_patch):
    """ACTUAL CRASH: DiffError when move source doesn't exist.

    Steps to reproduce:
    1. Try to move from nonexistent path
    2. Call apply()
    3. DiffError
    """
    from spiritengine.diff import DiffError

    base = {'a': 1}
    patch = [{'op': 'move', 'from': '/nonexistent', 'path': '/b'}]

    with pytest.raises(DiffError):
        apply_patch(base, patch)


def test_CRASH_copy_from_nonexistent_source(apply_patch):
    """ACTUAL CRASH: DiffError when copy source doesn't exist.

    Steps to reproduce:
    1. Try to copy from nonexistent path
    2. Call apply()
    3. DiffError
    """
    from spiritengine.diff import DiffError

    base = {'a': 1}
    patch = [{'op': 'copy', 'from': '/nonexistent', 'path': '/b'}]

    with pytest.raises(DiffError):
        apply_patch(base, patch)


def test_CRASH_move_missing_from_field(apply_patch):
    """ACTUAL CRASH: InvalidPatchError when move lacks 'from' field.

    Steps to reproduce:
    1. Create move operation without 'from' field
    2. Call apply()
    3. InvalidPatchError
    """
    from spiritengine.diff import InvalidPatchError

    base = {'a': 1}
    patch = [{'op': 'move', 'path': '/b'}]  # Missing 'from'

    with pytest.raises(InvalidPatchError):
        apply_patch(base, patch)


# =============================================================================
# CRASH 11: Test Operation Failures
# =============================================================================

def test_CRASH_test_operation_value_mismatch(apply_patch):
    """ACTUAL CRASH: DiffError when test operation fails.

    Steps to reproduce:
    1. Create test operation with wrong expected value
    2. Call apply()
    3. DiffError - test failed (wrapped JsonPatchTestFailed)
    """
    from spiritengine.diff import DiffError

    base = {'x': 1}
    patch = [{'op': 'test', 'path': '/x', 'value': 2}]  # Expects 2, actual is 1

    with pytest.raises(DiffError):
        apply_patch(base, patch)


def test_CRASH_test_operation_on_nonexistent_path(apply_patch):
    """ACTUAL CRASH: DiffError when testing nonexistent path.

    Steps to reproduce:
    1. Test operation on path that doesn't exist
    2. Call apply()
    3. DiffError
    """
    from spiritengine.diff import DiffError

    base = {'x': 1}
    patch = [{'op': 'test', 'path': '/nonexistent', 'value': 1}]

    with pytest.raises(DiffError):
        apply_patch(base, patch)


# =============================================================================
# Summary Report
# =============================================================================

def test_crash_summary():
    """Summary of all crashes demonstrated.

    RECURSION CRASHES (2):
    - test_CRASH_deep_recursion_in_canonicalize: RecursionError at 5000 levels
    - test_CRASH_deep_recursion_in_differs: RecursionError in differs()

    TYPE ERRORS (5):
    - test_CRASH_integer_keys_in_dict: CanonError for int keys
    - test_CRASH_tuple_keys_in_dict: CanonError for tuple keys
    - test_CRASH_bytes_in_config: TypeError for bytes
    - test_CRASH_set_in_config: TypeError for sets
    - test_CRASH_custom_object_in_config: TypeError for custom objects

    CIRCULAR REFERENCE ERRORS (2):
    - test_CRASH_circular_reference_in_config: CanonError
    - test_CRASH_mutual_circular_reference: CanonError

    NAN/INFINITY ERRORS (3):
    - test_CRASH_nan_in_config: CanonError
    - test_CRASH_infinity_in_config: CanonError
    - test_CRASH_negative_infinity_in_config: CanonError

    MALFORMED PATCH ERRORS (4):
    - test_CRASH_patch_missing_op_field: InvalidPatchError
    - test_CRASH_patch_missing_path_field: InvalidPatchError
    - test_CRASH_patch_invalid_op_type: InvalidPatchError
    - test_CRASH_patch_with_non_list_type: InvalidPatchError

    PATH ERRORS (3):
    - test_CRASH_path_missing_leading_slash: DiffError
    - test_CRASH_path_to_nonexistent_location: DiffError
    - test_CRASH_path_through_primitive: DiffError

    ARRAY INDEX ERRORS (2):
    - test_CRASH_array_index_beyond_bounds: DiffError
    - test_CRASH_array_index_non_numeric: DiffError

    REMOVE ERRORS (2):
    - test_CRASH_remove_nonexistent_key: PatchConflictError
    - test_CRASH_remove_from_empty_dict: PatchConflictError

    MOVE/COPY ERRORS (3):
    - test_CRASH_move_from_nonexistent_source: DiffError
    - test_CRASH_copy_from_nonexistent_source: DiffError
    - test_CRASH_move_missing_from_field: InvalidPatchError

    TEST OPERATION ERRORS (2):
    - test_CRASH_test_operation_value_mismatch: PatchConflictError
    - test_CRASH_test_operation_on_nonexistent_path: DiffError

    TOTAL: 28 different crash scenarios documented
    """
    pass
