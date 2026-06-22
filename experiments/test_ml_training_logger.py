"""
Tests for agent/ml_training_logger.py.

Run: python experiments/test_ml_training_logger.py
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.ml_training_logger import (
    make_training_example, serialize_action, serialize_state_summary,
    append_jsonl, write_jsonl, _safe_value,
    infer_deck_id, infer_opponent_deck_id, compute_outcome_weight,
)

PASS = "[PASS]"
FAIL = "[FAIL]"
_failures = 0
_total = 0

def check(label, condition):
    global _failures, _total
    _total += 1
    status = PASS if condition else FAIL
    print(f"  {status}  {label}")
    if not condition:
        _failures += 1

STATE = {
    "active_pokemon": {"card_id": "269", "hp_remaining": 250, "energy_count": 4},
    "bench": [{"card_id": "265"}],
    "prizes_remaining": 3, "turn": 5,
    "opponent": {
        "prizes_remaining": 4,
        "active_pokemon": {"card_id": "999", "hp_remaining": 100},
        "bench": [],
    },
}
ACTION = {"type": 13, "attackId": 1, "cardId": "269", "index": 0, "area": 0}
BREAKDOWN = {
    "type_score": 10.0, "adv_score": 5.0, "attack_plan_bonus": 2.5,
    "ml_score": 0.0, "ml_reason": "",
}
FEATURES = {
    "prizes_remaining": 3, "is_attack": True, "predicted_damage": 230,
    "can_ko": True, "best_plan_type": "winning_ko",
    "action_matches_plan": True, "action_plan_bonus": 15.0,
}

# ===================================================================
print("\n--- make_training_example ---")

ex = make_training_example(
    state=STATE, action=ACTION, selected=True,
    score=123.4, reason="test", breakdown=BREAKDOWN,
    features=FEATURES, game_id=80001, decision_id="80001-5-3",
    candidate_index=0,
)
check("Returns dict", isinstance(ex, dict))
check("selected=True", ex["selected"] == True)
check("score preserved", ex["score"] == 123.4)
check("game_id", ex["game_id"] == 80001)
check("decision_id", ex["decision_id"] == "80001-5-3")
check("features included", "features" in ex)
check("breakdown included", "breakdown" in ex)
check("action included", "action" in ex)
check("state_summary included", "state_summary" in ex)

# JSON serializable
j = json.dumps(ex)
check("JSON serializable", isinstance(j, str))
parsed = json.loads(j)
check("Round-trip valid", parsed["selected"] == True)

# ===================================================================
print("\n--- selected=False ---")

ex_f = make_training_example(state=STATE, action=ACTION, selected=False, score=50.0)
check("selected=False stored", ex_f["selected"] == False)

# ===================================================================
print("\n--- serialize_action ---")

sa = serialize_action(ACTION)
check("Action type", sa["type"] == 13)
check("Action cardId", sa["cardId"] == "269")
check("Action attackId", sa["attackId"] == 1)
check("None action: empty dict", serialize_action(None) == {})

# ===================================================================
print("\n--- serialize_state_summary ---")

ss = serialize_state_summary(STATE)
check("State prizes", ss["prizes_remaining"] == 3)
check("State active cid", ss["my_active_cid"] == "269")
check("None state: empty dict", serialize_state_summary(None) == {})

# ===================================================================
print("\n--- breakdown with ml_score ---")

ex_ml = make_training_example(state=STATE, action=ACTION, selected=True,
                              breakdown={"ml_score": 5.0, "ml_reason": "ml_linear",
                                         "attack_plan_bonus": 10.0})
check("ML score in breakdown", ex_ml["breakdown"]["ml_score"] == 5.0)
check("Plan bonus in breakdown", ex_ml["breakdown"]["attack_plan_bonus"] == 10.0)

# ===================================================================
print("\n--- None / empty safety ---")

ex_none = make_training_example(state=None, action=None, selected=False)
check("None state/action: no crash", isinstance(ex_none, dict))
check("None: JSON serializable", isinstance(json.dumps(ex_none), str))

ex_empty = make_training_example(state={}, action={}, selected=True)
check("Empty: no crash", isinstance(ex_empty, dict))

# ===================================================================
print("\n--- _safe_value edge cases ---")

check("safe: set", _safe_value({1, 2, 3}) == ["1", "2", "3"])
check("safe: tuple", _safe_value((1, 2)) == [1, 2])
check("safe: None", _safe_value(None) is None)
check("safe: object", isinstance(_safe_value(object()), str))

# ===================================================================
print("\n--- append_jsonl ---")

with tempfile.TemporaryDirectory() as td:
    path = os.path.join(td, "sub", "test.jsonl")
    append_jsonl(path, {"a": 1})
    append_jsonl(path, {"b": 2})
    with open(path) as f:
        lines = f.readlines()
    check("append_jsonl: 2 lines", len(lines) == 2)
    check("append_jsonl: valid JSON", json.loads(lines[0])["a"] == 1)

# ===================================================================
print("\n--- write_jsonl ---")

with tempfile.TemporaryDirectory() as td:
    path = os.path.join(td, "batch.jsonl")
    write_jsonl(path, [{"x": 1}, {"x": 2}, {"x": 3}])
    with open(path) as f:
        lines = f.readlines()
    check("write_jsonl: 3 lines", len(lines) == 3)

# ===================================================================
print("\n--- outcome schema ---")

ex_out = make_training_example(
    state=STATE, action=ACTION, selected=True, score=10.0,
    deck_id="ionos_kilowattrel", opponent_deck_id="mirror",
    game_result="win", winner="player1", final_score=100.0,
    prizes_taken=6, opponent_prizes_taken=3, turn_count=15,
    safety_violation=False, outcome_weight=1.0,
)
check("deck_id stored", ex_out["deck_id"] == "ionos_kilowattrel")
check("opponent_deck_id stored", ex_out["opponent_deck_id"] == "mirror")
check("outcome block present", "outcome" in ex_out)
check("outcome.game_result", ex_out["outcome"]["game_result"] == "win")
check("outcome.winner", ex_out["outcome"]["winner"] == "player1")
check("outcome.prizes_taken", ex_out["outcome"]["prizes_taken"] == 6)
check("outcome.turn_count", ex_out["outcome"]["turn_count"] == 15)
check("outcome.safety_violation", ex_out["outcome"]["safety_violation"] == False)
check("outcome.outcome_weight", ex_out["outcome"]["outcome_weight"] == 1.0)
check("Outcome JSON serializable", isinstance(json.dumps(ex_out), str))

# No outcome when not provided
ex_no_out = make_training_example(state=STATE, action=ACTION, selected=True)
check("No outcome when empty", "outcome" not in ex_no_out)
check("No deck_id when empty", "deck_id" not in ex_no_out)

# ===================================================================
print("\n--- state_summary extended fields ---")

STATE_EXT = {
    "active_pokemon": {"card_id": "269", "hp_remaining": 250, "energy_count": 4, "is_ex": True},
    "bench": [{"card_id": "265"}],
    "prizes_remaining": 3, "deck_count": 20, "hand_count": 5,
    "opponent": {
        "prizes_remaining": 4,
        "active_pokemon": {"card_id": "999", "hp_remaining": 100, "is_ex": False},
        "bench": [{"card_id": "888"}, {"card_id": "777"}],
    },
}
ss = serialize_state_summary(STATE_EXT)
check("deck_count in summary", ss["deck_count"] == 20)
check("hand_count in summary", ss["hand_count"] == 5)
check("my_active_is_ex", ss["my_active_is_ex"] == True)
check("opp_active_is_ex", ss["opp_active_is_ex"] == False)
check("opp_bench_count", ss["opp_bench_count"] == 2)

# ===================================================================
print("\n--- infer_deck_id ---")

check("deck_name", infer_deck_id({"deck_name": "ionos"}) == "ionos")
check("deck_id", infer_deck_id({"deck_id": "abc"}) == "abc")
check("empty -> unknown", infer_deck_id({}) == "unknown")
check("None -> unknown", infer_deck_id(None) == "unknown")

# ===================================================================
print("\n--- infer_opponent_deck_id ---")

check("opp deck_name", infer_opponent_deck_id({"opponent": {"deck_name": "mirror"}}) == "mirror")
check("opp empty -> unknown", infer_opponent_deck_id({}) == "unknown")
check("opp None -> unknown", infer_opponent_deck_id(None) == "unknown")

# ===================================================================
print("\n--- compute_outcome_weight ---")

check("win -> 1.0", compute_outcome_weight("win") == 1.0)
check("won -> 1.0", compute_outcome_weight("won") == 1.0)
check("loss -> -1.0", compute_outcome_weight("loss") == -1.0)
check("lost -> -1.0", compute_outcome_weight("lost") == -1.0)
check("draw -> 0.0", compute_outcome_weight("draw") == 0.0)
check("tie -> 0.0", compute_outcome_weight("tie") == 0.0)
check("empty -> None", compute_outcome_weight("") is None)
check("unknown -> None", compute_outcome_weight("something") is None)
check("WIN case insensitive", compute_outcome_weight("WIN") == 1.0)

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
