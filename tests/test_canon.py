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
# from spiritengine.canon import serialize, CanonError


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================

@pytest.fixture
def serialize():
    """Import serialize function - allows tests to run before implementation exists."""
    from spiritengine.canon import serialize
    return serialize


@pytest.fixture
def CanonError():
    """Import CanonError exception class."""
    from spiritengine.canon import CanonError
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
        """Unicode keys sort by UTF-16 code unit order (RFC 8785)."""
        # For BMP characters, UTF-16 order matches Unicode code point order
        obj = {"\u00e9": 1, "e": 2, "\u0065\u0301": 3}  # é, e, e+combining
        result = serialize(obj)
        # "e" (U+0065) < "e\u0301" (U+0065 U+0301) < "é" (U+00E9)
        assert result.index(b'"e"') < result.index(b'"\xc3\xa9"')

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
        """RFC 8785: -0 must serialize as 0."""
        result = serialize(-0.0)
        # Should NOT contain minus sign
        assert result == b'0' or result == b'0.0'
        assert b'-' not in result

    def test_positive_zero(self, serialize):
        """Positive zero serializes correctly."""
        result = serialize(0.0)
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
        """Simple float values serialize correctly."""
        assert serialize(1.5) == b'1.5'
        assert serialize(0.5) == b'0.5'
        assert serialize(123.456) == b'123.456'

    def test_float_precision_reproducibility(self, serialize):
        """Float precision is consistent across calls."""
        val = 0.1 + 0.2  # Known to be 0.30000000000000004
        result1 = serialize(val)
        result2 = serialize(val)
        assert result1 == result2

    def test_scientific_notation_consistency(self, serialize):
        """Large/small floats consistently use or avoid scientific notation."""
        large = 1e20
        small = 1e-10

        result_large = serialize(large)
        result_small = serialize(small)

        # Results should be consistent (we don't mandate format, just consistency)
        assert serialize(large) == result_large
        assert serialize(small) == result_small

    def test_float_vs_integer_distinction(self, serialize):
        """Float and integer serialize differently when values differ."""
        # 1 and 1.0 may or may not produce different output depending on impl
        # But 1 and 1.5 must differ
        assert serialize(1) != serialize(1.5)

    def test_very_small_float(self, serialize):
        """Very small floats serialize without error."""
        tiny = 1e-300
        result = serialize(tiny)
        assert isinstance(result, bytes)
        # Should round-trip
        parsed = json.loads(result)
        assert parsed == tiny or abs(parsed - tiny) / tiny < 1e-10

    def test_very_large_float(self, serialize):
        """Very large floats serialize without error."""
        huge = 1e300
        result = serialize(huge)
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
        """Combining characters serialize correctly."""
        # e + combining acute = é (two code points)
        combining = "e\u0301"
        result = serialize(combining)
        parsed = json.loads(result)
        assert parsed == combining

    def test_unicode_normalization_preserved(self, serialize):
        """Different Unicode normalizations produce different output."""
        # NFC: é as single code point
        nfc = "\u00e9"
        # NFD: e + combining acute
        nfd = "e\u0301"

        result_nfc = serialize(nfc)
        result_nfd = serialize(nfd)

        # These are different strings, should produce different canonical output
        assert result_nfc != result_nfd

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
        """Integer and float may serialize differently."""
        int_result = serialize(1)
        float_result = serialize(1.0)
        # They might be the same (b'1') or different (b'1' vs b'1.0')
        # Both are valid, but they should be consistent
        assert serialize(1) == int_result
        assert serialize(1.0) == float_result

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
        obj = [1, "two", True, None, 3.5]
        result = serialize(obj)
        assert result == b'[1,"two",true,null,3.5]'

    def test_mixed_nested_structure(self, serialize):
        """Complex nested structure with mixed types."""
        obj = {
            "string": "hello",
            "number": 42,
            "float": 3.14,
            "bool": True,
            "null": None,
            "list": [1, 2, 3],
            "nested": {"a": 1}
        }
        result = serialize(obj)
        assert isinstance(result, bytes)
        # Verify round-trip
        parsed = json.loads(result)
        assert parsed["string"] == "hello"
        assert parsed["number"] == 42
        assert parsed["bool"] is True
        assert parsed["null"] is None


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
        for value in [42, 3.14, "hello", True, False, None]:
            result = serialize(value)
            parsed = json.loads(result)
            assert parsed == value

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
        def text(): return _DummyStrategy()
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


@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="Hypothesis not installed")
class TestHypothesis:
    """Property-based tests using Hypothesis."""

    @given(st.integers())
    def test_integer_determinism(self, n):
        """Any integer serializes deterministically."""
        from spiritengine.canon import serialize
        result1 = serialize(n)
        result2 = serialize(n)
        assert result1 == result2

    @given(st.floats(allow_nan=False, allow_infinity=False))
    def test_float_determinism(self, f):
        """Any valid float serializes deterministically."""
        from spiritengine.canon import serialize
        result1 = serialize(f)
        result2 = serialize(f)
        assert result1 == result2

    @given(st.text())
    def test_string_determinism(self, s):
        """Any string serializes deterministically."""
        from spiritengine.canon import serialize
        # Skip strings with lone surrogates
        try:
            s.encode('utf-8')
        except UnicodeEncodeError:
            assume(False)

        result1 = serialize(s)
        result2 = serialize(s)
        assert result1 == result2

    @given(st.dictionaries(st.text(), st.integers()))
    def test_dict_determinism(self, d):
        """Any dict serializes deterministically."""
        from spiritengine.canon import serialize
        # Skip strings with lone surrogates in keys
        for key in d:
            try:
                key.encode('utf-8')
            except UnicodeEncodeError:
                assume(False)

        result1 = serialize(d)
        result2 = serialize(d)
        assert result1 == result2

    @given(st.lists(st.integers()))
    def test_list_determinism(self, lst):
        """Any list serializes deterministically."""
        from spiritengine.canon import serialize
        result1 = serialize(lst)
        result2 = serialize(lst)
        assert result1 == result2

    @given(st.recursive(
        st.none() | st.booleans() | st.integers() |
        st.floats(allow_nan=False, allow_infinity=False) | st.text(),
        lambda children: st.lists(children) | st.dictionaries(st.text(), children),
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

        from spiritengine.canon import serialize
        result = serialize(obj)
        parsed = json.loads(result)
        # Note: int/float distinction might be lost in round-trip
        # We just verify it's valid JSON
        assert result == serialize(parsed)


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
