"""Round 2 bugs found by Gremlin/Oracle via horizon cast --async.

These are NEW bugs beyond the validation gaps from Round 1.
"""

import pytest
from knurl.yield_ import deserialize, serialize, validate


class TestDeserializeTypeViolations:
    """deserialize() returns non-dict types, violating return type hint."""

    def test_deserialize_array_returns_list(self):
        """Deserializing JSON array returns list, not dict."""
        result = deserialize('[]')

        # Bug: returns list instead of dict
        assert isinstance(result, list)
        assert result == []

        # This breaks downstream code expecting dict
        with pytest.raises(TypeError):
            result['task_id']  # Can't index list with string

    def test_deserialize_null_returns_none(self):
        """Deserializing null returns None, not dict."""
        result = deserialize('null')

        # Bug: returns None instead of dict
        assert result is None

        # This breaks downstream code
        with pytest.raises(TypeError):
            result['task_id']

    def test_deserialize_string_returns_string(self):
        """Deserializing JSON string returns string, not dict."""
        result = deserialize('"hello"')

        # Bug: returns string instead of dict
        assert isinstance(result, str)
        assert result == "hello"

        # This breaks downstream code
        with pytest.raises(TypeError):
            result['task_id']

    def test_deserialize_number_returns_number(self):
        """Deserializing JSON number returns int/float, not dict."""
        result = deserialize('42')

        # Bug: returns int instead of dict
        assert isinstance(result, int)
        assert result == 42

        # This breaks downstream code
        with pytest.raises(TypeError):
            result['task_id']


class TestOptionalFieldTypeConfusion:
    """Optional fields (files, metadata) don't validate types."""

    def test_files_as_string_passes_validation(self):
        """files field can be string instead of list."""
        yield_data = {
            'task_id': 'test',
            'result': 'success',
            'files': '/etc/passwd'  # Should be list, not string
        }

        errors = validate(yield_data)

        # Bug: no type validation on optional fields
        assert len(errors) == 0

    def test_files_as_dict_passes_validation(self):
        """files field can be dict instead of list."""
        yield_data = {
            'task_id': 'test',
            'result': 'success',
            'files': {'malicious': 'data'}
        }

        errors = validate(yield_data)
        assert len(errors) == 0

    def test_metadata_as_string_passes_validation(self):
        """metadata field can be string instead of dict."""
        yield_data = {
            'task_id': 'test',
            'result': 'success',
            'metadata': 'injected_string'  # Should be dict
        }

        errors = validate(yield_data)
        assert len(errors) == 0

    def test_metadata_as_list_passes_validation(self):
        """metadata field can be list instead of dict."""
        yield_data = {
            'task_id': 'test',
            'result': 'success',
            'metadata': [1, 2, 3]
        }

        errors = validate(yield_data)
        assert len(errors) == 0


class TestSerializeNoValidation:
    """serialize() doesn't call validate(), so invalid data serializes."""

    def test_serialize_invalid_result_value(self):
        """Can serialize yield with invalid result value."""
        yield_data = {
            'task_id': 'test',
            'result': 'maybe'  # Invalid result value
        }

        # Bug: validate() not called, so invalid data serializes
        serialized = serialize(yield_data)
        assert serialized is not None

        # Round-trip preserves invalid data
        deserialized = deserialize(serialized)
        assert deserialized['result'] == 'maybe'

    def test_serialize_missing_required_fields(self):
        """Can serialize yield missing required fields."""
        yield_data = {'output': 'data'}  # Missing task_id and result

        # Bug: no validation before serialization
        serialized = serialize(yield_data)
        assert serialized is not None

        deserialized = deserialize(serialized)
        assert 'task_id' not in deserialized
        assert 'result' not in deserialized


class TestSemanticInconsistency:
    """No consistency checks between related fields."""

    def test_result_error_without_error_field_passes(self):
        """result='failed' without error field passes validation."""
        yield_data = {
            'task_id': 'test',
            'result': 'failed'  # Should require 'error' field
        }

        errors = validate(yield_data)

        # Bug: no semantic validation
        assert len(errors) == 0

    def test_result_skipped_with_output_passes(self):
        """result='skipped' with output data passes (semantically odd)."""
        yield_data = {
            'task_id': 'test',
            'result': 'skipped',
            'output': 'detailed output data'  # Why output if skipped?
        }

        errors = validate(yield_data)
        assert len(errors) == 0


class TestGetTaskIdReturnType:
    """get_task_id() return type doesn't match type hint."""

    def test_get_task_id_returns_non_string(self):
        """get_task_id() can return list/dict/int instead of str|None."""
        from knurl.yield_ import get_task_id

        # Type hint says str | None, but actually returns Any
        result = get_task_id({'task_id': [1, 2, 3], 'result': 'success'})

        # Bug: returns list instead of str|None
        assert isinstance(result, list)
        assert result == [1, 2, 3]

    def test_get_task_id_with_dict_task_id(self):
        """get_task_id() returns dict when task_id is dict."""
        from knurl.yield_ import get_task_id

        result = get_task_id({'task_id': {'nested': 'value'}, 'result': 'success'})

        # Bug: returns dict instead of str|None
        assert isinstance(result, dict)
