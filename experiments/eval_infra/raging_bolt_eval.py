"""CLI entry point: manifest / run / summarize.

`manifest` and the CLI-shape/fail-closed-resolution parts of `run` and
`summarize` are exercised by experiments/test_eval_infra.py on any OS.
Actually spawning experiments/head_to_head.py to play real games only works
on Linux/WSL (cg.game requires libcg.so) -- see README.md caveats F1/F8/F9;
that part of `run` is implemented here but not executed by this repo's
Windows-based test session (L1-L3, explicitly deferred, not claimed passing).

Produces a "Measurement Report" (summarize's --out), which is DISTINCT from
a Gatekeeper "Evidence Bundle": it omits profile_id/profile_version/
profile_sha256/cycle_id/evidence_round (those only exist once bound to an
active App Profile, out of scope here) but every cell it does emit is
shaped exactly like a Gatekeeper Evidence cell (exact 6 keys, see
schema.build_cell), so assembling a real Evidence Bundle from a Measurement
Report plus an active Profile's binding fields is a distinct, later,
out-of-scope step this module does not perform.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from experiments.eval_infra import clone_opponent, opponent_registry, schema
from experiments.eval_infra.canon import canonicalize, sha256_hex
from experiments.eval_infra.stats import (
    exact_count_interval, game_cluster_bootstrap_delta,
    newcombe_delta, percentile_interval, percentile_statistic, wilson_interval,
)

_HEAD_TO_HEAD_PATH = os.path.join(_REPO_ROOT, "experiments", "head_to_head.py")
_PINS_PATH = os.path.join(_REPO_ROOT, "experiments", "eval_infra", "opponent_pins.json")


def _sha256_of_file_bytes(paths: list[str]) -> str:
    import hashlib
    h = hashlib.sha256()
    for p in paths:
        with open(p, "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def _artifact_binding(artifact_id: str, agent_path: str, deck_path: str, params_path: str | None) -> dict:
    file_list = [agent_path, deck_path] + ([params_path] if params_path else [])
    return {
        "artifact_id": artifact_id,
        "sha256": _sha256_of_file_bytes(file_list),
        "agent_path": agent_path,
        "deck_path": deck_path,
        "params_path": params_path,
    }


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------

def cmd_manifest(args: argparse.Namespace) -> int:
    if os.path.exists(args.out):
        print(f"ERROR: refusing to overwrite existing manifest file: {args.out}", file=sys.stderr)
        return 1
    if args.games_per_worker < 1:
        print(f"ERROR: --games-per-worker must be >= 1, got {args.games_per_worker}", file=sys.stderr)
        return 1
    import math
    if not math.isfinite(args.wall_timeout_seconds) or args.wall_timeout_seconds <= 0:
        print(f"ERROR: --wall-timeout-seconds must be finite and > 0, got {args.wall_timeout_seconds}", file=sys.stderr)
        return 1

    candidate = _artifact_binding(
        args.candidate_artifact_id, args.candidate_agent, args.candidate_deck, args.candidate_params
    )
    baseline = _artifact_binding(
        args.baseline_artifact_id, args.baseline_agent, args.baseline_deck, args.baseline_params
    )
    if candidate["sha256"] == baseline["sha256"]:
        print("ERROR: candidate and baseline artifacts are byte-identical; refusing to "
              "produce a manifest that would compare an artifact against itself.", file=sys.stderr)
        return 1

    protocol_identity = {
        "id": args.protocol_id,
        "step_limit": 2000,
        # games_per_worker/wall_timeout_seconds are the SOLE source of truth for `run` --
        # `run` reads them back out of this manifest rather than accepting its own
        # independent CLI values, so the executed protocol can never silently diverge from
        # the one bound into comparison_manifest_sha256.
        "games_per_worker": args.games_per_worker,
        "wall_timeout_seconds": str(args.wall_timeout_seconds),
        "worker_model": "one_subprocess_per_batch_of_games_per_worker",
        "seat_alternation_rule": "head_to_head.py --first-player, alternated across scheduled attempts",
        "decision_time_measurement": "wall-clock time.perf_counter() per agent decision, tagged actor=a|b; summarize uses only actor=a (the arm under measurement)",
        "game_rng_control": {"availability": "UNAVAILABLE", "reason": "no seed/RNG-control parameter exists anywhere in cg.api/cg.game's Python surface"},
    }
    dataset_identity = {
        "id": args.dataset_id,
        "version": args.dataset_version,
        "required_opponents": list(schema.REQUIRED_LEAGUE_OPPONENTS),
        "auxiliary_opponents": [opponent_registry.MIRROR_OPPONENT_ID],
    }
    protocol_sha256 = sha256_hex(protocol_identity)
    dataset_sha256 = sha256_hex(dataset_identity)

    manifest = {
        "schema_version": "1",
        "stage": args.stage,
        "candidate_role": args.candidate_role,
        "protocol_identity": {**protocol_identity, "sha256": protocol_sha256},
        "dataset_identity": {**dataset_identity, "sha256": dataset_sha256},
        "candidate_artifact": candidate,
        "baseline_artifact": baseline,
    }
    comparison_identity = {
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
    print(f"Wrote manifest to {args.out} (comparison_manifest_sha256={manifest['comparison_manifest_sha256'][:12]}...)")
    return 0


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------

def _manifest_hash8(manifest: dict) -> str:
    """Short form for display/log messages and the (non-security-relevant)
    run_index.json filename ONLY. Never used for the reuse-rejection binding
    below -- an 8-hex prefix is not a strong enough identity guard against a
    renamed/mismatched file, so per-(opponent,arm) jsonl filenames use the
    FULL 64-hex comparison_manifest_sha256 instead (_jsonl_filename)."""
    return manifest["comparison_manifest_sha256"][:8]


def _manifest_hash_full(manifest: dict) -> str:
    return manifest["comparison_manifest_sha256"]


def _jsonl_filename(manifest: dict, opponent_id: str, arm: str) -> str:
    return f"{_manifest_hash_full(manifest)}__{opponent_id}__{arm}.jsonl"


def _resolve_opponent_agent_deck(res: opponent_registry.OpponentResolution, manifest: dict, arm: str):
    """For 'mirror', the opponent IS the arm's own artifact (self-play)."""
    if res.opponent_id == opponent_registry.MIRROR_OPPONENT_ID:
        artifact = manifest["candidate_artifact"] if arm == "candidate" else manifest["baseline_artifact"]
        return artifact["agent_path"], artifact["deck_path"]
    if res.agent_path is not None:
        return os.path.join(_REPO_ROOT, res.agent_path), os.path.join(_REPO_ROOT, res.deck_path)
    return None, None  # pinned_clone opponents resolved separately via clone_opponent


def _count_lines(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def _verify_manifest_integrity(manifest: dict) -> str | None:
    """Recompute protocol_identity/dataset_identity/comparison_manifest_sha256 from the
    manifest's OWN stored fields (mirroring cmd_manifest's exact construction) and confirm
    they match the manifest's own stored hashes. Catches a hand-edited manifest -- e.g.
    games_per_worker or wall_timeout_seconds changed in the JSON file after `manifest` wrote
    it -- whose content no longer matches what comparison_manifest_sha256 claims to identify.
    Both `run` and `summarize` call this before trusting anything else in the manifest.
    Returns an error string on any mismatch, else None."""
    protocol_identity = dict(manifest.get("protocol_identity", {}))
    stored_protocol_sha256 = protocol_identity.pop("sha256", None)
    recomputed_protocol_sha256 = sha256_hex(protocol_identity)
    if recomputed_protocol_sha256 != stored_protocol_sha256:
        return (f"protocol_identity hash mismatch: manifest claims {stored_protocol_sha256!r}, "
                f"recomputed {recomputed_protocol_sha256!r} -- protocol_identity (e.g. "
                f"games_per_worker/wall_timeout_seconds) was edited after `manifest` wrote this file")

    dataset_identity = dict(manifest.get("dataset_identity", {}))
    stored_dataset_sha256 = dataset_identity.pop("sha256", None)
    recomputed_dataset_sha256 = sha256_hex(dataset_identity)
    if recomputed_dataset_sha256 != stored_dataset_sha256:
        return (f"dataset_identity hash mismatch: manifest claims {stored_dataset_sha256!r}, "
                f"recomputed {recomputed_dataset_sha256!r} -- dataset_identity was edited "
                f"after `manifest` wrote this file")

    candidate = manifest.get("candidate_artifact", {})
    baseline = manifest.get("baseline_artifact", {})
    comparison_identity = {
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
    """Rehash an artifact's files against the sha256 recorded in the
    manifest at `manifest` time; returns an error string if they no longer
    match (the artifact changed on disk since manifest was created), else
    None."""
    files = [artifact["agent_path"], artifact["deck_path"]] + (
        [artifact["params_path"]] if artifact.get("params_path") else []
    )
    actual = _sha256_of_file_bytes([os.path.join(_REPO_ROOT, p) if not os.path.isabs(p) else p for p in files])
    if actual != artifact["sha256"]:
        return (f"artifact {artifact['artifact_id']!r} sha256 mismatch: manifest recorded "
                f"{artifact['sha256'][:12]}..., current files hash to {actual[:12]}... "
                f"(files changed since `manifest` was written)")
    return None


def cmd_run(args: argparse.Namespace) -> int:
    if args.games_per_segment < 1:
        print("ERROR: --games-per-segment must be >= 1", file=sys.stderr)
        return 1

    with open(args.manifest, encoding="utf-8") as f:
        manifest = json.load(f)

    integrity_error = _verify_manifest_integrity(manifest)
    if integrity_error:
        print(f"ERROR: {integrity_error}", file=sys.stderr)
        return 1

    # games_per_worker/wall_timeout_seconds are read from the manifest's OWN
    # protocol_identity, never from an independent CLI flag on `run` -- this
    # is what actually got hashed into comparison_manifest_sha256 at
    # `manifest` time, so the executed protocol cannot silently diverge from
    # the one the manifest identifies.
    games_per_worker = manifest["protocol_identity"]["games_per_worker"]
    wall_timeout_seconds = float(manifest["protocol_identity"]["wall_timeout_seconds"])
    if games_per_worker < 1:
        print(f"ERROR: manifest's protocol_identity.games_per_worker must be >= 1, got {games_per_worker}", file=sys.stderr)
        return 1

    for artifact_key in ("candidate_artifact", "baseline_artifact"):
        mismatch = _verify_artifact_unchanged(manifest[artifact_key])
        if mismatch:
            print(f"ERROR: {mismatch}", file=sys.stderr)
            return 1

    pins = opponent_registry.load_pins(_PINS_PATH)
    os.makedirs(args.jsonl_out, exist_ok=True)
    clone_dest_root = tempfile.mkdtemp(prefix="eval_infra_run_clones_")

    skipped: list[dict] = []
    executed: list[dict] = []
    subprocess_errors: list[dict] = []
    try:
        for opponent_id in args.opponent:
            res = opponent_registry.resolve_opponent(opponent_id, pins, _REPO_ROOT)
            opp_agent_by_arm: dict[str, tuple[str, str]] = {}

            if res.availability == opponent_registry.AVAILABLE:
                for arm in ("baseline", "candidate"):
                    opp_agent_by_arm[arm] = _resolve_opponent_agent_deck(res, manifest, arm)
            elif res.availability == opponent_registry.PARTIAL and res.requires_clone and res.commit_sha:
                entry = pins.get(opponent_id, {})
                repo_url = entry.get("repo_url") if isinstance(entry, dict) else None
                file_paths = entry.get("file_paths") if isinstance(entry, dict) else None
                if not repo_url or not file_paths or len(file_paths) != 2:
                    skipped.append({"opponent_id": opponent_id, "availability": "UNAVAILABLE",
                                     "reason": "opponent_pins.json entry has a commit_sha but is missing "
                                               "repo_url or exactly-2-entry file_paths (agent, deck)"})
                    continue
                try:
                    dest_dir = os.path.join(clone_dest_root, opponent_id)
                    clone_result = clone_opponent.clone_and_verify(
                        opponent_id, repo_url, res.commit_sha, tuple(file_paths), dest_dir,
                    )
                    agent_abs, deck_abs = clone_result.files[0].absolute_path, clone_result.files[1].absolute_path
                    for arm in ("baseline", "candidate"):
                        opp_agent_by_arm[arm] = (agent_abs, deck_abs)
                except clone_opponent.ClonePinError as exc:
                    skipped.append({"opponent_id": opponent_id, "availability": "UNAVAILABLE",
                                     "reason": f"clone_and_verify failed: {exc}"})
                    continue
            else:
                skipped.append({"opponent_id": opponent_id, "availability": res.availability, "reason": res.reason})
                continue

            for arm in ("baseline", "candidate"):
                opp_agent, opp_deck = opp_agent_by_arm.get(arm, (None, None))
                if opp_agent is None:
                    skipped.append({"opponent_id": opponent_id, "arm": arm, "reason": "opponent resolution failed for this arm"})
                    continue
                arm_artifact = manifest["candidate_artifact"] if arm == "candidate" else manifest["baseline_artifact"]
                out_path = os.path.join(args.jsonl_out, _jsonl_filename(manifest, opponent_id, arm))
                if os.path.exists(out_path):
                    subprocess_errors.append({"opponent_id": opponent_id, "arm": arm,
                                               "reason": f"refusing to append to an already-existing jsonl "
                                                         f"output file (rerun with a fresh --jsonl-out dir): {out_path}"})
                    continue
                arm_had_error = False
                env = os.environ.copy()
                if arm_artifact.get("params_path"):
                    params_abs = (arm_artifact["params_path"] if os.path.isabs(arm_artifact["params_path"])
                                  else os.path.join(_REPO_ROOT, arm_artifact["params_path"]))
                    env["POKEMON_AI_PARAMS_PATH"] = params_abs
                else:
                    # Explicitly clear rather than inherit -- a stale value in the
                    # orchestrator's own environment must not silently affect a run whose
                    # manifest did not bind a params file.
                    env.pop("POKEMON_AI_PARAMS_PATH", None)

                games_run = 0
                games_confirmed = 0
                while games_run < args.games_per_segment:
                    batch = min(games_per_worker, args.games_per_segment - games_run)
                    first_player = "a" if (games_run // games_per_worker) % 2 == 0 else "b"
                    lines_before = _count_lines(out_path)
                    cmd = [
                        sys.executable, _HEAD_TO_HEAD_PATH,
                        "--agent-a", arm_artifact["agent_path"], "--deck-a", arm_artifact["deck_path"],
                        "--agent-b", opp_agent, "--deck-b", opp_deck,
                        "--n", str(batch), "--first-player", first_player,
                        "--jsonl-out", out_path, "--record-decision-timing",
                        "--label-a", arm, "--label-b", opponent_id,
                    ]
                    try:
                        proc = subprocess.run(cmd, timeout=wall_timeout_seconds, capture_output=True, text=True, env=env)
                        lines_after = _count_lines(out_path)
                        new_lines = lines_after - lines_before
                        if proc.returncode != 0:
                            # e.g. head_to_head.py's own win32 guard on a non-Linux host, or any
                            # other subprocess failure. Must NOT be silently reported as executed.
                            subprocess_errors.append({
                                "opponent_id": opponent_id, "arm": arm, "batch_start": games_run,
                                "returncode": proc.returncode,
                                "stderr": proc.stderr.strip()[-2000:],
                                "stdout": proc.stdout.strip()[-2000:],
                            })
                            arm_had_error = True
                            break
                        if new_lines != batch:
                            # Zero exit code but the wrong number of records written -- must
                            # not be silently reported as fully executed.
                            subprocess_errors.append({
                                "opponent_id": opponent_id, "arm": arm, "batch_start": games_run,
                                "reason": f"subprocess exited 0 but wrote {new_lines} jsonl record(s), expected {batch}",
                            })
                            arm_had_error = True
                            break
                        games_confirmed += new_lines
                    except subprocess.TimeoutExpired:
                        # Parent-synthesized incomplete record: head_to_head.py cannot observe
                        # its own hang, so only the orchestrator (here) can write this. The
                        # timed-out subprocess may have already flushed some real records
                        # before hanging (relevant when games_per_worker > 1) -- recount actual
                        # lines rather than assuming zero.
                        lines_at_timeout = _count_lines(out_path)
                        real_new_lines = max(0, lines_at_timeout - lines_before)
                        if real_new_lines >= batch:
                            # The subprocess had already fully completed this batch's real
                            # records before hanging (e.g. during interpreter/native-library
                            # shutdown, not mid-game) -- the file already has exactly `batch`
                            # new real lines. Do NOT append a synthesized record here: an
                            # internal counter can be capped, but the already-written real
                            # lines on disk cannot be un-written, so appending one more line
                            # would leave the physical jsonl file with MORE than `batch` lines
                            # regardless of how the counter is capped. Treat this batch as
                            # genuinely, fully completed instead.
                            games_confirmed += batch
                            games_run += batch
                            continue
                        with open(out_path, "a", encoding="utf-8") as jf:
                            jf.write(json.dumps({
                                "schema_version": "1", "game_index": games_run + real_new_lines,
                                "first_seat_agent": first_player, "label_a": arm, "label_b": opponent_id,
                                "termination": {"category": "timeout", "kind": "wall_clock"},
                                "result": None, "error_actor": None, "legality": "unknown",
                                "decisions": None,
                            }) + "\n")
                        advanced = real_new_lines + 1
                        games_confirmed += advanced
                        games_run += advanced
                        continue
                    games_run += batch

                if not arm_had_error:
                    executed.append({"opponent_id": opponent_id, "arm": arm, "jsonl_path": out_path, "games": games_confirmed})
    finally:
        shutil.rmtree(clone_dest_root, ignore_errors=True)

    partial = bool(skipped) or bool(subprocess_errors)
    if subprocess_errors and not args.allow_partial:
        print(f"ERROR: {len(subprocess_errors)} head_to_head.py subprocess invocation(s) "
              f"failed and --allow-partial not set: {subprocess_errors}", file=sys.stderr)
        return 1
    if skipped and not args.allow_partial:
        print(f"ERROR: fail-closed: {len(skipped)} opponent/arm combination(s) unavailable and "
              f"--allow-partial not set: {skipped}", file=sys.stderr)
        return 1

    run_index = {
        "comparison_manifest_sha256": manifest["comparison_manifest_sha256"],
        "partial_diagnostic": partial,
        "skipped": skipped,
        "subprocess_errors": subprocess_errors,
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

_KNOWN_OPPONENT_IDS = frozenset(schema.REQUIRED_LEAGUE_OPPONENTS) | {opponent_registry.MIRROR_OPPONENT_ID}


def _load_and_validate_jsonl(path: str, manifest_hash_full: str, expected_opponent_id: str, expected_arm: str) -> list[dict]:
    basename = os.path.basename(path)
    if not basename.startswith(manifest_hash_full + "__"):
        raise schema.SchemaError(
            f"REUSE_REJECTED: {basename!r} does not carry the expected FULL 64-hex manifest "
            f"hash prefix {manifest_hash_full!r} -- refusing to mix games collected under a "
            f"different manifest."
        )
    records = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            rec = schema.validate_game_record(json.loads(line))
            # label_a/label_b are set by cmd_run to exactly (arm, opponent_id) -- cross-check
            # them against the filename-derived (expected_arm, expected_opponent_id) so a
            # mismatched/hand-edited/misnamed file is rejected rather than silently trusted.
            if rec["label_a"] != expected_arm or rec["label_b"] != expected_opponent_id:
                raise schema.SchemaError(
                    f"RECORD_LABEL_MISMATCH in {basename!r} line {line_no}: "
                    f"record says label_a={rec['label_a']!r} label_b={rec['label_b']!r}, "
                    f"filename implies arm={expected_arm!r} opponent_id={expected_opponent_id!r}"
                )
            records.append(rec)
    return records


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
    == 'a' -- cmd_run always invokes head_to_head.py with the arm as
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
    if not b_games or not c_games:
        return None
    pfn = percentile_statistic(pct)
    b_pooled = [v for g in b_games for v in g]
    c_pooled = [v for g in c_games for v in g]
    b_stats = percentile_interval(b_pooled, pct, confidence)
    c_stats = percentile_interval(c_pooled, pct, confidence)
    seed_material = {
        "comparison_manifest_sha256": manifest_hash, "metric_id": metric_id,
        "segment_id": segment_id, "rng_seed": rng_seed,
    }
    delta = game_cluster_bootstrap_delta(b_games, c_games, pfn, seed_material, replicates, confidence)
    # `observations` reflects the number of GAME CLUSTERS actually backing the bootstrap
    # (b_games/c_games, after _arm_own_decision_durations_ms already dropped games with no
    # captured own-decision at all) -- NOT the raw baseline_records+candidate_records game
    # count, which would overstate coverage if some games contributed zero latency samples
    # (e.g. decisions=None because --record-decision-timing was off for that game, or an
    # engine_null_start game with no decisions to time at all).
    return schema.build_cell(metric_id, segment_id, len(b_games) + len(c_games), b_stats, c_stats, delta)


def _observation_count_cell(baseline_records: list[dict], candidate_records: list[dict], segment_id: str) -> dict | None:
    b_games = _arm_own_decision_durations_ms(baseline_records)
    c_games = _arm_own_decision_durations_ms(candidate_records)
    if b_games is None or c_games is None:
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
            if opponent_id not in _KNOWN_OPPONENT_IDS:
                raise schema.SchemaError(
                    f"UNKNOWN_OPPONENT: {basename!r} implies opponent_id={opponent_id!r}, "
                    f"which is not one of {sorted(_KNOWN_OPPONENT_IDS)}"
                )
            if arm not in ("baseline", "candidate"):
                raise schema.SchemaError(f"UNKNOWN_ARM: {basename!r} implies arm={arm!r}, expected baseline/candidate")
            key = (opponent_id, arm)
            if key in all_records:
                raise schema.SchemaError(f"DUPLICATE_JSONL_INPUT: (opponent_id={opponent_id!r}, arm={arm!r}) "
                                          f"supplied more than once across --jsonl-in arguments")
            all_records[key] = _load_and_validate_jsonl(path, manifest_hash, opponent_id, arm)
    except schema.SchemaError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
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
    for seat_val, seg_id in (("a", schema.SEGMENT_FIRST_PLAYER), ("b", schema.SEGMENT_SECOND_PLAYER)):
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
    # numerator and denominator, per the three-bucket model documented in README.md's F2. A
    # naive _rate_cell(..., lambda r: r["legality"]=="illegal") over ALL records (including
    # "unknown" ones) would silently count every unknown case as a non-illegal observation,
    # diluting/suppressing the reported rate -- exactly the bug an earlier heterogeneous-
    # model audit pass (Codex Final Auditor) found and this filtering fixes.
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
    }

    report = {
        "schema_version": "1",
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
    print(f"Wrote Measurement Report to {args.out} ({len(cells)} cells)")
    return 0


# --------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="raging_bolt evaluation infrastructure CLI")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_manifest = sub.add_parser("manifest", help="Write a comparison manifest (protocol/dataset/artifact identities)")
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
    p_manifest.add_argument("--games-per-worker", type=int, default=1)
    p_manifest.add_argument("--wall-timeout-seconds", type=float, default=120.0)
    p_manifest.add_argument("--out", required=True)
    p_manifest.set_defaults(func=cmd_manifest)

    p_run = sub.add_parser("run", help="Play the scheduled games for a manifest")
    p_run.add_argument("--manifest", required=True)
    p_run.add_argument("--opponent", action="append", required=True,
                        help="Repeatable. Must be one of lucario/dragapult/megastarmie/mirror.")
    p_run.add_argument("--games-per-segment", type=int, required=True)
    # games_per_worker/wall_timeout_seconds are NOT CLI flags here -- they are read from
    # --manifest's own protocol_identity (set once, at `manifest` time) so the executed
    # protocol can never silently diverge from what comparison_manifest_sha256 identifies.
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
    p_summarize.add_argument("--out", required=True)
    p_summarize.set_defaults(func=cmd_summarize)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
