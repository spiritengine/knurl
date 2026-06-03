"""
Comprehensive test suite for ledger.canon - Canonical JSON Serialization.

This module ensures deterministic serialization where the same input ALWAYS
produces the exact same output, suitable for content-addressable hashing.

Based on RFC 8785 (JSON Canonicalization Scheme) research:
- Keys sorted by UTF-16 code unit order
- -0.0 becomes 0
- NaN/Infinity must error
- No whitespace between tokens
- UTF-8 output

Test Categories:
1. Determinism - Same input always produces same output
2. Key Ordering - Dict keys sorted correctly, recursively
3. Float Handling - Edge cases: -0, precision, scientific notation
4. String Handling - Unicode, escaping, surrogates
5. Type Handling - int/float/bool/None distinctions
6. Structure - Deep nesting, wide dicts, circular refs
7. Errors - Invalid inputs produce clear errors
8. Round Trip - json.loads(serialize(x)) gives equivalent structure
"""

import json
import math
import sys
import unicodedata
from typing import Any

import pytest

# Will import from implementation
# from knurl.canon import serialize, CanonError


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================

@pytest.fixture
def serialize():
    """Import serialize function - allows tests to run before implementation exists."""
    from knurl.canon import serialize
    return serialize


@pytest.fixture
def CanonError():
    """Import CanonError exception class."""
    from knurl.canon import CanonError
    return CanonError


def assert_canonical(serialize, obj: Any, expected: bytes) -> None:
    """Assert that serialization produces expected canonical bytes."""
    result = serialize(obj)
    assert isinstance(result, bytes), f"Expected bytes, got {type(result)}"
    assert result == expected, f"Expected {expected!r}, got {result!r}"


# =============================================================================
# TestDeterminism - Same input always produces same output
# =============================================================================

class TestDeterminism:
    """Core determinism property: same input → same output, always."""

    def test_repeated_calls_same_result(self, serialize):
        """Multiple serialize calls on same object produce identical output."""
        obj = {"name": "test", "values": [1, 2, 3], "nested": {"a": 1}}
        results = [serialize(obj) for _ in range(100)]
        assert len(set(results)) == 1, "All results should be identical"

    def test_different_dict_insertion_order(self, serialize):
        """Dicts with same content but different insertion order → same output."""
        dict1 = {"z": 1, "a": 2, "m": 3}
        dict2 = {"a": 2, "m": 3, "z": 1}
        dict3 = {"m": 3, "z": 1, "a": 2}

        result1 = serialize(dict1)
        result2 = serialize(dict2)
        result3 = serialize(dict3)

        assert result1 == result2 == result3

    def test_equivalent_structures(self, serialize):
        """Logically equivalent structures serialize identically."""
        # List created different ways
        list1 = [1, 2, 3]
        list2 = list(range(1, 4))
        list3 = [x for x in [1, 2, 3]]

        assert serialize(list1) == serialize(list2) == serialize(list3)

    def test_nested_dict_ordering_determinism(self, serialize):
        """Deeply nested dicts with varying insertion order → same output."""
        nested1 = {
            "z": {"b": 1, "a": 2},
            "a": {"z": 3, "m": 4}
        }
        nested2 = {
            "a": {"m": 4, "z": 3},
            "z": {"a": 2, "b": 1}
        }

        assert serialize(nested1) == serialize(nested2)


# =============================================================================
# TestKeyOrdering - Dict keys sorted correctly
# =============================================================================

class TestKeyOrdering:
    """Keys must be sorted per RFC 8785 (UTF-16 code unit order)."""

    def test_simple_alphabetic_sort(self, serialize):
        """Basic ASCII keys sort alphabetically."""
        obj = {"zebra": 1, "apple": 2, "mango": 3}
        result = serialize(obj)
        # Keys should appear in order: apple, mango, zebra
        assert result == b'{"apple":2,"mango":3,"zebra":1}'

    def test_empty_string_key_first(self, serialize):
        """Empty string key comes before all others."""
        obj = {"a": 1, "": 0, "b": 2}
        result = serialize(obj)
        assert result == b'{"":0,"a":1,"b":2}'

    def test_length_ordering(self, serialize):
        """Shorter keys before longer when prefix matches."""
        obj = {"ab": 2, "a": 1, "abc": 3}
        result = serialize(obj)
        assert result == b'{"a":1,"ab":2,"abc":3}'

    def test_recursive_key_sorting(self, serialize):
        """Nested dicts also have their keys sorted."""
        obj = {
            "outer": {"z": 1, "a": 2},
            "inner": {"m": 3, "b": 4}
        }
        result = serialize(obj)
        # Both outer keys and inner keys must be sorted
        assert b'"a":2' in result and result.index(b'"a":2') < result.index(b'"z":1')
        assert b'"b":4' in result and result.index(b'"b":4') < result.index(b'"m":3')

    def test_deeply_nested_sorting(self, serialize):
        """Keys sorted at all nesting levels."""
        obj = {
            "z": {
                "z": {"z": 1, "a": 2},
                "a": {"z": 3, "a": 4}
            },
            "a": 5
        }
        result = serialize(obj)
        # "a" should come before "z" at every level
        expected = b'{"a":5,"z":{"a":{"a":4,"z":3},"z":{"a":2,"z":1}}}'
        assert result == expected

    def test_sorting_in_list_of_dicts(self, serialize):
        """Dicts inside lists also have sorted keys."""
        obj = [{"z": 1, "a": 2}, {"m": 3, "b": 4}]
        result = serialize(obj)
        assert result == b'[{"a":2,"z":1},{"b":4,"m":3}]'

    def test_numeric_string_keys(self, serialize):
        """Numeric string keys sort lexicographically, not numerically."""
        obj = {"10": 1, "2": 2, "1": 3}
        result = serialize(obj)
        # Lexicographic: "1" < "10" < "2"
        assert result == b'{"1":3,"10":1,"2":2}'

    def test_unicode_key_sorting_utf16(self, serialize):
        """UTF-16 code unit sort: supplementary chars sort before high-BMP chars.

        Supplementary characters (> U+FFFF) encode as surrogate pairs in UTF-16.
        High surrogates (0xD800-0xDBFF) are numerically less than U+E000-U+FFFF,
        so a supplementary char sorts BEFORE a high-BMP char in UTF-16 code unit
        order, but AFTER it in Unicode code point order.
        """
        # U+E000 (private-use area, code point 57344)
        # U+10000 (Linear B Syllabary, code point 65536)
        # UTF-16: U+10000 -> [0xD800, 0xDC00]; U+E000 -> [0xE000]
        # 0xD800 < 0xE000, so U+10000 sorts BEFORE U+E000 in UTF-16 order
        obj = {"\uE000": 1, "\U00010000": 2}
        result = serialize(obj)
        keys = list(json.loads(result).keys())
        assert keys[0] == "\U00010000", (
            "Supplementary char \\U00010000 should sort before \\uE000 "
            "in UTF-16 code unit order"
        )

    def test_case_sensitive_sorting(self, serialize):
        """Upper and lowercase letters sort by code point."""
        obj = {"a": 1, "B": 2, "A": 3, "b": 4}
        result = serialize(obj)
        # ASCII order: A (65) < B (66) < a (97) < b (98)
        assert result == b'{"A":3,"B":2,"a":1,"b":4}'


# =============================================================================
# TestFloatHandling - Float edge cases
# =============================================================================

class TestFloatHandling:
    """Float serialization edge cases."""

    def test_negative_zero_becomes_zero(self, serialize):
        """RFC 8785: -0 must serialize as 0 when accept_floats=True."""
        result = serialize(-0.0, accept_floats=True)
        assert result == b'0' or result == b'0.0'
        assert b'-' not in result

    def test_positive_zero(self, serialize):
        """Positive zero serializes correctly when accept_floats=True."""
        result = serialize(0.0, accept_floats=True)
        assert result in (b'0', b'0.0')

    def test_nan_raises_error(self, serialize, CanonError):
        """NaN is not valid JSON and must raise an error."""
        with pytest.raises(CanonError) as exc_info:
            serialize(float('nan'))
        assert 'nan' in str(exc_info.value).lower() or 'NaN' in str(exc_info.value)

    def test_positive_infinity_raises_error(self, serialize, CanonError):
        """Positive infinity must raise an error."""
        with pytest.raises(CanonError) as exc_info:
            serialize(float('inf'))
        assert 'inf' in str(exc_info.value).lower()

    def test_negative_infinity_raises_error(self, serialize, CanonError):
        """Negative infinity must raise an error."""
        with pytest.raises(CanonError) as exc_info:
            serialize(float('-inf'))
        assert 'inf' in str(exc_info.value).lower()

    def test_nan_in_nested_structure(self, serialize, CanonError):
        """NaN buried in structure must still raise error."""
        with pytest.raises(CanonError):
            serialize({"deeply": {"nested": {"value": float('nan')}}})

    def test_infinity_in_list(self, serialize, CanonError):
        """Infinity in a list must raise error."""
        with pytest.raises(CanonError):
            serialize([1, 2, float('inf'), 4])

    def test_simple_floats(self, serialize):
        """Simple float values serialize correctly when accept_floats=True."""
        assert serialize(1.5, accept_floats=True) == b'1.5'
        assert serialize(0.5, accept_floats=True) == b'0.5'
        assert serialize(123.456, accept_floats=True) == b'123.456'

    def test_float_precision_reproducibility(self, serialize):
        """Float precision is consistent across calls (accept_floats=True)."""
        val = 0.1 + 0.2  # Known to be 0.30000000000000004
        result1 = serialize(val, accept_floats=True)
        result2 = serialize(val, accept_floats=True)
        assert result1 == result2

    def test_scientific_notation_consistency(self, serialize):
        """Large/small floats consistently use or avoid scientific notation (accept_floats=True)."""
        large = 1e20
        small = 1e-10

        result_large = serialize(large, accept_floats=True)
        result_small = serialize(small, accept_floats=True)

        assert serialize(large, accept_floats=True) == result_large
        assert serialize(small, accept_floats=True) == result_small

    def test_float_vs_integer_distinction(self, serialize):
        """Float and integer serialize differently when values differ (accept_floats=True for float)."""
        assert serialize(1) != serialize(1.5, accept_floats=True)

    def test_very_small_float(self, serialize):
        """Very small floats serialize without error when accept_floats=True."""
        tiny = 1e-300
        result = serialize(tiny, accept_floats=True)
        assert isinstance(result, bytes)
        parsed = json.loads(result)
        assert parsed == tiny or abs(parsed - tiny) / tiny < 1e-10

    def test_very_large_float(self, serialize):
        """Very large floats serialize without error when accept_floats=True."""
        huge = 1e300
        result = serialize(huge, accept_floats=True)
        assert isinstance(result, bytes)
        parsed = json.loads(result)
        assert parsed == huge or abs(parsed - huge) / huge < 1e-10


# =============================================================================
# TestStringHandling - Unicode and escaping
# =============================================================================

class TestStringHandling:
    """String serialization including Unicode and escaping."""

    def test_simple_ascii(self, serialize):
        """Simple ASCII strings serialize correctly."""
        assert serialize("hello") == b'"hello"'
        assert serialize("Hello World") == b'"Hello World"'

    def test_empty_string(self, serialize):
        """Empty string serializes correctly."""
        assert serialize("") == b'""'

    def test_escape_quotes(self, serialize):
        """Quotes in strings are escaped."""
        result = serialize('say "hello"')
        assert result == b'"say \\"hello\\""'

    def test_escape_backslash(self, serialize):
        """Backslashes are escaped."""
        result = serialize("path\\to\\file")
        assert result == b'"path\\\\to\\\\file"'

    def test_escape_newline(self, serialize):
        """Newlines are escaped as \\n."""
        result = serialize("line1\nline2")
        assert result == b'"line1\\nline2"'

    def test_escape_tab(self, serialize):
        """Tabs are escaped as \\t."""
        result = serialize("col1\tcol2")
        assert result == b'"col1\\tcol2"'

    def test_escape_carriage_return(self, serialize):
        """Carriage returns are escaped as \\r."""
        result = serialize("line1\rline2")
        assert result == b'"line1\\rline2"'

    def test_escape_form_feed(self, serialize):
        """Form feeds are escaped as \\f."""
        result = serialize("page1\fpage2")
        assert result == b'"page1\\fpage2"'

    def test_escape_backspace(self, serialize):
        """Backspaces are escaped as \\b."""
        result = serialize("back\bspace")
        assert result == b'"back\\bspace"'

    def test_control_characters_escaped(self, serialize):
        """Control characters U+0000-U+001F are escaped."""
        # NUL character
        result = serialize("\x00")
        assert b"\\u0000" in result or b"\\x00" in result

    def test_unicode_basic_multilingual_plane(self, serialize):
        """Unicode BMP characters serialize correctly."""
        # Japanese
        result = serialize("日本語")
        assert "日本語".encode('utf-8') in result or b'\\u' in result

    def test_unicode_emoji(self, serialize):
        """Emoji (outside BMP) serialize correctly."""
        result = serialize("😀")
        assert isinstance(result, bytes)
        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed == "😀"

    def test_unicode_combining_characters(self, serialize):
        """Combining characters are NFC-normalized before serialization."""
        # e + combining acute (NFD) normalizes to precomposed é (NFC, U+00E9)
        combining = "e\u0301"
        result = serialize(combining)
        parsed = json.loads(result)
        assert parsed == "\u00e9"

    def test_nfc_normalization_idempotent(self, serialize):
        """NFC and NFD inputs produce identical canonical output (both normalize to NFC)."""
        nfc = "\u00e9"   # precomposed é
        nfd = "e\u0301"  # e + combining acute accent

        result_nfc = serialize(nfc)
        result_nfd = serialize(nfd)

        assert result_nfc == result_nfd

    def test_lone_surrogate_raises_error(self, serialize, CanonError):
        """Lone surrogates must raise an error (RFC 8785)."""
        # \ud800 is a lone high surrogate
        try:
            lone_surrogate = "\ud800"
            with pytest.raises(CanonError):
                serialize(lone_surrogate)
        except UnicodeEncodeError:
            # Python may not even allow creating this string
            pytest.skip("Python rejected lone surrogate at string creation")

    def test_line_separator_handling(self, serialize):
        """U+2028 (line separator) is handled correctly."""
        result = serialize("\u2028")
        # Should be valid JSON
        assert isinstance(result, bytes)
        parsed = json.loads(result)
        assert parsed == "\u2028"

    def test_paragraph_separator_handling(self, serialize):
        """U+2029 (paragraph separator) is handled correctly."""
        result = serialize("\u2029")
        assert isinstance(result, bytes)
        parsed = json.loads(result)
        assert parsed == "\u2029"

    def test_very_long_string(self, serialize):
        """Very long strings serialize without error."""
        long_string = "a" * 100000
        result = serialize(long_string)
        assert isinstance(result, bytes)
        parsed = json.loads(result)
        assert parsed == long_string


# =============================================================================
# TestTypeHandling - Type distinctions
# =============================================================================

class TestTypeHandling:
    """Correct handling of different Python types."""

    def test_integer(self, serialize):
        """Integers serialize as JSON numbers without decimal."""
        assert serialize(42) == b'42'
        assert serialize(0) == b'0'
        assert serialize(-17) == b'-17'

    def test_large_integer(self, serialize):
        """Large integers beyond JS safe range still serialize."""
        large = 2**60
        result = serialize(large)
        assert isinstance(result, bytes)
        parsed = json.loads(result)
        assert parsed == large

    def test_boolean_true(self, serialize):
        """True serializes as 'true', not '1'."""
        assert serialize(True) == b'true'

    def test_boolean_false(self, serialize):
        """False serializes as 'false', not '0'."""
        assert serialize(False) == b'false'

    def test_none(self, serialize):
        """None serializes as 'null'."""
        assert serialize(None) == b'null'

    def test_int_vs_float_difference(self, serialize):
        """Integer and float may serialize differently (accept_floats=True for float)."""
        int_result = serialize(1)
        float_result = serialize(1.0, accept_floats=True)
        assert serialize(1) == int_result
        assert serialize(1.0, accept_floats=True) == float_result

    def test_bool_not_int(self, serialize):
        """Boolean is NOT treated as integer."""
        # True == 1 in Python, but JSON distinguishes them
        assert serialize(True) != serialize(1)
        assert serialize(False) != serialize(0)

    def test_empty_list(self, serialize):
        """Empty list serializes correctly."""
        assert serialize([]) == b'[]'

    def test_empty_dict(self, serialize):
        """Empty dict serializes correctly."""
        assert serialize({}) == b'{}'

    def test_list_of_primitives(self, serialize):
        """List of various primitives."""
        # Without floats (default behavior)
        obj = [1, "two", True, None]
        result = serialize(obj)
        assert result == b'[1,"two",true,null]'
        # With floats
        obj_with_float = [1, "two", True, None, 3.5]
        result_with_float = serialize(obj_with_float, accept_floats=True)
        assert result_with_float == b'[1,"two",true,null,3.5]'

    def test_mixed_nested_structure(self, serialize):
        """Complex nested structure with mixed types (no floats by default)."""
        obj = {
            "string": "hello",
            "number": 42,
            "bool": True,
            "null": None,
            "list": [1, 2, 3],
            "nested": {"a": 1}
        }
        result = serialize(obj)
        assert isinstance(result, bytes)
        parsed = json.loads(result)
        assert parsed["string"] == "hello"
        assert parsed["number"] == 42
        assert parsed["bool"] is True
        assert parsed["null"] is None

    def test_mixed_nested_structure_with_floats(self, serialize):
        """Mixed structure with floats when accept_floats=True."""
        obj = {"float": 3.14, "nested": {"x": 2.71}}
        result = serialize(obj, accept_floats=True)
        assert isinstance(result, bytes)
        parsed = json.loads(result)
        assert abs(parsed["float"] - 3.14) < 1e-10


# =============================================================================
# TestStructure - Structural edge cases
# =============================================================================

class TestStructure:
    """Tests for structural edge cases."""

    def test_deeply_nested_dict(self, serialize):
        """Deeply nested dicts (100 levels) serialize without error."""
        obj = {"level": 0}
        current = obj
        for i in range(1, 100):
            current["nested"] = {"level": i}
            current = current["nested"]

        result = serialize(obj)
        assert isinstance(result, bytes)

    def test_deeply_nested_list(self, serialize):
        """Deeply nested lists (100 levels) serialize without error."""
        obj = [0]
        current = obj
        for i in range(1, 100):
            new_list = [i]
            current.append(new_list)
            current = new_list

        result = serialize(obj)
        assert isinstance(result, bytes)

    def test_wide_dict(self, serialize):
        """Dict with many keys serializes correctly."""
        obj = {f"key_{i:04d}": i for i in range(1000)}
        result = serialize(obj)
        assert isinstance(result, bytes)
        # Keys should be sorted
        assert b'"key_0000"' in result
        assert result.index(b'"key_0000"') < result.index(b'"key_0001"')

    def test_wide_list(self, serialize):
        """List with many elements serializes correctly."""
        obj = list(range(1000))
        result = serialize(obj)
        assert result.startswith(b'[0,1,2,')

    def test_circular_reference_raises_error(self, serialize, CanonError):
        """Circular references must raise an error."""
        obj = {"a": 1}
        obj["self"] = obj  # Circular reference

        with pytest.raises((CanonError, ValueError, RecursionError)):
            serialize(obj)

    def test_list_circular_reference(self, serialize, CanonError):
        """Circular references in lists must raise an error."""
        obj = [1, 2, 3]
        obj.append(obj)  # Circular reference

        with pytest.raises((CanonError, ValueError, RecursionError)):
            serialize(obj)

    def test_shared_reference_allowed(self, serialize):
        """Shared references (non-circular) are allowed."""
        shared = {"shared": True}
        obj = {"a": shared, "b": shared}

        result = serialize(obj)
        assert isinstance(result, bytes)
        # Both references should serialize to the same thing
        assert result.count(b'"shared":true') == 2


# =============================================================================
# TestErrors - Error handling
# =============================================================================

class TestErrors:
    """Tests for proper error handling."""

    def test_bytes_raises_error(self, serialize, CanonError):
        """Bytes objects are not JSON serializable."""
        with pytest.raises((CanonError, TypeError)):
            serialize(b"hello")

    def test_set_raises_error(self, serialize, CanonError):
        """Sets are not JSON serializable."""
        with pytest.raises((CanonError, TypeError)):
            serialize({1, 2, 3})

    def test_datetime_raises_error(self, serialize, CanonError):
        """Datetime objects are not JSON serializable."""
        from datetime import datetime
        with pytest.raises((CanonError, TypeError)):
            serialize(datetime.now())

    def test_custom_object_raises_error(self, serialize, CanonError):
        """Custom objects are not JSON serializable."""
        class CustomClass:
            pass

        with pytest.raises((CanonError, TypeError)):
            serialize(CustomClass())

    def test_function_raises_error(self, serialize, CanonError):
        """Functions are not JSON serializable."""
        with pytest.raises((CanonError, TypeError)):
            serialize(lambda x: x)

    def test_nan_error_message_clear(self, serialize, CanonError):
        """NaN error message is informative."""
        with pytest.raises(CanonError) as exc_info:
            serialize(float('nan'))

        error_msg = str(exc_info.value).lower()
        assert 'nan' in error_msg or 'not a number' in error_msg

    def test_non_string_dict_key_rejected(self, serialize, CanonError):
        """Non-string dict keys must raise CanonError."""
        # Integer keys would silently coerce to strings, breaking canonicality
        # (different Python dicts would produce same output)
        with pytest.raises(CanonError) as exc_info:
            serialize({1: "one"})
        assert "must be strings" in str(exc_info.value)

    def test_none_dict_key_rejected(self, serialize, CanonError):
        """None as dict key must raise CanonError."""
        with pytest.raises(CanonError) as exc_info:
            serialize({None: "value"})
        assert "must be strings" in str(exc_info.value)

    def test_nested_non_string_key_rejected(self, serialize, CanonError):
        """Non-string keys in nested dicts must raise CanonError."""
        with pytest.raises(CanonError):
            serialize({"outer": {1: "nested int key"}})


# =============================================================================
# TestRoundTrip - Serialization/deserialization consistency
# =============================================================================

class TestRoundTrip:
    """Tests that serialized JSON can be parsed back correctly."""

    def test_simple_round_trip(self, serialize):
        """Simple values round-trip correctly."""
        for value in [42, "hello", True, False, None]:
            result = serialize(value)
            parsed = json.loads(result)
            assert parsed == value
        # Floats require accept_floats=True
        for value in [3.14]:
            result = serialize(value, accept_floats=True)
            parsed = json.loads(result)
            assert abs(parsed - value) < 1e-10

    def test_list_round_trip(self, serialize):
        """Lists round-trip correctly."""
        obj = [1, 2, 3, "four", None]
        result = serialize(obj)
        parsed = json.loads(result)
        assert parsed == obj

    def test_dict_round_trip(self, serialize):
        """Dicts round-trip correctly."""
        obj = {"a": 1, "b": 2, "c": [1, 2, 3]}
        result = serialize(obj)
        parsed = json.loads(result)
        assert parsed == obj

    def test_nested_round_trip(self, serialize):
        """Complex nested structures round-trip correctly."""
        obj = {
            "users": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25}
            ],
            "metadata": {
                "count": 2,
                "active": True
            }
        }
        result = serialize(obj)
        parsed = json.loads(result)
        assert parsed == obj

    def test_unicode_round_trip(self, serialize):
        """Unicode content round-trips correctly."""
        obj = {"greeting": "こんにちは", "emoji": "😀🎉"}
        result = serialize(obj)
        parsed = json.loads(result)
        assert parsed == obj

    def test_escaped_characters_round_trip(self, serialize):
        """Escaped characters round-trip correctly."""
        obj = {"text": "line1\nline2\ttab\\backslash\"quote"}
        result = serialize(obj)
        parsed = json.loads(result)
        assert parsed == obj


# =============================================================================
# TestNoWhitespace - Minimal encoding
# =============================================================================

class TestNoWhitespace:
    """Tests that output contains no unnecessary whitespace."""

    def test_no_spaces_after_colon(self, serialize):
        """No space after colon in objects."""
        result = serialize({"a": 1})
        assert b': ' not in result
        assert b':"' not in result or b'"a":1' in result

    def test_no_spaces_after_comma(self, serialize):
        """No space after comma in lists or objects."""
        result = serialize([1, 2, 3])
        assert b', ' not in result
        assert result == b'[1,2,3]'

    def test_no_leading_trailing_whitespace(self, serialize):
        """No leading or trailing whitespace."""
        result = serialize({"a": 1})
        assert not result.startswith(b' ')
        assert not result.startswith(b'\n')
        assert not result.endswith(b' ')
        assert not result.endswith(b'\n')


# =============================================================================
# Property-Based Tests with Hypothesis
# =============================================================================

try:
    from hypothesis import given, strategies as st, settings, assume
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False
    # Provide dummy decorators so class definition doesn't fail
    def given(*args, **kwargs):
        return lambda f: f
    def settings(*args, **kwargs):
        return lambda f: f
    def assume(x):
        pass
    # Dummy strategy that supports | operator
    class _DummyStrategy:
        def __or__(self, other):
            return self
        def __ror__(self, other):
            return self
    class st:
        @staticmethod
        def integers(): return _DummyStrategy()
        @staticmethod
        def floats(**kwargs): return _DummyStrategy()
        @staticmethod
        def text(*args, **kwargs): return _DummyStrategy()
        @staticmethod
        def characters(*args, **kwargs): return _DummyStrategy()
        @staticmethod
        def dictionaries(k, v): return _DummyStrategy()
        @staticmethod
        def lists(x): return _DummyStrategy()
        @staticmethod
        def recursive(*args, **kwargs): return _DummyStrategy()
        @staticmethod
        def none(): return _DummyStrategy()
        @staticmethod
        def booleans(): return _DummyStrategy()


# Canonical string domain: assigned, non-surrogate code points. canon rejects
# unassigned ('Cn') code points (cross-UCD-version hazard) and lone surrogates
# ('Cs'), so determinism/round-trip properties are tested over this alphabet.
_CANON_TEXT = st.text(st.characters(exclude_categories=('Cs', 'Cn')))


@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="Hypothesis not installed")
class TestHypothesis:
    """Property-based tests using Hypothesis."""

    @given(st.integers())
    def test_integer_determinism(self, n):
        """Any integer serializes deterministically."""
        from knurl.canon import serialize
        result1 = serialize(n)
        result2 = serialize(n)
        assert result1 == result2

    @given(st.floats(allow_nan=False, allow_infinity=False))
    def test_float_determinism(self, f):
        """Any valid float serializes deterministically with accept_floats=True."""
        from knurl.canon import serialize
        result1 = serialize(f, accept_floats=True)
        result2 = serialize(f, accept_floats=True)
        assert result1 == result2

    @given(_CANON_TEXT)
    def test_string_determinism(self, s):
        """Any canonical-domain string serializes deterministically."""
        from knurl.canon import serialize
        # Skip strings with lone surrogates
        try:
            s.encode('utf-8')
        except UnicodeEncodeError:
            assume(False)

        result1 = serialize(s)
        result2 = serialize(s)
        assert result1 == result2

    @given(st.dictionaries(_CANON_TEXT, st.integers()))
    def test_dict_determinism(self, d):
        """Any dict serializes deterministically."""
        from knurl.canon import serialize
        import unicodedata as _ud
        # Skip lone surrogates and keys that would collide after NFC normalization
        nfc_keys = []
        for key in d:
            try:
                key.encode('utf-8')
            except UnicodeEncodeError:
                assume(False)
            nfc_keys.append(_ud.normalize("NFC", key))
        assume(len(nfc_keys) == len(set(nfc_keys)))

        result1 = serialize(d)
        result2 = serialize(d)
        assert result1 == result2

    @given(st.lists(st.integers()))
    def test_list_determinism(self, lst):
        """Any list serializes deterministically."""
        from knurl.canon import serialize
        result1 = serialize(lst)
        result2 = serialize(lst)
        assert result1 == result2

    @given(st.recursive(
        st.none() | st.booleans() | st.integers() |
        st.floats(allow_nan=False, allow_infinity=False) | _CANON_TEXT,
        lambda children: st.lists(children) | st.dictionaries(_CANON_TEXT, children),
        max_leaves=50
    ))
    @settings(max_examples=200)
    def test_complex_structure_round_trip(self, obj):
        """Complex structures round-trip through JSON."""
        # Skip objects with problematic strings
        def check_strings(o):
            if isinstance(o, str):
                try:
                    o.encode('utf-8')
                except UnicodeEncodeError:
                    return False
            elif isinstance(o, dict):
                for k, v in o.items():
                    if not check_strings(k) or not check_strings(v):
                        return False
            elif isinstance(o, list):
                for item in o:
                    if not check_strings(item):
                        return False
            return True

        assume(check_strings(obj))

        from knurl.canon import serialize
        import unicodedata as _ud

        # Skip non-NFC strings: they normalize and may cause key collisions
        def all_nfc(o):
            if isinstance(o, str):
                return _ud.is_normalized("NFC", o)
            elif isinstance(o, dict):
                return all(all_nfc(k) and all_nfc(v) for k, v in o.items())
            elif isinstance(o, list):
                return all(all_nfc(i) for i in o)
            return True

        assume(all_nfc(obj))

        result = serialize(obj, accept_floats=True)
        parsed = json.loads(result)
        # Note: int/float distinction might be lost in round-trip
        assert result == serialize(parsed, accept_floats=True)


# =============================================================================
# Cross-Validation Tests
# =============================================================================

class TestCrossValidation:
    """Cross-validate against known implementations."""

    def test_against_json_dumps_sorted(self, serialize):
        """Compare output with json.dumps(sort_keys=True) for simple cases."""
        simple_cases = [
            {"b": 1, "a": 2},
            [1, 2, 3],
            "hello",
            42,
            True,
            None,
        ]

        for obj in simple_cases:
            result = serialize(obj)
            expected = json.dumps(obj, sort_keys=True, separators=(',', ':')).encode('utf-8')
            assert result == expected, f"Mismatch for {obj}"

    def test_nested_dict_matches_json_dumps(self, serialize):
        """Nested dict matches json.dumps sorted output."""
        obj = {
            "z": {"b": 1, "a": 2},
            "a": {"z": 3, "m": 4}
        }
        result = serialize(obj)
        expected = json.dumps(obj, sort_keys=True, separators=(',', ':')).encode('utf-8')
        assert result == expected


class TestSurrogateKeyWrapping:
    """A lone surrogate in a key must surface as CanonError, not a raw
    UnicodeEncodeError leaking past the wrapper (it arises from non-UTF-8
    filesystem names reaching serialization)."""

    def test_surrogate_key_raises_canon_error(self, serialize, CanonError):
        with pytest.raises(CanonError):
            serialize({"\udcff": "value"})

    def test_surrogate_value_raises_canon_error(self, serialize, CanonError):
        with pytest.raises(CanonError):
            serialize({"k": "\udcff"})


class TestTupleDepth:
    """json.dumps serializes tuples as arrays, so the depth/circular guards
    must cover tuples too - otherwise a deeply nested tuple leaks a raw
    RecursionError instead of CanonError."""

    def test_deeply_nested_tuple_raises_canon_error(self, serialize, CanonError):
        obj = 0
        for _ in range(2000):  # well past MAX_DEPTH
            obj = (obj,)
        with pytest.raises(CanonError):
            serialize(obj)

    def test_shallow_tuple_serializes_as_array(self, serialize):
        assert serialize((1, 2, 3)) == b"[1,2,3]"


# =============================================================================
# TestFloatRejection - Float rejection by default
# =============================================================================

class TestFloatRejection:
    """Floats are rejected by default; accept_floats=True is required for float use."""

    def test_float_rejected_by_default(self, serialize, CanonError):
        """Floats raise CanonError by default."""
        with pytest.raises(CanonError, match="[Ff]loat"):
            serialize(1.5)

    def test_float_in_dict_rejected_by_default(self, serialize, CanonError):
        """Float values nested in dicts are rejected by default."""
        with pytest.raises(CanonError):
            serialize({"x": 3.14})

    def test_float_in_list_rejected_by_default(self, serialize, CanonError):
        """Float values in lists are rejected by default."""
        with pytest.raises(CanonError):
            serialize([1, 2, 3.5])

    def test_nan_always_rejected(self, serialize, CanonError):
        """NaN is rejected even with accept_floats=True."""
        with pytest.raises(CanonError, match="[Nn]aN"):
            serialize(float('nan'), accept_floats=True)

    def test_infinity_always_rejected(self, serialize, CanonError):
        """Infinity is rejected even with accept_floats=True."""
        with pytest.raises(CanonError, match="[Ii]nf"):
            serialize(float('inf'), accept_floats=True)

    def test_negative_infinity_always_rejected(self, serialize, CanonError):
        """Negative infinity is rejected even with accept_floats=True."""
        with pytest.raises(CanonError, match="[Ii]nf"):
            serialize(float('-inf'), accept_floats=True)

    def test_accept_floats_enables_floats(self, serialize):
        """accept_floats=True permits float values."""
        assert serialize(1.5, accept_floats=True) == b'1.5'
        assert serialize({"pi": 3.14}, accept_floats=True) == b'{"pi":3.14}'

    def test_accept_floats_false_is_default(self, serialize, CanonError):
        """Calling serialize() with no flags rejects floats."""
        with pytest.raises(CanonError):
            serialize(0.5)


# =============================================================================
# TestNFCNormalization - NFC Unicode normalization
# =============================================================================

class TestNFCNormalization:
    """All string values are NFC-normalized before serialization."""

    def test_nfc_and_nfd_produce_same_bytes(self, serialize):
        """NFD and NFC input strings produce identical canonical bytes."""
        nfc = "é"    # precomposed é
        nfd = "é"   # e + combining acute accent
        assert serialize(nfc) == serialize(nfd)

    def test_nfc_applied_to_string_values(self, serialize):
        """String leaf values are NFC-normalized."""
        nfd_input = {"key": "é"}   # NFD é in value
        nfc_input = {"key": "é"}    # NFC é in value
        assert serialize(nfd_input) == serialize(nfc_input)

    def test_nfc_applied_to_keys(self, serialize):
        """Object keys are NFC-normalized."""
        nfd_key = {"é": 1}    # NFD é as key
        nfc_key = {"é": 1}     # NFC é as key
        assert serialize(nfd_key) == serialize(nfc_key)

    def test_nfc_applied_in_nested_structures(self, serialize):
        """NFC normalization applies recursively in nested structures."""
        nfd = {"a": {"b": "é"}}
        nfc = {"a": {"b": "é"}}
        assert serialize(nfd) == serialize(nfc)

    def test_nfc_applied_in_list_values(self, serialize):
        """NFC normalization applies to strings inside lists."""
        nfd = ["é", "café"]
        nfc = ["é", "café"]
        assert serialize(nfd) == serialize(nfc)

    def test_nfc_already_normalized_is_idempotent(self, serialize):
        """Strings already in NFC are unchanged."""
        nfc = "é"  # precomposed é, already NFC
        result = serialize(nfc)
        # Round-trip: parsed value should be the same NFC string
        assert json.loads(result) == nfc

    def test_nfc_duplicate_key_after_normalization_rejected(self, serialize, CanonError):
        """Keys that become identical after NFC normalization are rejected."""
        # "é" and "é" both normalize to "é"
        obj = {"é": 1, "é": 2}
        with pytest.raises(CanonError, match="[Dd]uplicate"):
            serialize(obj)

    def test_nfc_output_is_valid_utf8(self, serialize):
        """Canonical bytes are always valid UTF-8."""
        # Japanese characters — already NFC
        result = serialize({"greeting": "こんにちは"})
        result.decode('utf-8')  # must not raise

    def test_lone_surrogate_rejected(self, serialize, CanonError):
        """Strings with lone surrogates are rejected (cannot be UTF-8 encoded)."""
        try:
            lone = "\ud800"
            with pytest.raises(CanonError):
                serialize(lone)
        except (UnicodeEncodeError, UnicodeDecodeError):
            pytest.skip("Python rejected lone surrogate at string creation")


# =============================================================================
# TestConformanceVectors - Deterministic byte vectors for CI drift detection
# =============================================================================

class TestConformanceVectors:
    """Hard-coded input→bytes test vectors.

    These vectors verify that the canonical serialization produces bit-identical
    output across Python versions and implementation changes. Any drift is a
    breaking change to the wire format and must be treated as such.

    Reject vectors verify that specific inputs raise CanonError.

    Hex values computed from the SKEIN canonical serialization spec
    (finding-20260511-pqxy): RFC 8785 + mandatory NFC normalization.
    """

    # Positive vectors: (description, input, expected_hex)
    POSITIVE_VECTORS = [
        (
            "ASCII string pair",
            {"hello": "world"},
            "7b2268656c6c6f223a22776f726c64227d",
        ),
        (
            "Two-key sorted dict",
            {"b": 2, "a": 1},
            "7b2261223a312c2262223a327d",
        ),
        (
            "Empty object",
            {},
            "7b7d",
        ),
        (
            "Empty array",
            [],
            "5b5d",
        ),
        (
            "Booleans and null (sorted keys a < b < c)",
            {"c": True, "a": False, "b": None},
            "7b2261223a66616c73652c2262223a6e756c6c2c2263223a747275657d",
        ),
        (
            "Large integer beyond JS safe range (2^53+1)",
            {"n": 9007199254740993},
            "7b226e223a393030373139393235343734303939337d",
        ),
        (
            "Microsecond timestamp (SKEIN created_at field)",
            {"created_at": 1746915264123456},
            "7b22637265617465645f6174223a313734363931353236343132333435367d",
        ),
        (
            "Deeply nested structure",
            {"a": {"b": {"c": 1}}},
            "7b2261223a7b2262223a7b2263223a317d7d7d",
        ),
        (
            "Mixed-type array (integers, booleans, null, string)",
            [1, True, False, None, "ok"],
            "5b312c747275652c66616c73652c6e756c6c2c226f6b225d",
        ),
        (
            "NFC key precomposed (café with é=U+00E9)",
            # Key "café" where é is precomposed U+00E9 (already NFC)
            {"café": 1},
            "7b22636166c3a9223a317d",
        ),
        (
            "NFD key normalized to NFC (e + combining acute -> é)",
            # Key is NFD: e (U+0065) + combining acute (U+0301)
            # After NFC normalization: é (U+00E9)
            # Output must equal the NFC key vector above
            {"é": 1},
            "7b22c3a9223a317d",
        ),
    ]

    # Float vectors (accept_floats=True required)
    FLOAT_VECTORS = [
        (
            "Negative zero normalized to positive zero",
            -0.0,
            "302e30",  # b'0.0' — Python json.dumps(0.0) = '0.0'
        ),
        (
            "Simple float",
            1.5,
            "312e35",  # b'1.5'
        ),
    ]

    # Reject vectors: (description, input, accept_floats)
    REJECT_VECTORS = [
        ("NaN always rejected",             float('nan'),        True),
        ("Positive infinity always rejected", float('inf'),       True),
        ("Negative infinity always rejected", float('-inf'),      True),
        ("Float rejected by default",        1.5,                False),
        ("Float in dict rejected by default", {"x": 3.14},       False),
        ("Non-string dict key rejected",     {1: "one"},         False),
        ("None dict key rejected",           {None: "v"},        False),
    ]

    def test_positive_vectors(self, serialize):
        """All positive vectors produce the expected canonical bytes."""
        for desc, input_val, expected_hex in self.POSITIVE_VECTORS:
            result = serialize(input_val)
            expected = bytes.fromhex(expected_hex)
            assert result == expected, (
                f"Vector '{desc}' failed:\n"
                f"  got:      {result.hex()}\n"
                f"  expected: {expected_hex}"
            )

    def test_float_vectors(self, serialize):
        """Float vectors produce expected bytes when accept_floats=True."""
        for desc, input_val, expected_hex in self.FLOAT_VECTORS:
            result = serialize(input_val, accept_floats=True)
            expected = bytes.fromhex(expected_hex)
            assert result == expected, (
                f"Float vector '{desc}' failed:\n"
                f"  got:      {result.hex()}\n"
                f"  expected: {expected_hex}"
            )

    def test_reject_vectors(self, serialize, CanonError):
        """All reject vectors raise CanonError."""
        for desc, input_val, accept_floats in self.REJECT_VECTORS:
            with pytest.raises(CanonError):
                serialize(input_val, accept_floats=accept_floats)

    def test_nfc_and_nfd_produce_same_hex(self, serialize):
        """NFD and NFC variants of the same key produce identical canonical bytes."""
        nfc_result = serialize({"é": 1})
        nfd_result = serialize({"é": 1})
        assert nfc_result == nfd_result
        assert nfc_result.hex() == "7b22c3a9223a317d"

    def test_depth_limit_enforced(self, serialize, CanonError):
        """Nesting beyond MAX_DEPTH raises CanonError."""
        from knurl.canon import MAX_DEPTH
        # Build structure with depth = MAX_DEPTH + 1
        obj = {}
        current = obj
        for _ in range(MAX_DEPTH + 1):
            inner = {}
            current["x"] = inner
            current = inner
        with pytest.raises(CanonError, match="[Dd]epth"):
            serialize(obj)

    def test_circular_reference_rejected(self, serialize, CanonError):
        """Circular references raise CanonError."""
        obj = {"a": 1}
        obj["self"] = obj
        with pytest.raises((CanonError, ValueError, RecursionError)):
            serialize(obj)

    def test_utf16_sort_diverges_from_code_point_order(self, serialize):
        """Verify UTF-16 sort order for supplementary vs high-BMP characters."""
        # U+10000 has UTF-16 high surrogate 0xD800 < U+E000 = 0xE000
        # So in UTF-16 code unit order: U+10000 sorts BEFORE U+E000
        # (opposite of code point order: 0x10000 > 0xE000)
        obj = {"": 1, "\U00010000": 2}
        result = serialize(obj)
        keys = list(json.loads(result).keys())
        assert keys[0] == "\U00010000"
        assert keys[1] == ""


class TestIntegerMagnitude:
    """Integers are bounded to MAX_INT_DIGITS decimal digits, enforced uniformly
    across interpreter versions (CPython 3.11+ caps int<->str at 4300 digits; older
    versions do not). The bound is what keeps a huge integer from hashing on one
    node and being rejected on another."""

    def test_max_digits_value(self):
        from knurl.canon import MAX_INT_DIGITS
        assert MAX_INT_DIGITS == 4300

    def test_integer_at_limit_serializes(self, serialize):
        # 10**4299 has exactly 4300 digits -> accepted.
        n = 10 ** (4300 - 1)
        assert len(str(n)) == 4300
        assert serialize({"n": n}) == b'{"n":' + str(n).encode() + b'}'

    def test_integer_over_limit_raises_canon_error(self, serialize, CanonError):
        # 10**4300 is 1 followed by 4300 zeros = 4301 digits -> rejected. (We do
        # NOT str() it: on 3.11+ str() of a 4301-digit int itself raises ValueError
        # from the int<->str cap — exactly the cost canon.serialize must avoid.)
        n = 10 ** 4300
        with pytest.raises(CanonError):
            serialize({"n": n})

    def test_negative_over_limit_raises(self, serialize, CanonError):
        with pytest.raises(CanonError):
            serialize(-(10 ** 4300))

    def test_bool_is_not_caught_by_int_bound(self, serialize):
        # bool is an int subclass but must serialize as true/false, never be
        # mistaken for an oversized integer.
        assert serialize({"a": True, "b": False}) == b'{"a":true,"b":false}'

    def test_ordinary_large_ints_unaffected(self, serialize):
        # Values SKEIN actually uses (microsecond timestamps, >2^53 ids) are tiny
        # next to the limit and round-trip exactly.
        for n in (2 ** 53 + 1, 2 ** 64, 1746915264123456, 10 ** 100):
            assert json.loads(serialize({"n": n}))["n"] == n

    def test_lowered_int_str_limit_is_rejected(self, serialize, CanonError):
        # If the process lowers the int<->str cap below MAX_INT_DIGITS, serialize
        # must fail loudly rather than silently diverge from nodes at the default
        # cap (json.dumps would reject some <=MAX_INT_DIGITS ints those nodes accept).
        set_limit = getattr(sys, "set_int_max_str_digits", None)
        get_limit = getattr(sys, "get_int_max_str_digits", None)
        if set_limit is None or get_limit is None:
            pytest.skip("interpreter has no int<->str digit cap (CPython < 3.11)")
        original = get_limit()
        try:
            set_limit(1000)  # below MAX_INT_DIGITS (4300)
            with pytest.raises(CanonError):
                serialize({"n": 1})
        finally:
            set_limit(original)

    def test_default_int_str_limit_serializes(self, serialize):
        # At the default cap (== MAX_INT_DIGITS) or unlimited, serialize works.
        assert serialize({"n": 1}) == b'{"n":1}'


class TestUnassignedCodePointRejection:
    """Code points unassigned ('Cn') in the running Unicode database are rejected
    so a cross-UCD-version normalization divergence fails loudly rather than
    producing a second canonical form. Assigned code points (incl. private-use)
    serialize normally."""

    def test_unicode_version_is_exposed(self):
        from knurl.canon import UNICODE_VERSION
        assert UNICODE_VERSION == unicodedata.unidata_version

    def test_noncharacter_rejected(self, serialize, CanonError):
        for cp in ("￿", "﷐", "\U0010FFFF"):  # permanent noncharacters
            assert unicodedata.category(cp) == "Cn"
            with pytest.raises(CanonError):
                serialize({"k": cp})
            with pytest.raises(CanonError):
                serialize(cp)  # also as a top-level / key value

    def test_unassigned_as_key_rejected(self, serialize, CanonError):
        with pytest.raises(CanonError):
            serialize({"￿": 1})

    def test_assigned_text_and_private_use_serialize(self, serialize):
        assert unicodedata.category("") == "Co"  # private use is assigned
        assert serialize({"k": ""}) == b'{"k":"\xee\x80\x80"}'
        assert serialize({"café": "naïve"}) is not None

    def test_surrogate_still_rejected_not_via_cn(self, serialize, CanonError):
        # Lone surrogates are category 'Cs', caught by the UTF-8 encode check.
        with pytest.raises(CanonError):
            serialize({"k": "\ud800"})
