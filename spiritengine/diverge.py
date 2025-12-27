"""
Divergence detection for fingerprint chains.

Compares two fingerprint chains and identifies where they diverge. This enables:
- Cache reuse detection (how much of a previous run can be reused)
- Cache invalidation point detection (where to start rebuilding)
- Change analysis (what changed between runs)

Usage:
    from spiritengine import diverge

    # Compare two fingerprint chains
    old_fps = ['sha256:aaa', 'sha256:bbb', 'sha256:ccc', 'sha256:ddd']
    new_fps = ['sha256:aaa', 'sha256:bbb', 'sha256:xxx', 'sha256:yyy']

    result = diverge.find(old_fps, new_fps)
    # Returns: DivergenceResult(
    #   divergence_index=2,        # First index where they differ
    #   common_prefix_length=2,    # Steps 0-1 are identical
    #   old_remainder=2,           # Steps 2-3 in old
    #   new_remainder=2,           # Steps 2-3 in new
    # )

    # Check if chains are identical
    if diverge.identical(old_fps, new_fps):
        print('No changes')

    # Get common prefix
    common = diverge.common_prefix(old_fps, new_fps)
    # Returns: ['sha256:aaa', 'sha256:bbb']

Design based on research into:
- Docker layer cache comparison (cascade invalidation)
- Git merge-base detection (finding divergence points)
- Longest common prefix algorithms (efficient comparison)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DivergenceResult:
    """Result of comparing two fingerprint chains.

    Attributes:
        divergence_index: Index of first differing element, or None if chains
            are identical. If 0, chains differ immediately. If None, chains
            are completely identical.
        common_prefix_length: Number of elements that match from the start.
            Equal to divergence_index when chains diverge, or len(chain) when
            identical.
        old_remainder: Number of elements remaining in old chain after the
            common prefix. Zero if old is prefix of new or chains are identical.
        new_remainder: Number of elements remaining in new chain after the
            common prefix. Zero if new is prefix of old or chains are identical.

    Invariants:
        - common_prefix_length + old_remainder == len(old)
        - common_prefix_length + new_remainder == len(new)
        - divergence_index == common_prefix_length when chains diverge
        - divergence_index is None when chains are identical
    """

    divergence_index: int | None
    common_prefix_length: int
    old_remainder: int
    new_remainder: int


def find(old: list[str], new: list[str]) -> DivergenceResult:
    """Find where two fingerprint chains diverge.

    Compares chains element-by-element to find the first position where they
    differ. This uses the same cascade invalidation principle as Docker layer
    caching: once chains diverge, all subsequent elements are considered
    different.

    Args:
        old: The original fingerprint chain
        new: The new fingerprint chain

    Returns:
        DivergenceResult describing where and how the chains differ.

    Example:
        >>> old = ['sha256:aaa', 'sha256:bbb', 'sha256:ccc']
        >>> new = ['sha256:aaa', 'sha256:bbb', 'sha256:xxx']
        >>> result = find(old, new)
        >>> result.divergence_index
        2
        >>> result.common_prefix_length
        2
        >>> result.old_remainder
        1
        >>> result.new_remainder
        1
    """
    # Compare element-by-element until we find a mismatch
    common_len = 0
    for o, n in zip(old, new):
        if o != n:
            # Found divergence point
            return DivergenceResult(
                divergence_index=common_len,
                common_prefix_length=common_len,
                old_remainder=len(old) - common_len,
                new_remainder=len(new) - common_len,
            )
        common_len += 1

    # No mismatch found in overlapping portion
    # Check if one is a prefix of the other, or they're identical
    if len(old) == len(new):
        # Chains are completely identical
        return DivergenceResult(
            divergence_index=None,
            common_prefix_length=len(old),
            old_remainder=0,
            new_remainder=0,
        )
    elif len(old) > len(new):
        # New is a prefix of old (old has extra elements)
        return DivergenceResult(
            divergence_index=len(new),
            common_prefix_length=len(new),
            old_remainder=len(old) - len(new),
            new_remainder=0,
        )
    else:
        # Old is a prefix of new (new has extra elements)
        return DivergenceResult(
            divergence_index=len(old),
            common_prefix_length=len(old),
            old_remainder=0,
            new_remainder=len(new) - len(old),
        )


def identical(old: list[str], new: list[str]) -> bool:
    """Check if two fingerprint chains are identical.

    A quick check that returns True only if the chains are exactly the same
    length and all elements match.

    Args:
        old: First fingerprint chain
        new: Second fingerprint chain

    Returns:
        True if chains are identical, False if they differ in any way

    Example:
        >>> identical(['sha256:aaa'], ['sha256:aaa'])
        True
        >>> identical(['sha256:aaa'], ['sha256:bbb'])
        False
        >>> identical(['sha256:aaa'], ['sha256:aaa', 'sha256:bbb'])
        False
    """
    return find(old, new).divergence_index is None


def common_prefix(old: list[str], new: list[str]) -> list[str]:
    """Extract the common prefix of two fingerprint chains.

    Returns the portion of the chains that match from the beginning. This
    represents the cached work that can be reused.

    Args:
        old: First fingerprint chain
        new: Second fingerprint chain

    Returns:
        List of fingerprints that match at the start of both chains.
        Empty list if chains diverge immediately.

    Example:
        >>> old = ['sha256:aaa', 'sha256:bbb', 'sha256:ccc']
        >>> new = ['sha256:aaa', 'sha256:bbb', 'sha256:xxx']
        >>> common_prefix(old, new)
        ['sha256:aaa', 'sha256:bbb']
    """
    result = find(old, new)
    return old[:result.common_prefix_length]
