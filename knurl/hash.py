"""
Content-addressable hashing.

Produces deterministic hashes where the same content always gets the same hash.
The hash IS the address - use it for content-addressable storage and deduplication.

Four entry points, each a distinct interface (never a mode flag on another):
    - compute(str)        hash a string (UTF-8 encoded)
    - compute_bytes(bytes) hash a raw binary blob
    - compute_file(path)   stream-hash a file's bytes (bounded memory)
    - compute_tree(path)   canonical hash of a directory tree

All four share one output format - 'sha256:<hex>', or 'prefix:sha256:<hex>'
when a namespace prefix is given - so digests stay algorithm-qualified.

Usage:
    from knurl.hash import compute, compute_bytes, compute_file, compute_tree

    # Strings and bytes (compute(s) == compute_bytes(s.encode('utf-8')))
    compute("hello world")            # 'sha256:b94d27b9...'
    compute_bytes(b"\\x00\\x01\\x02")   # 'sha256:...'

    # Files (streamed - safe for multi-GB payloads)
    compute_file("video.mp4")         # 'sha256:...'

    # Directory trees (reproducible across machines)
    compute_tree("mirror/")           # 'sha256:...'

    # With namespace prefix
    compute("hello", prefix="config") # 'config:sha256:2cf24dba...'
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import stat
import unicodedata
from typing import Optional, Union

from . import canon


class HashError(Exception):
    """Raised when hashing fails.

    Common causes:
    - Invalid prefix format
    - Input is the wrong type
    - A file or tree cannot be read
    - Malformed hash string for verification
    """
    pass


# Read files in 1 MiB chunks so multi-gigabyte payloads (videos, disk images)
# are hashed with bounded memory rather than loaded all at once.
_FILE_CHUNK_SIZE = 1024 * 1024

# Open flags for hashing a single regular file. O_NONBLOCK stops a FIFO from
# blocking the open forever (we reject it after fstat, then clear O_NONBLOCK
# before reading); O_BINARY avoids newline translation on Windows. Both are
# absent on some platforms, hence getattr.
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_BINARY", 0) | _O_NONBLOCK
# O_NOFOLLOW lets the tree walk refuse a final-component symlink that was swapped
# in after classification (a file->symlink TOCTOU). Absent on some platforms.
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)

# fullmatch (not search/match with '$') so a trailing newline is rejected:
# re '$' matches just before a final '\n', which would let "ok\n" slip through.
_PREFIX_RE = re.compile(r'[a-zA-Z0-9_-]+')
_HEX_RE = re.compile(r'[0-9a-f]+')


def _normalize_prefix(prefix: Optional[str]) -> Optional[str]:
    """Validate a namespace prefix and normalize empty strings to None.

    Shared by every hashing entry point so their prefix rules cannot drift.

    Raises HashError if the prefix is the wrong type or contains characters
    outside [a-zA-Z0-9_-].
    """
    if prefix is None:
        return None
    if not isinstance(prefix, str):
        raise HashError(f"Prefix must be a string, got {type(prefix).__name__}")
    if prefix == "":
        return None
    if not _PREFIX_RE.fullmatch(prefix):
        raise HashError(
            f"Prefix must contain only alphanumeric characters, hyphens, and underscores. "
            f"Got: {prefix!r}"
        )
    return prefix


def _format_digest(hash_hex: str, prefix: Optional[str]) -> str:
    """Format a hex digest into the algorithm-qualified hash string."""
    if prefix:
        return f"{prefix}:sha256:{hash_hex}"
    return f"sha256:{hash_hex}"


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
            "For bytes use compute_bytes(); for files use compute_file()."
        )

    prefix = _normalize_prefix(prefix)

    # Compute SHA256 hash (UTF-8 encoding is deterministic). Call str.encode
    # explicitly rather than content.encode() so a str subclass cannot override
    # encode() to change the bytes we hash (which would break content-addressing)
    # or to raise a non-UnicodeEncodeError past the contract. A string holding a
    # lone surrogate (e.g. from os.fsdecode with surrogateescape) cannot be UTF-8
    # encoded - surface that as HashError, like the tree path, not a raw error.
    try:
        content_bytes = str.encode(content, 'utf-8')
    except UnicodeEncodeError as e:
        raise HashError(
            f"Content is not valid UTF-8 (lone surrogates?): {e}"
        ) from e
    hash_hex = hashlib.sha256(content_bytes).hexdigest()

    return _format_digest(hash_hex, prefix)


def compute_bytes(content: Union[bytes, bytearray, memoryview],
                  prefix: Optional[str] = None) -> str:
    """Compute a content-addressable hash for a raw binary blob.

    The bytes counterpart to compute(). Because compute() hashes the UTF-8
    encoding of its string, the two agree on text:
    compute_bytes(s.encode('utf-8')) == compute(s).

    Args:
        content: Raw bytes to hash. Accepts bytes, bytearray, or memoryview.
                 A str is rejected - use compute() for strings.
        prefix: Optional namespace prefix (same rules as compute()).

    Returns:
        A hash string: 'sha256:hexdigest' or 'prefix:sha256:hexdigest'.

    Raises:
        HashError: If content is not bytes-like or prefix is invalid.

    Examples:
        >>> compute_bytes(b"hello")
        'sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
    """
    if isinstance(content, str):
        raise HashError(
            "Content must be bytes, got str. Use compute() for strings, "
            "or encode to bytes first."
        )
    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise HashError(
            f"Content must be bytes-like (bytes, bytearray, memoryview), "
            f"got {type(content).__name__}."
        )

    prefix = _normalize_prefix(prefix)

    # A strided or non-byte-itemsize memoryview cannot be fed to hashlib
    # directly (it raises BufferError); copy out its logical bytes first. A
    # released or otherwise unusable buffer raises ValueError/BufferError here -
    # wrap those as HashError to honor the contract for this accepted type.
    try:
        if isinstance(content, memoryview) and (content.itemsize != 1 or not content.contiguous):
            content = content.tobytes()
        hash_hex = hashlib.sha256(content).hexdigest()
    except (ValueError, BufferError, TypeError) as e:
        raise HashError(f"Could not hash bytes content: {e}") from e
    return _format_digest(hash_hex, prefix)


def _file_digest(path: Union[str, os.PathLike], *, nofollow: bool) -> str:
    """Stream the SHA256 hex digest of a regular file.

    Opens with O_NONBLOCK and confirms (via fstat) the descriptor is a regular
    file before reading. This rejects FIFOs (which would otherwise block the
    open forever) and devices like /dev/zero (an infinite read) rather than
    hanging - compute_file is public and may be handed an untrusted path.

    When nofollow is True the open uses O_NOFOLLOW, so a final-component symlink
    is refused. The tree walk uses this to close a file->symlink TOCTOU: an
    entry classified as a regular file that is swapped for a symlink before it
    is opened raises rather than hashing the symlink's target.

    Reads in fixed-size chunks, so memory stays bounded for multi-GB files.

    Raises HashError if the path cannot be opened or is not a regular file.
    """
    flags = _OPEN_FLAGS
    if nofollow:
        flags |= _O_NOFOLLOW

    try:
        fd = os.open(path, flags)
    except OSError as e:
        raise HashError(f"Could not open file {os.fspath(path)!r}: {e}") from e

    try:
        try:
            is_regular = stat.S_ISREG(os.fstat(fd).st_mode)
        except OSError as e:
            raise HashError(f"Could not stat file {os.fspath(path)!r}: {e}") from e
        if not is_regular:
            raise HashError(
                f"Not a regular file (FIFO, socket, or device?): {os.fspath(path)!r}"
            )
        # O_NONBLOCK was only needed so the open() above could not hang on a
        # FIFO. Now that the fd is confirmed regular, clear it so the read loop
        # behaves like an ordinary blocking read - some filesystems (NFS, FUSE)
        # can return EAGAIN on a non-blocking regular-file read, which we do not
        # want to mistake for an error.
        if _O_NONBLOCK:
            try:
                os.set_blocking(fd, True)
            except OSError as e:
                raise HashError(
                    f"Could not configure file {os.fspath(path)!r}: {e}"
                ) from e
        hasher = hashlib.sha256()
        try:
            while True:
                chunk = os.read(fd, _FILE_CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
        except OSError as e:
            raise HashError(f"Could not read file {os.fspath(path)!r}: {e}") from e
    finally:
        # Suppress close errors: on a read-only fd they are benign, and letting
        # one raise from the finally would mask an in-flight HashError (e.g. the
        # wrapped read error above) and leak a raw OSError.
        try:
            os.close(fd)
        except OSError:
            pass

    return hasher.hexdigest()


def _resolve_path(path) -> Union[str, bytes]:
    """Convert path to a str/bytes via os.fspath, raising HashError for any
    unusable path input.

    compute_file/compute_tree document wrong/unusable path input as a HashError
    cause, matching compute()/compute_bytes(). Without this, the path-conversion
    boundary leaks non-HashError exceptions: a non-path type or a PathLike whose
    __fspath__ misbehaves raises TypeError; a path with an embedded null byte
    raises ValueError from os.open. Normalize all of those to HashError here, so
    callers can rely on the documented contract.
    """
    if not isinstance(path, (str, bytes, os.PathLike)):
        raise HashError(
            f"Path must be a string or path-like, got {type(path).__name__}."
        )
    try:
        # str/bytes pass through; a PathLike is converted via __fspath__, which
        # is the caller's code and may raise or return the wrong type - any such
        # failure means an unusable path, which is a HashError by contract.
        resolved = os.fspath(path)
    except Exception as e:
        raise HashError(f"Invalid path: {e}") from e
    if (isinstance(resolved, str) and "\x00" in resolved) or (
        isinstance(resolved, bytes) and b"\x00" in resolved
    ):
        raise HashError("Invalid path: embedded null byte.")
    return resolved


def compute_file(path: Union[str, os.PathLike], prefix: Optional[str] = None) -> str:
    """Compute a content-addressable hash for a file's bytes.

    The file is read in fixed-size chunks and never loaded into memory in
    full, so it is safe for multi-gigabyte payloads. The result matches
    compute_bytes() over the same byte content.

    A symlink to a regular file is followed and hashed. Non-regular files
    (FIFOs, sockets, devices) are rejected rather than blocked on, so passing
    an untrusted path cannot hang the process.

    Args:
        path: Path to a readable regular file (or a symlink to one).
        prefix: Optional namespace prefix (same rules as compute()).

    Returns:
        A hash string: 'sha256:hexdigest' or 'prefix:sha256:hexdigest'.

    Raises:
        HashError: If prefix is invalid, or the file cannot be read
                   (missing, a directory, a non-regular file, permission
                   denied, etc.).

    Examples:
        >>> compute_file("hello.txt")
        'sha256:...'
    """
    path = _resolve_path(path)
    prefix = _normalize_prefix(prefix)
    return _format_digest(_file_digest(path, nofollow=False), prefix)


def compute_tree(path: Union[str, os.PathLike], prefix: Optional[str] = None) -> str:
    """Compute a canonical, reproducible hash of a directory tree.

    The same tree of files always hashes identically across machines and runs,
    which makes the digest usable for version dedup (same hash = same content,
    different hash = new version).

    The scheme:
      - Walk the tree, building a manifest mapping each entry's relative path
        to a typed descriptor.
      - Paths are relative to ``path``, use POSIX '/' separators, and are
        Unicode-normalized to NFC so a name stored decomposed on one OS
        (e.g. macOS) matches the same name stored composed on another (Linux).
      - Regular files map to {"type": "file", "hash": compute_file(entry)}.
        Symlinks map to {"type": "symlink", "target": <normalized target>} -
        the target is recorded, never followed. The typed descriptor keeps a
        file whose contents are "../x" from colliding with a symlink to "../x".
      - File mode / executable bit is not included: content only.
      - Empty subdirectories contribute nothing (like git, which tracks files,
        not directories). A tree with at least one symlink is non-empty even
        if it has no regular files.
      - The manifest is serialized with canon (sorted keys, no whitespace) and
        the resulting bytes are hashed with compute_bytes().

    Root symlinks: if ``path`` itself is a symlink to a directory it is
    followed, exactly as tar, git, or cd would follow the path you hand them -
    the caller chose it. Only symlinks discovered *inside* the tree are
    recorded rather than followed. Pass ``Path(path).resolve()`` if you need
    the root resolved explicitly.

    Concurrency: the digest reflects the tree as it is read. Hashing a tree
    that is being modified concurrently is out of scope - the result may
    reflect an intermediate state. O_NOFOLLOW/O_NONBLOCK opens defend against
    the cheap file<->symlink and special-file swaps, but a hash of a live,
    adversarially-mutating tree is not guaranteed to match any single snapshot.
    (O_NOFOLLOW is POSIX-only; where it is unavailable, e.g. Windows, the
    file->symlink swap defense is inactive.)

    Args:
        path: Path to a directory (str or PathLike; bytes paths are rejected).
        prefix: Optional namespace prefix applied to the final tree digest only
                (inner file digests are unprefixed).

    Returns:
        A hash string: 'sha256:hexdigest' or 'prefix:sha256:hexdigest'.

    Raises:
        HashError: If prefix is invalid, the path is a bytes path or not a
                   directory, a directory cannot be read, the tree contains no
                   entries (empty tree), a non-regular file (FIFO, socket,
                   device) is encountered, an entry has a name or symlink target
                   that is not valid UTF-8, or an entry cannot be read.
    """
    prefix = _normalize_prefix(prefix)

    root = _resolve_path(path)
    if isinstance(root, bytes):
        raise HashError(
            "compute_tree requires a string path, got bytes. "
            "Decode it first, e.g. compute_tree(path.decode())."
        )
    if not os.path.isdir(root):
        raise HashError(
            f"compute_tree requires a directory, got {root!r}. "
            "Use compute_file() for files."
        )

    manifest: dict[str, dict[str, str]] = {}
    # Normalized relative paths claimed so far - across files, symlinks, AND
    # directories. Two distinct on-disk names that normalize to the same NFC
    # path must be refused, not collapsed by walk order. Tracking directories
    # too is essential: sibling dirs like "café" and "café" with
    # *different* children produce non-colliding leaf keys, so without this they
    # would merge into one logical directory and two distinct trees would hash
    # identically.
    seen: set[str] = set()

    def _on_walk_error(err: OSError) -> None:
        # os.walk swallows scandir errors by default, which would silently omit
        # an unreadable subtree and hash incomplete content as if complete.
        # Raising here surfaces it instead.
        raise HashError(f"Could not read directory while walking tree: {err}") from err

    def _rel_key(abs_path: str, what: str) -> str:
        """Relative POSIX path of abs_path under root, NFC-normalized.

        A non-UTF-8 name decodes (via surrogateescape) to lone surrogates.
        normalize() passes those through, but they cannot be UTF-8 encoded for
        hashing - surface a clear HashError now rather than letting a
        UnicodeEncodeError later escape from serialization.
        """
        rel_posix = os.path.relpath(abs_path, root).replace(os.sep, "/")
        try:
            rel_posix.encode("utf-8")
        except UnicodeEncodeError as e:
            raise HashError(
                f"Cannot hash {what} with a non-UTF-8 name: {abs_path!r} ({e})"
            ) from e
        return unicodedata.normalize("NFC", rel_posix)

    def _claim(key: str) -> None:
        if key in seen:
            raise HashError(
                f"Path collision after NFC normalization: {key!r}. Two distinct "
                f"entries normalize to the same name; the tree cannot be hashed "
                f"reproducibly."
            )
        seen.add(key)

    # followlinks=False: symlinked directories are recorded as symlink entries
    # below rather than descended into (avoids cycles and escaping the tree).
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=_on_walk_error):
        # Claim each real directory's normalized path (the root itself is rel
        # ".", skipped) so colliding sibling directories are caught.
        if dirpath != root:
            _claim(_rel_key(dirpath, "directory"))

        # Symlinked directories appear in dirnames; record them as symlinks.
        entries = [os.path.join(dirpath, name) for name in filenames]
        entries += [
            os.path.join(dirpath, name)
            for name in dirnames
            if os.path.islink(os.path.join(dirpath, name))
        ]

        for full in entries:
            key = _rel_key(full, "entry")
            _claim(key)

            # islink must be checked before isfile: isfile follows symlinks,
            # so a symlink to a file would otherwise be treated as the file.
            if os.path.islink(full):
                try:
                    target = os.readlink(full)
                except OSError as e:
                    raise HashError(f"Could not read symlink {full!r}: {e}") from e
                # Normalize the target the same way as paths (POSIX separators,
                # then NFC) so symlinked trees hash identically across platforms.
                target = target.replace(os.sep, "/")
                try:
                    target.encode("utf-8")
                except UnicodeEncodeError as e:
                    raise HashError(
                        f"Cannot hash symlink with a non-UTF-8 target: {full!r} ({e})"
                    ) from e
                target = unicodedata.normalize("NFC", target)
                manifest[key] = {"type": "symlink", "target": target}
            elif os.path.isfile(full):
                # nofollow: if this entry was swapped for a symlink after the
                # islink check above, refuse it rather than hash its target.
                manifest[key] = {
                    "type": "file",
                    "hash": _format_digest(_file_digest(full, nofollow=True), None),
                }
            else:
                raise HashError(
                    f"Unsupported non-regular file in tree (FIFO, socket, or "
                    f"device?): {full!r}"
                )

    if not manifest:
        raise HashError(f"Tree contains no entries (no files or symlinks): {root!r}")

    serialized = canon.serialize(manifest)
    return compute_bytes(serialized, prefix=prefix)


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
        # Apply the same charset as _normalize_prefix, so verify() rejects a
        # malformed prefix here with a clear message instead of letting it
        # surface confusingly from compute()'s prefix validation.
        if not _PREFIX_RE.fullmatch(prefix):
            raise HashError(
                f"Invalid hash format: prefix {prefix!r} contains illegal "
                f"characters. Got: {hash_string!r}"
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

    # Validate digest is hex (fullmatch so a trailing newline is rejected)
    if not _HEX_RE.fullmatch(digest):
        raise HashError(
            f"Invalid SHA256 digest. Must contain only lowercase hex characters."
        )


def _extract_prefix(hash_string: str) -> Optional[str]:
    """Extract prefix from hash string, if present."""
    parts = hash_string.split(":")
    if len(parts) == 3:
        return parts[0]
    return None
