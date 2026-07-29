"""Fast regression tests for the PR#202 review-fix round -- replay tape
exhaustion (RagingBoltPolicy._predict_hidden / ReplayTapeExhausted /
experiments/replay_decision.py's TAPE_EXHAUSTED reporting).

"Fast" here means: none of these tests exercise a real engine rollout
(cg.api.search_begin/search_step never actually run) -- an exhausted
replay tape makes _predict_hidden() raise immediately, before
_engine_search_choose ever calls search_begin. They still need ONE real
captured Observation (via experiments/_review_fix_bundle_fixture.py, a
short mirror match), which is the unavoidable, shared setup cost -- see
experiments/test_raging_bolt_review_fixes_integration.py for the tests
that genuinely need engine-backed rollouts (telemetry counters actually
incrementing from real search, shadow-eval paired sampling), split out
separately per review feedback since that suite is slower.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _review_fix_bundle_fixture import (
    REPO_ROOT,
    capture_bundle,
    load_agent_module,
)

_TMPDIR = None
_MAIN_RECORDS = None


def setUpModule():
    global _TMPDIR, _MAIN_RECORDS
    _TMPDIR, _bundle_path, _MAIN_RECORDS = capture_bundle(min_main_records=1)


def tearDownModule():
    if _TMPDIR:
        import shutil
        shutil.rmtree(_TMPDIR, ignore_errors=True)


class ReplayTapeExhaustionTests(unittest.TestCase):
    def test_empty_tape_raises_and_sets_flag(self):
        from cg.api import to_observation_class

        mod = load_agent_module("BENCHMARK", "test_main_tape_empty")
        obs = to_observation_class(_MAIN_RECORDS[0]["obs_dict"])
        policy = mod.RagingBoltPolicy(obs, replay_hidden_samples=[])
        self.assertFalse(policy._replay_tape_exhausted)
        with self.assertRaises(mod.ReplayTapeExhausted):
            policy._predict_hidden()
        self.assertTrue(policy._replay_tape_exhausted)

    def test_decision_with_exhausted_tape_completes_but_flags_explicitly(self):
        from cg.api import to_observation_class

        mod = load_agent_module("BENCHMARK", "test_main_tape_decision")
        obs = to_observation_class(_MAIN_RECORDS[0]["obs_dict"])
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
        rec = dict(_MAIN_RECORDS[0])
        rec["captured_hidden_samples"] = []  # force exhaustion for every repeat
        truncated_bundle = os.path.join(_TMPDIR, "truncated.jsonl")
        with open(truncated_bundle, "w", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

        result = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "experiments", "replay_decision.py"),
             truncated_bundle, "--repeats", "2"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
        self.assertIn("TAPE_EXHAUSTED", result.stdout)
        self.assertNotEqual(result.returncode, 0, "a tape-exhausted replay must exit non-zero")


if __name__ == "__main__":
    unittest.main()
