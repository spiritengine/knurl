# knurl

Rock-solid primitives for content-addressable hashing, chain fingerprinting, and config diffing.

Know when configs have changed and which downstream steps need to re-run. The same data always produces the same hash, making it easy to cache results, skip unnecessary work, and avoid storing duplicates.

Extracted from the SpiritEngine project.

## Why knurl?

Use knurl when you need:
- **Execution plan caching** - Skip re-running steps when config hasn't changed
- **Content-addressable storage** - Store and retrieve data by its hash
- **Config change detection** - Know exactly which configs changed and what downstream steps need re-execution
- **Deterministic hashing** - Same data always produces same hash, even across systems
- **Chain invalidation** - Automatically invalidate downstream steps when an upstream config changes

## Who uses knurl?

- **Workflow orchestration developers** - Building tools like Airflow/Prefect/Dagster alternatives
- **Build system creators** - Making cache-aware build tools (Bazel, Buck, Make-like systems)
- **AI agent platform developers** - Coordinating multi-agent systems with execution caching
- **Data pipeline tool builders** - Needing smart caching for expensive transformations

## Installation

```bash
pip install knurl

# With diff support (requires jsonpatch)
pip install knurl[diff]
```

## Quick Start

```python
from knurl import canon, hash, chain, diverge

# Canonical serialization (same dict always produces same bytes)
canonical_bytes = canon.serialize({"b": 1, "a": 2})  # b'{"a":2,"b":1}'

# Content-addressable hashing
content_hash = hash.compute("hello world")  # 'sha256:b94d27b9...'

# Chain fingerprinting (each step depends on previous)
configs = [
    {"task": "build", "image": "python:3.10"},
    {"task": "test", "coverage": True},
    {"task": "deploy", "env": "prod"}
]
fingerprints = chain.fingerprint(configs)
# ['sha256:aaa...', 'sha256:bbb...', 'sha256:ccc...']

# Divergence detection (find where chains differ)
result = diverge.find(old_fingerprints, new_fingerprints)
# DivergenceResult(diverged=True, index=1, old='sha256:bbb...', new='sha256:xxx...')
```

## Modules

- **canon** - Canonical JSON serialization (RFC 8785 inspired)
- **hash** - Content-addressable hashing with optional namespaces
- **chain** - Merkle-like chain fingerprinting for execution plans
- **diverge** - Divergence detection for fingerprint chains
- **diff** - JSON Patch (RFC 6902) for config diffs
- **yield_** - Yield data serialization
- **address** - SKEIN address parsing and validation

## Common Workflows

### Execution Plan Caching
- Fingerprint each step's config using `chain.fingerprint()`
- Cache results keyed by fingerprint
- On re-run, check if fingerprint exists in cache
- If found, skip execution and use cached result
- If not found or changed, execute step and cache new result

### Detecting Config Changes
- Store previous fingerprints for a chain of configs
- On update, compute new fingerprints with `chain.fingerprint()`
- Use `diverge.find()` to locate first changed config
- All steps from divergence point onward need re-execution

### Content-Addressable Storage
- Hash content with `hash.compute(content)`
- Store content using hash as key/filename
- Retrieve by hash (guaranteed content match)
- Automatic deduplication (same content = same hash)
- Optional namespace prefixes for organization

### Config Diffing
- Serialize configs to canonical form with `canon.serialize()`
- Compute diff between configs using `diff.compute()`
- Apply patches with `diff.apply()`
- Track config evolution over time

## Detailed Usage

### Canonical Serialization

Produces deterministic JSON bytes where identical data structures always produce identical output:

```python
from knurl import canon

# Dicts are sorted by key
config = {"database": "postgres", "cache": "redis", "api_version": 2}
canonical = canon.serialize(config)
# b'{"api_version":2,"cache":"redis","database":"postgres"}'

# Same config, different key order -> same output
config2 = {"cache": "redis", "api_version": 2, "database": "postgres"}
assert canon.serialize(config2) == canonical

# Use for hashing configs
import hashlib
config_hash = hashlib.sha256(canonical).hexdigest()
```

### Content-Addressable Hashing

Hash strings with optional namespace prefixes:

```python
from knurl import hash

# Basic hashing
content_hash = hash.compute("hello world")
# 'sha256:b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9'

# With namespace prefix for organization
config_hash = hash.compute('{"env": "prod"}', prefix="config")
# 'config:sha256:...'

schedule_hash = hash.compute('{"cron": "0 * * * *"}', prefix="schedule")
# 'schedule:sha256:...'

# Verify content matches hash
is_valid = hash.verify("hello world", content_hash)  # True
is_valid = hash.verify("hello", content_hash)  # False
```

### Chain Fingerprinting

Create fingerprint chains where each step depends on the previous:

```python
from knurl import chain

# Define execution steps
steps = [
    {"task": "fetch_data", "source": "s3://bucket/data.csv"},
    {"task": "transform", "method": "normalize"},
    {"task": "train_model", "algorithm": "xgboost"},
    {"task": "evaluate", "metric": "accuracy"}
]

# Compute fingerprints (each depends on previous)
fingerprints = chain.fingerprint(steps)
# [
#   'sha256:aaa...',  # depends on: config[0]
#   'sha256:bbb...',  # depends on: config[1] + fingerprint[0]
#   'sha256:ccc...',  # depends on: config[2] + fingerprint[1]
#   'sha256:ddd...'   # depends on: config[3] + fingerprint[2]
# ]

# Incremental fingerprinting
fp1 = chain.fingerprint_step(steps[0], previous_fingerprint=None)
fp2 = chain.fingerprint_step(steps[1], previous_fingerprint=fp1)
# fp2 == fingerprints[1]
```

**Key property:** Changing step N invalidates fingerprints for steps N, N+1, N+2, ... (cascade invalidation)

### Divergence Detection

Find where two fingerprint chains diverge:

```python
from knurl import diverge

old_fingerprints = ['sha256:aaa...', 'sha256:bbb...', 'sha256:ccc...']
new_fingerprints = ['sha256:aaa...', 'sha256:xxx...', 'sha256:yyy...']

result = diverge.find(old_fingerprints, new_fingerprints)
# DivergenceResult(
#     diverged=True,
#     index=1,  # First difference at index 1
#     old='sha256:bbb...',
#     new='sha256:xxx...'
# )

# No divergence
result = diverge.find(old_fingerprints, old_fingerprints)
# DivergenceResult(diverged=False, index=None, old=None, new=None)
```

### Config Diffing

Compute and apply JSON patches:

```python
from knurl import diff

old_config = {"workers": 2, "timeout": 30, "cache": "redis"}
new_config = {"workers": 4, "timeout": 30, "cache": "memcached", "debug": True}

# Compute diff (RFC 6902 JSON Patch)
patch = diff.compute(old_config, new_config)
# [
#   {"op": "replace", "path": "/workers", "value": 4},
#   {"op": "replace", "path": "/cache", "value": "memcached"},
#   {"op": "add", "path": "/debug", "value": True}
# ]

# Apply patch
result = diff.apply(old_config, patch)
assert result == new_config
```

## Requirements

- Python 3.10+
- No dependencies (stdlib only)
- Optional: `jsonpatch` for diff module

## License

MIT
