"""
Yield serialization for step outputs.

Serialize and deserialize step yields (outputs) for storage and resumption.
Yields are passed between chain steps and must survive storage/retrieval
with perfect fidelity.

Note: Module is named yield_.py since 'yield' is a Python reserved word.

Standard yield structure:
    {
        'task_id': str,           # Required: which task produced this
        'result': str,            # Required: 'success' | 'failed' | 'skipped'
        'output': Any,            # Optional: task output (string, dict, etc.)
        'error': str | None,      # Optional: error message if failed
        'shard_name': str | None, # Optional: shard if task ran in shard
        'files': list[str],       # Optional: files created/modified
        'metadata': dict,         # Optional: arbitrary metadata
    }
"""

from __future__ import annotations

import json
from typing import Any

from . import canon


REQUIRED_FIELDS = {'task_id', 'result'}
VALID_RESULTS = {'success', 'failed', 'skipped'}


def serialize(yield_data: dict) -> str:
    """Serialize yield data to canonical JSON string.

    Uses ledger.canon for deterministic serialization where the same
    input always produces the exact same output.

    Args:
        yield_data: Yield dict to serialize

    Returns:
        Canonical JSON string representation

    Raises:
        CanonError: If yield_data contains NaN, Infinity, or circular references
        TypeError: If yield_data contains non-JSON-serializable types

    Example:
        >>> yield_data = {'task_id': 'task_001', 'result': 'success'}
        >>> serialize(yield_data)
        '{"result":"success","task_id":"task_001"}'
    """
    # canon.serialize returns bytes, we decode to string for storage
    return canon.serialize(yield_data).decode('utf-8')


def deserialize(serialized: str) -> dict:
    """Deserialize a JSON string to yield data.

    Args:
        serialized: JSON string to parse

    Returns:
        Parsed yield dict

    Raises:
        json.JSONDecodeError: If input is not valid JSON

    Example:
        >>> deserialize('{"result":"success","task_id":"task_001"}')
        {'result': 'success', 'task_id': 'task_001'}
    """
    return json.loads(serialized)


def validate(yield_data: dict) -> list[str]:
    """Validate yield data structure.

    Checks for:
    - Required fields (task_id, result)
    - Valid result values (success, failed, skipped)

    Does NOT enforce strict typing on optional fields to allow
    flexibility in what tasks can return.

    Args:
        yield_data: Yield dict to validate

    Returns:
        List of error messages (empty if valid)

    Example:
        >>> validate({'task_id': 'test', 'result': 'success'})
        []
        >>> validate({'result': 'success'})
        ['Missing required field: task_id']
        >>> validate({'task_id': 'test', 'result': 'maybe'})
        ["Invalid result 'maybe': must be one of success, failed, skipped"]
    """
    errors = []

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in yield_data:
            errors.append(f'Missing required field: {field}')

    # Check result value if present
    if 'result' in yield_data:
        result = yield_data['result']
        if result not in VALID_RESULTS:
            valid_options = ', '.join(sorted(VALID_RESULTS))
            errors.append(f"Invalid result '{result}': must be one of {valid_options}")

    return errors


def get_task_id(yield_data: dict) -> str | None:
    """Extract task_id from yield data.

    Args:
        yield_data: Yield dict

    Returns:
        task_id value, or None if not present

    Example:
        >>> get_task_id({'task_id': 'beadle_001', 'result': 'success'})
        'beadle_001'
        >>> get_task_id({'result': 'success'})
        None
    """
    return yield_data.get('task_id')


def get_shard_name(yield_data: dict) -> str | None:
    """Extract shard_name from yield data.

    Args:
        yield_data: Yield dict

    Returns:
        shard_name value, or None if not present or explicitly None

    Example:
        >>> get_shard_name({'task_id': 't1', 'result': 'success', 'shard_name': 'shard-abc'})
        'shard-abc'
        >>> get_shard_name({'task_id': 't1', 'result': 'success'})
        None
    """
    return yield_data.get('shard_name')
