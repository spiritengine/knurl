"""Tests for compute_tree_manifest - the manifest-exposing form of compute_tree.

The brief (brief-20260604-d1ze) makes the manifest a first-class API for hoard's
content-addressed Tree RSP. The load-bearing invariant is that the tree digest is
derivable from *exactly* the exposed entries, with no hidden inputs:

    compute_tree(path, prefix)
      == compute_tree_manifest(path, prefix).digest
      == compute_bytes(canon.serialize(entries), prefix=prefix)

These tests pin that invariant, the digest's byte-for-byte stability across the
delegation refactor, error parity with compute_tree, and the documented
properties (prefix applies to digest only; entries are size-free and drop empty
directories).
"""

import dataclasses
import json
import os
import tempfile

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from knurl import canon
from knurl.hash import (
    HashError,
    TreeManifest,
    compute_bytes,
    compute_file,
    compute_tree,
    compute_tree_manifest,
)


def _write(path, content=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _assert_invariant(root, prefix=None):
    """The three forms of the digest must agree, and the manifest must be
    self-consistent (digest re-derivable from entries alone)."""
    m = compute_tree_manifest(root, prefix)
    assert isinstance(m, TreeManifest)
    assert m.digest == compute_tree(root, prefix)
    assert m.digest == compute_bytes(canon.serialize(m.entries), prefix=prefix)
    return m


class TestPublicSurface:
    def test_exported_from_package(self):
        import knurl

        assert knurl.compute_tree_manifest is compute_tree_manifest
        assert knurl.TreeManifest is TreeManifest

    def test_result_is_frozen(self, tmp_path):
        _write(tmp_path / "t" / "a.txt", b"alpha")
        m = compute_tree_manifest(tmp_path / "t")
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.digest = "sha256:" + "0" * 64
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.entries = {}

    def test_fields_present(self, tmp_path):
        _write(tmp_path / "t" / "a.txt", b"alpha")
        m = compute_tree_manifest(tmp_path / "t")
        assert set(m.__dataclass_fields__) == {"digest", "entries", "paths"}
        assert m.digest.startswith("sha256:")
        assert isinstance(m.entries, dict)


class TestGoldenManifest:
    """A known synthetic tree produces an expected entries dict and digest.

    These literals are the regression anchor: if the walk, normalization, or
    serialization changes in a way that shifts existing digests, this breaks.
    """

    def _build(self, root):
        _write(root / "a.txt", b"alpha")
        _write(root / "sub" / "b.txt", b"beta")
        os.symlink("a.txt", root / "link")

    def test_golden_entries(self, tmp_path):
        root = tmp_path / "t"
        self._build(root)
        m = compute_tree_manifest(root)
        assert m.entries == {
            "a.txt": {
                "type": "file",
                "hash": "sha256:8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8",
            },
            "sub/b.txt": {
                "type": "file",
                "hash": "sha256:f44e64e75f3948e9f73f8dfa94721c4ce8cbb4f265c4790c702b2d41cfbf2753",
            },
            "link": {"type": "symlink", "target": "a.txt"},
        }

    def test_golden_digest_stable(self, tmp_path):
        """compute_tree output is byte-for-byte identical after the delegation
        refactor - existing digests must not shift."""
        root = tmp_path / "t"
        self._build(root)
        expected = "sha256:99f0fb975a0a5943444b46d06606eb58e7f55c7d578c16c9b4008ed21ad9a30e"
        assert compute_tree(root) == expected
        assert compute_tree_manifest(root).digest == expected

    def test_golden_file_hash_matches_compute_file(self, tmp_path):
        """Each entry hash is exactly compute_file() over that blob - unprefixed."""
        root = tmp_path / "t"
        self._build(root)
        m = compute_tree_manifest(root)
        assert m.entries["a.txt"]["hash"] == compute_file(root / "a.txt")
        assert m.entries["sub/b.txt"]["hash"] == compute_file(root / "sub" / "b.txt")


class TestInvariant:
    def test_single_file(self, tmp_path):
        root = tmp_path / "t"
        _write(root / "only.txt", b"solo")
        m = _assert_invariant(root)
        assert set(m.entries) == {"only.txt"}

    def test_single_symlink_no_regular_files(self, tmp_path):
        """A tree with only a symlink is non-empty and obeys the invariant."""
        root = tmp_path / "t"
        root.mkdir()
        os.symlink("somewhere", root / "link")
        m = _assert_invariant(root)
        assert m.entries == {"link": {"type": "symlink", "target": "somewhere"}}

    def test_nested_dirs(self, tmp_path):
        root = tmp_path / "t"
        _write(root / "a.txt", b"a")
        _write(root / "x" / "b.txt", b"b")
        _write(root / "x" / "y" / "c.txt", b"c")
        m = _assert_invariant(root)
        assert set(m.entries) == {"a.txt", "x/b.txt", "x/y/c.txt"}

    def test_symlinks_mixed(self, tmp_path):
        root = tmp_path / "t"
        _write(root / "real.txt", b"payload")
        os.symlink("real.txt", root / "filelink")
        _write(root / "d" / "inner.txt", b"data")
        os.symlink("d", root / "dirlink")
        m = _assert_invariant(root)
        assert m.entries["filelink"] == {"type": "symlink", "target": "real.txt"}
        assert m.entries["dirlink"] == {"type": "symlink", "target": "d"}

    def test_empty_dirs_present_are_dropped(self, tmp_path):
        """Empty directories contribute no entries; the invariant still holds and
        the digest matches a tree without those empty dirs."""
        with_empty = tmp_path / "t1"
        without = tmp_path / "t2"
        for root in (with_empty, without):
            _write(root / "a.txt", b"alpha")
        (with_empty / "empty").mkdir()
        (with_empty / "nested" / "deep").mkdir(parents=True)

        m = _assert_invariant(with_empty)
        assert set(m.entries) == {"a.txt"}
        assert compute_tree_manifest(with_empty).digest == compute_tree_manifest(without).digest

    def test_unicode_nfc_names(self, tmp_path):
        """A decomposed (NFD) name and its composed (NFC) form yield identical
        entries keys and digest."""
        nfc = "café.txt"      # é as one code point
        nfd = "café.txt"     # e + combining acute
        t1, t2 = tmp_path / "t1", tmp_path / "t2"
        _write(t1 / nfc, b"data")
        _write(t2 / nfd, b"data")
        m1 = _assert_invariant(t1)
        m2 = _assert_invariant(t2)
        assert set(m1.entries) == set(m2.entries) == {nfc}
        assert m1.digest == m2.digest


class TestOnDiskPaths:
    """`paths` exposes the real on-disk relative path per entry (pre-NFC), so a
    consumer can re-read a file whose stored name form differs from its NFC key.
    Brief brief-20260606-psks; the bug it fixes is an NFD-named file being
    unreadable via the composed key on a non-normalizing filesystem (Linux)."""

    # U+00E9 is precomposed 'é'; "e" + U+0301 is its decomposed (NFD) form.
    _NFC = "caf\u00e9.txt"
    _NFD = "cafe\u0301.txt"

    def test_keys_match_entries(self, tmp_path):
        """paths.keys() == entries.keys() exactly, across files, symlinks, dirs."""
        root = tmp_path / "t"
        _write(root / "a.txt", b"a")
        _write(root / "d" / "b.txt", b"b")
        os.symlink("a.txt", root / "link")
        m = compute_tree_manifest(root)
        assert m.paths.keys() == m.entries.keys()

    def test_ascii_nfc_paths_equal_keys(self, tmp_path):
        """For all-ASCII / already-NFC names, paths[k] == k (the common no-op)."""
        root = tmp_path / "t"
        _write(root / "a.txt", b"a")
        _write(root / "sub" / "b.txt", b"b")
        os.symlink("a.txt", root / "link")
        m = compute_tree_manifest(root)
        for k in m.entries:
            assert m.paths[k] == k

    def test_blob_at_path_hashes_to_entry(self, tmp_path):
        """The blob at paths[k] hashes to entries[k]['hash'] - exactly hoard's
        operation: read the file at the real path, confirm it is the addressed
        content."""
        root = tmp_path / "t"
        _write(root / "a.txt", b"alpha")
        _write(root / "deep" / "b.bin", b"\x00\x01beta")
        m = compute_tree_manifest(root)
        for k, desc in m.entries.items():
            if desc["type"] == "file":
                assert compute_file(root / m.paths[k]) == desc["hash"]

    def test_nfd_name_real_path_reopens_where_nfc_key_does_not(self, tmp_path):
        """The fix: an NFD-named file is keyed by its NFC form (digest stability),
        but only paths[nfc_key] - the decomposed on-disk path - re-opens it."""
        root = tmp_path / "t"
        root.mkdir()
        (root / self._NFD).write_bytes(b"payload")
        on_disk = os.listdir(root)
        # Only meaningful if the filesystem preserved the decomposed bytes.
        if self._NFD not in on_disk or self._NFC in on_disk:
            pytest.skip("filesystem normalized the name; cannot exercise NFD path")

        m = compute_tree_manifest(root)
        # The entry key is the composed (NFC) form...
        assert self._NFC in m.entries
        assert self._NFD not in m.entries
        # ...but the on-disk path is the decomposed form that actually exists.
        assert m.paths[self._NFC] == self._NFD
        assert not (root / self._NFC).exists()   # the bug: NFC key does not resolve
        assert (root / m.paths[self._NFC]).exists()   # the real path does
        # And the blob there hashes to the entry's address.
        assert compute_file(root / m.paths[self._NFC]) == m.entries[self._NFC]["hash"]

    def test_paths_outside_digest_nfc_nfd_agree(self, tmp_path):
        """An NFC-named tree and an NFD-named tree of the same content hash
        identically (paths differ, digest does not - paths is not in the digest)."""
        t_nfc, t_nfd = tmp_path / "t1", tmp_path / "t2"
        _write(t_nfc / self._NFC, b"data")
        _write(t_nfd / self._NFD, b"data")
        if self._NFD not in os.listdir(t_nfd) or self._NFC in os.listdir(t_nfd):
            pytest.skip("filesystem normalized the NFD name")
        m_nfc = compute_tree_manifest(t_nfc)
        m_nfd = compute_tree_manifest(t_nfd)
        assert m_nfc.digest == m_nfd.digest          # digest unaffected
        assert m_nfc.entries == m_nfd.entries          # same NFC keys + hashes
        assert m_nfc.paths[self._NFC] == self._NFC     # on-disk forms differ...
        assert m_nfd.paths[self._NFC] == self._NFD     # ...only in paths

    def test_symlink_path_recorded(self, tmp_path):
        """A symlink entry gets a paths entry locating the link itself."""
        root = tmp_path / "t"
        _write(root / "real.txt", b"x")
        os.symlink("real.txt", root / "link")
        m = compute_tree_manifest(root)
        assert m.paths["link"] == "link"
        assert os.path.islink(root / m.paths["link"])


class TestPrefix:
    def test_prefix_applies_to_digest_only(self, tmp_path):
        root = tmp_path / "t"
        _write(root / "a.txt", b"alpha")
        _write(root / "link_target.txt", b"t")
        os.symlink("link_target.txt", root / "link")

        plain = compute_tree_manifest(root)
        prefixed = compute_tree_manifest(root, prefix="tree")

        # Digest carries the prefix; the entries are byte-for-byte identical.
        assert prefixed.digest == "tree:" + plain.digest
        assert prefixed.entries == plain.entries

    def test_inner_file_hashes_unprefixed(self, tmp_path):
        root = tmp_path / "t"
        _write(root / "a.txt", b"alpha")
        m = compute_tree_manifest(root, prefix="tree")
        for desc in m.entries.values():
            if desc["type"] == "file":
                assert desc["hash"].startswith("sha256:")
                assert ":" not in desc["hash"][len("sha256:"):]

    def test_invalid_prefix_raises(self, tmp_path):
        root = tmp_path / "t"
        _write(root / "a.txt", b"alpha")
        with pytest.raises(HashError):
            compute_tree_manifest(root, prefix="bad!prefix")


class TestErrorParity:
    """Each failure raises HashError from BOTH compute_tree and
    compute_tree_manifest - they share one walk, so the contract cannot drift."""

    def _both_raise(self, root, match):
        with pytest.raises(HashError, match=match):
            compute_tree(root)
        with pytest.raises(HashError, match=match):
            compute_tree_manifest(root)

    def test_empty_tree(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        self._both_raise(root, "no files")

    def test_only_empty_subdirs(self, tmp_path):
        root = tmp_path / "t"
        (root / "a" / "b").mkdir(parents=True)
        self._both_raise(root, "no files")

    def test_not_a_directory(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_bytes(b"x")
        self._both_raise(p, "requires a directory")

    def test_nfc_collision(self, tmp_path):
        root = tmp_path / "t"
        root.mkdir()
        nfc = "café.txt"
        nfd = "café.txt"
        (root / nfc).write_bytes(b"one")
        (root / nfd).write_bytes(b"two")
        if len(os.listdir(root)) < 2:
            pytest.skip("filesystem normalized the names to a single entry")
        self._both_raise(root, "collision after NFC")

    def test_non_regular_file(self, tmp_path):
        if not hasattr(os, "mkfifo"):
            pytest.skip("platform has no FIFOs")
        root = tmp_path / "t"
        root.mkdir()
        os.mkfifo(root / "pipe")
        self._both_raise(root, "non-regular file")

    def test_non_utf8_filename(self, tmp_path):
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
        self._both_raise(root, "non-UTF-8 name")

    def test_non_utf8_symlink_target(self, tmp_path):
        if os.name == "nt":
            pytest.skip("POSIX-only")
        root = tmp_path / "t"
        root.mkdir()
        bad_target = b"target\xfe.txt".decode("utf-8", "surrogateescape")
        try:
            os.symlink(bad_target, root / "link")
        except (OSError, ValueError, UnicodeError):
            pytest.skip("cannot create symlink with non-UTF-8 target")
        self._both_raise(root, "non-UTF-8 target")

    def test_bytes_path_rejected(self, tmp_path):
        root = tmp_path / "t"
        _write(root / "a.txt", b"x")
        with pytest.raises(HashError, match="string path"):
            compute_tree_manifest(os.fsencode(root))

    def test_unassigned_codepoint_name_raises_hash_error(self, tmp_path):
        """A name with a code point unassigned in the running UCD (category Cn)
        is valid UTF-8 but has no stable NFC form. canon rejects it; the tree
        path must surface that as HashError (not let CanonError escape), from
        both entry points. Hardening finding A (gremlin + oracle)."""
        root = tmp_path / "t"
        root.mkdir()
        # U+0378 is unassigned (Cn); valid UTF-8 b"\xcd\xb8".
        name = "f͸.txt"
        try:
            (root / name).write_bytes(b"x")
        except (OSError, ValueError, UnicodeError):
            pytest.skip("filesystem rejects the name")
        # If the running UCD ever assigns U+0378, canon would accept it and this
        # case no longer exercises the Cn path.
        import unicodedata

        if unicodedata.category("͸") != "Cn":
            pytest.skip("U+0378 is assigned in this Unicode build")
        self._both_raise(root, "canonically hashed")

    def test_unassigned_codepoint_symlink_target_raises_hash_error(self, tmp_path):
        root = tmp_path / "t"
        root.mkdir()
        _write(root / "anchor.txt", b"x")  # keep the tree non-empty regardless
        try:
            os.symlink("target͸", root / "link")
        except (OSError, ValueError, UnicodeError):
            pytest.skip("cannot create symlink with that target")
        import unicodedata

        if unicodedata.category("͸") != "Cn":
            pytest.skip("U+0378 is assigned in this Unicode build")
        self._both_raise(root, "canonically hashed")


class TestManifestProperties:
    """Documented hardening properties (findings B and D): the frozen wrapper
    protects field rebinding only, entries is an intentionally-shared mutable
    dict, and the instance is not hashable."""

    def test_not_hashable(self, tmp_path):
        """frozen=True synthesizes __hash__, but entries is a dict, so hashing an
        instance raises - documented; callers key on .digest instead."""
        _write(tmp_path / "t" / "a.txt", b"alpha")
        m = compute_tree_manifest(tmp_path / "t")
        with pytest.raises(TypeError):
            hash(m)

    def test_entries_is_the_hashed_object_byte_faithful(self, tmp_path):
        """entries IS the object that was serialized to produce digest (no copy),
        so re-deriving from the unmutated entries reproduces digest exactly."""
        _write(tmp_path / "t" / "a.txt", b"alpha")
        m = compute_tree_manifest(tmp_path / "t")
        assert compute_bytes(canon.serialize(m.entries)) == m.digest

    def test_mutating_entries_does_not_retroactively_change_digest(self, tmp_path):
        """digest is a precomputed immutable string; mutating entries after the
        call leaves digest stale (the documented footgun) rather than corrupting
        it in place. Confirms there is no live coupling to defend the invariant."""
        _write(tmp_path / "t" / "a.txt", b"alpha")
        m = compute_tree_manifest(tmp_path / "t")
        original = m.digest
        m.entries["a.txt"]["hash"] = "sha256:" + "0" * 64
        assert m.digest == original  # unchanged
        assert compute_bytes(canon.serialize(m.entries)) != original  # now stale

    def test_no_cross_call_aliasing(self, tmp_path):
        """Each call builds a fresh manifest; poisoning one call's entries does
        not leak into a later call."""
        _write(tmp_path / "t" / "a.txt", b"alpha")
        m1 = compute_tree_manifest(tmp_path / "t")
        m1.entries.clear()
        m1.entries["INJECTED"] = {"type": "file", "hash": "sha256:" + "0" * 64}
        m2 = compute_tree_manifest(tmp_path / "t")
        assert "INJECTED" not in m2.entries
        assert m2.entries["a.txt"]["hash"].startswith("sha256:")


class TestStreamedFileHashing:
    def test_large_file_hash_matches_compute_file(self, tmp_path):
        """A file larger than the read chunk is streamed; its manifest hash
        equals compute_file (bounded memory, no full load)."""
        root = tmp_path / "t"
        big = b"\x5a" * (5 * 1024 * 1024 + 7)  # > 1 MiB chunk, not a multiple
        _write(root / "big.bin", big)
        m = compute_tree_manifest(root)
        assert m.entries["big.bin"]["hash"] == compute_file(root / "big.bin")


class TestManifestRoundTrip:
    """A stored manifest reproduces the digest without re-walking the tree -
    the basis for a deterministic verify over a content-addressed store."""

    def test_digest_from_stored_entries(self, tmp_path):
        root = tmp_path / "t"
        _write(root / "a.txt", b"alpha")
        _write(root / "d" / "b.txt", b"beta")
        os.symlink("a.txt", root / "link")

        m = compute_tree_manifest(root, prefix="hoard")
        # Simulate persistence: round-trip entries through canon's JSON form.
        stored = canon.serialize(m.entries)
        import json

        recovered = json.loads(stored)
        # Recompute the digest from the recovered manifest alone (no live tree).
        assert compute_bytes(canon.serialize(recovered), prefix="hoard") == m.digest

    def test_iteration_order_does_not_affect_digest(self, tmp_path):
        """canon sorts keys, so a reordered entries dict reproduces the digest."""
        root = tmp_path / "t"
        _write(root / "a.txt", b"a")
        _write(root / "b.txt", b"b")
        _write(root / "c.txt", b"c")
        m = compute_tree_manifest(root)
        reordered = dict(reversed(list(m.entries.items())))
        assert list(reordered) != list(m.entries)  # genuinely reordered
        assert compute_bytes(canon.serialize(reordered)) == m.digest


# --- Property-based: the invariant must hold for ALL trees, not hand-picked ones.

# A small alphabet of name fragments that deliberately mixes ASCII, an NFC
# precomposed char and its NFD decomposition (so sibling collisions arise), a
# CJK code point, and tokens that build nested paths and dotted extensions.
_FRAGMENTS = st.sampled_from(
    ["a", "b", "Z", "0", "9", "-", "_", " ", "x", "\u00e9", "e\u0301", "\u4e2d", "sub", ".txt"]
)
# A single path component: 1-3 fragments joined, excluding the reserved "." / ".."
# and anything with a separator or NUL (those are tested explicitly elsewhere).
_component = (
    st.lists(_FRAGMENTS, min_size=1, max_size=3)
    .map("".join)
    .filter(lambda s: s not in ("", ".", "..") and "/" not in s and "\x00" not in s)
)
# A relative path of 1-3 components.
_rel_path = st.lists(_component, min_size=1, max_size=3)
# A symlink target: a short string; "/" allowed (recorded, never followed),
# NUL excluded (os.symlink would reject it before we ever hash).
_target = st.text(
    alphabet=st.sampled_from(["a", "b", "/", ".", "-", "\u00e9", "\u4e2d", "x"]),
    min_size=1,
    max_size=8,
)
_entry = st.tuples(
    _rel_path,
    st.one_of(
        st.tuples(st.just("file"), st.binary(max_size=48)),
        st.tuples(st.just("symlink"), _target),
    ),
)


def _materialize(root, entries):
    """Best-effort build the tree; skip entries that conflict on disk (a name
    used as both file and dir, a target os.symlink rejects). Returns True if at
    least one entry landed."""
    placed = 0
    for comps, (kind, payload) in entries:
        full = os.path.join(root, *comps)
        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            if kind == "file":
                with open(full, "wb") as f:
                    f.write(payload)
            else:
                os.symlink(payload, full)
        except (OSError, ValueError):
            continue  # conflicting path or unrepresentable entry - drop it
        placed += 1
    return placed > 0


class TestInvariantProperty:
    """Fuzz the three-way invariant and the storage round-trip over random trees.

    For any tree we can build: either both entry points raise HashError (parity),
    or the digest is derivable from exactly the exposed entries AND survives a
    JSON persist -> reload -> recompute (hoard's actual stored-manifest path)."""

    @settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(entries=st.lists(_entry, min_size=1, max_size=8), prefix=st.one_of(st.none(), st.just("hoard")))
    def test_invariant_holds_or_errors_in_parity(self, entries, prefix):
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "tree")
            os.mkdir(root)
            assume(_materialize(root, entries))

            try:
                m = compute_tree_manifest(root, prefix)
            except HashError:
                # Whatever made the manifest path raise must also make the
                # delegating compute_tree raise - parity is structural.
                with pytest.raises(HashError):
                    compute_tree(root, prefix)
                return

            # The three-way invariant.
            assert m.digest == compute_tree(root, prefix)
            assert m.digest == compute_bytes(canon.serialize(m.entries), prefix=prefix)

            # entries faithfully captures the digest's inputs even after a JSON
            # round-trip (the hoard stored-manifest -> recompute path): persisting
            # and reloading the manifest reproduces the exact digest.
            reloaded = json.loads(canon.serialize(m.entries))
            assert compute_bytes(canon.serialize(reloaded), prefix=prefix) == m.digest

            # paths mirrors entries exactly and is outside the digest.
            assert m.paths.keys() == m.entries.keys()

            # Every entry is a well-formed typed descriptor; file hashes
            # unprefixed; and paths[key] re-opens the exact on-disk entry.
            for key, desc in m.entries.items():
                assert desc["type"] in ("file", "symlink")
                real = os.path.join(root, m.paths[key])
                assert os.path.lexists(real)  # the real path exists on disk
                if desc["type"] == "file":
                    assert desc["hash"].startswith("sha256:")
                    assert ":" not in desc["hash"][len("sha256:"):]
                    # the blob at the real path hashes to the entry's address
                    assert compute_file(real) == desc["hash"]
                else:
                    assert "target" in desc
