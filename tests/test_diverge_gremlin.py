"""Gremlin attack tests for spiritengine.diverge

These tests target assumptions in divergence detection.
Each test tries to break something that looks solid.

Attack vectors:
- Type confusion (non-lists, None, mixed types)
- Invalid fingerprint formats (no sha256:, wrong digest length, uppercase)
- Unicode edge cases
- Mutability during execution
- Very deep chains (memory/performance)
- Numeric edge cases in indices
"""

import pytest
from spiritengine import diverge
from spiritengine.diverge import DivergenceResult


def fp(suffix: str) -> str:
    """Helper to create fingerprint strings."""
    return f"sha256:{suffix}"


class TestTypeConfusion:
    """ATTACK: What happens with wrong types?"""

    def test_find_with_none_old(self):
        """ATTACK: find() with None as old chain"""
        new = [fp("aaa")]

        # Should fail gracefully, not crash
        with pytest.raises((TypeError, AttributeError)):
            diverge.find(None, new)

    def test_find_with_none_new(self):
        """ATTACK: find() with None as new chain"""
        old = [fp("aaa")]

        with pytest.raises((TypeError, AttributeError)):
            diverge.find(old, None)

    def test_find_with_both_none(self):
        """ATTACK: find() with both None"""
        with pytest.raises((TypeError, AttributeError)):
            diverge.find(None, None)

    def test_find_with_string_instead_of_list(self):
        """ATTACK: Pass string instead of list"""
        # Strings are iterable, might partially work
        old = "sha256:aaa"  # String, not list
        new = [fp("aaa")]

        # Either fails or treats each char as element
        try:
            result = diverge.find(old, new)
            # If it "works", it's comparing chars to fingerprints
            # Should diverge immediately since 's' != 'sha256:aaa'
            assert result.divergence_index == 0
        except (TypeError, AttributeError):
            pass  # Acceptable to reject

    def test_find_with_tuple_instead_of_list(self):
        """ATTACK: Pass tuple instead of list"""
        old = (fp("aaa"), fp("bbb"))
        new = (fp("aaa"), fp("bbb"))

        # Tuples are iterable - should work same as lists
        result = diverge.find(old, new)
        assert result.divergence_index is None
        assert result.common_prefix_length == 2

    def test_find_with_generator(self):
        """ATTACK: Pass generator instead of list"""
        old = (fp(s) for s in ["aaa", "bbb"])
        new = [fp("aaa"), fp("bbb")]

        # Generators can only be consumed once
        # Will this break? Will it work?
        try:
            result = diverge.find(old, new)
            # If it works with generators, that's a feature
        except TypeError:
            pass  # Acceptable to require lists


class TestMixedTypes:
    """ATTACK: Lists with non-string elements"""

    def test_find_with_int_in_chain(self):
        """ATTACK: Integer mixed with fingerprints"""
        old = [fp("aaa"), 12345, fp("ccc")]  # int in middle
        new = [fp("aaa"), fp("bbb"), fp("ccc")]

        # Comparing int to string should diverge
        result = diverge.find(old, new)
        assert result.divergence_index == 1
        assert result.common_prefix_length == 1

    def test_find_with_none_in_chain(self):
        """ATTACK: None mixed with fingerprints"""
        old = [fp("aaa"), None, fp("ccc")]
        new = [fp("aaa"), fp("bbb"), fp("ccc")]

        # None != string, should diverge
        result = diverge.find(old, new)
        assert result.divergence_index == 1

    def test_find_with_dict_in_chain(self):
        """ATTACK: Dict mixed with fingerprints"""
        old = [fp("aaa"), {"hash": "bbb"}, fp("ccc")]
        new = [fp("aaa"), fp("bbb"), fp("ccc")]

        # Dict != string, should diverge
        result = diverge.find(old, new)
        assert result.divergence_index == 1

    def test_find_with_all_wrong_types(self):
        """ATTACK: No strings at all"""
        old = [1, 2, 3]
        new = [1, 2, 4]

        # Should still compare correctly
        result = diverge.find(old, new)
        assert result.divergence_index == 2
        assert result.common_prefix_length == 2


class TestInvalidFingerprintFormats:
    """ATTACK: Malformed fingerprint strings"""

    def test_find_with_missing_prefix(self):
        """ATTACK: Fingerprints without sha256: prefix"""
        old = ["aaa", "bbb"]  # Missing sha256: prefix
        new = ["aaa", "bbb"]

        # Should still compare (strings are strings)
        result = diverge.find(old, new)
        assert result.divergence_index is None
        # diverge.py doesn't validate fingerprint format

    def test_find_with_wrong_prefix(self):
        """ATTACK: Wrong hash algorithm prefix"""
        old = ["md5:aaa", "md5:bbb"]
        new = ["md5:aaa", "md5:bbb"]

        # Still just string comparison
        result = diverge.find(old, new)
        assert result.divergence_index is None

    def test_find_with_uppercase_digest(self):
        """ATTACK: Uppercase hex digest (should be lowercase per spec)"""
        old = ["sha256:AAA", "sha256:BBB"]
        new = ["sha256:aaa", "sha256:bbb"]

        # String comparison is case-sensitive
        # Uppercase != lowercase, should diverge immediately
        result = diverge.find(old, new)
        assert result.divergence_index == 0

    def test_find_with_short_digest(self):
        """ATTACK: Short digest (not 64 hex chars)"""
        old = ["sha256:abc", "sha256:def"]  # Only 3 chars
        new = ["sha256:abc", "sha256:def"]

        # Still strings, should work
        result = diverge.find(old, new)
        assert result.divergence_index is None

    def test_find_with_empty_fingerprint(self):
        """ATTACK: Empty string as fingerprint"""
        old = ["", "sha256:bbb"]
        new = ["", "sha256:bbb"]

        # Empty strings are valid strings
        result = diverge.find(old, new)
        assert result.divergence_index is None


class TestUnicodeEdgeCases:
    """ATTACK: Non-ASCII characters in fingerprints"""

    def test_find_with_emoji_in_fingerprint(self):
        """ATTACK: Emoji in fingerprint string"""
        old = ["sha256:🔥", "sha256:bbb"]
        new = ["sha256:🔥", "sha256:bbb"]

        # Unicode comparison should work
        result = diverge.find(old, new)
        assert result.divergence_index is None

    def test_find_with_different_unicode_normalization(self):
        """ATTACK: Same visual character, different normalization"""
        # é can be U+00E9 (composed) or e + U+0301 (decomposed)
        old = ["sha256:café"]  # NFC normalization
        new = ["sha256:café"]  # NFD normalization (visually same)

        # Python string comparison is byte-wise
        # Different normalizations might compare as different
        result = diverge.find(old, new)
        # This test documents behavior - may be equal or not

    def test_find_with_cyrillic_lookalike(self):
        """ATTACK: Cyrillic 'a' vs Latin 'a'"""
        # Cyrillic 'а' (U+0430) looks like Latin 'a' (U+0061)
        old = ["sha256:а"]  # Cyrillic
        new = ["sha256:a"]  # Latin

        # Different characters, should diverge
        result = diverge.find(old, new)
        assert result.divergence_index == 0


class TestMemoryAndPerformance:
    """ATTACK: Very deep chains to stress memory/performance"""

    def test_find_with_extremely_deep_chains(self):
        """ATTACK: Million-element chains"""
        # Create 1M element chains that diverge at end
        base = [fp(f"elem{i:08d}") for i in range(999_999)]
        old = base + [fp("old_end")]
        new = base + [fp("new_end")]

        # Should handle without memory issues
        result = diverge.find(old, new)
        assert result.divergence_index == 999_999
        assert result.common_prefix_length == 999_999

    def test_find_with_very_long_fingerprint_strings(self):
        """ATTACK: Fingerprints with very long strings"""
        # Create fingerprints with 10KB strings
        long_suffix = "a" * 10_000
        old = [fp(long_suffix), fp("bbb")]
        new = [fp(long_suffix), fp("bbb")]

        # Should handle without issues
        result = diverge.find(old, new)
        assert result.divergence_index is None


class TestMutabilityAttacks:
    """ATTACK: Mutate inputs during or after execution"""

    def test_result_not_affected_by_input_mutation(self):
        """ATTACK: Modify input list after calling find()"""
        old = [fp("aaa"), fp("bbb"), fp("ccc")]
        new = [fp("aaa"), fp("bbb"), fp("xxx")]

        result = diverge.find(old, new)

        # Now mutate the inputs
        old[0] = fp("mutated")
        new[1] = fp("mutated")

        # Result should be unaffected (it's computed, not storing references)
        assert result.divergence_index == 2
        assert result.common_prefix_length == 2

    def test_common_prefix_mutation_safety(self):
        """ATTACK: Mutate the returned common_prefix list"""
        old = [fp("aaa"), fp("bbb"), fp("ccc")]
        new = [fp("aaa"), fp("bbb"), fp("xxx")]

        prefix = diverge.common_prefix(old, new)
        assert len(prefix) == 2

        # Mutate the returned prefix
        prefix[0] = fp("hacked")
        prefix.append(fp("malicious"))

        # Original inputs should be unaffected
        assert old[0] == fp("aaa")
        assert len(old) == 3

        # Calling again should give clean result
        prefix2 = diverge.common_prefix(old, new)
        assert prefix2[0] == fp("aaa")
        assert len(prefix2) == 2


class TestNumericEdgeCases:
    """ATTACK: Extreme values for indices and counts"""

    def test_result_counts_on_empty_chains(self):
        """ATTACK: Verify counts are 0, not None or negative"""
        result = diverge.find([], [])

        # All counts should be 0, not None or negative
        assert result.common_prefix_length == 0
        assert result.old_remainder == 0
        assert result.new_remainder == 0
        assert result.divergence_index is None  # Not 0, but None

    def test_result_counts_never_negative(self):
        """ATTACK: Counts should never be negative"""
        # Try various combinations
        test_cases = [
            ([], [fp("a")]),
            ([fp("a")], []),
            ([fp("a"), fp("b")], [fp("x")]),
            ([fp("x")], [fp("a"), fp("b")]),
        ]

        for old, new in test_cases:
            result = diverge.find(old, new)
            assert result.common_prefix_length >= 0
            assert result.old_remainder >= 0
            assert result.new_remainder >= 0
            if result.divergence_index is not None:
                assert result.divergence_index >= 0


class TestInvariantViolations:
    """ATTACK: Try to create inconsistent DivergenceResult states"""

    def test_invariant_lengths_always_add_up(self):
        """ATTACK: Verify prefix + remainder = length always holds"""
        import random

        # Generate random test cases
        for _ in range(100):
            old_len = random.randint(0, 20)
            new_len = random.randint(0, 20)
            common_len = random.randint(0, min(old_len, new_len))

            # Create chains with controlled divergence point
            common = [fp(f"c{i}") for i in range(common_len)]
            old = common + [fp(f"o{i}") for i in range(old_len - common_len)]
            new = common + [fp(f"n{i}") for i in range(new_len - common_len)]

            result = diverge.find(old, new)

            # Invariant: must always hold
            assert result.common_prefix_length + result.old_remainder == len(old)
            assert result.common_prefix_length + result.new_remainder == len(new)

    def test_divergence_index_consistency(self):
        """ATTACK: divergence_index should always equal common_prefix_length when not None"""
        test_cases = [
            ([fp("a")], [fp("b")]),  # Diverge at 0
            ([fp("a"), fp("b")], [fp("a"), fp("x")]),  # Diverge at 1
            ([fp("a"), fp("b"), fp("c")], [fp("a"), fp("b"), fp("x")]),  # Diverge at 2
        ]

        for old, new in test_cases:
            result = diverge.find(old, new)
            if result.divergence_index is not None:
                assert result.divergence_index == result.common_prefix_length

    def test_identical_implies_no_divergence_index(self):
        """ATTACK: If chains identical, divergence_index must be None"""
        identical_chains = [
            ([], []),
            ([fp("a")], [fp("a")]),
            ([fp("a"), fp("b"), fp("c")], [fp("a"), fp("b"), fp("c")]),
        ]

        for old, new in identical_chains:
            result = diverge.find(old, new)
            assert result.divergence_index is None
            assert diverge.identical(old, new) is True


class TestEdgeCasesBeyondSpec:
    """ATTACK: Scenarios not explicitly documented in spec"""

    def test_find_with_duplicate_fingerprints_in_chain(self):
        """ATTACK: Same fingerprint appears multiple times"""
        old = [fp("aaa"), fp("bbb"), fp("aaa")]  # aaa appears twice
        new = [fp("aaa"), fp("bbb"), fp("aaa")]

        # Should still work - duplicates are fine
        result = diverge.find(old, new)
        assert result.divergence_index is None

    def test_find_with_all_identical_fingerprints(self):
        """ATTACK: All fingerprints are the same"""
        old = [fp("aaa"), fp("aaa"), fp("aaa")]
        new = [fp("aaa"), fp("aaa"), fp("aaa")]

        # Still identical
        result = diverge.find(old, new)
        assert result.divergence_index is None

    def test_find_with_whitespace_differences(self):
        """ATTACK: Fingerprints differ only in whitespace"""
        old = ["sha256:aaa", "sha256:bbb"]
        new = ["sha256:aaa ", "sha256:bbb"]  # Trailing space on first element

        # String comparison is exact, should diverge at index 0
        result = diverge.find(old, new)
        assert result.divergence_index == 0  # First element differs

    def test_common_prefix_returns_slice_not_reference(self):
        """ATTACK: Ensure common_prefix returns a new list"""
        old = [fp("aaa"), fp("bbb"), fp("ccc")]
        new = [fp("aaa"), fp("bbb"), fp("xxx")]

        prefix = diverge.common_prefix(old, new)

        # Should be a slice (new list), not reference to old
        assert prefix == [fp("aaa"), fp("bbb")]
        assert prefix is not old  # Different object

        # Mutating prefix shouldn't affect old
        prefix.clear()
        assert len(old) == 3  # old unchanged
