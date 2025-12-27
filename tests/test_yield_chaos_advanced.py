"""
CHAOS TEST: yield_.py - Advanced destruction suite
More exotic edge cases and potential exploits.
"""

import json
import pytest
from knurl import yield_ as y


class TestPrototypeInspiration:
    """
    Python doesn't have prototype pollution like JS, but there are
    analogous issues with special dunder keys and class attributes.
    """

    def test_dunder_class_key(self):
        """__class__ as a key - legal in JSON, weird in Python."""
        data = {
            'task_id': 'test',
            'result': 'success',
            '__class__': 'should_be_harmless',
        }
        errors = y.validate(data)
        assert errors == []
        restored = y.deserialize(y.serialize(data))
        assert restored['__class__'] == 'should_be_harmless'

    def test_dunder_dict_key(self):
        """__dict__ as a key."""
        data = {
            'task_id': 'test',
            'result': 'success',
            '__dict__': {'overwrite': 'attempt'},
        }
        errors = y.validate(data)
        assert errors == []
        restored = y.deserialize(y.serialize(data))
        assert restored['__dict__'] == {'overwrite': 'attempt'}

    def test_dunder_init_key(self):
        """__init__ as a key."""
        data = {
            'task_id': 'test',
            'result': 'success',
            '__init__': 'malicious',
        }
        restored = y.deserialize(y.serialize(data))
        assert restored['__init__'] == 'malicious'


class TestKeyCollisionAttacks:
    """What if keys collide in subtle ways?"""

    def test_whitespace_key_variants(self):
        """Keys that differ only in trailing/leading whitespace."""
        data = {
            'task_id': 'test',
            'result': 'success',
            'key': 'no space',
            ' key': 'leading space',
            'key ': 'trailing space',
        }
        restored = y.deserialize(y.serialize(data))
        assert len(restored) == 5
        assert restored['key'] == 'no space'
        assert restored[' key'] == 'leading space'
        assert restored['key '] == 'trailing space'

    def test_unicode_normalization_collision(self):
        """
        Unicode strings that look identical but have different byte representations.
        é could be U+00E9 or U+0065 U+0301
        """
        # Composed form (single codepoint)
        key1 = '\u00e9'  # é
        # Decomposed form (e + combining acute accent)
        key2 = 'e\u0301'  # é (visually identical)

        data = {
            'task_id': 'test',
            'result': 'success',
            key1: 'composed',
            key2: 'decomposed',
        }
        # These look identical but are different keys!
        assert key1 != key2
        restored = y.deserialize(y.serialize(data))
        # Both keys preserved separately
        assert restored[key1] == 'composed'
        assert restored[key2] == 'decomposed'

    def test_case_collision(self):
        """Keys differing only in case."""
        data = {
            'task_id': 'test',
            'result': 'success',
            'Task_ID': 'uppercase version',
        }
        errors = y.validate(data)
        assert errors == []  # Both task_id and Task_ID present
        restored = y.deserialize(y.serialize(data))
        assert restored['task_id'] == 'test'
        assert restored['Task_ID'] == 'uppercase version'


class TestNumericLimits:
    """Numeric edge cases that might cause issues."""

    def test_float_max(self):
        """Maximum float value."""
        import sys
        data = {'task_id': 'test', 'result': 'success', 'output': sys.float_info.max}
        restored = y.deserialize(y.serialize(data))
        assert restored['output'] == sys.float_info.max

    def test_float_min_positive(self):
        """Minimum positive float value."""
        import sys
        data = {'task_id': 'test', 'result': 'success', 'output': sys.float_info.min}
        restored = y.deserialize(y.serialize(data))
        assert restored['output'] == sys.float_info.min

    def test_float_epsilon(self):
        """Float epsilon."""
        import sys
        data = {'task_id': 'test', 'result': 'success', 'output': sys.float_info.epsilon}
        restored = y.deserialize(y.serialize(data))
        assert restored['output'] == sys.float_info.epsilon

    def test_subnormal_float(self):
        """Subnormal (denormalized) float."""
        import sys
        subnormal = sys.float_info.min / 2
        data = {'task_id': 'test', 'result': 'success', 'output': subnormal}
        restored = y.deserialize(y.serialize(data))
        # Subnormal floats might lose precision in JSON
        assert abs(restored['output'] - subnormal) < sys.float_info.epsilon

    def test_integer_disguised_as_float(self):
        """Integer value stored as float."""
        data = {'task_id': 'test', 'result': 'success', 'output': 5.0}
        serialized = y.serialize(data)
        # JSON might serialize 5.0 as "5" or "5.0"
        restored = y.deserialize(serialized)
        assert restored['output'] == 5.0


class TestHashStability:
    """
    Test that the same data produces the same serialization.
    Important for content-addressable storage.
    """

    def test_key_order_invariance(self):
        """Different key insertion order produces same output."""
        from collections import OrderedDict

        # Create dicts with different insertion order
        d1 = {'z': 1, 'a': 2, 'm': 3}
        d2 = {'a': 2, 'm': 3, 'z': 1}
        d3 = {'m': 3, 'z': 1, 'a': 2}

        s1 = y.serialize({'task_id': 't', 'result': 'success', 'output': d1})
        s2 = y.serialize({'task_id': 't', 'result': 'success', 'output': d2})
        s3 = y.serialize({'task_id': 't', 'result': 'success', 'output': d3})

        assert s1 == s2 == s3

    def test_list_order_preserved(self):
        """List order MUST be preserved (not sorted)."""
        data = {'task_id': 't', 'result': 'success', 'output': [3, 1, 2]}
        restored = y.deserialize(y.serialize(data))
        assert restored['output'] == [3, 1, 2]  # Order preserved

    def test_nested_key_order_invariance(self):
        """Deeply nested key order doesn't affect output."""
        nested1 = {'outer': {'inner': {'z': 1, 'a': 2}}}
        nested2 = {'outer': {'inner': {'a': 2, 'z': 1}}}

        s1 = y.serialize({'task_id': 't', 'result': 'success', 'output': nested1})
        s2 = y.serialize({'task_id': 't', 'result': 'success', 'output': nested2})

        assert s1 == s2


class TestJsonEdgeCases:
    """JSON-specific edge cases."""

    def test_unicode_escapes_in_key(self):
        """Keys with Unicode escape sequences."""
        data = {'task_id': 'test', 'result': 'success', '\u0000': 'null char key'}
        restored = y.deserialize(y.serialize(data))
        assert restored['\x00'] == 'null char key'

    def test_empty_string_key(self):
        """Empty string as dictionary key."""
        data = {'task_id': 'test', 'result': 'success', '': 'empty key'}
        restored = y.deserialize(y.serialize(data))
        assert restored[''] == 'empty key'

    def test_backslash_in_string(self):
        """Backslashes must be properly escaped."""
        data = {'task_id': 'test', 'result': 'success', 'output': 'C:\\Windows\\System32'}
        restored = y.deserialize(y.serialize(data))
        assert restored['output'] == 'C:\\Windows\\System32'

    def test_quotes_in_string(self):
        """Quotes must be properly escaped."""
        data = {'task_id': 'test', 'result': 'success', 'output': 'He said "hello"'}
        restored = y.deserialize(y.serialize(data))
        assert restored['output'] == 'He said "hello"'

    def test_all_json_escapes(self):
        """All JSON escape sequences."""
        # \", \\, \/, \b, \f, \n, \r, \t
        special = '"\\/\b\f\n\r\t'
        data = {'task_id': 'test', 'result': 'success', 'output': special}
        restored = y.deserialize(y.serialize(data))
        assert restored['output'] == special


class TestBooleanConfusion:
    """Boolean edge cases."""

    def test_boolean_in_output(self):
        """True/False survive as booleans, not 1/0."""
        data = {'task_id': 'test', 'result': 'success', 'output': True}
        restored = y.deserialize(y.serialize(data))
        assert restored['output'] is True
        # Note: In Python, True == 1 evaluates to True (boolean is subclass of int)
        # But we can check type identity
        assert isinstance(restored['output'], bool)

    def test_boolean_strict_identity(self):
        """Boolean identity check."""
        data = {'task_id': 'test', 'result': 'success', 'output': False}
        restored = y.deserialize(y.serialize(data))
        # Note: 0 == False in Python, but we want type preservation
        assert isinstance(restored['output'], bool)

    def test_boolean_vs_int_in_list(self):
        """Booleans and ints in same list."""
        data = {'task_id': 'test', 'result': 'success', 'output': [True, 1, False, 0]}
        restored = y.deserialize(y.serialize(data))
        assert restored['output'] == [True, 1, False, 0]
        # Type check
        assert isinstance(restored['output'][0], bool)
        assert isinstance(restored['output'][1], int) and not isinstance(restored['output'][1], bool)
        assert isinstance(restored['output'][2], bool)
        assert isinstance(restored['output'][3], int) and not isinstance(restored['output'][3], bool)


class TestNullConfusion:
    """Null/None edge cases."""

    def test_null_vs_missing(self):
        """Explicit null vs missing key."""
        with_null = {'task_id': 'test', 'result': 'success', 'error': None}
        without = {'task_id': 'test', 'result': 'success'}

        r1 = y.deserialize(y.serialize(with_null))
        r2 = y.deserialize(y.serialize(without))

        # with_null has 'error' key, without doesn't
        assert 'error' in r1
        assert 'error' not in r2

    def test_string_null_vs_null(self):
        """String "null" vs actual null."""
        data = {
            'task_id': 'test',
            'result': 'success',
            'output': {'real_null': None, 'string_null': 'null'},
        }
        restored = y.deserialize(y.serialize(data))
        assert restored['output']['real_null'] is None
        assert restored['output']['string_null'] == 'null'


class TestResultFieldHijacking:
    """Can we confuse the result field?"""

    def test_result_with_extra_whitespace(self):
        """Result with leading/trailing whitespace."""
        data = {'task_id': 'test', 'result': ' success '}
        errors = y.validate(data)
        # Whitespace makes it invalid - ' success ' != 'success'
        assert len(errors) == 1

    def test_result_case_sensitivity(self):
        """Result is case-sensitive."""
        for bad_result in ['SUCCESS', 'Success', 'FAILED', 'Failed', 'SKIPPED', 'Skipped']:
            data = {'task_id': 'test', 'result': bad_result}
            errors = y.validate(data)
            assert len(errors) == 1, f"{bad_result} should be invalid"

    def test_result_unicode_lookalike(self):
        """Result with Unicode lookalike characters."""
        # Using Cyrillic 'с' (U+0441) which looks like Latin 's'
        fake_success = 'succes\u0441'  # Last 's' is Cyrillic
        data = {'task_id': 'test', 'result': fake_success}
        errors = y.validate(data)
        assert len(errors) == 1  # Should be rejected


class TestMutabilityAfterDeserialization:
    """Check that deserialized data is properly independent."""

    def test_modify_after_deserialize(self):
        """Modifying deserialized data doesn't affect other copies."""
        original = {'task_id': 'test', 'result': 'success', 'output': {'a': 1}}
        serialized = y.serialize(original)

        copy1 = y.deserialize(serialized)
        copy2 = y.deserialize(serialized)

        copy1['output']['a'] = 999
        assert copy2['output']['a'] == 1  # Unaffected


class TestMemoryExhaustionVectors:
    """Inputs that could cause memory issues."""

    def test_repeated_string_reference(self):
        """Same string repeated many times (should be efficient)."""
        repeated = ['same_string'] * 10000
        data = {'task_id': 'test', 'result': 'success', 'output': repeated}
        restored = y.deserialize(y.serialize(data))
        assert len(restored['output']) == 10000
        assert all(s == 'same_string' for s in restored['output'])

    def test_exponential_key_length(self):
        """Keys with exponentially increasing length."""
        keys = {('k' * (2 ** i)): i for i in range(10)}  # 1, 2, 4, 8, ... 512 char keys
        data = {'task_id': 'test', 'result': 'success', 'output': keys}
        restored = y.deserialize(y.serialize(data))
        assert len(restored['output']) == 10


class TestChaosGapSummary:
    """Final summary of all identified gaps."""

    def test_full_gap_inventory(self):
        """Complete inventory of validation gaps."""
        gaps = {
            'type_safety': [
                "task_id accepts any JSON type (int, list, dict, None, bool)",
                "task_id accepts empty string",
                "files field has no type validation (accepts string, int, dict)",
                "metadata field has no type validation",
                "error field has no type validation",
                "shard_name field has no type validation",
            ],
            'semantic': [
                "validate() and serialize() check orthogonal properties",
                "deserialize() returns any valid JSON, not just dicts",
                "get_task_id/get_shard_name return falsy values differently than None",
                "No length limits on any field",
                "No character restrictions on task_id",
            ],
            'interop': [
                "Very large integers may not survive JS roundtrip",
                "Tuples silently become lists",
                "Unicode normalization not enforced (NFC vs NFD)",
            ],
        }

        print("\n\nCOMPLETE GAP INVENTORY:")
        for category, items in gaps.items():
            print(f"\n{category.upper()}:")
            for item in items:
                print(f"  • {item}")

        # Count total gaps
        total = sum(len(v) for v in gaps.values())
        print(f"\nTOTAL GAPS: {total}")
        assert total > 0  # Documentation test
