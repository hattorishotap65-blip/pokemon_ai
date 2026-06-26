"""
Tests for experiments/learning/decision_advisor.py.

Run: python experiments/test_learning_decision_advisor.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.learning.decision_advisor import rank_candidates, choose_best_candidate

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


STATE = {
    "active": "タケルライコex",
    "bench": ["オーガポンみどりのめんex"],
    "hand": ["アカマツ"],
    "discard": [],
    "prizes_remaining": 6,
    "opponent_active": "X",
    "opponent_bench": [],
}

CANDIDATES = [
    {"id": "play_crispin", "label": "アカマツを使う", "type": "supporter"},
    {"id": "use_teal_dance", "label": "みどりのまいを使う", "type": "ability"},
    {"id": "attack_bellowing", "label": "Bellowing Thunderで攻撃する", "type": "attack"},
]

WEIGHTS = {"use_crispin_value": 55.0, "teal_dance_value": 50.0, "energy_discard_risk": -20.0}

print("=== rank_candidates ===")

ranked = rank_candidates(STATE, CANDIDATES, WEIGHTS)
check("rank returns list", isinstance(ranked, list) and len(ranked) == 3)
check("ranked by score descending", ranked[0]["score"] >= ranked[1]["score"] >= ranked[2]["score"])
check("action_id present", all("action_id" in r for r in ranked))
check("original_index preserved", set(r["original_index"] for r in ranked) == {0, 1, 2})
check("normalized_action present", all("normalized_action" in r for r in ranked))
check("crispin ranks first", ranked[0]["action_id"] == "play_crispin")

print("\n=== choose_best_candidate ===")

best = choose_best_candidate(STATE, CANDIDATES, WEIGHTS)
check("best is not None", best is not None)
check("best is crispin", best["action_id"] == "play_crispin")

print("\n=== edge cases ===")

check("empty candidates -> []", rank_candidates(STATE, [], WEIGHTS) == [])
check("empty candidates -> None", choose_best_candidate(STATE, [], WEIGHTS) is None)
check("empty weights -> no crash", len(rank_candidates(STATE, CANDIDATES, {})) == 3)
check("None state -> no crash", len(rank_candidates(None, CANDIDATES, WEIGHTS)) == 3)

unknown_cands = [{"id": "mystery", "label": "something unknown"}]
ranked_unk = rank_candidates(STATE, unknown_cands, WEIGHTS)
check("unknown action -> score 0, no crash", len(ranked_unk) == 1 and ranked_unk[0]["score"] == 0.0)

check("non-list candidates -> []", rank_candidates(STATE, "bad", WEIGHTS) == [])

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
