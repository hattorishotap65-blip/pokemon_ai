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
    if current_engine != recorded_engine:
        return (f"engine_binding mismatch: libcg.so and/or its Python wrapper files "
                f"(reference/extracted/cg/*.py) differ from what `manifest` recorded "
                f"(recorded libcg_so_sha256={recorded_engine.get('libcg_so_sha256')!r}, "
                f"now {current_engine.get('libcg_so_sha256')!r})")

    current_evaluator = _evaluator_binding()
    recorded_evaluator = manifest["protocol_identity"]["evaluator_binding"]
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
        if not repo_url or not file_paths or len(file_paths) != 2 or not commit_sha:
            raise ValueError(
                f"opponent {opponent_id!r}: opponent_pins.json entry incomplete or missing "
                f"(needs commit_sha + repo_url + exactly-2 file_paths: agent, deck) -- drop it "
                f"from --opponent or add a valid pin first"
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

    pins = opponent_registry.load_pins(_PINS_PATH)
    selected_opponents = []
    for opponent_id in args.opponent:
        try:
            selected_opponents.append(_resolve_opponent_binding(opponent_id, pins))
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    league_complete = set(schema.REQUIRED_LEAGUE_OPPONENTS) <= set(args.opponent)
    side_allocation_schedule = ["a" if i % 2 == 0 else "b" for i in range(args.games_per_segment)]

    protocol_identity = {
        "id": args.protocol_id,
        "step_limit": 2000,
        "games_per_worker": 1,  # forced -- seat alternation is unimplemented for >1 (see README F3)
        "wall_timeout_seconds": str(args.wall_timeout_seconds),
        "games_per_segment": args.games_per_segment,
        "side_allocation_schedule": side_allocation_schedule,
        "worker_model": "one_subprocess_per_game",
        "decision_time_measurement": "wall-clock time.perf_counter() per agent decision, tagged actor=a|b; summarize uses only actor=a (the arm under measurement)",
        "game_rng_control": {"availability": "UNAVAILABLE", "reason": "no seed/RNG-control parameter exists anywhere in cg.api/cg.game's Python surface"},
        "engine_binding": _engine_binding(),
        "evaluator_binding": _evaluator_binding(),
        "runtime_environment": _runtime_environment(),
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
    protocol_identity = dict(manifest.get("protocol_identity", {}))
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
    if protocol_identity.get("games_per_worker") != _ACTUAL_GAMES_PER_WORKER:
        return (f"protocol_identity.games_per_worker={protocol_identity.get('games_per_worker')!r} "
                f"does not match the actual value `run` always uses "
                f"({_ACTUAL_GAMES_PER_WORKER}) -- this manifest claims a games_per_worker that "
                f"`run` cannot actually enforce")

    dataset_identity = dict(manifest.get("dataset_identity", {}))
    stored_dataset_sha256 = dataset_identity.pop("sha256", None)
    recomputed_dataset_sha256 = sha256_hex(dataset_identity)
    if recomputed_dataset_sha256 != stored_dataset_sha256:
        return (f"dataset_identity hash mismatch: manifest claims {stored_dataset_sha256!r}, "
                f"recomputed {recomputed_dataset_sha256!r} -- dataset_identity (e.g. "
                f"selected_opponents) was edited after `manifest` wrote this file")

    candidate = manifest.get("candidate_artifact", {})
    baseline = manifest.get("baseline_artifact", {})
    for label, artifact in (("candidate_artifact", candidate), ("baseline_artifact", baseline)):
        stored_bundle_sha256 = artifact.get("sha256")
        recomputed_bundle_sha256 = _artifact_bundle_sha256_from_files(artifact.get("files", []))
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
    for f in artifact.get("files", []):
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


def cmd_run(args: argparse.Namespace) -> int:
    with open(args.manifest, encoding="utf-8") as f:
        manifest = json.load(f)

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
                        # (genuinely completed) instead of fabricating a spurious timeout.
                        raw_lines = _read_jsonl(batch_raw_path)
                        if raw_lines:
                            raw_record = raw_lines[0]
                        else:
                            raw_record = {
                                "schema_version": "1", "game_index": 0, "first_seat_agent": first_player,
                                "label_a": arm, "label_b": opponent_id,
                                "termination": {"category": "timeout", "kind": "wall_clock"},
                                "result": None, "error_actor": None, "legality": "unknown",
                                "decisions": None,
                            }
                    finally:
                        if os.path.exists(batch_raw_path):
                            os.remove(batch_raw_path)

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
                   pct: float, confidence: str, replicates: int, rng_seed: int, manifest_hash: str) -> dict | None:
    b_games = _arm_own_decision_durations_ms(baseline_records)
    c_games = _arm_own_decision_durations_ms(candidate_records)
    if not b_games or not c_games or (len(b_games) + len(c_games)) == 0:
        # Never a hard crash: if every game in this segment contributed zero own-decisions
        # (e.g. all engine_null_start, or timing simply wasn't captured), the cell is
        # UNAVAILABLE (omitted), not an exception from schema.build_cell's observations>=1 check.
        return None
    pfn = percentile_statistic(pct)
    base_seed = {"comparison_manifest_sha256": manifest_hash, "metric_id": metric_id,
                 "segment_id": segment_id, "rng_seed": rng_seed}
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
    with open(args.manifest, encoding="utf-8") as f:
        manifest = json.load(f)

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

    try:
        confidence = Decimal(args.confidence_level)
        if not (Decimal("0") < confidence < Decimal("1")):
            raise schema.SchemaError(f"--confidence-level must be strictly between 0 and 1, got {args.confidence_level!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: invalid --confidence-level: {exc}", file=sys.stderr)
        return 1
    if args.bootstrap_replicates < 1:
        print("ERROR: --bootstrap-replicates must be >= 1", file=sys.stderr)
        return 1

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
            all_records[key] = _load_and_validate_jsonl(path, manifest, opponent_id, arm)

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
    league_baseline = [r for (opp, arm), recs in all_records.items() if opp != "mirror" and arm == "baseline" for r in recs]
    league_candidate = [r for (opp, arm), recs in all_records.items() if opp != "mirror" and arm == "candidate" for r in recs]

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
                              conf_str, args.bootstrap_replicates, args.rng_seed, manifest_hash)
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
        # Recorded so a report is self-documenting/reproducible: the same comparison_manifest
        # can be summarized with different confidence/replicate/seed choices, so those choices
        # must travel with the output, not be silently implied by whatever the caller happened
        # to pass this time.
        "measurement_settings": {
            "confidence_level": conf_str,
            "bootstrap_replicates": args.bootstrap_replicates,
            "rng_seed": args.rng_seed,
        },
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
    p_summarize.add_argument("--confidence-level", default="0.95")
    p_summarize.add_argument("--bootstrap-replicates", type=int, default=10_000)
    p_summarize.add_argument("--rng-seed", type=int, required=True,
                              help="Required (no default) for reproducible bootstrap output.")
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
