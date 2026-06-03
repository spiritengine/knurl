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
- Nesting deeper than MAX_DEPTH raises CanonError
- Integers with more than MAX_INT_DIGITS decimal digits raise CanonError
- Output is UTF-8 bytes (no BOM)

Integer handling (a deliberate divergence from a literal RFC 8785, which other
implementations MUST match): integers are serialized as their EXACT base-10
digits, NOT as IEEE-754 doubles per RFC 8785 §3.2.2.3 — so 9007199254740993 stays
itself rather than collapsing to 9007199254740992. The int-vs-float distinction is
by JSON SYNTAX, not value: a number token containing '.' or 'e'/'E' is a float and
is rejected by default (so {"n":1e2} is rejected while {"n":100} is accepted, even
though both equal 100). A reference RFC 8785 library bolted to NFC would diverge
here; the SKEIN spec (finding-20260511-pqxy) pins exact-integer rendering.

Duplicate-key note: json.loads() silently coalesces duplicate keys before this
function sees them. Callers that need to reject duplicate-keyed JSON strings
should parse with json.loads(s, object_pairs_hook=detect_duplicates) before
calling serialize().

Cross-version/cross-language parity rests on two environment assumptions that an
operator MUST keep aligned across all nodes that compare hashes:
- Unicode database version. NFC normalization is computed by the interpreter's
  bundled unicodedata. The Unicode stability policy guarantees the normalization
  of an *assigned* character never changes, but a code point that is unassigned
  in one node's UCD and assigned (with composition/combining data) in another's
  can normalize differently — so a string containing such a code point may hash
  differently across Python versions (e.g. 3.8 ships UCD 12.1, 3.12 ships 15.0).
  For ASCII identifiers and timestamps this is moot; for arbitrary user Unicode
  the spec must pin a UCD version (or reject code points unassigned in it).
- int<->str digit limit. CPython 3.11+ caps int<->str conversion (default 4300
  digits, == MAX_INT_DIGITS). serialize() refuses to run if the process has
  LOWERED that cap below MAX_INT_DIGITS, because json.dumps would then reject
  some integers that other nodes accept (see _require_int_str_limit).
"""

from __future__ import annotations

import json
import math
import sys
import unicodedata
from typing import Any


class CanonError(Exception):
    """Raised when a value cannot be canonically serialized.

    Common causes:
    - NaN or Infinity floats
    - Floats when accept_floats=False (the default)
    - Circular references
    - Excessive nesting depth (> MAX_DEPTH)
    - Integer magnitude exceeding MAX_INT_DIGITS decimal digits
    - Non-string dict keys
    - Duplicate keys after NFC normalization
    - Strings containing lone Unicode surrogates

    Note: a genuinely non-JSON type (bytes, set, Decimal, complex, a custom
    object) raises TypeError from json.dumps, NOT CanonError — that is a caller
    type error, not a canonicalization-domain rejection, and serialize()'s own
    docstring documents it as TypeError. Callers that must catch both should
    catch (CanonError, TypeError). (Such types never arise from json.loads, so
    they are unreachable from the JSON input domain anyway.)
    """
    pass


# Maximum nesting depth to prevent stack overflow. Kept well under Python's
# default recursion limit (1000) because serialize() makes three sequential
# recursive passes (_validate, _normalize, json.dumps) that together spend
# roughly two interpreter frames per nesting level: at the old value of 500 a
# structure *at* the limit overflowed the native stack on CPython 3.10/3.11 (and
# under any non-trivial ambient call stack) before the depth check could raise.
# 200 leaves ample headroom on every supported interpreter, so a structure at or
# below MAX_DEPTH always serializes and a deeper one raises CanonError — never a
# raw RecursionError. (Practical JSON nests far shallower than this.)
MAX_DEPTH = 200

# Maximum magnitude of an integer, as a count of base-10 digits in its absolute
# value. An integer with more than MAX_INT_DIGITS digits raises CanonError.
# 4300 matches CPython 3.11+'s default int<->str conversion limit: on 3.11+ a
# larger integer already fails mid-serialize, while 3.8-3.10 have no cap, so
# without this guard the same integer would hash on one node and be rejected on
# another — a version split in the content-address scheme. Enforcing it here (and
# at the same boundary as the interpreter's own parse-side limit) makes the
# accept/reject outcome uniform across versions. It is also vastly beyond any real
# SKEIN integer (microsecond timestamps are ~16 digits) and bounds the superlinear
# cost of int<->str on adversarially huge values.
MAX_INT_DIGITS = 4300
# Precomputed once: an integer has more than MAX_INT_DIGITS digits iff its
# absolute value is >= 10**MAX_INT_DIGITS. Comparing against this avoids calling
# str() on a giant int — the very superlinear operation the limit exists to bound.
# (This is integer arithmetic, not int<->str, so it is unaffected by the cap below.)
_MAX_INT_MAGNITUDE = 10 ** MAX_INT_DIGITS

# The Unicode database version backing this interpreter's NFC normalization
# (3.8 ships 12.1.0 ... 3.12 ships 15.0.0). Exposed so a deployment can detect a
# UCD mismatch across nodes. By Unicode's Normalization Stability Policy the NFC
# of an ASSIGNED character is immutable across versions, so the only cross-version
# divergence vector is a code point that is unassigned in one node's UCD and
# assigned (with composition/combining data) in another's. _nfc rejects code
# points unassigned in the running UCD, so any string every node accepts
# normalizes identically; comparing UNICODE_VERSION lets a fleet notice when a
# newer interpreter has widened the accepted set (a coordinated-upgrade concern,
# never a silent second hash). Pinning a fixed UCD for true cross-language parity
# is deferred to when a non-Python implementation exists.
UNICODE_VERSION = unicodedata.unidata_version


def _require_int_str_limit() -> None:
    """Refuse to serialize if the interpreter's int<->str cap is below MAX_INT_DIGITS.

    _validate bounds integers to MAX_INT_DIGITS, so json.dumps only ever renders
    integers within the limit. But CPython 3.11+ lets a process LOWER its int<->str
    digit cap (sys.set_int_max_str_digits) below MAX_INT_DIGITS; json.dumps would
    then raise on integers in (cap, MAX_INT_DIGITS] that nodes at the default cap
    serialize fine — a silent cross-environment hash split. Detect that and fail
    loudly instead. A cap of 0 means "unlimited" and is fine; on CPython < 3.11
    there is no cap and the getter is absent.
    """
    get_limit = getattr(sys, "get_int_max_str_digits", None)
    if get_limit is None:
        return
    limit = get_limit()
    if limit and limit < MAX_INT_DIGITS:
        raise CanonError(
            f"Interpreter int<->str digit limit ({limit}) is below the canonical "
            f"limit ({MAX_INT_DIGITS}); raise it with sys.set_int_max_str_digits "
            f"(or set 0 to disable) so canonical output is consistent across nodes."
        )


def _nfc(s: str) -> str:
    """NFC-normalize s, rejecting code points unassigned in the running UCD.

    A code point whose category is 'Cn' (reserved-unassigned or a noncharacter)
    in this interpreter's Unicode database may be assigned with composition or
    combining data in a newer database, where it would normalize differently.
    Rejecting it makes such a cross-version divergence fail loudly on the
    older-UCD node rather than silently produce a second canonical form (and
    hash); any string every node accepts then normalizes identically. Lone
    surrogates are category 'Cs', not 'Cn', and are caught by the UTF-8 encode
    check below. See UNICODE_VERSION.
    """
    for ch in s:
        if unicodedata.category(ch) == 'Cn':
            raise CanonError(
                f"Code point U+{ord(ch):04X} is unassigned (category Cn) in this "
                f"interpreter's Unicode database (version {UNICODE_VERSION}); it has "
                f"no stable canonical form across Unicode versions and is rejected."
            )
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
    - Integers exceeding MAX_INT_DIGITS decimal digits
    - Circular references
    - Non-string dict keys
    - Excessive nesting depth
    """
    if depth > MAX_DEPTH:
        raise CanonError(f"Maximum nesting depth ({MAX_DEPTH}) exceeded")

    # Tuples are included alongside dict/list because json.dumps serializes them
    # as arrays: without this a tuple would bypass validation entirely, so a
    # deeply nested tuple would slip past MAX_DEPTH and leak a raw RecursionError,
    # and a float or non-string key inside a tuple would escape rejection.
    if isinstance(obj, (dict, list, tuple)):
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
        else:  # list or tuple
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

    # bool is an int subclass but serializes as true/false, so exclude it.
    elif isinstance(obj, int) and not isinstance(obj, bool):
        # Bound integer magnitude uniformly across interpreters (see MAX_INT_DIGITS).
        # abs() + a precomputed power-of-ten comparison avoids stringifying the int.
        if abs(obj) >= _MAX_INT_MAGNITUDE:
            raise CanonError(
                f"Integer magnitude exceeds the canonical limit of "
                f"{MAX_INT_DIGITS} decimal digits"
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

    elif isinstance(obj, (list, tuple)):
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
            accept_floats=False), an integer exceeding MAX_INT_DIGITS decimal
            digits, circular references, non-string dict keys, duplicate keys
            after NFC normalization, strings with lone surrogates, or nesting
            depth exceeding MAX_DEPTH.
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
    _require_int_str_limit()
    # _validate enforces MAX_DEPTH and raises CanonError before the native stack
    # can give out, so the RecursionError guard below should never fire for input
    # within the limit. It is a belt-and-suspenders for an unusually deep ambient
    # call stack: a too-deep structure must always surface as a clean CanonError,
    # never a raw RecursionError. (We deliberately do NOT raise the recursion
    # limit to "make room" — that only converts a catchable error into a possible
    # interpreter crash, and mutating that global is not thread-safe.)
    #
    # _validate/_normalize raise CanonError directly (floats, NaN, duplicate keys,
    # lone surrogates), which propagates unwrapped. The json.dumps encode() stays
    # covered defensively: ensure_ascii=False would keep any lone surrogate in the
    # string, and encoding it to UTF-8 raises UnicodeEncodeError (a ValueError) —
    # wrapped as CanonError rather than letting the raw error escape.
    #
    # The validate-then-normalize design assumes inputs are plain builtin
    # containers, as produced by json.loads. A hostile dict/list SUBCLASS whose
    # items()/__iter__ yields clean data on the validate pass and dirty data on
    # the normalize pass could smuggle a float or non-string key into the output;
    # that is out of scope — SKEIN canonicalizes json.loads output, never
    # arbitrary subclass instances.
    try:
        _validate(obj, set(), accept_floats=accept_floats)
        normalized = _normalize(obj)
        json_str = json.dumps(
            normalized,
            sort_keys=False,       # Key ordering is handled by _normalize (UTF-16)
            separators=(',', ':'), # No whitespace
            ensure_ascii=False,    # Allow UTF-8 characters directly
            allow_nan=False,       # Belt-and-suspenders: reject NaN/Inf at json level
        )
        return json_str.encode('utf-8')
    except RecursionError as e:
        # Reaching the interpreter's native recursion limit. Usually this is
        # genuinely over-deep input, but a structure within MAX_DEPTH can also
        # trip it under a very deep caller stack — so the message does not assert
        # MAX_DEPTH was exceeded, only that the limit was hit. Either way the
        # contract holds: a clean CanonError, never a raw RecursionError.
        raise CanonError(
            "Structure too deeply nested to serialize: reached the interpreter "
            f"recursion limit (canonical nesting limit is MAX_DEPTH={MAX_DEPTH})"
        ) from e
    except ValueError as e:
        # ValueError covers NaN/Infinity (allow_nan=False) and UnicodeEncodeError
        # (a ValueError subclass) from encoding a lone surrogate.
        raise CanonError(str(e)) from e
