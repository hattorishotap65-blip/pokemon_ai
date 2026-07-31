"""Read-only verifier for the multi-agent-workflow template package.

Two subcommands:
  source-integrity   Check the package's own files against manifest.json.
  plan               Compare (in memory only) rendered package files against
                      an external target-root, using manifest.json as the
                      single source of truth for how each file should be
                      treated (adoption_mode).

This tool never writes, copies, merges, installs, updates, uninstalls,
backs up, renames, or deletes anything. It never imports the subprocess
module and never runs a shell command or a Git command. It only reads
files (package side and, for `plan`, an external target-root) and prints
a report to stdout.

Package root is resolved from this file's own location
(``Path(__file__).resolve().parents[1]``), not from the current working
directory, so the tool behaves the same regardless of where it is invoked
from.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------
# Resource limits (overage is reported as INVALID, never silently ignored)
# --------------------------------------------------------------------------

MAX_MANIFEST_BYTES = 1 * 1024 * 1024       # 1 MiB
MAX_MANIFEST_FILES = 500
MAX_FILE_BYTES = 5 * 1024 * 1024           # 5 MiB per file
MAX_TOTAL_READ_BYTES = 50 * 1024 * 1024    # 50 MiB per run (manifest.json's own
                                            # bytes are seeded into this budget once,
                                            # never double-counted)
MAX_PATH_DEPTH = 64
MAX_PLACEHOLDERS = 100

# --------------------------------------------------------------------------
# Manifest vocabulary
# --------------------------------------------------------------------------

ALLOWED_CLASSIFICATIONS = {
    "CONFIG", "AGENT", "SKILL", "WORKFLOW_DOC", "DECISION_TEMPLATE",
    "RULE_SNIPPET", "PACKAGE_METADATA", "PACKAGE_TOOL",
}
ALLOWED_CONTENT_MODES = {"VERBATIM", "GENERIFIED", "NEW", "SKELETON"}
ALLOWED_ADOPTION_MODES = {
    "PACKAGE_METADATA", "COPY_IF_ABSENT", "MANUAL_REVIEW",
    "REFERENCE_ONLY", "TEMPLATE_RENAME",
}
NO_TARGET_ADOPTION_MODES = {"PACKAGE_METADATA", "REFERENCE_ONLY"}

STATE_MISSING = "MISSING"
STATE_IDENTICAL = "IDENTICAL"
STATE_DIFFERENT = "DIFFERENT"
STATE_INVALID = "INVALID"
STATE_UNRESOLVED = "UNRESOLVED_PLACEHOLDER"
STATE_SKIPPED = "SKIPPED"  # display-only; not one of the 5 comparison states
# display-only, not one of the 5 comparison states: a blocking containment/
# symlink/junction/reparse/I/O safety-boundary finding. Kept distinct from
# STATE_INVALID (a non-blocking content/type/metadata problem) so a
# displayed [INVALID] line always corresponds 1:1 with the summary's
# `invalid` count, and a displayed [BLOCKING_ERROR] line always corresponds
# 1:1 with the summary's `blocking_errors` count -- the same finding is
# never counted in both.
STATE_BLOCKING_ERROR = "BLOCKING_ERROR"

# --------------------------------------------------------------------------
# Exit codes
# --------------------------------------------------------------------------

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_USAGE = 2
EXIT_MISSING_PREREQ = 3
EXIT_INVALID = 4
EXIT_IO_CONTAINMENT = 8

TARGET_ROOT_DISPLAY = "<target-root>"

TOKEN_RE = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")
PLACEHOLDER_DECL_RE = re.compile(r"^\{\{([A-Z][A-Z0-9_]*)\}\}$")
SET_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Unicode general categories rejected in any --set VALUE: Cc = control,
# Zl = line separator (U+2028), Zp = paragraph separator (U+2029). This
# covers NUL, all C0/C1 control characters, CR, LF, tab, vertical tab,
# and form feed without needing to enumerate each one individually.
_DISALLOWED_VALUE_CATEGORIES = ("Cc", "Zl", "Zp")


class BlockingError(Exception):
    """Base for errors that stop the whole run with a specific reason code."""


class UsageError(BlockingError):
    pass


class PrerequisiteMissingError(BlockingError):
    pass


class ManifestInvalidError(BlockingError):
    pass


class ContainmentError(BlockingError):
    pass


@dataclass
class FileEntry:
    path: str
    classification: str
    content_mode: str
    sha256: Optional[str]
    required: bool
    notes: str
    target_path: Optional[str]
    adoption_mode: str


@dataclass
class ManifestData:
    files: list
    placeholders: list
    path_placeholder_names: set


# --------------------------------------------------------------------------
# Path safety helpers
# --------------------------------------------------------------------------

def _split_components(path_str: str):
    return path_str.replace("\\", "/").split("/")


def _is_unsafe_relative_path(path_str: str) -> Optional[str]:
    """Lexical safety check for a manifest ``path``/``target_path`` string
    (which may still contain ``{{...}}``-style placeholders). Returns a reason
    string if unsafe, else None."""
    if not isinstance(path_str, str) or path_str == "":
        return "EMPTY_PATH"
    if "\x00" in path_str:
        return "NUL_BYTE"
    if path_str.startswith("\\\\") or path_str.startswith("//"):
        return "UNC_PATH"
    if path_str.startswith("/") or path_str.startswith("\\"):
        return "ABSOLUTE_PATH"
    if ":" in path_str:
        return "DRIVE_PATH"
    # Manifest paths/target_paths are a canonical, platform-independent
    # inventory format: forward slash only. A backslash is rejected
    # outright rather than silently treated as a separator, since the
    # on-disk unlisted-file scan always produces "/"-joined relative
    # paths and a backslash-vs-slash mismatch there could let a declared
    # path silently fail to match its own scanned entry.
    if "\\" in path_str:
        return "BACKSLASH_IN_PATH"
    parts = _split_components(path_str)
    if len(parts) > MAX_PATH_DEPTH:
        return "PATH_TOO_DEEP"
    for part in parts:
        if part == "":
            return "EMPTY_COMPONENT"
        if part == ".":
            return "DOT_COMPONENT"
        if part == "..":
            return "PARENT_TRAVERSAL"
    return None


def _contains_disallowed_control_or_separator(value: str) -> bool:
    return any(unicodedata.category(ch) in _DISALLOWED_VALUE_CATEGORIES for ch in value)


def _is_unsafe_set_value(value: str) -> Optional[str]:
    """General safety check applied to every --set VALUE, regardless of
    whether it is later used inside a target_path."""
    if value == "":
        return "EMPTY_SET_VALUE"
    if "{{" in value or "}}" in value:
        return "UNSAFE_SET_VALUE"
    if _contains_disallowed_control_or_separator(value):
        return "CONTROL_CHARACTER_IN_SET_VALUE"
    return None


def _is_unsafe_path_placeholder_value(value: str) -> Optional[str]:
    """Additional safety check for a --set VALUE that will be substituted
    into a target_path (i.e. must behave as a single, safe path element).
    Callers should also apply _is_unsafe_set_value first."""
    if value == "":
        return "EMPTY_VALUE"
    if _contains_disallowed_control_or_separator(value):
        return "CONTROL_CHARACTER_IN_VALUE"
    if "/" in value or "\\" in value:
        return "PATH_SEPARATOR_IN_VALUE"
    if ":" in value:
        return "COLON_IN_VALUE"
    if value == ".":
        return "DOT_VALUE"
    if value == "..":
        return "DOTDOT_VALUE"
    return None


def _path_is_reparse_or_symlink(path_str: str) -> bool:
    """True if path_str is (or cannot be safely proven not to be) a
    symlink, junction, or other reparse point. Errors are treated as
    unsafe (fail closed)."""
    try:
        if os.path.islink(path_str):
            return True
    except OSError:
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None:
        try:
            if isjunction(path_str):
                return True
        except OSError:
            return True
    if os.name == "nt":
        try:
            st = os.lstat(path_str)
        except FileNotFoundError:
            return False
        except OSError:
            return True
        attrs = getattr(st, "st_file_attributes", None)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if attrs is not None and (attrs & reparse_flag):
            return True
    return False


def _resolve_and_check_containment(root: Path, rel_path_str: str):
    """Resolve rel_path_str under root, rejecting any symlink/junction/
    reparse-point redirect (internal or external) at ANY path component
    (not just the final one), any lexical/real-path escape from root, and
    any case-only collision at ANY existing path component (not just the
    final one) on case-insensitive filesystems.

    NOTE (TOCTOU): there is a theoretical window between this check and
    the subsequent read of the file's bytes. This tool is a read-only,
    local, single-user, point-in-time diagnostic (not a multi-tenant
    trust boundary), so full TOCTOU elimination via low-level fd-based
    open+fstat sequencing is treated as out of scope for this v1.

    Returns (resolved_path, reason_or_None).
    """
    parts = [p for p in _split_components(rel_path_str) if p != ""]
    current = root
    for part in parts:
        parent = current
        current = current / part
        try:
            exists_here = os.path.lexists(str(current))
        except OSError:
            return current, "CONTAINMENT_ERROR"
        if not exists_here:
            continue
        if _path_is_reparse_or_symlink(str(current)):
            return current, "CONTAINMENT_ERROR"
        try:
            actual_names = {e.name for e in os.scandir(str(parent))}
        except OSError:
            return current, "CONTAINMENT_ERROR"
        if part not in actual_names:
            if any(n.casefold() == part.casefold() for n in actual_names):
                return current, "CASE_COLLISION"
            # lexists() said it exists but scandir cannot find it under any
            # casing: an inconsistent/racy filesystem state. Fail closed.
            return current, "CONTAINMENT_ERROR"

    try:
        root_real = os.path.realpath(str(root))
    except OSError:
        return current, "CONTAINMENT_ERROR"

    expected = os.path.normcase(os.path.normpath(os.path.join(root_real, *parts))) if parts \
        else os.path.normcase(os.path.normpath(root_real))

    try:
        lexical_full = os.path.join(str(root), *parts) if parts else str(root)
        actual_real = os.path.realpath(lexical_full)
    except OSError:
        return current, "CONTAINMENT_ERROR"
    actual = os.path.normcase(os.path.normpath(actual_real))

    if expected != actual:
        return current, "CONTAINMENT_ERROR"

    return current, None


def _find_tokens(text: str):
    return set(TOKEN_RE.findall(text))


def _substitute_tokens(text: str, values: dict) -> str:
    def repl(m):
        return values.get(m.group(1), m.group(0))
    return TOKEN_RE.sub(repl, text)


# --------------------------------------------------------------------------
# Manifest loading and validation (fail-fast: any structural problem with
# the manifest itself aborts the whole run with a single reason code,
# before any per-file comparison work begins)
# --------------------------------------------------------------------------

def load_manifest(package_root: Path):
    """Returns (ManifestData, manifest_size_bytes).

    manifest.json is a package file like any other and must pass the same
    containment check (reject symlink/junction/reparse points at any path
    component, any lexical/real-path escape from package_root, both
    external and internal redirects) BEFORE it is ever stat()'d or read.
    _resolve_and_check_containment() only depends on package_root and the
    literal relative path "manifest.json" -- it does not depend on any
    already-parsed manifest data -- so it can run here, ahead of manifest
    parsing, without duplicating the containment logic used for every
    other package file.
    """
    resolved_manifest, containment_reason = _resolve_and_check_containment(
        package_root, "manifest.json")
    if containment_reason:
        raise ContainmentError(containment_reason)

    try:
        st = os.lstat(str(resolved_manifest))
    except FileNotFoundError:
        raise PrerequisiteMissingError("MANIFEST_MISSING")
    except OSError:
        raise ContainmentError("MANIFEST_IO_ERROR")

    if stat.S_ISDIR(st.st_mode):
        raise ManifestInvalidError("MANIFEST_IS_DIRECTORY")
    if not stat.S_ISREG(st.st_mode):
        raise ManifestInvalidError("MANIFEST_SPECIAL_FILE")

    size = st.st_size
    if size > MAX_MANIFEST_BYTES:
        raise ManifestInvalidError("MANIFEST_TOO_LARGE")

    try:
        raw = resolved_manifest.read_bytes()
    except OSError:
        raise ContainmentError("MANIFEST_IO_ERROR")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ManifestInvalidError("MANIFEST_NOT_UTF8")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise ManifestInvalidError("MANIFEST_MALFORMED_JSON")

    if not isinstance(data, dict):
        raise ManifestInvalidError("MANIFEST_NOT_OBJECT")

    files_raw = data.get("files")
    if not isinstance(files_raw, list):
        raise ManifestInvalidError("MANIFEST_FILES_NOT_LIST")
    if len(files_raw) > MAX_MANIFEST_FILES:
        raise ManifestInvalidError("MANIFEST_TOO_MANY_FILES")

    placeholders_raw = data.get("placeholders")
    if not isinstance(placeholders_raw, list):
        raise ManifestInvalidError("MANIFEST_PLACEHOLDERS_NOT_LIST")
    if len(placeholders_raw) > MAX_PLACEHOLDERS:
        raise ManifestInvalidError("MANIFEST_TOO_MANY_PLACEHOLDERS")

    declared = []
    seen_declared = set()
    for item in placeholders_raw:
        if not isinstance(item, str):
            raise ManifestInvalidError("MALFORMED_PLACEHOLDER_DECLARATION")
        m = PLACEHOLDER_DECL_RE.match(item)
        if not m:
            raise ManifestInvalidError("MALFORMED_PLACEHOLDER_DECLARATION")
        name = m.group(1)
        if name in seen_declared:
            raise ManifestInvalidError("DUPLICATE_PLACEHOLDER_DECLARATION")
        seen_declared.add(name)
        declared.append(name)

    required_keys = (
        "path", "classification", "content_mode", "sha256",
        "required", "notes", "target_path", "adoption_mode",
    )

    entries = []
    seen_paths = set()
    manifest_self_seen = False

    for raw_entry in files_raw:
        if not isinstance(raw_entry, dict):
            raise ManifestInvalidError("FILE_ENTRY_NOT_OBJECT")
        for key in required_keys:
            if key not in raw_entry:
                raise ManifestInvalidError("FILE_ENTRY_MISSING_FIELD")

        path = raw_entry["path"]
        if not isinstance(path, str) or path == "":
            raise ManifestInvalidError("FILE_ENTRY_INVALID_PATH")
        if _is_unsafe_relative_path(path):
            raise ManifestInvalidError("UNSAFE_PACKAGE_PATH")
        if path in seen_paths:
            raise ManifestInvalidError("DUPLICATE_MANIFEST_PATH")
        seen_paths.add(path)

        classification = raw_entry["classification"]
        if classification not in ALLOWED_CLASSIFICATIONS:
            raise ManifestInvalidError("UNKNOWN_CLASSIFICATION")

        content_mode = raw_entry["content_mode"]
        if content_mode not in ALLOWED_CONTENT_MODES:
            raise ManifestInvalidError("UNKNOWN_CONTENT_MODE")

        required_flag = raw_entry["required"]
        if not isinstance(required_flag, bool):
            raise ManifestInvalidError("REQUIRED_NOT_BOOLEAN")

        adoption_mode = raw_entry["adoption_mode"]
        if adoption_mode not in ALLOWED_ADOPTION_MODES:
            raise ManifestInvalidError("UNKNOWN_ADOPTION_MODE")

        target_path = raw_entry["target_path"]
        if target_path is not None:
            if not isinstance(target_path, str) or target_path == "":
                raise ManifestInvalidError("INVALID_TARGET_PATH_TYPE")
            if _is_unsafe_relative_path(target_path):
                raise ManifestInvalidError("UNSAFE_TARGET_PATH")

        if adoption_mode in NO_TARGET_ADOPTION_MODES:
            if target_path is not None:
                raise ManifestInvalidError("ADOPTION_MODE_TARGET_PATH_MISMATCH")
        else:
            if target_path is None:
                raise ManifestInvalidError("ADOPTION_MODE_TARGET_PATH_MISMATCH")

        notes = raw_entry["notes"]
        if not isinstance(notes, str):
            raise ManifestInvalidError("NOTES_NOT_STRING")

        sha256 = raw_entry["sha256"]
        if path == "manifest.json":
            manifest_self_seen = True
            if sha256 is not None:
                raise ManifestInvalidError("MANIFEST_SELF_HASH_NOT_NULL")
            if "self-referential hash intentionally omitted" not in notes:
                raise ManifestInvalidError("MANIFEST_SELF_NOTES_MISSING_PHRASE")
        else:
            if not isinstance(sha256, str) or not SHA256_RE.match(sha256):
                raise ManifestInvalidError("INVALID_SHA256_FORMAT")

        entries.append(FileEntry(
            path=path, classification=classification, content_mode=content_mode,
            sha256=sha256, required=required_flag, notes=notes,
            target_path=target_path, adoption_mode=adoption_mode,
        ))

    if not manifest_self_seen:
        raise ManifestInvalidError("MANIFEST_SELF_ENTRY_MISSING")

    path_placeholder_names = set()
    for e in entries:
        if e.target_path:
            tokens = _find_tokens(e.target_path)
            for t in tokens:
                if t not in seen_declared:
                    raise ManifestInvalidError("UNDECLARED_PLACEHOLDER_IN_TARGET_PATH")
            path_placeholder_names |= tokens

    manifest_data = ManifestData(files=entries, placeholders=declared,
                                  path_placeholder_names=path_placeholder_names)
    return manifest_data, size


# --------------------------------------------------------------------------
# Output helpers (non-disclosure: never print file bodies, user-supplied
# content-only-placeholder values, absolute target-root paths, or raw
# OSError/argparse text; target-root is always shown as the fixed literal
# below. Path-placeholder values MAY appear as part of a rendered relative
# target_path, since that is the tool's core comparison output — see
# README.md "検証CLI（verifier）" for the exact boundary.)
# --------------------------------------------------------------------------

def _print_file_line(state, package_path, target_display, mode, reason):
    print(f"[{state}]")
    print(f"package: {package_path}")
    print(f"target: {target_display}")
    print(f"mode: {mode}")
    print(f"reason: {reason}")
    print()


def _counter_key_for_state(state: str) -> str:
    """Maps a display state to its summary counter key. STATE_BLOCKING_ERROR
    is the one state whose counter key ("blocking_errors", plural) does not
    match state.lower() ("blocking_error", singular) -- every other state's
    counter key is simply its own lowercased name."""
    if state == STATE_BLOCKING_ERROR:
        return "blocking_errors"
    return state.lower()


def _print_summary(counts: Counter, exit_code: int, extra_keys=()):
    print("summary:")
    for key in (
        "compared", "identical", "missing", "different", "invalid", "blocking_errors",
        "unresolved_placeholder", "skipped_by_mode", "manual_review_required",
    ):
        print(f"  {key}: {counts.get(key, 0)}")
    for key in extra_keys:
        print(f"  {key}: {counts.get(key, 0)}")
    print(f"  final_exit: {exit_code}")


# --------------------------------------------------------------------------
# source-integrity
# --------------------------------------------------------------------------

def _check_package_file_integrity(package_root: Path, entry: FileEntry, total_read_so_far: int,
                                   declared: set):
    """Returns (state, reason, blocking, bytes_read). `blocking=True` always
    pairs with state=STATE_BLOCKING_ERROR (never STATE_INVALID) -- blocking
    containment/I/O safety-boundary findings are counted and displayed
    separately from non-blocking content/type/metadata INVALID findings."""
    resolved, reason = _resolve_and_check_containment(package_root, entry.path)
    if reason:
        return STATE_BLOCKING_ERROR, reason, True, 0

    try:
        st = os.lstat(str(resolved))
    except FileNotFoundError:
        return STATE_MISSING, "PACKAGE_FILE_MISSING", False, 0
    except OSError:
        return STATE_BLOCKING_ERROR, "PACKAGE_FILE_IO_ERROR", True, 0

    if stat.S_ISDIR(st.st_mode):
        return STATE_INVALID, "PACKAGE_PATH_IS_DIRECTORY", False, 0
    if not stat.S_ISREG(st.st_mode):
        return STATE_INVALID, "SPECIAL_FILE", False, 0
    if st.st_size > MAX_FILE_BYTES:
        return STATE_INVALID, "FILE_TOO_LARGE", False, 0
    if total_read_so_far + st.st_size > MAX_TOTAL_READ_BYTES:
        return STATE_INVALID, "TOTAL_READ_LIMIT_EXCEEDED", False, 0

    try:
        data = resolved.read_bytes()
    except OSError:
        return STATE_BLOCKING_ERROR, "PACKAGE_FILE_IO_ERROR", True, st.st_size

    # If the file is valid UTF-8 text, confirm any {{...}}-style token it contains is
    # a declared placeholder. Binary/non-UTF-8 files are not scanned (this
    # tool only ever renders placeholders in UTF-8 text, in `plan`).
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    if text is not None:
        undeclared = sorted(t for t in _find_tokens(text) if t not in declared)
        if undeclared:
            return STATE_INVALID, "UNDECLARED_PLACEHOLDER", False, len(data)

    actual_hash = hashlib.sha256(data).hexdigest()
    if actual_hash != entry.sha256:
        return STATE_DIFFERENT, "HASH_DRIFT", False, len(data)
    return STATE_IDENTICAL, "BYTE_IDENTICAL", False, len(data)


class _ScanBudgetExceeded(Exception):
    """Internal-only signal: the package-root scan's entry budget
    (MAX_MANIFEST_FILES, counting every entry examined -- files,
    directories, symlinks/reparse points, and special entries alike, not
    only regular files) has been exceeded. Raising this immediately
    unwinds the ENTIRE recursive walk (not just the current directory's
    loop), so no further sibling entries, further directories, or further
    branches are scanned once the budget is exceeded, and the resulting
    TOO_MANY_PACKAGE_FILES finding is reported exactly once per run."""


def _scan_package_for_unlisted_files(package_root: Path, manifest_paths: set):
    """Recursively scan package_root (read-only) for regular files not
    declared in manifest_paths. Never descends into a symlink/junction/
    reparse-point directory; any such entry found (whether file or
    directory) is itself reported as a blocking containment concern
    unless its exact relative path is a declared manifest path. Applies
    the same MAX_MANIFEST_FILES / MAX_PATH_DEPTH limits used elsewhere;
    MAX_MANIFEST_FILES here is a scan entry budget (every entry examined
    counts toward it), not a count of regular files only. Does not read
    file contents, create/modify/delete anything, or print anything
    itself.

    Returns a list of (relpath, reason, blocking) tuples; empty means no
    problems found. There is deliberately no ignore-list (no `.DS_Store`,
    `__pycache__`, `.pyc`, editor backups, etc. are special-cased).
    """
    problems = []
    total_entries = 0

    def walk(dir_path: Path, rel_parts: list):
        nonlocal total_entries
        if len(rel_parts) > MAX_PATH_DEPTH:
            problems.append((None, "PATH_TOO_DEEP", False))
            return
        try:
            entries = sorted(os.scandir(str(dir_path)), key=lambda e: e.name)
        except OSError:
            problems.append((None, "CONTAINMENT_ERROR", True))
            return

        for entry in entries:
            if total_entries >= MAX_MANIFEST_FILES:
                raise _ScanBudgetExceeded()
            total_entries += 1

            entry_rel_parts = rel_parts + [entry.name]
            entry_rel = "/".join(entry_rel_parts)
            full_path = dir_path / entry.name

            if _path_is_reparse_or_symlink(str(full_path)):
                if entry_rel not in manifest_paths:
                    problems.append((entry_rel, "CONTAINMENT_ERROR", True))
                # Never descend into a symlink/junction/reparse point,
                # whether or not it is declared.
                continue

            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                problems.append((entry_rel, "CONTAINMENT_ERROR", True))
                continue

            if is_dir:
                # An empty (or entirely-declared) directory is never itself
                # flagged -- only unlisted regular files are.
                walk(full_path, entry_rel_parts)
                continue

            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                problems.append((entry_rel, "CONTAINMENT_ERROR", True))
                continue

            if not stat.S_ISREG(st.st_mode):
                if entry_rel not in manifest_paths:
                    problems.append((entry_rel, "UNLISTED_SPECIAL_FILE", False))
                continue

            if entry_rel not in manifest_paths:
                problems.append((entry_rel, "UNLISTED_PACKAGE_FILE", False))

    try:
        walk(package_root, [])
    except _ScanBudgetExceeded:
        problems.append((None, "TOO_MANY_PACKAGE_FILES", False))
    return problems


def run_source_integrity(package_root: Path) -> int:
    try:
        manifest, manifest_size = load_manifest(package_root)
    except PrerequisiteMissingError as e:
        print(f"[BLOCKED] reason: {e.args[0]}")
        return EXIT_MISSING_PREREQ
    except ManifestInvalidError as e:
        print(f"[BLOCKED] reason: {e.args[0]}")
        return EXIT_INVALID
    except ContainmentError as e:
        print(f"[BLOCKED] reason: {e.args[0]}")
        return EXIT_IO_CONTAINMENT

    declared = set(manifest.placeholders)
    counts = Counter()
    # Reaching this point means load_manifest() already validated the
    # manifest's structure, self-hash rule, and files/placeholders/
    # adoption_mode consistency in full -- so the manifest is valid by
    # definition here. This is a boolean-style summary field, not a count.
    counts["manifest_valid"] = 1
    total_read = manifest_size
    saw_blocking = saw_invalid = saw_missing = saw_drift = False

    for entry in sorted(manifest.files, key=lambda e: e.path):
        if entry.path == "manifest.json":
            counts["self_hash_omitted"] += 1
            _print_file_line(STATE_SKIPPED, entry.path, "not-applicable",
                              entry.adoption_mode, "SELF_HASH_INTENTIONALLY_OMITTED")
            continue

        counts["compared"] += 1
        state, reason, blocking, nbytes = _check_package_file_integrity(
            package_root, entry, total_read, declared)
        total_read += nbytes
        counts[_counter_key_for_state(state)] += 1
        # hash_compared only counts entries where a real SHA-256 comparison
        # against the manifest's recorded value actually completed --
        # MISSING/INVALID/etc. never reach that comparison and must not be
        # counted here, even though they are still counted in `compared`.
        if state == STATE_IDENTICAL:
            counts["hash_compared"] += 1
            counts["hash_matched"] += 1
        elif state == STATE_DIFFERENT:
            counts["hash_compared"] += 1
            counts["hash_mismatched"] += 1
        _print_file_line(state, entry.path, "not-applicable", entry.adoption_mode, reason)

        if blocking:
            saw_blocking = True
        elif state == STATE_INVALID:
            saw_invalid = True
        elif state == STATE_MISSING:
            saw_missing = True
        elif state == STATE_DIFFERENT:
            saw_drift = True

    manifest_paths = {e.path for e in manifest.files}
    unlisted_problems = _scan_package_for_unlisted_files(package_root, manifest_paths)
    counts["unlisted_package_files"] = sum(
        1 for _, reason, _ in unlisted_problems if reason == "UNLISTED_PACKAGE_FILE"
    )
    for relpath, reason, blocking in unlisted_problems:
        display_path = relpath if relpath is not None else "not-applicable"
        if blocking:
            # A blocking containment/I/O safety-boundary concern is
            # displayed as [BLOCKING_ERROR] and counted in `blocking_errors`
            # (exit 8) -- never as an additional [INVALID]/`invalid`, so the
            # same finding is never counted in both, and each displayed
            # status line always has a matching count in the summary.
            _print_file_line(STATE_BLOCKING_ERROR, display_path, "not-applicable", "UNLISTED", reason)
            saw_blocking = True
            counts["blocking_errors"] += 1
        else:
            _print_file_line(STATE_INVALID, display_path, "not-applicable", "UNLISTED", reason)
            saw_invalid = True
            counts["invalid"] += 1

    if saw_blocking:
        exit_code = EXIT_IO_CONTAINMENT
    elif saw_invalid:
        exit_code = EXIT_INVALID
    elif saw_missing:
        exit_code = EXIT_MISSING_PREREQ
    elif saw_drift:
        exit_code = EXIT_DRIFT
    else:
        exit_code = EXIT_OK

    _print_summary(counts, exit_code,
                    extra_keys=("hash_compared", "hash_matched", "hash_mismatched",
                                "self_hash_omitted", "manifest_valid", "unlisted_package_files"))
    return exit_code


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------

def _parse_set_args(raw_list):
    result = {}
    for item in raw_list:
        if "=" not in item:
            raise UsageError("MALFORMED_SET_ARGUMENT")
        name, _, value = item.partition("=")
        if not SET_NAME_RE.match(name):
            raise UsageError("MALFORMED_SET_NAME")
        if name in result:
            raise UsageError("DUPLICATE_SET_NAME")
        reason = _is_unsafe_set_value(value)
        if reason:
            raise UsageError(reason)
        result[name] = value
    return result


def _plan_check_one(package_root: Path, target_root: Path, entry: FileEntry,
                     values: dict, declared: set, total_read_so_far: int):
    """Returns (state, reason, blocking, target_display, bytes_read).
    `blocking=True` always pairs with state=STATE_BLOCKING_ERROR (never
    STATE_INVALID) -- see _check_package_file_integrity's docstring."""
    resolved_pkg, reason = _resolve_and_check_containment(package_root, entry.path)
    if reason:
        return STATE_BLOCKING_ERROR, reason, True, "not-applicable", 0

    try:
        st = os.lstat(str(resolved_pkg))
    except FileNotFoundError:
        return STATE_MISSING, "PACKAGE_FILE_MISSING", False, "not-applicable", 0
    except OSError:
        return STATE_BLOCKING_ERROR, "PACKAGE_FILE_IO_ERROR", True, "not-applicable", 0

    if stat.S_ISDIR(st.st_mode):
        return STATE_INVALID, "PACKAGE_PATH_IS_DIRECTORY", False, "not-applicable", 0
    if not stat.S_ISREG(st.st_mode):
        return STATE_INVALID, "SPECIAL_FILE", False, "not-applicable", 0
    if st.st_size > MAX_FILE_BYTES:
        return STATE_INVALID, "FILE_TOO_LARGE", False, "not-applicable", 0
    if total_read_so_far + st.st_size > MAX_TOTAL_READ_BYTES:
        return STATE_INVALID, "TOTAL_READ_LIMIT_EXCEEDED", False, "not-applicable", 0

    try:
        raw_pkg_bytes = resolved_pkg.read_bytes()
    except OSError:
        return STATE_BLOCKING_ERROR, "PACKAGE_FILE_IO_ERROR", True, "not-applicable", st.st_size

    try:
        pkg_text = raw_pkg_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return STATE_INVALID, "PACKAGE_FILE_NOT_UTF8", False, "not-applicable", st.st_size

    target_path_tokens = _find_tokens(entry.target_path) if entry.target_path else set()
    content_tokens = _find_tokens(pkg_text)
    all_tokens = target_path_tokens | content_tokens

    undeclared = sorted(t for t in all_tokens if t not in declared)
    if undeclared:
        return STATE_INVALID, "UNDECLARED_PLACEHOLDER", False, "not-applicable", st.st_size

    missing_values = sorted(t for t in all_tokens if t not in values)
    if missing_values:
        reason_detail = "UNRESOLVED_PLACEHOLDER:" + ",".join(missing_values)
        return STATE_UNRESOLVED, reason_detail, False, "not-applicable", st.st_size

    rendered_target_path = _substitute_tokens(entry.target_path, values)
    if _is_unsafe_relative_path(rendered_target_path):
        return STATE_INVALID, "UNSAFE_TARGET_PATH", False, "not-applicable", st.st_size

    rendered_pkg_bytes = _substitute_tokens(pkg_text, values).encode("utf-8")

    resolved_target, reason = _resolve_and_check_containment(target_root, rendered_target_path)
    if reason:
        return STATE_BLOCKING_ERROR, reason, True, rendered_target_path, st.st_size

    try:
        texists = os.path.lexists(str(resolved_target))
    except OSError:
        return STATE_BLOCKING_ERROR, "TARGET_IO_ERROR", True, rendered_target_path, st.st_size

    if not texists:
        return STATE_MISSING, "TARGET_MISSING", False, rendered_target_path, st.st_size

    try:
        tst = os.lstat(str(resolved_target))
    except OSError:
        return STATE_BLOCKING_ERROR, "TARGET_IO_ERROR", True, rendered_target_path, st.st_size

    if stat.S_ISDIR(tst.st_mode):
        return STATE_INVALID, "TARGET_IS_DIRECTORY", False, rendered_target_path, st.st_size
    if not stat.S_ISREG(tst.st_mode):
        return STATE_INVALID, "SPECIAL_FILE", False, rendered_target_path, st.st_size
    if tst.st_size > MAX_FILE_BYTES:
        return STATE_INVALID, "FILE_TOO_LARGE", False, rendered_target_path, st.st_size
    if total_read_so_far + st.st_size + tst.st_size > MAX_TOTAL_READ_BYTES:
        return STATE_INVALID, "TOTAL_READ_LIMIT_EXCEEDED", False, rendered_target_path, st.st_size

    try:
        target_bytes = resolved_target.read_bytes()
    except OSError:
        return STATE_BLOCKING_ERROR, "TARGET_IO_ERROR", True, rendered_target_path, st.st_size + tst.st_size

    total_bytes = st.st_size + tst.st_size
    if rendered_pkg_bytes == target_bytes:
        return STATE_IDENTICAL, "BYTE_IDENTICAL", False, rendered_target_path, total_bytes
    return STATE_DIFFERENT, "BYTE_DIFFERENT", False, rendered_target_path, total_bytes


def run_plan(package_root: Path, target_root_str: str, set_pairs: list) -> int:
    try:
        raw_values = _parse_set_args(set_pairs)
    except UsageError as e:
        print(f"usage error: {e.args[0]}", file=sys.stderr)
        return EXIT_USAGE

    try:
        manifest, manifest_size = load_manifest(package_root)
    except PrerequisiteMissingError as e:
        print(f"[BLOCKED] reason: {e.args[0]}")
        return EXIT_MISSING_PREREQ
    except ManifestInvalidError as e:
        print(f"[BLOCKED] reason: {e.args[0]}")
        return EXIT_INVALID
    except ContainmentError as e:
        print(f"[BLOCKED] reason: {e.args[0]}")
        return EXIT_IO_CONTAINMENT

    declared = set(manifest.placeholders)
    unknown = set(raw_values) - declared
    if unknown:
        print("usage error: UNKNOWN_SET_NAME", file=sys.stderr)
        return EXIT_USAGE

    for name, value in raw_values.items():
        if name in manifest.path_placeholder_names:
            reason = _is_unsafe_path_placeholder_value(value)
            if reason:
                print(f"usage error: {reason}", file=sys.stderr)
                return EXIT_USAGE

    target_root = Path(target_root_str)
    try:
        troot_exists = target_root.exists()
    except OSError:
        print(f"[BLOCKED] target root inaccessible: {TARGET_ROOT_DISPLAY}")
        return EXIT_IO_CONTAINMENT
    if not troot_exists:
        print(f"[BLOCKED] target root does not exist: {TARGET_ROOT_DISPLAY}")
        return EXIT_MISSING_PREREQ

    if _path_is_reparse_or_symlink(str(target_root)):
        print(f"[BLOCKED] target root is a symlink/junction/reparse point: {TARGET_ROOT_DISPLAY}")
        return EXIT_IO_CONTAINMENT

    try:
        troot_is_dir = target_root.is_dir()
    except OSError:
        print(f"[BLOCKED] target root inaccessible: {TARGET_ROOT_DISPLAY}")
        return EXIT_IO_CONTAINMENT
    if not troot_is_dir:
        print(f"[BLOCKED] target root is not a directory: {TARGET_ROOT_DISPLAY}")
        return EXIT_MISSING_PREREQ

    counts = Counter()
    total_read = manifest_size
    saw_blocking = False
    saw_package_prerequisite_missing = False
    manual_review_required = False

    for entry in sorted(manifest.files, key=lambda e: e.path):
        if entry.adoption_mode in NO_TARGET_ADOPTION_MODES:
            counts["skipped_by_mode"] += 1
            _print_file_line(STATE_SKIPPED, entry.path, "not-applicable",
                              entry.adoption_mode, "SKIPPED_BY_MODE")
            continue

        state, reason, blocking, target_display, nbytes = _plan_check_one(
            package_root, target_root, entry, raw_values, declared, total_read)
        total_read += nbytes
        counts["compared"] += 1
        counts[_counter_key_for_state(state)] += 1

        if state == STATE_MISSING and reason == "PACKAGE_FILE_MISSING":
            saw_package_prerequisite_missing = True

        if entry.adoption_mode == "MANUAL_REVIEW" and state not in (STATE_INVALID, STATE_BLOCKING_ERROR):
            manual_review_required = True
            counts["manual_review_required"] += 1

        _print_file_line(state, entry.path, target_display, entry.adoption_mode, reason)

        if blocking:
            saw_blocking = True

    if saw_blocking:
        exit_code = EXIT_IO_CONTAINMENT
    elif counts.get("invalid", 0) > 0:
        exit_code = EXIT_INVALID
    elif saw_package_prerequisite_missing:
        exit_code = EXIT_MISSING_PREREQ
    elif (counts.get("missing", 0) > 0 or counts.get("different", 0) > 0
          or counts.get("unresolved_placeholder", 0) > 0 or manual_review_required):
        exit_code = EXIT_DRIFT
    else:
        exit_code = EXIT_OK

    _print_summary(counts, exit_code)
    return exit_code


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class _SafeArgumentParser(argparse.ArgumentParser):
    """Never echoes user-supplied argument text back to the user. All
    argparse-level usage problems (missing/unknown arguments, invalid
    choices, unrecognized arguments, etc.) are reported with a single
    fixed, safe message. --help/-h is unaffected (argparse handles it via
    a separate code path that does not call error())."""

    def error(self, message):
        print("usage error: INVALID_CLI_ARGUMENTS", file=sys.stderr)
        self.exit(EXIT_USAGE)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(
        prog="verify_workflow_template.py",
        description=(
            "Read-only verifier for the multi-agent-workflow template package. "
            "Never writes, copies, merges, installs, updates, uninstalls, or "
            "runs Git/subprocess commands. Do not pass secrets as --set values."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("source-integrity",
                    help="Check the package's own files against manifest.json")

    plan_parser = sub.add_parser(
        "plan", help="Compare rendered package files against a target root (read-only)")
    plan_parser.add_argument("--target-root", required=True)
    plan_parser.add_argument(
        "--set", dest="set_values", action="append", default=[],
        metavar="NAME=VALUE",
        help="Placeholder value, e.g. --set PROJECT_NAME=example. Repeatable. "
             "Do not pass secrets or credentials as a value.",
    )

    return parser


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = build_arg_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        code = e.code
        return code if isinstance(code, int) else EXIT_USAGE

    package_root = Path(__file__).resolve().parents[1]

    if args.command == "source-integrity":
        return run_source_integrity(package_root)
    if args.command == "plan":
        return run_plan(package_root, args.target_root, args.set_values or [])
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
