"""Round 3: Crash bugs with None/invalid inputs and serialization failures."""

import pytest
from knurl.yield_ import serialize, validate, deserialize
from knurl.canon import CanonError


class TestNoneInputCrashes:
    """Functions crash when given None instead of dict."""

    def test_validate_none_crashes(self):
        """validate(None) crashes instead of returning errors."""
        with pytest.raises(TypeError):
            validate(None)

    def test_validate_string_doesnt_crash_but_returns_errors(self):
        """validate('string') doesn't crash, returns errors."""
        errors = validate("string")

        # Doesn't crash, but returns errors
        assert len(errors) > 0

    def test_serialize_none_doesnt_crash(self):
        """serialize(None) doesn't crash - canon handles it."""
        result = serialize(None)
        assert result == "null"


class TestCircularReferences:
    """Circular references cause CanonError."""

    def test_circular_reference_in_output_crashes(self):
        """Circular reference in output field crashes."""
        data = {'task_id': 'test', 'result': 'success', 'output': {}}
        data['output']['circular'] = data['output']

        with pytest.raises(CanonError):
            serialize(data)

    def test_self_referencing_yield_data_crashes(self):
        """Yield data referencing itself crashes."""
        data = {'task_id': 'test', 'result': 'success'}
        data['self'] = data

        with pytest.raises(CanonError):
            serialize(data)


class TestMalformedJSON:
    """deserialize() crashes on malformed JSON."""

    def test_deserialize_empty_string_crashes(self):
        """Empty string is not valid JSON."""
        with pytest.raises(Exception):  # JSONDecodeError
            deserialize("")

    def test_deserialize_invalid_json_crashes(self):
        """Malformed JSON crashes."""
        with pytest.raises(Exception):
            deserialize("{invalid json")

    def test_deserialize_trailing_comma_crashes(self):
        """JSON with trailing comma crashes."""
        with pytest.raises(Exception):
            deserialize('{"task_id": "test",}')


class TestNonSerializableTypes:
    """Non-JSON-serializable types in yield_data."""

    def test_function_in_output_crashes(self):
        """Function object in output field crashes."""
        def my_func():
            pass

        data = {'task_id': 'test', 'result': 'success', 'output': my_func}

        with pytest.raises((TypeError, CanonError)):
            serialize(data)

    def test_bytes_in_output_crashes(self):
        """Bytes object in output field crashes."""
        data = {'task_id': 'test', 'result': 'success', 'output': b'bytes'}

        with pytest.raises((TypeError, CanonError)):
            serialize(data)

    def test_set_in_metadata_crashes(self):
        """Set in metadata crashes - sets not JSON serializable."""
        data = {
            'task_id': 'test',
            'result': 'success',
            'metadata': {'tags': {1, 2, 3}}
        }

        # Sets crash during serialization
        with pytest.raises(TypeError):
            serialize(data)
