"""Additional hash tests based on Oracle mantle edge case analysis.

These tests focus on edge cases Oracle identified that weren't fully covered:
- Unicode normalization forms (NFC, NFD, NFKC, NFKD)
- Line ending variations (Unix, Windows, Mac)
- Extreme content sizes (50MB+)
- Zero-width and invisible unicode characters
"""

import pytest
import unicodedata
from knurl.hash import compute, verify, HashError


class TestUnicodeNormalizationForms:
    """Test that different unicode normalization forms produce different hashes.

    This is intentional behavior - hash.py does NOT normalize unicode.
    The canon module is responsible for normalization if needed.
    """

    def test_nfc_vs_nfd_cafe(self):
        """Composed vs decomposed é in 'café' produces different hashes."""
        # NFC: é as single codepoint U+00E9
        cafe_nfc = "café"

        # NFD: e + combining acute accent
        cafe_nfd = unicodedata.normalize('NFD', cafe_nfc)

        # Different unicode representations
        assert cafe_nfc != cafe_nfd
        assert cafe_nfc.encode('utf-8') != cafe_nfd.encode('utf-8')

        # But hashes differ (we hash bytes as-is)
        hash_nfc = compute(cafe_nfc)
        hash_nfd = compute(cafe_nfd)
        assert hash_nfc != hash_nfd

        # Each verifies with its own form
        assert verify(cafe_nfc, hash_nfc)
        assert verify(cafe_nfd, hash_nfd)

        # Cross-verification fails
        assert not verify(cafe_nfc, hash_nfd)
        assert not verify(cafe_nfd, hash_nfc)

    def test_nfkc_vs_nfkd_ligatures(self):
        """Compatibility normalization of ligatures."""
        # ﬁ ligature (U+FB01) vs f + i
        fi_ligature = "\ufb01"
        fi_separate = "fi"

        # Normalize to compatibility form
        fi_nfkc = unicodedata.normalize('NFKC', fi_ligature)
        fi_nfkd = unicodedata.normalize('NFKD', fi_ligature)

        # All produce different hashes (we don't normalize)
        h_ligature = compute(fi_ligature)
        h_separate = compute(fi_separate)
        h_nfkc = compute(fi_nfkc)
        h_nfkd = compute(fi_nfkd)

        # All distinct (some might coincidentally match)
        hashes = {h_ligature, h_separate, h_nfkc, h_nfkd}
        # At minimum, ligature differs from separate
        assert h_ligature != h_separate

    def test_combining_diacritics_order(self):
        """Different diacritic order produces different hashes."""
        # e + acute + grave
        e_acute_grave = "e\u0301\u0300"
        # e + grave + acute
        e_grave_acute = "e\u0300\u0301"

        # Different byte sequences
        assert e_acute_grave.encode('utf-8') != e_grave_acute.encode('utf-8')

        # Different hashes
        assert compute(e_acute_grave) != compute(e_grave_acute)


class TestLineEndingVariations:
    """Comprehensive line ending tests."""

    def test_unix_vs_windows_vs_mac_line_endings(self):
        """LF, CRLF, CR all produce different hashes."""
        unix = "line1\nline2"      # LF
        windows = "line1\r\nline2"  # CRLF
        mac = "line1\rline2"        # CR

        h_unix = compute(unix)
        h_windows = compute(windows)
        h_mac = compute(mac)

        # All different
        assert h_unix != h_windows
        assert h_windows != h_mac
        assert h_unix != h_mac

    def test_mixed_line_endings(self):
        """Mixed line endings within same content."""
        mixed1 = "unix\nwindows\r\nmac\r"
        mixed2 = "unix\nwindows\nmac\n"  # All Unix

        # Different content, different hashes
        assert compute(mixed1) != compute(mixed2)

    def test_trailing_newline_matters(self):
        """Trailing newline affects hash."""
        without = "content"
        with_lf = "content\n"
        with_crlf = "content\r\n"

        h_without = compute(without)
        h_lf = compute(with_lf)
        h_crlf = compute(with_crlf)

        # All different
        assert len({h_without, h_lf, h_crlf}) == 3


class TestExtremeSizes:
    """Test with very large inputs."""

    def test_50mb_content(self):
        """50MB content hashes successfully."""
        # 50 million 'x' characters
        huge = "x" * (50 * 1024 * 1024)

        h = compute(huge)
        assert h.startswith("sha256:")

        # Still deterministic
        assert compute(huge) == h

        # Verify works
        assert verify(huge, h)

    def test_100mb_content_with_prefix(self):
        """100MB content with prefix."""
        huge = "a" * (100 * 1024 * 1024)

        h = compute(huge, prefix="huge")
        assert h.startswith("huge:sha256:")

        assert verify(huge, h)

    def test_million_line_breaks(self):
        """Content with 1 million newlines."""
        many_newlines = "\n" * 1_000_000

        h = compute(many_newlines)
        assert verify(many_newlines, h)


class TestZeroWidthAndInvisible:
    """Zero-width and invisible unicode characters."""

    def test_zero_width_space_affects_hash(self):
        """Zero-width space (invisible) changes hash."""
        without = "hello world"
        with_zwsp = "hello\u200bworld"  # Zero-width space between words

        # Visually identical in many renderers but different bytes
        assert compute(without) != compute(with_zwsp)

    def test_zero_width_joiner_affects_hash(self):
        """Zero-width joiner affects hash."""
        without = "👨👩👧👦"
        with_zwj = "👨\u200d👩\u200d👧\u200d👦"  # Family emoji via ZWJ

        # Different hashes
        assert compute(without) != compute(with_zwj)

    def test_soft_hyphen_affects_hash(self):
        """Soft hyphen (invisible optional line break) affects hash."""
        without = "extraordinary"
        with_shy = "extra\u00adordinary"  # Soft hyphen

        assert compute(without) != compute(with_shy)

    def test_bom_at_start_affects_hash(self):
        """Byte order mark at start of content."""
        without = "content"
        with_bom = "\ufeffcontent"  # BOM prefix

        assert compute(without) != compute(with_bom)

    def test_multiple_zero_width_chars(self):
        """Stacking multiple zero-width characters."""
        base = "test"

        # Different zero-width characters
        zwsp = "test\u200b"      # Zero-width space
        zwnj = "test\u200c"      # Zero-width non-joiner
        zwj = "test\u200d"       # Zero-width joiner

        hashes = {
            compute(base),
            compute(zwsp),
            compute(zwnj),
            compute(zwj)
        }

        # All different
        assert len(hashes) == 4


class TestWhitespaceEdgeCases:
    """Various whitespace character edge cases."""

    def test_all_unicode_whitespace_types(self):
        """Different unicode whitespace characters produce different hashes."""
        whitespaces = [
            " ",      # Space (U+0020)
            "\t",     # Tab (U+0009)
            "\n",     # Line feed (U+000A)
            "\r",     # Carriage return (U+000D)
            "\u00a0", # Non-breaking space
            "\u1680", # Ogham space mark
            "\u2000", # En quad
            "\u2001", # Em quad
            "\u2002", # En space
            "\u2003", # Em space
            "\u3000", # Ideographic space
        ]

        hashes = [compute(ws) for ws in whitespaces]

        # All different
        assert len(set(hashes)) == len(whitespaces)

    def test_multiple_spaces_vs_single(self):
        """Multiple consecutive spaces differ from single space."""
        one = "hello world"
        two = "hello  world"
        four = "hello    world"

        assert compute(one) != compute(two)
        assert compute(two) != compute(four)
        assert compute(one) != compute(four)


class TestPrefixEdgeCases:
    """Additional prefix edge cases from Oracle."""

    def test_prefix_length_extremes(self):
        """Test prefix length boundaries."""
        # Single character
        h1 = compute("test", prefix="a")
        assert h1.startswith("a:sha256:")

        # Very long (1000 chars)
        long_prefix = "x" * 1000
        h2 = compute("test", prefix=long_prefix)
        assert h2.startswith(f"{long_prefix}:sha256:")

        # Extremely long (100k chars) - technically allowed
        extreme_prefix = "y" * 100_000
        h3 = compute("test", prefix=extreme_prefix)
        assert h3.startswith(f"{extreme_prefix}:sha256:")

    def test_prefix_all_hyphens(self):
        """Prefix can be all hyphens."""
        h = compute("test", prefix="-----")
        assert h.startswith("-----:sha256:")

    def test_prefix_all_underscores(self):
        """Prefix can be all underscores."""
        h = compute("test", prefix="_____")
        assert h.startswith("_____:sha256:")

    def test_prefix_alternating_valid_chars(self):
        """Prefix alternating between valid character types."""
        h = compute("test", prefix="a1_b2-c3")
        assert h.startswith("a1_b2-c3:sha256:")


class TestVerifyEdgeCases:
    """Additional verify() edge cases."""

    def test_verify_with_prefix_extracted_correctly(self):
        """Verify extracts prefix correctly for comparison."""
        content = "data"

        # Hash with various prefixes
        h_a = compute(content, prefix="prefixA")
        h_b = compute(content, prefix="prefixB")
        h_none = compute(content)

        # Verify with correct prefix
        assert verify(content, h_a)
        assert verify(content, h_b)
        assert verify(content, h_none)

        # Cross-verification fails (prefix mismatch)
        assert not verify("wrong", h_a)
        assert not verify("wrong", h_b)
        assert not verify("wrong", h_none)

    def test_verify_case_sensitivity_in_digest(self):
        """Verify is case-sensitive on digest (must be lowercase)."""
        content = "test"
        h = compute(content)

        # Uppercase digest should be rejected during validation
        digest = h.split(":")[-1]
        uppercase_digest = "sha256:" + digest.upper()

        with pytest.raises(HashError):
            verify(content, uppercase_digest)
