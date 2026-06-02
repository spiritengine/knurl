"""Property-based invariants for knurl.hash primitives (the Oracle's gauntlet).

These pin the mathematical properties that must hold for *all* inputs, not just
the hand-picked cases in test_hash_bytes_file_tree.py.
"""

import os
import unittest.mock as mock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import knurl.hash as kh
from knurl.hash import compute, compute_bytes, compute_file, compute_tree, HashError


# Prefixes that _normalize_prefix accepts.
_prefixes = st.from_regex(r"[a-zA-Z0-9_-]+", fullmatch=True)


@given(st.text())
def test_compute_bytes_agrees_with_compute(s):
    """For any string s: compute_bytes(s.encode('utf-8')) == compute(s).

    st.text() can produce lone surrogates, which are not UTF-8 encodable. Both
    sides must refuse those: s.encode() raises UnicodeEncodeError, and compute()
    wraps it as HashError. Cover that branch rather than letting the test error.
    """
    try:
        encoded = s.encode("utf-8")
    except UnicodeEncodeError:
        with pytest.raises(HashError):
            compute(s)
        return
    assert compute_bytes(encoded) == compute(s)


@given(st.binary(max_size=4096))
def test_compute_file_equals_compute_bytes(content):
    """compute_file(path) == compute_bytes(content) when the file holds content.

    Uses a fresh temp file per example (hypothesis @given cannot take a
    function-scoped fixture like tmp_path).
    """
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(content)
        name = f.name
    try:
        assert compute_file(name) == compute_bytes(content)
    finally:
        os.unlink(name)


@given(st.binary(max_size=1024), _prefixes)
def test_prefix_wraps_outer_digest_only(content, prefix):
    """A prefixed digest shares the same hex as the unprefixed digest."""
    plain = compute_bytes(content)
    prefixed = compute_bytes(content, prefix=prefix)
    assert prefixed == f"{prefix}:{plain}"
    assert plain.split(":")[-1] == prefixed.split(":")[-1]


@given(st.binary(max_size=256))
def test_empty_prefix_equals_no_prefix(content):
    assert compute_bytes(content, prefix="") == compute_bytes(content, prefix=None)
    assert compute_bytes(content, prefix="") == compute_bytes(content)


def test_chunk_size_does_not_affect_file_digest(tmp_path):
    """Varying the read chunk size must not change compute_file's output."""
    content = os.urandom(2 * 1024 * 1024 + 13)
    p = tmp_path / "f.bin"
    p.write_bytes(content)
    expected = compute_bytes(content)

    original = kh._FILE_CHUNK_SIZE
    try:
        for chunk_size in (1, 7, 512, 4096, 1024 * 1024, 4 * 1024 * 1024):
            kh._FILE_CHUNK_SIZE = chunk_size
            assert compute_file(p) == expected, f"diverged at chunk_size={chunk_size}"
    finally:
        kh._FILE_CHUNK_SIZE = original


def test_tree_digest_independent_of_walk_order(tmp_path):
    """compute_tree gives the same digest regardless of os.walk ordering."""
    root = tmp_path / "t"
    for i in range(20):
        sub = root / f"dir_{i % 4}"
        (sub).mkdir(parents=True, exist_ok=True)
        (sub / f"file_{i:03d}.bin").write_bytes(f"content-{i}".encode())

    baseline = compute_tree(root)

    real_walk = os.walk

    def reversed_walk(path, *args, **kwargs):
        for dirpath, dirnames, filenames in real_walk(path, *args, **kwargs):
            dirnames[:] = list(reversed(dirnames))
            yield dirpath, dirnames, list(reversed(filenames))

    with mock.patch("knurl.hash.os.walk", reversed_walk):
        reordered = compute_tree(root)

    assert baseline == reordered


def test_tree_prefix_wraps_outer_digest_only(tmp_path):
    root = tmp_path / "t"
    (root).mkdir()
    (root / "a.txt").write_bytes(b"content")
    plain = compute_tree(root)
    prefixed = compute_tree(root, prefix="ns")
    assert prefixed == f"ns:{plain}"
    assert plain.split(":")[-1] == prefixed.split(":")[-1]
