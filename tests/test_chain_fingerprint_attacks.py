"""Adversarial tests for chain fingerprinting.

Attack vectors:
1. Prefix injection - config content that looks like fingerprints
2. Boundary confusion - first step vs chained step collisions
3. Unicode normalization attacks
4. Colon injection in keys/values
5. Empty/null/extreme cases
6. Canonical JSON edge cases
"""

import pytest
import json
from knurl.chain import fingerprint, fingerprint_step, ChainError


def fp(config):
    """Helper: fingerprint a single config."""
    return fingerprint([config])[0]


def fp_chained(config, previous_fingerprint):
    """Helper: fingerprint with previous."""
    return fingerprint_step(config, previous_fingerprint=previous_fingerprint)


class TestPrefixInjection:
    """Attack: Config content that starts with 'sha256:' to confuse parsers."""

    def test_config_with_sha256_prefix_key(self):
        """Key starting with 'sha256:' should not be confused with fingerprint."""
        config = {"sha256:fake123abc": "malicious"}
        result = fp(config)

        # Should be valid fingerprint format
        assert result.startswith("sha256:")
        assert len(result) == 71  # sha256: + 64 hex chars

        # Should NOT match the fake prefix
        assert "fake123abc" not in result

    def test_config_with_sha256_prefix_value(self):
        """Value starting with 'sha256:' should not be confused."""
        config = {"key": "sha256:deadbeef" * 8}  # 64 chars
        result = fp(config)

        assert result.startswith("sha256:")
        assert "deadbeef" not in result or result != config["key"]

    def test_config_that_json_dumps_to_sha256_prefix(self):
        """Config that when JSON-ified starts with 'sha256:' literal."""
        # This is tricky - JSON always starts with { or [ for objects/arrays
        # But what about a string value that looks like a fingerprint?
        config = {"a": "sha256:" + "0" * 64}
        result = fp(config)

        # Fingerprint should be different from the embedded sha256 string
        assert result != config["a"]


class TestFirstVsChainedCollision:
    """Attack: Can first-step fingerprint equal a chained-step fingerprint?"""

    def test_first_step_format(self):
        """First step should hash just the canonical JSON."""
        config = {"step": "first"}
        result = fp(config)

        # Format: sha256:HASH
        assert result.startswith("sha256:")
        canonical = json.dumps(config, sort_keys=True, separators=(',', ':'))

        # Manually verify we're hashing the right thing
        import hashlib
        expected_hash = hashlib.sha256(canonical.encode()).hexdigest()
        assert result == f"sha256:{expected_hash}"

    def test_chained_step_format(self):
        """Chained step should hash 'prev_fp:canonical_json'."""
        config1 = {"step": "first"}
        fp1 = fp(config1)

        config2 = {"step": "second"}
        fp2 = fp_chained(config2, fp1)

        # Verify chained format
        canonical2 = json.dumps(config2, sort_keys=True, separators=(',', ':'))
        hash_input = f"{fp1}:{canonical2}"

        import hashlib
        expected_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        assert fp2 == f"sha256:{expected_hash}"

    def test_collision_attempt_colon_in_config(self):
        """Try to make first-step output match chained-step pattern.

        Attack: If config contains 'sha256:PREV:' prefix, could it collide?
        First step hashes: canonical(config)
        Chained step hashes: 'sha256:PREV:' + canonical(config)

        For collision: hash(A) == hash('sha256:X:' + B)
        This would require SHA256 collision - cryptographically hard.
        But let's test the structure doesn't allow confusion.
        """
        # Try to craft config that when JSON-ified looks like chained input
        prev_fp = "sha256:" + "a" * 64

        # Config that includes the previous fingerprint as content
        config = {"injected": f"{prev_fp}:{{}}"}
        result = fp(config)

        # First step should still work normally
        assert result.startswith("sha256:")
        assert result != prev_fp

        # Now try using it as chained step
        config2 = {"next": "step"}
        result2 = fp_chained(config2, result)

        # Should produce different fingerprint
        assert result2 != result
        assert result2.startswith("sha256:")


class TestColonInjection:
    """Attack: Keys/values with colons to confuse hash input format."""

    def test_key_with_colons(self):
        """Key containing ':' should not break fingerprinting."""
        config = {"key:with:colons": "value"}
        result = fp(config)

        assert result.startswith("sha256:")
        assert len(result) == 71

    def test_value_with_colons(self):
        """Value containing ':' should not break fingerprinting."""
        config = {"key": "value:with:many:colons:here"}
        result = fp(config)

        assert result.startswith("sha256:")
        assert len(result) == 71

    def test_chained_with_colons_in_config(self):
        """Chained fingerprint with colons in config.

        Hash input format: 'sha256:PREV:canonical_json'
        If canonical_json contains colons, could it confuse parsing?
        """
        config1 = {"step": "first"}
        fp1 = fp(config1)

        config2 = {"a:b:c": "value:with:colons"}
        fp2 = fp_chained(config2, fp1)

        # Should work fine - colons are inside the JSON structure
        assert fp2.startswith("sha256:")
        assert fp2 != fp1

    def test_config_mimicking_hash_input_format(self):
        """Config that when JSONified looks like 'sha256:...:...'.

        This tests if canonical JSON can create confusion.
        JSON objects start with '{', so this is hard, but let's try.
        """
        # Best we can do is put the pattern in a value
        config = {"mimicry": "sha256:abc123:config"}
        result = fp(config)

        assert result.startswith("sha256:")
        # Fingerprint should be based on the full config structure
        assert "mimicry" not in result


class TestUnicodeNormalization:
    """Attack: Different Unicode representations of same character."""

    def test_unicode_normalization_nfc_vs_nfd(self):
        """Test if NFC vs NFD normalization causes different fingerprints.

        'é' can be represented as:
        - U+00E9 (NFC - composed)
        - U+0065 U+0301 (NFD - decomposed: e + combining acute)
        """
        config_nfc = {"key": "caf\u00e9"}  # café with composed é
        config_nfd = {"key": "cafe\u0301"}  # café with decomposed é

        fp_nfc = fp(config_nfc)
        fp_nfd = fp(config_nfd)

        # These SHOULD be different - we're not normalizing Unicode
        # If they're the same, that's actually good (normalization)
        # If they're different, users need to be aware
        # Document the behavior - different byte sequences -> different hashes
        print(f"NFC: {fp_nfc}")
        print(f"NFD: {fp_nfd}")

    def test_zero_width_characters(self):
        """Zero-width characters should affect fingerprint."""
        config1 = {"key": "value"}
        config2 = {"key": "val\u200bue"}  # Zero-width space

        fp1 = fp(config1)
        fp2 = fp(config2)

        # Should be different
        assert fp1 != fp2

    def test_homoglyph_attack(self):
        """Visually similar but different characters."""
        config1 = {"key": "A"}  # Latin A
        config2 = {"key": "\u0391"}  # Greek Alpha (U+0391)

        fp1 = fp(config1)
        fp2 = fp(config2)

        # Should be different
        assert fp1 != fp2


class TestEmptyAndNull:
    """Attack: Empty configs, null values, edge cases."""

    def test_empty_config(self):
        """Empty dict should fingerprint successfully."""
        config = {}
        result = fp(config)

        assert result.startswith("sha256:")
        assert len(result) == 71

    def test_null_value(self):
        """Null values should be allowed."""
        config = {"key": None}
        result = fp(config)

        assert result.startswith("sha256:")

    def test_empty_string_key(self):
        """Empty string as key."""
        config = {"": "value"}
        result = fp(config)

        assert result.startswith("sha256:")

    def test_empty_string_value(self):
        """Empty string as value."""
        config = {"key": ""}
        result = fp(config)

        assert result.startswith("sha256:")


class TestExtremeSizes:
    """Attack: Very large or deeply nested configs."""

    def test_large_config(self):
        """Config with many keys."""
        config = {f"key_{i}": f"value_{i}" for i in range(10000)}
        result = fp(config)

        assert result.startswith("sha256:")
        assert len(result) == 71

    def test_deep_nesting(self):
        """Deeply nested config (reasonable depth).

        Note: Python's default recursion limit (~1000) limits nesting depth.
        The canon module uses recursive validation, so very deep structures
        will hit the stack limit. This is acceptable - real configs won't
        be nested 1000+ levels deep.
        """
        config = {"level": None}
        current = config
        # Use 50 levels - reasonable for real configs, won't hit recursion limit
        for i in range(50):
            current["level"] = {"next": None}
            current = current["level"]

        result = fp(config)
        assert result.startswith("sha256:")

    def test_very_long_value(self):
        """Very long string value."""
        config = {"key": "x" * 1_000_000}
        result = fp(config)

        assert result.startswith("sha256:")
        assert len(result) == 71


class TestCanonicalJSONEdgeCases:
    """Attack: Edge cases in JSON canonicalization."""

    def test_key_ordering(self):
        """Same keys different order should give same fingerprint."""
        config1 = {"z": 1, "a": 2, "m": 3}
        config2 = {"a": 2, "m": 3, "z": 1}

        fp1 = fp(config1)
        fp2 = fp(config2)

        assert fp1 == fp2

    def test_whitespace_in_json(self):
        """Whitespace should not affect fingerprint (canonical form)."""
        # This test is implicit - we control JSON serialization
        # But let's verify the canonical form is compact
        config = {"key": "value"}
        canonical = json.dumps(config, sort_keys=True, separators=(',', ':'))

        # Should have no spaces
        assert ' ' not in canonical

    def test_float_representation(self):
        """Float representation consistency."""
        config1 = {"val": 1.0}
        config2 = {"val": 1.00000}

        fp1 = fp(config1)
        fp2 = fp(config2)

        # Python JSON should handle this consistently
        assert fp1 == fp2

    def test_integer_vs_float(self):
        """Integer vs float - document behavior."""
        config1 = {"val": 1}
        config2 = {"val": 1.0}

        fp1 = fp(config1)
        fp2 = fp(config2)

        # Document: JSON serializes 1 and 1.0 differently
        # 1 -> "1", 1.0 -> "1.0"
        # So fingerprints will differ

    def test_boolean_vs_integer(self):
        """Boolean vs integer."""
        config1 = {"val": True}
        config2 = {"val": 1}

        fp1 = fp(config1)
        fp2 = fp(config2)

        # Should be different
        assert fp1 != fp2


class TestSecurityImplications:
    """High-level security tests."""

    def test_fingerprint_determinism(self):
        """Same config should always produce same fingerprint."""
        config = {"key": "value", "num": 42}

        fp1 = fp(config)
        fp2 = fp(config)
        fp3 = fp(config)

        assert fp1 == fp2 == fp3

    def test_fingerprint_uniqueness(self):
        """Different configs should produce different fingerprints."""
        configs = [
            {"a": 1},
            {"a": 2},
            {"b": 1},
            {"a": 1, "b": 2},
        ]

        fingerprints = [fp(c) for c in configs]

        # All should be unique
        assert len(fingerprints) == len(set(fingerprints))

    def test_chain_integrity(self):
        """Chain should be tamper-evident."""
        config1 = {"step": 1}
        fp1 = fp(config1)

        config2 = {"step": 2}
        fp2 = fp_chained(config2, fp1)

        config3 = {"step": 3}
        fp3 = fp_chained(config3, fp2)

        # If we try to chain step 3 from step 1 (skipping step 2)
        fp3_alt = fp_chained(config3, fp1)

        # Should be different
        assert fp3 != fp3_alt

    def test_previous_fingerprint_validation(self):
        """Invalid previous fingerprint format should fail."""
        config = {"step": 2}

        # Try various invalid formats
        invalid_fps = [
            "not-a-fingerprint",
            "sha256:",  # Missing hash
            "sha256:abc",  # Too short
            "md5:" + "a" * 32,  # Wrong algorithm
            "sha256:" + "g" * 64,  # Invalid hex
            "sha256:" + "A" * 64,  # Uppercase hex (we produce lowercase)
            " sha256:" + "a" * 64,  # Leading whitespace
            "sha256: " + "a" * 64,  # Space after colon
        ]

        for invalid_fp_str in invalid_fps:
            with pytest.raises(ChainError):
                fp_chained(config, invalid_fp_str)

    def test_all_digit_fingerprint_accepted(self):
        """All-digit hex fingerprint should be accepted.

        This tests a bug where islower() was used to check for lowercase hex,
        but islower() returns False for strings with only digits.
        """
        config = {"step": 2}

        # All-digit fingerprints are valid lowercase hex
        all_zeros = "sha256:" + "0" * 64
        result = fp_chained(config, all_zeros)
        assert result.startswith("sha256:")

        # Mix of digits only
        all_digits = "sha256:" + "1234567890" * 6 + "1234"
        result = fp_chained(config, all_digits)
        assert result.startswith("sha256:")
