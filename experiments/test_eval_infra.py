"""
Tests for experiments/eval_infra/ (the raging_bolt evaluation infrastructure).

Windows-runnable (T1-T17 below): no cabt engine execution, no network.
Follows the existing custom PASS/FAIL script-harness convention used by
experiments/test_cabt_runner_scripts.py (no pytest anywhere in this repo).

Explicitly NOT covered here (Linux-only, deferred, never claimed as run from
this session -- see experiments/eval_infra/README.md caveats F1/F8/F9):

  L1. End-to-end experiments/head_to_head.py --jsonl-out over real games,
      verifying the emitted record shape against real engine output
      (including a real engine IndexError if one can be provoked, and a
      real agent_exception).
  L2. Parent wall-timeout: force a hang and confirm
      experiments/eval_infra/raging_bolt_eval.py's `run` kills the
      subprocess and synthesizes a termination.kind="wall_clock" record.
  L3. Full `run` -> `summarize` round trip against real, genuinely pinned
      opponent clones (network required), spot-checked by hand.

Run: python experiments/test_eval_infra.py
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)

PASS = "[PASS]"
FAIL = "[FAIL]"
_failures = 0
_total = 0


def check(label, condition):
    global _failures, _total
    _total += 1
    status = PASS if condition else FAIL
    print("  %s  %s" % (status, label))
    if not condition:
        _failures += 1


CLI_MODULE_PATH = os.path.join(_REPO_ROOT, "experiments", "eval_infra", "raging_bolt_eval.py")


def run_cli(*args, timeout=30):
    return subprocess.run(
        [sys.executable, "-m", "experiments.eval_infra.raging_bolt_eval", *args],
        cwd=_REPO_ROOT, capture_output=True, text=True, timeout=timeout,
    )


# ---------------------------------------------------------------------------
# T1 / T2: canonicalization drift guard against the REAL tools/outcome_gatekeeper.py
# ---------------------------------------------------------------------------
print("=== T1/T2: canonicalization drift guard (test-only import) ===")

from experiments.eval_infra.canon import canonicalize  # noqa: E402
from tools.outcome_gatekeeper import canonical_profile_bytes  # test-only, read-only import  # noqa: E402

_EXAMPLE_PROFILE_PATH = os.path.join(_REPO_ROOT, "profiles", "outcome", "pokemon-ai.example.json")
with open(_EXAMPLE_PROFILE_PATH, encoding="utf-8") as _f:
    _GATEKEEPER_REAL_PROFILE = json.load(_f)

_FIXTURES = [
    {"b": 1, "a": 2},
    {"a": {"z": 1, "y": 2}, "b": [1, 2, 3]},
    {"unicode": "\u65e5\u672c\u8a9e"},
    {"negative": -1, "decimal_like": "1.50"},
]
# key-order variants of the same logical content, to prove sort_keys parity
_FIXTURES.append({"z": 1, "a": 2, "m": 3})
_FIXTURES.append({"a": 2, "m": 3, "z": 1})

for i, fx in enumerate(_FIXTURES):
    ours = canonicalize(fx)
    theirs = json.dumps(fx, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    check(f"canonicalize() matches raw json.dumps recipe byte-for-byte [fixture {i}]", ours == theirs)

# byte-for-byte against the REAL Gatekeeper function on the actual, real example Profile
_gk_bytes = canonical_profile_bytes(_GATEKEEPER_REAL_PROFILE)
_our_bytes = canonicalize(_GATEKEEPER_REAL_PROFILE)
check("canonicalize() matches tools.outcome_gatekeeper.canonical_profile_bytes() byte-for-byte "
      "on the real profiles/outcome/pokemon-ai.example.json", _gk_bytes == _our_bytes)

_gk_src = open(os.path.join(_REPO_ROOT, "tools", "outcome_gatekeeper.py"), encoding="utf-8").read()
for kw in ('sort_keys=True', 'ensure_ascii=False', 'separators=(",", ":")', 'allow_nan=False'):
    check(f"tools/outcome_gatekeeper.py still contains kwarg {kw!r} (source-text drift guard)", kw in _gk_src)

# ---------------------------------------------------------------------------
# T3: hash stability / sensitivity
# ---------------------------------------------------------------------------
print("\n=== T3: hash stability / sensitivity ===")

from experiments.eval_infra.canon import sha256_hex  # noqa: E402

h1 = sha256_hex({"a": 1, "b": 2})
h2 = sha256_hex({"b": 2, "a": 1})
check("hash stable across key-insertion-order variants", h1 == h2)
h3 = sha256_hex({"a": 1, "b": 3})
check("hash sensitive to a single value change", h1 != h3)
import re as _re  # noqa: E402
check("sha256_hex output is 64 lowercase hex chars", bool(_re.fullmatch(r"[0-9a-f]{64}", h1)))

# ---------------------------------------------------------------------------
# T4: stats fixtures, including 0/n and n/n edge cases
# ---------------------------------------------------------------------------
print("\n=== T4: stats.py fixtures ===")

from experiments.eval_infra.stats import (  # noqa: E402
    exact_count_interval, game_cluster_bootstrap_delta, mean_statistic,
    newcombe_delta, percentile, percentile_statistic, wilson_interval,
)
from decimal import Decimal  # noqa: E402

try:
    wilson_interval(0, 0)
    check("wilson_interval(0, 0) raises ValueError", False)
except ValueError:
    check("wilson_interval(0, 0) raises ValueError", True)

w = wilson_interval(50, 100)
check("wilson_interval(50,100) estimate == 0.5", w.estimate == "0.5")
check("wilson_interval(50,100) lower/upper roughly symmetric around 0.5",
      abs((Decimal(w.upper) - Decimal("0.5")) - (Decimal("0.5") - Decimal(w.lower))) < Decimal("0.001"))

w0 = wilson_interval(0, 100)
check("wilson_interval(0,100) estimate is exactly 0", w0.estimate == "0")
check("wilson_interval(0,100) upper bound is strictly positive (finite n property)", Decimal(w0.upper) > 0)
w100 = wilson_interval(100, 100)
check("wilson_interval(100,100) estimate is exactly 1", w100.estimate == "1")
check("wilson_interval(100,100) lower bound is strictly less than 1 (finite n property)", Decimal(w100.lower) < 1)

for triple in (w, w0, w100):
    check(f"wilson_interval({triple}) satisfies lower<=estimate<=upper",
          Decimal(triple.lower) <= Decimal(triple.estimate) <= Decimal(triple.upper))

nd = newcombe_delta(20, 100, 30, 100)
check("newcombe_delta satisfies lower<=estimate<=upper", Decimal(nd.lower) <= Decimal(nd.estimate) <= Decimal(nd.upper))
check("newcombe_delta estimate == candidate - baseline point estimates", nd.estimate == "0.1")
# Fixed numeric reference values for the actual Newcombe-Wilson hybrid formula (Newcombe
# 1998, "Method 10"), independently computed: baseline 20/100, candidate 30/100 ->
# lower~=-0.020249, upper~=0.216735. An earlier implementation used naive interval
# subtraction (delta_lo = c_lo - b_hi / delta_hi = c_hi - b_lo) instead of this formula,
# which is a valid but needlessly wide bound, not the standard Newcombe method -- caught by
# an earlier heterogeneous-model audit pass. This test pins the corrected formula's exact
# output so that regression is caught immediately, not just "some interval was produced".
check(f"newcombe_delta(20,100,30,100) matches the Newcombe-Wilson reference interval "
      f"(got lower={nd.lower!r}, upper={nd.upper!r})",
      abs(Decimal(nd.lower) - Decimal("-0.020249")) < Decimal("0.001") and
      abs(Decimal(nd.upper) - Decimal("0.216735")) < Decimal("0.001"))

check("percentile([1..5], 50) == 3", percentile([1, 2, 3, 4, 5], 50) == 3)
check("percentile([1..5], 0) == 1 (min)", percentile([1, 2, 3, 4, 5], 0) == 1)
check("percentile([1..5], 100) == 5 (max)", percentile([1, 2, 3, 4, 5], 100) == 5)

try:
    percentile([], 50)
    check("percentile([]) raises ValueError", False)
except ValueError:
    check("percentile([]) raises ValueError", True)

eci = exact_count_interval(42)
check("exact_count_interval is degenerate (estimate==lower==upper)", eci.estimate == eci.lower == eci.upper == "42")

# ---------------------------------------------------------------------------
# T5: whole-game (not per-decision) bootstrap resampling unit
# ---------------------------------------------------------------------------
print("\n=== T5: whole-game cluster bootstrap resampling unit ===")

seed = {"comparison_manifest_sha256": "fixture", "metric_id": "win_rate", "segment_id": "overall"}
b_games = [[1.0], [0.0], [1.0], [1.0], [0.0]] * 4
c_games = [[1.0], [1.0], [1.0], [0.0], [1.0]] * 4
r1 = game_cluster_bootstrap_delta(b_games, c_games, mean_statistic, seed, replicates=500)
r2 = game_cluster_bootstrap_delta(b_games, c_games, mean_statistic, seed, replicates=500)
check("game_cluster_bootstrap_delta is deterministic given identical seed_material", r1 == r2)
seed_other_metric = {**seed, "metric_id": "different_metric"}
r3 = game_cluster_bootstrap_delta(b_games, c_games, mean_statistic, seed_other_metric, replicates=500)
check("game_cluster_bootstrap_delta output changes when seed_material's metric_id changes", r1 != r3)

# whole-game-vs-per-decision distinction: build a fixture where every decision
# within a game is IDENTICAL but games differ sharply, and confirm resampling
# WHOLE GAMES together (not decisions independently) reproduces the expected
# per-game variance rather than an artificially narrow per-decision variance.
lat_baseline_games = [[100.0, 100.0, 100.0]] * 3 + [[10.0, 10.0, 10.0]] * 3  # 2 distinct game-level values
lat_candidate_games = [[95.0, 95.0, 95.0]] * 3 + [[9.0, 9.0, 9.0]] * 3
p50fn = percentile_statistic(50)
lat_delta = game_cluster_bootstrap_delta(lat_baseline_games, lat_candidate_games, p50fn,
                                          {**seed, "metric_id": "decision_time_p50_ms"}, replicates=2000)
# Each arm has exactly 6 GAMES (3 all-high, 3 all-low), each game internally
# homogeneous (3 identical decisions). Resampling WHOLE GAMES draws with
# replacement from only 6 correlated clusters per arm, so the resampled
# median can only ever land on one of 3 discrete values per arm (whichever
# cluster type dominates the 6 draws, or the interpolated midpoint on an
# exact 3-3 split) -- giving a WIDE possible delta range (theoretically
# [-91, 85] here). Resampling at the DECISION level instead (18 effectively
# independent draws per arm from the same pooled multiset) would have a much
# larger effective sample size and thus concentrate tightly around the
# dead-center delta (~-3), producing a MUCH NARROWER interval. This test
# distinguishes the two by requiring a wide interval, which only whole-game
# clustering produces for this fixture.
lat_width = Decimal(lat_delta.upper) - Decimal(lat_delta.lower)
check(f"lat_delta interval is wide ({lat_delta.lower}..{lat_delta.upper}, width={lat_width}), "
      "consistent with whole-game (not per-decision) resampling variance",
      lat_width > Decimal("50"))

try:
    game_cluster_bootstrap_delta([], c_games, mean_statistic, seed)
    check("game_cluster_bootstrap_delta([], ...) raises ValueError", False)
except ValueError:
    check("game_cluster_bootstrap_delta([], ...) raises ValueError", True)

# ---------------------------------------------------------------------------
# T6: every cell always has delta_stats, including guardrail metrics; zero
# observations must never produce a cell with observations: 0
# ---------------------------------------------------------------------------
print("\n=== T6: cell shape (schema.build_cell) ===")

from experiments.eval_infra import schema  # noqa: E402

for metric_id in (schema.METRIC_WIN_RATE, schema.METRIC_ILLEGAL_ACTION_RATE, schema.METRIC_DECISION_TIME_P95_MS):
    cell = schema.build_cell(metric_id, schema.SEGMENT_OVERALL, 10, w.as_dict(), w.as_dict(), nd.as_dict())
    check(f"build_cell({metric_id}) has exactly the 6 required keys",
          set(cell) == schema.CELL_REQUIRED_KEYS)
    check(f"build_cell({metric_id}) always includes delta_stats", "delta_stats" in cell and cell["delta_stats"] is not None)

try:
    schema.build_cell(schema.METRIC_WIN_RATE, schema.SEGMENT_OVERALL, 0, w.as_dict(), w.as_dict(), nd.as_dict())
    check("build_cell with observations=0 raises (must be omitted by caller instead)", False)
except schema.SchemaError:
    check("build_cell with observations=0 raises (must be omitted by caller instead)", True)

try:
    schema.validate_stats_triple({"estimate": "0.5", "lower": "0.6", "upper": "0.4"})
    check("validate_stats_triple rejects lower>upper", False)
except schema.SchemaError:
    check("validate_stats_triple rejects lower>upper", True)

# ---------------------------------------------------------------------------
# T7: metric/segment ID alignment to the example App Profile (fixture-only,
# never loads the Profile as active config)
# ---------------------------------------------------------------------------
print("\n=== T7: metric/segment ID alignment (fixture-only compat) ===")

if os.path.exists(_EXAMPLE_PROFILE_PATH):
    _profile = _GATEKEEPER_REAL_PROFILE
    _profile_metric_ids = {m["id"] for m in _profile.get("metrics", [])}
    _profile_segment_ids = {s["id"] for s in _profile.get("segments", [])}
    for mid in (schema.METRIC_WIN_RATE, schema.METRIC_ERROR_RATE, schema.METRIC_TIMEOUT_RATE,
                schema.METRIC_ILLEGAL_ACTION_RATE, schema.METRIC_DECISION_TIME_P95_MS):
        check(f"harness metric ID {mid!r} matches an ID in the example Profile", mid in _profile_metric_ids)
    for sid in schema.LEAGUE_SEGMENT_IDS:
        check(f"harness segment ID {sid!r} matches an ID in the example Profile", sid in _profile_segment_ids)
    check("harness's auxiliary 'mirror' segment is NOT in the example Profile's segment list "
          "(mirror never feeds a league cell)", schema.SEGMENT_MIRROR not in _profile_segment_ids)
else:
    check("profiles/outcome/pokemon-ai.example.json exists (skipping ID-alignment checks otherwise)", False)

# ---------------------------------------------------------------------------
# T8: opponent_registry -- injected temp paths only, never real gitignored files
# ---------------------------------------------------------------------------
print("\n=== T8: opponent_registry.py (injected paths, not real worktree state) ===")

from experiments.eval_infra import opponent_registry  # noqa: E402

_tmp_repo = tempfile.mkdtemp(prefix="eval_infra_registry_test_")
try:
    res_missing = opponent_registry.resolve_opponent("lucario", {}, _tmp_repo)
    check("lucario UNAVAILABLE when injected repo_root has no local files", res_missing.availability == opponent_registry.UNAVAILABLE)

    _agent_dir = os.path.join(_tmp_repo, "experiments", "agents")
    _deck_dir = os.path.join(_tmp_repo, "experiments", "decks")
    os.makedirs(_agent_dir, exist_ok=True)
    os.makedirs(_deck_dir, exist_ok=True)
    open(os.path.join(_agent_dir, "top_lucario_1084_main.py"), "w").close()
    open(os.path.join(_deck_dir, "top_lucario_1084.csv"), "w").close()
    res_present = opponent_registry.resolve_opponent("lucario", {}, _tmp_repo)
    check("lucario AVAILABLE when injected repo_root has both local files present", res_present.availability == opponent_registry.AVAILABLE)

    res_mirror = opponent_registry.resolve_opponent("mirror", {}, _tmp_repo)
    check("mirror is always AVAILABLE, requires no pin/clone", res_mirror.availability == opponent_registry.AVAILABLE and not res_mirror.requires_clone)

    res_no_pin = opponent_registry.resolve_opponent("dragapult", {}, _tmp_repo)
    check("dragapult UNAVAILABLE with empty pins dict", res_no_pin.availability == opponent_registry.UNAVAILABLE)

    res_bad_pin = opponent_registry.resolve_opponent("dragapult", {"dragapult": {"commit_sha": "not-40-hex"}}, _tmp_repo)
    check("dragapult UNAVAILABLE with malformed commit_sha", res_bad_pin.availability == opponent_registry.UNAVAILABLE)

    good_sha = "a" * 40
    res_good_pin = opponent_registry.resolve_opponent("dragapult", {"dragapult": {"commit_sha": good_sha}}, _tmp_repo)
    check("dragapult PARTIAL with a well-formed pinned commit_sha (not yet clone-verified)",
          res_good_pin.availability == opponent_registry.PARTIAL and res_good_pin.commit_sha == good_sha)

    res_unknown = opponent_registry.resolve_opponent("not_a_real_opponent", {}, _tmp_repo)
    check("unknown opponent_id resolves UNAVAILABLE, does not raise", res_unknown.availability == opponent_registry.UNAVAILABLE)
finally:
    shutil.rmtree(_tmp_repo, ignore_errors=True)

# ---------------------------------------------------------------------------
# T9: clone_opponent.py hardening against a synthetic LOCAL git repo (no network)
# ---------------------------------------------------------------------------
print("\n=== T9: clone_opponent.py (synthetic local git repo, no network) ===")

from experiments.eval_infra.clone_opponent import ClonePinError, clone_and_verify  # noqa: E402

_synth_repo = tempfile.mkdtemp(prefix="eval_infra_synth_repo_")
_git_available = shutil.which("git") is not None
_commit_sha = None
try:
    if _git_available:
        def _git(*args):
            subprocess.run(["git", *args], cwd=_synth_repo, check=True, capture_output=True)

        _git("init", "-q")
        _git("config", "user.email", "test@example.com")
        _git("config", "user.name", "test")
        os.makedirs(os.path.join(_synth_repo, "agents", "fake"), exist_ok=True)
        with open(os.path.join(_synth_repo, "agents", "fake", "main.py"), "w", encoding="utf-8") as f:
            f.write("def agent(obs): return []\n")
        with open(os.path.join(_synth_repo, "agents", "fake", "deck.csv"), "w", encoding="utf-8") as f:
            f.write("1\n2\n3\n")
        _git("add", "agents")
        _git("commit", "-q", "-m", "init")
        _commit_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=_synth_repo, check=True, capture_output=True, text=True
        ).stdout.strip()

    check("git is available in this environment (prerequisite for T9)", _git_available)
    _clone_dest = tempfile.mkdtemp(prefix="eval_infra_clone_dest_")
    if _git_available:
        result = clone_and_verify("dragapult", _synth_repo, _commit_sha,
                                   ("agents/fake/main.py", "agents/fake/deck.csv"), _clone_dest)
        check("clone_and_verify succeeds against a real local synthetic repo at the exact pinned commit",
              result.commit_sha == _commit_sha and len(result.files) == 2)
        check("clone_and_verify hashes are 64 lowercase hex", all(_re.fullmatch(r"[0-9a-f]{64}", f.sha256) for f in result.files))

        # Directly reproduces the bug an earlier heterogeneous-model audit pass (Codex Final
        # Auditor) found: an earlier implementation deleted the clone directory in `finally`
        # BEFORE the caller could use the returned paths, making them unusable. Confirm the
        # returned files still exist and are still readable AFTER clone_and_verify has
        # returned (i.e. after its internal clone-directory cleanup has already run).
        for cf in result.files:
            check(f"returned file {cf.repo_relative_path!r} still exists on disk after "
                  "clone_and_verify() returns (clone-dir cleanup must not delete it)",
                  os.path.isfile(cf.absolute_path))
            with open(cf.absolute_path, "rb") as fh:
                content = fh.read()
            reread_hash = __import__("hashlib").sha256(content).hexdigest()
            check(f"returned file {cf.repo_relative_path!r} is genuinely readable and its "
                  "content still matches the reported sha256", reread_hash == cf.sha256)
        try:
            clone_and_verify("dragapult", _synth_repo, "a" * 40, ("agents/fake/main.py",), _clone_dest)
            check("clone_and_verify rejects a well-formed but nonexistent commit_sha", False)
        except ClonePinError:
            check("clone_and_verify rejects a well-formed but nonexistent commit_sha", True)

        try:
            clone_and_verify("dragapult", _synth_repo, _commit_sha, ("../etc/passwd",), _clone_dest)
            check("clone_and_verify rejects a path-traversal file_paths entry", False)
        except ClonePinError:
            check("clone_and_verify rejects a path-traversal file_paths entry", True)

        try:
            clone_and_verify("dragapult", _synth_repo, _commit_sha, ("C:\\Windows\\System32\\drivers\\etc\\hosts",), _clone_dest)
            check("clone_and_verify rejects a backslash/absolute file_paths entry", False)
        except ClonePinError:
            check("clone_and_verify rejects a backslash/absolute file_paths entry", True)

        try:
            clone_and_verify("dragapult", "-evil-flag-injection", _commit_sha, ("agents/fake/main.py",), _clone_dest)
            check("clone_and_verify rejects a flag-like (leading '-') repo_url", False)
        except ClonePinError:
            check("clone_and_verify rejects a flag-like (leading '-') repo_url", True)

        try:
            clone_and_verify("dragapult", _synth_repo, "not-40-hex", ("agents/fake/main.py",), _clone_dest)
            check("clone_and_verify rejects a malformed (non-40-hex) commit_sha before touching git", False)
        except ClonePinError:
            check("clone_and_verify rejects a malformed (non-40-hex) commit_sha before touching git", True)
    shutil.rmtree(_clone_dest, ignore_errors=True)
finally:
    shutil.rmtree(_synth_repo, ignore_errors=True)

# ---------------------------------------------------------------------------
# T12/T13: CLI integration (manifest/run/summarize --help, overwrite refusal,
# fail-closed opponent resolution, reuse-rejection)
# ---------------------------------------------------------------------------
print("\n=== T12/T13: raging_bolt_eval.py CLI integration ===")

check("raging_bolt_eval.py file exists", os.path.exists(CLI_MODULE_PATH))
r_compile = subprocess.run([sys.executable, "-m", "py_compile", CLI_MODULE_PATH], capture_output=True, text=True)
check("raging_bolt_eval.py compiles", r_compile.returncode == 0)

for sub in ("manifest", "run", "summarize"):
    r = run_cli(sub, "--help")
    check(f"'{sub} --help' exits 0", r.returncode == 0)

_cli_tmp = tempfile.mkdtemp(prefix="eval_infra_cli_test_")
try:
    manifest_path = os.path.join(_cli_tmp, "manifest.json")
    r_manifest = run_cli(
        "manifest",
        "--candidate-agent", "experiments/agents/raging_bolt/main.py",
        "--candidate-deck", "experiments/decks/raging_bolt_ogerpon.csv",
        "--candidate-artifact-id", "candidate-v1",
        "--baseline-agent", "main.py", "--baseline-deck", "deck.csv", "--baseline-artifact-id", "baseline-v1",
        "--protocol-id", "proto-v1", "--dataset-id", "ds-v1", "--dataset-version", "1", "--stage", "screening",
        "--out", manifest_path,
    )
    check("manifest subcommand succeeds with distinct candidate/baseline artifacts", r_manifest.returncode == 0)
    check("manifest subcommand creates the output file", os.path.exists(manifest_path))

    r_manifest_again = run_cli(
        "manifest",
        "--candidate-agent", "experiments/agents/raging_bolt/main.py",
        "--candidate-deck", "experiments/decks/raging_bolt_ogerpon.csv",
        "--candidate-artifact-id", "candidate-v1",
        "--baseline-agent", "main.py", "--baseline-deck", "deck.csv", "--baseline-artifact-id", "baseline-v1",
        "--protocol-id", "proto-v1", "--dataset-id", "ds-v1", "--dataset-version", "1", "--stage", "screening",
        "--out", manifest_path,
    )
    check("manifest subcommand refuses to overwrite an existing manifest file", r_manifest_again.returncode != 0)

    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            _manifest_obj = json.load(f)
        # manifest_hash8 is used ONLY for the informational run_index.json filename (matches
        # cmd_run's own _manifest_hash8 usage there); every per-(opponent,arm) jsonl filename
        # must use the FULL 64-hex hash, matching cmd_run's _jsonl_filename/_manifest_hash_full.
        manifest_hash8 = _manifest_obj["comparison_manifest_sha256"][:8]
        manifest_hash_full = _manifest_obj["comparison_manifest_sha256"]
        check("manifest's games_per_worker/wall_timeout_seconds are recorded in protocol_identity",
              "games_per_worker" in _manifest_obj["protocol_identity"] and
              "wall_timeout_seconds" in _manifest_obj["protocol_identity"])

        jsonl_dir = os.path.join(_cli_tmp, "jsonl")

        r_zero_segment = run_cli(
            "run", "--manifest", manifest_path, "--opponent", "mirror",
            "--games-per-segment", "0", "--jsonl-out", jsonl_dir,
        )
        check("run subcommand rejects --games-per-segment 0", r_zero_segment.returncode != 0)

        # games_per_worker is now a `manifest`-time setting (bound into protocol_identity,
        # not an independently-settable `run` flag -- see the manifest/run protocol-identity
        # binding fix). `manifest --games-per-worker 0` is itself rejected at creation time
        # (see T17), and separately `run` no longer even accepts a --games-per-worker flag.
        r_run_flag_removed = run_cli(
            "run", "--manifest", manifest_path, "--opponent", "mirror",
            "--games-per-segment", "2", "--games-per-worker", "1", "--jsonl-out", jsonl_dir,
        )
        check("run subcommand no longer accepts a --games-per-worker flag at all "
              "(games_per_worker now comes exclusively from --manifest)",
              r_run_flag_removed.returncode != 0 and
              ("unrecognized arguments" in r_run_flag_removed.stderr or
               "unrecognized arguments" in r_run_flag_removed.stdout))

        r_run_fail_closed = run_cli(
            "run", "--manifest", manifest_path, "--opponent", "lucario",
            "--games-per-segment", "2", "--jsonl-out", jsonl_dir,
        )
        check("run subcommand fails closed (nonzero exit) when the only requested opponent is UNAVAILABLE "
              "and --allow-partial is not set", r_run_fail_closed.returncode != 0)

        r_run_partial = run_cli(
            "run", "--manifest", manifest_path, "--opponent", "lucario", "--opponent", "dragapult",
            "--games-per-segment", "2", "--jsonl-out", jsonl_dir, "--allow-partial",
        )
        check("run subcommand succeeds with --allow-partial when opponents are unavailable", r_run_partial.returncode == 0)
        # NOTE: read this run's index immediately -- a later `run` invocation into the same
        # --jsonl-out dir (the rerun-protection test below) writes its OWN run_index.json to
        # the same manifest-hash-derived filename, which would overwrite this one if read later.
        index_path = os.path.join(jsonl_dir, f"{manifest_hash8}__run_index.json")
        if os.path.exists(index_path):
            with open(index_path, encoding="utf-8") as f:
                _index = json.load(f)
            check("run index reports partial_diagnostic=true", _index.get("partial_diagnostic") is True)
            check("run index lists both unavailable opponents as skipped", len(_index.get("skipped", [])) == 2)
        else:
            check("run index file was created", False)

        # rerun protection: pre-create the exact jsonl output path `run` would write to for
        # an AVAILABLE opponent (mirror), then confirm `run` refuses to write into it rather
        # than silently appending (which would mix games from two different invocations).
        os.makedirs(jsonl_dir, exist_ok=True)
        preexisting_path = os.path.join(jsonl_dir, f"{manifest_hash_full}__mirror__baseline.jsonl")
        with open(preexisting_path, "w", encoding="utf-8") as f:
            f.write('{"pre":"existing"}\n')
        run_cli(
            "run", "--manifest", manifest_path, "--opponent", "mirror",
            "--games-per-segment", "1", "--jsonl-out", jsonl_dir, "--allow-partial",
        )
        with open(preexisting_path, encoding="utf-8") as f:
            _preexisting_content_after = f.read()
        check("run subcommand refuses to write into an already-existing per-(opponent,arm) "
              "jsonl file (rerun protection) rather than silently appending to it",
              _preexisting_content_after == '{"pre":"existing"}\n')
        os.remove(preexisting_path)

        # reuse-rejection: a jsonl file whose filename carries the WRONG manifest hash prefix
        os.makedirs(jsonl_dir, exist_ok=True)
        wrong_hash_path = os.path.join(jsonl_dir, "deadbeef__lucario__baseline.jsonl")
        with open(wrong_hash_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "schema_version": "1", "game_index": 0, "first_seat_agent": "a",
                "label_a": "baseline", "label_b": "lucario",
                "termination": {"category": "result", "kind": "win"}, "result": {"winner": "a"},
                "error_actor": None, "legality": "legal", "decisions": None,
            }) + "\n")
        r_summarize_reuse = run_cli(
            "summarize", "--manifest", manifest_path, "--jsonl-in", wrong_hash_path,
            "--stage", "screening", "--rng-seed", "1", "--out", os.path.join(_cli_tmp, "report_reject.json"),
        )
        check("summarize refuses a --jsonl-in file whose filename manifest-hash prefix "
              "doesn't match --manifest (reuse-rejection)", r_summarize_reuse.returncode != 0)

        # a genuine, correctly-named but tiny synthetic jsonl set, to exercise the happy
        # path end to end (aggregation logic only -- no real games). label_a/label_b are
        # set exactly as cmd_run itself would set them (label_a=arm, label_b=opponent_id),
        # and each game includes a "decisions" list with actor-tagged entries (one "a" =
        # this arm's own decision, one "b" = the opponent's) so p50/p95/observation_count
        # cells have something real to aggregate, and so the actor-filtering logic (only
        # "a" counts) is actually exercised, not just build_cell's shape in isolation.
        right_hash_baseline = os.path.join(jsonl_dir, f"{manifest_hash_full}__lucario__baseline.jsonl")
        right_hash_candidate = os.path.join(jsonl_dir, f"{manifest_hash_full}__lucario__candidate.jsonl")
        _fixtures = (
            (right_hash_baseline, "baseline", "a", True, 100.0, 200.0),
            (right_hash_candidate, "candidate", "b", False, 80.0, 210.0),
        )
        for path, arm, seat, win, own_ms, opp_ms in _fixtures:
            with open(path, "w", encoding="utf-8") as f:
                for gi in range(4):
                    f.write(json.dumps({
                        "schema_version": "1", "game_index": gi, "first_seat_agent": seat,
                        "label_a": arm, "label_b": "lucario",
                        "termination": {"category": "result", "kind": "win"},
                        "result": {"winner": "a" if win else "b"},
                        "error_actor": None, "legality": "legal",
                        "decisions": [
                            {"ply": 0, "actor": "a", "duration_ms": own_ms + gi},
                            {"ply": 1, "actor": "b", "duration_ms": opp_ms + gi},
                        ],
                    }) + "\n")
        report_path = os.path.join(_cli_tmp, "report_ok.json")
        r_summarize_ok = run_cli(
            "summarize", "--manifest", manifest_path,
            "--jsonl-in", right_hash_baseline, "--jsonl-in", right_hash_candidate,
            "--stage", "screening", "--rng-seed", "1", "--out", report_path,
        )
        check("summarize succeeds on correctly-named, schema-valid jsonl input "
              f"(stderr: {r_summarize_ok.stderr.strip()[:300]!r})" if r_summarize_ok.returncode != 0 else
              "summarize succeeds on correctly-named, schema-valid jsonl input",
              r_summarize_ok.returncode == 0)
        if os.path.exists(report_path):
            with open(report_path, encoding="utf-8") as f:
                _report = json.load(f)
            check("Measurement Report has NO Gatekeeper-only identity fields "
                  "(profile_id/cycle_id/evidence_round) -- not an Evidence Bundle",
                  not any(k in _report for k in ("profile_id", "cycle_id", "evidence_round")))
            _cell_metric_ids = set()
            for cell in _report.get("cells", []):
                check(f"report cell {cell['metric_id']}/{cell['segment_id']} has exactly the 6 required keys",
                      set(cell) == schema.CELL_REQUIRED_KEYS)
                _cell_metric_ids.add(cell["metric_id"])
            check("report emits a decision_time_p50_ms cell (was previously silently never emitted)",
                  schema.METRIC_DECISION_TIME_P50_MS in _cell_metric_ids)
            check("report emits a p95_decision_time cell (was previously silently never emitted)",
                  schema.METRIC_DECISION_TIME_P95_MS in _cell_metric_ids)
            check("report emits an observation_count cell (was previously silently never emitted)",
                  schema.METRIC_OBSERVATION_COUNT in _cell_metric_ids)
            _obs_cell = next((c for c in _report["cells"] if c["metric_id"] == schema.METRIC_OBSERVATION_COUNT), None)
            if _obs_cell:
                # 4 games * 1 own-decision each = 4 observations per arm (opponent's "b"
                # decisions must be excluded, not counted as this arm's observations)
                check("observation_count baseline estimate reflects only actor='a' decisions "
                      "(4 games x 1 own-decision each = 4), not the opponent's decisions too",
                      _obs_cell["baseline_stats"]["estimate"] == "4")
                check("observation_count candidate estimate reflects only actor='a' decisions",
                      _obs_cell["candidate_stats"]["estimate"] == "4")
            _p50_cell = next((c for c in _report["cells"] if c["metric_id"] == schema.METRIC_DECISION_TIME_P50_MS), None)
            if _p50_cell:
                # own_ms fixtures were 100/101/102/103 (baseline) and 80/81/82/83
                # (candidate); opponent's 200s/210s must NOT leak into these estimates.
                check("decision_time_p50_ms baseline estimate is in the own-decision range "
                      "(100-103), not contaminated by the opponent's 200-203 range",
                      Decimal("100") <= Decimal(_p50_cell["baseline_stats"]["estimate"]) <= Decimal("103"))
                check("decision_time_p50_ms candidate estimate is in the own-decision range "
                      "(80-83), not contaminated by the opponent's 210-213 range",
                      Decimal("80") <= Decimal(_p50_cell["candidate_stats"]["estimate"]) <= Decimal("83"))
            check("Measurement Report records measurement_settings (confidence_level/"
                  "bootstrap_replicates/rng_seed) so the report is self-documenting",
                  _report.get("measurement_settings") == {
                      "confidence_level": "0.95", "bootstrap_replicates": 10000, "rng_seed": 1,
                  })
        else:
            check("summarize report file was created", False)

        # illegal_action_rate's denominator must exclude legality=="unknown" records: build a
        # dedicated fixture with 2 "legal", 1 "illegal", and 1 "unknown" game per arm. If
        # "unknown" were silently counted as non-illegal (the bug an earlier heterogeneous-
        # model audit pass found), the rate would read 1/4 instead of the correct 1/3.
        illegal_baseline_path = os.path.join(jsonl_dir, f"{manifest_hash_full}__megastarmie__baseline.jsonl")
        illegal_candidate_path = os.path.join(jsonl_dir, f"{manifest_hash_full}__megastarmie__candidate.jsonl")
        for path, arm in ((illegal_baseline_path, "baseline"), (illegal_candidate_path, "candidate")):
            with open(path, "w", encoding="utf-8") as f:
                for legality, category, kind in (
                    ("legal", "result", "win"), ("legal", "result", "win"),
                    ("illegal", "error", "illegal_action"), ("unknown", "error", "unclassified_exception"),
                ):
                    f.write(json.dumps({
                        "schema_version": "1", "game_index": 0, "first_seat_agent": "a",
                        "label_a": arm, "label_b": "megastarmie",
                        "termination": {"category": category, "kind": kind},
                        "result": {"winner": "a"} if category == "result" else None,
                        "error_actor": None, "legality": legality, "decisions": None,
                    }) + "\n")
        illegal_report_path = os.path.join(_cli_tmp, "report_illegal.json")
        r_illegal = run_cli(
            "summarize", "--manifest", manifest_path,
            "--jsonl-in", illegal_baseline_path, "--jsonl-in", illegal_candidate_path,
            "--stage", "screening", "--rng-seed", "1", "--out", illegal_report_path,
        )
        check("summarize succeeds on the dedicated illegal-action-denominator fixture", r_illegal.returncode == 0)
        if os.path.exists(illegal_report_path):
            with open(illegal_report_path, encoding="utf-8") as f:
                _illegal_report = json.load(f)
            _illegal_cell = next((c for c in _illegal_report["cells"]
                                   if c["metric_id"] == schema.METRIC_ILLEGAL_ACTION_RATE), None)
            check("illegal_action_rate cell was emitted for the dedicated fixture", _illegal_cell is not None)
            if _illegal_cell:
                # denominator must be 3 (legal+illegal only) per arm, i.e. 6 total -- NOT 4
                # per arm / 8 total, which is what including "unknown" records would give.
                check("illegal_action_rate denominator excludes legality=='unknown' records "
                      f"(observations={_illegal_cell['observations']!r}, expected 6, not 8)",
                      _illegal_cell["observations"] == 6)
                check("illegal_action_rate estimate is 1/3 (1 illegal out of 3 known-legality "
                      f"games), not 1/4 (got {_illegal_cell['baseline_stats']['estimate']!r})",
                      abs(Decimal(_illegal_cell["baseline_stats"]["estimate"]) - (Decimal(1) / Decimal(3))) < Decimal("0.001"))
        else:
            check("illegal-action-denominator report file was created", False)

        # --stage mismatch vs the manifest's own recorded stage must be rejected
        r_stage_mismatch = run_cli(
            "summarize", "--manifest", manifest_path,
            "--jsonl-in", right_hash_baseline, "--jsonl-in", right_hash_candidate,
            "--stage", "confirmation", "--rng-seed", "1", "--out", os.path.join(_cli_tmp, "report_stage.json"),
        )
        check("summarize rejects --stage that disagrees with the manifest's own stage",
              r_stage_mismatch.returncode != 0)

        # duplicate (opponent, arm) --jsonl-in inputs must be rejected, not silently overwritten
        r_dup = run_cli(
            "summarize", "--manifest", manifest_path,
            "--jsonl-in", right_hash_baseline, "--jsonl-in", right_hash_baseline, "--jsonl-in", right_hash_candidate,
            "--stage", "screening", "--rng-seed", "1", "--out", os.path.join(_cli_tmp, "report_dup.json"),
        )
        check("summarize rejects a duplicate (opponent,arm) supplied twice via --jsonl-in",
              r_dup.returncode != 0)

        # an unknown opponent_id (from filename) must be rejected, not silently aggregated
        unknown_opp_path = os.path.join(jsonl_dir, f"{manifest_hash_full}__not_a_real_opponent__baseline.jsonl")
        with open(unknown_opp_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "schema_version": "1", "game_index": 0, "first_seat_agent": "a",
                "label_a": "baseline", "label_b": "not_a_real_opponent",
                "termination": {"category": "result", "kind": "win"}, "result": {"winner": "a"},
                "error_actor": None, "legality": "legal", "decisions": None,
            }) + "\n")
        r_unknown_opp = run_cli(
            "summarize", "--manifest", manifest_path, "--jsonl-in", unknown_opp_path,
            "--stage", "screening", "--rng-seed", "1", "--out", os.path.join(_cli_tmp, "report_unknown.json"),
        )
        check("summarize rejects an unknown opponent_id parsed from the jsonl filename",
              r_unknown_opp.returncode != 0)

        # a record whose label_a/label_b disagree with the filename's (arm, opponent_id)
        # must be rejected, not silently trusted
        mismatched_label_path = os.path.join(jsonl_dir, f"{manifest_hash_full}__dragapult__baseline.jsonl")
        with open(mismatched_label_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "schema_version": "1", "game_index": 0, "first_seat_agent": "a",
                "label_a": "WRONG_ARM_NAME", "label_b": "dragapult",
                "termination": {"category": "result", "kind": "win"}, "result": {"winner": "a"},
                "error_actor": None, "legality": "legal", "decisions": None,
            }) + "\n")
        r_mismatch = run_cli(
            "summarize", "--manifest", manifest_path, "--jsonl-in", mismatched_label_path,
            "--stage", "screening", "--rng-seed", "1", "--out", os.path.join(_cli_tmp, "report_mismatch.json"),
        )
        check("summarize rejects a record whose label_a doesn't match the filename-implied arm",
              r_mismatch.returncode != 0)
finally:
    shutil.rmtree(_cli_tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# T15: an artifact's bound --*-params file is actually applied via
# POKEMON_AI_PARAMS_PATH when `run` invokes head_to_head.py (previously the
# params file was hashed into the manifest but never actually used)
# ---------------------------------------------------------------------------
print("\n=== T15: params.json binding (POKEMON_AI_PARAMS_PATH) ===")

import unittest.mock  # noqa: E402

from experiments.eval_infra import raging_bolt_eval  # noqa: E402

_t15_tmp = tempfile.mkdtemp(prefix="eval_infra_t15_")
try:
    t15_manifest_path = os.path.join(_t15_tmp, "manifest.json")
    r_t15_manifest = subprocess.run([
        sys.executable, "-m", "experiments.eval_infra.raging_bolt_eval", "manifest",
        "--candidate-agent", "experiments/agents/raging_bolt/main.py",
        "--candidate-deck", "experiments/decks/raging_bolt_ogerpon.csv",
        "--candidate-artifact-id", "candidate-params-test",
        "--candidate-params", "params.json",  # read-only use of the real, protected params.json
        "--baseline-agent", "main.py", "--baseline-deck", "deck.csv", "--baseline-artifact-id", "baseline-params-test",
        "--protocol-id", "proto-params-test", "--dataset-id", "ds-v1", "--dataset-version", "1", "--stage", "screening",
        "--out", t15_manifest_path,
    ], cwd=_REPO_ROOT, capture_output=True, text=True)
    check("T15 setup: manifest with --candidate-params succeeds", r_t15_manifest.returncode == 0)

    if os.path.exists(t15_manifest_path):
        captured_envs = []

        def _fake_subprocess_run(cmd, timeout=None, capture_output=None, text=None, env=None):
            captured_envs.append(env)
            out_path = cmd[cmd.index("--jsonl-out") + 1]
            n = int(cmd[cmd.index("--n") + 1])
            with open(out_path, "a", encoding="utf-8") as f:
                for i in range(n):
                    f.write(json.dumps({
                        "schema_version": "1", "game_index": i, "first_seat_agent": "a",
                        "label_a": "candidate", "label_b": "mirror",
                        "termination": {"category": "result", "kind": "win"}, "result": {"winner": "a"},
                        "error_actor": None, "legality": "legal", "decisions": None,
                    }) + "\n")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        t15_args = argparse.Namespace(
            manifest=t15_manifest_path, opponent=["mirror"], games_per_segment=1,
            jsonl_out=os.path.join(_t15_tmp, "jsonl"), allow_partial=False,
        )
        with unittest.mock.patch("experiments.eval_infra.raging_bolt_eval.subprocess.run", side_effect=_fake_subprocess_run):
            t15_rc = raging_bolt_eval.cmd_run(t15_args)
        check("T15: cmd_run (with subprocess.run mocked) returns success", t15_rc == 0)

        params_abs_expected = os.path.join(_REPO_ROOT, "params.json")
        candidate_env_calls = [e for e in captured_envs if e is not None and e.get("POKEMON_AI_PARAMS_PATH") == params_abs_expected]
        check(f"POKEMON_AI_PARAMS_PATH was set to the candidate artifact's bound params.json "
              f"for at least one subprocess call ({len(candidate_env_calls)} of {len(captured_envs)} calls)",
              len(candidate_env_calls) >= 1)

        # baseline arm has NO --baseline-params bound -- confirm POKEMON_AI_PARAMS_PATH is
        # explicitly ABSENT for those calls (not silently inherited from this test process's
        # own environment, and not left over from the candidate arm's calls).
        baseline_env_calls = [e for e in captured_envs if e is not None and e.get("POKEMON_AI_PARAMS_PATH") != params_abs_expected]
        check("POKEMON_AI_PARAMS_PATH is absent (not stale-inherited) for the baseline arm, "
              "which has no bound params file", all("POKEMON_AI_PARAMS_PATH" not in e for e in baseline_env_calls))
    else:
        check("T15: manifest was created (prerequisite for the rest of T15)", False)
finally:
    shutil.rmtree(_t15_tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# T16: TimeoutExpired accounting -- a subprocess that hangs after flushing
# SOME (but not all) of its batch's real records must have those records
# counted (not silently assumed to be zero): case A. A subprocess that hangs
# only AFTER flushing ALL of its batch's real records must be treated as
# genuinely, fully completed -- no synthesized record is appended in that
# case, since capping an internal counter cannot un-write the real lines
# already physically on disk: case B (an earlier "cap at batch-1" design
# still appended a spurious extra line here; see case B's own comment below).
# ---------------------------------------------------------------------------
print("\n=== T16: TimeoutExpired accounting (mocked subprocess hang) ===")

_t16_tmp = tempfile.mkdtemp(prefix="eval_infra_t16_")
try:
    t16_manifest_path = os.path.join(_t16_tmp, "manifest.json")
    r_t16_manifest = subprocess.run([
        sys.executable, "-m", "experiments.eval_infra.raging_bolt_eval", "manifest",
        "--candidate-agent", "experiments/agents/raging_bolt/main.py",
        "--candidate-deck", "experiments/decks/raging_bolt_ogerpon.csv",
        "--candidate-artifact-id", "candidate-timeout-test",
        "--baseline-agent", "main.py", "--baseline-deck", "deck.csv", "--baseline-artifact-id", "baseline-timeout-test",
        "--protocol-id", "proto-timeout-test", "--dataset-id", "ds-v1", "--dataset-version", "1", "--stage", "screening",
        "--games-per-worker", "3", "--out", t16_manifest_path,
    ], cwd=_REPO_ROOT, capture_output=True, text=True)
    check("T16 setup: manifest with --games-per-worker 3 succeeds", r_t16_manifest.returncode == 0)

    if os.path.exists(t16_manifest_path):
        def _make_hang_after_n(n_real_records):
            def _fake_run(cmd, timeout=None, capture_output=None, text=None, env=None):
                out_path = cmd[cmd.index("--jsonl-out") + 1]
                with open(out_path, "a", encoding="utf-8") as f:
                    for i in range(n_real_records):
                        f.write(json.dumps({
                            "schema_version": "1", "game_index": i, "first_seat_agent": "a",
                            "label_a": "candidate", "label_b": "mirror",
                            "termination": {"category": "result", "kind": "win"}, "result": {"winner": "a"},
                            "error_actor": None, "legality": "legal", "decisions": None,
                        }) + "\n")
                raise subprocess.TimeoutExpired(cmd, timeout or 1)
            return _fake_run

        # Case A: hangs after flushing 2 of 3 requested records -- expect 2 real + 1
        # synthesized = 3 total lines, games advance by exactly 3 (not 1, the pre-fix bug).
        t16_jsonl_dir_a = os.path.join(_t16_tmp, "jsonl_a")
        t16_args_a = argparse.Namespace(
            manifest=t16_manifest_path, opponent=["mirror"], games_per_segment=3,
            jsonl_out=t16_jsonl_dir_a, allow_partial=True,
        )
        with unittest.mock.patch("experiments.eval_infra.raging_bolt_eval.subprocess.run", side_effect=_make_hang_after_n(2)):
            t16_rc_a = raging_bolt_eval.cmd_run(t16_args_a)
        check("T16 case A (hang after 2 of 3 records): cmd_run returns success (--allow-partial)", t16_rc_a == 0)
        t16_candidate_files_a = [f for f in os.listdir(t16_jsonl_dir_a) if f.endswith("__candidate.jsonl")] if os.path.isdir(t16_jsonl_dir_a) else []
        if t16_candidate_files_a:
            with open(os.path.join(t16_jsonl_dir_a, t16_candidate_files_a[0]), encoding="utf-8") as f:
                t16_lines_a = [ln for ln in f if ln.strip()]
            check(f"T16 case A: jsonl has exactly 3 lines (2 real + 1 synthesized timeout), got {len(t16_lines_a)}",
                  len(t16_lines_a) == 3)
            t16_kinds_a = [json.loads(ln)["termination"]["kind"] for ln in t16_lines_a]
            check("T16 case A: exactly one synthesized wall_clock timeout record present",
                  t16_kinds_a.count("wall_clock") == 1 and t16_kinds_a.count("win") == 2)
        else:
            check("T16 case A: a candidate jsonl file was created", False)

        # Case B: hangs AFTER flushing all 3 requested records (e.g. late shutdown hang).
        # An earlier implementation capped the INTERNAL counter at batch-1 in this case and
        # still appended a synthesized record -- but capping the counter cannot un-write the
        # 3 real lines already physically on disk, so that "fix" actually left 4 physical
        # lines for a batch of 3 (an overshoot a downstream `summarize` would silently
        # consume). The correct behavior is: when real_new_lines >= batch, the batch is
        # already genuinely, fully complete -- do NOT append any synthesized record at all.
        t16_jsonl_dir_b = os.path.join(_t16_tmp, "jsonl_b")
        t16_args_b = argparse.Namespace(
            manifest=t16_manifest_path, opponent=["mirror"], games_per_segment=3,
            jsonl_out=t16_jsonl_dir_b, allow_partial=True,
        )
        with unittest.mock.patch("experiments.eval_infra.raging_bolt_eval.subprocess.run", side_effect=_make_hang_after_n(3)):
            t16_rc_b = raging_bolt_eval.cmd_run(t16_args_b)
        check("T16 case B (hang after all 3 records already flushed): cmd_run returns success", t16_rc_b == 0)
        t16_candidate_files_b = [f for f in os.listdir(t16_jsonl_dir_b) if f.endswith("__candidate.jsonl")] if os.path.isdir(t16_jsonl_dir_b) else []
        if t16_candidate_files_b:
            with open(os.path.join(t16_jsonl_dir_b, t16_candidate_files_b[0]), encoding="utf-8") as f:
                t16_lines_b = [ln for ln in f if ln.strip()]
            check("T16 case B: NO synthesized record is appended when the subprocess had "
                  f"already fully completed the batch (exactly 3 real lines, no overshoot "
                  f"past games_per_segment=3), got {len(t16_lines_b)}",
                  len(t16_lines_b) == 3)
            t16_kinds_b = [json.loads(ln)["termination"]["kind"] for ln in t16_lines_b]
            check("T16 case B: no spurious wall_clock timeout record appears among the 3 "
                  "genuinely-completed games", "wall_clock" not in t16_kinds_b)
        else:
            check("T16 case B: a candidate jsonl file was created", False)
    else:
        check("T16: manifest was created (prerequisite for the rest of T16)", False)
finally:
    shutil.rmtree(_t16_tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# T17: manifest integrity -- games_per_worker/wall_timeout_seconds rejected
# at `manifest` creation time if invalid, and a manifest file hand-edited
# after `manifest` wrote it (so its stored hashes no longer match its own
# content) is rejected by both `run` and `summarize`, not silently trusted.
# ---------------------------------------------------------------------------
print("\n=== T17: manifest integrity (creation-time validation + tamper detection) ===")

_t17_tmp = tempfile.mkdtemp(prefix="eval_infra_t17_")
try:
    def _make_manifest(out_path, **overrides):
        cmd = [
            sys.executable, "-m", "experiments.eval_infra.raging_bolt_eval", "manifest",
            "--candidate-agent", "experiments/agents/raging_bolt/main.py",
            "--candidate-deck", "experiments/decks/raging_bolt_ogerpon.csv",
            "--candidate-artifact-id", "candidate-t17",
            "--baseline-agent", "main.py", "--baseline-deck", "deck.csv", "--baseline-artifact-id", "baseline-t17",
            "--protocol-id", "proto-t17", "--dataset-id", "ds-v1", "--dataset-version", "1", "--stage", "screening",
            "--out", out_path,
        ]
        for k, v in overrides.items():
            cmd += [k, str(v)]
        return subprocess.run(cmd, cwd=_REPO_ROOT, capture_output=True, text=True)

    r_bad_worker = _make_manifest(os.path.join(_t17_tmp, "m_bad_worker.json"), **{"--games-per-worker": 0})
    check("manifest rejects --games-per-worker 0 at creation time", r_bad_worker.returncode != 0)

    r_bad_timeout_zero = _make_manifest(os.path.join(_t17_tmp, "m_bad_timeout0.json"), **{"--wall-timeout-seconds": 0})
    check("manifest rejects --wall-timeout-seconds 0 at creation time", r_bad_timeout_zero.returncode != 0)

    r_bad_timeout_neg = _make_manifest(os.path.join(_t17_tmp, "m_bad_timeout_neg.json"), **{"--wall-timeout-seconds": -5})
    check("manifest rejects a negative --wall-timeout-seconds at creation time", r_bad_timeout_neg.returncode != 0)

    good_manifest_path = os.path.join(_t17_tmp, "m_good.json")
    r_good = _make_manifest(good_manifest_path)
    check("manifest (valid args) succeeds -- prerequisite for the tamper-detection checks below",
          r_good.returncode == 0)

    if r_good.returncode == 0:
        with open(good_manifest_path, encoding="utf-8") as f:
            _good_manifest = json.load(f)

        # Tamper case 1: edit protocol_identity.games_per_worker without updating its sha256.
        tampered1_path = os.path.join(_t17_tmp, "m_tampered1.json")
        _tampered1 = json.loads(json.dumps(_good_manifest))
        _tampered1["protocol_identity"]["games_per_worker"] = 999
        with open(tampered1_path, "w", encoding="utf-8") as f:
            json.dump(_tampered1, f)
        r_run_tampered1 = run_cli(
            "run", "--manifest", tampered1_path, "--opponent", "mirror",
            "--games-per-segment", "1", "--jsonl-out", os.path.join(_t17_tmp, "jsonl1"),
        )
        check("run rejects a manifest whose protocol_identity.games_per_worker was edited "
              "without updating protocol_identity.sha256 (tamper detection)",
              r_run_tampered1.returncode != 0)

        # Tamper case 2: edit the top-level comparison_manifest_sha256 itself to some other
        # value, leaving protocol_identity/dataset_identity internally self-consistent.
        tampered2_path = os.path.join(_t17_tmp, "m_tampered2.json")
        _tampered2 = json.loads(json.dumps(_good_manifest))
        _tampered2["comparison_manifest_sha256"] = "0" * 64
        with open(tampered2_path, "w", encoding="utf-8") as f:
            json.dump(_tampered2, f)
        r_summarize_tampered2 = run_cli(
            "summarize", "--manifest", tampered2_path,
            "--jsonl-in", os.path.join(_t17_tmp, f"{'0' * 64}__mirror__candidate.jsonl"),
            "--stage", "screening", "--rng-seed", "1", "--out", os.path.join(_t17_tmp, "report_tampered2.json"),
        )
        check("summarize rejects a manifest whose top-level comparison_manifest_sha256 was "
              "directly edited to a value inconsistent with its own protocol/dataset/artifact "
              "fields (tamper detection)", r_summarize_tampered2.returncode != 0)

        # Negative control: the untampered manifest must still be accepted by the same
        # integrity check (confirms the check isn't just rejecting everything).
        r_run_untampered = run_cli(
            "run", "--manifest", good_manifest_path, "--opponent", "lucario",
            "--games-per-segment", "1", "--jsonl-out", os.path.join(_t17_tmp, "jsonl3"),
        )
        check("run accepts an untampered manifest (fails only for lucario's own genuine "
              "UNAVAILABLE reason, not for a false-positive integrity rejection)",
              "hash mismatch" not in (r_run_untampered.stderr or "") and
              "was edited" not in (r_run_untampered.stderr or ""))
    else:
        check("(setup) a valid manifest was creatable for the tamper-detection checks", False)
finally:
    shutil.rmtree(_t17_tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# T14: content safety -- no absolute paths / env values / secret-like strings
# in emitted artifacts from the happy-path run above
# ---------------------------------------------------------------------------
print("\n=== T14: content safety scan ===")

_SECRET_LIKE_RE = _re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*\S")


def _scan_for_unsafe_content(obj) -> list[str]:
    problems = []
    text = json.dumps(obj)
    if _re.search(r"[A-Za-z]:[\\/]", text):
        problems.append("contains a Windows absolute path")
    if _SECRET_LIKE_RE.search(text):
        problems.append("contains a secret-like key=value pattern")
    for env_val in os.environ.values():
        if len(env_val) > 8 and env_val in text:
            problems.append(f"contains a literal environment variable value ({env_val[:4]}...)")
            break
    return problems

_report_check_target = {
    "schema_version": "1", "comparison_manifest_sha256": "a" * 64,
    "cells": [schema.build_cell(schema.METRIC_WIN_RATE, schema.SEGMENT_OVERALL, 10, w.as_dict(), w.as_dict(), nd.as_dict())],
    "diagnostics": {"illegal_action_known_legal_or_illegal": 10},
}
problems = _scan_for_unsafe_content(_report_check_target)
check("a representative Measurement Report payload contains no absolute paths/secrets/env leakage",
      problems == [], )
if problems:
    print("    problems found:", problems)

# Also scan the REAL Measurement Report actually emitted by the CLI in T12/T13 above (not
# just a hand-built synthetic object) -- `_report` was captured before its temp dir was
# cleaned up.
if "_report" in globals():
    real_problems = _scan_for_unsafe_content(_report)
    check("the REAL Measurement Report emitted by `summarize` in T12/T13 contains no "
          "absolute paths/secrets/env leakage", real_problems == [])
    if real_problems:
        print("    problems found:", real_problems)
else:
    check("a real Measurement Report was available to content-scan (T12/T13 must have run)", False)

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
