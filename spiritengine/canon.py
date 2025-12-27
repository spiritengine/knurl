"""
Canonical JSON serialization for content-addressable hashing.

This module produces deterministic JSON bytes where the same input always
produces the exact same output. Suitable for hashing configurations and
other data structures where byte-level reproducibility matters.

Based on RFC 8785 (JSON Canonicalization Scheme) principles:
- Dict keys sorted lexicographically (ASCII/UTF-16 code unit order)
- No whitespace between tokens
- -0.0 normalized to 0.0
- NaN/Infinity raise errors
- UTF-8 encoded output
"""

from __future__ import annotations

import json
import math
from typing import Any


class CanonError(Exception):
    """Raised when a value cannot be canonically serialized.

    Common causes:
    - NaN or Infinity floats
    - Circular references
    - Non-JSON-serializable types (bytes, sets, custom objects)
    - Excessive nesting depth
    """
    pass


# Maximum nesting depth to prevent stack overflow
MAX_DEPTH = 500


def _validate(obj: Any, seen: set[int], depth: int = 0) -> None:
    """Recursively validate that obj contains no invalid values.

    Raises CanonError for:
    - NaN floats
    - Infinity floats (positive or negative)
    - Circular references
    - Non-string dict keys
    - Excessive nesting depth

    Args:
        obj: The object to validate
        seen: Set of object ids already visited (for circular reference detection)
        depth: Current nesting depth
    """
    if depth > MAX_DEPTH:
        raise CanonError(f"Maximum nesting depth ({MAX_DEPTH}) exceeded")

    # Check for circular references in containers
    if isinstance(obj, (dict, list)):
        obj_id = id(obj)
        if obj_id in seen:
            raise CanonError("Circular reference detected")
        seen = seen | {obj_id}  # Create new set to avoid mutation across branches

        if isinstance(obj, dict):
            for key, value in obj.items():
                if not isinstance(key, str):
                    raise CanonError(
                        f"Dict keys must be strings for canonical JSON, got {type(key).__name__}: {key!r}"
                    )
                _validate(value, seen, depth + 1)
        else:  # list
            for item in obj:
                _validate(item, seen, depth + 1)

    elif isinstance(obj, float):
        if math.isnan(obj):
            raise CanonError("NaN values cannot be serialized to canonical JSON")
        if math.isinf(obj):
            raise CanonError("Infinity values cannot be serialized to canonical JSON")


def _normalize(obj: Any) -> Any:
    """Recursively normalize values for canonical serialization.

    Transformations:
    - -0.0 becomes 0.0 (RFC 8785 requirement)
    - Dict keys remain strings (JSON requirement)
    - All other values pass through unchanged

    Args:
        obj: The object to normalize

    Returns:
        Normalized object suitable for json.dumps
    """
    if isinstance(obj, dict):
        return {key: _normalize(value) for key, value in obj.items()}

    elif isinstance(obj, list):
        return [_normalize(item) for item in obj]

    elif isinstance(obj, float):
        # Handle -0.0 -> 0.0 (copysign detects negative zero)
        if obj == 0.0 and math.copysign(1.0, obj) < 0:
            return 0.0
        return obj

    # bool must be checked before int (bool is subclass of int in Python)
    elif isinstance(obj, bool):
        return obj

    elif isinstance(obj, (int, str, type(None))):
        return obj

    # Let json.dumps handle type errors for other types
    return obj


def serialize(obj: Any) -> bytes:
    """Serialize an object to canonical JSON bytes.

    Produces deterministic output suitable for content-addressable hashing.
    The same input will always produce the exact same byte sequence.

    Args:
        obj: A JSON-serializable object (dict, list, str, int, float, bool, None)

    Returns:
        UTF-8 encoded canonical JSON bytes

    Raises:
        CanonError: If the object contains NaN, Infinity, or circular references
        TypeError: If the object contains non-JSON-serializable types

    Example:
        >>> serialize({"b": 1, "a": 2})
        b'{"a":2,"b":1}'

        >>> serialize([1, 2, 3])
        b'[1,2,3]'

        >>> serialize(float('nan'))
        CanonError: NaN values cannot be serialized to canonical JSON
    """
    # Validate first (check for NaN, Infinity, circular refs)
    _validate(obj, set())

    # Normalize values (convert -0.0 to 0.0)
    normalized = _normalize(obj)

    # Serialize with canonical settings
    try:
        json_str = json.dumps(
            normalized,
            sort_keys=True,        # Lexicographic key ordering
            separators=(',', ':'), # No whitespace
            ensure_ascii=False,    # Allow UTF-8 characters directly
            allow_nan=False,       # Belt-and-suspenders: reject NaN/Inf at json level too
        )
    except ValueError as e:
        # json.dumps raises ValueError for NaN/Infinity when allow_nan=False
        raise CanonError(str(e)) from e

    return json_str.encode('utf-8')
