"""Tests for validation gaps in yield_.py found by Round 1 hardening.

validate() only checks field presence and result membership, but doesn't
enforce types or check for meaningless values like empty strings or None.
"""

import pytest
from knurl.yield_ import validate, serialize, deserialize


class TestValidationTypeChecking:
    """validate() doesn't enforce types on required fields."""

    def test_none_task_id_passes_validation(self):
        """task_id=None passes validation but violates contract."""
        yield_data = {'task_id': None, 'result': 'success'}
        errors = validate(yield_data)

        # Bug: should reject None but doesn't
        assert len(errors) == 0

        # This will cause type errors downstream
        with pytest.raises(AttributeError):
            yield_data['task_id'].startswith('task_')

    def test_integer_task_id_passes_validation(self):
        """Integer task_id passes validation."""
        yield_data = {'task_id': 123, 'result': 'success'}
        errors = validate(yield_data)

        # Bug: should reject int but doesn't
        assert len(errors) == 0

    def test_list_task_id_passes_validation(self):
        """List task_id passes validation."""
        yield_data = {'task_id': ['a', 'b'], 'result': 'success'}
        errors = validate(yield_data)

        # Bug: should reject list but doesn't
        assert len(errors) == 0

    def test_dict_task_id_passes_validation(self):
        """Dict task_id passes validation."""
        yield_data = {'task_id': {'nested': 'value'}, 'result': 'success'}
        errors = validate(yield_data)

        # Bug: should reject dict but doesn't
        assert len(errors) == 0

    def test_integer_result_unclear_error(self):
        """Integer result gives unclear error message."""
        yield_data = {'task_id': 'test', 'result': 123}
        errors = validate(yield_data)

        assert len(errors) == 1
        # Error message says "Invalid result '123'" instead of "must be string"
        assert "123" in errors[0]


class TestValidationEmptyValues:
    """validate() accepts empty/whitespace strings."""

    def test_empty_string_task_id_passes(self):
        """Empty string task_id passes validation."""
        yield_data = {'task_id': '', 'result': 'success'}
        errors = validate(yield_data)

        # Bug: should reject empty string
        assert len(errors) == 0

    def test_whitespace_task_id_passes(self):
        """Whitespace-only task_id passes validation."""
        yield_data = {'task_id': '   ', 'result': 'success'}
        errors = validate(yield_data)

        # Bug: should reject whitespace
        assert len(errors) == 0

    def test_newline_task_id_passes(self):
        """task_id with just newline passes."""
        yield_data = {'task_id': '\n', 'result': 'success'}
        errors = validate(yield_data)

        # Bug: should reject
        assert len(errors) == 0


class TestValidationCaseSensitivity:
    """validate() should be case-sensitive for result values."""

    def test_capitalized_result_not_validated(self):
        """'Success' with capital S should be rejected."""
        yield_data = {'task_id': 'test', 'result': 'Success'}
        errors = validate(yield_data)

        # Correctly rejects (case-sensitive)
        assert len(errors) == 1
        assert 'Invalid result' in errors[0]

    def test_result_with_whitespace_not_validated(self):
        """' success ' with whitespace should be rejected."""
        yield_data = {'task_id': 'test', 'result': ' success '}
        errors = validate(yield_data)

        # Correctly rejects
        assert len(errors) == 1


class TestSerializationWithInvalidData:
    """serialize() doesn't call validate(), so invalid data serializes."""

    def test_serialize_none_task_id_succeeds(self):
        """Can serialize yield with None task_id."""
        yield_data = {'task_id': None, 'result': 'success'}

        # Bug: validate() not called, so this works
        serialized = serialize(yield_data)
        assert serialized is not None

        # Round-trip works
        result = deserialize(serialized)
        assert result['task_id'] is None

    def test_serialize_integer_task_id_succeeds(self):
        """Can serialize yield with integer task_id."""
        yield_data = {'task_id': 123, 'result': 'success'}

        # Bug: validate() not called
        serialized = serialize(yield_data)
        result = deserialize(serialized)
        assert result['task_id'] == 123

    def test_serialize_empty_task_id_succeeds(self):
        """Can serialize yield with empty task_id."""
        yield_data = {'task_id': '', 'result': 'success'}

        # Bug: validate() not called
        serialized = serialize(yield_data)
        result = deserialize(serialized)
        assert result['task_id'] == ''


class TestUnicodeEdgeCases:
    """Unicode edge cases from Oracle review."""

    def test_unicode_normalization_not_applied(self):
        """Different unicode forms produce different hashes."""
        import unicodedata

        # NFC: single codepoint é
        nfc = {'task_id': 'café', 'result': 'success'}

        # NFD: e + combining accent
        nfd = {'task_id': unicodedata.normalize('NFD', 'café'), 'result': 'success'}

        # Both pass validation
        assert validate(nfc) == []
        assert validate(nfd) == []

        # But serialize differently
        assert serialize(nfc) != serialize(nfd)

    def test_zero_width_characters_in_task_id(self):
        """Zero-width characters are allowed."""
        yield_data = {'task_id': 'test\u200bdata', 'result': 'success'}

        # Passes validation
        assert validate(yield_data) == []

        # Can serialize
        serialized = serialize(yield_data)
        assert serialized is not None

    def test_homograph_attack_possible(self):
        """Cyrillic 'а' looks like Latin 'a' but different bytes."""
        latin = {'task_id': 'task_a', 'result': 'success'}
        cyrillic = {'task_id': 'task_а', 'result': 'success'}  # Cyrillic а

        # Both pass validation
        assert validate(latin) == []
        assert validate(cyrillic) == []

        # But are different
        assert serialize(latin) != serialize(cyrillic)
