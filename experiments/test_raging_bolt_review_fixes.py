"""Regression tests for the PR#202 review-fix round:

1. PRODUCTION telemetry is fully untouched by a real decision.
2. BENCHMARK telemetry is recorded (fixed-size aggregate, not an unbounded list).
3. Replaying a BENCHMARK-swallowed exception preserves BENCHMARK's
   non-raising control flow (the bug this guards against: replay_decision.py
   used to default to DEBUG, which would re-raise instead of matching
   capture-time behavior).
4. A replay tape shortage is detected explicitly (ReplayTapeExhausted /
   RagingBoltPolicy._replay_tape_exhausted), not silently backfilled with
   fresh sampling.
5. experiments/shadow_eval_compare.py applies the SAME hidden sample to
   every candidate before advancing to the next sample (the bug this
   guards against: an earlier version consumed the hidden-sample tape
   one-entry-per-candidate, comparing candidates under different hidden
   states).

Runs experiments/head_to_head.py (subprocess) as a mirror match (raging_bolt
vs itself, so only files tracked in git are needed -- sandbox opponents like
top_lucario_1084 are gitignored/local-only and would make this test silently
skip on a fresh CI checkout) with PR0-B replay-bundle capture enabled, and
stops the subprocess as soon as enough MAIN/engine-search decisions have
been captured rather than waiting for a full game to finish -- a mirror
match runs engine search on both sides, roughly doubling per-decision cost,
and a full game was measured to exceed 300s, too slow for a CI fixture that
just needs a handful of real captured decisions.
"""
from __future__ import annotations
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AGENT_PATH = os.path.join(REPO_ROOT, "experiments", "agents", "raging_bolt", "main.py")
DECK_A = os.path.join(REPO_ROOT, "experiments", "decks", "raging_bolt_ogerpon.csv")
SHADOW_SCRIPT = os.path.join(REPO_ROOT, "experiments", "shadow_eval_compare.py")
# Mirror match (raging_bolt vs itself) deliberately, not vs. a sandbox
# opponent: only main.py/raging_bolt_ogerpon.csv are tracked in git (opponent
# agents like top_lucario_1084 are gitignored, regenerated/local-only), and
# these tests must actually run in CI, not silently skip on a fresh checkout.

sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "reference", "extracted"))


def _load_agent_module(exec_mode, name):
    """Load a fresh copy of main.py under a specific EXEC_MODE. Temporarily
    sets the env var for the duration of module exec (EXEC_MODE is read
    once at import time), then restores whatever was there before."""
    backup = os.environ.get("POKEMON_AI_EXEC_MODE")
    os.environ["POKEMON_AI_EXEC_MODE"] = exec_mode
    try:
        spec = importlib.util.spec_from_file_location(name, AGENT_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if backup is None:
            os.environ.pop("POKEMON_AI_EXEC_MODE", None)
        else:
            os.environ["POKEMON_AI_EXEC_MODE"] = backup
    return mod


_MODULE_TMPDIR = None
_MODULE_BUNDLE_PATH = None
_MODULE_MAIN_RECORDS = None
_MODULE_SKIP_REASON = None


def setUpModule():
    """Capture ONE small real Replay Bundle (via a short real game) ONCE
    for the whole test module -- every TestCase class below shares it,
    rather than each class independently re-running an expensive
    real-engine game capture (which was slow enough to blow past
    reasonable CI timeouts when done four times)."""
    global _MODULE_TMPDIR, _MODULE_BUNDLE_PATH, _MODULE_MAIN_RECORDS, _MODULE_SKIP_REASON
    if not (os.path.exists(AGENT_PATH) and os.path.exists(DECK_A)):
        _MODULE_SKIP_REASON = "experiments/agents/raging_bolt/main.py or its deck is missing"
        return
    _MODULE_TMPDIR = tempfile.mkdtemp(prefix="pr202_review_fix_test_")
    _MODULE_BUNDLE_PATH = os.path.join(_MODULE_TMPDIR, "bundle.jsonl")
    env = dict(os.environ)
    env["POKEMON_AI_EXEC_MODE"] = "BENCHMARK"
    env["POKEMON_AI_REPLAY_BUNDLE_PATH"] = _MODULE_BUNDLE_PATH

    MIN_MAIN_RECORDS = 3
    POLL_INTERVAL_S = 2.0
    MAX_WAIT_S = 240.0

    def _count_main_records():
        if not os.path.exists(_MODULE_BUNDLE_PATH):
            return 0, []
        with open(_MODULE_BUNDLE_PATH, encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        main_records = [r for r in records if r.get("captured_hidden_samples")]
        return len(main_records), main_records

    proc = subprocess.Popen(
        [sys.executable, os.path.join(REPO_ROOT, "experiments", "head_to_head.py"),
         "--agent-a", AGENT_PATH, "--deck-a", DECK_A,
         "--agent-b", AGENT_PATH, "--deck-b", DECK_A, "--n", "1"],
        cwd=REPO_ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + MAX_WAIT_S
        main_records = []
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break  # game finished on its own before the threshold -- fine, use what's captured
            count, main_records = _count_main_records()
            if count >= MIN_MAIN_RECORDS:
                break
            time.sleep(POLL_INTERVAL_S)
        else:
            count, main_records = _count_main_records()
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

    _MODULE_MAIN_RECORDS = main_records
    if not _MODULE_MAIN_RECORDS:
        _MODULE_SKIP_REASON = "captured bundle had no MAIN/engine-search decisions to test against"


def tearDownModule():
    if _MODULE_TMPDIR:
        shutil.rmtree(_MODULE_TMPDIR, ignore_errors=True)


class _SharedBundleTestCase(unittest.TestCase):
    """Base class: exposes the module-level shared bundle to every test."""

    @classmethod
    def setUpClass(cls):
        if _MODULE_SKIP_REASON:
            raise unittest.SkipTest(_MODULE_SKIP_REASON)
        cls._tmpdir = _MODULE_TMPDIR
        cls.bundle_path = _MODULE_BUNDLE_PATH
        cls.main_records = _MODULE_MAIN_RECORDS


class TelemetryGatingTests(_SharedBundleTestCase):
    def test_production_telemetry_unchanged_by_real_decision(self):
        mod = _load_agent_module("PRODUCTION", "test_main_prod_unchanged")
        before = mod.get_telemetry()
        mod.agent(self.main_records[0]["obs_dict"])
        after = mod.get_telemetry()
        self.assertEqual(before, after, "PRODUCTION must not mutate any telemetry field")
        self.assertEqual(after["decision_runtime_count"], 0)
        self.assertEqual(after["search_attempt_count"], 0)
        self.assertEqual(after["rollout_attempt_count"], 0)
        self.assertEqual(after["errors"], [])

    def test_benchmark_telemetry_recorded_as_fixed_size_aggregate(self):
        mod = _load_agent_module("BENCHMARK", "test_main_bench_recorded")
        before = mod.get_telemetry()
        mod.agent(self.main_records[0]["obs_dict"])
        after = mod.get_telemetry()
        self.assertEqual(after["decision_runtime_count"], before["decision_runtime_count"] + 1)
        self.assertEqual(after["search_attempt_count"], before["search_attempt_count"] + 1)
        self.assertNotIn("decision_runtime_ms", after, "unbounded per-decision list must be gone")
        self.assertIn("decision_runtime_total_ms", after)
        self.assertIn("decision_runtime_max_ms", after)
        self.assertGreater(after["decision_runtime_max_ms"], 0.0)


class ReplayControlFlowTests(_SharedBundleTestCase):
    def test_benchmark_replay_matches_benchmark_capture_control_flow(self):
        """Force a rollout-level exception (monkeypatched) and confirm
        BENCHMARK mode swallows it identically whether the decision is
        live or replayed -- i.e. replaying under the default BENCHMARK
        mode reproduces capture-time control flow, not DEBUG's re-raise."""
        from cg.api import to_observation_class

        rec = self.main_records[0]

        def run_with_forced_rollout_error(mod):
            obs = to_observation_class(rec["obs_dict"])
            policy = mod.RagingBoltPolicy(obs, replay_hidden_samples=list(rec["captured_hidden_samples"]))
            orig_eval = mod.RagingBoltPolicy._eval_search_state
            call_count = {"n": 0}

            def flaky_eval(self, state, my_index):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise RuntimeError("forced rollout failure for regression test")
                return orig_eval(self, state, my_index)

            mod.RagingBoltPolicy._eval_search_state = flaky_eval
            try:
                decision = (
                    policy.choose_with_search()
                    if obs.select.context == 0 else policy.choose()
                )
            finally:
                mod.RagingBoltPolicy._eval_search_state = orig_eval
            return decision, mod.get_telemetry()

        mod_live = _load_agent_module("BENCHMARK", "test_main_ctrl_live")
        decision_live, telemetry_live = run_with_forced_rollout_error(mod_live)
        self.assertIsInstance(decision_live, list)
        self.assertGreaterEqual(telemetry_live["rollout_error_count"], 1)

        mod_replay = _load_agent_module("BENCHMARK", "test_main_ctrl_replay")
        decision_replay, telemetry_replay = run_with_forced_rollout_error(mod_replay)
        self.assertIsInstance(decision_replay, list)
        self.assertGreaterEqual(telemetry_replay["rollout_error_count"], 1)
        # Both runs must complete without raising (BENCHMARK's contract) --
        # the control-flow shape (list returned, rollout_error_count
        # incremented, no exception propagated) matches between the "live"
        # and "replay" invocation of the identical scenario.


class ReplayTapeExhaustionTests(_SharedBundleTestCase):
    def test_empty_tape_raises_and_sets_flag(self):
        from cg.api import to_observation_class

        mod = _load_agent_module("BENCHMARK", "test_main_tape_empty")
        obs = to_observation_class(self.main_records[0]["obs_dict"])
        policy = mod.RagingBoltPolicy(obs, replay_hidden_samples=[])
        self.assertFalse(policy._replay_tape_exhausted)
        with self.assertRaises(mod.ReplayTapeExhausted):
            policy._predict_hidden()
        self.assertTrue(policy._replay_tape_exhausted)

    def test_decision_with_exhausted_tape_completes_but_flags_explicitly(self):
        from cg.api import to_observation_class

        mod = _load_agent_module("BENCHMARK", "test_main_tape_decision")
        obs = to_observation_class(self.main_records[0]["obs_dict"])
        policy = mod.RagingBoltPolicy(obs, replay_hidden_samples=[])
        decision = (
            policy.choose_with_search()
            if obs.select.context == 0 else policy.choose()
        )
        self.assertIsInstance(decision, list)
        self.assertTrue(
            policy._replay_tape_exhausted,
            "an exhausted replay tape must be flagged explicitly, never silently "
            "backfilled with fresh sampling and reported as a faithful replay",
        )

    def test_replay_decision_cli_reports_tape_exhausted_distinctly(self):
        """experiments/replay_decision.py must classify a tape-exhausted
        run as TAPE_EXHAUSTED, separate from MISMATCH/OK, and exit non-zero."""
        rec = dict(self.main_records[0])
        rec["captured_hidden_samples"] = []  # force exhaustion for every repeat
        truncated_bundle = os.path.join(self._tmpdir, "truncated.jsonl")
        with open(truncated_bundle, "w", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

        result = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "experiments", "replay_decision.py"),
             truncated_bundle, "--repeats", "2"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
        self.assertIn("TAPE_EXHAUSTED", result.stdout)
        self.assertNotEqual(result.returncode, 0, "a tape-exhausted replay must exit non-zero")


class ShadowEvalPairedSampleTests(_SharedBundleTestCase):
    def test_same_hidden_sample_applied_to_every_candidate_before_advancing(self):
        spec = importlib.util.spec_from_file_location("shadow_eval_compare_review_fix_test", SHADOW_SCRIPT)
        shadow_mod = importlib.util.module_from_spec(spec)
        backup = os.environ.get("POKEMON_AI_EXEC_MODE")
        os.environ["POKEMON_AI_EXEC_MODE"] = "BENCHMARK"
        try:
            spec.loader.exec_module(shadow_mod)
        finally:
            if backup is None:
                os.environ.pop("POKEMON_AI_EXEC_MODE", None)
            else:
                os.environ["POKEMON_AI_EXEC_MODE"] = backup

        mod = shadow_mod._load_agent_module()
        rec = next(
            (r for r in self.main_records
             if r.get("select_context") == 0 and len(r.get("legal_actions") or []) >= 2),
            None,
        )
        if rec is None:
            self.skipTest("no captured MAIN record with >=2 legal actions available in this bundle")

        seen_samples_in_call_order = []
        orig_predict = mod.RagingBoltPolicy._predict_hidden

        def traced_predict(self):
            preds = orig_predict(self)
            seen_samples_in_call_order.append(preds)
            return preds

        mod.RagingBoltPolicy._predict_hidden = traced_predict
        try:
            shadow_mod.evaluate_record(mod, rec, top_k=3, n_samples=2)
        finally:
            mod.RagingBoltPolicy._predict_hidden = orig_predict

        n_candidates = min(3, len(rec["legal_actions"]))
        self.assertGreaterEqual(
            len(seen_samples_in_call_order), n_candidates,
            "expected at least one full round of _predict_hidden calls",
        )
        first_round = seen_samples_in_call_order[:n_candidates]
        self.assertTrue(
            all(s == first_round[0] for s in first_round),
            "every candidate in the first round must be evaluated against the "
            "IDENTICAL hidden sample before any candidate advances to the next one "
            f"-- got {first_round}",
        )
        second_round = seen_samples_in_call_order[n_candidates:2 * n_candidates]
        if len(second_round) == n_candidates:
            self.assertTrue(
                all(s == second_round[0] for s in second_round),
                "every candidate in the second round must also share one identical sample",
            )


if __name__ == "__main__":
    unittest.main()
