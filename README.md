# knurl

Rock-solid primitives for content-addressable hashing, chain fingerprinting, and config diffing.

Extracted from the SpiritEngine project.

## Modules

- **canon** - Canonical JSON serialization (RFC 8785 inspired)
- **hash** - Content-addressable hashing
- **chain** - Merkle-like chain fingerprinting
- **diverge** - Divergence detection for fingerprint chains
- **diff** - JSON Patch (RFC 6902) diffs
- **yield_** - Yield data serialization

## Installation

```bash
pip install knurl

# With diff support (requires jsonpatch)
pip install knurl[diff]
```

## Usage

```python
from knurl import canon, hash, chain, diverge

# Canonical serialization
canonical_bytes = canon.serialize({"b": 1, "a": 2})  # b'{"a":2,"b":1}'

# Content-addressable hashing
content_hash = hash.compute("hello world")  # 'sha256:...'

# Chain fingerprinting
fingerprints = chain.fingerprint([config1, config2, config3])

# Divergence detection
result = diverge.find(old_fingerprints, new_fingerprints)
```

## Requirements

- Python 3.10+
- No dependencies (stdlib only)
- Optional: `jsonpatch` for diff module
