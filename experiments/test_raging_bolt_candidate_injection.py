"""Unit tests for the win-rate-cycle1 candidate-coverage guarantee in
RagingBoltPolicy._engine_search_choose() (rule_tactical_candidate_guarantees).

_score_option() caps ATTACK at min(base,700) and ATTACH at min(base,1100)
whenever a competing PLAY/ABILITY/supporter is legal (main.py's
_score_option), so a lethal attack, the attach that completes Bellowing
Thunder's energy requirement, or a retreat that enables an attacker can rank
below the heuristic top_k and never reach engine search. These tests
construct a bare RagingBoltPolicy instance (bypassing __init__ and
rank()/_score_option(), which need a real Observation) with exactly the
attributes _engine_search_choose()'s candidate-construction block reads, then
monkeypatch _predict_hidden() to raise immediately -- this happens strictly
after candidate-list construction (and after this PR's injection telemetry
is recorded) but before any real engine call, so no cg.api engine work
actually runs. The per-candidate try/except in _ucb1_choose /
_engine_search_choose's flat-allocation loop swallows that raise, so the
call completes (returning None, since no candidate got a successful
rollout) without needing a real search_begin/search_step/search_end.

Still needs `cg` (for OptionType/AreaType/main.py's module-level import),
hence WSL/Linux + reference/extracted/cg on sys.path, like the rest of this
suite.
"""
from __future__ import annotations
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _review_fix_bundle_fixture import load_agent_module

_PredictHiddenSentinel = RuntimeError("test: _predict_hidden must not be reached by candidate-construction assertions")


def _make_bare_policy(mod, options, *, active_id=0, bolt_ready=False,
                       can_ko_with_bt=False, bt_total_energy=0, opp_active_hp=0,
                       bench=None):
    """A RagingBoltPolicy instance with only the attributes
    _engine_search_choose()'s candidate-construction block reads. No
    Observation, no rank()/_score_option() call -- ranked/scores are passed
    in directly by the caller instead."""
    policy = object.__new__(mod.RagingBoltPolicy)
    policy.select = types.SimpleNamespace(option=options, maxCount=1, minCount=0)
    policy.obs = None  # never dereferenced unless the attach-lethal branch fires
    policy.my_index = 0
    policy.active_id = active_id
    policy.bolt_ready = bolt_ready
    policy.can_ko_with_bt = can_ko_with_bt
    policy.bt_total_energy = bt_total_energy
    policy.opp_active = types.SimpleNamespace(hp=opp_active_hp) if opp_active_hp else None
    policy.opp_active_hp = opp_active_hp
    policy.me = types.SimpleNamespace(bench=bench or [], prize=[])
    policy.opponent = types.SimpleNamespace(prize=[])

    def _raise_predict_hidden(self):
        raise _PredictHiddenSentinel
    policy._predict_hidden = types.MethodType(_raise_predict_hidden, policy)
    return policy


class AttackCandidateInjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_agent_module("BENCHMARK", "test_main_candidate_injection")

    def setUp(self):
        self.mod.reset_telemetry()

    def test_lethal_attack_crowded_out_of_top5_is_injected(self):
        """5 PLAY options outrank a lethal ATTACK (option index 5, scored
        last) -- top_k=5 alone would never let engine search see the attack
        at all. rule_tactical_candidate_guarantees must add it back."""
        OptionType = self.mod.OptionType
        options = [types.SimpleNamespace(type=OptionType.PLAY, index=i) for i in range(5)]
        options.append(types.SimpleNamespace(type=OptionType.ATTACK, index=5, attackId=0))
        ranked = [0, 1, 2, 3, 4, 5]
        scores = [1000, 900, 800, 700, 600, 50]

        policy = _make_bare_policy(self.mod, options, can_ko_with_bt=True)
        policy._engine_search_choose(ranked, scores)

        telemetry = self.mod.get_telemetry()
        self.assertEqual(
            telemetry["candidate_injection_attack_count"], 1,
            "the excluded ATTACK must be injected exactly once",
        )
        self.assertEqual(telemetry["candidate_injection_decision_count"], 1)

    def test_attack_already_in_top_k_is_not_double_injected(self):
        """If the ATTACK already ranks inside top_k, no injection should
        fire -- the guarantee only fills a genuine coverage gap."""
        OptionType = self.mod.OptionType
        options = [types.SimpleNamespace(type=OptionType.ATTACK, index=0, attackId=0)]
        options += [types.SimpleNamespace(type=OptionType.PLAY, index=i) for i in range(1, 5)]
        ranked = [0, 1, 2, 3, 4]
        scores = [2300, 1000, 900, 800, 700]

        policy = _make_bare_policy(self.mod, options, can_ko_with_bt=True)
        policy._engine_search_choose(ranked, scores)

        telemetry = self.mod.get_telemetry()
        self.assertEqual(telemetry["candidate_injection_attack_count"], 0)
        self.assertEqual(telemetry["candidate_injection_decision_count"], 0)

    def test_injection_gate_can_be_disabled_via_params(self):
        """rule_tactical_candidate_guarantees=0 must fully restore baseline
        (pre-candidate-1) behavior -- rollback path."""
        OptionType = self.mod.OptionType
        options = [types.SimpleNamespace(type=OptionType.PLAY, index=i) for i in range(5)]
        options.append(types.SimpleNamespace(type=OptionType.ATTACK, index=5, attackId=0))
        ranked = [0, 1, 2, 3, 4, 5]
        scores = [1000, 900, 800, 700, 600, 50]

        backup = self.mod.P.get("rule_tactical_candidate_guarantees")
        self.mod.P["rule_tactical_candidate_guarantees"] = 0
        try:
            policy = _make_bare_policy(self.mod, options, can_ko_with_bt=True)
            policy._engine_search_choose(ranked, scores)
        finally:
            if backup is None:
                self.mod.P.pop("rule_tactical_candidate_guarantees", None)
            else:
                self.mod.P["rule_tactical_candidate_guarantees"] = backup

        telemetry = self.mod.get_telemetry()
        self.assertEqual(telemetry["candidate_injection_attack_count"], 0)

    def test_injection_budget_caps_at_two_even_with_all_three_gaps_present(self):
        """Attack, lethal-attach, and attacker-enabling-retreat are all
        simultaneously excluded from top_k -- the +2 ceiling (protecting the
        fixed rollout budget) must still cap total injections at 2, not 3."""
        OptionType = self.mod.OptionType
        AreaType = self.mod.AreaType
        C = self.mod.C

        class _FakeAttachedPokemon:
            id = C.RAGING_BOLT_EX
            energies = [4]  # lightning only -- fighting still needed, so "fills_bt_req"-eligible

        class _FakeBenchBolt:
            id = C.RAGING_BOLT_EX
            energies = [4, 6]  # ready: has both lightning and fighting

        def fake_get_card(obs, area, index, player_index):
            if area == AreaType.ACTIVE:
                return _FakeAttachedPokemon()
            return None

        orig_get_card = self.mod.get_card
        self.mod.get_card = fake_get_card
        try:
            options = [types.SimpleNamespace(type=OptionType.PLAY, index=i) for i in range(5)]
            options.append(types.SimpleNamespace(type=OptionType.ATTACK, index=5, attackId=0))
            options.append(types.SimpleNamespace(
                type=OptionType.ATTACH, index=6, inPlayArea=AreaType.ACTIVE, inPlayIndex=0))
            options.append(types.SimpleNamespace(type=OptionType.RETREAT, index=7))
            ranked = [0, 1, 2, 3, 4, 5, 6, 7]
            scores = [1000, 900, 800, 700, 600, 50, 40, 30]

            policy = _make_bare_policy(
                self.mod, options,
                active_id=C.RAGING_BOLT_EX, bolt_ready=True,
                can_ko_with_bt=False, bt_total_energy=3, opp_active_hp=200,
                bench=[_FakeBenchBolt()],
            )
            policy._engine_search_choose(ranked, scores)
        finally:
            self.mod.get_card = orig_get_card

        telemetry = self.mod.get_telemetry()
        total_injections = (
            telemetry["candidate_injection_attack_count"]
            + telemetry["candidate_injection_attach_lethal_count"]
            + telemetry["candidate_injection_retreat_count"]
        )
        self.assertLessEqual(
            total_injections, 2,
            "the +2 injection ceiling must hold even when all three gaps are present",
        )
        self.assertGreaterEqual(total_injections, 1, "at least the highest-priority gap should be filled")


if __name__ == "__main__":
    unittest.main()
