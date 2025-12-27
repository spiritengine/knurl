"""Oracle property-based tests for knurl.diverge

Uses Hypothesis to verify mathematical properties hold for ALL possible inputs.

Properties verified:
1. Invariants always hold (lengths, indices)
2. Idempotence (find(a, a) always identical)
3. Commutativity of length (prefix length same regardless of order)
4. Prefix relationships
5. Transitivity of equality
6. Consistency between functions
"""

import pytest
from hypothesis import given, strategies as st, assume
from knurl import diverge
from knurl.diverge import DivergenceResult


# Strategy: Generate valid fingerprint-like strings
fingerprints = st.text(
    alphabet="0123456789abcdef",
    min_size=64,
    max_size=64
).map(lambda h: f"sha256:{h}")

# Strategy: Lists of fingerprints
fingerprint_lists = st.lists(fingerprints, min_size=0, max_size=100)


class TestInvariantProperties:
    """Properties that must ALWAYS hold for any input."""

    @given(old=fingerprint_lists, new=fingerprint_lists)
    def test_length_invariants_always_hold(self, old, new):
        """PROPERTY: prefix + remainder == total length"""
        result = diverge.find(old, new)

        # Invariant 1: old length decomposition
        assert result.common_prefix_length + result.old_remainder == len(old), \
            f"Old length broken: {result.common_prefix_length} + {result.old_remainder} != {len(old)}"

        # Invariant 2: new length decomposition
        assert result.common_prefix_length + result.new_remainder == len(new), \
            f"New length broken: {result.common_prefix_length} + {result.new_remainder} != {len(new)}"

    @given(old=fingerprint_lists, new=fingerprint_lists)
    def test_counts_never_negative(self, old, new):
        """PROPERTY: All counts are non-negative"""
        result = diverge.find(old, new)

        assert result.common_prefix_length >= 0
        assert result.old_remainder >= 0
        assert result.new_remainder >= 0
        if result.divergence_index is not None:
            assert result.divergence_index >= 0

    @given(old=fingerprint_lists, new=fingerprint_lists)
    def test_divergence_index_consistency(self, old, new):
        """PROPERTY: divergence_index == common_prefix_length when divergent"""
        result = diverge.find(old, new)

        if result.divergence_index is not None:
            assert result.divergence_index == result.common_prefix_length, \
                "divergence_index must equal common_prefix_length when chains diverge"

    @given(old=fingerprint_lists, new=fingerprint_lists)
    def test_common_prefix_length_bounded(self, old, new):
        """PROPERTY: common_prefix_length <= min(len(old), len(new))"""
        result = diverge.find(old, new)

        max_possible = min(len(old), len(new))
        assert result.common_prefix_length <= max_possible, \
            f"common_prefix_length ({result.common_prefix_length}) > min({len(old)}, {len(new)}) = {max_possible}"


class TestIdempotenceProperties:
    """Properties about comparing a list to itself."""

    @given(chain=fingerprint_lists)
    def test_find_identical_to_self(self, chain):
        """PROPERTY: find(a, a) always returns no divergence"""
        result = diverge.find(chain, chain)

        assert result.divergence_index is None
        assert result.common_prefix_length == len(chain)
        assert result.old_remainder == 0
        assert result.new_remainder == 0

    @given(chain=fingerprint_lists)
    def test_identical_returns_true_for_self(self, chain):
        """PROPERTY: identical(a, a) is always True"""
        assert diverge.identical(chain, chain) is True

    @given(chain=fingerprint_lists)
    def test_common_prefix_of_self_is_self(self, chain):
        """PROPERTY: common_prefix(a, a) == a"""
        prefix = diverge.common_prefix(chain, chain)
        assert prefix == chain


class TestSymmetryProperties:
    """Properties about order of arguments."""

    @given(old=fingerprint_lists, new=fingerprint_lists)
    def test_common_prefix_length_symmetric(self, old, new):
        """PROPERTY: common_prefix length same regardless of order"""
        result1 = diverge.find(old, new)
        result2 = diverge.find(new, old)

        # Length of common prefix should be same
        assert result1.common_prefix_length == result2.common_prefix_length

    @given(old=fingerprint_lists, new=fingerprint_lists)
    def test_identical_is_symmetric(self, old, new):
        """PROPERTY: identical(a, b) == identical(b, a)"""
        assert diverge.identical(old, new) == diverge.identical(new, old)

    @given(old=fingerprint_lists, new=fingerprint_lists)
    def test_divergence_index_symmetric_when_not_prefix(self, old, new):
        """PROPERTY: When not prefix relationship, divergence indices match"""
        result1 = diverge.find(old, new)
        result2 = diverge.find(new, old)

        # If neither is prefix of other, divergence index should be same
        if len(old) == len(new):
            if result1.divergence_index is not None:
                assert result1.divergence_index == result2.divergence_index


class TestPrefixProperties:
    """Properties about prefix relationships."""

    @given(
        chain=fingerprint_lists,
        prefix_len=st.integers(min_value=0, max_value=50)
    )
    def test_prefix_relationship_detected(self, chain, prefix_len):
        """PROPERTY: If b is prefix of a, find() detects it correctly"""
        # Take a prefix
        assume(len(chain) >= prefix_len)
        prefix = chain[:prefix_len]
        full = chain

        result = diverge.find(full, prefix)

        # Should diverge at the prefix length
        if len(prefix) < len(full):
            assert result.divergence_index == len(prefix)
            assert result.common_prefix_length == len(prefix)
            assert result.old_remainder == len(full) - len(prefix)
            assert result.new_remainder == 0
        else:
            # Same length = identical
            assert result.divergence_index is None

    @given(data=st.data())
    def test_extending_chain_preserves_prefix(self, data):
        """PROPERTY: Adding element preserves common prefix with original"""
        chain = data.draw(fingerprint_lists)
        extra = data.draw(fingerprints)

        extended = chain + [extra]

        result = diverge.find(chain, extended)

        # Original should be prefix of extended
        assert result.divergence_index == len(chain)
        assert result.common_prefix_length == len(chain)
        assert result.old_remainder == 0
        assert result.new_remainder == 1


class TestTransitivityProperties:
    """Properties about relationships between three chains."""

    @given(a=fingerprint_lists, b=fingerprint_lists, c=fingerprint_lists)
    def test_identical_transitivity(self, a, b, c):
        """PROPERTY: If a==b and b==c, then a==c"""
        if diverge.identical(a, b) and diverge.identical(b, c):
            assert diverge.identical(a, c), \
                "Transitivity violated: a==b, b==c, but a!=c"

    @given(data=st.data())
    def test_prefix_transitivity(self, data):
        """PROPERTY: If a is prefix of b, and b is prefix of c, then a is prefix of c"""
        # Generate nested prefixes
        c = data.draw(fingerprint_lists)
        assume(len(c) >= 2)

        b_len = data.draw(st.integers(min_value=0, max_value=len(c)))
        b = c[:b_len]

        a_len = data.draw(st.integers(min_value=0, max_value=len(b)))
        a = b[:a_len]

        # Verify a is prefix of c
        result_ac = diverge.find(c, a)
        if a_len < len(c):
            assert result_ac.divergence_index == a_len
            assert result_ac.common_prefix_length == a_len


class TestConsistencyBetweenFunctions:
    """Properties about consistency between find(), identical(), common_prefix()."""

    @given(old=fingerprint_lists, new=fingerprint_lists)
    def test_identical_matches_find(self, old, new):
        """PROPERTY: identical() and find() agree on whether chains are identical"""
        result = diverge.find(old, new)
        is_identical = diverge.identical(old, new)

        if result.divergence_index is None:
            assert is_identical is True
        else:
            assert is_identical is False

    @given(old=fingerprint_lists, new=fingerprint_lists)
    def test_common_prefix_length_matches_find(self, old, new):
        """PROPERTY: len(common_prefix()) == find().common_prefix_length"""
        result = diverge.find(old, new)
        prefix = diverge.common_prefix(old, new)

        assert len(prefix) == result.common_prefix_length

    @given(old=fingerprint_lists, new=fingerprint_lists)
    def test_common_prefix_contents_match_input(self, old, new):
        """PROPERTY: common_prefix() returns actual prefix from old"""
        result = diverge.find(old, new)
        prefix = diverge.common_prefix(old, new)

        # Should match the first N elements of old
        assert prefix == old[:result.common_prefix_length]


class TestBoundaryProperties:
    """Properties at boundaries (empty, single element, etc.)."""

    @given(fp=fingerprints)
    def test_single_element_identical(self, fp):
        """PROPERTY: Single element chains that match are identical"""
        result = diverge.find([fp], [fp])

        assert result.divergence_index is None
        assert result.common_prefix_length == 1
        assert result.old_remainder == 0
        assert result.new_remainder == 0

    @given(fp1=fingerprints, fp2=fingerprints)
    def test_single_element_different(self, fp1, fp2):
        """PROPERTY: Different single elements diverge at 0"""
        assume(fp1 != fp2)

        result = diverge.find([fp1], [fp2])

        assert result.divergence_index == 0
        assert result.common_prefix_length == 0
        assert result.old_remainder == 1
        assert result.new_remainder == 1

    @given(chain=fingerprint_lists)
    def test_empty_vs_non_empty(self, chain):
        """PROPERTY: Empty vs non-empty always diverges at 0"""
        assume(len(chain) > 0)

        result = diverge.find([], chain)

        assert result.divergence_index == 0
        assert result.common_prefix_length == 0
        assert result.old_remainder == 0
        assert result.new_remainder == len(chain)


class TestDivergencePointProperties:
    """Properties about where chains diverge."""

    @given(data=st.data())
    def test_divergence_point_is_first_mismatch(self, data):
        """PROPERTY: divergence_index points to first differing element"""
        # Generate chain with controlled divergence
        common = data.draw(fingerprint_lists)
        old_tail = data.draw(st.lists(fingerprints, min_size=1, max_size=10))
        new_tail = data.draw(st.lists(fingerprints, min_size=1, max_size=10))

        # Ensure first elements of tails differ
        assume(len(old_tail) > 0 and len(new_tail) > 0)
        assume(old_tail[0] != new_tail[0])

        old = common + old_tail
        new = common + new_tail

        result = diverge.find(old, new)

        # Should diverge exactly at len(common)
        assert result.divergence_index == len(common)
        assert result.common_prefix_length == len(common)

    @given(data=st.data())
    def test_all_elements_before_divergence_match(self, data):
        """PROPERTY: All elements before divergence_index must be identical"""
        old = data.draw(fingerprint_lists)
        new = data.draw(fingerprint_lists)

        result = diverge.find(old, new)

        if result.divergence_index is not None and result.divergence_index > 0:
            # All elements before divergence must match
            for i in range(result.divergence_index):
                assert old[i] == new[i], \
                    f"Elements before divergence should match: old[{i}]={old[i]} != new[{i}]={new[i]}"


class TestRemainderProperties:
    """Properties about remainder counts."""

    @given(old=fingerprint_lists, new=fingerprint_lists)
    def test_remainder_sum_is_total_minus_prefix(self, old, new):
        """PROPERTY: Total elements = common + old_remainder + new_remainder"""
        result = diverge.find(old, new)

        total_elements = len(old) + len(new)
        accounted_for = result.common_prefix_length + result.old_remainder + result.common_prefix_length + result.new_remainder

        # Each element should be counted exactly once
        assert accounted_for == total_elements

    @given(old=fingerprint_lists, new=fingerprint_lists)
    def test_both_remainders_zero_implies_identical(self, old, new):
        """PROPERTY: If both remainders are 0, chains are identical"""
        result = diverge.find(old, new)

        if result.old_remainder == 0 and result.new_remainder == 0:
            assert result.divergence_index is None
            assert diverge.identical(old, new) is True
