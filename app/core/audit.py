"""Deterministic SHA-256 audit hash-chain helpers."""

import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from typing import Any


def _canonical_event(event: Mapping[str, Any]) -> bytes:
    payload = {key: value for key, value in event.items() if key not in {"prev_hash", "hash"}}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode(
        "utf-8"
    )


def create_audit_event(event: Mapping[str, Any], prev_hash: str = "") -> dict[str, Any]:
    """Add previous and current hashes to an audit event."""
    payload = {key: value for key, value in event.items() if key not in {"prev_hash", "hash"}}
    digest = hashlib.sha256(prev_hash.encode("ascii") + _canonical_event(payload)).hexdigest()
    return {**payload, "prev_hash": prev_hash, "hash": digest}


def verify_chain(events: Sequence[Mapping[str, Any]]) -> bool:
    """Verify event hashes and previous-hash links from the genesis event onward."""
    expected_previous = ""
    for event in events:
        previous = event.get("prev_hash", "")
        actual_hash = event.get("hash")
        if not isinstance(previous, str) or not isinstance(actual_hash, str):
            return False
        if not hmac.compare_digest(previous, expected_previous):
            return False
        expected_hash = create_audit_event(event, previous)["hash"]
        if not hmac.compare_digest(actual_hash, expected_hash):
            return False
        expected_previous = actual_hash
    return True
