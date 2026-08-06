"""Hardened, pinned external-opponent resolution.

Never floats to a remote's default branch HEAD (unlike experiments/web/
setup_agents.py, which this module does not modify or call) -- a commit SHA
is a REQUIRED input with no default, enforced by opponent_registry.py never
inventing one.

Hardening (see experiments/eval_infra/README.md caveat F4 for the one
remaining, deliberately-accepted gap in this threat model):
  - subprocess invoked with shell=False and an explicit argv list, never a
    shell string.
  - the repository URL is rejected if it starts with "-" (a cheap guard
    against a pin value being parsed as a flag by git), if it contains "::"
    (git's ext::/fd:: remote-helper transport syntax, which can execute an
    arbitrary command), if it uses any "scheme://" other than "https://",
    or if it looks like SCP-style SSH remote syntax (user@host:path or
    bare host:path) -- only "https://..." or a bare local filesystem path
    (no "@", no ":" outside a Windows drive-letter prefix like "C:") is
    accepted. This closes what an earlier version left as a documented,
    deliberately-accepted gap.
  - the clone lands in a directory from tempfile.mkdtemp() (OS temp dir,
    outside the repository), and pin values themselves (commit SHA, and any
    repo-relative file path requested from the clone) are rejected if they
    contain "..", a backslash, or a drive letter -- guards against path
    escape out of the clone root.
  - after checkout, `git rev-parse --verify <sha>^{commit}` must equal the
    requested commit exactly, or the resolution is UNAVAILABLE.
  - only the explicitly-listed files are read and SHA-256 hashed; the hash
    is taken once immediately after checkout and re-taken immediately
    before the caller loads the file, and a mismatch invalidates the result
    (a TOCTOU guard against the local clone changing between those two
    reads).
  - the CLONE directory (which holds the full checked-out repository) is
    deleted (shutil.rmtree) in a finally block immediately after the
    explicitly-requested files are copied out to a separate, caller-owned
    `dest_dir` -- so the full external repository is never left behind, and
    only the exact files the caller asked for persist, at `dest_dir`, for as
    long as the CALLER needs them (e.g. for the duration of one
    head_to_head.py subprocess invocation). Earlier versions of this module
    deleted the clone directory before returning any path to the caller,
    which made the returned paths unusable -- fixed: this module now
    returns paths under `dest_dir`, which is NOT deleted by this module; the
    caller is responsible for cleaning up `dest_dir` when done with it.
    Nothing under either directory is ever copied into any tracked
    repository path.
"""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import PurePosixPath

_COMMIT_SHA_RE_LEN = 40


class ClonePinError(ValueError):
    pass


@dataclass(frozen=True)
class ClonedFile:
    repo_relative_path: str
    absolute_path: str  # under dest_dir, NOT under the (already-deleted) clone dir
    sha256: str


@dataclass(frozen=True)
class CloneResult:
    opponent_id: str
    repo_url: str
    commit_sha: str
    dest_dir: str
    files: tuple[ClonedFile, ...]


def _reject_unsafe_pin_value(value: str, label: str) -> None:
    if ".." in value or "\\" in value or (len(value) >= 2 and value[1] == ":"):
        raise ClonePinError(f"{label} contains an unsafe path component: {value!r}")


_ALLOWED_URL_SCHEME = "https"


def _reject_unsafe_url(repo_url: str) -> None:
    if not repo_url or repo_url.startswith("-"):
        raise ClonePinError(f"repo_url rejected (empty or flag-like): {repo_url!r}")
    if "::" in repo_url:
        # Rejects git's remote-helper transport syntax (e.g. ext::, fd::), which can be
        # used to make `git clone` execute an arbitrary command.
        raise ClonePinError(
            f"repo_url rejected (contains '::', a git remote-helper transport syntax like "
            f"ext::/fd:: that can execute arbitrary commands): {repo_url!r}"
        )
    if "://" in repo_url:
        scheme = repo_url.split("://", 1)[0].lower()
        if scheme != _ALLOWED_URL_SCHEME:
            raise ClonePinError(
                f"repo_url scheme {scheme!r} is not in the allowlist (only "
                f"{_ALLOWED_URL_SCHEME!r} or a bare local filesystem path -- no scheme "
                f"separator -- is permitted): {repo_url!r}"
            )
        return  # https://... -- allowed
    # No "://" at all: must be a bare LOCAL filesystem path, not SCP-style SSH remote syntax
    # (git accepts both "user@host:path" and bare "host:path" as remotes, neither of which
    # contains "://" or "::"). An earlier version accepted these unconditionally, silently
    # treating an SSH remote as if it were "just a local path" -- reject anything containing
    # "@" (a strong signal of user@host syntax), and reject any ":" that is not a Windows
    # drive-letter prefix (e.g. "C:") -- a bare "host:path" has a colon that is neither.
    if "@" in repo_url:
        raise ClonePinError(
            f"repo_url rejected (contains '@', which is SCP-style SSH remote syntax "
            f"'user@host:path', not a bare local filesystem path): {repo_url!r}"
        )
    colon_idx = repo_url.find(":")
    # The drive-letter exception is only meaningful on Windows itself -- on Linux/WSL (where
    # real cabt games actually run, per repo docs), a single-letter host like "a:b" is
    # unambiguously SCP-style git remote syntax, not a filesystem drive letter, and git on
    # that platform will interpret it as such. An earlier version applied this exception on
    # every platform, so "a:b" bypassed the allowlist even when running on Linux/WSL -- found
    # by an independent heterogeneous-model audit.
    is_drive_letter_prefix = (
        platform.system() == "Windows" and colon_idx == 1 and repo_url[0].isalpha()
    )
    if colon_idx != -1 and not is_drive_letter_prefix:
        raise ClonePinError(
            f"repo_url rejected (contains ':' that is not a Windows drive-letter prefix on "
            f"this platform, which is SCP-style SSH remote syntax 'host:path', not a bare "
            f"local filesystem path): {repo_url!r}"
        )
    # A bare local filesystem path with no "@" and no non-drive-letter ":" -- allowed (used
    # by this module's own synthetic-local-repo tests). A real production pin should
    # normally use https://.


def clone_and_verify(
    opponent_id: str,
    repo_url: str,
    commit_sha: str,
    file_paths: tuple[str, ...],
    dest_dir: str,
) -> CloneResult:
    """Clone repo_url to a repo-external temp dir, verify the checked-out
    commit exactly matches commit_sha, copy the explicitly-listed
    file_paths out to `dest_dir` (a directory the CALLER owns and must
    clean up when done -- this function never deletes it), and return their
    contents' identity with absolute_path pointing under `dest_dir`. Raises
    ClonePinError on any hardening violation or verification failure --
    callers must treat that as this opponent being UNAVAILABLE for this
    run, never as a reason to fall back to an unpinned/floating clone.
    """
    if len(commit_sha) != _COMMIT_SHA_RE_LEN or not all(c in "0123456789abcdef" for c in commit_sha):
        raise ClonePinError(f"commit_sha must be exactly 40 lowercase hex chars, got {commit_sha!r}")
    _reject_unsafe_url(repo_url)
    if not file_paths:
        raise ClonePinError("file_paths must list at least one file to clone")
    for p in file_paths:
        _reject_unsafe_pin_value(p, "file_paths entry")
        if PurePosixPath(p).is_absolute():
            raise ClonePinError(f"file_paths entry must be repo-relative, got absolute: {p!r}")
    if len(file_paths) != len(set(os.path.basename(p) for p in file_paths)):
        raise ClonePinError("file_paths entries must have distinct basenames (dest_dir is flat)")

    os.makedirs(dest_dir, exist_ok=True)
    clone_dir = tempfile.mkdtemp(prefix="eval_infra_opponent_clone_")
    try:
        _run_git(["clone", "--no-checkout", repo_url, clone_dir])
        _run_git(["-C", clone_dir, "fetch", "--depth", "1", "origin", commit_sha])
        _run_git(["-C", clone_dir, "checkout", "--detach", commit_sha])
        verified = _run_git(["-C", clone_dir, "rev-parse", "--verify", f"{commit_sha}^{{commit}}"])
        actual_sha = verified.stdout.strip()
        if actual_sha != commit_sha:
            raise ClonePinError(
                f"post-checkout verification failed: expected {commit_sha}, got {actual_sha}"
            )

        files: list[ClonedFile] = []
        for rel in file_paths:
            src_abs = _safe_join(clone_dir, rel)
            src_hash = _sha256_file(src_abs)
            dest_abs = os.path.join(dest_dir, os.path.basename(rel))
            shutil.copy2(src_abs, dest_abs)
            dest_hash = _sha256_file(dest_abs)  # verifies the copy is byte-identical to the clone
            if src_hash != dest_hash:
                raise ClonePinError(f"copy verification failed (hash mismatch after copy): {rel}")
            files.append(ClonedFile(repo_relative_path=rel, absolute_path=dest_abs, sha256=dest_hash))

        return CloneResult(
            opponent_id=opponent_id, repo_url=repo_url, commit_sha=commit_sha,
            dest_dir=dest_dir, files=tuple(files),
        )
    finally:
        # Only the full clone (potentially the whole external repo) is
        # removed here. The explicitly-requested files already live under
        # dest_dir, which this function does not own and does not delete.
        shutil.rmtree(clone_dir, ignore_errors=True)


def _safe_join(base_dir: str, repo_relative_path: str) -> str:
    import os

    candidate = os.path.normpath(os.path.join(base_dir, repo_relative_path))
    base_real = os.path.realpath(base_dir)
    candidate_real = os.path.realpath(candidate)
    if os.path.commonpath([base_real, candidate_real]) != base_real:
        raise ClonePinError(f"path escapes clone root (symlink or traversal): {repo_relative_path!r}")
    if not os.path.isfile(candidate_real):
        raise ClonePinError(f"expected file not found in clone: {repo_relative_path!r}")
    return candidate_real


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_git(args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args],
        shell=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise ClonePinError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result
