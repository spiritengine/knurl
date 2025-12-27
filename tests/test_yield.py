"""
Comprehensive test suite for ledger.yield_ - Yield Serialization.

This module tests serialization and deserialization of step yields (outputs)
for storage and resumption. Yields are passed between chain steps and must
survive storage/retrieval with perfect fidelity.

Note: Module is named yield_.py since 'yield' is a Python reserved word.

Test Categories:
1. Serialization - Round-trip, all fields, determinism
2. Output Types - String, dict, list, nested, None, large outputs
3. Validation - Required fields, valid values, type checking
4. Extractors - get_task_id, get_shard_name helpers
5. Edge Cases - Empty yields, unicode, circular references
6. Error Handling - Clear error messages for invalid inputs
"""

import json
from typing import Any

import pytest


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================

@pytest.fixture
def serialize():
    """Import serialize function."""
    from spiritengine.yield_ import serialize
    return serialize


@pytest.fixture
def deserialize():
    """Import deserialize function."""
    from spiritengine.yield_ import deserialize
    return deserialize


@pytest.fixture
def validate():
    """Import validate function."""
    from spiritengine.yield_ import validate
    return validate


@pytest.fixture
def get_task_id():
    """Import get_task_id function."""
    from spiritengine.yield_ import get_task_id
    return get_task_id


@pytest.fixture
def get_shard_name():
    """Import get_shard_name function."""
    from spiritengine.yield_ import get_shard_name
    return get_shard_name


def minimal_yield() -> dict:
    """Return a minimal valid yield with only required fields."""
    return {
        'task_id': 'test_001',
        'result': 'success',
    }


def full_yield() -> dict:
    """Return a yield with all standard fields."""
    return {
        'task_id': 'beadle_001',
        'result': 'success',
        'output': {'files_created': ['a.txt', 'b.txt']},
        'error': None,
        'shard_name': 'shard-abc123',
        'files': ['a.txt', 'b.txt'],
        'metadata': {'duration_ms': 1234, 'retries': 0},
    }


# =============================================================================
# TestSerialization - Basic round-trip serialization
# =============================================================================

class TestSerialization:
    """Tests for serialize/deserialize round-trip behavior."""

    def test_simple_roundtrip(self, serialize, deserialize):
        """Minimal yield round-trips correctly."""
        original = minimal_yield()
        serialized = serialize(original)
        restored = deserialize(serialized)
        assert restored == original

    def test_all_fields_roundtrip(self, serialize, deserialize):
        """Full yield with all fields round-trips correctly."""
        original = full_yield()
        serialized = serialize(original)
        restored = deserialize(serialized)
        assert restored == original

    def test_optional_fields_missing(self, serialize, deserialize):
        """Yield with missing optional fields round-trips correctly."""
        original = {
            'task_id': 'task_123',
            'result': 'failed',
            'error': 'Something went wrong',
        }
        serialized = serialize(original)
        restored = deserialize(serialized)
        assert restored == original

    def test_serialize_returns_string(self, serialize):
        """Serialize returns a string (not bytes)."""
        result = serialize(minimal_yield())
        assert isinstance(result, str)

    def test_serialize_is_json(self, serialize):
        """Serialized output is valid JSON."""
        result = serialize(full_yield())
        # Should not raise
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_deterministic_output(self, serialize):
        """Multiple serialize calls produce identical output."""
        original = full_yield()
        results = [serialize(original) for _ in range(10)]
        assert len(set(results)) == 1, "All results should be identical"

    def test_different_dict_order_same_output(self, serialize):
        """Dict with same content but different insertion order → same output."""
        yield1 = {'task_id': 'a', 'result': 'success', 'output': 'x'}
        yield2 = {'result': 'success', 'output': 'x', 'task_id': 'a'}
        yield3 = {'output': 'x', 'task_id': 'a', 'result': 'success'}

        assert serialize(yield1) == serialize(yield2) == serialize(yield3)


# =============================================================================
# TestOutputTypes - Various output field types
# =============================================================================

class TestOutputTypes:
    """Tests for different types of output field values."""

    def test_string_output(self, serialize, deserialize):
        """String output round-trips correctly."""
        original = {
            'task_id': 'task_1',
            'result': 'success',
            'output': 'Hello, world!',
        }
        restored = deserialize(serialize(original))
        assert restored['output'] == 'Hello, world!'

    def test_dict_output(self, serialize, deserialize):
        """Dict output round-trips correctly."""
        original = {
            'task_id': 'task_1',
            'result': 'success',
            'output': {'key': 'value', 'nested': {'a': 1, 'b': 2}},
        }
        restored = deserialize(serialize(original))
        assert restored['output'] == {'key': 'value', 'nested': {'a': 1, 'b': 2}}

    def test_list_output(self, serialize, deserialize):
        """List output round-trips correctly."""
        original = {
            'task_id': 'task_1',
            'result': 'success',
            'output': [1, 2, 3, 'four', None],
        }
        restored = deserialize(serialize(original))
        assert restored['output'] == [1, 2, 3, 'four', None]

    def test_nested_output(self, serialize, deserialize):
        """Deeply nested output round-trips correctly."""
        original = {
            'task_id': 'task_1',
            'result': 'success',
            'output': {
                'level1': {
                    'level2': {
                        'level3': [{'deep': True}]
                    }
                }
            },
        }
        restored = deserialize(serialize(original))
        assert restored['output']['level1']['level2']['level3'][0]['deep'] is True

    def test_none_output(self, serialize, deserialize):
        """None output round-trips correctly."""
        original = {
            'task_id': 'task_1',
            'result': 'success',
            'output': None,
        }
        restored = deserialize(serialize(original))
        assert restored['output'] is None

    def test_empty_output(self, serialize, deserialize):
        """Empty dict and list outputs round-trip correctly."""
        for empty_val in [{}, []]:
            original = {
                'task_id': 'task_1',
                'result': 'success',
                'output': empty_val,
            }
            restored = deserialize(serialize(original))
            assert restored['output'] == empty_val

    def test_boolean_output(self, serialize, deserialize):
        """Boolean output round-trips correctly."""
        original = {
            'task_id': 'task_1',
            'result': 'success',
            'output': True,
        }
        restored = deserialize(serialize(original))
        assert restored['output'] is True

    def test_integer_output(self, serialize, deserialize):
        """Integer output round-trips correctly."""
        original = {
            'task_id': 'task_1',
            'result': 'success',
            'output': 42,
        }
        restored = deserialize(serialize(original))
        assert restored['output'] == 42

    def test_float_output(self, serialize, deserialize):
        """Float output round-trips correctly."""
        original = {
            'task_id': 'task_1',
            'result': 'success',
            'output': 3.14159,
        }
        restored = deserialize(serialize(original))
        assert abs(restored['output'] - 3.14159) < 1e-10

    def test_large_output(self, serialize, deserialize):
        """Large output (1MB+) round-trips correctly."""
        # Create ~1MB string
        large_string = 'x' * (1024 * 1024)
        original = {
            'task_id': 'task_1',
            'result': 'success',
            'output': large_string,
        }
        restored = deserialize(serialize(original))
        assert restored['output'] == large_string
        assert len(restored['output']) == 1024 * 1024

    def test_large_nested_output(self, serialize, deserialize):
        """Large nested structure round-trips correctly."""
        # Many keys
        large_dict = {f'key_{i}': i for i in range(1000)}
        original = {
            'task_id': 'task_1',
            'result': 'success',
            'output': large_dict,
        }
        restored = deserialize(serialize(original))
        assert restored['output'] == large_dict


# =============================================================================
# TestValidation - Required fields and valid values
# =============================================================================

class TestValidation:
    """Tests for validate() function."""

    def test_valid_yield_no_errors(self, validate):
        """Valid yield returns empty error list."""
        errors = validate(minimal_yield())
        assert errors == []

    def test_full_yield_no_errors(self, validate):
        """Full valid yield returns empty error list."""
        errors = validate(full_yield())
        assert errors == []

    def test_missing_task_id(self, validate):
        """Missing task_id is detected."""
        yield_data = {'result': 'success'}
        errors = validate(yield_data)
        assert len(errors) == 1
        assert 'task_id' in errors[0].lower()

    def test_missing_result(self, validate):
        """Missing result is detected."""
        yield_data = {'task_id': 'test_001'}
        errors = validate(yield_data)
        assert len(errors) == 1
        assert 'result' in errors[0].lower()

    def test_missing_both_required(self, validate):
        """Missing both required fields detected."""
        yield_data = {'output': 'something'}
        errors = validate(yield_data)
        assert len(errors) == 2

    def test_invalid_result_value(self, validate):
        """Invalid result value is detected."""
        yield_data = {
            'task_id': 'test_001',
            'result': 'maybe',  # Invalid - must be success/failed/skipped
        }
        errors = validate(yield_data)
        assert len(errors) == 1
        assert 'result' in errors[0].lower() or 'invalid' in errors[0].lower()

    def test_valid_result_success(self, validate):
        """'success' is a valid result."""
        yield_data = {'task_id': 'test_001', 'result': 'success'}
        errors = validate(yield_data)
        assert errors == []

    def test_valid_result_failed(self, validate):
        """'failed' is a valid result."""
        yield_data = {'task_id': 'test_001', 'result': 'failed'}
        errors = validate(yield_data)
        assert errors == []

    def test_valid_result_skipped(self, validate):
        """'skipped' is a valid result."""
        yield_data = {'task_id': 'test_001', 'result': 'skipped'}
        errors = validate(yield_data)
        assert errors == []

    def test_empty_dict(self, validate):
        """Empty dict has both required field errors."""
        errors = validate({})
        assert len(errors) == 2

    def test_extra_fields_allowed(self, validate):
        """Extra fields beyond standard set are allowed."""
        yield_data = {
            'task_id': 'test_001',
            'result': 'success',
            'custom_field': 'custom_value',
            'another_extra': [1, 2, 3],
        }
        errors = validate(yield_data)
        assert errors == []


# =============================================================================
# TestExtractors - get_task_id and get_shard_name helpers
# =============================================================================

class TestExtractors:
    """Tests for helper extraction functions."""

    def test_get_task_id(self, get_task_id):
        """get_task_id extracts task_id correctly."""
        yield_data = {'task_id': 'beadle_001', 'result': 'success'}
        assert get_task_id(yield_data) == 'beadle_001'

    def test_get_task_id_missing(self, get_task_id):
        """get_task_id returns None when task_id missing."""
        yield_data = {'result': 'success'}
        assert get_task_id(yield_data) is None

    def test_get_shard_name_present(self, get_shard_name):
        """get_shard_name extracts shard_name when present."""
        yield_data = {
            'task_id': 'test_001',
            'result': 'success',
            'shard_name': 'shard-xyz789',
        }
        assert get_shard_name(yield_data) == 'shard-xyz789'

    def test_get_shard_name_absent(self, get_shard_name):
        """get_shard_name returns None when shard_name absent."""
        yield_data = {'task_id': 'test_001', 'result': 'success'}
        assert get_shard_name(yield_data) is None

    def test_get_shard_name_none_value(self, get_shard_name):
        """get_shard_name returns None when shard_name is explicitly None."""
        yield_data = {
            'task_id': 'test_001',
            'result': 'success',
            'shard_name': None,
        }
        assert get_shard_name(yield_data) is None

    def test_get_task_id_empty_dict(self, get_task_id):
        """get_task_id handles empty dict gracefully."""
        assert get_task_id({}) is None

    def test_get_shard_name_empty_dict(self, get_shard_name):
        """get_shard_name handles empty dict gracefully."""
        assert get_shard_name({}) is None


# =============================================================================
# TestEdgeCases - Unusual inputs and boundary conditions
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and unusual inputs."""

    def test_unicode_in_task_id(self, serialize, deserialize):
        """Unicode characters in task_id round-trip correctly."""
        original = {
            'task_id': 'タスク_001',  # Japanese
            'result': 'success',
        }
        restored = deserialize(serialize(original))
        assert restored['task_id'] == 'タスク_001'

    def test_unicode_in_output(self, serialize, deserialize):
        """Unicode characters in output round-trip correctly."""
        original = {
            'task_id': 'test_001',
            'result': 'success',
            'output': '日本語テスト 🎉 émojis',
        }
        restored = deserialize(serialize(original))
        assert restored['output'] == '日本語テスト 🎉 émojis'

    def test_emoji_in_all_fields(self, serialize, deserialize):
        """Emoji in various fields round-trip correctly."""
        original = {
            'task_id': 'task_🚀_001',
            'result': 'success',
            'output': '✅ Done',
            'error': None,
            'metadata': {'status_emoji': '🎯'},
        }
        restored = deserialize(serialize(original))
        assert restored == original

    def test_very_long_task_id(self, serialize, deserialize):
        """Very long task_id round-trips correctly."""
        long_id = 'a' * 10000
        original = {
            'task_id': long_id,
            'result': 'success',
        }
        restored = deserialize(serialize(original))
        assert restored['task_id'] == long_id

    def test_very_long_error_message(self, serialize, deserialize):
        """Very long error message round-trips correctly."""
        long_error = 'Error: ' + ('x' * 100000)
        original = {
            'task_id': 'test_001',
            'result': 'failed',
            'error': long_error,
        }
        restored = deserialize(serialize(original))
        assert restored['error'] == long_error

    def test_newlines_in_output(self, serialize, deserialize):
        """Newlines in output round-trip correctly."""
        original = {
            'task_id': 'test_001',
            'result': 'success',
            'output': 'line1\nline2\nline3',
        }
        restored = deserialize(serialize(original))
        assert restored['output'] == 'line1\nline2\nline3'

    def test_special_characters_in_output(self, serialize, deserialize):
        """Special characters round-trip correctly."""
        original = {
            'task_id': 'test_001',
            'result': 'success',
            'output': 'tab:\there\nquote:"test"\nbackslash:\\path',
        }
        restored = deserialize(serialize(original))
        assert restored['output'] == 'tab:\there\nquote:"test"\nbackslash:\\path'

    def test_empty_files_list(self, serialize, deserialize):
        """Empty files list round-trips correctly."""
        original = {
            'task_id': 'test_001',
            'result': 'success',
            'files': [],
        }
        restored = deserialize(serialize(original))
        assert restored['files'] == []

    def test_many_files(self, serialize, deserialize):
        """Many files in list round-trip correctly."""
        original = {
            'task_id': 'test_001',
            'result': 'success',
            'files': [f'/path/to/file_{i}.txt' for i in range(1000)],
        }
        restored = deserialize(serialize(original))
        assert len(restored['files']) == 1000
        assert restored['files'][500] == '/path/to/file_500.txt'

    def test_empty_metadata(self, serialize, deserialize):
        """Empty metadata dict round-trips correctly."""
        original = {
            'task_id': 'test_001',
            'result': 'success',
            'metadata': {},
        }
        restored = deserialize(serialize(original))
        assert restored['metadata'] == {}

    def test_complex_metadata(self, serialize, deserialize):
        """Complex nested metadata round-trips correctly."""
        original = {
            'task_id': 'test_001',
            'result': 'success',
            'metadata': {
                'timing': {'start': 1234567890, 'end': 1234567900},
                'resources': {'memory_mb': 512, 'cpu_percent': 45.5},
                'tags': ['production', 'critical'],
            },
        }
        restored = deserialize(serialize(original))
        assert restored['metadata'] == original['metadata']


# =============================================================================
# TestCircularReferences - Should error on circular refs
# =============================================================================

class TestCircularReferences:
    """Tests for circular reference handling."""

    def test_circular_reference_in_output_errors(self, serialize):
        """Circular reference in output raises error."""
        from spiritengine.canon import CanonError

        circular = {'a': 1}
        circular['self'] = circular

        yield_data = {
            'task_id': 'test_001',
            'result': 'success',
            'output': circular,
        }

        with pytest.raises((CanonError, ValueError, RecursionError)):
            serialize(yield_data)

    def test_circular_reference_in_metadata_errors(self, serialize):
        """Circular reference in metadata raises error."""
        from spiritengine.canon import CanonError

        circular = [1, 2, 3]
        circular.append(circular)

        yield_data = {
            'task_id': 'test_001',
            'result': 'success',
            'metadata': {'data': circular},
        }

        with pytest.raises((CanonError, ValueError, RecursionError)):
            serialize(yield_data)


# =============================================================================
# TestDeserializationErrors - Invalid JSON handling
# =============================================================================

class TestDeserializationErrors:
    """Tests for deserialization error handling."""

    def test_invalid_json_raises_error(self, deserialize):
        """Invalid JSON string raises error."""
        with pytest.raises(json.JSONDecodeError):
            deserialize("not valid json")

    def test_empty_string_raises_error(self, deserialize):
        """Empty string raises error."""
        with pytest.raises(json.JSONDecodeError):
            deserialize("")

    def test_valid_json_non_dict_returns_as_is(self, deserialize):
        """Valid JSON that's not a dict is returned as-is."""
        # This is an edge case - deserialize just parses JSON
        # Validation would catch non-dict yields
        result = deserialize('"just a string"')
        assert result == "just a string"


# =============================================================================
# TestIntegration - Real-world usage patterns
# =============================================================================

class TestIntegration:
    """Tests for realistic usage patterns."""

    def test_successful_task_yield(self, serialize, deserialize, validate):
        """Typical successful task yield."""
        yield_data = {
            'task_id': 'beadle_001',
            'result': 'success',
            'output': {
                'files_created': ['output.txt', 'log.txt'],
                'records_processed': 1000,
            },
            'files': ['output.txt', 'log.txt'],
            'metadata': {
                'duration_ms': 5432,
                'memory_peak_mb': 128,
            },
        }

        # Validate
        errors = validate(yield_data)
        assert errors == []

        # Round-trip
        restored = deserialize(serialize(yield_data))
        assert restored == yield_data

    def test_failed_task_yield(self, serialize, deserialize, validate):
        """Typical failed task yield with error."""
        yield_data = {
            'task_id': 'beadle_002',
            'result': 'failed',
            'error': 'Connection timeout after 30s',
            'output': None,
            'metadata': {
                'retries': 3,
                'last_error': 'ETIMEDOUT',
            },
        }

        errors = validate(yield_data)
        assert errors == []

        restored = deserialize(serialize(yield_data))
        assert restored == yield_data

    def test_skipped_task_yield(self, serialize, deserialize, validate):
        """Typical skipped task yield."""
        yield_data = {
            'task_id': 'beadle_003',
            'result': 'skipped',
            'output': 'Cache hit - no work needed',
            'metadata': {
                'skip_reason': 'cache_hit',
                'cache_key': 'abc123def456',
            },
        }

        errors = validate(yield_data)
        assert errors == []

        restored = deserialize(serialize(yield_data))
        assert restored == yield_data

    def test_shard_task_yield(self, serialize, deserialize, validate, get_shard_name):
        """Task that ran in a shard."""
        yield_data = {
            'task_id': 'shard_task_001',
            'result': 'success',
            'shard_name': 'shard-7bb5e657-20251210-001',
            'output': {'commit': 'abc123'},
            'files': ['src/feature.py', 'tests/test_feature.py'],
        }

        errors = validate(yield_data)
        assert errors == []

        assert get_shard_name(yield_data) == 'shard-7bb5e657-20251210-001'

        restored = deserialize(serialize(yield_data))
        assert restored == yield_data


# =============================================================================
# Property-Based Tests with Hypothesis
# =============================================================================

try:
    from hypothesis import given, strategies as st, settings, assume
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False

    def given(*args, **kwargs):
        return lambda f: f

    def settings(*args, **kwargs):
        return lambda f: f

    def assume(x):
        pass

    class _DummyStrategy:
        def __or__(self, other):
            return self

    class st:
        @staticmethod
        def text(**kwargs):
            return _DummyStrategy()

        @staticmethod
        def sampled_from(values):
            return _DummyStrategy()

        @staticmethod
        def dictionaries(k, v):
            return _DummyStrategy()

        @staticmethod
        def none():
            return _DummyStrategy()


@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="Hypothesis not installed")
class TestHypothesis:
    """Property-based tests using Hypothesis."""

    @given(
        task_id=st.text(min_size=1),
        result=st.sampled_from(['success', 'failed', 'skipped']),
    )
    def test_any_valid_yield_roundtrips(self, task_id, result):
        """Any valid yield round-trips correctly."""
        from spiritengine.yield_ import serialize, deserialize

        # Skip strings that can't be UTF-8 encoded
        try:
            task_id.encode('utf-8')
        except UnicodeEncodeError:
            assume(False)

        yield_data = {'task_id': task_id, 'result': result}
        restored = deserialize(serialize(yield_data))
        assert restored == yield_data

    @given(
        task_id=st.text(min_size=1),
        result=st.sampled_from(['success', 'failed', 'skipped']),
    )
    @settings(max_examples=50)
    def test_validation_accepts_valid_yields(self, task_id, result):
        """Validation accepts any structurally valid yield."""
        from spiritengine.yield_ import validate

        try:
            task_id.encode('utf-8')
        except UnicodeEncodeError:
            assume(False)

        yield_data = {'task_id': task_id, 'result': result}
        errors = validate(yield_data)
        assert errors == []
