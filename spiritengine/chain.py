"""
Chain fingerprinting for execution plan caching.

Computes fingerprints for chains of steps where each step's fingerprint depends on:
1. Its own config (a dict)
2. The previous step's fingerprint

This creates a Merkle-like chain where changing any step invalidates all subsequent
steps - exactly the property needed for execution plan caching.

Design based on research into:
- Merkle trees (domain separation, cascade property)
- Git commit chaining (parent hash as input data)
- Docker layer caching (ChainID formula)

Usage:
    from spiritengine import chain

    # Batch: fingerprint entire chain at once
    steps = [config1, config2, config3, config4]
    fingerprints = chain.fingerprint(steps)
    # Returns: ['sha256:aaa...', 'sha256:bbb...', 'sha256:ccc...', 'sha256:ddd...']

    # Incremental: build one step at a time
    fp = chain.fingerprint_step(config, previous_fingerprint=None)
    fp2 = chain.fingerprint_step(config2, previous_fingerprint=fp)

Key properties:
    - Deterministic: same input always produces same output
    - Chain dependency: fingerprint[i] = hash(config[i] + fingerprint[i-1])
    - Position sensitive: same config at different positions produces different fingerprints
    - Cascade invalidation: changing step N invalidates fingerprints N, N+1, N+2, ...

Note on Unicode:
    Configs are hashed as raw bytes without Unicode normalization. This means
    visually identical strings with different Unicode representations (e.g.,
    'café' as U+00E9 vs 'café' as e + U+0301 combining accent) will produce
    different fingerprints. If your configs may contain text from varying
    sources, normalize to a consistent form (e.g., NFC) before fingerprinting.
"""

from __future__ import annotations

from typing import Optional

from . import canon, hash as ledger_hash
from .canon import CanonError
from .hash import HashError


class ChainError(Exception):
    """Raised when chain fingerprinting fails.

    Common causes:
    - Invalid config (not a dict, contains non-JSON types)
    - Invalid previous_fingerprint format
    - Configs containing NaN, Infinity, or circular references
    """
    pass


def fingerprint_step(config: dict, previous_fingerprint: Optional[str] = None) -> str:
    """Compute fingerprint for a single step in a chain.

    The fingerprint depends on both the config content and the previous step's
    fingerprint (if any), creating the chain dependency.

    Args:
        config: The step configuration. Must be a JSON-serializable dict.
        previous_fingerprint: The fingerprint of the previous step, or None
            for the first step in a chain.

    Returns:
        A fingerprint string in format 'sha256:hexdigest'.

    Raises:
        ChainError: If config is invalid or previous_fingerprint format is wrong.

    Example:
        >>> fp1 = fingerprint_step({"action": "build"})
        >>> fp2 = fingerprint_step({"action": "test"}, previous_fingerprint=fp1)
    """
    # Validate config type
    if not isinstance(config, dict):
        raise ChainError(
            f"Config must be a dict, got {type(config).__name__}"
        )

    # Validate previous_fingerprint format if provided
    if previous_fingerprint is not None:
        if not isinstance(previous_fingerprint, str):
            raise ChainError(
                f"previous_fingerprint must be a string, got {type(previous_fingerprint).__name__}"
            )
        # Validate it looks like a hash
        if not previous_fingerprint.startswith("sha256:"):
            raise ChainError(
                f"Invalid previous_fingerprint format. Expected 'sha256:hexdigest', "
                f"got: {previous_fingerprint!r}"
            )
        parts = previous_fingerprint.split(":")
        if len(parts) != 2 or len(parts[1]) != 64:
            raise ChainError(
                f"Invalid previous_fingerprint format. Expected 64-char hex digest, "
                f"got: {previous_fingerprint!r}"
            )
        # Validate hex characters (must be lowercase to match our output format)
        # Note: can't use islower() because digit-only strings return False
        digest = parts[1]
        if not all(c in '0123456789abcdef' for c in digest):
            raise ChainError(
                f"Invalid previous_fingerprint format. Digest must be lowercase hexadecimal, "
                f"got: {previous_fingerprint!r}"
            )

    # Serialize config to canonical JSON bytes
    try:
        canonical_bytes = canon.serialize(config)
    except CanonError as e:
        raise ChainError(f"Cannot serialize config: {e}") from e
    except TypeError as e:
        raise ChainError(f"Config contains non-JSON-serializable type: {e}") from e

    # Convert to string for hashing
    canonical_str = canonical_bytes.decode('utf-8')

    # Build the hash input
    # Format: "previous_fingerprint:canonical_json" or just "canonical_json" for first step
    # The colon separator ensures no ambiguity between previous hash and config
    if previous_fingerprint is not None:
        hash_input = f"{previous_fingerprint}:{canonical_str}"
    else:
        hash_input = canonical_str

    # Compute hash
    try:
        return ledger_hash.compute(hash_input)
    except HashError as e:
        raise ChainError(f"Hash computation failed: {e}") from e


def fingerprint(steps: list[dict]) -> list[str]:
    """Compute fingerprints for a chain of steps.

    Each fingerprint depends on its config and the previous fingerprint,
    creating a chain where changing any step invalidates all subsequent steps.

    Args:
        steps: List of step configurations. Each must be a JSON-serializable dict.

    Returns:
        List of fingerprint strings, one per step. Same length as input.
        Empty list if input is empty.

    Raises:
        ChainError: If input is not a list or any config is invalid.

    Example:
        >>> configs = [{"action": "build"}, {"action": "test"}, {"action": "deploy"}]
        >>> fps = fingerprint(configs)
        >>> len(fps)
        3
        >>> fps[0] != fps[1] != fps[2]  # All different
        True
    """
    # Validate input type
    if not isinstance(steps, list):
        raise ChainError(
            f"Steps must be a list, got {type(steps).__name__}"
        )

    # Handle empty chain
    if not steps:
        return []

    # Build fingerprints incrementally
    fingerprints = []
    previous = None

    for i, config in enumerate(steps):
        try:
            fp = fingerprint_step(config, previous_fingerprint=previous)
        except ChainError:
            raise  # Re-raise with original message
        except Exception as e:
            raise ChainError(f"Error fingerprinting step {i}: {e}") from e

        fingerprints.append(fp)
        previous = fp

    return fingerprints
