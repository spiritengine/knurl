"""
Tests for knurl.address module.

Tests follow the Rock-Solid Primitive playbook: define what "correct" means before implementing.

Coverage:
- Happy path: basic parse/construct/validate usage
- Edge cases: empty, unicode, whitespace, multiple slashes
- Error cases: invalid inputs, malformed addresses
"""

import pytest

# Import will fail until implementation exists
from knurl.address import (
    parse,
    construct,
    validate,
    AddressError,
    ParsedAddress,
)


class TestParse:
    """Tests for parse() function."""

    # === Layer 1: Bare folio ID ===

    def test_parse_bare_folio_id(self):
        """Bare folio ID returns (None, folio_id)."""
        result = parse("brief-20251226-n1br")
        assert result == ParsedAddress(user=None, project=None, folio_id="brief-20251226-n1br")

    def test_parse_bare_issue(self):
        """Different folio types work."""
        result = parse("issue-20251106-a7b3")
        assert result == ParsedAddress(user=None, project=None, folio_id="issue-20251106-a7b3")

    def test_parse_bare_friction(self):
        result = parse("friction-20251225-xyz9")
        assert result == ParsedAddress(user=None, project=None, folio_id="friction-20251225-xyz9")

    # === Layer 2: Project-qualified ===

    def test_parse_project_qualified(self):
        """project/folio_id returns (project, folio_id)."""
        result = parse("speakbot/brief-20251226-n1br")
        assert result == ParsedAddress(user=None, project="speakbot", folio_id="brief-20251226-n1br")

    def test_parse_project_with_hyphen(self):
        """Project names with hyphens work."""
        result = parse("my-project/issue-20251106-a7b3")
        assert result == ParsedAddress(user=None, project="my-project", folio_id="issue-20251106-a7b3")

    def test_parse_project_with_underscore(self):
        """Project names with underscores work."""
        result = parse("my_project/issue-20251106-a7b3")
        assert result == ParsedAddress(user=None, project="my_project", folio_id="issue-20251106-a7b3")

    def test_parse_project_with_numbers(self):
        """Project names with numbers work."""
        result = parse("project123/brief-20251226-n1br")
        assert result == ParsedAddress(user=None, project="project123", folio_id="brief-20251226-n1br")

    # === Layer 3: User-scoped ===

    def test_parse_user_scoped(self):
        """@user/project/folio_id returns full ParsedAddress."""
        result = parse("@patrick/speakbot/brief-20251226-n1br")
        assert result == ParsedAddress(user="patrick", project="speakbot", folio_id="brief-20251226-n1br")

    def test_parse_user_with_hyphen(self):
        """User names with hyphens work."""
        result = parse("@my-user/project/issue-20251106-a7b3")
        assert result == ParsedAddress(user="my-user", project="project", folio_id="issue-20251106-a7b3")

    def test_parse_user_with_underscore(self):
        """User names with underscores work."""
        result = parse("@my_user/project/issue-20251106-a7b3")
        assert result == ParsedAddress(user="my_user", project="project", folio_id="issue-20251106-a7b3")

    # === Edge Cases ===

    def test_parse_preserves_case_in_project(self):
        """Case is preserved in project names."""
        result = parse("MyProject/brief-20251226-n1br")
        assert result == ParsedAddress(user=None, project="MyProject", folio_id="brief-20251226-n1br")

    def test_parse_strips_whitespace(self):
        """Leading/trailing whitespace is stripped."""
        result = parse("  brief-20251226-n1br  ")
        assert result == ParsedAddress(user=None, project=None, folio_id="brief-20251226-n1br")

    def test_parse_strips_whitespace_project(self):
        """Whitespace stripped from project-qualified."""
        result = parse("  speakbot/brief-20251226-n1br  ")
        assert result == ParsedAddress(user=None, project="speakbot", folio_id="brief-20251226-n1br")

    # === Error Cases ===

    def test_parse_empty_string(self):
        """Empty string raises AddressError."""
        with pytest.raises(AddressError, match="empty"):
            parse("")

    def test_parse_whitespace_only(self):
        """Whitespace-only string raises AddressError."""
        with pytest.raises(AddressError, match="empty"):
            parse("   ")

    def test_parse_none_raises(self):
        """None input raises AddressError."""
        with pytest.raises(AddressError, match="must be a string"):
            parse(None)

    def test_parse_non_string_raises(self):
        """Non-string input raises AddressError."""
        with pytest.raises(AddressError, match="must be a string"):
            parse(123)

    def test_parse_multiple_slashes_error(self):
        """More than 2 slashes (excluding @ prefix) is an error."""
        with pytest.raises(AddressError, match="too many"):
            parse("a/b/c/d")

    def test_parse_empty_project_error(self):
        """Empty project name is an error."""
        with pytest.raises(AddressError, match="empty.*project"):
            parse("/brief-20251226-n1br")

    def test_parse_empty_folio_id_error(self):
        """Empty folio ID is an error."""
        with pytest.raises(AddressError, match="empty.*folio"):
            parse("speakbot/")

    def test_parse_empty_user_error(self):
        """Empty user name is an error."""
        with pytest.raises(AddressError, match="empty.*user"):
            parse("@/project/brief-20251226-n1br")

    def test_parse_at_without_slash_is_bare(self):
        """@ in folio ID without slash is treated as bare."""
        # Unusual but valid: if someone has a folio ID starting with @
        # We treat this as bare since there's no slash
        with pytest.raises(AddressError, match="invalid.*folio"):
            parse("@notavalidfolio")

    def test_parse_invalid_project_chars(self):
        """Project names with invalid characters raise error."""
        with pytest.raises(AddressError, match="invalid.*project"):
            parse("proj!ect/brief-20251226-n1br")

    def test_parse_invalid_user_chars(self):
        """User names with invalid characters raise error."""
        with pytest.raises(AddressError, match="invalid.*user"):
            parse("@us!er/project/brief-20251226-n1br")

    def test_parse_trailing_slash_error(self):
        """Trailing slash with no folio is an error."""
        with pytest.raises(AddressError, match="empty.*folio"):
            parse("project/")


class TestConstruct:
    """Tests for construct() function."""

    def test_construct_bare(self):
        """Construct bare address from folio_id only."""
        result = construct(folio_id="brief-20251226-n1br")
        assert result == "brief-20251226-n1br"

    def test_construct_project_qualified(self):
        """Construct project-qualified address."""
        result = construct(project="speakbot", folio_id="brief-20251226-n1br")
        assert result == "speakbot/brief-20251226-n1br"

    def test_construct_user_scoped(self):
        """Construct user-scoped address."""
        result = construct(user="patrick", project="speakbot", folio_id="brief-20251226-n1br")
        assert result == "@patrick/speakbot/brief-20251226-n1br"

    def test_construct_none_project_is_bare(self):
        """None project produces bare address."""
        result = construct(project=None, folio_id="brief-20251226-n1br")
        assert result == "brief-20251226-n1br"

    def test_construct_empty_project_is_bare(self):
        """Empty string project produces bare address."""
        result = construct(project="", folio_id="brief-20251226-n1br")
        assert result == "brief-20251226-n1br"

    # === Error Cases ===

    def test_construct_missing_folio_id(self):
        """Missing folio_id raises error."""
        with pytest.raises(AddressError, match="folio_id.*required"):
            construct()

    def test_construct_none_folio_id(self):
        """None folio_id raises error."""
        with pytest.raises(AddressError, match="folio_id.*required"):
            construct(folio_id=None)

    def test_construct_empty_folio_id(self):
        """Empty folio_id raises error."""
        with pytest.raises(AddressError, match="folio_id.*required"):
            construct(folio_id="")

    def test_construct_user_without_project(self):
        """User without project raises error (can't have Layer 3 without Layer 2)."""
        with pytest.raises(AddressError, match="project.*required.*user"):
            construct(user="patrick", folio_id="brief-20251226-n1br")

    def test_construct_invalid_project_chars(self):
        """Invalid project characters raise error."""
        with pytest.raises(AddressError, match="invalid.*project"):
            construct(project="bad/name", folio_id="brief-20251226-n1br")

    def test_construct_invalid_user_chars(self):
        """Invalid user characters raise error."""
        with pytest.raises(AddressError, match="invalid.*user"):
            construct(user="bad@name", project="project", folio_id="brief-20251226-n1br")


class TestValidate:
    """Tests for validate() function."""

    # === Valid addresses ===

    def test_validate_bare_folio(self):
        """Valid bare folio ID returns True."""
        assert validate("brief-20251226-n1br") is True

    def test_validate_project_qualified(self):
        """Valid project-qualified address returns True."""
        assert validate("speakbot/brief-20251226-n1br") is True

    def test_validate_user_scoped(self):
        """Valid user-scoped address returns True."""
        assert validate("@patrick/speakbot/brief-20251226-n1br") is True

    def test_validate_various_types(self):
        """Various folio types are valid."""
        types = ["brief", "issue", "friction", "finding", "notion",
                 "summary", "tender", "plan", "playbook", "mantle", "writ"]
        for t in types:
            assert validate(f"{t}-20251226-abc1") is True

    # === Invalid addresses ===

    def test_validate_empty(self):
        """Empty string is invalid."""
        assert validate("") is False

    def test_validate_whitespace(self):
        """Whitespace only is invalid."""
        assert validate("   ") is False

    def test_validate_bad_format(self):
        """Bad format is invalid."""
        assert validate("not-a-valid-address") is False

    def test_validate_invalid_project(self):
        """Invalid project chars is invalid."""
        assert validate("bad!project/brief-20251226-n1br") is False

    def test_validate_empty_project(self):
        """Empty project is invalid."""
        assert validate("/brief-20251226-n1br") is False

    def test_validate_too_many_slashes(self):
        """Too many slashes is invalid."""
        assert validate("a/b/c/d") is False

    def test_validate_non_string(self):
        """Non-string is invalid (returns False, doesn't raise)."""
        assert validate(None) is False
        assert validate(123) is False
        assert validate([]) is False


class TestValidateFolioFormat:
    """Tests for folio ID format validation."""

    def test_validate_correct_format(self):
        """Correct folio format is valid."""
        # {type}-{YYYYMMDD}-{4char}
        assert validate("brief-20251226-n1br") is True
        assert validate("issue-20251106-a7b3") is True

    def test_validate_date_must_be_8_digits(self):
        """Date part must be exactly 8 digits."""
        assert validate("brief-2025126-n1br") is False  # 7 digits
        assert validate("brief-202512260-n1br") is False  # 9 digits

    def test_validate_suffix_must_be_4_chars(self):
        """Suffix must be exactly 4 chars."""
        assert validate("brief-20251226-n1b") is False  # 3 chars
        assert validate("brief-20251226-n1brx") is False  # 5 chars

    def test_validate_suffix_alphanumeric_lowercase(self):
        """Suffix must be lowercase alphanumeric."""
        assert validate("brief-20251226-N1BR") is False  # uppercase
        assert validate("brief-20251226-n1b!") is False  # special char

    def test_validate_unknown_type_rejected(self):
        """Unknown folio types are rejected."""
        assert validate("unknown-20251226-n1br") is False
        assert validate("foo-20251226-n1br") is False

    def test_validate_invalid_date_rejected(self):
        """Invalid dates in folio IDs are rejected."""
        # Month 13
        assert validate("brief-20251301-n1br") is False
        # Day 32
        assert validate("brief-20251232-n1br") is False
        # Month 00
        assert validate("brief-20250001-n1br") is False
        # Day 00
        assert validate("brief-20250100-n1br") is False
        # Feb 30
        assert validate("brief-20250230-n1br") is False
        # Feb 29 in non-leap year
        assert validate("brief-20230229-n1br") is False

    def test_validate_valid_dates_accepted(self):
        """Valid dates are accepted."""
        # Normal date
        assert validate("brief-20251226-n1br") is True
        # Feb 29 in leap year
        assert validate("brief-20240229-n1br") is True
        # End of month
        assert validate("brief-20251231-n1br") is True


class TestRoundTrip:
    """Tests that parse and construct are inverses."""

    def test_roundtrip_bare(self):
        """parse(construct(x)) == x for bare addresses."""
        addr = "brief-20251226-n1br"
        parsed = parse(addr)
        reconstructed = construct(folio_id=parsed.folio_id)
        assert reconstructed == addr

    def test_roundtrip_project(self):
        """parse(construct(x)) == x for project-qualified."""
        addr = "speakbot/brief-20251226-n1br"
        parsed = parse(addr)
        reconstructed = construct(project=parsed.project, folio_id=parsed.folio_id)
        assert reconstructed == addr

    def test_roundtrip_user(self):
        """parse(construct(x)) == x for user-scoped."""
        addr = "@patrick/speakbot/brief-20251226-n1br"
        parsed = parse(addr)
        reconstructed = construct(user=parsed.user, project=parsed.project, folio_id=parsed.folio_id)
        assert reconstructed == addr

    def test_construct_then_parse(self):
        """construct then parse returns same values."""
        user, project, folio = "alice", "myproj", "issue-20251226-abcd"
        addr = construct(user=user, project=project, folio_id=folio)
        parsed = parse(addr)
        assert parsed.user == user
        assert parsed.project == project
        assert parsed.folio_id == folio


class TestLengthLimits:
    """Tests for length-based DoS prevention."""

    def test_parse_very_long_project(self):
        """Very long project names are rejected."""
        long_project = "a" * 1000
        with pytest.raises(AddressError, match="too long|length"):
            parse(f"{long_project}/brief-20251226-n1br")

    def test_parse_very_long_user(self):
        """Very long user names are rejected."""
        long_user = "a" * 1000
        with pytest.raises(AddressError, match="too long|length"):
            parse(f"@{long_user}/project/brief-20251226-n1br")

    def test_parse_very_long_address(self):
        """Very long total address is rejected."""
        # Even if individual components are ok, total length matters
        long_addr = "a" * 300 + "/brief-20251226-n1br"
        with pytest.raises(AddressError, match="too long|length"):
            parse(long_addr)

    def test_construct_very_long_project(self):
        """Very long project names rejected in construct."""
        with pytest.raises(AddressError, match="too long|length"):
            construct(project="x" * 1000, folio_id="brief-20251226-n1br")

    def test_reasonable_length_ok(self):
        """Reasonable length names work."""
        # 50 chars is reasonable
        result = parse("a" * 50 + "/brief-20251226-n1br")
        assert result.project == "a" * 50


class TestWhitespaceHandling:
    """Tests for whitespace handling edge cases."""

    def test_parse_whitespace_around_slash(self):
        """Whitespace around slashes is handled."""
        # Should either strip or reject clearly
        result = parse("speakbot / brief-20251226-n1br")
        # Expect stripped
        assert result.project == "speakbot"
        assert result.folio_id == "brief-20251226-n1br"

    def test_parse_whitespace_in_user_scoped(self):
        """Whitespace around slashes in user-scoped is handled."""
        result = parse("@patrick / speakbot / brief-20251226-n1br")
        assert result.user == "patrick"
        assert result.project == "speakbot"
        assert result.folio_id == "brief-20251226-n1br"


class TestEdgeCaseErrorMessages:
    """Tests for clear error messages on edge cases."""

    def test_double_slash_shows_empty_component(self):
        """Double slash gives clear empty component message."""
        with pytest.raises(AddressError, match="empty"):
            parse("project//brief-20251226-n1br")

    def test_leading_slash_shows_empty_project(self):
        """Leading slash gives clear empty project message."""
        with pytest.raises(AddressError, match="empty.*project"):
            parse("/brief-20251226-n1br")


class TestParsedAddress:
    """Tests for ParsedAddress dataclass."""

    def test_parsed_address_equality(self):
        """ParsedAddress instances with same values are equal."""
        a = ParsedAddress(user="x", project="y", folio_id="z")
        b = ParsedAddress(user="x", project="y", folio_id="z")
        assert a == b

    def test_parsed_address_inequality(self):
        """ParsedAddress instances with different values are not equal."""
        a = ParsedAddress(user="x", project="y", folio_id="z")
        b = ParsedAddress(user="a", project="y", folio_id="z")
        assert a != b

    def test_parsed_address_none_defaults(self):
        """ParsedAddress can have None for user and project."""
        p = ParsedAddress(user=None, project=None, folio_id="brief-20251226-n1br")
        assert p.user is None
        assert p.project is None
        assert p.folio_id == "brief-20251226-n1br"

    def test_parsed_address_is_bare(self):
        """is_bare property returns True when no project."""
        bare = ParsedAddress(user=None, project=None, folio_id="brief-20251226-n1br")
        qualified = ParsedAddress(user=None, project="x", folio_id="brief-20251226-n1br")
        assert bare.is_bare is True
        assert qualified.is_bare is False

    def test_parsed_address_is_user_scoped(self):
        """is_user_scoped property returns True when user present."""
        bare = ParsedAddress(user=None, project=None, folio_id="x")
        project = ParsedAddress(user=None, project="p", folio_id="x")
        user = ParsedAddress(user="u", project="p", folio_id="x")
        assert bare.is_user_scoped is False
        assert project.is_user_scoped is False
        assert user.is_user_scoped is True


# === Property-Based Tests ===

from hypothesis import given, strategies as st, assume
from knurl.address import VALID_FOLIO_TYPES


# Strategy for valid 4-char suffixes (lowercase alphanumeric)
suffix_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
    min_size=4,
    max_size=4,
)

# Strategy for valid folio types
folio_type_strategy = st.sampled_from(sorted(VALID_FOLIO_TYPES))

# Strategy for valid dates (formatted as YYYYMMDD)
# Constrain to years 1000-9999 to ensure 8-digit dates
from datetime import date
date_strategy = st.dates(
    min_value=date(1000, 1, 1),
    max_value=date(9999, 12, 31),
).map(lambda d: d.strftime("%Y%m%d"))

# Strategy for valid project/user names (alphanumeric + hyphen + underscore, 1-128 chars)
name_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
    min_size=1,
    max_size=128,
)


@st.composite
def folio_id_strategy(draw):
    """Generate valid folio IDs."""
    folio_type = draw(folio_type_strategy)
    date = draw(date_strategy)
    suffix = draw(suffix_strategy)
    return f"{folio_type}-{date}-{suffix}"


class TestPropertyBased:
    """Property-based tests using Hypothesis."""

    @given(folio_id=folio_id_strategy())
    def test_roundtrip_bare_address(self, folio_id):
        """Round-trip invariant for bare addresses: parse(construct(...)) returns same components."""
        addr = construct(folio_id=folio_id)
        parsed = parse(addr)
        assert parsed.user is None
        assert parsed.project is None
        assert parsed.folio_id == folio_id

    @given(project=name_strategy, folio_id=folio_id_strategy())
    def test_roundtrip_project_address(self, project, folio_id):
        """Round-trip invariant for project-qualified addresses."""
        addr = construct(project=project, folio_id=folio_id)
        parsed = parse(addr)
        assert parsed.user is None
        assert parsed.project == project
        assert parsed.folio_id == folio_id

    @given(user=name_strategy, project=name_strategy, folio_id=folio_id_strategy())
    def test_roundtrip_user_scoped_address(self, user, project, folio_id):
        """Round-trip invariant for user-scoped addresses."""
        addr = construct(user=user, project=project, folio_id=folio_id)
        parsed = parse(addr)
        assert parsed.user == user
        assert parsed.project == project
        assert parsed.folio_id == folio_id

    @given(folio_id=folio_id_strategy())
    def test_parse_idempotent_bare(self, folio_id):
        """Idempotence: parse(addr) called twice gives same result."""
        addr = construct(folio_id=folio_id)
        parsed1 = parse(addr)
        parsed2 = parse(addr)
        assert parsed1 == parsed2

    @given(project=name_strategy, folio_id=folio_id_strategy())
    def test_parse_idempotent_project(self, project, folio_id):
        """Idempotence: parse(addr) called twice gives same result for project-qualified."""
        addr = construct(project=project, folio_id=folio_id)
        parsed1 = parse(addr)
        parsed2 = parse(addr)
        assert parsed1 == parsed2

    @given(user=name_strategy, project=name_strategy, folio_id=folio_id_strategy())
    def test_parse_idempotent_user_scoped(self, user, project, folio_id):
        """Idempotence: parse(addr) called twice gives same result for user-scoped."""
        addr = construct(user=user, project=project, folio_id=folio_id)
        parsed1 = parse(addr)
        parsed2 = parse(addr)
        assert parsed1 == parsed2

    @given(folio_id=folio_id_strategy())
    def test_validate_true_for_constructed_bare(self, folio_id):
        """validate() returns True for any constructed bare address."""
        addr = construct(folio_id=folio_id)
        assert validate(addr) is True

    @given(project=name_strategy, folio_id=folio_id_strategy())
    def test_validate_true_for_constructed_project(self, project, folio_id):
        """validate() returns True for any constructed project-qualified address."""
        addr = construct(project=project, folio_id=folio_id)
        assert validate(addr) is True

    @given(user=name_strategy, project=name_strategy, folio_id=folio_id_strategy())
    def test_validate_true_for_constructed_user_scoped(self, user, project, folio_id):
        """validate() returns True for any constructed user-scoped address."""
        addr = construct(user=user, project=project, folio_id=folio_id)
        assert validate(addr) is True

    @given(folio_id=folio_id_strategy())
    def test_valid_address_is_parseable_bare(self, folio_id):
        """Any address that passes validate() should be parseable without exception."""
        addr = construct(folio_id=folio_id)
        if validate(addr):
            # Should not raise
            parsed = parse(addr)
            assert parsed is not None

    @given(project=name_strategy, folio_id=folio_id_strategy())
    def test_valid_address_is_parseable_project(self, project, folio_id):
        """Any project-qualified address that passes validate() should be parseable."""
        addr = construct(project=project, folio_id=folio_id)
        if validate(addr):
            parsed = parse(addr)
            assert parsed is not None

    @given(user=name_strategy, project=name_strategy, folio_id=folio_id_strategy())
    def test_valid_address_is_parseable_user_scoped(self, user, project, folio_id):
        """Any user-scoped address that passes validate() should be parseable."""
        addr = construct(user=user, project=project, folio_id=folio_id)
        if validate(addr):
            parsed = parse(addr)
            assert parsed is not None

    @given(st.text())
    def test_validate_implies_parseable(self, addr):
        """For any string, if validate() returns True, parse() must not raise."""
        if validate(addr):
            # Should not raise
            parsed = parse(addr)
            assert parsed is not None
