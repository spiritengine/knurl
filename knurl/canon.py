"""
Canonical JSON serialization for content-addressable hashing.

Implements the SKEIN canonical serialization spec (finding-20260511-pqxy in
mesh-v1 site), which is RFC 8785 with mandatory NFC Unicode normalization.

Rules:
- All string values (object keys and string leaves at any depth) are
  NFC-normalized (unicodedata.normalize('NFC', s)) before serialization
- Object keys sorted by UTF-16 code unit order (RFC 8785 §3.2.3)
- No whitespace between tokens; separators are ',' and ':'
- Floats rejected by default; pass accept_floats=True for non-canonical use
- -0.0 normalized to 0.0 (only relevant when accept_floats=True)
- NaN and Infinity always raise CanonError
- Non-string dict keys raise CanonError
- Duplicate keys after NFC normalization raise CanonError
- Nesting deeper than 500 raises CanonError
- Output is UTF-8 bytes (no BOM)

Duplicate-key note: json.loads() silently coalesces duplicate keys before this
function sees them. Callers that need to reject duplicate-keyed JSON strings
should parse with json.loads(s, object_pairs_hook=detect_duplicates) before
calling serialize().
"""

from __future__ import annotations

import json
import math
import unicodedata
from typing import Any


class CanonError(Exception):
    """Raised when a value cannot be canonically serialized.

    Common causes:
    - NaN or Infinity floats
    - Floats when accept_floats=False (the default)
    - Circular references
    - Non-JSON-serializable types (bytes, sets, custom objects)
    - Excessive nesting depth (> 500)
    - Non-string dict keys
    - Duplicate keys after NFC normalization
    - Strings containing lone Unicode surrogates
    """
    pass


MAX_DEPTH = 500


def _nfc(s: str) -> str:
    """Apply NFC normalization and verify UTF-8 encodability."""
    try:
        normalized = unicodedata.normalize('NFC', s)
        normalized.encode('utf-8')
        return normalized
    except (ValueError, UnicodeEncodeError) as e:
        raise CanonError(
            f"String cannot be Unicode NFC-normalized or UTF-8 encoded: {s!r}: {e}"
        ) from e


def _utf16_sort_key(s: str) -> tuple[int, ...]:
    """Return sort key using UTF-16 code unit order (RFC 8785 §3.2.3).

    Python's default string comparison uses Unicode code point order, which
    diverges from UTF-16 code unit order for supplementary characters
    (> U+FFFF). Specifically, a supplementary character's high surrogate
    (0xD800-0xDBFF) is numerically less than U+E000-U+FFFF, so supplementary
    characters sort before high-BMP characters in UTF-16 order but after them
    in code point order.
    """
    try:
        encoded = s.encode('utf-16-be')
        return tuple(
            int.from_bytes(encoded[i:i+2], 'big')
            for i in range(0, len(encoded), 2)
        )
    except UnicodeEncodeError as e:
        raise CanonError(
            f"Key cannot be encoded for UTF-16 sorting (lone surrogate?): {s!r}: {e}"
        ) from e


def _validate(obj: Any, seen: set[int], depth: int = 0, accept_floats: bool = False) -> None:
    """Recursively validate that obj contains no invalid values.

    Raises CanonError for:
    - NaN or Infinity floats
    - Floats when accept_floats is False
    - Circular references
    - Non-string dict keys
    - Excessive nesting depth
    """
    if depth > MAX_DEPTH:
        raise CanonError(f"Maximum nesting depth ({MAX_DEPTH}) exceeded")

    if isinstance(obj, (dict, list)):
        obj_id = id(obj)
        if obj_id in seen:
            raise CanonError("Circular reference detected")
        seen = seen | {obj_id}

        if isinstance(obj, dict):
            for key, value in obj.items():
                if not isinstance(key, str):
                    raise CanonError(
                        f"Dict keys must be strings for canonical JSON, "
                        f"got {type(key).__name__}: {key!r}"
                    )
                _validate(value, seen, depth + 1, accept_floats)
        else:
            for item in obj:
                _validate(item, seen, depth + 1, accept_floats)

    elif isinstance(obj, float):
        if math.isnan(obj):
            raise CanonError("NaN values cannot be serialized to canonical JSON")
        if math.isinf(obj):
            raise CanonError("Infinity values cannot be serialized to canonical JSON")
        if not accept_floats:
            raise CanonError(
                f"Float values are not allowed in canonical JSON (got {obj!r}). "
                "Pass accept_floats=True for non-canonical use."
            )


def _normalize(obj: Any) -> Any:
    """Recursively normalize values for canonical serialization.

    Transformations:
    - String keys: NFC-normalized, deduplicated, sorted by UTF-16 code unit order
    - String values: NFC-normalized
    - -0.0 becomes 0.0 (RFC 8785 requirement; only reached when accept_floats=True)
    - All other values pass through unchanged
    """
    if isinstance(obj, dict):
        seen_keys: set[str] = set()
        normalized_pairs: list[tuple[str, Any]] = []
        for key, value in obj.items():
            nfc_key = _nfc(key)
            if nfc_key in seen_keys:
                raise CanonError(
                    f"Duplicate key after NFC normalization: {nfc_key!r}"
                )
            seen_keys.add(nfc_key)
            normalized_pairs.append((nfc_key, _normalize(value)))
        return dict(
            sorted(normalized_pairs, key=lambda item: _utf16_sort_key(item[0]))
        )

    elif isinstance(obj, list):
        return [_normalize(item) for item in obj]

    elif isinstance(obj, str):
        return _nfc(obj)

    elif isinstance(obj, bool):
        return obj

    elif isinstance(obj, float):
        if obj == 0.0 and math.copysign(1.0, obj) < 0:
            return 0.0
        return obj

    elif isinstance(obj, (int, type(None))):
        return obj

    return obj


def serialize(obj: Any, *, accept_floats: bool = False) -> bytes:
    """Serialize an object to canonical JSON bytes.

    Produces deterministic output suitable for content-addressable hashing.
    The same input always produces the exact same byte sequence.

    All string values (keys and leaves) are NFC-normalized before serialization.
    Object keys are sorted by UTF-16 code unit order per RFC 8785 §3.2.3.

    Args:
        obj: A JSON-serializable object (dict, list, str, int, bool, None).
            Floats are rejected by default.
        accept_floats: If True, accept float values. -0.0 is normalized to 0.0
            per RFC 8785. NaN and Infinity are always rejected regardless of
            this flag. SKEIN canonical hashes must never set accept_floats=True.

    Returns:
        UTF-8 encoded canonical JSON bytes (no BOM).

    Raises:
        CanonError: If the object contains NaN, Infinity, floats (when
            accept_floats=False), circular references, non-string dict keys,
            duplicate keys after NFC normalization, strings with lone surrogates,
            or nesting depth exceeding 500.
        TypeError: If the object contains non-JSON-serializable types (bytes,
            sets, custom objects).

    Example:
        >>> serialize({"b": 1, "a": 2})
        b'{"a":2,"b":1}'

        >>> serialize([1, 2, 3])
        b'[1,2,3]'

        >>> serialize(float('nan'))
        CanonError: NaN values cannot be serialized to canonical JSON

        >>> serialize(1.5)
        CanonError: Float values are not allowed in canonical JSON...

        >>> serialize(1.5, accept_floats=True)
        b'1.5'
    """
    _validate(obj, set(), accept_floats=accept_floats)
    normalized = _normalize(obj)

    try:
        json_str = json.dumps(
            normalized,
            sort_keys=False,       # Key ordering is handled by _normalize()
            separators=(',', ':'), # No whitespace
            ensure_ascii=False,    # Allow UTF-8 characters directly
            allow_nan=False,       # Belt-and-suspenders: reject NaN/Inf at json level
        )
    except ValueError as e:
        raise CanonError(str(e)) from e

    return json_str.encode('utf-8')
