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

# Captured BEFORE any test patches subprocess.run. unittest.mock.patch("...raging_bolt_eval.subprocess.run", ...)
# patches the "run" attribute on the actual subprocess module object (import binds a
# reference, not a copy), so it is a PROCESS-WIDE patch for the duration of the `with` block
# -- not scoped to raging_bolt_eval's own subprocess calls. cmd_run() also calls
# _verify_execution_bindings_unchanged(), which calls platform.system()/release()/machine()/
# python_version(); on some platforms/Python versions these can themselves shell out via
# subprocess.run with a signature the head_to_head.py-shaped fakes below don't accept,
# aborting the whole suite with an uncaught TypeError instead of a clean test failure (found
# by an independent heterogeneous-model audit). Every subprocess.run fake below must
# therefore recognize genuine head_to_head.py invocations (identified by "--jsonl-out" in the
# command) and delegate anything else to the REAL subprocess.run, rather than assuming every
# call during the patched window is one it knows how to handle.
_REAL_SUBPROCESS_RUN = subprocess.run


def _is_head_to_head_invocation(cmd) -> bool:
    return isinstance(cmd, (list, tuple)) and "--jsonl-out" in cmd

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

# validate_game_record's "result" must be consistent with "termination.category" -- an
# earlier version never validated this at all, so a corrupt record with result=[] passed
# schema validation and then crashed summarize's win-rate computation with an uncaught
# AttributeError, and a record claiming BOTH termination.category="timeout" AND a populated
# result={"winner":...} would be silently double-counted as both a timeout and a win (found
# by an independent heterogeneous-model audit).
def _base_raw_record(**overrides):
    record = {
        "schema_version": "1", "game_index": 0, "first_seat_agent": "a",
        "label_a": "candidate", "label_b": "mirror",
        "termination": {"category": "result", "kind": "win"}, "result": {"winner": "a"},
        "error_actor": None, "legality": "legal", "decisions": None,
    }
    record.update(overrides)
    return record


try:
    schema.validate_game_record(_base_raw_record(result=[]))
    check("validate_game_record rejects result=[] (not a dict) instead of letting a later "
          "win-rate computation crash on it with an uncaught AttributeError", False)
except schema.SchemaError:
    check("validate_game_record rejects result=[] (not a dict) instead of letting a later "
          "win-rate computation crash on it with an uncaught AttributeError", True)

try:
    schema.validate_game_record(_base_raw_record(
        termination={"category": "timeout", "kind": "wall_clock"}, result={"winner": "a"}))
    check("validate_game_record rejects termination.category='timeout' combined with a "
          "populated result (would otherwise be double-counted as both a timeout AND a win)", False)
except schema.SchemaError:
    check("validate_game_record rejects termination.category='timeout' combined with a "
          "populated result (would otherwise be double-counted as both a timeout AND a win)", True)

try:
    schema.validate_game_record(_base_raw_record(
        termination={"category": "result", "kind": "win"}, result=None))
    check("validate_game_record rejects termination.category='result' with result=None "
          "(a win/draw claim requires an actual winner)", False)
except schema.SchemaError:
    check("validate_game_record rejects termination.category='result' with result=None "
          "(a win/draw claim requires an actual winner)", True)

check("validate_game_record accepts a genuinely valid result-category record (no false "
      "positive)", schema.validate_game_record(_base_raw_record())["result"] == {"winner": "a"})
check("validate_game_record accepts a genuinely valid timeout-category record with "
      "result=None (no false positive)",
      schema.validate_game_record(_base_raw_record(
          termination={"category": "timeout", "kind": "wall_clock"}, result=None))["result"] is None)

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
    for sid in (schema.SEGMENT_OVERALL, schema.SEGMENT_OPPONENT_LUCARIO,
                schema.SEGMENT_OPPONENT_DRAGAPULT, schema.SEGMENT_OPPONENT_MEGASTARMIE):
        check(f"harness segment ID {sid!r} matches an ID in the example Profile", sid in _profile_segment_ids)
    # seat-0/seat-1 are DELIBERATELY NOT aligned with the example Profile's "first-player"/
    # "second-player" IDs -- head_to_head.py's --first-player only controls deck-slot
    # assignment, not the engine's own coin-flip-determined first-mover, so using the
    # Profile's "first-player" naming here would overclaim engine-confirmed first-mover
    # status (see schema.py's module docstring and README F1). Confirm the deliberate
    # non-alignment explicitly rather than silently matching-or-not.
    check("harness's seat-0 segment ID deliberately does NOT alias the example Profile's "
          "'first-player' ID (we don't claim confirmed engine first-mover)",
          schema.SEGMENT_SEAT_0 not in _profile_segment_ids and schema.SEGMENT_SEAT_0 == "seat-0")
    check("harness's seat-1 segment ID deliberately does NOT alias the example Profile's "
          "'second-player' ID", schema.SEGMENT_SEAT_1 not in _profile_segment_ids and schema.SEGMENT_SEAT_1 == "seat-1")
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

from experiments.eval_infra.clone_opponent import ClonePinError, clone_and_verify, _reject_unsafe_url  # noqa: E402

# Direct unit-level test of _reject_unsafe_url itself, called with NO git subprocess
# involved at all. The Test Auditor found that testing this ONLY through clone_and_verify
# (below) is largely tautological: for most disallowed URLs, git's own transport failure
# also raises ClonePinError (via _run_git), so those integration-level checks would still
# "pass" even if _reject_unsafe_url were deleted entirely -- silently hiding a regression.
# Worse, "fd::0" specifically would hang for the full 120s _run_git timeout and raise an
# uncaught subprocess.TimeoutExpired (not ClonePinError) if the allowlist check were
# removed, crashing this suite instead of failing the assertion. Calling the guard function
# directly exercises exactly the security boundary, with no git process and no possibility
# of a hang.
for _bad_url in ("ext::sh -c 'touch pwned'", "fd::0", "http://example.com/x.git",
                  "git://example.com/x.git", "ssh://example.com/x.git",
                  "user@host:path", "git@github.com:foo/bar.git", "host:path", "-evil-flag"):
    try:
        _reject_unsafe_url(_bad_url)
        check(f"_reject_unsafe_url rejects {_bad_url!r} directly (no git subprocess involved)", False)
    except ClonePinError:
        check(f"_reject_unsafe_url rejects {_bad_url!r} directly (no git subprocess involved)", True)

for _good_url in ("https://example.com/x.git", "relative/local/path"):
    try:
        _reject_unsafe_url(_good_url)
        check(f"_reject_unsafe_url accepts {_good_url!r} (no false positive)", True)
    except ClonePinError as _e:
        check(f"_reject_unsafe_url accepts {_good_url!r} (no false positive): {_e}", False)
# "C:\\some\\windows\\path" is DELIBERATELY NOT tested here unconditionally against the real
# (unmocked) platform.system() -- whether it's accepted is platform-dependent BY DESIGN (see
# the platform-gated block below): it's a genuine drive-letter path on Windows, but on
# Linux/WSL (where CI actually runs this suite) it's indistinguishable from an SCP-style
# "host:path" remote and must be REJECTED. An earlier version tested it here as
# unconditionally "good", which passed on a Windows dev machine but failed this suite on
# Linux CI once the platform gate below was added -- found by real Linux CI failure, not by
# any local run on Windows.

# The single-letter-drive-letter exception (e.g. "C:") is only meaningful ON WINDOWS -- an
# independent heterogeneous-model audit found that an earlier version applied it on every
# platform, so a single-char SCP-style host like "a:b" bypassed the allowlist even when
# running on Linux/WSL (where real cabt games actually run), because git on that platform
# interprets "a:b" as SCP-style host:path, not a filesystem drive letter. Confirm the
# platform check is actually wired in by monkeypatching clone_opponent.platform.system.
import experiments.eval_infra.clone_opponent as _clone_opponent_mod  # noqa: E402
_orig_platform_system = _clone_opponent_mod.platform.system
try:
    _clone_opponent_mod.platform.system = lambda: "Linux"
    try:
        _reject_unsafe_url("a:b")
        check("_reject_unsafe_url rejects single-letter SCP-style 'a:b' when platform.system() "
              "reports Linux (the Windows-drive-letter exception must not apply there)", False)
    except ClonePinError:
        check("_reject_unsafe_url rejects single-letter SCP-style 'a:b' when platform.system() "
              "reports Linux (the Windows-drive-letter exception must not apply there)", True)

    try:
        _reject_unsafe_url("C:\\some\\windows\\path")
        check("_reject_unsafe_url rejects a Windows drive-letter-shaped path "
              "('C:\\\\some\\\\windows\\\\path') when platform.system() reports Linux -- on "
              "Linux/WSL this is indistinguishable from SCP-style 'host:path' remote syntax "
              "and must not be treated as a filesystem drive letter", False)
    except ClonePinError:
        check("_reject_unsafe_url rejects a Windows drive-letter-shaped path "
              "('C:\\\\some\\\\windows\\\\path') when platform.system() reports Linux -- on "
              "Linux/WSL this is indistinguishable from SCP-style 'host:path' remote syntax "
              "and must not be treated as a filesystem drive letter", True)

    _clone_opponent_mod.platform.system = lambda: "Windows"
    try:
        _reject_unsafe_url("C:\\some\\windows\\path")
        check("_reject_unsafe_url still accepts a genuine drive-letter path when "
              "platform.system() reports Windows (no false positive from the platform check)", True)
    except ClonePinError as _e:
        check(f"_reject_unsafe_url still accepts a genuine drive-letter path when "
              f"platform.system() reports Windows (no false positive from the platform check): {_e}", False)
finally:
    _clone_opponent_mod.platform.system = _orig_platform_system

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

        # URL scheme allowlist: only https:// (or a bare local path, no scheme) is permitted;
        # git's ext::/fd:: remote-helper transport syntax (arbitrary command execution) and
        # non-https schemes must be rejected before git is ever invoked.
        for bad_url in ("ext::sh -c 'touch pwned'", "fd::0", "http://example.com/x.git",
                         "git://example.com/x.git", "ssh://example.com/x.git"):
            try:
                clone_and_verify("dragapult", bad_url, _commit_sha, ("agents/fake/main.py",), _clone_dest)
                check(f"clone_and_verify rejects disallowed URL scheme/transport {bad_url!r}", False)
            except ClonePinError:
                check(f"clone_and_verify rejects disallowed URL scheme/transport {bad_url!r}", True)

        try:
            clone_and_verify("dragapult", _synth_repo, "not-40-hex", ("agents/fake/main.py",), _clone_dest)
            check("clone_and_verify rejects a malformed (non-40-hex) commit_sha before touching git", False)
        except ClonePinError:
            check("clone_and_verify rejects a malformed (non-40-hex) commit_sha before touching git", True)
    shutil.rmtree(_clone_dest, ignore_errors=True)
finally:
    shutil.rmtree(_synth_repo, ignore_errors=True)

# ---------------------------------------------------------------------------
# T12: manifest CLI -- resolves/freezes/hashes everything at creation time
# ---------------------------------------------------------------------------
print("\n=== T12: manifest CLI (freezes opponents/games/hashes at creation time) ===")

check("raging_bolt_eval.py file exists", os.path.exists(CLI_MODULE_PATH))
r_compile = subprocess.run([sys.executable, "-m", "py_compile", CLI_MODULE_PATH], capture_output=True, text=True)
check("raging_bolt_eval.py compiles", r_compile.returncode == 0)

for sub in ("manifest", "run", "summarize"):
    r = run_cli(sub, "--help")
    check(f"'{sub} --help' exits 0", r.returncode == 0)

_help_run = run_cli("run", "--help")
check("run --help does NOT list --opponent (now manifest-time only)", "--opponent" not in _help_run.stdout)
check("run --help does NOT list --games-per-segment (now manifest-time only)", "--games-per-segment" not in _help_run.stdout)
check("run --help does NOT list --games-per-worker (forced to 1, not a flag anywhere)", "--games-per-worker" not in _help_run.stdout)
check("run --help does NOT list --wall-timeout-seconds (now manifest-time only)", "--wall-timeout-seconds" not in _help_run.stdout)

_cli_tmp = tempfile.mkdtemp(prefix="eval_infra_cli_test_")
try:
    manifest_path = os.path.join(_cli_tmp, "manifest.json")

    def _manifest_args(out_path, opponents=("mirror",), games_per_segment=2, **overrides):
        args = [
            "manifest",
            "--candidate-agent", "experiments/agents/raging_bolt/main.py",
            "--candidate-deck", "experiments/decks/raging_bolt_ogerpon.csv",
            "--candidate-artifact-id", "candidate-v1",
            "--baseline-agent", "main.py", "--baseline-deck", "deck.csv", "--baseline-artifact-id", "baseline-v1",
            "--protocol-id", "proto-v1", "--dataset-id", "ds-v1", "--dataset-version", "1", "--stage", "screening",
            "--games-per-segment", str(games_per_segment),
            "--out", out_path,
        ]
        for opp in opponents:
            args += ["--opponent", opp]
        for k, v in overrides.items():
            args += [k, str(v)]
        return args

    r_manifest = run_cli(*_manifest_args(manifest_path))
    check("manifest subcommand succeeds with distinct candidate/baseline artifacts and a "
          f"resolvable opponent (mirror) (stderr: {r_manifest.stderr.strip()[:300]!r})" if r_manifest.returncode != 0 else
          "manifest subcommand succeeds with distinct candidate/baseline artifacts and a resolvable opponent (mirror)",
          r_manifest.returncode == 0)
    check("manifest subcommand creates the output file", os.path.exists(manifest_path))

    r_manifest_again = run_cli(*_manifest_args(manifest_path))
    check("manifest subcommand refuses to overwrite an existing manifest file", r_manifest_again.returncode != 0)

    r_dup_opponent = run_cli(*_manifest_args(os.path.join(_cli_tmp, "m_dup_opp.json"), opponents=("mirror", "mirror")))
    check("manifest rejects a duplicate --opponent in the selection list", r_dup_opponent.returncode != 0)

    r_no_opponent_args = [a for a in _manifest_args(os.path.join(_cli_tmp, "m_no_opp.json")) if a != "--opponent" and a != "mirror"]
    r_no_opponent = run_cli(*r_no_opponent_args)
    check("manifest rejects an empty --opponent selection", r_no_opponent.returncode != 0)

    # lucario/dragapult/megastarmie cannot be resolved in this environment (no local files,
    # no opponent_pins.json entries) -- manifest creation for any of them must ABORT with a
    # clear error, not silently produce a manifest that only partially reflects the request.
    for unresolvable_opp in ("lucario", "dragapult", "megastarmie"):
        r_unresolvable = run_cli(*_manifest_args(
            os.path.join(_cli_tmp, f"m_{unresolvable_opp}.json"), opponents=("mirror", unresolvable_opp)
        ))
        check(f"manifest creation ABORTS (not silently partial) when a requested opponent "
              f"({unresolvable_opp}) cannot be resolved right now", r_unresolvable.returncode != 0)
        check(f"manifest creation failure for unresolvable {unresolvable_opp} does not leave "
              f"a manifest file behind", not os.path.exists(os.path.join(_cli_tmp, f"m_{unresolvable_opp}.json")))

    r_zero_games = run_cli(*_manifest_args(os.path.join(_cli_tmp, "m_zero_games.json"), games_per_segment=0))
    check("manifest rejects --games-per-segment 0", r_zero_games.returncode != 0)

    r_zero_timeout = run_cli(*_manifest_args(os.path.join(_cli_tmp, "m_zero_timeout.json"),
                                              **{"--wall-timeout-seconds": 0}))
    check("manifest rejects --wall-timeout-seconds 0", r_zero_timeout.returncode != 0)

    # The candidate-vs-baseline "byte-identical artifact" self-comparison guard compares
    # artifact BUNDLE hashes, and path is now part of that hash (see T20) -- an independent
    # heterogeneous-model audit found that two different SPELLINGS of the same underlying file
    # ("main.py" vs "./main.py") would then bypass the guard, since the unnormalized path
    # strings differ even though they resolve to identical content at the identical location.
    # Confirm the guard still fires once paths are normalized before hashing.
    r_same_artifact_diff_spelling = run_cli(
        "manifest",
        "--candidate-agent", "main.py", "--candidate-deck", "deck.csv", "--candidate-artifact-id", "same-c",
        "--baseline-agent", "./main.py", "--baseline-deck", "./deck.csv", "--baseline-artifact-id", "same-b",
        "--protocol-id", "proto-same", "--dataset-id", "ds-v1", "--dataset-version", "1", "--stage", "screening",
        "--opponent", "mirror", "--games-per-segment", "1",
        "--out", os.path.join(_cli_tmp, "m_same_artifact_diff_spelling.json"),
    )
    check("manifest rejects candidate/baseline artifacts that are the SAME underlying file "
          "referenced with different (but equivalent) path spellings ('main.py' vs "
          "'./main.py') -- path normalization must happen before hashing, not bypass the "
          "self-comparison guard", r_same_artifact_diff_spelling.returncode != 0)

    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            _manifest_obj = json.load(f)
        manifest_hash8 = _manifest_obj["comparison_manifest_sha256"][:8]
        manifest_hash_full = _manifest_obj["comparison_manifest_sha256"]

        check("manifest's protocol_identity records games_per_worker forced to 1",
              _manifest_obj["protocol_identity"]["games_per_worker"] == 1)
        check("manifest's protocol_identity records games_per_segment",
              _manifest_obj["protocol_identity"]["games_per_segment"] == 2)
        check("manifest's protocol_identity records a side_allocation_schedule of the right length",
              len(_manifest_obj["protocol_identity"]["side_allocation_schedule"]) == 2)
        check("manifest's protocol_identity records engine_binding (libcg.so hash or explicit UNAVAILABLE)",
              "engine_binding" in _manifest_obj["protocol_identity"] and
              "availability" in _manifest_obj["protocol_identity"]["engine_binding"])
        check("manifest's protocol_identity records evaluator_binding (this module's own source hash)",
              "evaluator_binding" in _manifest_obj["protocol_identity"] and
              "bundle_sha256" in _manifest_obj["protocol_identity"]["evaluator_binding"])
        check("manifest's protocol_identity records runtime_environment (python/OS info)",
              "runtime_environment" in _manifest_obj["protocol_identity"] and
              "python_version" in _manifest_obj["protocol_identity"]["runtime_environment"])
        check("manifest's dataset_identity records selected_opponents (mirror only, here)",
              [o["opponent_id"] for o in _manifest_obj["dataset_identity"]["selected_opponents"]] == ["mirror"])
        check("manifest's dataset_identity.league_complete is False (mirror alone is not the full "
              "required league)", _manifest_obj["dataset_identity"]["league_complete"] is False)
        check("candidate_artifact records individual per-file hashes (not a raw-byte-concat hash)",
              {f["logical_name"] for f in _manifest_obj["candidate_artifact"]["files"]} == {"agent", "deck"})

# ---------------------------------------------------------------------------
# T13: run CLI -- executes EXACTLY what --manifest fixes; no independent
# --opponent/--games-per-segment; refuses to overwrite existing output;
# reuse-rejection uses the FULL 64-hex hash, not a truncated prefix
# ---------------------------------------------------------------------------
        print("\n=== T13: run CLI (manifest-driven, no independent opponent/games selection) ===")

        jsonl_dir = os.path.join(_cli_tmp, "jsonl")

        r_run_with_opponent_flag = run_cli("run", "--manifest", manifest_path, "--opponent", "mirror", "--jsonl-out", jsonl_dir)
        check("run subcommand rejects a --opponent flag outright (unrecognized argument)",
              r_run_with_opponent_flag.returncode != 0 and
              ("unrecognized arguments" in r_run_with_opponent_flag.stderr or
               "unrecognized arguments" in r_run_with_opponent_flag.stdout))

        r_run_with_games_flag = run_cli("run", "--manifest", manifest_path, "--games-per-segment", "5", "--jsonl-out", jsonl_dir)
        check("run subcommand rejects a --games-per-segment flag outright (unrecognized argument)",
              r_run_with_games_flag.returncode != 0 and
              ("unrecognized arguments" in r_run_with_games_flag.stderr or
               "unrecognized arguments" in r_run_with_games_flag.stdout))

        # On Windows, real games cannot run at all (head_to_head.py's own platform guard) --
        # `run` must report this honestly as an error, never fabricate success.
        r_run_windows = run_cli("run", "--manifest", manifest_path, "--jsonl-out", jsonl_dir)
        check("run subcommand fails closed (nonzero exit) without --allow-partial when the "
              "underlying head_to_head.py subprocess cannot run real games on this platform",
              r_run_windows.returncode != 0)

        r_run_allow_partial = run_cli("run", "--manifest", manifest_path, "--jsonl-out", jsonl_dir, "--allow-partial")
        check("run subcommand succeeds with --allow-partial even when every game attempt fails "
              "(honestly reported, not fabricated)", r_run_allow_partial.returncode == 0)
        index_path = os.path.join(jsonl_dir, f"{manifest_hash8}__run_index.json")
        if os.path.exists(index_path):
            with open(index_path, encoding="utf-8") as f:
                _index = json.load(f)
            check("run index reports partial_diagnostic=true", _index.get("partial_diagnostic") is True)
            check("run index's errors list is non-empty and honestly attributes the platform "
                  "failure (no fabricated success)", len(_index.get("errors", [])) > 0)
        else:
            check("run index file was created", False)

        # rerun protection: pre-create the exact jsonl output path `run` would write to, then
        # confirm `run` refuses to write into it rather than silently appending.
        os.makedirs(jsonl_dir, exist_ok=True)
        preexisting_path = os.path.join(jsonl_dir, f"{manifest_hash_full}__mirror__baseline.jsonl")
        with open(preexisting_path, "w", encoding="utf-8") as f:
            f.write('{"pre":"existing"}\n')
        run_cli("run", "--manifest", manifest_path, "--jsonl-out", jsonl_dir, "--allow-partial")
        with open(preexisting_path, encoding="utf-8") as f:
            _preexisting_content_after = f.read()
        check("run subcommand refuses to write into an already-existing per-(opponent,arm) "
              "jsonl file (rerun protection) rather than silently appending to it",
              _preexisting_content_after == '{"pre":"existing"}\n')
        os.remove(preexisting_path)

        # reuse-rejection: a jsonl file whose filename carries only an 8-char (not full 64-hex)
        # prefix, or the wrong hash entirely, must be rejected by `summarize`.
        wrong_hash_path = os.path.join(jsonl_dir, "deadbeef__mirror__baseline.jsonl")
        with open(wrong_hash_path, "w", encoding="utf-8") as f:
            f.write("{}\n")
        r_summarize_reuse = run_cli(
            "summarize", "--manifest", manifest_path, "--jsonl-in", wrong_hash_path,
            "--stage", "screening", "--rng-seed", "1", "--allow-partial-report",
            "--out", os.path.join(_cli_tmp, "report_reject.json"),
        )
        check("summarize refuses a --jsonl-in file whose filename doesn't carry the FULL "
              "64-hex manifest hash prefix (reuse-rejection)", r_summarize_reuse.returncode != 0)

        truncated_hash_path = os.path.join(jsonl_dir, f"{manifest_hash8}__mirror__baseline.jsonl")
        with open(truncated_hash_path, "w", encoding="utf-8") as f:
            f.write("{}\n")
        r_summarize_truncated = run_cli(
            "summarize", "--manifest", manifest_path, "--jsonl-in", truncated_hash_path,
            "--stage", "screening", "--rng-seed", "1", "--allow-partial-report",
            "--out", os.path.join(_cli_tmp, "report_reject2.json"),
        )
        check("summarize refuses a --jsonl-in file named with only the TRUNCATED 8-char "
              "hash prefix (not the full 64-hex) -- stronger than the old 8-char scheme",
              r_summarize_truncated.returncode != 0)
    else:
        check("(setup) manifest was creatable for the T13/T14/T17 checks below", False)
finally:
    shutil.rmtree(_cli_tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# T15: an artifact's bound --*-params file is actually applied via
# POKEMON_AI_PARAMS_PATH when `run` invokes head_to_head.py
# ---------------------------------------------------------------------------
print("\n=== T15: params.json binding (POKEMON_AI_PARAMS_PATH) ===")

import unittest.mock  # noqa: E402
import argparse as _argparse  # noqa: E402 (already imported as argparse at top; alias avoids shadowing)

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
        "--opponent", "mirror", "--games-per-segment", "1",
        "--out", t15_manifest_path,
    ], cwd=_REPO_ROOT, capture_output=True, text=True)
    check("T15 setup: manifest with --candidate-params succeeds", r_t15_manifest.returncode == 0)

    if os.path.exists(t15_manifest_path):
        captured_envs = []

        def _fake_subprocess_run(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args")
            if not _is_head_to_head_invocation(cmd):
                return _REAL_SUBPROCESS_RUN(*args, **kwargs)
            captured_envs.append(kwargs.get("env"))
            out_path = cmd[cmd.index("--jsonl-out") + 1]
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "schema_version": "1", "game_index": 0, "first_seat_agent": "a",
                    "label_a": "candidate", "label_b": "mirror",
                    "termination": {"category": "result", "kind": "win"}, "result": {"winner": "a"},
                    "error_actor": None, "legality": "legal", "decisions": None,
                }) + "\n")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        t15_args = _argparse.Namespace(manifest=t15_manifest_path, jsonl_out=os.path.join(_t15_tmp, "jsonl"), allow_partial=False)
        with unittest.mock.patch("experiments.eval_infra.raging_bolt_eval.subprocess.run", side_effect=_fake_subprocess_run):
            t15_rc = raging_bolt_eval.cmd_run(t15_args)
        check("T15: cmd_run (with subprocess.run mocked) returns success", t15_rc == 0)

        params_abs_expected = os.path.join(_REPO_ROOT, "params.json")
        candidate_env_calls = [e for e in captured_envs if e is not None and e.get("POKEMON_AI_PARAMS_PATH") == params_abs_expected]
        check(f"POKEMON_AI_PARAMS_PATH was set to the candidate artifact's bound params.json "
              f"for at least one subprocess call ({len(candidate_env_calls)} of {len(captured_envs)} calls)",
              len(candidate_env_calls) >= 1)
        baseline_env_calls = [e for e in captured_envs if e is not None and e.get("POKEMON_AI_PARAMS_PATH") != params_abs_expected]
        check("POKEMON_AI_PARAMS_PATH is absent (not stale-inherited) for the baseline arm, "
              "which has no bound params file", all("POKEMON_AI_PARAMS_PATH" not in e for e in baseline_env_calls))

        # relative artifact paths must be normalized to repo-root-absolute before being passed
        # to the subprocess -- confirm every --agent-*/--deck-* value seen by the mock was absolute.
        for call_args in [c for c in [captured_envs] if False]:  # placeholder, real check below
            pass
    else:
        check("T15: manifest was created (prerequisite for the rest of T15)", False)
finally:
    shutil.rmtree(_t15_tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# T15b: relative artifact paths are normalized to repo-root-absolute before
# being passed to the head_to_head.py subprocess (avoids cwd-dependent ambiguity)
# ---------------------------------------------------------------------------
print("\n=== T15b: artifact path normalization ===")

_t15b_tmp = tempfile.mkdtemp(prefix="eval_infra_t15b_")
try:
    t15b_manifest_path = os.path.join(_t15b_tmp, "manifest.json")
    r_t15b_manifest = subprocess.run([
        sys.executable, "-m", "experiments.eval_infra.raging_bolt_eval", "manifest",
        "--candidate-agent", "experiments/agents/raging_bolt/main.py",
        "--candidate-deck", "experiments/decks/raging_bolt_ogerpon.csv",
        "--candidate-artifact-id", "candidate-path-test",
        "--baseline-agent", "main.py", "--baseline-deck", "deck.csv", "--baseline-artifact-id", "baseline-path-test",
        "--protocol-id", "proto-path-test", "--dataset-id", "ds-v1", "--dataset-version", "1", "--stage", "screening",
        "--opponent", "mirror", "--games-per-segment", "1",
        "--out", t15b_manifest_path,
    ], cwd=_REPO_ROOT, capture_output=True, text=True)
    check("T15b setup: manifest succeeds", r_t15b_manifest.returncode == 0)

    if os.path.exists(t15b_manifest_path):
        captured_cmds = []

        def _fake_run_capture_cmd(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args")
            if not _is_head_to_head_invocation(cmd):
                return _REAL_SUBPROCESS_RUN(*args, **kwargs)
            captured_cmds.append(cmd)
            out_path = cmd[cmd.index("--jsonl-out") + 1]
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "schema_version": "1", "game_index": 0, "first_seat_agent": "a",
                    "label_a": "candidate", "label_b": "mirror",
                    "termination": {"category": "result", "kind": "win"}, "result": {"winner": "a"},
                    "error_actor": None, "legality": "legal", "decisions": None,
                }) + "\n")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        t15b_args = _argparse.Namespace(manifest=t15b_manifest_path, jsonl_out=os.path.join(_t15b_tmp, "jsonl"), allow_partial=False)
        with unittest.mock.patch("experiments.eval_infra.raging_bolt_eval.subprocess.run", side_effect=_fake_run_capture_cmd):
            raging_bolt_eval.cmd_run(t15b_args)
        all_paths = []
        for cmd in captured_cmds:
            for flag in ("--agent-a", "--deck-a", "--agent-b", "--deck-b"):
                all_paths.append(cmd[cmd.index(flag) + 1])
        check(f"every --agent-*/--deck-* path passed to the head_to_head.py subprocess is "
              f"absolute (normalized to repo root), not left relative ({len(all_paths)} paths checked)",
              len(all_paths) > 0 and all(os.path.isabs(p) for p in all_paths))
    else:
        check("T15b: manifest was created", False)
finally:
    shutil.rmtree(_t15b_tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# T16: TimeoutExpired accounting (mocked subprocess hang). games_per_worker
# is now always 1, so every subprocess call corresponds to exactly one game.
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
        "--opponent", "mirror", "--games-per-segment", "2",
        "--out", t16_manifest_path,
    ], cwd=_REPO_ROOT, capture_output=True, text=True)
    check("T16 setup: manifest with games_per_segment=2 succeeds", r_t16_manifest.returncode == 0)

    if os.path.exists(t16_manifest_path):
        # Case A: the subprocess hangs WITHOUT having written its single real record yet --
        # expect a synthesized wall_clock record, globally-unique game_id, and the run to
        # still report success (games advance by 1 per TimeoutExpired).
        def _fake_hang_no_flush(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args")
            if not _is_head_to_head_invocation(cmd):
                return _REAL_SUBPROCESS_RUN(*args, **kwargs)
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 1)

        t16_jsonl_dir_a = os.path.join(_t16_tmp, "jsonl_a")
        t16_args_a = _argparse.Namespace(manifest=t16_manifest_path, jsonl_out=t16_jsonl_dir_a, allow_partial=True)
        with unittest.mock.patch("experiments.eval_infra.raging_bolt_eval.subprocess.run", side_effect=_fake_hang_no_flush):
            t16_rc_a = raging_bolt_eval.cmd_run(t16_args_a)
        check("T16 case A (hang, no record flushed): cmd_run returns success (--allow-partial)", t16_rc_a == 0)
        t16_candidate_files_a = [f for f in os.listdir(t16_jsonl_dir_a) if f.endswith("__candidate.jsonl")] if os.path.isdir(t16_jsonl_dir_a) else []
        if t16_candidate_files_a:
            with open(os.path.join(t16_jsonl_dir_a, t16_candidate_files_a[0]), encoding="utf-8") as f:
                t16_lines_a = [json.loads(ln) for ln in f if ln.strip()]
            check(f"T16 case A: exactly games_per_segment=2 records were written, got {len(t16_lines_a)}",
                  len(t16_lines_a) == 2)
            check("T16 case A: both records are synthesized wall_clock timeouts",
                  all(r["termination"]["kind"] == "wall_clock" for r in t16_lines_a))
            check("T16 case A: both records have distinct, globally-unique game_id values",
                  len({r["game_id"] for r in t16_lines_a}) == 2)
        else:
            check("T16 case A: a candidate jsonl file was created", False)

        # Case B: the subprocess DOES manage to flush its one real record just before the
        # timeout fires (e.g. the game finished but the process hung during shutdown) --
        # expect that REAL record to be used as-is, no spurious synthesized record on top of it.
        def _make_hang_after_flush(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args")
            if not _is_head_to_head_invocation(cmd):
                return _REAL_SUBPROCESS_RUN(*args, **kwargs)
            first_player = cmd[cmd.index("--first-player") + 1]
            out_path = cmd[cmd.index("--jsonl-out") + 1]
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "schema_version": "1", "game_index": 0, "first_seat_agent": first_player,
                    "label_a": "candidate", "label_b": "mirror",
                    "termination": {"category": "result", "kind": "win"}, "result": {"winner": "a"},
                    "error_actor": None, "legality": "legal", "decisions": None,
                }) + "\n")
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 1)

        t16_jsonl_dir_b = os.path.join(_t16_tmp, "jsonl_b")
        t16_args_b = _argparse.Namespace(manifest=t16_manifest_path, jsonl_out=t16_jsonl_dir_b, allow_partial=True)
        with unittest.mock.patch("experiments.eval_infra.raging_bolt_eval.subprocess.run", side_effect=_make_hang_after_flush):
            t16_rc_b = raging_bolt_eval.cmd_run(t16_args_b)
        check("T16 case B (hang after the single real record was already flushed): "
              "cmd_run returns success", t16_rc_b == 0)
        t16_candidate_files_b = [f for f in os.listdir(t16_jsonl_dir_b) if f.endswith("__candidate.jsonl")] if os.path.isdir(t16_jsonl_dir_b) else []
        if t16_candidate_files_b:
            with open(os.path.join(t16_jsonl_dir_b, t16_candidate_files_b[0]), encoding="utf-8") as f:
                t16_lines_b = [json.loads(ln) for ln in f if ln.strip()]
            check(f"T16 case B: exactly games_per_segment=2 records were written (real, not "
                  f"synthesized-on-top), got {len(t16_lines_b)}", len(t16_lines_b) == 2)
            check("T16 case B: no spurious wall_clock timeout record among the genuinely-"
                  "completed games", all(r["termination"]["kind"] != "wall_clock" for r in t16_lines_b))
        else:
            check("T16 case B: a candidate jsonl file was created", False)
    else:
        check("T16: manifest was created (prerequisite for the rest of T16)", False)
finally:
    shutil.rmtree(_t16_tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# T17: manifest integrity -- creation-time validation + tamper detection
# across the richer schema-2 field set
# ---------------------------------------------------------------------------
print("\n=== T17: manifest integrity (creation-time validation + tamper detection) ===")

_t17_tmp = tempfile.mkdtemp(prefix="eval_infra_t17_")
try:
    def _make_manifest17(out_path, **overrides):
        cmd = [
            sys.executable, "-m", "experiments.eval_infra.raging_bolt_eval", "manifest",
            "--candidate-agent", "experiments/agents/raging_bolt/main.py",
            "--candidate-deck", "experiments/decks/raging_bolt_ogerpon.csv",
            "--candidate-artifact-id", "candidate-t17",
            "--baseline-agent", "main.py", "--baseline-deck", "deck.csv", "--baseline-artifact-id", "baseline-t17",
            "--protocol-id", "proto-t17", "--dataset-id", "ds-v1", "--dataset-version", "1", "--stage", "screening",
            "--opponent", "mirror", "--games-per-segment", "2",
            "--out", out_path,
        ]
        for k, v in overrides.items():
            cmd += [k, str(v)]
        return subprocess.run(cmd, cwd=_REPO_ROOT, capture_output=True, text=True)

    r_bad_timeout_zero = _make_manifest17(os.path.join(_t17_tmp, "m_bad_timeout0.json"), **{"--wall-timeout-seconds": 0})
    check("manifest rejects --wall-timeout-seconds 0 at creation time", r_bad_timeout_zero.returncode != 0)

    r_bad_timeout_neg = _make_manifest17(os.path.join(_t17_tmp, "m_bad_timeout_neg.json"), **{"--wall-timeout-seconds": -5})
    check("manifest rejects a negative --wall-timeout-seconds at creation time", r_bad_timeout_neg.returncode != 0)

    good_manifest_path = os.path.join(_t17_tmp, "m_good.json")
    r_good = _make_manifest17(good_manifest_path)
    check("manifest (valid args) succeeds -- prerequisite for the tamper-detection checks below",
          r_good.returncode == 0)

    if r_good.returncode == 0:
        with open(good_manifest_path, encoding="utf-8") as f:
            _good_manifest = json.load(f)

        # Tamper case 1: edit protocol_identity.games_per_segment without updating its hash.
        tampered1_path = os.path.join(_t17_tmp, "m_tampered1.json")
        _tampered1 = json.loads(json.dumps(_good_manifest))
        _tampered1["protocol_identity"]["games_per_segment"] = 999
        with open(tampered1_path, "w", encoding="utf-8") as f:
            json.dump(_tampered1, f)
        r_run_tampered1 = run_cli(
            "run", "--manifest", tampered1_path, "--jsonl-out", os.path.join(_t17_tmp, "jsonl1"),
        )
        # Asserts the SPECIFIC integrity-check error text, not just a nonzero exit code -- on
        # this Windows machine, `run` WITHOUT --allow-partial fails for EVERY manifest (even a
        # perfectly valid, untampered one) once it reaches game execution, because head_to_head.py
        # cannot load libcg.so outside WSL/Linux. Checking only `returncode != 0` would make this
        # test pass even if the games_per_segment tamper-detection itself were completely removed
        # (found by an independent heterogeneous-model audit, applied here to every tamper case
        # in this section that runs `run` without --allow-partial).
        check("run rejects a manifest whose protocol_identity.games_per_segment was edited "
              "without updating protocol_identity.sha256 (tamper detection) -- specifically via "
              "the protocol_identity hash-mismatch error, not merely a nonzero exit that could "
              "also come from this platform's inability to run real games",
              r_run_tampered1.returncode != 0 and "protocol_identity hash mismatch" in (r_run_tampered1.stderr or ""))

        # Tamper case 2: edit the top-level comparison_manifest_sha256 itself.
        tampered2_path = os.path.join(_t17_tmp, "m_tampered2.json")
        _tampered2 = json.loads(json.dumps(_good_manifest))
        _tampered2["comparison_manifest_sha256"] = "0" * 64
        with open(tampered2_path, "w", encoding="utf-8") as f:
            json.dump(_tampered2, f)
        r_summarize_tampered2 = run_cli(
            "summarize", "--manifest", tampered2_path,
            "--jsonl-in", os.path.join(_t17_tmp, f"{'0' * 64}__mirror__candidate.jsonl"),
            "--stage", "screening", "--rng-seed", "1", "--allow-partial-report",
            "--out", os.path.join(_t17_tmp, "report_tampered2.json"),
        )
        check("summarize rejects a manifest whose top-level comparison_manifest_sha256 was "
              "directly edited to a value inconsistent with its own fields (tamper detection) "
              "-- checked via the specific comparison_manifest_sha256-mismatch error, not the "
              "deliberately-nonexistent --jsonl-in path used here",
              r_summarize_tampered2.returncode != 0 and
              "comparison_manifest_sha256 mismatch" in (r_summarize_tampered2.stderr or ""))

        # Tamper case 3: edit dataset_identity.selected_opponents (e.g. swap in a different
        # opponent list) without updating dataset_identity.sha256 -- this is the exact class
        # of tamper the external review's BLOCKER 1 named ("run a different opponent under the
        # same manifest hash").
        tampered3_path = os.path.join(_t17_tmp, "m_tampered3.json")
        _tampered3 = json.loads(json.dumps(_good_manifest))
        _tampered3["dataset_identity"]["selected_opponents"] = [
            {"opponent_id": "dragapult", "source_kind": "pinned_clone", "repo_url": "https://example.invalid/x.git",
             "commit_sha": "f" * 40, "files": [{"logical_name": "agent", "path": "a", "sha256": "1" * 64},
                                                {"logical_name": "deck", "path": "b", "sha256": "2" * 64}]},
        ]
        with open(tampered3_path, "w", encoding="utf-8") as f:
            json.dump(_tampered3, f)
        r_run_tampered3 = run_cli("run", "--manifest", tampered3_path, "--jsonl-out", os.path.join(_t17_tmp, "jsonl3"))
        check("run rejects a manifest whose dataset_identity.selected_opponents was swapped "
              "for a different opponent set without updating dataset_identity.sha256 -- "
              "prevents running a different opponent under the same manifest hash (checked via "
              "the specific dataset_identity hash-mismatch error, not merely a nonzero exit)",
              r_run_tampered3.returncode != 0 and "dataset_identity hash mismatch" in (r_run_tampered3.stderr or ""))

        # Tamper case 4: swap candidate_artifact.files[agent].path/sha256 to point at a
        # substituted file -- self-consistent within "files" alone -- while leaving the
        # top-level candidate_artifact.sha256 (bundle hash) untouched. This is the exact
        # attack the Test Auditor found empirically: without recomputing the bundle hash
        # from "files" and checking it against the stored top-level "sha256", `run` would
        # resolve the substituted path via _artifact_file_path and execute different content
        # than what comparison_manifest_sha256 claims to identify.
        evil_file_path = os.path.join(_t17_tmp, "evil_agent.py")
        with open(evil_file_path, "w", encoding="utf-8") as f:
            f.write("# substituted content, not the real candidate agent\n")
        import hashlib as _hashlib_t17
        evil_sha256 = _hashlib_t17.sha256(open(evil_file_path, "rb").read()).hexdigest()
        tampered4_path = os.path.join(_t17_tmp, "m_tampered4.json")
        _tampered4 = json.loads(json.dumps(_good_manifest))
        for f_entry in _tampered4["candidate_artifact"]["files"]:
            if f_entry["logical_name"] == "agent":
                f_entry["path"] = evil_file_path
                f_entry["sha256"] = evil_sha256
        with open(tampered4_path, "w", encoding="utf-8") as f:
            json.dump(_tampered4, f)
        r_run_tampered4 = run_cli("run", "--manifest", tampered4_path, "--jsonl-out", os.path.join(_t17_tmp, "jsonl4"))
        check("run rejects a manifest whose candidate_artifact.files[agent].path/sha256 was "
              "swapped to a substituted file while leaving candidate_artifact.sha256 (the "
              "bundle hash) untouched -- prevents executing different content under the same "
              "manifest hash (checked via the specific bundle sha256-mismatch error, not "
              "merely a nonzero exit)",
              r_run_tampered4.returncode != 0 and "candidate_artifact bundle sha256 mismatch" in (r_run_tampered4.stderr or ""))

        # Tamper case 5/6: forge protocol_identity.step_limit (and separately
        # games_per_worker) to a value OTHER than what `run` will actually enforce, while
        # FULLY recomputing every hash so the manifest is internally self-consistent (not
        # merely "edited without updating the hash", which tamper case 1 already covers).
        # `manifest` never exposes step_limit/games_per_worker as CLI flags -- they are always
        # hardcoded to match experiments/head_to_head.py's actual behavior -- so the only way
        # to produce a manifest claiming otherwise is to hand-build one, exactly as this test
        # does. Recording these fields without enforcing them at verification time would let
        # such a manifest pass every other check while claiming a step limit/games-per-worker
        # `run` cannot actually honor (found by an independent heterogeneous-model audit).
        def _forge_manifest_with_protocol_override(base_manifest, out_path, **protocol_overrides):
            protocol_identity = dict(base_manifest["protocol_identity"])
            protocol_identity.pop("sha256", None)
            protocol_identity.update(protocol_overrides)
            protocol_sha256 = sha256_hex(protocol_identity)
            dataset_identity = dict(base_manifest["dataset_identity"])
            dataset_sha256 = dataset_identity.pop("sha256")
            candidate = base_manifest["candidate_artifact"]
            baseline = base_manifest["baseline_artifact"]
            comparison_identity = {
                "schema_version": base_manifest["schema_version"], "candidate_role": base_manifest["candidate_role"],
                "dataset_sha256": dataset_sha256, "protocol_sha256": protocol_sha256,
                "candidate_artifact": {"artifact_id": candidate["artifact_id"], "sha256": candidate["sha256"]},
                "baseline_artifact": {"artifact_id": baseline["artifact_id"], "sha256": baseline["sha256"]},
                "stage": base_manifest["stage"],
            }
            forged = {
                "schema_version": base_manifest["schema_version"], "stage": base_manifest["stage"],
                "candidate_role": base_manifest["candidate_role"],
                "protocol_identity": {**protocol_identity, "sha256": protocol_sha256},
                "dataset_identity": {**dataset_identity, "sha256": dataset_sha256},
                "candidate_artifact": candidate, "baseline_artifact": baseline,
                "comparison_manifest_sha256": sha256_hex(comparison_identity),
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(forged, f, indent=2, sort_keys=True, ensure_ascii=False)
            return forged

        tampered5_path = os.path.join(_t17_tmp, "m_tampered5.json")
        _forge_manifest_with_protocol_override(_good_manifest, tampered5_path, step_limit=500)
        r_run_tampered5 = run_cli("run", "--manifest", tampered5_path, "--jsonl-out", os.path.join(_t17_tmp, "jsonl5"))
        check("run rejects an internally hash-consistent manifest whose protocol_identity."
              "step_limit=500 does not match the actual hardcoded engine step limit (2000) "
              "-- a claim `run` cannot enforce is never silently accepted (checked via the "
              "specific step_limit error, not merely a nonzero exit)",
              r_run_tampered5.returncode != 0 and
              "does not match the actual hardcoded engine step limit" in (r_run_tampered5.stderr or ""))

        tampered6_path = os.path.join(_t17_tmp, "m_tampered6.json")
        _forge_manifest_with_protocol_override(_good_manifest, tampered6_path, games_per_worker=2)
        r_run_tampered6 = run_cli("run", "--manifest", tampered6_path, "--jsonl-out", os.path.join(_t17_tmp, "jsonl6"))
        check("run rejects an internally hash-consistent manifest whose protocol_identity."
              "games_per_worker=2 does not match the actual value `run` always uses (1) -- a "
              "claim `run` cannot enforce is never silently accepted (checked via the "
              "specific games_per_worker error, not merely a nonzero exit)",
              r_run_tampered6.returncode != 0 and
              "games_per_worker=2" in (r_run_tampered6.stderr or "") and
              "does not match the actual value" in (r_run_tampered6.stderr or ""))

        # Tamper case 7: an internally hash-consistent manifest with games_per_segment=0 and
        # an empty side_allocation_schedule. `manifest` itself rejects --games-per-segment < 1
        # at creation time, but a hand-built manifest bypassing the CLI could still produce
        # this combination while remaining hash-consistent -- with zero required records,
        # summarize's completeness check would trivially treat "0 expected, 0 present" as
        # complete and could emit a zero-observation report_kind="primary" with no actual
        # evidence behind it (found by an independent heterogeneous-model audit).
        tampered7_path = os.path.join(_t17_tmp, "m_tampered7.json")
        _forge_manifest_with_protocol_override(_good_manifest, tampered7_path, games_per_segment=0, side_allocation_schedule=[])
        r_run_tampered7 = run_cli("run", "--manifest", tampered7_path, "--jsonl-out", os.path.join(_t17_tmp, "jsonl7"))
        check("run rejects an internally hash-consistent manifest whose "
              "games_per_segment=0 (an empty schedule can never be a sound comparison, "
              "regardless of hash consistency) -- checked via the specific "
              "games_per_segment error, not merely a nonzero exit",
              r_run_tampered7.returncode != 0 and "is not a positive integer" in (r_run_tampered7.stderr or ""))

        # Tamper case 8: forge candidate_artifact.files[agent].path from its normal
        # repo-relative form to a repo-INTERNAL ABSOLUTE path pointing at the exact same
        # (unchanged) file content, with EVERY hash fully, correctly recomputed (per-file
        # sha256 unchanged since content is identical; bundle sha256 and the top-level
        # comparison_manifest_sha256 both recomputed to match) -- fully internally
        # self-consistent, unlike tamper case 4 which deliberately left a hash stale.
        # Containment alone would accept this (the absolute path still resolves inside the
        # repo), but it is not the canonical repo-relative form `manifest` itself always
        # writes -- and both `run` and `summarize` copy/execute an artifact's "files" using
        # exactly what is stored, so an absolute local path could otherwise be embedded
        # verbatim into a report (found by an independent heterogeneous-model audit).
        _candidate_agent_entry = next(f for f in _good_manifest["candidate_artifact"]["files"] if f["logical_name"] == "agent")
        _candidate_agent_abs_path = os.path.join(_REPO_ROOT, _candidate_agent_entry["path"])
        _tampered8 = json.loads(json.dumps(_good_manifest))
        for f_entry in _tampered8["candidate_artifact"]["files"]:
            if f_entry["logical_name"] == "agent":
                f_entry["path"] = _candidate_agent_abs_path
        _tampered8["candidate_artifact"]["sha256"] = raging_bolt_eval._artifact_bundle_sha256_from_files(
            _tampered8["candidate_artifact"]["files"])
        _tampered8_comparison_identity = {
            "schema_version": _tampered8["schema_version"], "candidate_role": _tampered8["candidate_role"],
            "dataset_sha256": _tampered8["dataset_identity"]["sha256"], "protocol_sha256": _tampered8["protocol_identity"]["sha256"],
            "candidate_artifact": {"artifact_id": _tampered8["candidate_artifact"]["artifact_id"], "sha256": _tampered8["candidate_artifact"]["sha256"]},
            "baseline_artifact": {"artifact_id": _tampered8["baseline_artifact"]["artifact_id"], "sha256": _tampered8["baseline_artifact"]["sha256"]},
            "stage": _tampered8["stage"],
        }
        _tampered8["comparison_manifest_sha256"] = raging_bolt_eval.sha256_hex(_tampered8_comparison_identity)
        tampered8_path = os.path.join(_t17_tmp, "m_tampered8.json")
        with open(tampered8_path, "w", encoding="utf-8") as f:
            json.dump(_tampered8, f)

        r_run_tampered8 = run_cli("run", "--manifest", tampered8_path, "--jsonl-out", os.path.join(_t17_tmp, "jsonl8"))
        check("run rejects a fully hash-consistent manifest whose candidate_artifact."
              "files[agent].path is a repo-internal ABSOLUTE path (same content, still "
              "passes containment) instead of the canonical repo-relative form -- only the "
              "exact form `manifest` itself writes is ever accepted (checked via the "
              "specific canonical-path error, not merely a nonzero exit that this platform "
              "would also produce for an untampered manifest run without --allow-partial)",
              r_run_tampered8.returncode != 0 and
              "is not in the canonical repo-relative POSIX form" in (r_run_tampered8.stderr or ""))

        r_summarize_tampered8 = run_cli(
            "summarize", "--manifest", tampered8_path,
            "--jsonl-in", os.path.join(_t17_tmp, "nonexistent__mirror__baseline.jsonl"),
            "--stage", "screening", "--rng-seed", "1", "--allow-partial-report",
            "--out", os.path.join(_t17_tmp, "report_tampered8.json"),
        )
        check("summarize ALSO rejects the same non-canonical-path manifest, before it could "
              "ever embed candidate_artifact into a report (summarize now validates artifact "
              "paths itself, not only `run`) -- checked via the specific canonical-path "
              "error (not e.g. the deliberately-nonexistent --jsonl-in path used here, which "
              "would also produce SOME nonzero exit but for an unrelated reason)",
              r_summarize_tampered8.returncode != 0 and
              "is not in the canonical repo-relative POSIX form" in (r_summarize_tampered8.stderr or ""))

        # Negative control: the untampered manifest must still be accepted by the same
        # integrity check when actually attempting to run it.
        r_run_untampered = run_cli("run", "--manifest", good_manifest_path, "--jsonl-out", os.path.join(_t17_tmp, "jsonl_ok"), "--allow-partial")
        check("run accepts an untampered manifest (no false-positive integrity rejection)",
              "hash mismatch" not in (r_run_untampered.stderr or "") and
              "was edited" not in (r_run_untampered.stderr or ""))
    else:
        check("(setup) a valid manifest was creatable for the tamper-detection checks", False)
finally:
    shutil.rmtree(_t17_tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# T18: globally unique game_id across multiple subprocess-driven games;
# duplicate game_id rejected by summarize
# ---------------------------------------------------------------------------
print("\n=== T18: globally unique game_id across subprocesses; duplicate rejection ===")

_t18_tmp = tempfile.mkdtemp(prefix="eval_infra_t18_")
try:
    t18_manifest_path = os.path.join(_t18_tmp, "manifest.json")
    r_t18_manifest = subprocess.run([
        sys.executable, "-m", "experiments.eval_infra.raging_bolt_eval", "manifest",
        "--candidate-agent", "experiments/agents/raging_bolt/main.py",
        "--candidate-deck", "experiments/decks/raging_bolt_ogerpon.csv",
        "--candidate-artifact-id", "candidate-t18",
        "--baseline-agent", "main.py", "--baseline-deck", "deck.csv", "--baseline-artifact-id", "baseline-t18",
        "--protocol-id", "proto-t18", "--dataset-id", "ds-v1", "--dataset-version", "1", "--stage", "screening",
        "--opponent", "mirror", "--games-per-segment", "5",
        "--out", t18_manifest_path,
    ], cwd=_REPO_ROOT, capture_output=True, text=True)
    check("T18 setup: manifest with games_per_segment=5 succeeds", r_t18_manifest.returncode == 0)

    if os.path.exists(t18_manifest_path):
        # head_to_head.py's OWN "game_index" field always resets to 0 for every single-game
        # subprocess invocation (games_per_worker is forced to 1) -- if the orchestrator used
        # that field alone as the record identity, every record in one output file would
        # collide. Simulate 5 successive single-game subprocess calls (mirroring real
        # behavior) and confirm the ORCHESTRATOR's own "game_id" enrichment is unique across
        # all of them despite head_to_head.py's own field never varying.
        def _fake_run_always_index_zero(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args")
            if not _is_head_to_head_invocation(cmd):
                return _REAL_SUBPROCESS_RUN(*args, **kwargs)
            out_path = cmd[cmd.index("--jsonl-out") + 1]
            first_player = cmd[cmd.index("--first-player") + 1]
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "schema_version": "1", "game_index": 0,  # ALWAYS 0 -- mirrors real head_to_head.py behavior
                    "first_seat_agent": first_player, "label_a": "candidate", "label_b": "mirror",
                    "termination": {"category": "result", "kind": "win"}, "result": {"winner": "a"},
                    "error_actor": None, "legality": "legal", "decisions": None,
                }) + "\n")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        t18_jsonl_dir = os.path.join(_t18_tmp, "jsonl")
        t18_args = _argparse.Namespace(manifest=t18_manifest_path, jsonl_out=t18_jsonl_dir, allow_partial=False)
        with unittest.mock.patch("experiments.eval_infra.raging_bolt_eval.subprocess.run", side_effect=_fake_run_always_index_zero):
            t18_rc = raging_bolt_eval.cmd_run(t18_args)
        check("T18: cmd_run succeeds across 5 subprocess calls that each report game_index=0", t18_rc == 0)

        t18_candidate_files = [f for f in os.listdir(t18_jsonl_dir) if f.endswith("__candidate.jsonl")]
        if t18_candidate_files:
            with open(os.path.join(t18_jsonl_dir, t18_candidate_files[0]), encoding="utf-8") as f:
                t18_records = [json.loads(ln) for ln in f if ln.strip()]
            check(f"T18: 5 records were written despite head_to_head.py's game_index always "
                  f"being 0, got {len(t18_records)}", len(t18_records) == 5)
            check("T18: all 5 records have the SAME underlying head_to_head.py game_index (0) "
                  "-- confirms the collision precondition is real",
                  all(r["game_index"] == 0 for r in t18_records))
            t18_game_ids = [r["game_id"] for r in t18_records]
            check(f"T18: the orchestrator's enriched game_id is nonetheless globally unique "
                  f"across all 5 records ({len(set(t18_game_ids))} distinct of {len(t18_game_ids)})",
                  len(set(t18_game_ids)) == len(t18_game_ids) == 5)

            # Now feed these correctly-unique records through `summarize` -- must succeed.
            t18_report_path = os.path.join(_t18_tmp, "report_unique.json")
            t18_baseline_path = os.path.join(t18_jsonl_dir, f"{t18_manifest_path and json.load(open(t18_manifest_path))['comparison_manifest_sha256']}__mirror__baseline.jsonl")
            r_t18_summarize_ok = run_cli(
                "summarize", "--manifest", t18_manifest_path,
                "--jsonl-in", os.path.join(t18_jsonl_dir, t18_candidate_files[0]),
                "--stage", "screening", "--rng-seed", "1", "--allow-partial-report",
                "--out", t18_report_path,
            )
            check("summarize accepts a file whose game_id values are all genuinely unique",
                  r_t18_summarize_ok.returncode == 0)

            # Duplicate-game_id rejection: hand-craft a SECOND file (a different opponent/arm
            # slot) that reuses one of the candidate file's own game_id values verbatim.
            dup_path = os.path.join(t18_jsonl_dir, f"{t18_records[0]['comparison_manifest_sha256']}__mirror__baseline.jsonl")
            with open(dup_path, "w", encoding="utf-8") as f:
                dup_record = dict(t18_records[0])
                dup_record["arm"] = "baseline"
                dup_record["label_a"] = "baseline"
                dup_record["artifact_id"] = "baseline-t18"
                # game_id deliberately NOT changed -- reuses the candidate file's game_id.
                f.write(json.dumps(dup_record) + "\n")
            r_t18_dup = run_cli(
                "summarize", "--manifest", t18_manifest_path,
                "--jsonl-in", os.path.join(t18_jsonl_dir, t18_candidate_files[0]), "--jsonl-in", dup_path,
                "--stage", "screening", "--rng-seed", "1", "--allow-partial-report",
                "--out", os.path.join(_t18_tmp, "report_dup.json"),
            )
            check("summarize rejects a duplicate game_id reused across two different input "
                  "files", r_t18_dup.returncode != 0)
        else:
            check("T18: a candidate jsonl file was created", False)
    else:
        check("T18: manifest was created (prerequisite for the rest of T18)", False)
finally:
    shutil.rmtree(_t18_tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# T19: comparison_manifest_sha256 sensitivity -- changing any of the
# externally-reviewed-as-missing fields must change the hash
# ---------------------------------------------------------------------------
print("\n=== T19: manifest hash sensitivity ===")

from experiments.eval_infra.canon import sha256_hex as _sha256_hex_direct  # noqa: E402

_t19_tmp = tempfile.mkdtemp(prefix="eval_infra_t19_")
try:
    # games_per_segment change -> hash change (via the real CLI, mirror-only so both resolve).
    m19a_path = os.path.join(_t19_tmp, "m19a.json")
    m19b_path = os.path.join(_t19_tmp, "m19b.json")
    subprocess.run([sys.executable, "-m", "experiments.eval_infra.raging_bolt_eval", "manifest",
        "--candidate-agent", "experiments/agents/raging_bolt/main.py", "--candidate-deck", "experiments/decks/raging_bolt_ogerpon.csv",
        "--candidate-artifact-id", "c19", "--baseline-agent", "main.py", "--baseline-deck", "deck.csv", "--baseline-artifact-id", "b19",
        "--protocol-id", "p19", "--dataset-id", "d19", "--dataset-version", "1", "--stage", "screening",
        "--opponent", "mirror", "--games-per-segment", "2", "--out", m19a_path], cwd=_REPO_ROOT, capture_output=True, text=True)
    subprocess.run([sys.executable, "-m", "experiments.eval_infra.raging_bolt_eval", "manifest",
        "--candidate-agent", "experiments/agents/raging_bolt/main.py", "--candidate-deck", "experiments/decks/raging_bolt_ogerpon.csv",
        "--candidate-artifact-id", "c19", "--baseline-agent", "main.py", "--baseline-deck", "deck.csv", "--baseline-artifact-id", "b19",
        "--protocol-id", "p19", "--dataset-id", "d19", "--dataset-version", "1", "--stage", "screening",
        "--opponent", "mirror", "--games-per-segment", "4", "--out", m19b_path], cwd=_REPO_ROOT, capture_output=True, text=True)
    if os.path.exists(m19a_path) and os.path.exists(m19b_path):
        h19a = json.load(open(m19a_path, encoding="utf-8"))["comparison_manifest_sha256"]
        h19b = json.load(open(m19b_path, encoding="utf-8"))["comparison_manifest_sha256"]
        check("changing --games-per-segment (2 vs 4) changes comparison_manifest_sha256, "
              "all else equal", h19a != h19b)
    else:
        check("(setup) both games-per-segment variant manifests were creatable", False)

    # opponent commit change -> hash change (unit-level: _resolve_opponent_binding against a
    # synthetic local repo at two different commits, real network/pins file untouched).
    synth_repo19 = tempfile.mkdtemp(prefix="eval_infra_t19_repo_")
    try:
        def _git19(*args):
            subprocess.run(["git", *args], cwd=synth_repo19, check=True, capture_output=True)
        _git19("init", "-q")
        _git19("config", "user.email", "test@example.com")
        _git19("config", "user.name", "test")
        os.makedirs(os.path.join(synth_repo19, "agents", "x"), exist_ok=True)
        with open(os.path.join(synth_repo19, "agents", "x", "main.py"), "w", encoding="utf-8") as f:
            f.write("def agent(obs): return []\n")
        with open(os.path.join(synth_repo19, "agents", "x", "deck.csv"), "w", encoding="utf-8") as f:
            f.write("1\n2\n3\n")
        _git19("add", "agents")
        _git19("commit", "-q", "-m", "commit1")
        commit1 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=synth_repo19, capture_output=True, text=True).stdout.strip()

        # Same repo, second commit (different deck content) -> different commit AND different
        # deck file hash, exercising both "opponent commit changed" and "opponent deck changed".
        with open(os.path.join(synth_repo19, "agents", "x", "deck.csv"), "w", encoding="utf-8") as f:
            f.write("1\n2\n3\n4\n")
        _git19("add", "agents")
        _git19("commit", "-q", "-m", "commit2 (deck changed)")
        commit2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=synth_repo19, capture_output=True, text=True).stdout.strip()
        check("T19 setup: two distinct commits were created in the synthetic repo", commit1 != commit2)

        pins19 = {"dragapult": {"repo_url": synth_repo19, "commit_sha": commit1, "file_paths": ["agents/x/main.py", "agents/x/deck.csv"]}}
        binding1 = raging_bolt_eval._resolve_opponent_binding("dragapult", pins19)
        pins19b = {"dragapult": {"repo_url": synth_repo19, "commit_sha": commit2, "file_paths": ["agents/x/main.py", "agents/x/deck.csv"]}}
        binding2 = raging_bolt_eval._resolve_opponent_binding("dragapult", pins19b)

        check("opponent commit_sha differs between the two resolved bindings",
              binding1["commit_sha"] != binding2["commit_sha"])
        deck_hash1 = next(f["sha256"] for f in binding1["files"] if f["logical_name"] == "deck")
        deck_hash2 = next(f["sha256"] for f in binding2["files"] if f["logical_name"] == "deck")
        check("opponent DECK file sha256 differs between the two resolved bindings (deck content changed)",
              deck_hash1 != deck_hash2)

        ds_hash1 = _sha256_hex_direct({"selected_opponents": [binding1]})
        ds_hash2 = _sha256_hex_direct({"selected_opponents": [binding2]})
        check("a dataset_identity-shaped hash over the opponent binding changes when the "
              "opponent's commit (and deck) changes -- this is exactly what propagates into "
              "comparison_manifest_sha256 in a real manifest", ds_hash1 != ds_hash2)
    finally:
        shutil.rmtree(synth_repo19, ignore_errors=True)

    # selected-opponent-set change -> hash change (unit-level dataset_identity hash sensitivity).
    ds_mirror_only = _sha256_hex_direct({"selected_opponents": [{"opponent_id": "mirror", "source_kind": "self_play"}]})
    ds_mirror_plus_one = _sha256_hex_direct({"selected_opponents": [
        {"opponent_id": "mirror", "source_kind": "self_play"},
        {"opponent_id": "dragapult", "source_kind": "pinned_clone", "repo_url": "https://x", "commit_sha": "a" * 40,
         "files": [{"logical_name": "agent", "path": "a", "sha256": "b" * 64}, {"logical_name": "deck", "path": "c", "sha256": "d" * 64}]},
    ]})
    check("changing the SELECTED OPPONENT SET (mirror-only vs mirror+dragapult) changes the "
          "dataset_identity hash", ds_mirror_only != ds_mirror_plus_one)

    # engine/evaluator binding change -> hash change (unit-level protocol_identity sensitivity).
    proto_engine1 = _sha256_hex_direct({"engine_binding": {"availability": "AVAILABLE", "libcg_so_sha256": "a" * 64}})
    proto_engine2 = _sha256_hex_direct({"engine_binding": {"availability": "AVAILABLE", "libcg_so_sha256": "b" * 64}})
    check("changing engine_binding.libcg_so_sha256 changes the protocol_identity hash "
          "(this is exactly what a different/rebuilt libcg.so would produce)", proto_engine1 != proto_engine2)
    proto_eval1 = _sha256_hex_direct({"evaluator_binding": {"bundle_sha256": "a" * 64}})
    proto_eval2 = _sha256_hex_direct({"evaluator_binding": {"bundle_sha256": "b" * 64}})
    check("changing evaluator_binding.bundle_sha256 changes the protocol_identity hash "
          "(this is exactly what a code change to this evaluation harness would produce)", proto_eval1 != proto_eval2)

    # WSL/Linux distribution identity is part of runtime_environment (and therefore
    # protocol_identity) -- an independent heterogeneous-model audit found that
    # platform_system/platform_release/platform_machine alone cannot distinguish two WSL
    # distributions sharing the same reported kernel release and Python version.
    _rt_env19 = raging_bolt_eval._runtime_environment()
    check("runtime_environment includes an 'os_distribution' field", "os_distribution" in _rt_env19)
    check("os_distribution has an explicit 'availability' status (AVAILABLE or NOT_APPLICABLE, "
          "never silently omitted)", _rt_env19["os_distribution"].get("availability") in ("AVAILABLE", "NOT_APPLICABLE"))
    proto_os1 = _sha256_hex_direct({"runtime_environment": {"os_distribution": {"availability": "AVAILABLE", "wsl_distro_name": "Ubuntu-22.04", "os_release": None}}})
    proto_os2 = _sha256_hex_direct({"runtime_environment": {"os_distribution": {"availability": "AVAILABLE", "wsl_distro_name": "Debian", "os_release": None}}})
    check("changing os_distribution.wsl_distro_name changes the runtime_environment-shaped "
          "hash (two WSL distributions are distinguishable, not collapsed to the same binding)",
          proto_os1 != proto_os2)
finally:
    shutil.rmtree(_t19_tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# T20: artifact file-boundary unambiguity -- individual per-file hashes,
# not a raw-byte-concatenation hash that can't tell which file changed
# ---------------------------------------------------------------------------
print("\n=== T20: artifact file-boundary unambiguity ===")

# Created INSIDE the repo (not the OS temp dir) -- artifact paths are now confined to the
# repository root (see _resolve_repo_confined_artifact_path), so a fixture file outside the
# repo would be rejected outright rather than exercising the file-boundary behavior this test
# is actually about.
_t20_tmp = tempfile.mkdtemp(prefix="eval_infra_t20_", dir=_REPO_ROOT)
try:
    agent_path20 = os.path.join(_t20_tmp, "agent.py")
    deck_path20 = os.path.join(_t20_tmp, "deck.csv")
    with open(agent_path20, "w", encoding="utf-8") as f:
        f.write("def agent(obs): return []\n")
    with open(deck_path20, "w", encoding="utf-8") as f:
        f.write("1\n2\n3\n")
    binding_base = raging_bolt_eval._artifact_binding("art20", agent_path20, deck_path20, None)

    # Change ONLY the deck file's content.
    with open(deck_path20, "w", encoding="utf-8") as f:
        f.write("1\n2\n3\n4\n")
    binding_deck_changed = raging_bolt_eval._artifact_binding("art20", agent_path20, deck_path20, None)

    agent_hash_before = next(f["sha256"] for f in binding_base["files"] if f["logical_name"] == "agent")
    agent_hash_after = next(f["sha256"] for f in binding_deck_changed["files"] if f["logical_name"] == "agent")
    deck_hash_before = next(f["sha256"] for f in binding_base["files"] if f["logical_name"] == "deck")
    deck_hash_after = next(f["sha256"] for f in binding_deck_changed["files"] if f["logical_name"] == "deck")

    check("when only the DECK file changes, the individual AGENT file hash is unaffected "
          "(no file-boundary ambiguity)", agent_hash_before == agent_hash_after)
    check("when only the DECK file changes, the individual DECK file hash DOES change",
          deck_hash_before != deck_hash_after)
    check("the overall artifact bundle sha256 also changes (it's derived from the per-file list)",
          binding_base["sha256"] != binding_deck_changed["sha256"])
    check("the artifact binding's 'files' list names exactly which logical file changed "
          "(deck), not just an opaque bundle hash", binding_base["files"][1]["logical_name"] == "deck")

    # An independent heterogeneous-model audit found that an earlier version of
    # _artifact_bundle_sha256_from_files hashed only {logical_name, sha256}, so a file entry
    # could be repointed at a byte-identical COPY of the same content living at a DIFFERENT
    # path without changing the bundle hash at all. Confirm the bundle hash now also depends
    # on "path", not content alone.
    agent_copy_path20 = os.path.join(_t20_tmp, "agent_copy.py")
    shutil.copy2(agent_path20, agent_copy_path20)
    binding_same_content_diff_path = raging_bolt_eval._artifact_binding("art20", agent_copy_path20, deck_path20, None)
    agent_hash_copy = next(f["sha256"] for f in binding_same_content_diff_path["files"] if f["logical_name"] == "agent")
    check("the copied agent file's individual sha256 is identical to the original (same bytes)",
          agent_hash_copy == agent_hash_after)
    check("the overall artifact bundle sha256 STILL differs when a file entry is repointed at "
          "a byte-identical copy at a DIFFERENT path (path is bound, not just content) -- "
          "this is exactly the BLOCKER an independent heterogeneous-model audit found",
          binding_same_content_diff_path["sha256"] != binding_deck_changed["sha256"])
finally:
    shutil.rmtree(_t20_tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# T20b: candidate/baseline artifact paths are confined to the repository
# root -- absolute-outside-repo paths, "../" escapes, and symlink escapes
# are all rejected via realpath + commonpath containment (not just a
# string-level normpath, which resolves neither symlinks nor ".." against
# the real filesystem); a repo-internal absolute path normalizes to the
# same repo-relative artifact identity as the equivalent relative path;
# manifests and reports never persist a local absolute filesystem path.
# ---------------------------------------------------------------------------
print("\n=== T20b: artifact path repo-confinement ===")

_t20b_tmp = tempfile.mkdtemp(prefix="eval_infra_t20b_", dir=_REPO_ROOT)
_t20b_outside_tmp = tempfile.mkdtemp(prefix="eval_infra_t20b_outside_")
# Initialized here (before anything in the try block below can raise) so the `finally` at the
# end of this section can always safely check whether the escape-marker file was created,
# without risking a NameError if an earlier step in the try block fails first.
# _escape_marker_created (file exists on disk, set right after os.open succeeds) is
# deliberately separate from _escape_marker_writable (file exists AND was fully written) --
# cleanup must key off the former, or a write failure after a successful create would leak
# the (empty/partial) file.
_escape_marker_writable = False
_escape_marker_created = False
t20b_escape_target_abs = None
try:
    t20b_agent_abs = os.path.join(_t20b_tmp, "agent.py")
    t20b_deck_abs = os.path.join(_t20b_tmp, "deck.csv")
    with open(t20b_agent_abs, "w", encoding="utf-8") as f:
        f.write("def agent(obs): return []\n")
    with open(t20b_deck_abs, "w", encoding="utf-8") as f:
        f.write("1\n2\n3\n")
    t20b_agent_rel = os.path.relpath(t20b_agent_abs, _REPO_ROOT).replace(os.sep, "/")
    t20b_deck_rel = os.path.relpath(t20b_deck_abs, _REPO_ROOT).replace(os.sep, "/")

    # (1) A repo-INTERNAL absolute path normalizes to a repo-relative "path" in the stored
    # artifact binding -- never the absolute input itself.
    binding_via_absolute = raging_bolt_eval._artifact_binding("t20b-abs", t20b_agent_abs, t20b_deck_rel, None)
    stored_agent_path = next(f["path"] for f in binding_via_absolute["files"] if f["logical_name"] == "agent")
    check("a repo-internal ABSOLUTE agent path is normalized to a repo-relative path in the "
          f"stored artifact binding (got {stored_agent_path!r})",
          stored_agent_path == t20b_agent_rel and not os.path.isabs(stored_agent_path))

    # (5) Equivalent relative and absolute inputs (same underlying file) produce the SAME
    # artifact identity (same bundle sha256) -- not just the same stored path string.
    binding_via_relative = raging_bolt_eval._artifact_binding("t20b-rel", t20b_agent_rel, t20b_deck_rel, None)
    check("an artifact built from a repo-internal ABSOLUTE path and one built from the "
          "equivalent RELATIVE path produce the identical artifact bundle sha256 (same "
          "underlying file, same identity, regardless of input spelling)",
          binding_via_absolute["sha256"] == binding_via_relative["sha256"])

    # (2) An absolute path OUTSIDE the repository is rejected outright.
    t20b_outside_agent = os.path.join(_t20b_outside_tmp, "outside_agent.py")
    with open(t20b_outside_agent, "w", encoding="utf-8") as f:
        f.write("def agent(obs): return []\n")
    try:
        raging_bolt_eval._artifact_binding("t20b-outside", t20b_outside_agent, t20b_deck_rel, None)
        check("_artifact_binding rejects an absolute agent path OUTSIDE the repository root", False)
    except ValueError:
        check("_artifact_binding rejects an absolute agent path OUTSIDE the repository root", True)

    # (3) A "../" escape out of the repository is rejected, even though it's syntactically a
    # RELATIVE path (no leading absolute-path signal at all). The escape target is a REAL,
    # EXISTING file one level above the repo root -- an earlier version of this test pointed
    # at a marker file that was never created, so the rejection could equally have come from
    # _resolve_repo_confined_artifact_path's later `os.path.isfile()` check (a nonexistent
    # file) rather than from the containment check itself; if confinement were silently
    # removed/broken, that same "not a file" rejection would still fire and this test would
    # keep "passing" without ever detecting the regression (found by an independent
    # heterogeneous-model audit). Creating a real file at the escape target closes that gap:
    # only the containment check can reject a path that genuinely resolves to a real file.
    # A UNIQUE (UUID-suffixed) filename, created via O_CREAT|O_EXCL (atomic create-only-if-
    # absent), so this can never collide with -- and therefore never overwrite or later delete
    # -- any pre-existing file that happens to already live in the repo's parent directory
    # (an earlier version used a fixed, predictable filename and unconditionally removed it in
    # `finally`, which would have destroyed a same-named pre-existing file; found by an
    # independent heterogeneous-model audit).
    import uuid as _uuid_t20b
    t20b_escape_target_dir = os.path.dirname(_REPO_ROOT)
    t20b_escape_marker_name = f"eval_infra_t20b_escape_marker_{_uuid_t20b.uuid4().hex}.py"
    t20b_escape_target_abs = os.path.join(t20b_escape_target_dir, t20b_escape_marker_name)
    t20b_escape_rel = os.path.join("..", t20b_escape_marker_name)
    _escape_marker_writable = False
    try:
        _escape_marker_fd = os.open(t20b_escape_target_abs, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        # Set the moment the file actually exists on disk -- separate from
        # _escape_marker_writable below, which additionally requires the write to have
        # succeeded. If fdopen/write raised, the file would still exist (just empty/partial),
        # and cleanup must still remove it; gating cleanup on _escape_marker_writable alone
        # (which an earlier version did) would leak that file in exactly this failure mode
        # (found by an independent heterogeneous-model audit).
        _escape_marker_created = True
        with os.fdopen(_escape_marker_fd, "w", encoding="utf-8") as f:
            f.write("def agent(obs): return []\n")
        _escape_marker_writable = True
    except OSError as _escape_exc:
        _escape_marker_writable = False
        print(f"    [SKIP]  '../' escape check: could not create a real file in the "
              f"repo's parent directory in this environment ({_escape_exc}) -- NOT run, "
              f"not claimed as passing")
    if _escape_marker_writable:
        try:
            raging_bolt_eval._artifact_binding("t20b-escape", t20b_escape_rel, t20b_deck_rel, None)
            check("_artifact_binding rejects a '../' path that escapes the repository root "
                  "(escape target is a REAL, existing file -- rejection can only come from "
                  "the containment check, not a 'file not found' fallback)", False)
        except ValueError:
            check("_artifact_binding rejects a '../' path that escapes the repository root "
                  "(escape target is a REAL, existing file -- rejection can only come from "
                  "the containment check, not a 'file not found' fallback)", True)

    # (4) A symlink INSIDE the repo that points OUTSIDE it is rejected -- string-level checks
    # (normpath, or even a naive commonpath on the UNRESOLVED path) cannot catch this; only
    # realpath (which follows symlinks) can. Best-effort: symlink creation can fail with a
    # PermissionError on Windows without Developer Mode / admin rights -- if so, this specific
    # sub-check is honestly reported as unavailable rather than silently skipped or falsely
    # claimed as passing.
    t20b_symlink_path = os.path.join(_t20b_tmp, "symlink_agent.py")
    try:
        os.symlink(t20b_outside_agent, t20b_symlink_path)
        _symlink_available = True
    except (OSError, NotImplementedError) as _symlink_exc:
        _symlink_available = False
        print(f"    [SKIP]  symlink-escape check: could not create a symlink in this "
              f"environment ({_symlink_exc}) -- NOT run, not claimed as passing")
    if _symlink_available:
        t20b_symlink_rel = os.path.relpath(t20b_symlink_path, _REPO_ROOT).replace(os.sep, "/")
        try:
            raging_bolt_eval._artifact_binding("t20b-symlink", t20b_symlink_rel, t20b_deck_rel, None)
            check("_artifact_binding rejects a symlink that is nominally INSIDE the repo but "
                  "resolves (via realpath) to a target OUTSIDE it", False)
        except ValueError:
            check("_artifact_binding rejects a symlink that is nominally INSIDE the repo but "
                  "resolves (via realpath) to a target OUTSIDE it", True)

    # (6) A REAL, actually-generated manifest (via the CLI, not a fabricated fixture) and a
    # REAL, actually-generated report (via a hand-fed single mirror game through summarize,
    # exactly the enriched-record shape `run` itself would produce) never contain a local
    # absolute filesystem path -- Windows-style (e.g. "C:\...") or POSIX-style (the actual
    # _REPO_ROOT prefix on this machine, checked literally).
    def _scan_text_for_absolute_paths(label, text):
        problems = []
        if _re.search(r"[A-Za-z]:[\\/]", text):
            problems.append("Windows-style absolute path (X:\\ or X:/)")
        if _REPO_ROOT in text or _REPO_ROOT.replace(os.sep, "/") in text:
            problems.append("this machine's literal repo-root absolute path")
        if text.count('"/') and _re.search(r'"/(?:home|Users|usr|etc)/', text):
            problems.append("POSIX-style absolute path under /home, /Users, /usr, or /etc")
        check(f"{label} contains no absolute filesystem path", problems == [])
        if problems:
            print("    problems found:", problems)

    t20b_manifest_path = os.path.join(_t20b_tmp, "manifest.json")
    r_t20b_manifest = run_cli(
        "manifest",
        "--candidate-agent", "experiments/agents/raging_bolt/main.py",
        "--candidate-deck", "experiments/decks/raging_bolt_ogerpon.csv",
        "--candidate-artifact-id", "candidate-t20b",
        "--baseline-agent", "main.py", "--baseline-deck", "deck.csv", "--baseline-artifact-id", "baseline-t20b",
        "--protocol-id", "proto-t20b", "--dataset-id", "ds-v1", "--dataset-version", "1", "--stage", "screening",
        "--opponent", "mirror", "--games-per-segment", "1",
        "--out", t20b_manifest_path,
    )
    check(f"T20b setup: a real manifest was generated via the CLI (stderr: "
          f"{r_t20b_manifest.stderr.strip()[:300]!r})", r_t20b_manifest.returncode == 0)
    if os.path.exists(t20b_manifest_path):
        with open(t20b_manifest_path, encoding="utf-8") as f:
            _t20b_manifest_text = f.read()
            _t20b_manifest_obj = json.loads(_t20b_manifest_text)
        _scan_text_for_absolute_paths("a REAL, actually-generated manifest", _t20b_manifest_text)

        t20b_hash = _t20b_manifest_obj["comparison_manifest_sha256"]
        t20b_side_schedule = _t20b_manifest_obj["protocol_identity"]["side_allocation_schedule"]
        t20b_jsonl_dir = os.path.join(_t20b_tmp, "jsonl")
        os.makedirs(t20b_jsonl_dir, exist_ok=True)
        for arm in ("baseline", "candidate"):
            artifact_id = _t20b_manifest_obj[f"{arm}_artifact"]["artifact_id"]
            fname = os.path.join(t20b_jsonl_dir, f"{t20b_hash}__mirror__{arm}.jsonl")
            with open(fname, "w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "schema_version": "1", "game_index": 0, "first_seat_agent": t20b_side_schedule[0],
                    "label_a": arm, "label_b": "mirror",
                    "termination": {"category": "result", "kind": "win"}, "result": {"winner": "a"},
                    "error_actor": None, "legality": "legal", "decisions": None,
                    "game_id": f"{t20b_hash}:mirror:{arm}:000000", "batch_id": 0,
                    "comparison_manifest_sha256": t20b_hash, "dataset_id": _t20b_manifest_obj["dataset_identity"]["id"],
                    "protocol_id": _t20b_manifest_obj["protocol_identity"]["id"],
                    "opponent_id": "mirror", "arm": arm, "artifact_id": artifact_id,
                }) + "\n")
        t20b_report_path = os.path.join(_t20b_tmp, "report.json")
        r_t20b_summarize = run_cli(
            "summarize", "--manifest", t20b_manifest_path,
            "--jsonl-in", os.path.join(t20b_jsonl_dir, f"{t20b_hash}__mirror__baseline.jsonl"),
            "--jsonl-in", os.path.join(t20b_jsonl_dir, f"{t20b_hash}__mirror__candidate.jsonl"),
            "--stage", "screening", "--rng-seed", "1", "--allow-partial-report",
            "--out", t20b_report_path,
        )
        check(f"T20b setup: a real report was generated via summarize (stderr: "
              f"{r_t20b_summarize.stderr.strip()[:300]!r})", r_t20b_summarize.returncode == 0)
        if os.path.exists(t20b_report_path):
            with open(t20b_report_path, encoding="utf-8") as f:
                _t20b_report_text = f.read()
            _scan_text_for_absolute_paths("a REAL, actually-generated report", _t20b_report_text)
        else:
            check("T20b: a report file was created", False)
    else:
        check("T20b: a manifest file was created (prerequisite for the report-generation check)", False)
finally:
    shutil.rmtree(_t20b_tmp, ignore_errors=True)
    shutil.rmtree(_t20b_outside_tmp, ignore_errors=True)
    # Only remove the escape-marker file if THIS run actually created it (tracked via
    # _escape_marker_created, set immediately after the O_CREAT|O_EXCL open succeeded --
    # deliberately NOT gated on _escape_marker_writable, which also requires the subsequent
    # write to have succeeded; a write failure after a successful create would otherwise leak
    # the empty/partial file, found by an independent heterogeneous-model audit) -- never
    # unconditionally, and only by its unique tracked path.
    if _escape_marker_created:
        try:
            os.remove(t20b_escape_target_abs)
        except OSError:
            pass

# ---------------------------------------------------------------------------
# T21: partial league is never reported as "primary"; the league-wide
# external_league_win_rate/overall cell requires the full league AND
# complete inputs; seat segments use seat-0/seat-1, never first-player
# ---------------------------------------------------------------------------
print("\n=== T21: partial-league rejection; report_kind; seat-0/seat-1 labeling ===")


def _build_synthetic_manifest(opponent_ids, games_per_segment, out_path, stage="screening", league_complete_claim=None):
    """A manifest with FABRICATED bindings for opponents this test environment cannot
    actually resolve (no network/local files) -- used ONLY to exercise `summarize`'s
    league_complete/report_kind aggregation logic against internally-hash-consistent input.
    Never used to claim these opponents are genuinely available, and `run` would still fail
    closed against these fabricated bindings since no real files exist at these paths."""
    candidate = raging_bolt_eval._artifact_binding(
        "candidate-t21", "experiments/agents/raging_bolt/main.py", "experiments/decks/raging_bolt_ogerpon.csv", None)
    baseline = raging_bolt_eval._artifact_binding("baseline-t21", "main.py", "deck.csv", None)
    selected_opponents = []
    for opp in opponent_ids:
        if opp == "mirror":
            selected_opponents.append({"opponent_id": "mirror", "source_kind": "self_play"})
        else:
            selected_opponents.append({
                "opponent_id": opp, "source_kind": "pinned_clone",
                "repo_url": "https://example.invalid/fake.git", "commit_sha": "a" * 40,
                "files": [
                    {"logical_name": "agent", "path": f"agents/{opp}/main.py", "sha256": hashlib.sha256(f"{opp}-agent".encode()).hexdigest()},
                    {"logical_name": "deck", "path": f"agents/{opp}/deck.csv", "sha256": hashlib.sha256(f"{opp}-deck".encode()).hexdigest()},
                ],
            })
    league_complete = set(schema.REQUIRED_LEAGUE_OPPONENTS) <= set(opponent_ids)
    if league_complete_claim is not None:
        # Deliberately lie in dataset_identity.league_complete -- the hash below is computed
        # over this (false) claim, so the manifest is internally hash-consistent despite the
        # claim not matching selected_opponents. Used only to prove `summarize` recomputes
        # league completeness from selected_opponents itself rather than trusting this field.
        league_complete = league_complete_claim
    side_schedule = ["a" if i % 2 == 0 else "b" for i in range(games_per_segment)]
    protocol_identity = {
        "id": "proto-t21", "step_limit": 2000, "games_per_worker": 1,
        "wall_timeout_seconds": "30.0", "games_per_segment": games_per_segment,
        "side_allocation_schedule": side_schedule, "worker_model": "one_subprocess_per_game",
        "decision_time_measurement": "x", "game_rng_control": {"availability": "UNAVAILABLE", "reason": "x"},
        "engine_binding": raging_bolt_eval._engine_binding(),
        "evaluator_binding": raging_bolt_eval._evaluator_binding(),
        "runtime_environment": raging_bolt_eval._runtime_environment(),
    }
    dataset_identity = {"id": "ds-t21", "version": "1", "selected_opponents": selected_opponents, "league_complete": league_complete}
    protocol_sha256 = _sha256_hex_direct(protocol_identity)
    dataset_sha256 = _sha256_hex_direct(dataset_identity)
    manifest = {
        "schema_version": "2", "stage": stage, "candidate_role": "primary",
        "protocol_identity": {**protocol_identity, "sha256": protocol_sha256},
        "dataset_identity": {**dataset_identity, "sha256": dataset_sha256},
        "candidate_artifact": candidate, "baseline_artifact": baseline,
    }
    comparison_identity = {
        "schema_version": manifest["schema_version"], "candidate_role": manifest["candidate_role"],
        "dataset_sha256": dataset_sha256, "protocol_sha256": protocol_sha256,
        "candidate_artifact": {"artifact_id": candidate["artifact_id"], "sha256": candidate["sha256"]},
        "baseline_artifact": {"artifact_id": baseline["artifact_id"], "sha256": baseline["sha256"]},
        "stage": stage,
    }
    manifest["comparison_manifest_sha256"] = _sha256_hex_direct(comparison_identity)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True, ensure_ascii=False)
    return manifest


import hashlib  # noqa: E402

_t21_tmp = tempfile.mkdtemp(prefix="eval_infra_t21_")
try:
    # --- Mirror-only manifest: league_complete is False by construction. ---
    partial_manifest_path = os.path.join(_t21_tmp, "manifest_partial.json")
    partial_manifest = _build_synthetic_manifest(["mirror"], 2, partial_manifest_path)
    h21p = partial_manifest["comparison_manifest_sha256"]

    # first_seat_agent at a given batch_id must match the manifest's OWN
    # side_allocation_schedule[batch_id] for BOTH arms (both arms are scheduled with the same
    # per-game seat sequence) -- summarize now cross-checks this, so it must be correct here.
    partial_schedule = partial_manifest["protocol_identity"]["side_allocation_schedule"]
    mirror_b = os.path.join(_t21_tmp, f"{h21p}__mirror__baseline.jsonl")
    mirror_c = os.path.join(_t21_tmp, f"{h21p}__mirror__candidate.jsonl")
    for path, arm in ((mirror_b, "baseline"), (mirror_c, "candidate")):
        with open(path, "w", encoding="utf-8") as f:
            for gi in range(2):
                f.write(json.dumps({
                    "schema_version": "1", "game_index": 0, "first_seat_agent": partial_schedule[gi],
                    "label_a": arm, "label_b": "mirror",
                    "termination": {"category": "result", "kind": "win"}, "result": {"winner": "a"},
                    "error_actor": None, "legality": "legal", "decisions": None,
                    "game_id": f"{h21p}:mirror:{arm}:{gi:06d}", "batch_id": gi,
                    "comparison_manifest_sha256": h21p, "dataset_id": "ds-t21", "protocol_id": "proto-t21",
                    "opponent_id": "mirror", "arm": arm, "artifact_id": f"{arm}-t21",
                }) + "\n")

    r_partial_fail_closed = run_cli(
        "summarize", "--manifest", partial_manifest_path, "--jsonl-in", mirror_b, "--jsonl-in", mirror_c,
        "--stage", "screening", "--rng-seed", "1", "--out", os.path.join(_t21_tmp, "report_p1.json"),
    )
    check("summarize fails closed (nonzero exit) for a partial (mirror-only) league without "
          "--allow-partial-report -- a partial league is NEVER silently accepted as primary",
          r_partial_fail_closed.returncode != 0)

    r_partial_allowed = run_cli(
        "summarize", "--manifest", partial_manifest_path, "--jsonl-in", mirror_b, "--jsonl-in", mirror_c,
        "--stage", "screening", "--rng-seed", "1", "--allow-partial-report",
        "--out", os.path.join(_t21_tmp, "report_p2.json"),
    )
    check("summarize succeeds for the same partial league WITH --allow-partial-report",
          r_partial_allowed.returncode == 0)
    if r_partial_allowed.returncode == 0:
        _report_p = json.load(open(os.path.join(_t21_tmp, "report_p2.json"), encoding="utf-8"))
        check("a partial-league report is explicitly labeled report_kind='partial_diagnostic', "
              "never 'primary'", _report_p["report_kind"] == "partial_diagnostic")
        check("a partial-league report NEVER includes the league-wide "
              "external_league_win_rate/'overall' cell (mirror alone cannot represent the "
              "full fixed league)",
              not any(c["metric_id"] == schema.METRIC_WIN_RATE and c["segment_id"] == schema.SEGMENT_OVERALL
                      for c in _report_p["cells"]))

    # --- A manifest that LIES in dataset_identity.league_complete (claims True while
    # selected_opponents is mirror-only) must still be rejected as primary -- `summarize`
    # must recompute league completeness from selected_opponents itself, never trust the
    # stored boolean, even when the manifest is otherwise internally hash-consistent (found
    # by an independent heterogeneous-model audit: a hand-built-but-hash-consistent manifest
    # is possible without going through the `manifest` CLI, e.g. this test's own
    # _build_synthetic_manifest helper).
    lying_manifest_path = os.path.join(_t21_tmp, "manifest_lying.json")
    lying_manifest = _build_synthetic_manifest(["mirror"], 2, lying_manifest_path, league_complete_claim=True)
    check("a manifest claiming league_complete=True in dataset_identity while "
          "selected_opponents is mirror-only is still internally hash-consistent (this is "
          "exactly the attack being tested, not a setup bug)",
          lying_manifest["dataset_identity"]["league_complete"] is True)
    h21_lying = lying_manifest["comparison_manifest_sha256"]
    lying_mirror_b = os.path.join(_t21_tmp, f"{h21_lying}__mirror__baseline.jsonl")
    lying_mirror_c = os.path.join(_t21_tmp, f"{h21_lying}__mirror__candidate.jsonl")
    for path, arm in ((lying_mirror_b, "baseline"), (lying_mirror_c, "candidate")):
        with open(path, "w", encoding="utf-8") as f:
            for gi in range(2):
                f.write(json.dumps({
                    "schema_version": "1", "game_index": 0, "first_seat_agent": partial_schedule[gi],
                    "label_a": arm, "label_b": "mirror",
                    "termination": {"category": "result", "kind": "win"}, "result": {"winner": "a"},
                    "error_actor": None, "legality": "legal", "decisions": None,
                    "game_id": f"{h21_lying}:mirror:{arm}:{gi:06d}", "batch_id": gi,
                    "comparison_manifest_sha256": h21_lying, "dataset_id": "ds-t21", "protocol_id": "proto-t21",
                    "opponent_id": "mirror", "arm": arm, "artifact_id": f"{arm}-t21",
                }) + "\n")
    r_lying_fail_closed = run_cli(
        "summarize", "--manifest", lying_manifest_path, "--jsonl-in", lying_mirror_b, "--jsonl-in", lying_mirror_c,
        "--stage", "screening", "--rng-seed", "1", "--out", os.path.join(_t21_tmp, "report_lying.json"),
    )
    check("summarize fails closed (nonzero exit) for a manifest that falsely CLAIMS "
          "league_complete=True while selected_opponents is actually mirror-only -- the "
          "stored boolean is never trusted, only a recomputation from selected_opponents",
          r_lying_fail_closed.returncode != 0)

    # --- Full-league (3 required + mirror) synthetic manifest: report_kind must be "primary". ---
    full_manifest_path = os.path.join(_t21_tmp, "manifest_full.json")
    full_manifest = _build_synthetic_manifest(["lucario", "dragapult", "megastarmie", "mirror"], 2, full_manifest_path)
    h21f = full_manifest["comparison_manifest_sha256"]
    check("a manifest selecting all 3 required opponents has league_complete=True",
          full_manifest["dataset_identity"]["league_complete"] is True)

    full_schedule = full_manifest["protocol_identity"]["side_allocation_schedule"]
    full_paths = []
    for opp in ("lucario", "dragapult", "megastarmie"):
        for arm, winner in (("baseline", "b"), ("candidate", "a")):
            p = os.path.join(_t21_tmp, f"{h21f}__{opp}__{arm}.jsonl")
            full_paths.append(p)
            with open(p, "w", encoding="utf-8") as f:
                for gi in range(2):
                    f.write(json.dumps({
                        "schema_version": "1", "game_index": 0, "first_seat_agent": full_schedule[gi],
                        "label_a": arm, "label_b": opp,
                        "termination": {"category": "result", "kind": "win"}, "result": {"winner": winner},
                        "error_actor": None, "legality": "legal", "decisions": None,
                        "game_id": f"{h21f}:{opp}:{arm}:{gi:06d}", "batch_id": gi,
                        "comparison_manifest_sha256": h21f, "dataset_id": "ds-t21", "protocol_id": "proto-t21",
                        "opponent_id": opp, "arm": arm, "artifact_id": f"{arm}-t21",
                    }) + "\n")

    full_report_path = os.path.join(_t21_tmp, "report_full.json")
    r_full = run_cli(
        "summarize", "--manifest", full_manifest_path,
        *[a for p in full_paths for a in ("--jsonl-in", p)],
        "--stage", "screening", "--rng-seed", "1", "--out", full_report_path,
    )
    check(f"summarize succeeds (report_kind can be 'primary') for a complete league with all "
          f"required opponent/arm inputs present (stderr: {r_full.stderr.strip()[:400]!r})" if r_full.returncode != 0 else
          "summarize succeeds for a complete league with all required opponent/arm inputs present",
          r_full.returncode == 0)
    if r_full.returncode == 0:
        _report_f = json.load(open(full_report_path, encoding="utf-8"))
        check("a complete-league report with all inputs present is labeled report_kind='primary'",
              _report_f["report_kind"] == "primary")
        _overall_cell = next((c for c in _report_f["cells"]
                               if c["metric_id"] == schema.METRIC_WIN_RATE and c["segment_id"] == schema.SEGMENT_OVERALL), None)
        check("a primary report DOES include the league-wide external_league_win_rate/'overall' cell",
              _overall_cell is not None)
        _seat_segment_ids = {c["segment_id"] for c in _report_f["cells"] if c["metric_id"] == schema.METRIC_WIN_RATE} & {"seat-0", "seat-1", "first-player", "second-player"}
        check("emitted seat-segment cells use 'seat-0'/'seat-1' IDs, never 'first-player'/"
              "'second-player' (we do not claim confirmed engine first-mover)",
              _seat_segment_ids <= {"seat-0", "seat-1"})

    # Full league but MISSING one opponent's candidate input -> must still fail closed / be
    # explicitly partial_diagnostic, even though league_complete (the manifest's own
    # selection) is True -- "required opponents, both arms" must be validated too.
    incomplete_paths = [p for p in full_paths if "__megastarmie__candidate.jsonl" not in p]
    r_missing_input = run_cli(
        "summarize", "--manifest", full_manifest_path,
        *[a for p in incomplete_paths for a in ("--jsonl-in", p)],
        "--stage", "screening", "--rng-seed", "1", "--out", os.path.join(_t21_tmp, "report_missing.json"),
    )
    check("summarize fails closed when league_complete=True but one required opponent/arm's "
          "INPUT is missing (megastarmie/candidate), even without --allow-partial-report",
          r_missing_input.returncode != 0)
finally:
    shutil.rmtree(_t21_tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# T22: malformed JSON / non-numeric / negative / non-finite duration_ms are
# explicitly rejected, not silently coerced or ignored
# ---------------------------------------------------------------------------
print("\n=== T22: malformed input rejection ===")

_t22_tmp = tempfile.mkdtemp(prefix="eval_infra_t22_")
try:
    # Each malformed-value case gets its OWN freshly-created manifest (unique --protocol-id
    # per case, so each gets a distinct comparison_manifest_sha256) so its jsonl fixture can
    # be named with the CORRECT full-64-hex-hash + known-opponent + valid-arm filename
    # convention. An earlier version reused ad hoc filenames like "bad_12345.jsonl" that
    # didn't carry any valid hash prefix at all -- `summarize` rejected those at the
    # filename/reuse-rejection stage, before ever reaching JSON parsing or duration_ms
    # validation, so the test "passed" without actually exercising the validation it claimed
    # to test. This version names every fixture correctly so rejection genuinely happens for
    # the claimed reason.
    def _make_t22_manifest(case_label):
        path = os.path.join(_t22_tmp, f"manifest_{case_label}.json")
        subprocess.run([sys.executable, "-m", "experiments.eval_infra.raging_bolt_eval", "manifest",
            "--candidate-agent", "experiments/agents/raging_bolt/main.py", "--candidate-deck", "experiments/decks/raging_bolt_ogerpon.csv",
            "--candidate-artifact-id", "c22", "--baseline-agent", "main.py", "--baseline-deck", "deck.csv", "--baseline-artifact-id", "b22",
            "--protocol-id", f"p22-{case_label}", "--dataset-id", "d22", "--dataset-version", "1", "--stage", "screening",
            "--opponent", "mirror", "--games-per-segment", "1", "--out", path], cwd=_REPO_ROOT, capture_output=True, text=True)
        if not os.path.exists(path):
            return None
        return json.load(open(path, encoding="utf-8"))

    def _base_record(h, protocol_id, duration_ms):
        return {
            "schema_version": "1", "game_index": 0, "first_seat_agent": "a",
            "label_a": "candidate", "label_b": "mirror",
            "termination": {"category": "result", "kind": "win"}, "result": {"winner": "a"},
            "error_actor": None, "legality": "legal",
            "decisions": [{"ply": 0, "actor": "a", "duration_ms": duration_ms}],
            "game_id": f"{h}:mirror:candidate:000000", "batch_id": 0,
            "comparison_manifest_sha256": h, "dataset_id": "d22", "protocol_id": protocol_id,
            "opponent_id": "mirror", "arm": "candidate", "artifact_id": "c22",
        }

    for label, bad_value in (
        ("negative", -5.0),
        ("noninfinite_inf", float("inf")),
        ("noninfinite_nan", float("nan")),
        ("nonnumeric", "not-a-number"),
    ):
        t22_manifest = _make_t22_manifest(label)
        check(f"T22 setup: manifest for {label!r} case succeeds", t22_manifest is not None)
        if t22_manifest is None:
            continue
        h22 = t22_manifest["comparison_manifest_sha256"]
        bad_path = os.path.join(_t22_tmp, f"{h22}__mirror__candidate.jsonl")
        with open(bad_path, "w", encoding="utf-8") as f:
            rec = _base_record(h22, f"p22-{label}", bad_value)
            # json.dumps can't emit inf/nan under allow_nan=False semantics elsewhere in
            # this codebase, but Python's own json.dumps DOES emit them by default -- use
            # that here deliberately to simulate an externally-hand-crafted malformed file.
            f.write(json.dumps(rec) + "\n")
        r_bad = run_cli(
            "summarize", "--manifest", os.path.join(_t22_tmp, f"manifest_{label}.json"), "--jsonl-in", bad_path,
            "--stage", "screening", "--rng-seed", "1", "--allow-partial-report",
            "--out", os.path.join(_t22_tmp, f"report_{label}.json"),
        )
        check(f"summarize rejects a record with {label} duration_ms (correctly-named "
              f"fixture, so this actually exercises duration validation, not filename "
              f"reuse-rejection)", r_bad.returncode != 0)

    t22_manifest_mj = _make_t22_manifest("malformedjson")
    check("T22 setup: manifest for malformed-JSON case succeeds", t22_manifest_mj is not None)
    if t22_manifest_mj is not None:
        h22mj = t22_manifest_mj["comparison_manifest_sha256"]
        malformed_json_path = os.path.join(_t22_tmp, f"{h22mj}__mirror__candidate.jsonl")
        with open(malformed_json_path, "w", encoding="utf-8") as f:
            f.write("{not valid json at all\n")
        r_malformed = run_cli(
            "summarize", "--manifest", os.path.join(_t22_tmp, "manifest_malformedjson.json"),
            "--jsonl-in", malformed_json_path,
            "--stage", "screening", "--rng-seed", "1", "--allow-partial-report",
            "--out", os.path.join(_t22_tmp, "report_malformed.json"),
        )
        check("summarize rejects a correctly-named file containing malformed (unparseable) "
              "JSON with a clear error, not an uncaught traceback", r_malformed.returncode != 0)
finally:
    shutil.rmtree(_t22_tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# T23: baseline/candidate latency CIs have non-zero width (a real bootstrap
# confidence interval, not a degenerate point-estimate-only "interval");
# observation_count/latency cells are UNAVAILABLE (omitted), never an
# exception, when every game in a segment contributed zero decisions
# ---------------------------------------------------------------------------
print("\n=== T23: latency baseline/candidate CI non-zero-width; all-zero-decisions UNAVAILABLE ===")

_t23_tmp = tempfile.mkdtemp(prefix="eval_infra_t23_")
try:
    # NOTE: deliberately uses a non-mirror opponent (lucario, via the same
    # _build_synthetic_manifest helper T21 defines above -- lucario/dragapult/megastarmie
    # cannot be resolved via the real CLI in this offline test environment). Mirror games are
    # BY DESIGN excluded from every league_baseline/league_candidate-derived cell (win_rate,
    # error_rate, illegal_action_rate, AND latency/observation_count), so a mirror-only
    # fixture would never produce a latency cell at all -- that is correct product behavior,
    # not a bug, but it means this test must use a league opponent instead.
    t23_manifest_path = os.path.join(_t23_tmp, "manifest.json")
    # games_per_segment=6 to accommodate the largest fixture below (the varied-duration case
    # uses 6 games) -- summarize now validates every record's batch_id against the manifest's
    # own side_allocation_schedule length, so the manifest must be sized to fit.
    t23_manifest = _build_synthetic_manifest(["lucario"], 6, t23_manifest_path)

    if os.path.exists(t23_manifest_path):
        h23 = t23_manifest["comparison_manifest_sha256"]

        t23_schedule = t23_manifest["protocol_identity"]["side_allocation_schedule"]

        def _write_records(path, arm, durations_per_game):
            with open(path, "w", encoding="utf-8") as f:
                for gi, durations in enumerate(durations_per_game):
                    decisions = None if durations is None else [
                        {"ply": i, "actor": "a", "duration_ms": d} for i, d in enumerate(durations)
                    ] + [{"ply": 99, "actor": "b", "duration_ms": 9999.0}]  # opponent noise, must be excluded
                    f.write(json.dumps({
                        "schema_version": "1", "game_index": 0, "first_seat_agent": t23_schedule[gi],
                        "label_a": arm, "label_b": "lucario",
                        "termination": {"category": "result", "kind": "win"}, "result": {"winner": "a"},
                        "error_actor": None, "legality": "legal", "decisions": decisions,
                        "game_id": f"{h23}:lucario:{arm}:{gi:06d}", "batch_id": gi,
                        "comparison_manifest_sha256": h23, "dataset_id": "ds-t21", "protocol_id": "proto-t21",
                        "opponent_id": "lucario", "arm": arm, "artifact_id": f"{arm}-t21" if arm in ("baseline", "candidate") else f"{arm}23",
                    }) + "\n")

        b_path23 = os.path.join(_t23_tmp, f"{h23}__lucario__baseline.jsonl")
        c_path23 = os.path.join(_t23_tmp, f"{h23}__lucario__candidate.jsonl")
        _write_records(b_path23, "baseline", [[10.0, 12.0], [50.0], [8.0, 9.0, 11.0], [30.0], [15.0], [60.0]])
        _write_records(c_path23, "candidate", [[9.0, 11.0], [48.0], [7.0, 8.0, 10.0], [28.0], [14.0], [58.0]])
        report23_path = os.path.join(_t23_tmp, "report23.json")
        r23 = run_cli(
            "summarize", "--manifest", t23_manifest_path, "--jsonl-in", b_path23, "--jsonl-in", c_path23,
            "--stage", "screening", "--rng-seed", "7", "--allow-partial-report",
            "--out", report23_path,
        )
        check("summarize succeeds on a varied-duration latency fixture", r23.returncode == 0)
        if r23.returncode == 0:
            _report23 = json.load(open(report23_path, encoding="utf-8"))
            _p50_cell = next((c for c in _report23["cells"] if c["metric_id"] == schema.METRIC_DECISION_TIME_P50_MS), None)
            check("decision_time_p50_ms cell was emitted", _p50_cell is not None)
            if _p50_cell:
                b_lo, b_hi = Decimal(_p50_cell["baseline_stats"]["lower"]), Decimal(_p50_cell["baseline_stats"]["upper"])
                c_lo, c_hi = Decimal(_p50_cell["candidate_stats"]["lower"]), Decimal(_p50_cell["candidate_stats"]["upper"])
                check(f"baseline_stats latency CI has NON-ZERO width ({b_lo}..{b_hi}) -- a real "
                      f"bootstrap interval, not a degenerate point estimate", b_hi > b_lo)
                check(f"candidate_stats latency CI has NON-ZERO width ({c_lo}..{c_hi})", c_hi > c_lo)

        # All-zero-decisions case: every game has decisions=None (timing never captured) --
        # must produce an UNAVAILABLE (omitted) cell, never a crash.
        b_path23z = os.path.join(_t23_tmp, f"{h23}__lucario__baseline.jsonl")
        c_path23z = os.path.join(_t23_tmp, f"{h23}__lucario__candidate.jsonl")
        _write_records(b_path23z, "baseline", [None, None])
        _write_records(c_path23z, "candidate", [None, None])
        report23z_path = os.path.join(_t23_tmp, "report23z.json")
        r23z = run_cli(
            "summarize", "--manifest", t23_manifest_path, "--jsonl-in", b_path23z, "--jsonl-in", c_path23z,
            "--stage", "screening", "--rng-seed", "7", "--allow-partial-report",
            "--out", report23z_path,
        )
        check("summarize does NOT crash when every game in a segment has zero captured "
              "decisions (all decisions=None)", r23z.returncode == 0)
        if r23z.returncode == 0:
            _report23z = json.load(open(report23z_path, encoding="utf-8"))
            check("no decision_time_p50_ms/p95/observation_count cell is fabricated when "
                  "there is zero real timing data -- the metric is UNAVAILABLE (omitted)",
                  not any(c["metric_id"] in (schema.METRIC_DECISION_TIME_P50_MS, schema.METRIC_DECISION_TIME_P95_MS,
                                              schema.METRIC_OBSERVATION_COUNT) for c in _report23z["cells"]))
    else:
        check("T23: manifest was created (prerequisite)", False)
finally:
    shutil.rmtree(_t23_tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# T14: content safety -- no absolute paths / env values / secret-like strings
# in emitted artifacts
# ---------------------------------------------------------------------------
print("\n=== T14: content safety scan ===")


def _scan_for_unsafe_content(obj) -> list[str]:
    problems = []
    text = json.dumps(obj)
    if _re.search(r"[A-Za-z]:[\\/]", text):
        problems.append("contains a Windows absolute path")
    if _re.search(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*\S", text):
        problems.append("contains a secret-like key=value pattern")
    for env_val in os.environ.values():
        if len(env_val) > 8 and env_val in text:
            problems.append(f"contains a literal environment variable value ({env_val[:4]}...)")
            break
    return problems


w_fixture = wilson_interval(50, 100)
nd_fixture = newcombe_delta(20, 100, 30, 100)
_report_check_target = {
    "schema_version": "1", "report_kind": "primary", "comparison_manifest_sha256": "a" * 64,
    "cells": [schema.build_cell(schema.METRIC_WIN_RATE, schema.SEGMENT_OVERALL, 10,
                                 w_fixture.as_dict(), w_fixture.as_dict(), nd_fixture.as_dict())],
    "diagnostics": {"illegal_action_known_legal_or_illegal": 10},
}
problems = _scan_for_unsafe_content(_report_check_target)
check("a representative Measurement Report payload contains no absolute paths/secrets/env leakage",
      problems == [])
if problems:
    print("    problems found:", problems)

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
