"""CLI entry point: manifest / run / summarize.

`manifest` fully resolves and FREEZES everything about a comparison at
creation time: selected opponents (with exact commit SHA / individual file
SHA-256 for pinned-clone opponents, actually cloned-and-verified right then,
not merely referenced), games_per_segment, the exact per-game side
(seat-slot) allocation schedule, the compiled engine's libcg.so SHA-256,
this evaluator's own source SHA-256, and the Python/OS runtime environment.
All of this is hashed into `comparison_manifest_sha256`. `run` reads
opponents/games_per_segment/schedule EXCLUSIVELY from `--manifest` -- it has
no `--opponent`/`--games-per-segment` flags of its own, so the executed
protocol can never silently diverge from what the manifest identifies, and
`opponent_pins.json` is consulted ONLY by `manifest` (never by `run`), so a
manifest's hash can never be reused to execute a different opponent set
later. `run` also independently re-verifies every opponent/artifact binding
against disk (and, for pinned-clone opponents, re-clones and re-hashes) at
execution time, failing closed on any drift from what `manifest` recorded.

`manifest`/`run`'s CLI shape and fail-closed/tamper-detection paths are
exercised by experiments/test_eval_infra.py on any OS. Actually spawning
experiments/head_to_head.py to play real games only works on Linux/WSL
(cg.game requires libcg.so) -- see README.md caveats; that part of `run` is
implemented here but not executed by this repo's Windows-based test session
(L1-L3, explicitly deferred, not claimed passing).

Produces a "Measurement Report" (summarize's --out), which is DISTINCT from
a Gatekeeper "Evidence Bundle": it omits profile_id/profile_version/
profile_sha256/cycle_id/evidence_round (those only exist once bound to an
active App Profile, out of scope here) but every cell it does emit is
shaped exactly like a Gatekeeper Evidence cell (exact 6 keys, see
schema.build_cell), so assembling a real Evidence Bundle from a Measurement
Report plus an active Profile's binding fields is a distinct, later,
out-of-scope step this module does not perform. A report's `report_kind` is
"primary" only when every one of the manifest's selected opponents (a
superset that must equal {lucario, dragapult, megastarmie} for the report to
be eligible at all) has both baseline and candidate data present; otherwise
it is "partial_diagnostic" and the league-wide `external_league_win_rate`/
"overall" cell is never computed (per-opponent cells for whatever WAS
supplied still are).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from experiments.eval_infra import clone_opponent, opponent_registry, schema
from experiments.eval_infra.canon import sha256_hex
from experiments.eval_infra.stats import (
    exact_count_interval, game_cluster_bootstrap_delta, game_cluster_bootstrap_interval,
    newcombe_delta, percentile_statistic, wilson_interval,
)

_HEAD_TO_HEAD_PATH = os.path.join(_REPO_ROOT, "experiments", "head_to_head.py")
_PINS_PATH = os.path.join(_REPO_ROOT, "experiments", "eval_infra", "opponent_pins.json")
_LIBCG_SO_PATH = os.path.join(_REPO_ROOT, "reference", "extracted", "cg", "libcg.so")
_CG_PYTHON_WRAPPER_FILES = ("__init__.py", "api.py", "game.py", "utils.py", "sim.py")
_EVAL_INFRA_SOURCE_FILES = (
    "__init__.py", "canon.py", "stats.py", "schema.py", "opponent_registry.py", "clone_opponent.py", "raging_bolt_eval.py",
)

# The actual hardcoded engine-loop constants in experiments/head_to_head.py (`for step in
# range(2000):`) and this module's own `run` (always exactly 1 game per subprocess call, see
# the BLOCKER 2 module docstring). protocol_identity.step_limit/games_per_worker are recorded
# in every manifest to make this explicit, but recording them is not the same as enforcing
# them: a manifest built without going through the `manifest` CLI (but still internally
# hash-consistent) could claim a different step_limit/games_per_worker than what `run` will
# actually execute, with nothing catching the discrepancy. _verify_manifest_integrity checks
# both fields against these constants so such a manifest is rejected before `run`/`summarize`
# trust anything else in it.
_ACTUAL_STEP_LIMIT = 2000
_ACTUAL_GAMES_PER_WORKER = 1
_ACTUAL_WORKER_MODEL = "one_subprocess_per_game"
_ACTUAL_DECISION_TIME_MEASUREMENT = (
    "wall-clock time.perf_counter() per agent decision, tagged actor=a|b; summarize uses "
    "only actor=a (the arm under measurement)"
)
_ACTUAL_GAME_RNG_CONTROL = {
    "availability": "UNAVAILABLE",
    "reason": "no seed/RNG-control parameter exists anywhere in cg.api/cg.game's Python surface",
}

# The actual, fixed statistical methods this harness uses -- see stats.py's module docstring
# for the rationale (Wilson/Newcombe for game-level 0/1 rate metrics, since no seed/RNG
# control exists anywhere in cg.api/cg.game so runs are independent unpaired samples; a
# whole-game cluster bootstrap for decision-level latency metrics, since decisions within one
# game are correlated). Recorded into every manifest's protocol_identity.measurement_settings
# (and hashed into comparison_manifest_sha256) purely for self-documentation/auditability -- a
# CODE change to which method is actually used would already change comparison_manifest_sha256
# via evaluator_binding (raging_bolt_eval.py's own source hash), so these strings are not
# themselves an independent enforcement mechanism, just an explicit, human-readable record of
# what evaluator_binding's hash is currently pinning.
_RATE_INTERVAL_METHOD = "wilson_score"
_RATE_DELTA_METHOD = "newcombe_wilson"
_LATENCY_BOOTSTRAP_METHOD = "game_cluster_bootstrap_percentile"
_BOOTSTRAP_SEED_SCHEME = "sha256_counter(comparison_manifest_sha256, metric_id, segment_id, arm) -- no caller-supplied seed"


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _abs_repo_path(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(_REPO_ROOT, path)


def _confine_to_repo_root(abs_path: str, original_for_error: str) -> str:
    """Resolve an already-absolute path via os.path.realpath (collapsing "..", "." and
    SYMLINKS -- not just a string-level normpath) and confirm the result is contained within
    the repository root. Returns the resolved real absolute path (safe to open/hash). Raises
    ValueError on any escape: an absolute path outside the repo, a "../" traversal out of the
    repo, or a symlink that points outside the repo. Windows paths are case-insensitive, so
    the CONTAINMENT CHECK normalizes case via os.path.normcase; the returned path keeps its
    real on-disk case."""
    real_candidate = os.path.realpath(abs_path)
    real_repo_root = os.path.realpath(_REPO_ROOT)
    try:
        common = os.path.commonpath([real_repo_root, real_candidate])
    except ValueError:
        # e.g. paths on different Windows drives -- definitionally not contained.
        common = None
    if common is None or os.path.normcase(common) != os.path.normcase(real_repo_root):
        raise ValueError(
            f"path {original_for_error!r} resolves to {real_candidate!r}, which is outside "
            f"the repository root {real_repo_root!r} -- rejecting (escape via '..', an "
            f"absolute path outside the repo, or a symlink pointing outside it)"
        )
    return real_candidate


def _resolve_repo_confined_artifact_path(path: str) -> tuple[str, str]:
    """Resolve `path` (relative-to-repo-root or absolute) to a real file strictly confined to
    the repository. Returns (repo_relative_posix_path, real_absolute_path) -- ONLY the first
    value is ever stored in a manifest/files entry, so no local machine's absolute filesystem
    path is ever persisted (verified by T14's content-safety scan); the second value is used
    solely to open/hash the file's bytes right now. A repo-internal absolute path input is
    normalized to the same repo-relative form as an equivalent relative input (so both hash
    identically and the candidate/baseline "byte-identical artifact" self-comparison guard
    cannot be bypassed by spelling). Raises ValueError if the path cannot be confined to the
    repository (found necessary by an independent external review after an earlier version
    only did string-level normpath, which does not resolve symlinks or verify containment at
    all)."""
    abs_input = _abs_repo_path(path)
    real_candidate = _confine_to_repo_root(abs_input, path)
    if not os.path.isfile(real_candidate):
        raise ValueError(f"artifact path {path!r} (resolved to {real_candidate!r}) is not a file")
    real_repo_root = os.path.realpath(_REPO_ROOT)
    repo_relative = os.path.relpath(real_candidate, real_repo_root).replace(os.sep, "/")
    return repo_relative, real_candidate


def _artifact_binding(artifact_id: str, agent_path: str, deck_path: str, params_path: str | None) -> dict:
    """Individual per-file SHA-256 hashes, combined into a canonical bundle
    hash over the {logical_name, path, sha256} list -- NOT a hash of raw
    concatenated file bytes. A hash of concatenated bytes cannot distinguish
    "the agent changed" from "the deck changed" and has an ambiguous
    file-boundary; the per-file list here has none of that ambiguity, and
    each file's own hash is independently available too.

    "files" is the ONLY place a path lives in this binding -- there is
    deliberately no separate top-level agent_path/deck_path/params_path
    field. An earlier version kept both, and every consumer (execution,
    re-verification) read the top-level fields while only "files" was
    covered by comparison_manifest_sha256 -- so editing the top-level path
    alone (leaving "files" and the bundle hash untouched) would pass every
    integrity/re-hash check while silently executing different content. A
    single source of truth removes that gap by construction.

    Every path is resolved via _resolve_repo_confined_artifact_path -- which uses realpath
    (resolving symlinks, not just string-level normpath) and requires containment within the
    repository root -- before it is hashed or stored, so: (1) two different spellings of the
    same file (e.g. "main.py" vs "./main.py", or a repo-internal absolute path vs the
    equivalent relative one) resolve to the identical repo-relative path and therefore hash
    identically, restoring the candidate-vs-baseline "byte-identical artifact" self-comparison
    guard below; (2) a path outside the repository (absolute-elsewhere, "../" escape, or a
    symlink pointing outside the repo) is rejected outright, so it can never be hashed/read at
    all; (3) only the repo-relative POSIX path is ever stored -- never a local machine's
    absolute filesystem path -- in the manifest or, later, the report. Raises ValueError
    (caught by cmd_manifest) if any path cannot be confined to the repository."""
    entries = [("agent", agent_path), ("deck", deck_path)]
    if params_path:
        entries.append(("params", params_path))
    files = []
    for name, p in entries:
        repo_relative_path, abs_path_for_hash = _resolve_repo_confined_artifact_path(p)
        files.append({"logical_name": name, "path": repo_relative_path, "sha256": _hash_file(abs_path_for_hash)})
    bundle_sha256 = _artifact_bundle_sha256_from_files(files)
    return {
        "artifact_id": artifact_id,
        "sha256": bundle_sha256,
        "files": files,
    }


def _artifact_bundle_sha256_from_files(files: list[dict]) -> str:
    """The exact formula _artifact_binding uses to derive its top-level bundle
    sha256 from its own "files" list -- factored out so integrity-verification
    can recompute it from a manifest's stored "files" and confirm the stored
    top-level "sha256" was not edited independently of "files" (which is what
    comparison_manifest_sha256 actually binds, per _artifact_binding's
    docstring).

    Includes "path", not just "logical_name"/"sha256": an earlier version
    hashed only {logical_name, sha256}, so an entry could be repointed at a
    byte-identical copy of the same file living at a DIFFERENT path (same
    hash, different location) without changing the bundle hash at all --
    found by an independent heterogeneous-model audit. Since agent code can
    resolve neighboring files relative to its own path (e.g. deck.csv/
    params.json lookup relative to `main.py`'s directory, per this repo's
    documented path-resolution rules), an identical-bytes-different-location
    substitution can still change what the agent actually does at run time.
    Hashing "path" too means comparison_manifest_sha256 binds path AND
    content, not content alone."""
    return sha256_hex({"files": [{"logical_name": f["logical_name"], "path": f["path"], "sha256": f["sha256"]} for f in files]})


def _artifact_file_path(artifact: dict, logical_name: str) -> str | None:
    """The single, authoritative way to get one of an artifact's file paths
    -- always from "files" (the thing comparison_manifest_sha256 actually
    binds), never from a separate, potentially-stale top-level field."""
    for f in artifact.get("files", []):
        if f["logical_name"] == logical_name:
            return f["path"]
    return None


def _engine_binding() -> dict:
    """libcg.so (the compiled engine) plus its Python wrapper files
    (reference/extracted/cg/*.py, which cg.game/cg.api import) -- together
    these are "the engine as actually invoked". `manifest` computes this
    once; `run` and `summarize` both RECOMPUTE it and fail closed if it no
    longer matches (see _verify_execution_bindings_unchanged) -- an earlier
    version recorded this but never re-checked it at execution time."""
    if not os.path.isfile(_LIBCG_SO_PATH):
        return {"availability": "UNAVAILABLE", "reason": "reference/extracted/cg/libcg.so not found",
                "libcg_so_sha256": None, "wrapper_files": []}
    cg_dir = os.path.dirname(_LIBCG_SO_PATH)
    wrapper_files = [
        {"name": name, "sha256": _hash_file(os.path.join(cg_dir, name))}
        for name in _CG_PYTHON_WRAPPER_FILES if os.path.isfile(os.path.join(cg_dir, name))
    ]
    return {"availability": "AVAILABLE", "libcg_so_sha256": _hash_file(_LIBCG_SO_PATH), "wrapper_files": wrapper_files}


def _evaluator_binding() -> dict:
    """SHA-256 of every executable file this harness's measurement actually
    depends on: this package's own eval_infra/*.py source AND
    experiments/head_to_head.py -- the actual game-runner script `run`
    invokes as a subprocess. An earlier version omitted head_to_head.py, so
    a change to the real game-loop code would not have changed this
    binding despite directly affecting what gets measured."""
    eval_infra_dir = os.path.dirname(os.path.abspath(__file__))
    files = [{"name": name, "sha256": _hash_file(os.path.join(eval_infra_dir, name))} for name in _EVAL_INFRA_SOURCE_FILES]
    files.append({"name": "experiments/head_to_head.py", "sha256": _hash_file(_HEAD_TO_HEAD_PATH)})
    return {"bundle_sha256": sha256_hex({"files": files}), "files": files}


def _verify_execution_bindings_unchanged(manifest: dict) -> str | None:
    """Recompute engine_binding/evaluator_binding/runtime_environment RIGHT
    NOW and compare against what `manifest` recorded. An earlier version
    computed and hashed these into the manifest at creation time but never
    re-checked them at `run`/`summarize` time -- so libcg.so, its Python
    wrapper, this harness's own source, or head_to_head.py changing after
    the manifest was written would silently execute/summarize under a
    stale protocol hash. `runtime_environment` is enforced too (not merely
    recorded): this design's stated principle is that `manifest` freezes
    EVERYTHING, so a manifest is deliberately tied to being executed in the
    same Python/OS environment it was created in -- create a fresh manifest
    for a different machine, rather than silently reusing an old hash."""
    current_engine = _engine_binding()
    recorded_engine = manifest["protocol_identity"]["engine_binding"]
    # recorded_engine/recorded_evaluator must be validated as dicts BEFORE .get() is called on
    # them below -- a forged manifest could set either to a non-dict JSON value (e.g. a JSON
    # array) with a correctly recomputed protocol/comparison hash, which would otherwise raise
    # an uncaught AttributeError ('list' object has no attribute 'get') while formatting the
    # mismatch error itself, instead of a controlled rejection (found by an independent
    # heterogeneous-model audit).
    if not isinstance(recorded_engine, dict):
        return f"engine_binding in the manifest is not an object, got {recorded_engine!r}"
    if current_engine != recorded_engine:
        return (f"engine_binding mismatch: libcg.so and/or its Python wrapper files "
                f"(reference/extracted/cg/*.py) differ from what `manifest` recorded "
                f"(recorded libcg_so_sha256={recorded_engine.get('libcg_so_sha256')!r}, "
                f"now {current_engine.get('libcg_so_sha256')!r})")

    current_evaluator = _evaluator_binding()
    recorded_evaluator = manifest["protocol_identity"]["evaluator_binding"]
    if not isinstance(recorded_evaluator, dict):
        return f"evaluator_binding in the manifest is not an object, got {recorded_evaluator!r}"
    if current_evaluator != recorded_evaluator:
        return (f"evaluator_binding mismatch: this harness's own source code (including "
                f"experiments/head_to_head.py) differs from what `manifest` recorded "
                f"(recorded bundle_sha256={recorded_evaluator.get('bundle_sha256')!r}, now "
                f"{current_evaluator.get('bundle_sha256')!r})")

    current_runtime = _runtime_environment()
    recorded_runtime = manifest["protocol_identity"]["runtime_environment"]
    if current_runtime != recorded_runtime:
        return (f"runtime_environment mismatch: the current Python/OS environment differs "
                f"from what `manifest` recorded (recorded {recorded_runtime!r}, now "
                f"{current_runtime!r}) -- create a fresh manifest for this environment "
                f"rather than reusing one made elsewhere")
    return None


def _runtime_environment() -> dict:
    return {
        "python_version": platform.python_version(),
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_machine": platform.machine(),
        "os_distribution": _os_distribution_identity(),
    }


def _os_distribution_identity() -> dict:
    """Linux/WSL distribution identity. platform_system/platform_release/platform_machine
    alone cannot distinguish two different WSL distributions (or two Linux distros) that
    happen to share the same reported kernel release and the same Python version -- found by
    an independent heterogeneous-model audit. This matters specifically here because real
    cabt games require running under WSL/Linux (see repo docs); on Windows (no WSL_DISTRO_NAME
    env var and no /etc/os-release) this is NOT_APPLICABLE rather than a fabricated value."""
    wsl_distro_name = os.environ.get("WSL_DISTRO_NAME")
    try:
        os_release_info = platform.freedesktop_os_release()
        os_release = {
            "id": os_release_info.get("ID"),
            "version_id": os_release_info.get("VERSION_ID"),
            "pretty_name": os_release_info.get("PRETTY_NAME"),
        }
    except (OSError, AttributeError):
        os_release = None
    if wsl_distro_name is None and os_release is None:
        return {
            "availability": "NOT_APPLICABLE",
            "reason": "no WSL_DISTRO_NAME env var and no /etc/os-release -- not running under "
                      "WSL/Linux, or distribution identity is unavailable on this platform",
        }
    return {"availability": "AVAILABLE", "wsl_distro_name": wsl_distro_name, "os_release": os_release}


def _resolve_opponent_binding(opponent_id: str, pins: dict) -> dict:
    """Resolve and fully snapshot one opponent's identity AT MANIFEST TIME
    ONLY -- opponent_pins.json is never read again at `run` time (see module
    docstring). For a pinned-clone opponent this ACTUALLY CLONES AND
    VERIFIES the commit right now, so the manifest binds the opponent's real
    file hashes, not merely a commit reference that might not even resolve.
    Raises ValueError if the opponent cannot be fully resolved right now --
    manifest creation must abort in that case (caller must supply a valid
    pin or drop this opponent from --opponent), never proceed with a
    partially-specified binding."""
    if opponent_id == opponent_registry.MIRROR_OPPONENT_ID:
        return {"opponent_id": opponent_id, "source_kind": "self_play"}

    if opponent_id in opponent_registry.LOCAL_ONLY_OPPONENTS:
        paths = opponent_registry.LOCAL_ONLY_OPPONENTS[opponent_id]
        agent_abs = _abs_repo_path(paths["agent_path"])
        deck_abs = _abs_repo_path(paths["deck_path"])
        if not (os.path.isfile(agent_abs) and os.path.isfile(deck_abs)):
            raise ValueError(
                f"opponent {opponent_id!r} is UNAVAILABLE at manifest time (local-only files "
                f"absent, no known recovery path) -- drop it from --opponent or supply the "
                f"files first"
            )
        return {
            "opponent_id": opponent_id, "source_kind": "local_only",
            "files": [
                {"logical_name": "agent", "path": paths["agent_path"], "sha256": _hash_file(agent_abs)},
                {"logical_name": "deck", "path": paths["deck_path"], "sha256": _hash_file(deck_abs)},
            ],
        }

    if opponent_id in opponent_registry.PINNED_CLONE_OPPONENTS:
        entry = pins.get(opponent_id, {})
        repo_url = entry.get("repo_url") if isinstance(entry, dict) else None
        file_paths = entry.get("file_paths") if isinstance(entry, dict) else None
        commit_sha = entry.get("commit_sha") if isinstance(entry, dict) else None
        # Every field's TYPE must be validated here, not just truthiness -- `not file_paths`
        # is False for a non-empty non-list value (e.g. an int), so len(file_paths) below
        # would raise an uncaught TypeError, and clone_opponent.clone_and_verify's own
        # repo_url.startswith(...) checks would raise an uncaught AttributeError for a
        # non-string repo_url (found by an independent heterogeneous-model audit).
        if (not isinstance(repo_url, str) or not repo_url
                or not isinstance(file_paths, (list, tuple)) or len(file_paths) != 2
                or not all(isinstance(p, str) and p for p in file_paths)
                or not isinstance(commit_sha, str) or not commit_sha):
            raise ValueError(
                f"opponent {opponent_id!r}: opponent_pins.json entry incomplete, missing, or "
                f"malformed (needs a non-empty string commit_sha, a non-empty string repo_url, "
                f"and exactly 2 non-empty string file_paths: agent, deck) -- drop it from "
                f"--opponent or add a valid pin first"
            )
        dest_dir = tempfile.mkdtemp(prefix=f"eval_infra_manifest_clone_{opponent_id}_")
        try:
            clone_result = clone_opponent.clone_and_verify(
                opponent_id, repo_url, commit_sha, (file_paths[0], file_paths[1]), dest_dir,
            )
        except clone_opponent.ClonePinError as exc:
            raise ValueError(f"opponent {opponent_id!r}: clone_and_verify failed at manifest time: {exc}") from exc
        finally:
            shutil.rmtree(dest_dir, ignore_errors=True)
        return {
            "opponent_id": opponent_id, "source_kind": "pinned_clone",
            "repo_url": repo_url, "commit_sha": commit_sha,
            "files": [
                {"logical_name": "agent" if i == 0 else "deck", "path": cf.repo_relative_path, "sha256": cf.sha256}
                for i, cf in enumerate(clone_result.files)
            ],
        }

    raise ValueError(f"unknown opponent_id {opponent_id!r} (not mirror, not a known local_only "
                      f"or pinned_clone opponent)")


# The single, fixed mapping from opponent_id to the source_kind that opponent_id is REQUIRED
# to use -- never inferred from whatever source_kind a binding happens to claim.
_CANONICAL_OPPONENT_SOURCE_KIND = {
    opponent_registry.MIRROR_OPPONENT_ID: "self_play",
    **{opp_id: "local_only" for opp_id in opponent_registry.LOCAL_ONLY_OPPONENTS},
    **{opp_id: "pinned_clone" for opp_id in opponent_registry.PINNED_CLONE_OPPONENTS},
}


def _verify_opponent_binding_canonical(binding: dict) -> str | None:
    """Validates that ONE selected-opponent binding matches the canonical shape its
    opponent_id is required to have -- not merely that the manifest's own hash is
    self-consistent (_verify_manifest_integrity's hash checks only prove a binding wasn't
    edited AFTER `manifest` wrote it; they say nothing about whether the binding's CONTENT is
    semantically valid for that opponent_id, since a hand-forged manifest, never built via the
    `manifest` CLI, can freely choose both and recompute a matching hash).

    Without this check, a forged manifest could set source_kind="self_play" for EVERY
    opponent_id -- including lucario/dragapult/megastarmie -- with a correctly recomputed
    dataset_identity hash, so a mirror-only self-play run would appear to have all 3 required
    league opponents "selected" and become eligible for report_kind="primary" (found by an
    independent external review). `_resolve_opponent_paths_at_run_time` dispatches purely on
    source_kind, so such a binding would actually run (and label its output as) a self-play
    game under the required opponent's name.

    Called for every entry in dataset_identity.selected_opponents, by both `run` and
    `summarize` (via _verify_manifest_integrity), before league_complete or anything else is
    computed from selected_opponents. Returns an error string on any mismatch, else None."""
    if not isinstance(binding, dict):
        return f"selected_opponents entry is not an object, got {binding!r}"
    opponent_id = binding.get("opponent_id")
    source_kind = binding.get("source_kind")
    # opponent_id must be a hashable string BEFORE it is ever used as a dict key below --
    # a JSON array/object value here would otherwise raise an uncaught
    # `TypeError: unhashable type` from the dict .get() lookup instead of a controlled
    # rejection (found by an independent heterogeneous-model audit).
    if not isinstance(opponent_id, str):
        return f"selected_opponents entry has a non-string opponent_id, got {opponent_id!r}"
    expected_kind = _CANONICAL_OPPONENT_SOURCE_KIND.get(opponent_id)
    if expected_kind is None:
        return (f"selected_opponents entry has unknown opponent_id {opponent_id!r} (not "
                f"mirror, not a known local_only or pinned_clone opponent) -- rejected, "
                f"never silently accepted")
    if source_kind != expected_kind:
        return (f"opponent {opponent_id!r} binding has source_kind={source_kind!r}, but the "
                f"canonical mapping for {opponent_id!r} requires source_kind={expected_kind!r} "
                f"-- a binding claiming a different kind (e.g. a required league opponent "
                f"disguised as self_play so it runs a mirror game under that opponent's name) "
                f"is never accepted")

    if opponent_id == opponent_registry.MIRROR_OPPONENT_ID:
        extra = set(binding) - {"opponent_id", "source_kind"}
        if extra:
            return (f"mirror binding has unexpected extra field(s) {sorted(extra)} -- a "
                     f"mirror binding must be exactly {{opponent_id, source_kind}}, nothing "
                     f"claiming a repo_url/commit_sha/files")
        return None

    if opponent_id in opponent_registry.LOCAL_ONLY_OPPONENTS:
        extra = set(binding) - {"opponent_id", "source_kind", "files"}
        if extra:
            return f"{opponent_id!r} binding has unexpected extra field(s) {sorted(extra)}"
        files_error, by_name = _verify_opponent_files_canonical(opponent_id, binding.get("files"))
        if files_error:
            return files_error
        expected_paths = opponent_registry.LOCAL_ONLY_OPPONENTS[opponent_id]
        if by_name["agent"]["path"] != expected_paths["agent_path"]:
            return (f"{opponent_id!r} binding's agent file path "
                     f"{by_name['agent']['path']!r} does not match the canonical "
                     f"local_only path {expected_paths['agent_path']!r}")
        if by_name["deck"]["path"] != expected_paths["deck_path"]:
            return (f"{opponent_id!r} binding's deck file path "
                     f"{by_name['deck']['path']!r} does not match the canonical "
                     f"local_only path {expected_paths['deck_path']!r}")
        return None

    if opponent_id in opponent_registry.PINNED_CLONE_OPPONENTS:
        extra = set(binding) - {"opponent_id", "source_kind", "repo_url", "commit_sha", "files"}
        if extra:
            return f"{opponent_id!r} binding has unexpected extra field(s) {sorted(extra)}"
        repo_url = binding.get("repo_url")
        commit_sha = binding.get("commit_sha")
        if not isinstance(repo_url, str) or not repo_url:
            return f"{opponent_id!r} (pinned_clone) binding is missing a non-empty repo_url"
        if not isinstance(commit_sha, str) or len(commit_sha) != 40 or not all(c in "0123456789abcdef" for c in commit_sha):
            return (f"{opponent_id!r} (pinned_clone) binding's commit_sha must be exactly "
                     f"40 lowercase hex chars, got {commit_sha!r}")
        files_error, _by_name = _verify_opponent_files_canonical(opponent_id, binding.get("files"))
        if files_error:
            return files_error
        return None

    # Unreachable given the expected_kind lookup above, but fail closed rather than silently
    # accept an opponent_id this function has no canonical shape rule for.
    return f"opponent {opponent_id!r}: no canonical binding-shape rule defined"


def _verify_opponent_files_canonical(opponent_id: str, files) -> tuple[str | None, dict | None]:
    """Shared per-file validation for a local_only/pinned_clone opponent binding's "files"
    list: exactly 2 entries, logical_name exactly {agent, deck}, each entry has EXACTLY
    {logical_name, path, sha256} (no smuggled extra per-file field), sha256 is 64 lowercase
    hex, and path is repo-relative and safe (no "..", no absolute/drive-letter/backslash
    escape) -- an earlier version accepted a pinned-clone path like "../outside.py" and never
    checked for extra per-file fields, both found by an independent heterogeneous-model audit.
    Returns (error_or_None, {"agent": file_dict, "deck": file_dict} or None)."""
    if not isinstance(files, list) or len(files) != 2:
        return (f"{opponent_id!r} binding must have exactly 2 'files' entries (agent, deck), "
                f"got {files!r}"), None
    if not all(isinstance(f, dict) for f in files):
        return f"{opponent_id!r} binding's 'files' entries must each be an object", None
    _required_file_keys = {"logical_name", "path", "sha256"}
    for f in files:
        # Exact key-set equality, not just "no extras" -- an earlier version only checked
        # `set(f) - _required_file_keys`, which is empty for a MISSING key too (a subset check
        # passes trivially), so a file entry with e.g. only {path, sha256} (no logical_name)
        # passed this check and then crashed with an uncaught KeyError at `f["logical_name"]"
        # below -- found by an independent heterogeneous-model audit via direct reproduction.
        if set(f) != _required_file_keys:
            return (f"{opponent_id!r} binding has a 'files' entry whose keys are "
                     f"{sorted(f)!r}, expected exactly {sorted(_required_file_keys)!r} "
                     f"(missing and/or extra field(s))"), None
        sha = f.get("sha256")
        if not isinstance(sha, str) or len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha):
            return f"{opponent_id!r} binding's file sha256 must be exactly 64 lowercase hex chars, got {sha!r}", None
        path = f.get("path")
        if not isinstance(path, str) or not path:
            return f"{opponent_id!r} binding has a 'files' entry with a missing/empty path", None
        if ".." in path or path.startswith("/") or "\\" in path or (len(path) >= 2 and path[1] == ":"):
            return (f"{opponent_id!r} binding's file path {path!r} is unsafe (contains '..', "
                     f"is absolute, or uses a drive-letter/backslash) -- only a bare "
                     f"repo-relative path is ever accepted"), None
        # logical_name must be a hashable string BEFORE it is ever used as a dict key below --
        # a JSON array/object value here (e.g. {"logical_name": [], ...}) would otherwise raise
        # an uncaught `TypeError: unhashable type` from the dict-comprehension below instead of
        # a controlled rejection (found by an independent heterogeneous-model audit).
        logical_name = f.get("logical_name")
        if not isinstance(logical_name, str) or logical_name not in ("agent", "deck"):
            return (f"{opponent_id!r} binding has a 'files' entry with logical_name "
                     f"{logical_name!r}, expected exactly 'agent' or 'deck'"), None
    by_name = {f["logical_name"]: f for f in files}
    if set(by_name) != {"agent", "deck"}:
        return (f"{opponent_id!r} binding's files must have logical_name 'agent' and 'deck' "
                 f"exactly, got {sorted(by_name)}"), None
    return None, by_name


def _resolve_opponent_paths_at_run_time(binding: dict, clone_dest_root: str) -> tuple[str | None, str | None]:
    """Given one manifest-frozen opponent binding, re-verify it against disk
    (local_only) or re-clone+re-verify it (pinned_clone) and return absolute
    (agent_path, deck_path). Returns (None, None) for self_play (mirror) --
    the caller substitutes the arm's own artifact in that case. Raises
    ValueError if the binding no longer matches what the manifest recorded
    -- `run` must fail closed on drift, never silently proceed with content
    that differs from what comparison_manifest_sha256 identifies."""
    source_kind = binding.get("source_kind")
    opponent_id = binding["opponent_id"]

    if source_kind == "self_play":
        return None, None

    if source_kind == "local_only":
        files = {f["logical_name"]: f for f in binding["files"]}
        for f in files.values():
            abs_path = _abs_repo_path(f["path"])
            if not os.path.isfile(abs_path):
                raise ValueError(f"opponent {opponent_id!r} file {f['path']!r} (local_only) is "
                                  f"missing at run time (was present at manifest time)")
            actual = _hash_file(abs_path)
            if actual != f["sha256"]:
                raise ValueError(f"opponent {opponent_id!r} file {f['path']!r} changed since "
                                  f"manifest was written (sha256 mismatch)")
        return _abs_repo_path(files["agent"]["path"]), _abs_repo_path(files["deck"]["path"])

    if source_kind == "pinned_clone":
        files = {f["logical_name"]: f for f in binding["files"]}
        dest_dir = os.path.join(clone_dest_root, opponent_id)
        try:
            clone_result = clone_opponent.clone_and_verify(
                opponent_id, binding["repo_url"], binding["commit_sha"],
                (files["agent"]["path"], files["deck"]["path"]), dest_dir,
            )
        except clone_opponent.ClonePinError as exc:
            raise ValueError(f"opponent {opponent_id!r}: re-clone at run time failed: {exc}") from exc
        actual_by_path = {cf.repo_relative_path: cf for cf in clone_result.files}
        for logical_name, f in files.items():
            cf = actual_by_path.get(f["path"])
            if cf is None or cf.sha256 != f["sha256"]:
                raise ValueError(f"opponent {opponent_id!r} file {f['path']!r} changed since "
                                  f"manifest was written (sha256 mismatch at re-clone)")
        return actual_by_path[files["agent"]["path"]].absolute_path, actual_by_path[files["deck"]["path"]].absolute_path

    raise ValueError(f"opponent {opponent_id!r}: unknown source_kind {source_kind!r} in manifest binding")


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------

def cmd_manifest(args: argparse.Namespace) -> int:
    if os.path.exists(args.out):
        print(f"ERROR: refusing to overwrite existing manifest file: {args.out}", file=sys.stderr)
        return 1
    if args.games_per_segment < 1:
        print(f"ERROR: --games-per-segment must be >= 1, got {args.games_per_segment}", file=sys.stderr)
        return 1
    if not math.isfinite(args.wall_timeout_seconds) or args.wall_timeout_seconds <= 0:
        print(f"ERROR: --wall-timeout-seconds must be finite and > 0, got {args.wall_timeout_seconds}", file=sys.stderr)
        return 1
    if not args.opponent:
        print("ERROR: at least one --opponent is required", file=sys.stderr)
        return 1
    if len(set(args.opponent)) != len(args.opponent):
        print(f"ERROR: --opponent list contains duplicates: {args.opponent}", file=sys.stderr)
        return 1
    # `run`/`summarize` both require protocol_identity.id / dataset_identity.id /
    # candidate_artifact.artifact_id / baseline_artifact.artifact_id to be non-empty strings
    # (see _verify_manifest_integrity) -- validating that HERE, before writing the file, means
    # `manifest` can never succeed and write a file its own `run` immediately rejects on the
    # very next invocation (found by an independent heterogeneous-model audit).
    for _id_flag, _id_value in (
        ("--protocol-id", args.protocol_id), ("--dataset-id", args.dataset_id),
        ("--candidate-artifact-id", args.candidate_artifact_id),
        ("--baseline-artifact-id", args.baseline_artifact_id),
    ):
        if not isinstance(_id_value, str) or not _id_value:
            print(f"ERROR: {_id_flag} must be a non-empty string, got {_id_value!r}", file=sys.stderr)
            return 1
    # Statistical measurement settings are fixed HERE, at manifest-creation time, and hashed
    # into protocol_identity/comparison_manifest_sha256 -- `summarize` reads them back from the
    # manifest and has no flags of its own to set them. An earlier version let `summarize`
    # accept --confidence-level/--bootstrap-replicates/--rng-seed as free caller-time choices,
    # so the SAME comparison_manifest_sha256 could produce Measurement Reports with different
    # confidence intervals depending purely on what the `summarize` caller happened to pass --
    # found by an independent external review.
    try:
        confidence_level_decimal = Decimal(args.confidence_level)
        if not (Decimal("0") < confidence_level_decimal < Decimal("1")):
            raise ValueError(f"--confidence-level must be strictly between 0 and 1, got {args.confidence_level!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: invalid --confidence-level: {exc}", file=sys.stderr)
        return 1
    if args.bootstrap_replicates < 1:
        print("ERROR: --bootstrap-replicates must be >= 1", file=sys.stderr)
        return 1

    try:
        candidate = _artifact_binding(
            args.candidate_artifact_id, args.candidate_agent, args.candidate_deck, args.candidate_params
        )
        baseline = _artifact_binding(
            args.baseline_artifact_id, args.baseline_agent, args.baseline_deck, args.baseline_params
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if candidate["sha256"] == baseline["sha256"]:
        print("ERROR: candidate and baseline artifacts are byte-identical; refusing to "
              "produce a manifest that would compare an artifact against itself.", file=sys.stderr)
        return 1

    try:
        pins = opponent_registry.load_pins(_PINS_PATH)
    except ValueError as exc:
        # A malformed opponent_pins.json (unparseable JSON, or valid JSON that isn't an
        # object) must fail the same controlled way every other manifest-creation problem
        # here does -- an earlier version let this propagate straight out of `manifest`
        # entirely instead of the "ERROR: ..." + exit 1 pattern used everywhere else in this
        # function (found by an independent heterogeneous-model audit).
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    selected_opponents = []
    for opponent_id in args.opponent:
        try:
            selected_opponents.append(_resolve_opponent_binding(opponent_id, pins))
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    # Sorted by opponent_id (the canonical key) so dataset_identity's hash -- and therefore
    # comparison_manifest_sha256 -- depends only on the SET of selected opponents, never on
    # the order --opponent happened to be given on the command line (found by an independent
    # external review: the same opponent set specified in a different --opponent order would
    # otherwise hash differently, meaning two functionally-identical manifests wouldn't be
    # recognized as identical).
    selected_opponents.sort(key=lambda binding: binding["opponent_id"])

    league_complete = set(schema.REQUIRED_LEAGUE_OPPONENTS) <= set(args.opponent)
    side_allocation_schedule = ["a" if i % 2 == 0 else "b" for i in range(args.games_per_segment)]

    protocol_identity = {
        "id": args.protocol_id,
        "step_limit": 2000,
        "games_per_worker": 1,  # forced -- seat alternation is unimplemented for >1 (see README F3)
        "wall_timeout_seconds": str(args.wall_timeout_seconds),
        "games_per_segment": args.games_per_segment,
        "side_allocation_schedule": side_allocation_schedule,
        "worker_model": _ACTUAL_WORKER_MODEL,
        "decision_time_measurement": _ACTUAL_DECISION_TIME_MEASUREMENT,
        "game_rng_control": _ACTUAL_GAME_RNG_CONTROL,
        "engine_binding": _engine_binding(),
        "evaluator_binding": _evaluator_binding(),
        "runtime_environment": _runtime_environment(),
        "measurement_settings": {
            "confidence_level": str(confidence_level_decimal),
            "bootstrap_replicates": args.bootstrap_replicates,
            "rate_interval_method": _RATE_INTERVAL_METHOD,
            "rate_delta_method": _RATE_DELTA_METHOD,
            "latency_bootstrap_method": _LATENCY_BOOTSTRAP_METHOD,
            "bootstrap_seed_scheme": _BOOTSTRAP_SEED_SCHEME,
        },
    }
    dataset_identity = {
        "id": args.dataset_id,
        "version": args.dataset_version,
        "selected_opponents": selected_opponents,
        "league_complete": league_complete,
    }
    protocol_sha256 = sha256_hex(protocol_identity)
    dataset_sha256 = sha256_hex(dataset_identity)

    manifest = {
        "schema_version": "2",
        "stage": args.stage,
        "candidate_role": args.candidate_role,
        "protocol_identity": {**protocol_identity, "sha256": protocol_sha256},
        "dataset_identity": {**dataset_identity, "sha256": dataset_sha256},
        "candidate_artifact": candidate,
        "baseline_artifact": baseline,
    }
    comparison_identity = {
        "schema_version": manifest["schema_version"],
        "candidate_role": manifest["candidate_role"],
        "dataset_sha256": dataset_sha256,
        "protocol_sha256": protocol_sha256,
        "candidate_artifact": {"artifact_id": candidate["artifact_id"], "sha256": candidate["sha256"]},
        "baseline_artifact": {"artifact_id": baseline["artifact_id"], "sha256": baseline["sha256"]},
        "stage": args.stage,
    }
    manifest["comparison_manifest_sha256"] = sha256_hex(comparison_identity)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True, ensure_ascii=False)
    print(f"Wrote manifest to {args.out} (comparison_manifest_sha256={manifest['comparison_manifest_sha256'][:12]}..., "
          f"opponents={args.opponent}, league_complete={league_complete})")
    return 0


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------

def _manifest_hash8(manifest: dict) -> str:
    """Short form for display/log messages and the (non-security-relevant)
    run_index.json filename ONLY -- see _jsonl_filename for why per-game
    output files use the full hash instead."""
    return manifest["comparison_manifest_sha256"][:8]


def _manifest_hash_full(manifest: dict) -> str:
    return manifest["comparison_manifest_sha256"]


def _jsonl_filename(manifest: dict, opponent_id: str, arm: str) -> str:
    return f"{_manifest_hash_full(manifest)}__{opponent_id}__{arm}.jsonl"


def _verify_manifest_integrity(manifest: dict) -> str | None:
    """Recompute protocol_identity/dataset_identity/comparison_manifest_sha256 from the
    manifest's OWN stored fields (mirroring cmd_manifest's exact construction) and confirm
    they match the manifest's own stored hashes. Catches a hand-edited manifest -- e.g. a
    selected opponent's binding or games_per_segment changed in the JSON file after
    `manifest` wrote it -- whose content no longer matches what comparison_manifest_sha256
    claims to identify. Both `run` and `summarize` call this before trusting anything else in
    the manifest. Returns an error string on any mismatch, else None."""
    if not isinstance(manifest, dict):
        return f"manifest is not an object, got {manifest!r}"
    # protocol_identity/dataset_identity must be validated as dicts BEFORE the `dict(...)`
    # coercion below -- `dict()` happily accepts a JSON array of [key, value] pairs without
    # raising, so a forged (yet hash-consistent, since hashing a JSON value doesn't require it
    # to be a dict) manifest with e.g. protocol_identity=[["sha256","..."],...] would pass this
    # coercion, then crash later with an uncaught TypeError ("list indices must be integers")
    # on the first direct string-key access, instead of a controlled rejection (found by an
    # independent heterogeneous-model audit).
    raw_protocol_identity = manifest.get("protocol_identity")
    if not isinstance(raw_protocol_identity, dict):
        return f"protocol_identity is missing or not an object, got {raw_protocol_identity!r}"
    raw_dataset_identity = manifest.get("dataset_identity")
    if not isinstance(raw_dataset_identity, dict):
        return f"dataset_identity is missing or not an object, got {raw_dataset_identity!r}"
    # manifest["stage"] is read via direct indexing by both `run` and `summarize` (e.g.
    # `summarize` compares args.stage != manifest["stage"] before opening any jsonl file) -- it
    # was never required to be present/valid here, so a forged manifest omitting "stage"
    # entirely would pass every hash check (comparison_identity hashes manifest.get("stage"),
    # which is None either way) and then crash with an uncaught KeyError at the very first
    # direct-index read, instead of a controlled rejection (found by an independent same-model
    # audit).
    if manifest.get("stage") not in ("screening", "confirmation"):
        return f"manifest.stage must be 'screening' or 'confirmation', got {manifest.get('stage')!r}"
    # schema_version/candidate_role are hashed into comparison_manifest_sha256 via
    # comparison_identity (below) but were never otherwise validated here -- a forged manifest
    # could set either to an arbitrary value (or omit schema_version/candidate_role entirely,
    # since comparison_identity uses manifest.get(...)) and `summarize` would copy both
    # verbatim into its report with no semantic check, e.g. candidate_role=[] or
    # schema_version=null appearing in a report that is otherwise accepted as report_kind
    # "primary" (found by an independent heterogeneous-model audit).
    if manifest.get("schema_version") != "2":
        return f"manifest.schema_version must be '2', got {manifest.get('schema_version')!r}"
    if manifest.get("candidate_role") not in ("primary", "fallback"):
        return (f"manifest.candidate_role must be 'primary' or 'fallback', got "
                f"{manifest.get('candidate_role')!r}")
    protocol_identity = dict(raw_protocol_identity)
    stored_protocol_sha256 = protocol_identity.pop("sha256", None)
    recomputed_protocol_sha256 = sha256_hex(protocol_identity)
    if recomputed_protocol_sha256 != stored_protocol_sha256:
        return (f"protocol_identity hash mismatch: manifest claims {stored_protocol_sha256!r}, "
                f"recomputed {recomputed_protocol_sha256!r} -- protocol_identity (e.g. "
                f"games_per_segment/side_allocation_schedule/engine_binding) was edited after "
                f"`manifest` wrote this file")

    # A manifest built without going through the `manifest` CLI (which rejects
    # --games-per-segment < 1 at creation time) could still be internally hash-consistent with
    # games_per_segment=0 and an empty side_allocation_schedule -- with no league opponents and
    # no jsonl inputs required, summarize's completeness check would trivially treat "0 records
    # expected, 0 records present" as complete and emit a zero-observation report_kind="primary"
    # with no actual evidence (found by an independent heterogeneous-model audit). Reject
    # unsound games_per_segment/side_allocation_schedule combinations here so this is caught
    # before `run` or `summarize` trusts anything else in the manifest.
    games_per_segment = protocol_identity.get("games_per_segment")
    if not isinstance(games_per_segment, int) or isinstance(games_per_segment, bool) or games_per_segment < 1:
        return (f"protocol_identity.games_per_segment={games_per_segment!r} is not a positive "
                f"integer -- a manifest must specify at least 1 game per segment")
    expected_schedule = ["a" if i % 2 == 0 else "b" for i in range(games_per_segment)]
    if protocol_identity.get("side_allocation_schedule") != expected_schedule:
        return (f"protocol_identity.side_allocation_schedule="
                f"{protocol_identity.get('side_allocation_schedule')!r} does not match the "
                f"deterministic alternating sequence `manifest` always computes for "
                f"games_per_segment={games_per_segment} ({expected_schedule!r})")

    if protocol_identity.get("step_limit") != _ACTUAL_STEP_LIMIT:
        return (f"protocol_identity.step_limit={protocol_identity.get('step_limit')!r} does not "
                f"match the actual hardcoded engine step limit ({_ACTUAL_STEP_LIMIT}) in "
                f"experiments/head_to_head.py -- this manifest claims a step limit that `run` "
                f"cannot actually enforce")
    # bool is a subclass of int and _ACTUAL_GAMES_PER_WORKER == 1, so an unguarded `!=`
    # comparison would silently accept games_per_worker=True as equal to the required value
    # (found by an independent heterogeneous-model audit).
    _games_per_worker_claim = protocol_identity.get("games_per_worker")
    if isinstance(_games_per_worker_claim, bool) or _games_per_worker_claim != _ACTUAL_GAMES_PER_WORKER:
        return (f"protocol_identity.games_per_worker={_games_per_worker_claim!r} "
                f"does not match the actual value `run` always uses "
                f"({_ACTUAL_GAMES_PER_WORKER}) -- this manifest claims a games_per_worker that "
                f"`run` cannot actually enforce")
    # worker_model/decision_time_measurement/game_rng_control are fixed, self-documenting
    # claims about how this harness actually operates -- recorded into every manifest but,
    # until now, never re-verified against the ACTUAL fixed values, so a forged (yet
    # hash-consistent) manifest could claim a different worker_model/measurement
    # methodology/RNG-control status with nothing catching the discrepancy before `summarize`
    # copies whichever claim the manifest makes verbatim into its report (found by an
    # independent heterogeneous-model audit).
    if protocol_identity.get("worker_model") != _ACTUAL_WORKER_MODEL:
        return (f"protocol_identity.worker_model={protocol_identity.get('worker_model')!r} does "
                f"not match the actual fixed value ({_ACTUAL_WORKER_MODEL!r})")
    if protocol_identity.get("decision_time_measurement") != _ACTUAL_DECISION_TIME_MEASUREMENT:
        return (f"protocol_identity.decision_time_measurement does not match the actual fixed "
                f"value this harness uses")
    if protocol_identity.get("game_rng_control") != _ACTUAL_GAME_RNG_CONTROL:
        return (f"protocol_identity.game_rng_control does not match the actual fixed value "
                f"this harness uses")

    # wall_timeout_seconds is stored as a string (see cmd_manifest: str(args.wall_timeout_seconds))
    # and `run` later does float(manifest[...]["wall_timeout_seconds"]) before passing it to
    # subprocess.run(timeout=...) -- a forged (yet hash-consistent) non-numeric-string or
    # non-string value here (e.g. a JSON array) would otherwise raise an uncaught TypeError
    # from float() at that point instead of a controlled rejection here (found by an
    # independent heterogeneous-model audit).
    wall_timeout_seconds_raw = protocol_identity.get("wall_timeout_seconds")
    if not isinstance(wall_timeout_seconds_raw, str):
        return (f"protocol_identity.wall_timeout_seconds={wall_timeout_seconds_raw!r} is not a "
                f"string (it must be the str() form of a finite positive number)")
    try:
        wall_timeout_seconds_check = float(wall_timeout_seconds_raw)
    except ValueError:
        return (f"protocol_identity.wall_timeout_seconds={wall_timeout_seconds_raw!r} is not "
                f"parseable as a number")
    if not math.isfinite(wall_timeout_seconds_check) or wall_timeout_seconds_check <= 0:
        return (f"protocol_identity.wall_timeout_seconds={wall_timeout_seconds_raw!r} must be "
                f"finite and > 0")

    # protocol_identity.id / dataset_identity.id are read via direct manifest[...]["id"]
    # indexing by both `run` and `summarize` (e.g. to name jsonl output files) -- neither was
    # ever required to be present here, so a forged (yet hash-consistent) manifest omitting
    # either "id" field would pass every check above and then crash with an uncaught KeyError
    # at the first direct-index read, instead of a controlled rejection (found by an
    # independent same-model audit).
    if not isinstance(protocol_identity.get("id"), str) or not protocol_identity["id"]:
        return f"protocol_identity.id must be a non-empty string, got {protocol_identity.get('id')!r}"
    if not isinstance(raw_dataset_identity.get("id"), str) or not raw_dataset_identity["id"]:
        return f"dataset_identity.id must be a non-empty string, got {raw_dataset_identity.get('id')!r}"

    # engine_binding/evaluator_binding/runtime_environment are read via direct
    # manifest["protocol_identity"]["engine_binding"]-style indexing in
    # _verify_execution_bindings_unchanged (which always runs AFTER this function). The
    # isinstance(dict) checks added there catch a PRESENT-but-wrong-type value, but the direct
    # index itself raises an uncaught KeyError if the key is MISSING entirely -- that happens
    # before those isinstance checks ever get a chance to run. Requiring all three to be
    # present dicts here closes that gap (found by an independent heterogeneous-model audit).
    for _binding_field in ("engine_binding", "evaluator_binding", "runtime_environment"):
        if not isinstance(protocol_identity.get(_binding_field), dict):
            return (f"protocol_identity.{_binding_field} is missing or not an object, got "
                    f"{protocol_identity.get(_binding_field)!r}")

    # measurement_settings must be semantically valid, not merely present with SOME
    # self-consistent value -- `summarize` trusts these fields directly (no CLI flags of its
    # own to override or re-validate them), so a hand-forged manifest with e.g.
    # bootstrap_replicates=-5 or confidence_level="not-a-number" must be rejected HERE, before
    # `summarize` ever tries to use it.
    measurement_settings = protocol_identity.get("measurement_settings")
    if not isinstance(measurement_settings, dict):
        return "protocol_identity.measurement_settings is missing or not an object"
    _expected_measurement_setting_keys = {
        "confidence_level", "bootstrap_replicates", "rate_interval_method",
        "rate_delta_method", "latency_bootstrap_method", "bootstrap_seed_scheme",
    }
    _extra_measurement_keys = set(measurement_settings) - _expected_measurement_setting_keys
    if _extra_measurement_keys:
        return (f"protocol_identity.measurement_settings has unexpected extra field(s) "
                f"{sorted(_extra_measurement_keys)} -- e.g. a smuggled-back 'rng_seed' would "
                f"be copied verbatim into the report while its own bootstrap_seed_scheme "
                f"claims no caller-supplied seed exists; only the exact fixed key set is ever "
                f"accepted")
    try:
        confidence_level_check = Decimal(str(measurement_settings.get("confidence_level")))
        if not (Decimal("0") < confidence_level_check < Decimal("1")):
            raise ValueError("out of range")
    except Exception:  # noqa: BLE001
        return (f"protocol_identity.measurement_settings.confidence_level="
                f"{measurement_settings.get('confidence_level')!r} is not a valid confidence "
                f"level strictly between 0 and 1")
    replicates_check = measurement_settings.get("bootstrap_replicates")
    if not isinstance(replicates_check, int) or isinstance(replicates_check, bool) or replicates_check < 1:
        return (f"protocol_identity.measurement_settings.bootstrap_replicates="
                f"{replicates_check!r} is not a positive integer")
    for method_field, expected_method in (
        ("rate_interval_method", _RATE_INTERVAL_METHOD),
        ("rate_delta_method", _RATE_DELTA_METHOD),
        ("latency_bootstrap_method", _LATENCY_BOOTSTRAP_METHOD),
        ("bootstrap_seed_scheme", _BOOTSTRAP_SEED_SCHEME),
    ):
        if measurement_settings.get(method_field) != expected_method:
            return (f"protocol_identity.measurement_settings.{method_field}="
                    f"{measurement_settings.get(method_field)!r} does not match the actual "
                    f"method this harness's code implements ({expected_method!r}) -- this "
                    f"manifest claims a method `summarize` does not actually use")

    dataset_identity = dict(raw_dataset_identity)
    stored_dataset_sha256 = dataset_identity.pop("sha256", None)
    recomputed_dataset_sha256 = sha256_hex(dataset_identity)
    if recomputed_dataset_sha256 != stored_dataset_sha256:
        return (f"dataset_identity hash mismatch: manifest claims {stored_dataset_sha256!r}, "
                f"recomputed {recomputed_dataset_sha256!r} -- dataset_identity (e.g. "
                f"selected_opponents) was edited after `manifest` wrote this file")

    # Hash self-consistency alone does not prove selected_opponents' CONTENT is semantically
    # valid -- a hand-forged manifest could set source_kind="self_play" for lucario/dragapult/
    # megastarmie too, with a correctly recomputed dataset_identity hash. Reject any binding
    # whose source_kind doesn't match its opponent_id's fixed canonical mapping (or whose
    # shape is otherwise wrong) before league_complete or anything else is computed from
    # selected_opponents.
    selected_opponents = dataset_identity.get("selected_opponents")
    if not isinstance(selected_opponents, list) or not selected_opponents:
        return "dataset_identity.selected_opponents is missing, empty, or not a list"
    for binding in selected_opponents:
        binding_error = _verify_opponent_binding_canonical(binding)
        if binding_error:
            return f"selected_opponents binding invalid: {binding_error}"
    # Duplicate opponent_id entries and out-of-canonical-order entries are both rejected here
    # too -- `manifest` itself never produces either (duplicates are rejected at --opponent
    # parse time; the list is always sorted by opponent_id before hashing, see cmd_manifest),
    # so only a hand-forged manifest could contain them, and accepting either would let a
    # forged-but-hash-consistent manifest silently diverge from the canonical representation
    # this whole validation exists to enforce (found by an independent heterogeneous-model
    # audit).
    opponent_id_sequence = [b["opponent_id"] for b in selected_opponents]
    if len(set(opponent_id_sequence)) != len(opponent_id_sequence):
        return f"dataset_identity.selected_opponents contains duplicate opponent_id entries: {opponent_id_sequence!r}"
    if opponent_id_sequence != sorted(opponent_id_sequence):
        return (f"dataset_identity.selected_opponents is not sorted by opponent_id -- got "
                f"{opponent_id_sequence!r}, expected {sorted(opponent_id_sequence)!r} "
                f"(`manifest` always stores this list in sorted order)")

    candidate = manifest.get("candidate_artifact", {})
    baseline = manifest.get("baseline_artifact", {})
    _artifact_required_top_keys = {"artifact_id", "sha256", "files"}
    _artifact_required_file_keys = {"logical_name", "path", "sha256"}
    for label, artifact in (("candidate_artifact", candidate), ("baseline_artifact", baseline)):
        if not isinstance(artifact, dict):
            return f"{label} is not an object, got {artifact!r}"
        # The artifact's top-level key set must be EXACT, not merely a superset check -- an
        # earlier version never validated this, so a forged manifest could smuggle an extra
        # top-level field (e.g. an absolute local filesystem path under some unrelated key
        # name) onto candidate_artifact/baseline_artifact with no effect on
        # comparison_manifest_sha256 (only artifact_id/sha256 are hashed into it, not the
        # object's full key set), and `summarize` copies the artifact object verbatim into its
        # report -- so that smuggled field would leak straight into the report's JSON (found by
        # an independent heterogeneous-model audit).
        if set(artifact) != _artifact_required_top_keys:
            return (f"{label} has keys {sorted(artifact)!r}, expected exactly "
                    f"{sorted(_artifact_required_top_keys)!r} (missing and/or extra field(s))")
        if not isinstance(artifact.get("artifact_id"), str) or not artifact["artifact_id"]:
            return f"{label}.artifact_id must be a non-empty string, got {artifact.get('artifact_id')!r}"
        artifact_files = artifact.get("files")
        if not isinstance(artifact_files, list) or not artifact_files:
            return f"{label}.files is missing, empty, or not a list"
        seen_logical_names = []
        for f in artifact_files:
            # Every file entry's shape/types must be validated BEFORE it is ever hashed
            # (below, via _artifact_bundle_sha256_from_files) or later resolved against disk
            # (in _verify_artifact_unchanged) -- a forged (yet hash-consistent, since hashing
            # a JSON value doesn't require correct types) entry with e.g. a missing key or a
            # non-string path would otherwise raise an uncaught KeyError/TypeError instead of
            # a controlled rejection (found by an independent heterogeneous-model audit, the
            # artifact-file analogue of the opponent-file validation gaps fixed earlier).
            if not isinstance(f, dict) or set(f) != _artifact_required_file_keys:
                return (f"{label} has a 'files' entry whose keys are "
                        f"{sorted(f) if isinstance(f, dict) else f!r}, expected exactly "
                        f"{sorted(_artifact_required_file_keys)!r}")
            if not isinstance(f["logical_name"], str) or f["logical_name"] not in ("agent", "deck", "params"):
                return (f"{label} has a 'files' entry with logical_name {f['logical_name']!r}, "
                        f"expected exactly 'agent', 'deck', or 'params'")
            if not isinstance(f["path"], str) or not f["path"]:
                return f"{label} has a 'files' entry with a missing/empty/non-string path"
            sha = f["sha256"]
            if not isinstance(sha, str) or len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha):
                return f"{label} file sha256 must be exactly 64 lowercase hex chars, got {sha!r}"
            seen_logical_names.append(f["logical_name"])
        # The SET of logical_names present must be canonical too -- {agent, deck}, optionally
        # plus params, each appearing exactly once -- so a binding can't e.g. omit "deck"
        # entirely (which would pass every per-file check above yet later crash
        # _artifact_file_path's dict lookup with a missing key, or silently resolve to no deck
        # at run time) or list "agent" twice (silently dropping the real deck's file entry).
        if len(set(seen_logical_names)) != len(seen_logical_names):
            return f"{label}.files contains duplicate logical_name entries: {seen_logical_names!r}"
        if not {"agent", "deck"} <= set(seen_logical_names):
            return (f"{label}.files logical_name set is {sorted(seen_logical_names)!r}, must "
                    f"include at least 'agent' and 'deck'")
        stored_bundle_sha256 = artifact.get("sha256")
        recomputed_bundle_sha256 = _artifact_bundle_sha256_from_files(artifact_files)
        if recomputed_bundle_sha256 != stored_bundle_sha256:
            return (f"{label} bundle sha256 mismatch: manifest claims {stored_bundle_sha256!r}, "
                    f"recomputed from its own 'files' list {recomputed_bundle_sha256!r} -- "
                    f"{label}.files (the individual file paths/hashes that comparison_manifest_sha256 "
                    f"actually binds) was edited without updating {label}.sha256 to match, e.g. a "
                    f"file's path and sha256 were both swapped to point at substituted content while "
                    f"leaving the top-level bundle sha256 untouched")
    comparison_identity = {
        "schema_version": manifest.get("schema_version"),
        "candidate_role": manifest.get("candidate_role"),
        "dataset_sha256": recomputed_dataset_sha256,
        "protocol_sha256": recomputed_protocol_sha256,
        "candidate_artifact": {"artifact_id": candidate.get("artifact_id"), "sha256": candidate.get("sha256")},
        "baseline_artifact": {"artifact_id": baseline.get("artifact_id"), "sha256": baseline.get("sha256")},
        "stage": manifest.get("stage"),
    }
    recomputed_comparison_sha256 = sha256_hex(comparison_identity)
    if recomputed_comparison_sha256 != manifest.get("comparison_manifest_sha256"):
        return (f"comparison_manifest_sha256 mismatch: manifest claims "
                f"{manifest.get('comparison_manifest_sha256')!r}, recomputed "
                f"{recomputed_comparison_sha256!r} -- this manifest file was edited after "
                f"`manifest` wrote it")
    return None


def _verify_artifact_unchanged(artifact: dict) -> str | None:
    """Rehash an artifact's individual files against the sha256 values recorded in the
    manifest at `manifest` time; returns an error string if any no longer match (the
    artifact changed on disk since manifest was created), else None.

    Also re-confines each stored path to the repository root (same check
    _resolve_repo_confined_artifact_path applies at manifest-creation time) before reading
    it. `manifest` only ever writes an already-confined repo-relative path, but this function
    is the gate `run` AND `summarize` actually trust before touching disk / embedding a path
    into a report -- a hand-edited (yet internally hash-consistent, i.e. a forged manifest
    never built via the `manifest` CLI) "files" entry with an escaping path (e.g.
    "../../../etc/passwd", with its "sha256" edited to match) must not be silently read just
    because its own hash is locally self-consistent.

    Containment alone is not enough: a forged "files" entry could store a repo-INTERNAL
    ABSOLUTE path (e.g. "C:\\...\\repo\\main.py" instead of "main.py") with a correspondingly
    recomputed sha256/bundle hash -- fully contained, fully hash-consistent, but not the
    canonical repo-relative POSIX form `manifest` always writes. `summarize` copies an
    artifact's "files" verbatim into its report, so that absolute path would leak into the
    report's JSON (found by an independent heterogeneous-model audit). Requiring the stored
    path to equal the canonical form recomputed from where it actually resolves closes this:
    only the exact string `manifest` itself would have written is ever accepted."""
    real_repo_root = os.path.realpath(_REPO_ROOT)
    files = artifact.get("files", [])
    if not isinstance(files, list):
        return f"artifact {artifact.get('artifact_id')!r} 'files' is not a list, got {files!r}"
    for f in files:
        # Every file entry's shape/types must be validated BEFORE `f["path"]` is ever passed
        # to os.path-based resolution below -- a forged (yet hash-consistent, since hashing a
        # JSON value doesn't require it to be a string) "files" entry with e.g. path=[] would
        # otherwise raise an uncaught TypeError ("expected str, bytes or os.PathLike object,
        # not list") instead of a controlled rejection (found by an independent
        # heterogeneous-model audit).
        if (not isinstance(f, dict) or not isinstance(f.get("path"), str) or not f["path"]
                or not isinstance(f.get("sha256"), str)):
            return (f"artifact {artifact.get('artifact_id')!r} has a 'files' entry that is not "
                    f"an object with a non-empty string 'path' and a string 'sha256', got {f!r}")
        try:
            abs_path = _confine_to_repo_root(_abs_repo_path(f["path"]), f["path"])
        except ValueError as exc:
            return f"artifact {artifact['artifact_id']!r} file {f['path']!r}: {exc}"
        canonical_path = os.path.relpath(abs_path, real_repo_root).replace(os.sep, "/")
        if f["path"] != canonical_path:
            return (f"artifact {artifact['artifact_id']!r} file {f['path']!r} is not in the "
                    f"canonical repo-relative POSIX form `manifest` writes (expected "
                    f"{canonical_path!r}) -- e.g. an absolute-but-repo-internal path, a "
                    f"non-normalized path, or backslash separators; only the exact form "
                    f"`manifest` itself produces is ever accepted, to guarantee no local "
                    f"absolute path can be embedded into a report")
        if not os.path.isfile(abs_path):
            return f"artifact {artifact['artifact_id']!r} file {f['path']!r} is missing at run time"
        actual = _hash_file(abs_path)
        if actual != f["sha256"]:
            return (f"artifact {artifact['artifact_id']!r} file {f['path']!r} sha256 mismatch: "
                    f"manifest recorded {f['sha256'][:12]}..., current file hashes to "
                    f"{actual[:12]}... (file changed since `manifest` was written)")
    return None


def _count_lines(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def _read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _reject_json_constant(token: str) -> None:
    raise ValueError(
        f"manifest contains a non-finite JSON numeric token {token!r} -- NaN/Infinity/"
        f"-Infinity are never accepted anywhere in a manifest"
    )


def _load_manifest(path: str) -> tuple[dict | None, str | None]:
    """The single point every manifest is parsed from disk through. Python's json.load
    accepts the non-standard NaN/Infinity/-Infinity tokens by default (parse_constant is None),
    even though canon.sha256_hex's own json.dumps(..., allow_nan=False) rejects them -- so a
    forged manifest smuggling one of these tokens into e.g. protocol_identity would pass
    json.load silently and then raise an uncaught ValueError the moment
    _verify_manifest_integrity tries to hash that block, before any of its own field-by-field
    validation ever runs (found by an independent same-model audit). parse_constant here
    rejects all three tokens outright, with a controlled error, at parse time -- before
    anything downstream ever sees them."""
    try:
        with open(path, encoding="utf-8") as f:
            manifest = json.load(f, parse_constant=_reject_json_constant)
    except (OSError, ValueError) as exc:
        return None, f"failed to load manifest {path!r}: {exc}"
    return manifest, None


def cmd_run(args: argparse.Namespace) -> int:
    manifest, load_error = _load_manifest(args.manifest)
    if load_error:
        print(f"ERROR: {load_error}", file=sys.stderr)
        return 1

    integrity_error = _verify_manifest_integrity(manifest)
    if integrity_error:
        print(f"ERROR: {integrity_error}", file=sys.stderr)
        return 1

    execution_binding_error = _verify_execution_bindings_unchanged(manifest)
    if execution_binding_error:
        print(f"ERROR: {execution_binding_error}", file=sys.stderr)
        return 1

    for artifact_key in ("candidate_artifact", "baseline_artifact"):
        mismatch = _verify_artifact_unchanged(manifest[artifact_key])
        if mismatch:
            print(f"ERROR: {mismatch}", file=sys.stderr)
            return 1

    # games_per_segment/wall_timeout_seconds/side_allocation_schedule/selected_opponents are
    # read EXCLUSIVELY from the manifest -- `run` has no --opponent/--games-per-segment flags
    # of its own, so the executed protocol can never silently diverge from what
    # comparison_manifest_sha256 identifies. opponent_pins.json is NEVER read here.
    games_per_segment = manifest["protocol_identity"]["games_per_segment"]
    wall_timeout_seconds = float(manifest["protocol_identity"]["wall_timeout_seconds"])
    side_schedule = manifest["protocol_identity"]["side_allocation_schedule"]
    if len(side_schedule) != games_per_segment:
        print("ERROR: manifest's side_allocation_schedule length does not match games_per_segment "
              "(should be impossible given the integrity check above)", file=sys.stderr)
        return 1
    dataset_id = manifest["dataset_identity"]["id"]
    protocol_id = manifest["protocol_identity"]["id"]
    comparison_hash = manifest["comparison_manifest_sha256"]
    selected_opponents = manifest["dataset_identity"]["selected_opponents"]

    os.makedirs(args.jsonl_out, exist_ok=True)
    clone_dest_root = tempfile.mkdtemp(prefix="eval_infra_run_clones_")
    raw_tmp_root = tempfile.mkdtemp(prefix="eval_infra_run_raw_")

    errors: list[dict] = []
    executed: list[dict] = []
    try:
        for binding in selected_opponents:
            opponent_id = binding["opponent_id"]
            try:
                opp_agent_abs, opp_deck_abs = _resolve_opponent_paths_at_run_time(binding, clone_dest_root)
            except ValueError as exc:
                errors.append({"opponent_id": opponent_id, "reason": str(exc)})
                continue

            for arm in ("baseline", "candidate"):
                arm_artifact = manifest["candidate_artifact"] if arm == "candidate" else manifest["baseline_artifact"]
                arm_agent_path = _artifact_file_path(arm_artifact, "agent")
                arm_deck_path = _artifact_file_path(arm_artifact, "deck")
                arm_params_path = _artifact_file_path(arm_artifact, "params")
                if binding["source_kind"] == "self_play":
                    this_opp_agent = _abs_repo_path(arm_agent_path)
                    this_opp_deck = _abs_repo_path(arm_deck_path)
                else:
                    this_opp_agent, this_opp_deck = opp_agent_abs, opp_deck_abs

                out_path = os.path.join(args.jsonl_out, _jsonl_filename(manifest, opponent_id, arm))
                if os.path.exists(out_path):
                    errors.append({"opponent_id": opponent_id, "arm": arm,
                                    "reason": f"refusing to append to an already-existing jsonl "
                                              f"output file (rerun with a fresh --jsonl-out dir): {out_path}"})
                    continue

                env = os.environ.copy()
                if arm_params_path:
                    env["POKEMON_AI_PARAMS_PATH"] = _abs_repo_path(arm_params_path)
                else:
                    env.pop("POKEMON_AI_PARAMS_PATH", None)

                arm_ok = True
                seq = 0
                for gi in range(games_per_segment):
                    first_player = side_schedule[gi]
                    batch_raw_path = os.path.join(raw_tmp_root, f"{opponent_id}_{arm}_{gi}.jsonl")
                    cmd = [
                        sys.executable, _HEAD_TO_HEAD_PATH,
                        "--agent-a", _abs_repo_path(arm_agent_path), "--deck-a", _abs_repo_path(arm_deck_path),
                        "--agent-b", this_opp_agent, "--deck-b", this_opp_deck,
                        "--n", "1", "--first-player", first_player,
                        "--jsonl-out", batch_raw_path, "--record-decision-timing",
                        "--label-a", arm, "--label-b", opponent_id,
                    ]
                    raw_record = None
                    try:
                        proc = subprocess.run(cmd, timeout=wall_timeout_seconds, capture_output=True, text=True, env=env)
                        raw_lines = _read_jsonl(batch_raw_path)
                        if proc.returncode != 0:
                            errors.append({
                                "opponent_id": opponent_id, "arm": arm, "game_index": gi,
                                "returncode": proc.returncode,
                                "stderr": proc.stderr.strip()[-2000:], "stdout": proc.stdout.strip()[-2000:],
                            })
                            arm_ok = False
                            break
                        if len(raw_lines) != 1:
                            errors.append({
                                "opponent_id": opponent_id, "arm": arm, "game_index": gi,
                                "reason": f"subprocess exited 0 but wrote {len(raw_lines)} jsonl "
                                          f"record(s), expected exactly 1",
                            })
                            arm_ok = False
                            break
                        raw_record = raw_lines[0]
                    except subprocess.TimeoutExpired:
                        # head_to_head.py cannot observe its own hang, so only the orchestrator
                        # (here) can write a fallback record. If the subprocess had already
                        # flushed its single real record just before hanging, use it as-is
                        # (genuinely completed) instead of fabricating a spurious timeout. A
                        # malformed partial write at this point is treated the same as no write
                        # at all -- fall back to the honest synthesized timeout record rather
                        # than trying to salvage unparseable JSON.
                        try:
                            raw_lines = _read_jsonl(batch_raw_path)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            raw_lines = []
                        if len(raw_lines) > 1:
                            errors.append({
                                "opponent_id": opponent_id, "arm": arm, "game_index": gi,
                                "reason": f"subprocess timed out but had already written "
                                          f"{len(raw_lines)} jsonl record(s) (expected at most "
                                          f"1) before hanging -- refusing to silently pick one "
                                          f"and discard the rest",
                            })
                            arm_ok = False
                            break
                        elif raw_lines:
                            raw_record = raw_lines[0]
                        else:
                            raw_record = {
                                "schema_version": "1", "game_index": 0, "first_seat_agent": first_player,
                                "label_a": arm, "label_b": opponent_id,
                                "termination": {"category": "timeout", "kind": "wall_clock"},
                                "result": None, "error_actor": None, "legality": "unknown",
                                "decisions": None,
                            }
                    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                        # head_to_head.py exited (0 or nonzero -- doesn't matter, we never got
                        # far enough to check) having written unparseable JSON (or invalid
                        # UTF-8) to its jsonl output -- an earlier version let this propagate as
                        # an uncaught exception out of `run` entirely, instead of the same
                        # fail-closed per-game error path every other subprocess-output problem
                        # here uses (found by an independent heterogeneous-model audit).
                        errors.append({
                            "opponent_id": opponent_id, "arm": arm, "game_index": gi,
                            "reason": f"subprocess wrote unparseable/undecodable output to its "
                                      f"jsonl file: {exc}",
                        })
                        arm_ok = False
                        break
                    finally:
                        if os.path.exists(batch_raw_path):
                            os.remove(batch_raw_path)

                    # The raw record (whether freshly read, salvaged from a hung subprocess, or
                    # the synthesized timeout fallback) must itself be schema-valid BEFORE
                    # enrichment -- an earlier version did `dict(raw_record)` directly, so a
                    # subprocess that exited 0 but wrote a JSON value that ISN'T an object (e.g.
                    # an empty array `[]`) silently produced an enriched record missing every
                    # real game field via `dict([])` == `{}`, and `run` reported success instead
                    # of the malformed subprocess output it actually received (found by an
                    # independent heterogeneous-model audit). validate_game_record's own first
                    # check already handles a non-dict raw_record without crashing.
                    try:
                        raw_record = schema.validate_game_record(raw_record)
                    except schema.SchemaError as exc:
                        errors.append({
                            "opponent_id": opponent_id, "arm": arm, "game_index": gi,
                            "reason": f"the raw game record failed schema validation: {exc}",
                        })
                        arm_ok = False
                        break

                    # The record's own label_a/label_b/first_seat_agent must match what THIS
                    # invocation actually asked head_to_head.py to run -- `summarize` performs
                    # this exact cross-check later (RECORD_LABEL_MISMATCH / seat mismatch) when
                    # it reads the jsonl file back, but an earlier version of `run` never
                    # checked this itself, so it could write a mismatched record and still
                    # report success, only for `summarize` to reject the file afterward (found
                    # by an independent heterogeneous-model audit).
                    if raw_record["label_a"] != arm or raw_record["label_b"] != opponent_id:
                        errors.append({
                            "opponent_id": opponent_id, "arm": arm, "game_index": gi,
                            "reason": f"subprocess wrote label_a={raw_record['label_a']!r}/"
                                      f"label_b={raw_record['label_b']!r}, expected "
                                      f"label_a={arm!r}/label_b={opponent_id!r}",
                        })
                        arm_ok = False
                        break
                    if raw_record["first_seat_agent"] != first_player:
                        errors.append({
                            "opponent_id": opponent_id, "arm": arm, "game_index": gi,
                            "reason": f"subprocess wrote first_seat_agent="
                                      f"{raw_record['first_seat_agent']!r}, expected "
                                      f"{first_player!r} (per this manifest's "
                                      f"side_allocation_schedule)",
                        })
                        arm_ok = False
                        break

                    # Orchestrator enrichment: a GLOBALLY unique game_id (head_to_head.py's own
                    # "game_index" resets to 0 on every subprocess invocation and would collide
                    # across games at games_per_worker=1 if used alone -- see the BLOCKER this
                    # fixes), a batch_id, and full dataset/protocol/artifact/opponent identity.
                    # head_to_head.py itself never writes any of this (generic/application
                    # separation) -- only the orchestrator, which alone knows the comparison
                    # context, does.
                    enriched = dict(raw_record)
                    enriched["game_id"] = f"{comparison_hash}:{opponent_id}:{arm}:{seq:06d}"
                    enriched["batch_id"] = gi
                    enriched["comparison_manifest_sha256"] = comparison_hash
                    enriched["dataset_id"] = dataset_id
                    enriched["protocol_id"] = protocol_id
                    enriched["opponent_id"] = opponent_id
                    enriched["arm"] = arm
                    enriched["artifact_id"] = arm_artifact["artifact_id"]
                    with open(out_path, "a", encoding="utf-8") as outf:
                        outf.write(json.dumps(enriched) + "\n")
                    seq += 1

                if arm_ok:
                    executed.append({"opponent_id": opponent_id, "arm": arm, "jsonl_path": out_path, "games": seq})
    finally:
        shutil.rmtree(clone_dest_root, ignore_errors=True)
        shutil.rmtree(raw_tmp_root, ignore_errors=True)

    partial = bool(errors)
    if errors and not args.allow_partial:
        print(f"ERROR: {len(errors)} opponent/arm/game error(s) and --allow-partial not set: {errors}", file=sys.stderr)
        return 1

    run_index = {
        "comparison_manifest_sha256": comparison_hash,
        "partial_diagnostic": partial,
        "errors": errors,
        "executed": executed,
    }
    index_path = os.path.join(args.jsonl_out, f"{_manifest_hash8(manifest)}__run_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(run_index, f, indent=2, sort_keys=True, ensure_ascii=False)
    print(f"Wrote run index to {index_path} (partial_diagnostic={partial})")
    return 0


# --------------------------------------------------------------------------
# summarize
# --------------------------------------------------------------------------

def _load_and_validate_jsonl(path: str, manifest: dict, expected_opponent_id: str, expected_arm: str) -> list[dict]:
    """Loads and validates one jsonl file's records against BOTH the
    filename convention AND the manifest's own authoritative fields. An
    earlier version only checked dataset_id/protocol_id/artifact_id are
    non-empty strings (not that they match the manifest), only checked
    opponent_id against the generic known-opponent-ID set (not against
    which opponents THIS manifest actually selected), and never reconciled
    first_seat_agent against the manifest's own precomputed
    side_allocation_schedule -- so a record could claim the right
    comparison_manifest_sha256 while carrying inconsistent provenance or a
    fabricated seat assignment. All of that is cross-checked here."""
    manifest_hash_full = manifest["comparison_manifest_sha256"]
    selected_opponent_ids = {b["opponent_id"] for b in manifest["dataset_identity"]["selected_opponents"]}
    side_schedule = manifest["protocol_identity"]["side_allocation_schedule"]
    expected_dataset_id = manifest["dataset_identity"]["id"]
    expected_protocol_id = manifest["protocol_identity"]["id"]
    expected_artifact_id = manifest["candidate_artifact" if expected_arm == "candidate" else "baseline_artifact"]["artifact_id"]

    basename = os.path.basename(path)
    if not basename.startswith(manifest_hash_full + "__"):
        raise schema.SchemaError(
            f"REUSE_REJECTED: {basename!r} does not carry the expected FULL 64-hex manifest "
            f"hash prefix {manifest_hash_full!r} -- refusing to mix games collected under a "
            f"different manifest."
        )
    if expected_opponent_id not in selected_opponent_ids:
        raise schema.SchemaError(
            f"OPPONENT_NOT_SELECTED: {basename!r} implies opponent_id={expected_opponent_id!r}, "
            f"which is not among this manifest's own selected_opponents "
            f"({sorted(selected_opponent_ids)}) -- refusing to accept data for an opponent "
            f"this manifest never selected"
        )

    records = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise schema.SchemaError(f"MALFORMED_JSON in {basename!r} line {line_no}: {exc}") from exc
            rec = schema.validate_enriched_game_record(raw)
            if rec["opponent_id"] != expected_opponent_id or rec["arm"] != expected_arm:
                raise schema.SchemaError(
                    f"RECORD_IDENTITY_MISMATCH in {basename!r} line {line_no}: record says "
                    f"opponent_id={rec['opponent_id']!r} arm={rec['arm']!r}, filename implies "
                    f"opponent_id={expected_opponent_id!r} arm={expected_arm!r}"
                )
            if rec["label_a"] != expected_arm or rec["label_b"] != expected_opponent_id:
                raise schema.SchemaError(
                    f"RECORD_LABEL_MISMATCH in {basename!r} line {line_no}: "
                    f"record says label_a={rec['label_a']!r} label_b={rec['label_b']!r}, "
                    f"filename implies arm={expected_arm!r} opponent_id={expected_opponent_id!r}"
                )
            if rec["comparison_manifest_sha256"] != manifest_hash_full:
                raise schema.SchemaError(
                    f"RECORD_MANIFEST_HASH_MISMATCH in {basename!r} line {line_no}: record's own "
                    f"comparison_manifest_sha256 does not match --manifest"
                )
            if rec["dataset_id"] != expected_dataset_id:
                raise schema.SchemaError(
                    f"RECORD_DATASET_ID_MISMATCH in {basename!r} line {line_no}: record says "
                    f"dataset_id={rec['dataset_id']!r}, manifest's own dataset_identity.id is "
                    f"{expected_dataset_id!r}"
                )
            if rec["protocol_id"] != expected_protocol_id:
                raise schema.SchemaError(
                    f"RECORD_PROTOCOL_ID_MISMATCH in {basename!r} line {line_no}: record says "
                    f"protocol_id={rec['protocol_id']!r}, manifest's own protocol_identity.id is "
                    f"{expected_protocol_id!r}"
                )
            if rec["artifact_id"] != expected_artifact_id:
                raise schema.SchemaError(
                    f"RECORD_ARTIFACT_ID_MISMATCH in {basename!r} line {line_no}: record says "
                    f"artifact_id={rec['artifact_id']!r}, manifest's own {expected_arm}_artifact.artifact_id "
                    f"is {expected_artifact_id!r}"
                )
            if not (0 <= rec["batch_id"] < len(side_schedule)):
                raise schema.SchemaError(
                    f"RECORD_BATCH_ID_OUT_OF_RANGE in {basename!r} line {line_no}: batch_id="
                    f"{rec['batch_id']!r}, manifest's side_allocation_schedule has "
                    f"{len(side_schedule)} entries"
                )
            expected_seat = side_schedule[rec["batch_id"]]
            if rec["first_seat_agent"] != expected_seat:
                raise schema.SchemaError(
                    f"RECORD_SEAT_SCHEDULE_MISMATCH in {basename!r} line {line_no}: record's "
                    f"first_seat_agent={rec['first_seat_agent']!r} for batch_id={rec['batch_id']!r}, "
                    f"but manifest's side_allocation_schedule says {expected_seat!r} for that batch"
                )
            records.append(rec)
    return records


def _reject_duplicate_game_ids(all_records: dict[tuple[str, str], list[dict]]) -> str | None:
    seen: dict[str, tuple[str, str]] = {}
    for key, records in all_records.items():
        for rec in records:
            gid = rec["game_id"]
            if gid in seen:
                return f"DUPLICATE_GAME_ID: {gid!r} appears in both {seen[gid]!r} and {key!r}"
            seen[gid] = key
    return None


def _rate_cell(baseline_records: list[dict], candidate_records: list[dict], metric_id: str, segment_id: str,
               predicate, confidence: str) -> dict | None:
    """Game-level 0/1 rate metrics (win/error/timeout/illegal_action): each
    game contributes exactly one independent binary observation, so Wilson
    (per arm) + the Newcombe-Wilson delta (see stats.newcombe_delta) is the
    standard, appropriate method -- not a bootstrap (bootstrap is reserved
    for genuinely within-game-correlated, multi-observation-per-game metrics
    -- see _latency_cell)."""
    b_hits = [1.0 if predicate(r) else 0.0 for r in baseline_records]
    c_hits = [1.0 if predicate(r) else 0.0 for r in candidate_records]
    if not b_hits or not c_hits:
        return None  # omit the cell entirely; never emit observations: 0
    b_stats = wilson_interval(int(sum(b_hits)), len(b_hits), confidence)
    c_stats = wilson_interval(int(sum(c_hits)), len(c_hits), confidence)
    delta = newcombe_delta(int(sum(b_hits)), len(b_hits), int(sum(c_hits)), len(c_hits), confidence)
    return schema.build_cell(metric_id, segment_id, len(b_hits) + len(c_hits), b_stats, c_stats, delta)


def _arm_own_decision_durations_ms(records: list[dict]) -> list[list[float]] | None:
    """Per-game lists of ONLY this arm's own decisions' duration_ms (actor
    == 'a' -- `run` always invokes head_to_head.py with the arm as
    --agent-a and the opponent as --agent-b, so 'a' always means the arm
    being measured, never the opponent). Returns None if no record in this
    segment actually captured decision timing (--record-decision-timing was
    off), so the caller can omit the cell instead of fabricating zeros."""
    if not records or all(r.get("decisions") is None for r in records):
        return None
    games = []
    for r in records:
        decisions = r.get("decisions") or []
        games.append([d["duration_ms"] for d in decisions if d["actor"] == "a"])
    return [g for g in games if g]  # drop games with zero own-decisions (e.g. engine_null_start)


def _latency_cell(baseline_records: list[dict], candidate_records: list[dict], metric_id: str, segment_id: str,
                   pct: float, confidence: str, replicates: int, manifest_hash: str) -> dict | None:
    b_games = _arm_own_decision_durations_ms(baseline_records)
    c_games = _arm_own_decision_durations_ms(candidate_records)
    if not b_games or not c_games or (len(b_games) + len(c_games)) == 0:
        # Never a hard crash: if every game in this segment contributed zero own-decisions
        # (e.g. all engine_null_start, or timing simply wasn't captured), the cell is
        # UNAVAILABLE (omitted), not an exception from schema.build_cell's observations>=1 check.
        return None
    pfn = percentile_statistic(pct)
    # Deterministically derived from (comparison_manifest_sha256, metric_id, segment_id, arm)
    # ONLY -- no caller-supplied seed, matching _BOOTSTRAP_SEED_SCHEME. The same manifest +
    # the same JSONL input always produces the identical bootstrap output; there is no seed
    # for a caller to vary even if they wanted to (see BLOCKER 1 in the module docstring).
    base_seed = {"comparison_manifest_sha256": manifest_hash, "metric_id": metric_id, "segment_id": segment_id}
    b_stats = game_cluster_bootstrap_interval(b_games, pfn, {**base_seed, "arm": "baseline_interval"}, replicates, confidence)
    c_stats = game_cluster_bootstrap_interval(c_games, pfn, {**base_seed, "arm": "candidate_interval"}, replicates, confidence)
    delta = game_cluster_bootstrap_delta(b_games, c_games, pfn, base_seed, replicates, confidence)
    # `observations` reflects the number of GAME CLUSTERS actually backing the bootstrap
    # (post-filtering games with no captured own-decision), not the raw record count.
    return schema.build_cell(metric_id, segment_id, len(b_games) + len(c_games), b_stats, c_stats, delta)


def _observation_count_cell(baseline_records: list[dict], candidate_records: list[dict], segment_id: str) -> dict | None:
    b_games = _arm_own_decision_durations_ms(baseline_records)
    c_games = _arm_own_decision_durations_ms(candidate_records)
    if b_games is None or c_games is None or (len(b_games) + len(c_games)) == 0:
        return None
    b_total = sum(len(g) for g in b_games)
    c_total = sum(len(g) for g in c_games)
    return schema.build_cell(
        schema.METRIC_OBSERVATION_COUNT, segment_id, len(b_games) + len(c_games),
        exact_count_interval(b_total), exact_count_interval(c_total), exact_count_interval(c_total - b_total),
    )


def cmd_summarize(args: argparse.Namespace) -> int:
    manifest, load_error = _load_manifest(args.manifest)
    if load_error:
        print(f"ERROR: {load_error}", file=sys.stderr)
        return 1

    integrity_error = _verify_manifest_integrity(manifest)
    if integrity_error:
        print(f"ERROR: {integrity_error}", file=sys.stderr)
        return 1

    execution_binding_error = _verify_execution_bindings_unchanged(manifest)
    if execution_binding_error:
        print(f"ERROR: {execution_binding_error}", file=sys.stderr)
        return 1

    # summarize copies manifest["candidate_artifact"]/["baseline_artifact"] verbatim into its
    # report -- so their "files" paths must be validated (containment + canonical repo-relative
    # form) here too, not just by `run`, or a forged manifest fed directly to `summarize`
    # (never touching `run` at all) could embed an unvalidated/absolute path into the report.
    for artifact_key in ("candidate_artifact", "baseline_artifact"):
        artifact_error = _verify_artifact_unchanged(manifest[artifact_key])
        if artifact_error:
            print(f"ERROR: {artifact_error}", file=sys.stderr)
            return 1

    manifest_hash = _manifest_hash_full(manifest)

    if args.stage != manifest["stage"]:
        print(f"ERROR: --stage {args.stage!r} does not match manifest's stage {manifest['stage']!r}", file=sys.stderr)
        return 1

    # confidence_level/bootstrap_replicates come EXCLUSIVELY from the manifest's own
    # protocol_identity.measurement_settings -- summarize has no --confidence-level/
    # --bootstrap-replicates/--rng-seed flags of its own (see BLOCKER 1 in the module
    # docstring). Already semantically validated by _verify_manifest_integrity above; read
    # directly here.
    measurement_settings = manifest["protocol_identity"]["measurement_settings"]
    confidence = Decimal(measurement_settings["confidence_level"])
    bootstrap_replicates = measurement_settings["bootstrap_replicates"]

    try:
        all_records: dict[tuple[str, str], list[dict]] = {}
        for path in args.jsonl_in:
            basename = os.path.basename(path)
            parts = basename[len(manifest_hash) + 2:].rsplit(".jsonl", 1)[0].split("__")
            if len(parts) != 2:
                raise schema.SchemaError(f"unrecognized jsonl filename convention: {basename!r}")
            opponent_id, arm = parts
            if opponent_id not in schema.KNOWN_OPPONENT_IDS:
                raise schema.SchemaError(
                    f"UNKNOWN_OPPONENT: {basename!r} implies opponent_id={opponent_id!r}, "
                    f"which is not one of {sorted(schema.KNOWN_OPPONENT_IDS)}"
                )
            if arm not in ("baseline", "candidate"):
                raise schema.SchemaError(f"UNKNOWN_ARM: {basename!r} implies arm={arm!r}, expected baseline/candidate")
            key = (opponent_id, arm)
            if key in all_records:
                raise schema.SchemaError(f"DUPLICATE_JSONL_INPUT: (opponent_id={opponent_id!r}, arm={arm!r}) "
                                          f"supplied more than once across --jsonl-in arguments")
            # Sorted by game_id (globally unique -- see _reject_duplicate_game_ids below)
            # immediately after loading, so a JSONL file's own line order (which nothing
            # requires to already match batch_id order) can never affect the resulting stats.
            all_records[key] = sorted(_load_and_validate_jsonl(path, manifest, opponent_id, arm), key=lambda r: r["game_id"])

        dup_error = _reject_duplicate_game_ids(all_records)
        if dup_error:
            raise schema.SchemaError(dup_error)
    except schema.SchemaError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # Completeness is checked THREE ways per (opponent, arm), not just "does a file exist for
    # it" -- an earlier version only checked key presence in all_records, so an EMPTY or
    # partially-written file (e.g. from a `run --allow-partial` that failed after 1 of N
    # games) would still count as "present" and could be labeled report_kind="primary". Here:
    # (1) the (opponent, arm) key must exist at all, (2) it must have EXACTLY
    # games_per_segment records (not fewer, not more), (3) its records' batch_id values must
    # exactly cover {0, ..., games_per_segment-1} with no gaps and no duplicates.
    games_per_segment = manifest["protocol_identity"]["games_per_segment"]
    expected_batch_ids = set(range(games_per_segment))
    selected_opponent_ids = [b["opponent_id"] for b in manifest["dataset_identity"]["selected_opponents"]]
    league_opponent_ids = [o for o in selected_opponent_ids if o != opponent_registry.MIRROR_OPPONENT_ID]
    incomplete_inputs = []
    for opp in league_opponent_ids:
        for arm in ("baseline", "candidate"):
            key = (opp, arm)
            if key not in all_records:
                incomplete_inputs.append(f"{opp}/{arm}: missing entirely")
                continue
            records = all_records[key]
            if len(records) != games_per_segment:
                incomplete_inputs.append(
                    f"{opp}/{arm}: has {len(records)} record(s), expected exactly {games_per_segment}"
                )
                continue
            actual_batch_ids = {r["batch_id"] for r in records}
            if actual_batch_ids != expected_batch_ids:
                incomplete_inputs.append(
                    f"{opp}/{arm}: batch_id coverage {sorted(actual_batch_ids)} does not match "
                    f"the expected {sorted(expected_batch_ids)} (gap or duplicate batch)"
                )
    input_complete = not incomplete_inputs
    # Recomputed from the manifest's own selected_opponents, never trusted from the stored
    # dataset_identity.league_complete boolean directly -- an earlier version trusted that
    # stored field, so an internally hash-consistent-but-not-CLI-built manifest claiming
    # league_complete=true while selected_opponents actually covers only a subset of the
    # required league would still be accepted as report_kind="primary" (found by an
    # independent heterogeneous-model audit).
    league_complete = set(schema.REQUIRED_LEAGUE_OPPONENTS) <= set(selected_opponent_ids)
    report_kind = "primary" if (league_complete and input_complete) else "partial_diagnostic"
    if report_kind == "partial_diagnostic" and not args.allow_partial_report:
        print(f"ERROR: fail-closed: this would be a partial_diagnostic report (league_complete="
              f"{league_complete}, incomplete_inputs={incomplete_inputs}) "
              f"and --allow-partial-report was not set", file=sys.stderr)
        return 1

    cells = []
    # Sorted by game_id, NOT left in all_records' dict-iteration order (which follows
    # --jsonl-in's CLI argument order across opponents) -- the whole-game cluster bootstrap
    # (_latency_cell) maps each resample index to games[idx] by LIST POSITION, so a different
    # merge order would resample different actual game content at the same index even given
    # the identical seed_material, silently producing a different report from the same
    # manifest + the same JSONL inputs depending purely on --jsonl-in order (found by an
    # independent heterogeneous-model audit, reproduced empirically: two summarize calls
    # differing only in --jsonl-in order produced different confidence intervals).
    league_baseline = sorted(
        (r for (opp, arm), recs in all_records.items() if opp != "mirror" and arm == "baseline" for r in recs),
        key=lambda r: r["game_id"],
    )
    league_candidate = sorted(
        (r for (opp, arm), recs in all_records.items() if opp != "mirror" and arm == "candidate" for r in recs),
        key=lambda r: r["game_id"],
    )

    def _is_win(r):
        return r["result"] is not None and r["result"].get("winner") == "a"

    def _is_error(r):
        return r["termination"]["category"] == "error"

    def _is_timeout(r):
        return r["termination"]["category"] == "timeout"

    conf_str = str(confidence)

    # The league-wide "overall" external_league_win_rate cell is the one metric that claims
    # to represent the FULL fixed opponent league -- it must never be computed (and never
    # silently reported as if it were primary) from a partial opponent set.
    if report_kind == "primary":
        win_cell = _rate_cell(league_baseline, league_candidate, schema.METRIC_WIN_RATE, schema.SEGMENT_OVERALL, _is_win, conf_str)
        if win_cell:
            cells.append(win_cell)

    for opp_id, seg_id in (
        ("lucario", schema.SEGMENT_OPPONENT_LUCARIO),
        ("dragapult", schema.SEGMENT_OPPONENT_DRAGAPULT),
        ("megastarmie", schema.SEGMENT_OPPONENT_MEGASTARMIE),
    ):
        b = all_records.get((opp_id, "baseline"), [])
        c = all_records.get((opp_id, "candidate"), [])
        cell = _rate_cell(b, c, schema.METRIC_WIN_RATE, seg_id, _is_win, conf_str)
        if cell:
            cells.append(cell)
    for seat_val, seg_id in (("a", schema.SEGMENT_SEAT_0), ("b", schema.SEGMENT_SEAT_1)):
        b = [r for r in league_baseline if r["first_seat_agent"] == seat_val]
        c = [r for r in league_candidate if r["first_seat_agent"] == seat_val]
        cell = _rate_cell(b, c, schema.METRIC_WIN_RATE, seg_id, _is_win, conf_str)
        if cell:
            cells.append(cell)

    for metric_id, pred in (
        (schema.METRIC_ERROR_RATE, _is_error),
        (schema.METRIC_TIMEOUT_RATE, _is_timeout),
    ):
        cell = _rate_cell(league_baseline, league_candidate, metric_id, schema.SEGMENT_OVERALL, pred, conf_str)
        if cell:
            cells.append(cell)

    # illegal_action_rate's denominator is deliberately restricted to records with a KNOWN
    # legality (legal or illegal) -- "unknown" games (e.g. a malformed agent return, or any
    # error/timeout that isn't a confirmed engine-side IndexError) must be excluded from both
    # numerator and denominator, per the three-bucket model documented in README.md's F2.
    known_legality_baseline = [r for r in league_baseline if r["legality"] in ("legal", "illegal")]
    known_legality_candidate = [r for r in league_candidate if r["legality"] in ("legal", "illegal")]
    illegal_cell = _rate_cell(known_legality_baseline, known_legality_candidate,
                               schema.METRIC_ILLEGAL_ACTION_RATE, schema.SEGMENT_OVERALL,
                               lambda r: r["legality"] == "illegal", conf_str)
    if illegal_cell:
        cells.append(illegal_cell)

    for metric_id, pct in ((schema.METRIC_DECISION_TIME_P50_MS, 50), (schema.METRIC_DECISION_TIME_P95_MS, 95)):
        cell = _latency_cell(league_baseline, league_candidate, metric_id, schema.SEGMENT_OVERALL, pct,
                              conf_str, bootstrap_replicates, manifest_hash)
        if cell:
            cells.append(cell)
    obs_cell = _observation_count_cell(league_baseline, league_candidate, schema.SEGMENT_OVERALL)
    if obs_cell:
        cells.append(obs_cell)

    diagnostics = {
        "illegal_action_known_legal_or_illegal": sum(1 for r in league_baseline + league_candidate if r["legality"] in ("legal", "illegal")),
        "illegal_action_unknown_legality": sum(1 for r in league_baseline + league_candidate if r["legality"] == "unknown"),
        "mirror_games": sum(len(recs) for (opp, arm), recs in all_records.items() if opp == "mirror"),
        "league_complete": league_complete,
        "input_complete": input_complete,
        "incomplete_inputs": incomplete_inputs,
    }

    report = {
        "schema_version": "1",
        "report_kind": report_kind,
        "comparison_manifest_sha256": manifest["comparison_manifest_sha256"],
        "stage": manifest["stage"],
        "candidate_role": manifest.get("candidate_role"),
        "candidate_artifact": manifest["candidate_artifact"],
        "baseline_artifact": manifest["baseline_artifact"],
        "total_observations": len(league_baseline) + len(league_candidate),
        "cells": cells,
        "diagnostics": diagnostics,
        # Recorded so a report is self-documenting -- copied verbatim from the manifest's own
        # protocol_identity.measurement_settings (fixed at manifest-creation time, hashed into
        # comparison_manifest_sha256), not from any summarize-time caller choice. The same
        # comparison_manifest_sha256 + the same JSONL input ALWAYS produces this exact same
        # measurement_settings (and therefore identical stats output) -- there is no
        # caller-supplied seed for a different summarize invocation to vary.
        "measurement_settings": measurement_settings,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True, ensure_ascii=False)
    print(f"Wrote Measurement Report to {args.out} ({len(cells)} cells, report_kind={report_kind})")
    return 0


# --------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="raging_bolt evaluation infrastructure CLI")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_manifest = sub.add_parser("manifest", help="Resolve, freeze, and hash a full comparison specification")
    p_manifest.add_argument("--candidate-agent", required=True)
    p_manifest.add_argument("--candidate-deck", required=True)
    p_manifest.add_argument("--candidate-artifact-id", required=True)
    p_manifest.add_argument("--candidate-params", default=None)
    p_manifest.add_argument("--baseline-agent", required=True)
    p_manifest.add_argument("--baseline-deck", required=True)
    p_manifest.add_argument("--baseline-artifact-id", required=True)
    p_manifest.add_argument("--baseline-params", default=None)
    p_manifest.add_argument("--protocol-id", required=True)
    p_manifest.add_argument("--dataset-id", required=True)
    p_manifest.add_argument("--dataset-version", required=True)
    p_manifest.add_argument("--stage", choices=("screening", "confirmation"), required=True)
    p_manifest.add_argument("--candidate-role", choices=("primary", "fallback"), default="primary")
    p_manifest.add_argument("--wall-timeout-seconds", type=float, default=120.0)
    p_manifest.add_argument("--opponent", action="append", required=True,
                             help="Repeatable. Must be one of lucario/dragapult/megastarmie/mirror. "
                                  "Resolved, cloned-if-needed, and hash-bound RIGHT NOW.")
    p_manifest.add_argument("--games-per-segment", type=int, required=True)
    # Statistical measurement settings are fixed HERE (manifest-creation time), not at
    # `summarize` time -- see cmd_manifest's own comment and BLOCKER 1 in the module docstring.
    p_manifest.add_argument("--confidence-level", default="0.95")
    p_manifest.add_argument("--bootstrap-replicates", type=int, default=10_000)
    p_manifest.add_argument("--out", required=True)
    p_manifest.set_defaults(func=cmd_manifest)

    p_run = sub.add_parser("run", help="Play exactly the games a manifest fixes")
    p_run.add_argument("--manifest", required=True)
    # No --opponent / --games-per-segment / --games-per-worker / --wall-timeout-seconds here
    # -- ALL of these come exclusively from --manifest (see module docstring).
    p_run.add_argument("--jsonl-out", required=True, help="Output DIRECTORY for per-(opponent,arm) jsonl files")
    p_run.add_argument("--allow-partial", action="store_true")
    p_run.set_defaults(func=cmd_run)

    p_summarize = sub.add_parser("summarize", help="Aggregate jsonl records into a Measurement Report")
    p_summarize.add_argument("--manifest", required=True)
    p_summarize.add_argument("--jsonl-in", action="append", required=True)
    p_summarize.add_argument("--stage", choices=("screening", "confirmation"), required=True)
    # No --confidence-level / --bootstrap-replicates / --rng-seed here -- ALL statistical
    # measurement settings come exclusively from --manifest's protocol_identity.
    # measurement_settings (see cmd_manifest and BLOCKER 1 in the module docstring). An earlier
    # version let these be freely chosen at summarize-time, so the SAME
    # comparison_manifest_sha256 could produce Measurement Reports with different confidence
    # intervals -- found by an independent external review. The bootstrap seed is derived
    # deterministically from (comparison_manifest_sha256, metric_id, segment_id, arm); no
    # caller-supplied seed is needed or accepted.
    p_summarize.add_argument("--allow-partial-report", action="store_true",
                              help="Permit a partial_diagnostic report when the league is "
                                   "incomplete or inputs are missing for a selected opponent/arm. "
                                   "Without this, summarize fails closed instead.")
    p_summarize.add_argument("--out", required=True)
    p_summarize.set_defaults(func=cmd_summarize)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
