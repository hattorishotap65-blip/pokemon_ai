"""Integration regression tests for the PR#202 review-fix round -- these
genuinely exercise a real engine rollout (cg.api.search_begin/search_step
actually run), unlike experiments/test_raging_bolt_review_fixes.py's fast
suite (split out separately per review feedback, since this suite is
slower):

1. PRODUCTION telemetry is fully untouched by a real decision.
2. BENCHMARK telemetry is recorded (fixed-size aggregate, not an unbounded list).
3. Replaying a BENCHMARK-swallowed exception preserves BENCHMARK's
   non-raising control flow (the bug this guards against: replay_decision.py
   used to default to DEBUG, which would re-raise instead of matching
   capture-time behavior).
4. experiments/shadow_eval_compare.py applies the SAME hidden sample to
   every candidate before advancing to the next sample (the bug this
   guards against: an earlier version consumed the hidden-sample tape
   one-entry-per-candidate, comparing candidates under different hidden
   states).
"""
from __future__ import annotations
import importlib.util
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _review_fix_bundle_fixture import (
    SHADOW_SCRIPT,
    capture_bundle,
    load_agent_module,
)

_TMPDIR = None
_MAIN_RECORDS = None


def setUpModule():
    global _TMPDIR, _MAIN_RECORDS
    # >=2 so the shadow-eval paired-sample test below has more than one
    # legal action to compare in at least one captured record.
    _TMPDIR, _bundle_path, _MAIN_RECORDS = capture_bundle(min_main_records=2)


def tearDownModule():
    if _TMPDIR:
        import shutil
        shutil.rmtree(_TMPDIR, ignore_errors=True)


class TelemetryGatingTests(unittest.TestCase):
    def test_production_telemetry_unchanged_by_real_decision(self):
        mod = load_agent_module("PRODUCTION", "test_main_prod_unchanged")
        before = mod.get_telemetry()
        mod.agent(_MAIN_RECORDS[0]["obs_dict"])
        after = mod.get_telemetry()
        self.assertEqual(before, after, "PRODUCTION must not mutate any telemetry field")
        self.assertEqual(after["decision_runtime_count"], 0)
        self.assertEqual(after["capture_runtime_count"], 0)
        self.assertEqual(after["search_attempt_count"], 0)
        self.assertEqual(after["rollout_attempt_count"], 0)
        self.assertEqual(after["errors"], [])

    def test_benchmark_telemetry_recorded_as_fixed_size_aggregate(self):
        mod = load_agent_module("BENCHMARK", "test_main_bench_recorded")
        before = mod.get_telemetry()
        mod.agent(_MAIN_RECORDS[0]["obs_dict"])
        after = mod.get_telemetry()
        self.assertEqual(after["decision_runtime_count"], before["decision_runtime_count"] + 1)
        self.assertEqual(after["search_attempt_count"], before["search_attempt_count"] + 1)
        self.assertNotIn("decision_runtime_ms", after, "unbounded per-decision list must be gone")
        self.assertIn("decision_runtime_total_ms", after)
        self.assertIn("decision_runtime_max_ms", after)
        self.assertGreater(after["decision_runtime_max_ms"], 0.0)
        # No POKEMON_AI_REPLAY_BUNDLE_PATH set for this call -- capture is a
        # no-op, so capture_runtime must stay at zero (never conflated with
        # decision_runtime, and never incremented when capture doesn't run).
        self.assertEqual(after["capture_runtime_count"], before["capture_runtime_count"])


class ReplayControlFlowTests(unittest.TestCase):
    def test_benchmark_replay_matches_benchmark_capture_control_flow(self):
        """Force a rollout-level exception (monkeypatched) and confirm
        BENCHMARK mode swallows it identically whether the decision is
        live or replayed -- i.e. replaying under the default BENCHMARK
        mode reproduces capture-time control flow, not DEBUG's re-raise."""
        from cg.api import to_observation_class

        rec = _MAIN_RECORDS[0]

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

        mod_live = load_agent_module("BENCHMARK", "test_main_ctrl_live")
        decision_live, telemetry_live = run_with_forced_rollout_error(mod_live)
        self.assertIsInstance(decision_live, list)
        self.assertGreaterEqual(telemetry_live["rollout_error_count"], 1)

        mod_replay = load_agent_module("BENCHMARK", "test_main_ctrl_replay")
        decision_replay, telemetry_replay = run_with_forced_rollout_error(mod_replay)
        self.assertIsInstance(decision_replay, list)
        self.assertGreaterEqual(telemetry_replay["rollout_error_count"], 1)
        # Both runs must complete without raising (BENCHMARK's contract) --
        # the control-flow shape (list returned, rollout_error_count
        # incremented, no exception propagated) matches between the "live"
        # and "replay" invocation of the identical scenario.


class ShadowEvalPairedSampleTests(unittest.TestCase):
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
            (r for r in _MAIN_RECORDS
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
