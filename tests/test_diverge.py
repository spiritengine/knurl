"""Comprehensive test suite for ledger.diverge module."""
import pytest
from spiritengine import diverge
from spiritengine.diverge import DivergenceResult


def fp(suffix: str) -> str:
    """Helper to create fingerprint strings."""
    return f"sha256:{suffix}"


def chain(*suffixes: str) -> list[str]:
    """Helper to create fingerprint chains."""
    return [fp(s) for s in suffixes]


class TestIdenticalChains:
    """Tests for chains that are exactly the same."""

    def test_identical_empty_chains(self):
        result = diverge.find([], [])
        assert result.divergence_index is None
        assert result.common_prefix_length == 0
        assert result.old_remainder == 0
        assert result.new_remainder == 0

    def test_identical_single_element(self):
        old = new = chain("aaa")
        result = diverge.find(old, new)
        assert result.divergence_index is None
        assert result.common_prefix_length == 1
        assert result.old_remainder == 0
        assert result.new_remainder == 0

    def test_identical_multiple_elements(self):
        old = new = chain("aaa", "bbb", "ccc")
        result = diverge.find(old, new)
        assert result.divergence_index is None
        assert result.common_prefix_length == 3
        assert result.old_remainder == 0
        assert result.new_remainder == 0

    def test_identical_returns_true(self):
        old = new = chain("aaa", "bbb")
        assert diverge.identical(old, new) is True

    def test_identical_empty_returns_true(self):
        assert diverge.identical([], []) is True


class TestCompletelyDifferent:
    """Tests for chains with no common prefix."""

    def test_differ_at_index_zero(self):
        old = chain("aaa", "bbb")
        new = chain("xxx", "yyy")
        result = diverge.find(old, new)
        assert result.divergence_index == 0
        assert result.common_prefix_length == 0
        assert result.old_remainder == 2
        assert result.new_remainder == 2

    def test_single_elements_different(self):
        old = chain("aaa")
        new = chain("xxx")
        result = diverge.find(old, new)
        assert result.divergence_index == 0
        assert result.common_prefix_length == 0
        assert result.old_remainder == 1
        assert result.new_remainder == 1

    def test_common_prefix_empty_when_different(self):
        old = chain("aaa")
        new = chain("xxx")
        assert diverge.common_prefix(old, new) == []


class TestDivergenceAtEnd:
    """Tests for chains that diverge at the final element."""

    def test_last_element_differs(self):
        old = chain("aaa", "bbb", "ccc")
        new = chain("aaa", "bbb", "xxx")
        result = diverge.find(old, new)
        assert result.divergence_index == 2
        assert result.common_prefix_length == 2
        assert result.old_remainder == 1
        assert result.new_remainder == 1

    def test_common_prefix_excludes_divergent(self):
        old = chain("aaa", "bbb", "ccc")
        new = chain("aaa", "bbb", "xxx")
        assert diverge.common_prefix(old, new) == chain("aaa", "bbb")


class TestDivergenceAtMiddle:
    """Tests for chains that diverge somewhere in the middle."""

    def test_diverge_at_index_one(self):
        old = chain("aaa", "bbb", "ccc")
        new = chain("aaa", "xxx", "yyy")
        result = diverge.find(old, new)
        assert result.divergence_index == 1
        assert result.common_prefix_length == 1
        assert result.old_remainder == 2
        assert result.new_remainder == 2

    @pytest.mark.parametrize("diverge_at", range(1, 10))
    def test_parameterized_divergence_position(self, diverge_at):
        """Test divergence at various positions."""
        common = [fp(f"common{i:03d}") for i in range(diverge_at)]
        old = common + [fp("old_diverge")]
        new = common + [fp("new_diverge")]

        result = diverge.find(old, new)
        assert result.divergence_index == diverge_at
        assert result.common_prefix_length == diverge_at
        assert result.old_remainder == 1
        assert result.new_remainder == 1


class TestLengthMismatches:
    """Tests for chains of different lengths."""

    def test_old_longer_same_prefix(self):
        old = chain("aaa", "bbb", "ccc")
        new = chain("aaa", "bbb")
        result = diverge.find(old, new)
        assert result.divergence_index == 2
        assert result.common_prefix_length == 2
        assert result.old_remainder == 1
        assert result.new_remainder == 0

    def test_new_longer_same_prefix(self):
        old = chain("aaa", "bbb")
        new = chain("aaa", "bbb", "ccc")
        result = diverge.find(old, new)
        assert result.divergence_index == 2
        assert result.common_prefix_length == 2
        assert result.old_remainder == 0
        assert result.new_remainder == 1

    def test_old_longer_multiple_extra(self):
        old = chain("aaa", "bbb", "ccc", "ddd", "eee")
        new = chain("aaa", "bbb")
        result = diverge.find(old, new)
        assert result.divergence_index == 2
        assert result.common_prefix_length == 2
        assert result.old_remainder == 3
        assert result.new_remainder == 0

    def test_new_longer_multiple_extra(self):
        old = chain("aaa", "bbb")
        new = chain("aaa", "bbb", "ccc", "ddd", "eee")
        result = diverge.find(old, new)
        assert result.divergence_index == 2
        assert result.common_prefix_length == 2
        assert result.old_remainder == 0
        assert result.new_remainder == 3

    def test_empty_old(self):
        old = []
        new = chain("aaa", "bbb")
        result = diverge.find(old, new)
        assert result.divergence_index == 0
        assert result.common_prefix_length == 0
        assert result.old_remainder == 0
        assert result.new_remainder == 2

    def test_empty_new(self):
        old = chain("aaa", "bbb")
        new = []
        result = diverge.find(old, new)
        assert result.divergence_index == 0
        assert result.common_prefix_length == 0
        assert result.old_remainder == 2
        assert result.new_remainder == 0

    def test_both_empty(self):
        old = []
        new = []
        result = diverge.find(old, new)
        assert result.divergence_index is None
        assert result.common_prefix_length == 0
        assert result.old_remainder == 0
        assert result.new_remainder == 0

    def test_identical_returns_false_for_length_mismatch(self):
        old = chain("aaa", "bbb")
        new = chain("aaa", "bbb", "ccc")
        assert diverge.identical(old, new) is False


class TestSingleElementChains:
    """Edge cases with single-element chains."""

    def test_single_same(self):
        old = new = chain("aaa")
        assert diverge.identical(old, new) is True
        assert diverge.common_prefix(old, new) == old

    def test_single_different(self):
        old = chain("aaa")
        new = chain("xxx")
        result = diverge.find(old, new)
        assert result.divergence_index == 0
        assert result.common_prefix_length == 0
        assert result.old_remainder == 1
        assert result.new_remainder == 1

    def test_single_vs_empty(self):
        old = chain("aaa")
        new = []
        result = diverge.find(old, new)
        assert result.divergence_index == 0
        assert result.common_prefix_length == 0
        assert result.old_remainder == 1
        assert result.new_remainder == 0

    def test_empty_vs_single(self):
        old = []
        new = chain("aaa")
        result = diverge.find(old, new)
        assert result.divergence_index == 0
        assert result.common_prefix_length == 0
        assert result.old_remainder == 0
        assert result.new_remainder == 1


class TestResultConsistency:
    """Verify DivergenceResult fields are internally consistent."""

    @pytest.mark.parametrize("prefix_len,old_len,new_len", [
        (0, 3, 3),      # Diverge immediately, same length
        (2, 5, 4),      # Diverge at 2, old longer
        (3, 3, 5),      # Diverge at 3, new longer
        (5, 5, 5),      # Identical
        (0, 0, 3),      # Empty old
        (0, 3, 0),      # Empty new
        (0, 0, 0),      # Both empty
        (1, 1, 1),      # Single element identical
        (0, 1, 1),      # Single element different
        (10, 15, 12),   # Larger chains
    ])
    def test_result_invariants(self, prefix_len, old_len, new_len):
        """Verify result fields satisfy expected invariants."""
        common = [fp(f"c{i:03d}") for i in range(prefix_len)]
        old = common + [fp(f"o{i:03d}") for i in range(old_len - prefix_len)]
        new = common + [fp(f"n{i:03d}") for i in range(new_len - prefix_len)]

        result = diverge.find(old, new)

        # Invariant 1: common_prefix_length + remainder == original length
        assert result.common_prefix_length + result.old_remainder == len(old), \
            f"Failed for old: prefix={result.common_prefix_length} + remainder={result.old_remainder} != {len(old)}"
        assert result.common_prefix_length + result.new_remainder == len(new), \
            f"Failed for new: prefix={result.common_prefix_length} + remainder={result.new_remainder} != {len(new)}"

        # Invariant 2: divergence_index == common_prefix_length when divergent
        if result.divergence_index is not None:
            assert result.divergence_index == result.common_prefix_length, \
                f"divergence_index ({result.divergence_index}) != common_prefix_length ({result.common_prefix_length})"

        # Invariant 3: common_prefix matches
        expected_prefix = old[:result.common_prefix_length]
        actual_prefix = diverge.common_prefix(old, new)
        assert actual_prefix == expected_prefix, \
            f"common_prefix() returned {actual_prefix} but expected {expected_prefix}"

    def test_divergence_index_none_when_identical(self):
        old = new = chain("aaa", "bbb")
        result = diverge.find(old, new)
        assert result.divergence_index is None
        assert result.old_remainder == 0
        assert result.new_remainder == 0

    def test_divergence_index_none_implies_identical(self):
        """If divergence_index is None, chains must be identical."""
        old = new = chain("aaa", "bbb", "ccc")
        result = diverge.find(old, new)
        if result.divergence_index is None:
            assert old == new
            assert len(old) == len(new)
            assert result.old_remainder == 0
            assert result.new_remainder == 0


class TestPerformance:
    """Performance tests for large chains."""

    def test_large_identical_chains(self):
        """10k element identical chains should complete quickly."""
        old = new = [fp(f"elem{i:05d}") for i in range(10_000)]
        result = diverge.find(old, new)
        assert result.divergence_index is None
        assert result.common_prefix_length == 10_000
        assert result.old_remainder == 0
        assert result.new_remainder == 0

    def test_large_chains_diverge_at_end(self):
        """10k elements with divergence at end."""
        base = [fp(f"elem{i:05d}") for i in range(9_999)]
        old = base + [fp("old_end")]
        new = base + [fp("new_end")]
        result = diverge.find(old, new)
        assert result.divergence_index == 9_999
        assert result.common_prefix_length == 9_999
        assert result.old_remainder == 1
        assert result.new_remainder == 1

    def test_large_chains_diverge_at_start(self):
        """10k elements with immediate divergence."""
        old = [fp(f"old{i:05d}") for i in range(10_000)]
        new = [fp(f"new{i:05d}") for i in range(10_000)]
        result = diverge.find(old, new)
        assert result.divergence_index == 0
        assert result.common_prefix_length == 0
        assert result.old_remainder == 10_000
        assert result.new_remainder == 10_000

    def test_large_chains_diverge_middle(self):
        """10k elements with divergence at middle."""
        common = [fp(f"common{i:05d}") for i in range(5_000)]
        old = common + [fp(f"old{i:05d}") for i in range(5_000)]
        new = common + [fp(f"new{i:05d}") for i in range(5_000)]
        result = diverge.find(old, new)
        assert result.divergence_index == 5_000
        assert result.common_prefix_length == 5_000
        assert result.old_remainder == 5_000
        assert result.new_remainder == 5_000


class TestCommonPrefixFunction:
    """Dedicated tests for common_prefix() helper."""

    def test_empty_chains(self):
        assert diverge.common_prefix([], []) == []

    def test_no_common_prefix(self):
        old = chain("aaa", "bbb")
        new = chain("xxx", "yyy")
        assert diverge.common_prefix(old, new) == []

    def test_full_common_prefix_identical(self):
        old = new = chain("aaa", "bbb", "ccc")
        assert diverge.common_prefix(old, new) == old

    def test_partial_common_prefix(self):
        old = chain("aaa", "bbb", "ccc")
        new = chain("aaa", "bbb", "xxx")
        assert diverge.common_prefix(old, new) == chain("aaa", "bbb")

    def test_one_is_prefix_of_other(self):
        old = chain("aaa", "bbb")
        new = chain("aaa", "bbb", "ccc", "ddd")
        # Common prefix is the shorter chain
        assert diverge.common_prefix(old, new) == old

    def test_common_prefix_length_matches_divergence(self):
        """The length of common_prefix result should match common_prefix_length."""
        old = chain("aaa", "bbb", "ccc", "ddd")
        new = chain("aaa", "bbb", "xxx", "yyy")
        result = diverge.find(old, new)
        prefix = diverge.common_prefix(old, new)
        assert len(prefix) == result.common_prefix_length


class TestIdenticalFunction:
    """Dedicated tests for identical() helper."""

    def test_empty_chains_identical(self):
        assert diverge.identical([], []) is True

    def test_single_element_identical(self):
        old = new = chain("aaa")
        assert diverge.identical(old, new) is True

    def test_multiple_elements_identical(self):
        old = new = chain("aaa", "bbb", "ccc")
        assert diverge.identical(old, new) is True

    def test_different_at_start_not_identical(self):
        old = chain("aaa", "bbb")
        new = chain("xxx", "bbb")
        assert diverge.identical(old, new) is False

    def test_different_at_end_not_identical(self):
        old = chain("aaa", "bbb")
        new = chain("aaa", "xxx")
        assert diverge.identical(old, new) is False

    def test_different_lengths_not_identical(self):
        old = chain("aaa", "bbb")
        new = chain("aaa", "bbb", "ccc")
        assert diverge.identical(old, new) is False

    def test_empty_vs_non_empty_not_identical(self):
        assert diverge.identical([], chain("aaa")) is False
        assert diverge.identical(chain("aaa"), []) is False
