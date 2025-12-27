# SPIRITENGINE - Content-Addressable Primitives
#
# Provides rock-solid primitives for:
# - knurl.canon: Canonical serialization
# - knurl.hash: Content-addressable hashing
# - knurl.yield_: Yield serialization
# - knurl.diff: Diff computation & application
# - knurl.chain: Chain fingerprinting
# - knurl.diverge: Divergence detection

from .canon import serialize, CanonError
from .hash import compute, verify, HashError
from .chain import fingerprint, fingerprint_step, ChainError
from . import yield_
from . import diff
from . import chain
from . import diverge
from .diff import DiffError, PatchConflictError, InvalidPatchError, PathNotFoundError
from .diverge import DivergenceResult
