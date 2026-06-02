"""Adversarial probes on knurl.canon and knurl.hash.

Originally drafted by a hardening agent; vetted and trimmed to the sound,
non-duplicate cases. The valuable cases kept here are the MAX_DEPTH boundary
checks and the verify() edge cases, which the main gauntlet
(test_hash_bytes_file_tree.py, test_hash_properties.py) does not cover.

Note: a separate, real finding this probe surfaced - canon's exponential
traversal/expansion on shared-reference DAGs (`seen = seen | {obj_id}` rebuilds
per branch) - is tracked separately. It is out of scope for the hash path,
whose manifests are shallow string dicts, so it is intentionally not asserted
here as a "passing" DoS.
"""

import array

import pytest

from knurl import canon
from knurl.hash import compute, compute_bytes, compute_tree, verify, HashError


class TestStridedMemoryview:
    """A non-contiguous / wide-itemsize memoryview must hash its logical bytes,
    not crash with BufferError or hash the wrong bytes."""

    def test_wide_itemsize_uint32(self):
        arr = array.array("I", [1, 2, 3, 4])  # itemsize 4
        mv = memoryview(arr)
        assert mv.itemsize == 4
        assert compute_bytes(mv) == compute_bytes(arr.tobytes())

    def test_wide_itemsize_uint16(self):
        arr = array.array("H", [256, 512, 1024])  # itemsize 2
        assert compute_bytes(memoryview(arr)) == compute_bytes(arr.tobytes())


class TestMaxDepthBoundary:
    """canon's MAX_DEPTH guard must be exact (no off-by-one)."""

    def _nested(self, depth, container="list"):
        if container == "list":
            obj = [1]
            for _ in range(depth - 1):
                obj = [obj]
            return obj
        obj = {"v": 1}
        for _ in range(depth - 1):
            obj = {"v": obj}
        return obj

    def test_exactly_max_depth_succeeds(self):
        assert canon.serialize(self._nested(canon.MAX_DEPTH)) is not None

    def test_max_depth_plus_one_raises(self):
        with pytest.raises(canon.CanonError, match="depth"):
            canon.serialize(self._nested(canon.MAX_DEPTH + 1))

    def test_max_depth_dict(self):
        with pytest.raises(canon.CanonError, match="depth"):
            canon.serialize(self._nested(canon.MAX_DEPTH + 1, container="dict"))


class TestVerifyEdgeCases:
    def test_hash_with_four_colons_raises(self):
        with pytest.raises(HashError):
            verify("hello", f"ns:extra:sha256:{'a' * 64}")

    def test_uppercase_hex_rejected(self):
        with pytest.raises(HashError):
            verify("hello", f"sha256:{'A' * 64}")

    def test_empty_string_content_verifies(self):
        h = compute("")
        assert verify("", h)
        assert not verify(" ", h)


class TestTreeEdgeCases:
    def test_only_subdirs_no_files_raises(self, tmp_path):
        root = tmp_path / "t"
        (root / "sub1").mkdir(parents=True)
        (root / "sub2").mkdir(parents=True)
        with pytest.raises(HashError, match="no entries"):
            compute_tree(root)

    def test_single_byte_filename(self, tmp_path):
        root = tmp_path / "t"
        root.mkdir()
        (root / "a").write_bytes(b"x")
        assert compute_tree(root).startswith("sha256:")

    def test_filename_with_null_byte_raises(self):
        from knurl.hash import compute_file
        with pytest.raises(HashError):
            compute_file("/tmp/file\x00.txt")
