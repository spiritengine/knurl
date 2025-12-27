"""
Parse and construct layered SKEIN addresses.

SKEIN addresses support three layers:
- Layer 1 (Bare): folio_id only, e.g., "brief-20251226-n1br"
- Layer 2 (Project): project/folio_id, e.g., "speakbot/brief-20251226-n1br"
- Layer 3 (User): @user/project/folio_id, e.g., "@patrick/speakbot/brief-20251226-n1br"

Usage:
    from spiritengine.address import parse, construct, validate, ParsedAddress

    # Parse addresses
    parse("brief-20251226-n1br")
    # → ParsedAddress(user=None, project=None, folio_id="brief-20251226-n1br")

    parse("speakbot/brief-20251226-n1br")
    # → ParsedAddress(user=None, project="speakbot", folio_id="brief-20251226-n1br")

    parse("@patrick/speakbot/brief-20251226-n1br")
    # → ParsedAddress(user="patrick", project="speakbot", folio_id="brief-20251226-n1br")

    # Construct addresses
    construct(folio_id="brief-20251226-n1br")
    # → "brief-20251226-n1br"

    construct(project="speakbot", folio_id="brief-20251226-n1br")
    # → "speakbot/brief-20251226-n1br"

    # Validate addresses
    validate("brief-20251226-n1br")  # → True
    validate("not valid!")  # → False
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


class AddressError(Exception):
    """Raised when an address cannot be parsed or constructed.

    Common causes:
    - Empty address string
    - Invalid characters in user/project name
    - Malformed folio ID
    - Too many path components
    """
    pass


# Valid folio types in SKEIN
VALID_FOLIO_TYPES = frozenset([
    "brief", "issue", "friction", "finding", "notion",
    "summary", "tender", "plan", "playbook", "mantle", "writ",
    "thread", "sack",  # Internal types
])

# Regex for valid user/project names: alphanumeric, hyphen, underscore
NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')

# Regex for folio ID: {type}-{YYYYMMDD}-{4lowercase_alphanumeric}
# Type bounded to 1-32 chars as defensive measure (longest SKEIN type is ~10 chars)
FOLIO_ID_PATTERN = re.compile(
    r'^([a-z]{1,32})-(\d{8})-([a-z0-9]{4})$'
)

# Length limits to prevent DoS attacks
MAX_ADDRESS_LENGTH = 256  # Total address string
MAX_NAME_LENGTH = 128     # User or project name


@dataclass(frozen=True)
class ParsedAddress:
    """Result of parsing a SKEIN address.

    Attributes:
        user: User name (Layer 3) or None
        project: Project name (Layer 2) or None
        folio_id: The folio identifier (always present)
    """
    user: Optional[str]
    project: Optional[str]
    folio_id: str

    @property
    def is_bare(self) -> bool:
        """True if this is a bare (Layer 1) address with no project."""
        return self.project is None

    @property
    def is_user_scoped(self) -> bool:
        """True if this is a user-scoped (Layer 3) address."""
        return self.user is not None


def _validate_name(name: str, field: str) -> None:
    """Validate a user or project name.

    Args:
        name: The name to validate
        field: Field name for error messages ("user" or "project")

    Raises:
        AddressError: If name is empty, too long, or contains invalid characters
    """
    if not name:
        raise AddressError(f"Address has empty {field} name")
    if len(name) > MAX_NAME_LENGTH:
        raise AddressError(
            f"Address has {field} name that is too long: {len(name)} chars "
            f"(max {MAX_NAME_LENGTH})"
        )
    if not NAME_PATTERN.match(name):
        raise AddressError(
            f"Address has invalid {field} name: {name!r}. "
            f"Must contain only alphanumeric characters, hyphens, and underscores."
        )


def _validate_folio_id(folio_id: str) -> None:
    """Validate a folio ID format.

    Args:
        folio_id: The folio ID to validate

    Raises:
        AddressError: If folio ID format is invalid
    """
    if not folio_id:
        raise AddressError("Address has empty folio ID")

    match = FOLIO_ID_PATTERN.match(folio_id)
    if not match:
        raise AddressError(
            f"Address has invalid folio ID format: {folio_id!r}. "
            f"Expected format: {{type}}-{{YYYYMMDD}}-{{4char}}"
        )

    folio_type = match.group(1)
    if folio_type not in VALID_FOLIO_TYPES:
        raise AddressError(
            f"Address has unknown folio type: {folio_type!r}. "
            f"Valid types: {', '.join(sorted(VALID_FOLIO_TYPES))}"
        )


def parse(address: str) -> ParsedAddress:
    """Parse a SKEIN address string into components.

    Args:
        address: A SKEIN address string in one of these formats:
            - "folio_id" (bare)
            - "project/folio_id" (project-qualified)
            - "@user/project/folio_id" (user-scoped)

    Returns:
        ParsedAddress with user, project, and folio_id fields.

    Raises:
        AddressError: If the address is invalid.

    Examples:
        >>> parse("brief-20251226-n1br")
        ParsedAddress(user=None, project=None, folio_id='brief-20251226-n1br')

        >>> parse("speakbot/brief-20251226-n1br")
        ParsedAddress(user=None, project='speakbot', folio_id='brief-20251226-n1br')

        >>> parse("@patrick/speakbot/brief-20251226-n1br")
        ParsedAddress(user='patrick', project='speakbot', folio_id='brief-20251226-n1br')
    """
    # Type check
    if not isinstance(address, str):
        raise AddressError(
            f"Address must be a string, got {type(address).__name__}"
        )

    # Strip whitespace
    address = address.strip()

    # Check for empty
    if not address:
        raise AddressError("Address is empty")

    # Check total length
    if len(address) > MAX_ADDRESS_LENGTH:
        raise AddressError(
            f"Address is too long: {len(address)} chars (max {MAX_ADDRESS_LENGTH})"
        )

    # Check for user-scoped address (@user/project/folio_id)
    if address.startswith("@"):
        # Remove @ prefix
        address_body = address[1:]

        # Split and strip each component
        parts = [p.strip() for p in address_body.split("/")]

        # Check for empty components (from "//" or "/ /")
        if "" in parts:
            # Find which one is empty
            if parts[0] == "":
                raise AddressError("Address has empty user name")
            elif len(parts) > 1 and parts[1] == "":
                raise AddressError("Address has empty project name")
            else:
                raise AddressError("Address has empty folio ID")

        # Must have exactly 3 parts for user-scoped
        if len(parts) != 3:
            if len(parts) < 3:
                raise AddressError(
                    f"Address has invalid folio ID format: {address!r}. "
                    f"Expected format: {{type}}-{{YYYYMMDD}}-{{4char}}"
                )
            raise AddressError(
                f"Address has too many path components: {address!r}. "
                f"Expected format: @user/project/folio_id"
            )

        user, project, folio_id = parts

        # Validate components
        _validate_name(user, "user")
        _validate_name(project, "project")
        _validate_folio_id(folio_id)

        return ParsedAddress(user=user, project=project, folio_id=folio_id)

    # Non-@ address: split and strip components
    parts = [p.strip() for p in address.split("/")]

    # Check for empty components (from "//" or leading "/")
    if "" in parts:
        if parts[0] == "":
            raise AddressError("Address has empty project name")
        else:
            raise AddressError("Address has empty folio ID")

    if len(parts) == 1:
        # Bare folio ID
        folio_id = parts[0]
        _validate_folio_id(folio_id)
        return ParsedAddress(user=None, project=None, folio_id=folio_id)

    elif len(parts) == 2:
        # Project-qualified
        project, folio_id = parts
        _validate_name(project, "project")
        _validate_folio_id(folio_id)
        return ParsedAddress(user=None, project=project, folio_id=folio_id)

    else:
        # Too many slashes
        raise AddressError(
            f"Address has too many path components: {address!r}. "
            f"Expected format: folio_id or project/folio_id"
        )


def construct(
    *,
    user: Optional[str] = None,
    project: Optional[str] = None,
    folio_id: Optional[str] = None,
) -> str:
    """Construct a SKEIN address string from components.

    Args:
        user: Optional user name (Layer 3). Requires project if specified.
        project: Optional project name (Layer 2).
        folio_id: The folio identifier (required).

    Returns:
        A SKEIN address string.

    Raises:
        AddressError: If required fields are missing or values are invalid.

    Examples:
        >>> construct(folio_id="brief-20251226-n1br")
        'brief-20251226-n1br'

        >>> construct(project="speakbot", folio_id="brief-20251226-n1br")
        'speakbot/brief-20251226-n1br'

        >>> construct(user="patrick", project="speakbot", folio_id="brief-20251226-n1br")
        '@patrick/speakbot/brief-20251226-n1br'
    """
    # Validate folio_id (required)
    if not folio_id:
        raise AddressError("folio_id is required for address construction")

    _validate_folio_id(folio_id)

    # Normalize empty string to None
    if project == "":
        project = None
    if user == "":
        user = None

    # Validate user requires project
    if user and not project:
        raise AddressError(
            "project is required when user is specified "
            "(cannot have Layer 3 without Layer 2)"
        )

    # Validate names if provided
    if project:
        _validate_name(project, "project")
    if user:
        _validate_name(user, "user")

    # Build address
    if user:
        return f"@{user}/{project}/{folio_id}"
    elif project:
        return f"{project}/{folio_id}"
    else:
        return folio_id


def validate(address: object) -> bool:
    """Check if an address string is valid.

    Unlike parse(), this returns False instead of raising for invalid input.

    Args:
        address: Value to check.

    Returns:
        True if address is a valid SKEIN address string, False otherwise.

    Examples:
        >>> validate("brief-20251226-n1br")
        True

        >>> validate("not valid!")
        False

        >>> validate(None)
        False
    """
    if not isinstance(address, str):
        return False

    try:
        parse(address)
        return True
    except AddressError:
        return False
