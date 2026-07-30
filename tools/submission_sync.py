"""Read-only drift check between development-candidate and root-submission
copies of main.py, deck.csv, and params.json.

Step 8A scope (read-only check-only v1): this tool only reports. It never
writes, never decides which side is canonical or correct, and never invokes
the submission build script, cg, or main.py. See the Step 7 design-only
trial record for the integrated design this implements.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

LOGICAL_NAMES: tuple[str, ...] = ("main.py", "deck.csv", "params.json")

# Fixed comparison mapping (development candidate <-> root submission).
# Neither side is treated as canonical or correct here -- this tool reports
# drift only, it does not decide or sync anything.
FIXED_MAPPING: dict[str, tuple[str, str]] = {
    "main.py": ("experiments/agents/raging_bolt/main.py", "main.py"),
    "deck.csv": ("experiments/decks/raging_bolt_ogerpon.csv", "deck.csv"),
    "params.json": ("experiments/agents/raging_bolt/params.json", "params.json"),
}

EXIT_SUCCESS = 0
EXIT_DRIFT = 1
EXIT_MISSING = 3
EXIT_MALFORMED = 4
EXIT_CONTAINMENT = 8


class Classification(Enum):
    BYTE_IDENTICAL = "BYTE_IDENTICAL"
    SEMANTICALLY_EQUIVALENT = "SEMANTICALLY_EQUIVALENT"
    DIFFERENT = "DIFFERENT"


@dataclass
class PairReport:
    logical_name: str
    dev_rel_path: str
    root_rel_path: str
    dev_status: str
    root_status: str
    dev_reason: Optional[str] = None
    root_reason: Optional[str] = None
    dev_sha256: Optional[str] = None
    root_sha256: Optional[str] = None
    classification: Optional[Classification] = None
    dev_malformed_reason: Optional[str] = None
    root_malformed_reason: Optional[str] = None


# ── Path safety ────────────────────────────────────────────────────────────

def _is_within(path: str, root: str) -> bool:
    p = os.path.normcase(os.path.normpath(path))
    r = os.path.normcase(os.path.normpath(root))
    if p == r:
        return True
    try:
        common = os.path.commonpath([p, r])
    except ValueError:
        return False
    return common == r


def resolve_and_check(repo_root: Path, rel_path: str) -> tuple[Optional[Path], str]:
    """Resolve rel_path under repo_root and confirm it cannot escape via a
    symlink/junction/reparse point. Returns (path, "OK") or
    (None, "CONTAINMENT_ERROR"). Does not check existence -- a missing file
    that still resolves inside repo_root is not a containment error."""
    root_abs = os.path.abspath(str(repo_root))
    root_real = os.path.realpath(root_abs)

    candidate_abs = os.path.abspath(os.path.join(root_abs, rel_path))
    if not _is_within(candidate_abs, root_abs):
        return None, "CONTAINMENT_ERROR"

    candidate_real = os.path.realpath(candidate_abs)
    if not _is_within(candidate_real, root_real):
        return None, "CONTAINMENT_ERROR"

    return Path(candidate_abs), "OK"


def _read_side(repo_root: Path, rel_path: str) -> tuple[str, Optional[bytes], Optional[str]]:
    """Read-only fetch of one side of a pair. Returns
    (status, raw_bytes_or_None, reason_or_None). Never writes.

    Known residual limitation: there is a check-then-open gap between
    resolve_and_check()'s containment verdict and the read below. A
    symlink/junction swapped in that exact window could still escape
    containment. This is a diagnostic CLI over a locally-owned repo, not a
    multi-tenant boundary, so this is accepted rather than solved with
    lower-level fd-based open+fstat sequencing."""
    resolved, status = resolve_and_check(repo_root, rel_path)
    if status == "CONTAINMENT_ERROR":
        return (
            "CONTAINMENT_ERROR",
            None,
            "resolved path escapes repository root (or crosses an unexpected "
            "symlink/junction/reparse point)",
        )
    assert resolved is not None
    try:
        exists = resolved.exists()
    except OSError as exc:
        return "IO_ERROR", None, _sanitize_os_error(exc)
    if not exists:
        return "MISSING", None, None
    try:
        is_file = resolved.is_file()
    except OSError as exc:
        return "IO_ERROR", None, _sanitize_os_error(exc)
    if not is_file:
        return "IO_ERROR", None, "path exists but is not a regular file"
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        return "IO_ERROR", None, _sanitize_os_error(exc)
    return "OK", raw, None


def _sanitize_os_error(exc: OSError) -> str:
    """Describe an OSError without echoing the absolute filesystem path it
    may embed (str(exc) on most platforms includes the full path)."""
    if exc.strerror:
        return f"{type(exc).__name__}: {exc.strerror}"
    return type(exc).__name__


# ── Byte-level classification ───────────────────────────────────────────────

def _normalize_for_semantic_compare(data: bytes) -> bytes:
    """CRLF/lone-CR -> LF, and ignore only whether exactly one trailing LF is
    present (strip at most one trailing LF). Does NOT collapse multiple
    trailing blank lines -- those remain a real difference."""
    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if normalized.endswith(b"\n"):
        normalized = normalized[:-1]
    return normalized


def classify_bytes(dev_raw: bytes, root_raw: bytes) -> Classification:
    if dev_raw == root_raw:
        return Classification.BYTE_IDENTICAL
    if _normalize_for_semantic_compare(dev_raw) == _normalize_for_semantic_compare(root_raw):
        return Classification.SEMANTICALLY_EQUIVALENT
    return Classification.DIFFERENT


# ── Lightweight structural validation (not a rules/game validator) ─────────

def _validate_main_py(text: str) -> Optional[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return f"ast.parse failed: {exc}"
    has_agent = any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "agent"
        for node in tree.body
    )
    if not has_agent:
        return "no top-level function named 'agent'"
    return None


def _validate_params_json(text: str) -> Optional[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return f"json.loads failed: {exc}"
    if not isinstance(data, dict):
        return "top-level JSON value is not an object"
    return None


_POSITIVE_INT_RE = re.compile(r"^[0-9]+$")


def _validate_deck_csv(text: str) -> Optional[str]:
    try:
        rows = list(csv.reader(text.splitlines()))
    except csv.Error as exc:
        return f"csv parsing failed: {exc}"
    non_empty = 0
    for line_no, row in enumerate(rows, start=1):
        if len(row) == 0:
            return f"empty line at row {line_no} (blank lines are not allowed)"
        if len(row) != 1:
            return f"row {line_no} has {len(row)} columns, expected exactly 1"
        value = row[0]
        if not _POSITIVE_INT_RE.match(value) or int(value) <= 0:
            return f"row {line_no} is not a positive decimal integer: {value!r}"
        non_empty += 1
    if non_empty != 60:
        return f"expected exactly 60 non-empty rows, found {non_empty}"
    return None


def validate_structure(logical_name: str, raw: bytes) -> Optional[str]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return f"utf-8 decode failed: {exc}"
    if logical_name == "main.py":
        return _validate_main_py(text)
    if logical_name == "params.json":
        return _validate_params_json(text)
    if logical_name == "deck.csv":
        return _validate_deck_csv(text)
    return None


# ── Pair check ───────────────────────────────────────────────────────────────

def check_pair(repo_root: Path, logical_name: str) -> PairReport:
    dev_rel, root_rel = FIXED_MAPPING[logical_name]
    dev_status, dev_raw, dev_reason = _read_side(repo_root, dev_rel)
    root_status, root_raw, root_reason = _read_side(repo_root, root_rel)

    report = PairReport(
        logical_name=logical_name,
        dev_rel_path=dev_rel,
        root_rel_path=root_rel,
        dev_status=dev_status,
        root_status=root_status,
        dev_reason=dev_reason,
        root_reason=root_reason,
    )

    if dev_status == "OK" and dev_raw is not None:
        report.dev_sha256 = hashlib.sha256(dev_raw).hexdigest()
        report.dev_malformed_reason = validate_structure(logical_name, dev_raw)
    if root_status == "OK" and root_raw is not None:
        report.root_sha256 = hashlib.sha256(root_raw).hexdigest()
        report.root_malformed_reason = validate_structure(logical_name, root_raw)

    if dev_status == "OK" and root_status == "OK" and dev_raw is not None and root_raw is not None:
        report.classification = classify_bytes(dev_raw, root_raw)

    return report


def file_exit_category(report: PairReport, strict: bool) -> int:
    """Priority within one file: 8 > 4 > 3 > 1 > 0."""
    if report.dev_status in ("CONTAINMENT_ERROR", "IO_ERROR") or report.root_status in (
        "CONTAINMENT_ERROR",
        "IO_ERROR",
    ):
        return EXIT_CONTAINMENT
    if report.dev_malformed_reason or report.root_malformed_reason:
        return EXIT_MALFORMED
    if report.dev_status == "MISSING" or report.root_status == "MISSING":
        return EXIT_MISSING
    if report.classification == Classification.DIFFERENT:
        return EXIT_DRIFT
    if strict and report.classification == Classification.SEMANTICALLY_EQUIVALENT:
        return EXIT_DRIFT
    return EXIT_SUCCESS


# ── Selection / CLI plumbing ────────────────────────────────────────────────

def selected_names(file_args: Optional[list[str]]) -> list[str]:
    if not file_args:
        return list(LOGICAL_NAMES)
    seen: list[str] = []
    for name in file_args:
        if name not in seen:
            seen.append(name)
    return seen


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="submission_sync.py",
        description=(
            "Read-only drift check between development-candidate and "
            "root-submission files. Reports only; decides nothing."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser(
        "check",
        help="Compare development candidate vs root submission for main.py/deck.csv/params.json",
    )
    check.add_argument(
        "--strict",
        action="store_true",
        help="Treat SEMANTICALLY_EQUIVALENT as drift (exit 1)",
    )
    check.add_argument(
        "--file",
        action="append",
        choices=list(LOGICAL_NAMES),
        dest="file",
        help="Limit the check to one logical name; may be given multiple times. Default: all three.",
    )
    return parser


# ── Output ───────────────────────────────────────────────────────────────────

def _classification_label(report: PairReport, strict: bool) -> str:
    if report.classification is None:
        return "UNAVAILABLE"
    label = report.classification.value
    if report.classification == Classification.SEMANTICALLY_EQUIVALENT:
        label += " (DRIFT under --strict)" if strict else " (WARN)"
    elif report.classification == Classification.DIFFERENT:
        label += " (DRIFT)"
    return label


def _print_report(report: PairReport, strict: bool) -> None:
    print(f"{report.logical_name}: {_classification_label(report, strict)}")
    print(f"development: {report.dev_rel_path}")
    print(f"submission: {report.root_rel_path}")
    if report.dev_sha256:
        print(f"development_sha256: {report.dev_sha256}")
    if report.root_sha256:
        print(f"submission_sha256: {report.root_sha256}")

    reasons: list[str] = []
    if report.dev_status != "OK":
        detail = f": {report.dev_reason}" if report.dev_reason else ""
        reasons.append(f"development {report.dev_status}{detail}")
    if report.root_status != "OK":
        detail = f": {report.root_reason}" if report.root_reason else ""
        reasons.append(f"submission {report.root_status}{detail}")
    if report.dev_malformed_reason:
        reasons.append(f"development MALFORMED: {report.dev_malformed_reason}")
    if report.root_malformed_reason:
        reasons.append(f"submission MALFORMED: {report.root_malformed_reason}")

    if report.dev_malformed_reason or report.root_malformed_reason:
        print("validation: MALFORMED")
    elif report.dev_status == "OK" and report.root_status == "OK":
        print("validation: OK")
    else:
        print("validation: UNAVAILABLE")

    for reason in reasons:
        print(f"  reason: {reason}")
    print()


def _print_summary(reports: list[PairReport], categories: list[int]) -> None:
    checked = len(reports)
    byte_identical = sum(1 for r in reports if r.classification == Classification.BYTE_IDENTICAL)
    semantically_equivalent = sum(
        1 for r in reports if r.classification == Classification.SEMANTICALLY_EQUIVALENT
    )
    different = sum(1 for r in reports if r.classification == Classification.DIFFERENT)
    errors = sum(1 for c in categories if c in (EXIT_MISSING, EXIT_MALFORMED, EXIT_CONTAINMENT))
    overall_code = max(categories, default=EXIT_SUCCESS)
    overall_result = "SUCCESS" if overall_code == EXIT_SUCCESS else f"FAILURE (exit {overall_code})"

    print("summary:")
    print(f"  checked: {checked}")
    print(f"  byte_identical: {byte_identical}")
    print(f"  semantically_equivalent: {semantically_equivalent}")
    print(f"  different: {different}")
    print(f"  errors: {errors}")
    print(f"  overall: {overall_result}")


# ── Entry point ──────────────────────────────────────────────────────────────

def main(argv: Optional[list[str]] = None, repo_root: Optional[Path] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    root = Path(repo_root) if repo_root is not None else REPO_ROOT

    names = selected_names(args.file)
    reports = [check_pair(root, name) for name in names]
    categories = [file_exit_category(report, args.strict) for report in reports]

    for report in reports:
        _print_report(report, args.strict)
    _print_summary(reports, categories)

    return max(categories, default=EXIT_SUCCESS)


if __name__ == "__main__":
    sys.exit(main())
