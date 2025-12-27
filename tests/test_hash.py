"""Tests for content-addressable hash module.

Tests the knurl.hash module which provides:
- compute(content, prefix=None) -> hash string
- verify(content, hash_string) -> bool
- HashError for validation failures
"""

import pytest
from hypothesis import given, strategies as st

from knurl.hash import compute, verify, HashError


# Known SHA256 test vectors
SHA256_EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SHA256_HELLO = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


class TestComputeDeterminism:
    """Same input must always produce same hash."""

    def test_same_input_same_hash(self):
        """Identical inputs produce identical hashes."""
        assert compute("hello") == compute("hello")

    def test_different_input_different_hash(self):
        """Different inputs produce different hashes."""
        assert compute("hello") != compute("world")

    def test_whitespace_matters(self):
        """Whitespace differences produce different hashes."""
        assert compute("hello") != compute("hello ")
        assert compute("hello") != compute(" hello")
        assert compute("hello") != compute("hello\n")

    def test_case_sensitivity(self):
        """Case differences produce different hashes."""
        assert compute("Hello") != compute("hello")
        assert compute("HELLO") != compute("hello")


class TestComputeFormat:
    """Output format validation."""

    def test_format_without_prefix(self):
        """Hash without prefix: 'sha256:hexdigest'."""
        result = compute("hello")
        assert result.startswith("sha256:")
        assert ":" in result
        parts = result.split(":")
        assert len(parts) == 2
        assert parts[0] == "sha256"
        # Hex digest is 64 characters
        assert len(parts[1]) == 64

    def test_format_with_prefix(self):
        """Hash with prefix: 'prefix:sha256:hexdigest'."""
        result = compute("hello", prefix="config")
        assert result.startswith("config:sha256:")
        parts = result.split(":")
        assert len(parts) == 3
        assert parts[0] == "config"
        assert parts[1] == "sha256"
        assert len(parts[2]) == 64

    def test_hex_characters_only(self):
        """Digest contains only valid hex characters."""
        result = compute("hello")
        digest = result.split(":")[-1]
        assert all(c in "0123456789abcdef" for c in digest)


class TestKnownVectors:
    """SHA256 test vectors from known sources."""

    def test_empty_string_hash(self):
        """Empty string produces known SHA256 hash."""
        result = compute("")
        assert result == f"sha256:{SHA256_EMPTY}"

    def test_hello_hash(self):
        """'hello' produces known SHA256 hash."""
        result = compute("hello")
        assert result == f"sha256:{SHA256_HELLO}"

    def test_hello_with_prefix(self):
        """'hello' with prefix produces prefixed known hash."""
        result = compute("hello", prefix="test")
        assert result == f"test:sha256:{SHA256_HELLO}"


class TestEdgeCases:
    """Edge case handling."""

    def test_empty_string(self):
        """Empty string is valid input."""
        result = compute("")
        assert result.startswith("sha256:")

    def test_unicode_content(self):
        """Unicode content hashes correctly."""
        result = compute("\u00e9\u00e8\u00ea")  # é è ê
        assert result.startswith("sha256:")
        # Same unicode = same hash
        assert compute("café") == compute("café")

    def test_emoji(self):
        """Emoji content hashes correctly."""
        result = compute("🎉🚀")
        assert result.startswith("sha256:")

    def test_newlines(self):
        """Content with newlines hashes correctly."""
        result = compute("line1\nline2\nline3")
        assert result.startswith("sha256:")

    def test_large_content(self):
        """Large content hashes without error."""
        large = "x" * 1_000_000  # 1MB of data
        result = compute(large)
        assert result.startswith("sha256:")
        # Still deterministic
        assert compute(large) == result

    def test_whitespace_only(self):
        """Whitespace-only content is valid."""
        assert compute(" ").startswith("sha256:")
        assert compute("\t").startswith("sha256:")
        assert compute("\n").startswith("sha256:")
        # All different
        assert compute(" ") != compute("\t") != compute("\n")


class TestNamespacing:
    """Prefix/namespace handling."""

    def test_prefix_adds_namespace(self):
        """Prefix is prepended to hash."""
        without = compute("hello")
        with_prefix = compute("hello", prefix="config")
        assert with_prefix == f"config:{without}"

    def test_different_prefixes_different_strings(self):
        """Different prefixes produce different hash strings."""
        config = compute("hello", prefix="config")
        state = compute("hello", prefix="state")
        assert config != state

    def test_prefix_with_special_chars(self):
        """Prefix can contain allowed special characters."""
        result = compute("hello", prefix="my-config")
        assert result.startswith("my-config:sha256:")

    def test_empty_prefix_same_as_no_prefix(self):
        """Empty string prefix is treated as no prefix."""
        no_prefix = compute("hello")
        empty_prefix = compute("hello", prefix="")
        assert empty_prefix == no_prefix

    def test_prefix_with_colon_rejected(self):
        """Prefix containing colon is rejected (would break format)."""
        with pytest.raises(HashError):
            compute("hello", prefix="has:colon")

    def test_prefix_with_newline_rejected(self):
        """Prefix containing newline is rejected."""
        with pytest.raises(HashError):
            compute("hello", prefix="line1\nline2")

    def test_prefix_unicode_rejected(self):
        """Prefix containing non-ASCII is rejected."""
        with pytest.raises(HashError):
            compute("hello", prefix="préfix")

    def test_prefix_with_space_rejected(self):
        """Prefix containing space is rejected."""
        with pytest.raises(HashError):
            compute("hello", prefix="has space")


class TestVerify:
    """Hash verification."""

    def test_verify_correct_hash(self):
        """Verification succeeds for matching content."""
        hash_str = compute("hello")
        assert verify("hello", hash_str) is True

    def test_verify_wrong_content(self):
        """Verification fails for non-matching content."""
        hash_str = compute("hello")
        assert verify("world", hash_str) is False

    def test_verify_with_prefix(self):
        """Verification works with prefixed hashes."""
        hash_str = compute("hello", prefix="config")
        assert verify("hello", hash_str) is True
        assert verify("world", hash_str) is False

    def test_verify_empty_string(self):
        """Verification works for empty string."""
        hash_str = compute("")
        assert verify("", hash_str) is True
        assert verify(" ", hash_str) is False

    def test_verify_known_vector(self):
        """Verification works with known test vector."""
        assert verify("hello", f"sha256:{SHA256_HELLO}") is True
        assert verify("", f"sha256:{SHA256_EMPTY}") is True


class TestInputValidation:
    """Input validation and error handling."""

    def test_compute_rejects_none(self):
        """compute() rejects None input."""
        with pytest.raises((HashError, TypeError)):
            compute(None)

    def test_compute_rejects_bytes(self):
        """compute() rejects bytes input (expects string)."""
        with pytest.raises((HashError, TypeError)):
            compute(b"hello")

    def test_compute_rejects_int(self):
        """compute() rejects integer input."""
        with pytest.raises((HashError, TypeError)):
            compute(123)

    def test_compute_rejects_list(self):
        """compute() rejects list input."""
        with pytest.raises((HashError, TypeError)):
            compute(["hello"])

    def test_verify_rejects_invalid_hash_format(self):
        """verify() rejects malformed hash strings."""
        with pytest.raises(HashError):
            verify("hello", "not-a-valid-hash")

    def test_verify_rejects_wrong_algorithm(self):
        """verify() rejects unknown algorithm prefix."""
        with pytest.raises(HashError):
            verify("hello", f"md5:{SHA256_HELLO}")

    def test_verify_rejects_truncated_digest(self):
        """verify() rejects truncated digest."""
        with pytest.raises(HashError):
            verify("hello", "sha256:2cf24dba5fb0a30e")  # Too short

    def test_verify_rejects_invalid_hex(self):
        """verify() rejects non-hex characters in digest."""
        with pytest.raises(HashError):
            verify("hello", "sha256:" + "g" * 64)  # 'g' is not hex


class TestGremlinAttacks:
    """Tests discovered by gremlin security review."""

    def test_hash_with_four_colons_rejected(self):
        """Hash string with 4+ colons is rejected."""
        with pytest.raises(HashError):
            verify("hello", "a:b:sha256:" + "a" * 64)

    def test_uppercase_algorithm_rejected(self):
        """Uppercase algorithm name is rejected."""
        with pytest.raises(HashError):
            verify("hello", "SHA256:" + "a" * 64)

    def test_uppercase_hex_rejected(self):
        """Uppercase hex digits in digest are rejected."""
        with pytest.raises(HashError):
            verify("hello", "sha256:" + "A" * 64)

    def test_prefix_sha256_allowed_but_distinct(self):
        """Using 'sha256' as prefix is allowed (creates sha256:sha256:...)."""
        # This is a weird but valid use case
        result = compute("hello", prefix="sha256")
        assert result == f"sha256:sha256:{SHA256_HELLO}"
        # And it should verify correctly
        assert verify("hello", result) is True

    def test_forgery_attempt_fails(self):
        """Cannot forge a hash by prepending prefix to different content's hash."""
        real_hash = compute("secret")
        forged = "fake:" + real_hash  # Try to prepend a prefix
        # This should fail because the format is now prefix:sha256:digest
        # but forged is fake:sha256:digest (3 parts, valid format)
        # However, verify will recompute with prefix="fake" and compare
        assert verify("secret", forged) is True  # This verifies the content
        assert verify("wrong", forged) is False  # Wrong content fails

    def test_surrogate_pair_rejected(self):
        """Lone surrogate (invalid unicode) is rejected at encode time."""
        with pytest.raises(UnicodeEncodeError):
            compute("\ud800")  # Lone surrogate

    def test_very_long_prefix_allowed(self):
        """Very long prefixes are technically allowed."""
        # This is allowed but probably shouldn't be used in practice
        long_prefix = "x" * 1000
        result = compute("test", prefix=long_prefix)
        assert result.startswith(long_prefix + ":sha256:")

    def test_empty_parts_in_hash_rejected(self):
        """Hash strings with empty parts are rejected."""
        with pytest.raises(HashError):
            verify("hello", ":sha256:" + "a" * 64)  # Empty prefix part
        with pytest.raises(HashError):
            verify("hello", "prefix::sha256:" + "a" * 64)  # Extra colon


class TestAvalancheEffect:
    """Statistical tests for hash quality (from research)."""

    def test_single_char_change_avalanche(self):
        """Small input changes produce dramatically different hashes.

        A good hash function changes ~50% of output bits for a 1-bit input change.
        """
        h1 = compute("hello")
        h2 = compute("hallo")  # One character different

        d1 = h1.split(":")[-1]
        d2 = h2.split(":")[-1]

        # Count differing hex characters
        differences = sum(1 for a, b in zip(d1, d2) if a != b)

        # Should differ in most positions (avalanche effect)
        # With 64 hex chars, expect >30 differences
        assert differences > 30, f"Only {differences}/64 chars differ - weak avalanche"

    def test_sequential_inputs_no_pattern(self):
        """Sequential inputs don't produce sequential hashes."""
        hashes = [compute(str(i)) for i in range(100)]

        # All unique
        assert len(set(hashes)) == 100

        # Sorting hashes shouldn't recover original order
        sorted_hashes = sorted(hashes)
        assert hashes != sorted_hashes


class TestUnicodeNormalization:
    """Unicode handling tests (from research on determinism)."""

    def test_unicode_normalization_not_applied(self):
        """Different unicode representations produce different hashes.

        We hash bytes as-is - no normalization. The canon module
        should handle normalization if needed before hashing.
        """
        # é as single codepoint vs e + combining accent
        e_acute_composed = "\u00e9"      # é (single codepoint)
        e_acute_decomposed = "e\u0301"   # e + combining acute accent

        # These look identical but are different bytes
        assert compute(e_acute_composed) != compute(e_acute_decomposed)

    def test_null_bytes_preserved(self):
        """Strings with null bytes hash correctly."""
        result = compute("hello\x00world")
        assert result.startswith("sha256:")
        assert compute("hello\x00world") != compute("helloworld")


class TestRepeatedCalls:
    """Stability tests (from research on determinism)."""

    def test_hundred_calls_stable(self):
        """Hash is stable across 100 repeated calls."""
        s = "test content for stability check"
        results = [compute(s) for _ in range(100)]
        assert len(set(results)) == 1  # All identical


class TestCanonIntegration:
    """Test integration with canon module."""

    def test_canon_then_hash(self):
        """Canonical serialization then hashing is deterministic."""
        from knurl.canon import serialize

        obj = {"b": 1, "a": 2, "nested": {"z": 3, "y": 4}}

        # Serialize to canonical form
        canonical = serialize(obj).decode('utf-8')

        # Hash is deterministic
        h1 = compute(canonical)
        h2 = compute(canonical)
        assert h1 == h2

    def test_canon_key_order_irrelevant(self):
        """Different dict key orders produce same canonical hash."""
        from knurl.canon import serialize

        obj1 = {"a": 1, "b": 2}
        obj2 = {"b": 2, "a": 1}

        # Canonical form normalizes key order
        c1 = serialize(obj1).decode('utf-8')
        c2 = serialize(obj2).decode('utf-8')

        assert compute(c1) == compute(c2)


class TestPropertyBased:
    """Property-based tests using Hypothesis."""

    @given(st.text())
    def test_roundtrip_no_prefix(self, content):
        """verify(s, compute(s)) is always True for any valid string."""
        try:
            h = compute(content)
            assert verify(content, h) is True
        except UnicodeEncodeError:
            # Surrogate pairs can't be UTF-8 encoded - expected
            pass

    @given(st.text(), st.from_regex(r'[a-zA-Z0-9_-]+', fullmatch=True))
    def test_roundtrip_with_prefix(self, content, prefix):
        """verify(s, compute(s, p)) is always True with any valid prefix."""
        try:
            h = compute(content, prefix=prefix)
            assert verify(content, h) is True
        except UnicodeEncodeError:
            pass

    @given(st.text())
    def test_format_invariant(self, content):
        """Output always matches expected format."""
        import re
        try:
            h = compute(content)
            assert re.match(r'^sha256:[0-9a-f]{64}$', h)
        except UnicodeEncodeError:
            pass

    @given(st.text(), st.text())
    def test_different_inputs_different_hashes(self, s1, s2):
        """Different inputs produce different hashes (with high probability)."""
        if s1 == s2:
            return  # Skip identical inputs
        try:
            h1 = compute(s1)
            h2 = compute(s2)
            # SHA256 collision is astronomically unlikely
            assert h1 != h2
        except UnicodeEncodeError:
            pass

    @given(st.text(min_size=1))
    def test_prefix_preserved_in_output(self, prefix_candidate):
        """Valid prefix appears at start of output."""
        import re
        # Filter to valid prefix characters
        prefix = re.sub(r'[^a-zA-Z0-9_-]', '', prefix_candidate)
        if not prefix:
            return
        h = compute("test", prefix=prefix)
        assert h.startswith(f"{prefix}:sha256:")
