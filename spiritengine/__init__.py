# SPIRITENGINE - Content-Addressable Primitives
#
# Provides rock-solid primitives for:
# - spiritengine.canon: Canonical serialization
# - spiritengine.hash: Content-addressable hashing
# - spiritengine.yield_: Yield serialization
# - spiritengine.diff: Diff computation & application
# - spiritengine.chain: Chain fingerprinting
# - spiritengine.diverge: Divergence detection

from .canon import serialize, CanonError
from .hash import compute, verify, HashError
from .chain import fingerprint, fingerprint_step, ChainError
from . import yield_
from . import diff
from . import chain
from . import diverge
from .diff import DiffError, PatchConflictError, InvalidPatchError, PathNotFoundError
from .diverge import DivergenceResult
