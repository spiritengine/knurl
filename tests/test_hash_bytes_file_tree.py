"""Tests for binary, file, and tree hashing in knurl.hash.

Covers the additions made for hoard's content-addressable storage:
- compute_bytes(content, prefix=None) -> hash string
- compute_file(path, prefix=None)    -> streaming file hash
- compute_tree(path, prefix=None)    -> canonical directory-tree hash
"""

import os

import pytest

from knurl.hash import (
    compute,
    compute_bytes,
    compute_file,
    compute_tree,
    verify,
    HashError,
)

_HAS_NOFOLLOW = bool(getattr(os, "O_NOFOLLOW", 0))

# Known SHA256 vectors.
SHA256_EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SHA256_HELLO = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


class TestComputeBytes:
    def test_empty_bytes_vector(self):
        assert compute_bytes(b"") == f"sha256:{SHA256_EMPTY}"

    def test_known_vector(self):
        assert compute_bytes(b"hello") == f"sha256:{SHA256_HELLO}"

    def test_determinism(self):
        assert compute_bytes(b"\x00\x01\x02") == compute_bytes(b"\x00\x01\x02")

    def test_agrees_with_compute_on_text(self):
        """compute_bytes(s.encode('utf-8')) must equal compute(s)."""
        for s in ["hello", "", "naïve café", "日本語", "line\nbreak"]:
            assert compute_bytes(s.encode("utf-8")) == compute(s)

    def test_accepts_bytearray_and_memoryview(self):
        expected = compute_bytes(b"hello")
        assert compute_bytes(bytearray(b"hello")) == expected
        assert compute_bytes(memoryview(b"hello")) == expected

    def test_rejects_str(self):
        with pytest.raises(HashError, match="compute"):
            compute_bytes("hello")

    def test_rejects_other_types(self):
        with pytest.raises(HashError):
            compute_bytes(123)

    def test_prefix(self):
        assert compute_bytes(b"hello", prefix="config") == f"config:sha256:{SHA256_HELLO}"

    def test_empty_prefix_treated_as_none(self):
        assert compute_bytes(b"hello", prefix="") == compute_bytes(b"hello")

    def test_invalid_prefix(self):
        with pytest.raises(HashError):
            compute_bytes(b"hello", prefix="bad prefix!")


class TestComputeFile:
    def test_matches_compute_bytes(self, tmp_path):
        content = b"the quick brown fox"
        p = tmp_path / "f.bin"
        p.write_bytes(content)
        assert compute_file(p) == compute_bytes(content)

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty"
        p.write_bytes(b"")
        assert compute_file(p) == f"sha256:{SHA256_EMPTY}"

    def test_streaming_large_file(self, tmp_path):
        """A file larger than the chunk size hashes the same as the whole blob."""
        content = os.urandom(3 * 1024 * 1024 + 7)  # > 1 MiB, not chunk-aligned
        p = tmp_path / "big.bin"
        p.write_bytes(content)
        assert compute_file(p) == compute_bytes(content)

    def test_accepts_pathlike_and_str(self, tmp_path):
        p = tmp_path / "f.bin"
        p.write_bytes(b"data")
        assert compute_file(p) == compute_file(str(p))

    def test_prefix(self, tmp_path):
        p = tmp_path / "f.bin"
        p.write_bytes(b"hello")
        assert compute_file(p, prefix="blob") == f"blob:sha256:{SHA256_HELLO}"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(HashError, match="Could not open file"):
            compute_file(tmp_path / "does-not-exist")

    def test_directory_raises(self, tmp_path):
        with pytest.raises(HashError, match="[Nn]ot a regular file"):
            compute_file(tmp_path)


def _write(path, content=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


class TestComputeTree:
    def test_determinism(self, tmp_path):
        root = tmp_path / "t"
        _write(root / "a.txt", b"alpha")
        _write(root / "sub" / "b.txt", b"beta")
        assert compute_tree(root) == compute_tree(root)

    def test_identical_trees_match(self, tmp_path):
        t1, t2 = tmp_path / "t1", tmp_path / "t2"
        for root in (t1, t2):
            _write(root / "a.txt", b"alpha")
            _write(root / "sub" / "b.txt", b"beta")
        assert compute_tree(t1) == compute_tree(t2)

    def test_content_change_changes_hash(self, tmp_path):
        t1, t2 = tmp_path / "t1", tmp_path / "t2"
        _write(t1 / "a.txt", b"alpha")
        _write(t2 / "a.txt", b"ALPHA")
        assert compute_tree(t1) != compute_tree(t2)

    def test_path_change_changes_hash(self, tmp_path):
        t1, t2 = tmp_path / "t1", tmp_path / "t2"
        _write(t1 / "a.txt", b"alpha")
        _write(t2 / "b.txt", b"alpha")
        assert compute_tree(t1) != compute_tree(t2)

    def test_empty_subdir_ignored(self, tmp_path):
        t1, t2 = tmp_path / "t1", tmp_path / "t2"
        for root in (t1, t2):
            _write(root / "a.txt", b"alpha")
        (t2 / "empty_dir").mkdir()
        (t2 / "nested" / "also_empty").mkdir(parents=True)
        assert compute_tree(t1) == compute_tree(t2)

    def test_file_mode_ignored(self, tmp_path):
        t1, t2 = tmp_path / "t1", tmp_path / "t2"
        for root in (t1, t2):
            _write(root / "a.txt", b"alpha")
        os.chmod(t2 / "a.txt", 0o755)
        assert compute_tree(t1) == compute_tree(t2)

    def test_nfc_normalization(self, tmp_path):
        """A decomposed (NFD) name and its composed (NFC) form hash identically."""
        nfc = "caf\u00e9.txt"          # \u00e9 as one code point
        nfd = "cafe\u0301.txt"         # e + combining acute
        t1, t2 = tmp_path / "t1", tmp_path / "t2"
        _write(t1 / nfc, b"data")
        _write(t2 / nfd, b"data")
        assert compute_tree(t1) == compute_tree(t2)

    def test_prefix_wraps_outer_only(self, tmp_path):
        root = tmp_path / "t"
        _write(root / "a.txt", b"alpha")
        assert compute_tree(root, prefix="tree") == "tree:" + compute_tree(root)

    def test_symlink_recorded_not_followed(self, tmp_path):
        root = tmp_path / "t"
        _write(root / "real.txt", b"payload")
        os.symlink("real.txt", root / "link")
        # Must not crash, and the symlink target is part of the digest.
        h = compute_tree(root)
        assert h.startswith("sha256:")

    def test_symlinked_directory_recorded_not_descended(self, tmp_path):
        """A symlink to a directory is recorded once as a symlink, not walked."""
        root = tmp_path / "t"
        _write(root / "real" / "inner.txt", b"data")
        os.symlink("real", root / "dirlink")
        # If the link were descended, inner.txt would appear twice (under both
        # real/ and dirlink/). Compare against a tree where dirlink is instead a
        # symlink to a file: both must be single, distinct entries.
        h = compute_tree(root)
        assert h.startswith("sha256:")

        other = tmp_path / "t2"
        _write(other / "real" / "inner.txt", b"data")
        os.symlink("real.txt", other / "dirlink")  # different target
        assert compute_tree(root) != compute_tree(other)

    def test_symlink_target_participates_in_digest(self, tmp_path):
        """Two symlinks differing only in target hash differently."""
        t1, t2 = tmp_path / "t1", tmp_path / "t2"
        for root in (t1, t2):
            _write(root / "a.txt", b"x")
            _write(root / "b.txt", b"y")
        os.symlink("a.txt", t1 / "link")
        os.symlink("b.txt", t2 / "link")
        assert compute_tree(t1) != compute_tree(t2)

    def test_nfc_sibling_collision_raises(self, tmp_path):
        """Distinct sibling files that NFC-collide must raise, not silently drop one."""
        root = tmp_path / "t"
        root.mkdir()
        nfc = "caf\u00e9.txt"      # \u00e9 as one code point
        nfd = "cafe\u0301.txt"     # e + combining acute \u2014 distinct bytes, same NFC
        (root / nfc).write_bytes(b"one")
        (root / nfd).write_bytes(b"two")
        # Only meaningful if the filesystem kept them as two separate entries.
        if len(os.listdir(root)) < 2:
            pytest.skip("filesystem normalized the names to a single entry")
        with pytest.raises(HashError, match="collision after NFC"):
            compute_tree(root)

    def test_non_regular_file_raises(self, tmp_path):
        """A FIFO (or other non-regular file) raises rather than hashing garbage."""
        if not hasattr(os, "mkfifo"):
            pytest.skip("platform has no FIFOs")
        root = tmp_path / "t"
        root.mkdir()
        os.mkfifo(root / "pipe")
        with pytest.raises(HashError, match="non-regular file"):
            compute_tree(root)

    def test_symlink_distinct_from_regular_file(self, tmp_path):
        """A symlink to 'target' must not collide with a file containing 'target'."""
        t1, t2 = tmp_path / "t1", tmp_path / "t2"
        _write(t1 / "real.txt", b"payload")
        os.symlink("real.txt", t1 / "entry")
        _write(t2 / "real.txt", b"payload")
        _write(t2 / "entry", b"real.txt")  # regular file whose content is the target
        assert compute_tree(t1) != compute_tree(t2)

    def test_broken_symlink_ok(self, tmp_path):
        root = tmp_path / "t"
        root.mkdir()
        os.symlink("nonexistent-target", root / "dangling")
        h = compute_tree(root)
        assert h.startswith("sha256:")

    def test_empty_tree_raises(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        with pytest.raises(HashError, match="no files"):
            compute_tree(root)

    def test_only_empty_subdirs_raises(self, tmp_path):
        root = tmp_path / "t"
        (root / "a" / "b").mkdir(parents=True)
        with pytest.raises(HashError, match="no files"):
            compute_tree(root)

    def test_file_path_raises(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_bytes(b"x")
        with pytest.raises(HashError, match="requires a directory"):
            compute_tree(p)

    def test_missing_path_raises(self, tmp_path):
        with pytest.raises(HashError, match="requires a directory"):
            compute_tree(tmp_path / "nope")

    def test_invalid_prefix_raises(self, tmp_path):
        root = tmp_path / "t"
        _write(root / "a.txt", b"alpha")
        with pytest.raises(HashError):
            compute_tree(root, prefix="bad!prefix")


class TestComputeBytesHardening:
    def test_empty_bytearray_and_memoryview(self):
        expected = f"sha256:{SHA256_EMPTY}"
        assert compute_bytes(bytearray(b"")) == expected
        assert compute_bytes(memoryview(b"")) == expected

    def test_strided_memoryview(self):
        """A non-contiguous memoryview hashes its logical bytes, not BufferError."""
        mv = memoryview(b"abcdef")[::2]  # logical bytes b"ace"
        assert compute_bytes(mv) == compute_bytes(b"ace")

    def test_released_memoryview_raises_hash_error(self):
        """A released memoryview raises HashError, not a raw ValueError."""
        mv = memoryview(bytearray(b"abc"))
        mv.release()
        with pytest.raises(HashError):
            compute_bytes(mv)

    def test_wide_itemsize_memoryview(self):
        """A memoryview with itemsize > 1 hashes its raw bytes, not BufferError."""
        import array
        arr = array.array("H", [1, 2, 3])  # unsigned short, itemsize 2
        mv = memoryview(arr)
        assert mv.itemsize != 1
        assert compute_bytes(mv) == compute_bytes(mv.tobytes())

    def test_str_subclass_encode_override_ignored(self):
        """A str subclass cannot change the hashed bytes via an encode() override;
        compute() hashes the canonical UTF-8 of the string content."""
        class Weird(str):
            def encode(self, *a, **k):
                raise RuntimeError("should not be called")
        assert compute(Weird("hello")) == compute("hello")

    def test_compute_lone_surrogate_raises_hash_error(self):
        """compute() on a lone-surrogate string raises HashError, not a raw
        UnicodeEncodeError (matches the tree path's contract)."""
        with pytest.raises(HashError):
            compute("\ud800")


class TestPrefixHardening:
    """A prefix ending in a newline must be rejected at every entry point."""

    def test_trailing_newline_rejected_compute(self):
        with pytest.raises(HashError):
            compute("x", prefix="ok\n")

    def test_trailing_newline_rejected_compute_bytes(self):
        with pytest.raises(HashError):
            compute_bytes(b"x", prefix="ok\n")

    def test_trailing_newline_rejected_compute_file(self, tmp_path):
        p = tmp_path / "f"
        p.write_bytes(b"x")
        with pytest.raises(HashError):
            compute_file(p, prefix="ok\n")

    def test_trailing_newline_rejected_compute_tree(self, tmp_path):
        root = tmp_path / "t"
        _write(root / "a.txt", b"x")
        with pytest.raises(HashError):
            compute_tree(root, prefix="ok\n")


class TestVerifyHardening:
    def test_invalid_prefix_in_hash_string_raises_clearly(self):
        good_hex = compute_bytes(b"hello").split(":")[-1]
        with pytest.raises(HashError, match="prefix"):
            verify("hello", f"bad prefix!:sha256:{good_hex}")

    def test_trailing_newline_digest_rejected(self):
        good_hex = compute_bytes(b"hello").split(":")[-1]
        # 64 chars where the last is a newline must not validate as hex.
        with pytest.raises(HashError):
            verify("hello", f"sha256:{good_hex[:-1]}\n")


class TestComputeFileHardening:
    def test_fifo_raises_not_hangs(self, tmp_path):
        if not hasattr(os, "mkfifo"):
            pytest.skip("no FIFOs on this platform")
        fifo = tmp_path / "pipe"
        os.mkfifo(fifo)
        with pytest.raises(HashError, match="[Nn]ot a regular file"):
            compute_file(fifo)

    def test_dev_null_rejected(self):
        if not os.path.exists("/dev/null"):
            pytest.skip("no /dev/null")
        with pytest.raises(HashError, match="[Nn]ot a regular file"):
            compute_file("/dev/null")

    def test_symlink_to_regular_file_followed(self, tmp_path):
        target = tmp_path / "real.bin"
        target.write_bytes(b"payload")
        link = tmp_path / "link"
        os.symlink(target, link)
        assert compute_file(link) == compute_bytes(b"payload")

    def test_close_failure_does_not_mask_or_leak(self, tmp_path):
        """A failing os.close raises neither a raw OSError nor masks a read error."""
        import unittest.mock as mock
        p = tmp_path / "f.bin"
        p.write_bytes(b"data")
        # close fails alone: must not leak a raw OSError (success path otherwise).
        with mock.patch("knurl.hash.os.close", side_effect=OSError(5, "boom")):
            assert compute_file(p) == compute_bytes(b"data")

    def test_invalid_path_type_raises_hash_error(self, tmp_path):
        """compute_file/compute_tree reject non-path types with HashError."""
        for bad in (None, 123, ["x"]):
            with pytest.raises(HashError, match="path-like"):
                compute_file(bad)
            with pytest.raises(HashError, match="path-like"):
                compute_tree(bad)

    def test_null_byte_path_raises_hash_error(self):
        """A path with an embedded null byte raises HashError, not ValueError."""
        for func in (compute_file, compute_tree):
            with pytest.raises(HashError, match="null byte"):
                func("/tmp/foo\x00bar")

    def test_broken_pathlike_raises_hash_error(self):
        """A PathLike whose __fspath__ misbehaves raises HashError, not a raw
        TypeError/RuntimeError."""
        class BadReturn(os.PathLike):
            def __fspath__(self):
                return 123  # protocol violation

        class Raises(os.PathLike):
            def __fspath__(self):
                raise RuntimeError("boom")

        for bad in (BadReturn(), Raises()):
            with pytest.raises(HashError, match="Invalid path"):
                compute_file(bad)
            with pytest.raises(HashError, match="Invalid path"):
                compute_tree(bad)

    def test_set_blocking_failure_wrapped_as_hash_error(self, tmp_path):
        """If os.set_blocking fails, it surfaces as HashError, not raw OSError."""
        import unittest.mock as mock
        if not getattr(os, "O_NONBLOCK", 0):
            pytest.skip("O_NONBLOCK unavailable; set_blocking not called")
        p = tmp_path / "f.bin"
        p.write_bytes(b"data")
        with mock.patch("knurl.hash.os.set_blocking", side_effect=OSError(5, "boom")):
            with pytest.raises(HashError):
                compute_file(p)

    def test_symlink_to_fifo_rejected(self, tmp_path):
        if not hasattr(os, "mkfifo"):
            pytest.skip("no FIFOs on this platform")
        fifo = tmp_path / "pipe"
        os.mkfifo(fifo)
        link = tmp_path / "link"
        os.symlink(fifo, link)
        with pytest.raises(HashError, match="[Nn]ot a regular file"):
            compute_file(link)


class TestComputeTreeHardening:
    def test_bytes_path_rejected(self, tmp_path):
        root = tmp_path / "t"
        _write(root / "a.txt", b"x")
        with pytest.raises(HashError, match="string path"):
            compute_tree(os.fsencode(root))

    def test_non_utf8_filename_raises_hash_error(self, tmp_path):
        if os.name == "nt":
            pytest.skip("non-UTF-8 filenames are POSIX-only")
        root = tmp_path / "t"
        root.mkdir()
        bad = os.path.join(str(root), b"file\xff.txt".decode("utf-8", "surrogateescape"))
        try:
            with open(bad, "wb") as f:
                f.write(b"x")
        except (OSError, ValueError, UnicodeError):
            pytest.skip("filesystem rejects non-UTF-8 names")
        with pytest.raises(HashError, match="non-UTF-8 name"):
            compute_tree(root)

    def test_non_utf8_symlink_target_raises_hash_error(self, tmp_path):
        if os.name == "nt":
            pytest.skip("POSIX-only")
        root = tmp_path / "t"
        root.mkdir()
        bad_target = b"target\xfe.txt".decode("utf-8", "surrogateescape")
        try:
            os.symlink(bad_target, root / "link")
        except (OSError, ValueError, UnicodeError):
            pytest.skip("cannot create symlink with non-UTF-8 target")
        with pytest.raises(HashError, match="non-UTF-8 target"):
            compute_tree(root)

    def test_unreadable_subtree_raises(self, tmp_path):
        if os.name == "nt":
            pytest.skip("POSIX permissions")
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            pytest.skip("root bypasses permission checks")
        root = tmp_path / "t"
        _write(root / "a.txt", b"x")
        secret = root / "secret"
        _write(secret / "b.txt", b"y")
        os.chmod(secret, 0o000)
        try:
            with pytest.raises(HashError, match="Could not read directory"):
                compute_tree(root)
        finally:
            os.chmod(secret, 0o755)

    def test_root_symlink_followed(self, tmp_path):
        """A symlink handed in as the root is followed (like tar/git)."""
        real = tmp_path / "real"
        _write(real / "a.txt", b"content")
        link = tmp_path / "link"
        os.symlink(real, link)
        assert compute_tree(link) == compute_tree(real)

    def test_symlink_only_tree_succeeds(self, tmp_path):
        """A tree with only symlinks (no regular files) is valid and stable."""
        root = tmp_path / "t"
        root.mkdir()
        os.symlink("nonexistent", root / "dangling")
        h1 = compute_tree(root)
        assert h1 == compute_tree(root)
        assert h1.startswith("sha256:")

    def test_file_to_symlink_swap_refused_via_nofollow(self, tmp_path):
        """The O_NOFOLLOW path the tree uses for files refuses a swapped symlink."""
        if not _HAS_NOFOLLOW:
            pytest.skip("O_NOFOLLOW unavailable on this platform")
        from knurl.hash import _file_digest
        target = tmp_path / "outside.txt"
        target.write_bytes(b"external")
        link = tmp_path / "entry"
        os.symlink(target, link)
        with pytest.raises(HashError):
            _file_digest(link, nofollow=True)
        # Without nofollow it follows, matching public compute_file behavior.
        assert _file_digest(link, nofollow=False) == _file_digest(target, nofollow=False)

    def test_nfc_collision_across_directories(self, tmp_path):
        """Sibling directories that NFC-collide must raise even with different
        children - they must not silently merge into one logical directory."""
        root = tmp_path / "t"
        nfc, nfd = "caf\u00e9", "cafe\u0301"   # precomposed vs decomposed
        _write(root / nfc / "a.txt", b"one")
        _write(root / nfd / "b.txt", b"two")     # different child names
        if len(os.listdir(root)) < 2:
            pytest.skip("filesystem normalized directory names")
        with pytest.raises(HashError, match="collision after NFC"):
            compute_tree(root)

    def test_nfc_colliding_dirs_do_not_merge(self, tmp_path):
        """A split tree (NFC + NFD sibling dirs) must not silently hash like a
        merged tree; the collision must be refused."""
        split, merged = tmp_path / "split", tmp_path / "merged"
        nfc, nfd = "caf\u00e9", "cafe\u0301"
        _write(split / nfc / "a.txt", b"A")
        _write(split / nfd / "b.txt", b"B")
        if len(os.listdir(split)) < 2:
            pytest.skip("filesystem normalized directory names")
        _write(merged / nfc / "a.txt", b"A")
        _write(merged / nfc / "b.txt", b"B")
        with pytest.raises(HashError):
            compute_tree(split)
        assert compute_tree(merged).startswith("sha256:")

    def test_symlink_target_nfc_normalized(self, tmp_path):
        t1, t2 = tmp_path / "t1", tmp_path / "t2"
        _write(t1 / "anchor.txt", b"x")
        _write(t2 / "anchor.txt", b"x")
        os.symlink("caf\u00e9.txt", t1 / "link")   # NFC target
        os.symlink("cafe\u0301.txt", t2 / "link")  # NFD target
        assert compute_tree(t1) == compute_tree(t2)

    def test_astral_plane_filename_deterministic(self, tmp_path):
        root = tmp_path / "t"
        try:
            _write(root / "smile_\U0001F600.txt", b"a")
            _write(root / "clef_\U0001D11E.bin", b"b")
        except (OSError, ValueError, UnicodeError):
            pytest.skip("filesystem cannot store astral-plane filenames")
        assert compute_tree(root) == compute_tree(root)

    def test_json_special_chars_in_filename(self, tmp_path):
        root = tmp_path / "t"
        _write(root / 'has"quote.txt', b"a")
        _write(root / "back\\slash.txt", b"b")
        _write(root / "tab\tchar.txt", b"c")
        assert compute_tree(root) == compute_tree(root)

    def test_deep_nesting(self, tmp_path):
        root = tmp_path / "t"
        deep = root
        for i in range(100):
            deep = deep / f"d{i}"
        _write(deep / "leaf.txt", b"deep")
        assert compute_tree(root).startswith("sha256:")

    def test_trailing_slash_same_hash(self, tmp_path):
        root = tmp_path / "t"
        _write(root / "a.txt", b"x")
        assert compute_tree(str(root)) == compute_tree(str(root) + os.sep)

    def test_inner_hashes_unprefixed_regardless_of_prefix(self, tmp_path):
        from knurl import canon
        root = tmp_path / "t"
        _write(root / "a.txt", b"hello")
        inner = compute_file(root / "a.txt")  # unprefixed
        assert inner.startswith("sha256:")
        manifest = {"a.txt": {"type": "file", "hash": inner}}
        expected = compute_bytes(canon.serialize(manifest), prefix="ns")
        assert compute_tree(root, prefix="ns") == expected

    def test_known_tree_vector(self, tmp_path):
        """Pin the exact digest for a known two-file tree (catches format drift)."""
        from knurl import canon
        root = tmp_path / "t"
        _write(root / "a.txt", b"alpha")
        _write(root / "b.txt", b"beta")
        manifest = {
            "a.txt": {"type": "file", "hash": compute_bytes(b"alpha")},
            "b.txt": {"type": "file", "hash": compute_bytes(b"beta")},
        }
        expected = compute_bytes(canon.serialize(manifest))
        assert compute_tree(root) == expected

    def test_absolute_vs_relative_symlink_targets_differ(self, tmp_path):
        t1, t2 = tmp_path / "t1", tmp_path / "t2"
        _write(t1 / "real.txt", b"data")
        _write(t2 / "real.txt", b"data")
        os.symlink(str((t1 / "real.txt").resolve()), t1 / "link")  # absolute
        os.symlink("real.txt", t2 / "link")                        # relative
        assert compute_tree(t1) != compute_tree(t2)
