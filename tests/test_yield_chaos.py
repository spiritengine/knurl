"""
CHAOS TEST: yield_.py destruction suite
Finding the gaps, breaking the assumptions.

Run with: pytest mill/ledger/tests/test_yield_chaos.py -v
"""

import json
import math
import pytest

from knurl import yield_ as y
from knurl.canon import CanonError


class TestTypeConfusion:
    """Type confusion attacks - validate() doesn't check types."""

    def test_task_id_as_integer(self):
        """task_id as int passes validation - GAP!"""
        data = {'task_id': 12345, 'result': 'success'}
        errors = y.validate(data)
        # This SHOULD fail but doesn't - validate doesn't check type
        assert errors == [], "Expected empty (this is a gap - int task_id accepted)"

    def test_task_id_as_list(self):
        """task_id as list passes validation - GAP!"""
        data = {'task_id': ['a', 'b', 'c'], 'result': 'success'}
        errors = y.validate(data)
        assert errors == [], "Expected empty (this is a gap - list task_id accepted)"

    def test_task_id_as_dict(self):
        """task_id as dict passes validation - GAP!"""
        data = {'task_id': {'nested': 'dict'}, 'result': 'success'}
        errors = y.validate(data)
        assert errors == [], "Expected empty (this is a gap - dict task_id accepted)"

    def test_task_id_as_none(self):
        """task_id as None passes validation - GAP!"""
        data = {'task_id': None, 'result': 'success'}
        errors = y.validate(data)
        # 'task_id' key exists, so "missing field" check passes
        # but None is probably not a valid task_id semantically
        assert errors == [], "Expected empty (this is a gap - None task_id accepted)"

    def test_task_id_as_empty_string(self):
        """task_id as empty string passes validation - GAP!"""
        data = {'task_id': '', 'result': 'success'}
        errors = y.validate(data)
        assert errors == [], "Expected empty (this is a gap - empty string task_id accepted)"

    def test_result_as_integer_zero(self):
        """result as integer correctly rejected."""
        data = {'task_id': 'test', 'result': 0}
        errors = y.validate(data)
        # 0 is not in VALID_RESULTS set, so this correctly fails
        assert len(errors) == 1
        assert 'invalid' in errors[0].lower() or 'result' in errors[0].lower()

    def test_result_as_boolean(self):
        """result as boolean correctly rejected."""
        data = {'task_id': 'test', 'result': True}
        errors = y.validate(data)
        # True is not in VALID_RESULTS set
        assert len(errors) == 1


class TestSerializationAsymmetry:
    """Things that change type during serialization round-trip."""

    def test_tuple_becomes_list(self):
        """Tuples silently become lists - semantic change!"""
        data = {'task_id': 'test', 'result': 'success', 'output': (1, 2, 3)}
        serialized = y.serialize(data)
        restored = y.deserialize(serialized)
        # Tuple became list
        assert restored['output'] == [1, 2, 3]
        assert isinstance(restored['output'], list)
        assert not isinstance(restored['output'], tuple)
        # This is expected JSON behavior, but downstream code might care

    def test_int_keys_rejected(self):
        """Dict with int keys is correctly rejected by canon."""
        data = {'task_id': 'test', 'result': 'success', 'output': {1: 'one', 2: 'two'}}
        with pytest.raises(CanonError) as exc:
            y.serialize(data)
        assert 'string' in str(exc.value).lower()

    def test_set_rejected(self):
        """Sets are not JSON serializable."""
        data = {'task_id': 'test', 'result': 'success', 'output': {1, 2, 3}}
        with pytest.raises(TypeError):
            y.serialize(data)

    def test_bytes_rejected(self):
        """Bytes are not JSON serializable."""
        data = {'task_id': 'test', 'result': 'success', 'output': b'binary data'}
        with pytest.raises(TypeError):
            y.serialize(data)


class TestSpecialFloatValues:
    """Float edge cases."""

    def test_negative_zero_normalized(self):
        """-0.0 should normalize to 0.0."""
        data = {'task_id': 'test', 'result': 'success', 'output': -0.0}
        restored = y.deserialize(y.serialize(data))
        # Should be positive zero now
        assert math.copysign(1.0, restored['output']) > 0

    def test_very_large_int_survives(self):
        """Very large int (beyond JS safe int) survives round-trip."""
        big = 2**64
        data = {'task_id': 'test', 'result': 'success', 'output': big}
        restored = y.deserialize(y.serialize(data))
        assert restored['output'] == big
        # NOTE: JS consumers may have precision issues!

    def test_float_precision(self):
        """Float precision edge cases."""
        # 0.1 + 0.2 famously != 0.3 in float
        val = 0.1 + 0.2
        data = {'task_id': 'test', 'result': 'success', 'output': val}
        restored = y.deserialize(y.serialize(data))
        assert restored['output'] == val  # Preserves exact float representation


class TestValidateSerializeMismatch:
    """Cases where validate() and serialize() disagree."""

    def test_validates_but_doesnt_serialize(self):
        """Data passes validate() but fails serialize()."""
        class NotSerializable:
            pass
        data = {'task_id': 'test', 'result': 'success', 'output': NotSerializable()}
        errors = y.validate(data)
        assert errors == [], "validate() doesn't check output serializability"
        with pytest.raises(TypeError):
            y.serialize(data)

    def test_serializes_but_doesnt_validate(self):
        """Data fails validate() but passes serialize()."""
        data = {'task_id': 'test', 'result': 'bogus_status'}
        errors = y.validate(data)
        assert len(errors) == 1, "Should have validation error"
        # But it serializes fine!
        serialized = y.serialize(data)
        assert isinstance(serialized, str)
        # This is arguably correct - serialize is just JSON, validate is semantic


class TestExtractorEdgeCases:
    """Edge cases in get_task_id and get_shard_name."""

    def test_get_task_id_with_zero(self):
        """get_task_id returns 0 (not None) when task_id is 0."""
        data = {'task_id': 0, 'result': 'success'}
        result = y.get_task_id(data)
        assert result == 0
        assert result is not None  # Falsy but present

    def test_get_shard_name_empty_string(self):
        """get_shard_name returns '' (not None) when shard_name is ''."""
        data = {'task_id': 'test', 'result': 'success', 'shard_name': ''}
        result = y.get_shard_name(data)
        assert result == ''
        assert result is not None

    def test_get_task_id_with_false(self):
        """get_task_id returns False (not None) when task_id is False."""
        data = {'task_id': False, 'result': 'success'}
        result = y.get_task_id(data)
        assert result is False


class TestDownstreamPoisoning:
    """Yields that validate but would poison downstream code."""

    def test_files_as_string_not_list(self):
        """files field as string passes validation - GAP!"""
        data = {'task_id': 'test', 'result': 'success', 'files': '/single/file.txt'}
        errors = y.validate(data)
        assert errors == [], "validate doesn't check files type"
        # Downstream code expecting list would break

    def test_metadata_as_string_not_dict(self):
        """metadata field as string passes validation - GAP!"""
        data = {'task_id': 'test', 'result': 'success', 'metadata': 'not a dict'}
        errors = y.validate(data)
        assert errors == [], "validate doesn't check metadata type"

    def test_error_as_dict_not_string(self):
        """error field as dict passes validation - GAP!"""
        data = {'task_id': 'test', 'result': 'failed', 'error': {'code': 500, 'msg': 'fail'}}
        errors = y.validate(data)
        assert errors == [], "validate doesn't check error type"

    def test_shard_name_as_dict(self):
        """shard_name as complex object passes validation - GAP!"""
        data = {'task_id': 'test', 'result': 'success', 'shard_name': {'branch': 'main'}}
        errors = y.validate(data)
        assert errors == [], "validate doesn't check shard_name type"


class TestUntrustedDeserialization:
    """Deserializing from untrusted sources."""

    def test_deserialize_array(self):
        """Deserialize JSON array returns list (not dict)."""
        result = y.deserialize('[1, 2, 3]')
        assert isinstance(result, list)
        # This is technically valid but callers expecting dict will fail

    def test_deserialize_primitive_int(self):
        """Deserialize primitive int."""
        result = y.deserialize('42')
        assert result == 42
        # Not a dict!

    def test_deserialize_primitive_string(self):
        """Deserialize primitive string."""
        result = y.deserialize('"hello"')
        assert result == 'hello'

    def test_deserialize_null(self):
        """Deserialize null returns None."""
        result = y.deserialize('null')
        assert result is None

    def test_deserialize_trailing_garbage_rejected(self):
        """JSON with trailing garbage is rejected."""
        with pytest.raises(json.JSONDecodeError):
            y.deserialize('{"a": 1}garbage')


class TestPathologicalInputs:
    """Extreme and unusual inputs."""

    def test_deeply_nested_structure(self):
        """100 levels of nesting survives."""
        depth = 100
        obj = {'value': 'bottom'}
        for _ in range(depth):
            obj = {'nested': obj}
        data = {'task_id': 'test', 'result': 'success', 'output': obj}
        restored = y.deserialize(y.serialize(data))
        # Traverse to bottom
        current = restored['output']
        for _ in range(depth):
            current = current['nested']
        assert current['value'] == 'bottom'

    def test_very_deep_nesting_may_fail(self):
        """Extremely deep nesting exceeding MAX_DEPTH raises CanonError."""
        from knurl.canon import CanonError

        depth = 600  # Exceeds MAX_DEPTH (500)
        obj = {'value': 'bottom'}
        for _ in range(depth):
            obj = {'nested': obj}
        data = {'task_id': 'test', 'result': 'success', 'output': obj}
        # Raises CanonError due to depth limit
        with pytest.raises(CanonError, match="Maximum nesting depth"):
            y.serialize(data)

    def test_many_keys_dictionary(self):
        """Dict with 10000 keys."""
        many = {f'key_{i}': i for i in range(10000)}
        data = {'task_id': 'test', 'result': 'success', 'output': many}
        restored = y.deserialize(y.serialize(data))
        assert len(restored['output']) == 10000

    def test_control_characters_in_string(self):
        """Control characters survive round-trip."""
        data = {
            'task_id': 'test',
            'result': 'success',
            'output': '\x00\x01\x02\x03',
        }
        restored = y.deserialize(y.serialize(data))
        assert restored['output'] == '\x00\x01\x02\x03'

    def test_lone_surrogate_rejected(self):
        """Lone surrogate character causes encoding error."""
        # \ud800 is a lone high surrogate (invalid UTF-16)
        data = {'task_id': 'test', 'result': 'success', 'output': '\ud800'}
        with pytest.raises((UnicodeEncodeError, ValueError)):
            y.serialize(data)


class TestInjectionResistance:
    """Ensure injected JSON stays as string."""

    def test_json_in_string_stays_string(self):
        """JSON syntax in string values stays as string."""
        data = {
            'task_id': '{"injected": true}',
            'result': 'success',
            'output': '{"nested": "json"}'
        }
        restored = y.deserialize(y.serialize(data))
        assert isinstance(restored['task_id'], str)
        assert restored['task_id'] == '{"injected": true}'


class TestSummary:
    """Summary of discovered gaps."""

    def test_document_gaps(self):
        """Document all identified gaps in validation."""
        gaps = [
            "task_id accepts non-string types (int, list, dict, None, empty string)",
            "files field accepts non-list values",
            "metadata field accepts non-dict values",
            "error field accepts non-string values",
            "shard_name field accepts non-string values",
            "deserialize() returns non-dict for valid JSON arrays/primitives",
            "validate() and serialize() check different things",
            "get_task_id/get_shard_name return falsy values (0, '', False) differently than None",
        ]
        # This test always passes - it documents the gaps
        print("\n\nIDENTIFIED GAPS:")
        for gap in gaps:
            print(f"  • {gap}")
        assert True  # Documentation test
