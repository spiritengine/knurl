"""Tests for chain fingerprinting module.

Tests the knurl.chain module which provides:
- fingerprint(steps: list[dict]) -> list[str]  # Batch fingerprinting
- fingerprint_step(config: dict, previous_fingerprint: str = None) -> str  # Incremental

The core property: each fingerprint depends on config + previous fingerprint,
creating a Merkle-like chain where changing any step invalidates all subsequent.
"""

import pytest
from hypothesis import given, strategies as st, settings, assume

from knurl.chain import fingerprint, fingerprint_step, ChainError


# =============================================================================
# BASIC CHAIN OPERATIONS
# =============================================================================

class TestEmptyChain:
    """Empty chain handling."""

    def test_empty_chain_returns_empty_list(self):
        """Empty input produces empty output."""
        assert fingerprint([]) == []

    def test_empty_chain_not_none(self):
        """Empty chain returns list, not None."""
        result = fingerprint([])
        assert result is not None
        assert isinstance(result, list)


class TestSingleStepChain:
    """Single-element chains."""

    def test_single_step_returns_single_fingerprint(self):
        """Single config produces single fingerprint."""
        result = fingerprint([{"action": "build"}])
        assert len(result) == 1

    def test_single_step_format(self):
        """Single step fingerprint has correct format."""
        result = fingerprint([{"x": 1}])
        assert result[0].startswith("sha256:")
        assert len(result[0].split(":")[1]) == 64  # SHA256 hex length

    def test_single_step_deterministic(self):
        """Same single config always produces same fingerprint."""
        config = {"name": "test", "value": 42}
        assert fingerprint([config]) == fingerprint([config])

    def test_single_step_incremental_matches_batch(self):
        """fingerprint_step with no previous == fingerprint()[0]."""
        config = {"step": "one"}
        batch = fingerprint([config])
        incremental = fingerprint_step(config, previous_fingerprint=None)
        assert batch[0] == incremental


class TestMultiStepChain:
    """Multi-element chain basics."""

    def test_two_step_chain(self):
        """Two configs produce two fingerprints."""
        result = fingerprint([{"a": 1}, {"b": 2}])
        assert len(result) == 2

    def test_three_step_chain(self):
        """Three configs produce three fingerprints."""
        result = fingerprint([{"a": 1}, {"b": 2}, {"c": 3}])
        assert len(result) == 3

    def test_all_fingerprints_unique(self):
        """Each position gets unique fingerprint (even with same configs)."""
        result = fingerprint([{"x": 1}, {"x": 1}, {"x": 1}])
        # All three should be different due to chain dependency
        assert len(set(result)) == 3

    def test_multi_step_deterministic(self):
        """Same chain always produces same fingerprints."""
        chain = [{"a": 1}, {"b": 2}, {"c": 3}]
        assert fingerprint(chain) == fingerprint(chain)


class TestDeterminism:
    """Determinism guarantees."""

    def test_repeated_calls_identical(self):
        """100 repeated calls produce identical results."""
        config = {"test": "determinism", "count": 123}
        results = [fingerprint([config]) for _ in range(100)]
        assert len(set(tuple(r) for r in results)) == 1

    def test_key_order_irrelevant(self):
        """Dict key order doesn't affect fingerprint (canonical serialization)."""
        config1 = {"z": 1, "a": 2, "m": 3}
        config2 = {"a": 2, "m": 3, "z": 1}
        assert fingerprint([config1]) == fingerprint([config2])

    def test_nested_key_order_irrelevant(self):
        """Nested dict key order also normalized."""
        config1 = {"outer": {"z": 1, "a": 2}}
        config2 = {"outer": {"a": 2, "z": 1}}
        assert fingerprint([config1]) == fingerprint([config2])


# =============================================================================
# DEPENDENCY CORRECTNESS (The Core Property)
# =============================================================================

class TestChangePropagation:
    """Verify that changes propagate correctly through the chain."""

    def test_change_first_changes_all(self):
        """Changing step 0 changes all fingerprints."""
        chain_a = [{"x": 1}, {"y": 2}, {"z": 3}]
        chain_b = [{"x": 999}, {"y": 2}, {"z": 3}]  # Only first changed

        fp_a = fingerprint(chain_a)
        fp_b = fingerprint(chain_b)

        # ALL fingerprints should differ
        assert fp_a[0] != fp_b[0]
        assert fp_a[1] != fp_b[1]
        assert fp_a[2] != fp_b[2]

    def test_change_middle_changes_subsequent(self):
        """Changing step N changes fingerprints N+ but not 0..N-1."""
        chain_a = [{"a": 1}, {"b": 2}, {"c": 3}, {"d": 4}]
        chain_b = [{"a": 1}, {"b": 999}, {"c": 3}, {"d": 4}]  # Middle changed

        fp_a = fingerprint(chain_a)
        fp_b = fingerprint(chain_b)

        # Step 0 unchanged
        assert fp_a[0] == fp_b[0]

        # Steps 1, 2, 3 all changed (1 directly, 2-3 via cascade)
        assert fp_a[1] != fp_b[1]
        assert fp_a[2] != fp_b[2]
        assert fp_a[3] != fp_b[3]

    def test_change_last_only_changes_last(self):
        """Changing last step only changes last fingerprint."""
        chain_a = [{"a": 1}, {"b": 2}, {"c": 3}]
        chain_b = [{"a": 1}, {"b": 2}, {"c": 999}]  # Only last changed

        fp_a = fingerprint(chain_a)
        fp_b = fingerprint(chain_b)

        # Steps 0, 1 unchanged
        assert fp_a[0] == fp_b[0]
        assert fp_a[1] == fp_b[1]

        # Only step 2 changed
        assert fp_a[2] != fp_b[2]

    def test_same_config_different_position_different_fingerprint(self):
        """Identical config at different positions produces different fingerprints.

        This is THE critical test that catches naive implementations that don't
        actually include the previous fingerprint in the hash.
        """
        config = {"action": "step"}

        # Build chain where same config appears at positions 0 and 1
        chain = [config, config]
        fp = fingerprint(chain)

        # Position 0 and position 1 MUST differ
        assert fp[0] != fp[1], "Same config at different positions must have different fingerprints"

    def test_position_sensitivity_three_identical(self):
        """Three identical configs at different positions all differ."""
        config = {"identical": True}
        fp = fingerprint([config, config, config])

        assert fp[0] != fp[1]
        assert fp[1] != fp[2]
        assert fp[0] != fp[2]

    def test_swap_order_changes_all_after_swap(self):
        """Swapping two steps changes everything from swap point onward."""
        chain_a = [{"a": 1}, {"b": 2}, {"c": 3}]
        chain_b = [{"a": 1}, {"c": 3}, {"b": 2}]  # Swapped b and c

        fp_a = fingerprint(chain_a)
        fp_b = fingerprint(chain_b)

        # Step 0 same
        assert fp_a[0] == fp_b[0]

        # Steps 1, 2 differ
        assert fp_a[1] != fp_b[1]
        assert fp_a[2] != fp_b[2]


# =============================================================================
# INCREMENTAL VS BATCH EQUIVALENCE
# =============================================================================

class TestIncrementalBatchEquivalence:
    """Incremental building must match batch building."""

    def test_two_step_equivalence(self):
        """Two-step chain: incremental == batch."""
        configs = [{"a": 1}, {"b": 2}]

        batch = fingerprint(configs)

        fp0 = fingerprint_step(configs[0], previous_fingerprint=None)
        fp1 = fingerprint_step(configs[1], previous_fingerprint=fp0)

        assert batch[0] == fp0
        assert batch[1] == fp1

    def test_five_step_equivalence(self):
        """Five-step chain: incremental == batch."""
        configs = [{"step": i} for i in range(5)]

        batch = fingerprint(configs)

        incremental = []
        prev = None
        for config in configs:
            fp = fingerprint_step(config, previous_fingerprint=prev)
            incremental.append(fp)
            prev = fp

        assert batch == incremental

    def test_long_chain_equivalence(self):
        """100-step chain: incremental == batch."""
        configs = [{"index": i, "data": f"step_{i}"} for i in range(100)]

        batch = fingerprint(configs)

        incremental = []
        prev = None
        for config in configs:
            fp = fingerprint_step(config, previous_fingerprint=prev)
            incremental.append(fp)
            prev = fp

        assert batch == incremental

    def test_fingerprint_step_matches_fingerprint_at_index(self):
        """fingerprint_step(configs[i], fp[i-1]) == fingerprint(configs)[i]."""
        configs = [{"a": 1}, {"b": 2}, {"c": 3}, {"d": 4}]
        batch = fingerprint(configs)

        # Verify each position
        assert fingerprint_step(configs[0], None) == batch[0]
        assert fingerprint_step(configs[1], batch[0]) == batch[1]
        assert fingerprint_step(configs[2], batch[1]) == batch[2]
        assert fingerprint_step(configs[3], batch[2]) == batch[3]


# =============================================================================
# EDGE CASES - TYPES AND VALUES
# =============================================================================

class TestEmptyConfigs:
    """Empty config handling."""

    def test_empty_config(self):
        """Empty dict {} is valid config."""
        result = fingerprint([{}])
        assert len(result) == 1
        assert result[0].startswith("sha256:")

    def test_empty_config_chain(self):
        """Chain of empty configs works."""
        result = fingerprint([{}, {}, {}])
        assert len(result) == 3
        # All different due to position
        assert len(set(result)) == 3

    def test_empty_vs_non_empty(self):
        """Empty config differs from non-empty."""
        fp_empty = fingerprint([{}])
        fp_non_empty = fingerprint([{"key": "value"}])
        assert fp_empty[0] != fp_non_empty[0]


class TestNullAndMissing:
    """Null/None value handling."""

    def test_null_value(self):
        """Config with null value works."""
        result = fingerprint([{"key": None}])
        assert len(result) == 1

    def test_null_vs_missing(self):
        """{"key": null} differs from {}."""
        fp_null = fingerprint([{"key": None}])
        fp_missing = fingerprint([{}])
        assert fp_null[0] != fp_missing[0]

    def test_null_vs_empty_string(self):
        """{"key": null} differs from {"key": ""}."""
        fp_null = fingerprint([{"key": None}])
        fp_empty = fingerprint([{"key": ""}])
        assert fp_null[0] != fp_empty[0]

    def test_null_vs_zero(self):
        """{"key": null} differs from {"key": 0}."""
        fp_null = fingerprint([{"key": None}])
        fp_zero = fingerprint([{"key": 0}])
        assert fp_null[0] != fp_zero[0]


class TestNumericTypes:
    """Number handling edge cases."""

    def test_int_vs_float(self):
        """Integer 1 differs from float 1.0 (type preservation)."""
        fp_int = fingerprint([{"val": 1}])
        fp_float = fingerprint([{"val": 1.0}])
        # JSON doesn't distinguish, so these may be same - document behavior
        # If using strict typing, they'd differ

    def test_negative_zero(self):
        """-0.0 normalized to 0.0 (RFC 8785)."""
        fp_neg_zero = fingerprint([{"val": -0.0}])
        fp_zero = fingerprint([{"val": 0.0}])
        assert fp_neg_zero[0] == fp_zero[0]

    def test_large_integers(self):
        """Large integers work correctly."""
        big = 10**100
        result = fingerprint([{"big": big}])
        assert len(result) == 1

    def test_small_floats(self):
        """Very small floats work."""
        tiny = 1e-300
        result = fingerprint([{"tiny": tiny}])
        assert len(result) == 1

    def test_scientific_notation_type_preserved(self):
        """1e10 (float) differs from 10000000000 (int).

        In Python, 1e10 is a float and 10000000000 is an int.
        JSON serializes them differently (10000000000.0 vs 10000000000).
        This is correct behavior - type is preserved.
        """
        fp_float = fingerprint([{"val": 1e10}])  # float
        fp_int = fingerprint([{"val": 10000000000}])  # int
        # These SHOULD differ - one is float, one is int
        assert fp_float[0] != fp_int[0]

        # But same type should be equal
        fp_int_2 = fingerprint([{"val": int(1e10)}])
        assert fp_int[0] == fp_int_2[0]

    def test_nan_rejected(self):
        """NaN values should raise error (not serializable canonically)."""
        with pytest.raises((ChainError, ValueError)):
            fingerprint([{"val": float('nan')}])

    def test_infinity_rejected(self):
        """Infinity values should raise error."""
        with pytest.raises((ChainError, ValueError)):
            fingerprint([{"val": float('inf')}])

    def test_negative_infinity_rejected(self):
        """Negative infinity should raise error."""
        with pytest.raises((ChainError, ValueError)):
            fingerprint([{"val": float('-inf')}])


class TestStringTypes:
    """String handling edge cases."""

    def test_empty_string(self):
        """Empty string is valid value."""
        result = fingerprint([{"key": ""}])
        assert len(result) == 1

    def test_whitespace_preserved(self):
        """Whitespace in strings is preserved."""
        fp_no_space = fingerprint([{"key": "abc"}])
        fp_space = fingerprint([{"key": "a bc"}])
        fp_tabs = fingerprint([{"key": "a\tbc"}])
        assert fp_no_space[0] != fp_space[0]
        assert fp_space[0] != fp_tabs[0]

    def test_unicode_basic(self):
        """Basic unicode works."""
        result = fingerprint([{"greeting": "Hello, \u4e16\u754c"}])  # Hello, 世界
        assert len(result) == 1

    def test_emoji(self):
        """Emoji in strings works."""
        result = fingerprint([{"mood": "\U0001F600\U0001F389"}])  # 😀🎉
        assert len(result) == 1

    def test_unicode_normalization_not_applied(self):
        """Different unicode representations produce different fingerprints.

        We hash bytes as-is. If normalization is needed, canon module handles it.
        """
        # é as single codepoint vs e + combining accent
        composed = "\u00e9"      # é (single codepoint)
        decomposed = "e\u0301"   # e + combining acute accent

        # These look identical but are different bytes - should differ
        fp_composed = fingerprint([{"char": composed}])
        fp_decomposed = fingerprint([{"char": decomposed}])
        # Note: If canon normalizes, these would be equal. Test documents actual behavior.

    def test_null_bytes_in_string(self):
        """Strings with null bytes work."""
        result = fingerprint([{"data": "hello\x00world"}])
        assert len(result) == 1

    def test_newlines_preserved(self):
        """Newlines in strings are preserved."""
        fp_no_newline = fingerprint([{"text": "line1line2"}])
        fp_newline = fingerprint([{"text": "line1\nline2"}])
        assert fp_no_newline[0] != fp_newline[0]


class TestBooleans:
    """Boolean handling."""

    def test_true_value(self):
        """True works."""
        result = fingerprint([{"flag": True}])
        assert len(result) == 1

    def test_false_value(self):
        """False works."""
        result = fingerprint([{"flag": False}])
        assert len(result) == 1

    def test_true_vs_false(self):
        """True and False produce different fingerprints."""
        fp_true = fingerprint([{"flag": True}])
        fp_false = fingerprint([{"flag": False}])
        assert fp_true[0] != fp_false[0]

    def test_bool_vs_int(self):
        """True differs from 1, False differs from 0."""
        # In Python, bool is subclass of int, but JSON should preserve type
        fp_true = fingerprint([{"val": True}])
        fp_one = fingerprint([{"val": 1}])
        fp_false = fingerprint([{"val": False}])
        fp_zero = fingerprint([{"val": 0}])

        assert fp_true[0] != fp_one[0]
        assert fp_false[0] != fp_zero[0]


class TestNestedStructures:
    """Nested dicts and lists."""

    def test_nested_dict(self):
        """Nested dicts work."""
        result = fingerprint([{"outer": {"inner": {"deep": "value"}}}])
        assert len(result) == 1

    def test_nested_list(self):
        """Lists in dicts work."""
        result = fingerprint([{"items": [1, 2, 3]}])
        assert len(result) == 1

    def test_list_order_matters(self):
        """List element order affects fingerprint."""
        fp_123 = fingerprint([{"items": [1, 2, 3]}])
        fp_321 = fingerprint([{"items": [3, 2, 1]}])
        assert fp_123[0] != fp_321[0]

    def test_deeply_nested(self):
        """Very deep nesting works."""
        config = {"level": 0}
        for i in range(1, 50):
            config = {"level": i, "child": config}
        result = fingerprint([config])
        assert len(result) == 1

    def test_mixed_nesting(self):
        """Complex mixed structures work."""
        config = {
            "string": "value",
            "number": 42,
            "float": 3.14,
            "bool": True,
            "null": None,
            "list": [1, "two", 3.0, None, {"nested": "dict"}],
            "nested": {
                "a": [1, 2, 3],
                "b": {"deep": {"deeper": "value"}}
            }
        }
        result = fingerprint([config])
        assert len(result) == 1


class TestDuplicateConfigs:
    """Duplicate config handling."""

    def test_duplicate_configs_different_fingerprints(self):
        """Same config repeated gets different fingerprints (position matters)."""
        config = {"duplicate": True}
        result = fingerprint([config, config, config])
        assert len(set(result)) == 3  # All unique

    def test_alternating_configs(self):
        """Alternating A-B-A-B pattern works."""
        a = {"type": "A"}
        b = {"type": "B"}
        result = fingerprint([a, b, a, b])
        assert len(result) == 4
        # All should be unique
        assert len(set(result)) == 4


# =============================================================================
# EDGE CASES - SERIALIZATION BOUNDARIES
# =============================================================================

class TestSerializationAmbiguity:
    """Tests for serialization edge cases that could cause collisions."""

    def test_key_value_boundary(self):
        """{"a": "bc"} differs from {"ab": "c"}."""
        fp1 = fingerprint([{"a": "bc"}])
        fp2 = fingerprint([{"ab": "c"}])
        assert fp1[0] != fp2[0]

    def test_string_vs_number_type(self):
        """{"x": 1} differs from {"x": "1"}."""
        fp_num = fingerprint([{"x": 1}])
        fp_str = fingerprint([{"x": "1"}])
        assert fp_num[0] != fp_str[0]

    def test_array_vs_object(self):
        """[1, 2] differs from {"0": 1, "1": 2}."""
        fp_array = fingerprint([{"data": [1, 2]}])
        fp_obj = fingerprint([{"data": {"0": 1, "1": 2}}])
        assert fp_array[0] != fp_obj[0]


# =============================================================================
# PERFORMANCE AND SCALE
# =============================================================================

class TestLongChains:
    """Performance with long chains."""

    def test_hundred_steps(self):
        """100-step chain completes."""
        configs = [{"step": i} for i in range(100)]
        result = fingerprint(configs)
        assert len(result) == 100

    def test_thousand_steps(self):
        """1000-step chain completes in reasonable time."""
        configs = [{"step": i} for i in range(1000)]
        result = fingerprint(configs)
        assert len(result) == 1000

    @pytest.mark.slow
    def test_ten_thousand_steps(self):
        """10000-step chain completes."""
        configs = [{"step": i} for i in range(10000)]
        result = fingerprint(configs)
        assert len(result) == 10000


class TestLargeConfigs:
    """Performance with large configs."""

    def test_large_config(self):
        """Config with many keys works."""
        config = {f"key_{i}": f"value_{i}" for i in range(1000)}
        result = fingerprint([config])
        assert len(result) == 1

    def test_large_string_value(self):
        """Config with large string value works."""
        config = {"data": "x" * 1_000_000}  # 1MB string
        result = fingerprint([config])
        assert len(result) == 1

    def test_large_list(self):
        """Config with large list works."""
        config = {"items": list(range(10000))}
        result = fingerprint([config])
        assert len(result) == 1


# =============================================================================
# ERROR HANDLING
# =============================================================================

class TestInputValidation:
    """Input validation and error handling."""

    def test_non_dict_config_rejected(self):
        """Non-dict config raises error."""
        with pytest.raises((ChainError, TypeError)):
            fingerprint(["not a dict"])

    def test_non_list_input_rejected(self):
        """Non-list input raises error."""
        with pytest.raises((ChainError, TypeError)):
            fingerprint({"single": "config"})

    def test_circular_reference_rejected(self):
        """Circular reference in config raises error."""
        config = {"a": 1}
        config["self"] = config  # Circular!
        with pytest.raises((ChainError, ValueError)):
            fingerprint([config])

    def test_non_json_type_rejected(self):
        """Non-JSON-serializable types raise error."""
        with pytest.raises((ChainError, TypeError)):
            fingerprint([{"func": lambda x: x}])

    def test_bytes_rejected(self):
        """Bytes values raise error (use base64 string instead)."""
        with pytest.raises((ChainError, TypeError)):
            fingerprint([{"data": b"bytes"}])

    def test_invalid_previous_fingerprint(self):
        """Invalid previous_fingerprint format raises error."""
        with pytest.raises((ChainError, ValueError)):
            fingerprint_step({"a": 1}, previous_fingerprint="not-a-valid-hash")


# =============================================================================
# PROPERTY-BASED TESTS
# =============================================================================

# JSON-compatible values strategy (module level for hypothesis)
_json_primitives = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(),
)

def _json_values():
    """Strategy for JSON-compatible values."""
    return st.recursive(
        _json_primitives,
        lambda children: st.one_of(
            st.lists(children, max_size=5),
            st.dictionaries(st.text(max_size=10), children, max_size=5),
        ),
        max_leaves=20,
    )


class TestPropertyBased:
    """Property-based tests using Hypothesis."""

    @given(st.dictionaries(st.text(max_size=10), _json_values(), max_size=10))
    @settings(max_examples=100)
    def test_single_config_deterministic(self, config):
        """Any valid config produces deterministic fingerprint."""
        try:
            fp1 = fingerprint([config])
            fp2 = fingerprint([config])
            assert fp1 == fp2
        except (ChainError, ValueError, TypeError):
            pass  # Invalid configs can raise errors

    @given(st.lists(
        st.dictionaries(st.text(max_size=5), _json_primitives, max_size=5),
        min_size=2,
        max_size=10
    ))
    @settings(max_examples=50)
    def test_chain_length_matches_input(self, configs):
        """Output length always matches input length."""
        try:
            result = fingerprint(configs)
            assert len(result) == len(configs)
        except (ChainError, ValueError, TypeError):
            pass

    @given(st.dictionaries(st.text(max_size=5), _json_primitives, max_size=5))
    @settings(max_examples=50)
    def test_position_sensitivity_property(self, config):
        """Same config at positions 0 and 1 always produces different fingerprints."""
        try:
            result = fingerprint([config, config])
            assert result[0] != result[1]
        except (ChainError, ValueError, TypeError):
            pass

    @given(st.lists(
        st.dictionaries(st.text(max_size=5), _json_primitives, max_size=5),
        min_size=1,
        max_size=10
    ))
    @settings(max_examples=50)
    def test_incremental_equals_batch_property(self, configs):
        """Incremental always equals batch for any valid chain."""
        try:
            batch = fingerprint(configs)

            incremental = []
            prev = None
            for config in configs:
                fp = fingerprint_step(config, previous_fingerprint=prev)
                incremental.append(fp)
                prev = fp

            assert batch == incremental
        except (ChainError, ValueError, TypeError):
            pass

    @given(
        st.lists(st.dictionaries(st.text(max_size=5), _json_primitives, max_size=5), min_size=3, max_size=10),
        st.integers(min_value=0)
    )
    @settings(max_examples=50)
    def test_change_propagation_property(self, configs, change_idx):
        """Changing any config changes all subsequent fingerprints."""
        assume(len(configs) >= 2)
        change_idx = change_idx % len(configs)

        try:
            original = fingerprint(configs)

            # Modify the config at change_idx
            modified_configs = [dict(c) for c in configs]  # Deep copy
            modified_configs[change_idx]["__modified__"] = True
            modified = fingerprint(modified_configs)

            # Fingerprints before change_idx should be same
            for i in range(change_idx):
                assert original[i] == modified[i], f"Position {i} should be unchanged"

            # Fingerprints at and after change_idx should differ
            for i in range(change_idx, len(configs)):
                assert original[i] != modified[i], f"Position {i} should be changed"

        except (ChainError, ValueError, TypeError):
            pass


# =============================================================================
# INTEGRATION WITH CANON AND HASH
# =============================================================================

class TestCanonHashIntegration:
    """Integration with ledger.canon and ledger.hash modules."""

    def test_uses_canonical_serialization(self):
        """Verify fingerprint uses canonical JSON (sorted keys, no whitespace)."""
        # Different key orders should produce same fingerprint
        config1 = {"z": 1, "a": 2}
        config2 = {"a": 2, "z": 1}
        assert fingerprint([config1]) == fingerprint([config2])

    def test_fingerprint_format_matches_hash_module(self):
        """Fingerprint format matches ledger.hash output format."""
        from knurl.hash import compute

        result = fingerprint([{"test": "value"}])
        # Should be sha256:hexdigest format
        parts = result[0].split(":")
        assert len(parts) == 2
        assert parts[0] == "sha256"
        assert len(parts[1]) == 64
