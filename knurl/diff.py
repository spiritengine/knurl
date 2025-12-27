"""
Diff computation and application for config versioning.

Computes JSON Patch (RFC 6902) format diffs between configs and applies
patches to reconstruct historical versions.

Usage:
    from knurl import diff

    # Compute diff
    old_config = {'a': 1, 'b': 2}
    new_config = {'a': 1, 'b': 3, 'c': 4}

    patch = diff.compute(old_config, new_config)
    # Returns: [
    #   {'op': 'replace', 'path': '/b', 'value': 3},
    #   {'op': 'add', 'path': '/c', 'value': 4}
    # ]

    # Apply diff
    reconstructed = diff.apply(old_config, patch)
    assert reconstructed == new_config

    # Check if configs differ
    if diff.differs(old_config, new_config):
        print('Configs are different')

    # Human-readable summary
    summary = diff.summarize(patch)
    # Returns: '2 changes: replaced /b, added /c'
"""

from __future__ import annotations

import json
from typing import Any

from . import canon

# We use jsonpatch library for RFC 6902 compliance
# Install with: pip install jsonpatch
try:
    import jsonpatch
    JSONPATCH_AVAILABLE = True
except ImportError:
    JSONPATCH_AVAILABLE = False


class DiffError(Exception):
    """Base class for diff operation failures.

    Attributes:
        patch: The patch that failed (if available)
        base: The base config (if available)
        path: The JSON Pointer path that failed (if available)
    """

    def __init__(self, message: str, *, patch=None, base=None, path=None):
        super().__init__(message)
        self.patch = patch
        self.base = base
        self.path = path


class PatchConflictError(DiffError):
    """Patch operation conflicts with current state.

    Examples: adding key that exists, removing key that doesn't,
    replacing value at non-existent path.
    """
    pass


class InvalidPatchError(DiffError):
    """Patch format is malformed or invalid.

    Examples: missing 'op' field, unknown operation type,
    invalid JSON Pointer syntax.
    """
    pass


class PathNotFoundError(DiffError):
    """JSON Pointer path doesn't exist in target.

    The path in the patch operation doesn't match the structure
    of the base config.
    """
    pass


def _ensure_jsonpatch():
    """Ensure jsonpatch is available."""
    if not JSONPATCH_AVAILABLE:
        raise ImportError(
            "jsonpatch library required for diff operations. "
            "Install with: pip install jsonpatch"
        )


def _canonicalize(obj: dict) -> dict:
    """Convert object to canonical form for consistent diffing.

    Uses canon.serialize to ensure deterministic key ordering,
    then parses back to get a normalized dict.

    Args:
        obj: The object to canonicalize

    Returns:
        Canonicalized dict with sorted keys at all levels
    """
    canonical_bytes = canon.serialize(obj)
    return json.loads(canonical_bytes)


def compute(old: dict, new: dict) -> list[dict]:
    """Compute a JSON Patch diff between two configs.

    Args:
        old: The original config
        new: The new config

    Returns:
        List of RFC 6902 patch operations. Each operation is a dict with:
        - 'op': The operation type ('add', 'remove', 'replace', 'move', 'copy')
        - 'path': JSON Pointer to the target location
        - 'value': The new value (for 'add', 'replace')

    Example:
        >>> compute({'a': 1}, {'a': 2})
        [{'op': 'replace', 'path': '/a', 'value': 2}]

        >>> compute({'a': 1}, {'a': 1, 'b': 2})
        [{'op': 'add', 'path': '/b', 'value': 2}]
    """
    _ensure_jsonpatch()

    # Canonicalize for consistent diffs regardless of key order
    old_canon = _canonicalize(old)
    new_canon = _canonicalize(new)

    # Generate patch
    patch = jsonpatch.make_patch(old_canon, new_canon)

    # Return as list of dicts
    return patch.patch


def apply(base: dict, patch: list[dict]) -> dict:
    """Apply a JSON Patch to a base config.

    Args:
        base: The base config to patch
        patch: List of RFC 6902 patch operations

    Returns:
        New config with patch applied (base is not modified)

    Raises:
        DiffError: If patch cannot be applied to base (wrong base,
                   malformed patch, invalid paths, etc.)

    Example:
        >>> apply({'a': 1}, [{'op': 'replace', 'path': '/a', 'value': 2}])
        {'a': 2}
    """
    _ensure_jsonpatch()

    try:
        # Create patch object
        json_patch = jsonpatch.JsonPatch(patch)

        # Apply patch (returns new object, doesn't modify base)
        return json_patch.apply(base)

    except jsonpatch.JsonPatchConflict as e:
        # Extract path from error message if possible
        path = _extract_path_from_error(str(e))
        raise PatchConflictError(
            f"Patch conflict: {e}",
            patch=patch,
            base=base,
            path=path
        ) from e
    except jsonpatch.InvalidJsonPatch as e:
        raise InvalidPatchError(
            f"Invalid patch format: {e}",
            patch=patch
        ) from e
    except jsonpatch.JsonPatchException as e:
        raise DiffError(
            f"Patch error: {e}",
            patch=patch,
            base=base
        ) from e
    except KeyError as e:
        raise PathNotFoundError(
            f"Path not found: {e}",
            patch=patch,
            base=base,
            path=str(e)
        ) from e
    except Exception as e:
        raise DiffError(
            f"Failed to apply patch: {e}",
            patch=patch,
            base=base
        ) from e


def _extract_path_from_error(error_msg: str) -> str | None:
    """Try to extract JSON Pointer path from error message."""
    # Common patterns: "path '/foo/bar'", "pointer /foo/bar"
    import re
    match = re.search(r"(/[^\s',]+)", error_msg)
    return match.group(1) if match else None


def differs(old: dict, new: dict) -> bool:
    """Check if two configs differ.

    A quick check that doesn't require computing the full patch.

    Args:
        old: First config
        new: Second config

    Returns:
        True if configs differ, False if identical

    Example:
        >>> differs({'a': 1}, {'a': 2})
        True
        >>> differs({'a': 1}, {'a': 1})
        False
    """
    # Compare canonical forms for deterministic comparison
    old_canon = canon.serialize(old)
    new_canon = canon.serialize(new)
    return old_canon != new_canon


def summarize(patch: list[dict]) -> str:
    """Generate a human-readable summary of patch operations.

    Args:
        patch: List of RFC 6902 patch operations

    Returns:
        Human-readable string describing the changes

    Examples:
        >>> summarize([])
        'no changes'

        >>> summarize([{'op': 'replace', 'path': '/b', 'value': 3}])
        '1 change: replaced /b'

        >>> summarize([
        ...     {'op': 'replace', 'path': '/b', 'value': 3},
        ...     {'op': 'add', 'path': '/c', 'value': 4}
        ... ])
        '2 changes: replaced /b, added /c'
    """
    if not patch:
        return 'no changes'

    # Generate operation descriptions
    descriptions = []
    for op in patch:
        op_type = op.get('op', 'unknown')
        path = op.get('path', '?')

        # Convert op type to past tense
        verb_map = {
            'add': 'added',
            'remove': 'removed',
            'replace': 'replaced',
            'move': 'moved',
            'copy': 'copied',
            'test': 'tested',
        }
        verb = verb_map.get(op_type, op_type)
        descriptions.append(f"{verb} {path}")

    # Format output
    count = len(patch)
    change_word = 'change' if count == 1 else 'changes'
    ops_str = ', '.join(descriptions)

    return f"{count} {change_word}: {ops_str}"
