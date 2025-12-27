"""
Content-addressable hashing for canonical strings.

Produces deterministic hashes where the same content always gets the same hash.
The hash IS the address - use it for content-addressable storage and deduplication.

Usage:
    from knurl.hash import compute, verify, HashError

    # Basic hashing
    content_hash = compute("hello world")  # 'sha256:b94d27b9...'

    # With namespace prefix
    content_hash = compute("hello", prefix="config")  # 'config:sha256:2cf24dba...'

    # Verify content matches hash
    verify("hello", hash_string)  # True/False
"""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Optional


class HashError(Exception):
    """Raised when hashing fails.

    Common causes:
    - Invalid prefix format
    - Input is not a string
    - Malformed hash string for verification
    """
    pass


def compute(content: str, prefix: Optional[str] = None) -> str:
    """Compute a content-addressable hash for a string.

    Args:
        content: The string content to hash. Must be a string (not bytes).
        prefix: Optional namespace prefix (e.g., 'config', 'schedule').
                Must contain only alphanumeric chars, hyphens, underscores.

    Returns:
        A hash string in format:
        - Without prefix: 'sha256:hexdigest'
        - With prefix: 'prefix:sha256:hexdigest'

    Raises:
        HashError: If content is not a string or prefix is invalid.

    Examples:
        >>> compute("hello")
        'sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'

        >>> compute("hello", prefix="config")
        'config:sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
    """
    # Validate content type
    if not isinstance(content, str):
        raise HashError(
            f"Content must be a string, got {type(content).__name__}. "
            "For bytes, decode to string first."
        )

    # Validate prefix if provided
    if prefix is not None:
        if not isinstance(prefix, str):
            raise HashError(f"Prefix must be a string, got {type(prefix).__name__}")
        # Empty string treated as no prefix
        if prefix == "":
            prefix = None
        elif not re.match(r'^[a-zA-Z0-9_-]+$', prefix):
            raise HashError(
                f"Prefix must contain only alphanumeric characters, hyphens, and underscores. "
                f"Got: {prefix!r}"
            )

    # Compute SHA256 hash (UTF-8 encoding is deterministic)
    content_bytes = content.encode('utf-8')
    hash_hex = hashlib.sha256(content_bytes).hexdigest()

    # Format output
    if prefix:
        return f"{prefix}:sha256:{hash_hex}"
    return f"sha256:{hash_hex}"


def verify(content: str, hash_string: str) -> bool:
    """Verify that content matches an expected hash.

    Args:
        content: The string content to verify.
        hash_string: The expected hash string.

    Returns:
        True if the computed hash matches, False otherwise.

    Raises:
        HashError: If hash_string format is invalid.

    Example:
        >>> h = compute("hello")
        >>> verify("hello", h)
        True
        >>> verify("world", h)
        False
    """
    # Validate hash string format
    _validate_hash_string(hash_string)

    # Extract prefix if present
    prefix = _extract_prefix(hash_string)

    # Compute and compare using constant-time comparison
    # to prevent timing attacks that could leak hash information
    computed = compute(content, prefix=prefix)
    return hmac.compare_digest(computed, hash_string)


def _validate_hash_string(hash_string: str) -> None:
    """Validate hash string format.

    Raises HashError if format is invalid.
    """
    if not isinstance(hash_string, str):
        raise HashError(f"Hash string must be a string, got {type(hash_string).__name__}")

    parts = hash_string.split(":")

    if len(parts) == 2:
        # Format: algorithm:digest
        algorithm, digest = parts
        prefix = None
    elif len(parts) == 3:
        # Format: prefix:algorithm:digest
        prefix, algorithm, digest = parts
        # Validate prefix is not empty
        if not prefix:
            raise HashError(
                f"Invalid hash format: empty prefix. Got: {hash_string!r}"
            )
    else:
        raise HashError(
            f"Invalid hash format. Expected 'algorithm:digest' or "
            f"'prefix:algorithm:digest', got: {hash_string!r}"
        )

    # Validate algorithm
    if algorithm != "sha256":
        raise HashError(f"Unknown hash algorithm: {algorithm!r}. Only 'sha256' is supported.")

    # Validate digest length
    if len(digest) != 64:
        raise HashError(
            f"Invalid SHA256 digest length. Expected 64 characters, got {len(digest)}."
        )

    # Validate digest is hex
    if not re.match(r'^[0-9a-f]+$', digest):
        raise HashError(
            f"Invalid SHA256 digest. Must contain only lowercase hex characters."
        )


def _extract_prefix(hash_string: str) -> Optional[str]:
    """Extract prefix from hash string, if present."""
    parts = hash_string.split(":")
    if len(parts) == 3:
        return parts[0]
    return None
