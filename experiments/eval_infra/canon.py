"""Canonicalization and hashing helpers for eval-infra artifacts.

Mirrors (does NOT import) tools/outcome_gatekeeper.py's
canonical_profile_bytes() recipe, so that hashes produced here are byte-
compatible with the Gatekeeper's convention without coupling this generic
harness to Gatekeeper/App-Profile internals at runtime. experiments/
test_eval_infra.py contains a test-only, read-only import of the real
tools.outcome_gatekeeper.canonical_profile_bytes for a byte-for-byte drift
guard -- production code in this package never imports it.

canonicalize() does NOT call any Profile-schema validation (unlike
canonical_profile_bytes(), which validates a Profile first) -- it is a bare
canonical-JSON-bytes function usable on any JSON-serializable dict, since the
payloads canonicalized here (dataset/protocol/comparison identity, per-game
records) are not App Profile documents.
"""
from __future__ import annotations

import hashlib
import json
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

DECIMAL_PLACES_DEFAULT = 6


def canonicalize(value: Any) -> bytes:
    """Canonical JSON bytes: sort_keys, no ASCII-escaping, compact separators,
    NaN/Infinity rejected. Identical parameters to
    tools.outcome_gatekeeper.canonical_profile_bytes()'s json.dumps() call.
    """
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    """Lowercase 64-hex SHA-256 digest of canonicalize(value)."""
    return hashlib.sha256(canonicalize(value)).hexdigest()


def format_decimal(value: Any, places: int = DECIMAL_PLACES_DEFAULT) -> str:
    """Format a number as a canonical Decimal string matching
    tools.outcome_gatekeeper.DECIMAL_RE (^-?(?:0|[1-9][0-9]*)(?:\\.[0-9]*[1-9])?$)
    and its explicit rejection of the literal string "-0": no leading zeros,
    no trailing zeros after the decimal point, no bare "-0", no trailing ".".
    """
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    quantum = Decimal(1).scaleb(-places)
    d = d.quantize(quantum, rounding=ROUND_HALF_EVEN)
    if d == 0:
        d = Decimal(0)  # normalizes -0 -> 0 before formatting
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("", "-0", "-"):
        text = "0"
    return text
