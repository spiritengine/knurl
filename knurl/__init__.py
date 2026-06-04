# KNURL - Content-Addressable Primitives
#
# Provides rock-solid primitives for:
# - knurl.canon: Canonical serialization
# - knurl.hash: Content-addressable hashing
# - knurl.address: SKEIN address parsing
# - knurl.yield_: Yield serialization
# - knurl.diff: Diff computation & application
# - knurl.chain: Chain fingerprinting
# - knurl.diverge: Divergence detection

from .canon import (
    serialize,
    CanonError,
    MAX_DEPTH,
    MAX_INT_DIGITS,
    UNICODE_VERSION,
)
from .hash import (
    compute,
    compute_bytes,
    compute_file,
    compute_tree,
    compute_tree_manifest,
    verify,
    HashError,
    TreeManifest,
)
from .address import parse, construct, validate, ParsedAddress, AddressError
from .chain import fingerprint, fingerprint_step, ChainError
from . import yield_
from . import diff
from . import chain
from . import diverge
from . import address
from .diff import DiffError, PatchConflictError, InvalidPatchError, PathNotFoundError
from .diverge import DivergenceResult
