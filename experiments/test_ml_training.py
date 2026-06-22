"""
Tests for experiments/train_ml_policy.py.

Run: python experiments/test_ml_training.py
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.train_ml_policy import (
    load_examples, group_by_decision, flatten_numeric_features,
    score_features, train_pairwise_ranker, evaluate_ranker,
    save_weights, load_weights, get_sample_weight,
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

# ===================================================================
print("\n--- flatten_numeric_features ---")

ff = flatten_numeric_features({"a": 1, "b": 2.5, "c": True, "d": False,
                               "e": "skip", "f": None, "g": [1, 2]})
check("int preserved", ff["a"] == 1.0)
check("float preserved", ff["b"] == 2.5)
check("bool True -> 1.0", ff["c"] == 1.0)
check("bool False -> 0.0", ff["d"] == 0.0)
check("string skipped", "e" not in ff)
check("None skipped", "f" not in ff)
check("list skipped", "g" not in ff)

# one-hot
ff_oh = flatten_numeric_features({"best_plan_type": "winning_ko", "option_class": "attack"})
check("one-hot plan_type", ff_oh.get("best_plan_type=winning_ko") == 1.0)
check("one-hot option_class", ff_oh.get("option_class=attack") == 1.0)

ff_empty = flatten_numeric_features(None)
check("None features: empty dict", ff_empty == {})

ff_nan = flatten_numeric_features({"x": float("nan"), "y": float("inf")})
check("NaN skipped", "x" not in ff_nan)
check("Inf skipped", "y" not in ff_nan)

# ===================================================================
print("\n--- load_examples ---")

with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
    f.write(json.dumps({"decision_id": "d1", "selected": True, "features": {"a": 1}}) + "\n")
    f.write(json.dumps({"decision_id": "d1", "selected": False, "features": {"a": 0}}) + "\n")
    f.write(json.dumps({"decision_id": "d2", "selected": True, "features": {"a": 2}}) + "\n")
    tmp_path = f.name

exs = load_examples(tmp_path)
check("Load 3 examples", len(exs) == 3)
os.unlink(tmp_path)

# max_examples
with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
    for i in range(10):
        f.write(json.dumps({"i": i}) + "\n")
    tmp2 = f.name

exs2 = load_examples(tmp2, max_examples=3)
check("max_examples=3", len(exs2) == 3)
os.unlink(tmp2)

# ===================================================================
print("\n--- group_by_decision ---")

groups = group_by_decision(exs)
check("2 groups", len(groups) == 2)
check("d1 has 2", len(groups["d1"]) == 2)

# ===================================================================
print("\n--- score_features ---")

s = score_features({"a": 1.0, "b": 2.0}, {"a": 3.0, "b": -1.0})
check("Score = 1*3 + 2*(-1) = 1.0", s == 1.0)

s_empty = score_features({}, {"a": 3.0})
check("Empty features: 0.0", s_empty == 0.0)

# ===================================================================
print("\n--- train_pairwise_ranker ---")

train_data = [
    {"decision_id": "t1", "selected": True, "features": {"x": 10, "y": 1}},
    {"decision_id": "t1", "selected": False, "features": {"x": 2, "y": 5}},
    {"decision_id": "t2", "selected": True, "features": {"x": 8, "y": 0}},
    {"decision_id": "t2", "selected": False, "features": {"x": 1, "y": 3}},
    {"decision_id": "t2", "selected": False, "features": {"x": 3, "y": 4}},
]
train_groups = group_by_decision(train_data)
weights = train_pairwise_ranker(train_groups, epochs=3, lr=0.05, seed=42)
check("Weights not empty", len(weights) > 0)
check("x weight positive", weights.get("x", 0) > 0)

# ===================================================================
print("\n--- evaluate_ranker ---")

metrics = evaluate_ranker(train_groups, weights)
check("Metrics is dict", isinstance(metrics, dict))
check("Has top1_accuracy", "top1_accuracy" in metrics)
check("Has avg_selected_rank", "avg_selected_rank" in metrics)
check("Has selected_score_margin_avg", "selected_score_margin_avg" in metrics)
check("top1_accuracy <= 1.0", metrics["top1_accuracy"] <= 1.0)

# ===================================================================
print("\n--- save / load weights ---")

with tempfile.TemporaryDirectory() as td:
    path = os.path.join(td, "w.json")
    save_weights(path, {"a": 0.5, "b": -0.3}, {"top1_accuracy": 0.8})

    loaded = load_weights(path)
    check("Loaded is dict", isinstance(loaded, dict))
    check("enabled=False", loaded["enabled"] == False)
    check("Weights present", "a" in loaded["weights"])
    check("Metrics present", loaded["metrics"]["top1_accuracy"] == 0.8)
    check("model_type", loaded["model_type"] == "pairwise_linear_ranker")

# ===================================================================
print("\n--- edge cases ---")

# No positives
empty_groups = group_by_decision([
    {"decision_id": "e1", "selected": False, "features": {"x": 1}},
])
w_empty = train_pairwise_ranker(empty_groups, epochs=1, lr=0.01)
check("No positives: empty weights", w_empty == {})

m_empty = evaluate_ranker(empty_groups, {})
check("No positives: decisions=0", m_empty["decisions"] == 0)

# None features
w_none = train_pairwise_ranker(
    group_by_decision([
        {"decision_id": "n1", "selected": True, "features": None},
        {"decision_id": "n1", "selected": False, "features": None},
    ]),
    epochs=1, lr=0.01,
)
check("None features: no crash", isinstance(w_none, dict))

# ===================================================================
print("\n--- get_sample_weight ---")

check("win -> 1.0", get_sample_weight({"outcome": {"outcome_weight": 1.0}}) == 1.0)
check("loss -> 0.3", get_sample_weight({"outcome": {"outcome_weight": -1.0}}) == 0.3)
check("draw -> 0.5", get_sample_weight({"outcome": {"outcome_weight": 0.0}}) == 0.5)
check("unknown -> 0.7", get_sample_weight({"outcome": {"outcome_weight": None}}) == 0.7)
check("no outcome -> 0.7", get_sample_weight({}) == 0.7)
check("no outcome key -> 0.7", get_sample_weight({"outcome": {}}) == 0.7)

# ===================================================================
print("\n--- deck_id one-hot ---")

ff_deck = flatten_numeric_features({"x": 1}, {"deck_id": "ionos_kilowattrel", "opponent_deck_id": "unknown"})
check("deck_id one-hot", ff_deck.get("deck_id=ionos_kilowattrel") == 1.0)
check("opponent_deck_id one-hot", ff_deck.get("opponent_deck_id=unknown") == 1.0)
check("numeric preserved with extra", ff_deck.get("x") == 1.0)

# ===================================================================
print("\n--- outcome-weighted training ---")

ow_data = [
    {"decision_id": "w1", "selected": True, "features": {"x": 10, "y": 1},
     "outcome": {"outcome_weight": 1.0}},
    {"decision_id": "w1", "selected": False, "features": {"x": 2, "y": 5}},
    {"decision_id": "l1", "selected": True, "features": {"x": 8, "y": 0},
     "outcome": {"outcome_weight": -1.0}},
    {"decision_id": "l1", "selected": False, "features": {"x": 1, "y": 3}},
]
ow_groups = group_by_decision(ow_data)
w_ow = train_pairwise_ranker(ow_groups, epochs=3, lr=0.05, seed=42, use_outcome_weighting=True)
check("OW training: weights not empty", len(w_ow) > 0)

w_no_ow = train_pairwise_ranker(ow_groups, epochs=3, lr=0.05, seed=42, use_outcome_weighting=False)
check("No OW training: weights not empty", len(w_no_ow) > 0)

# ===================================================================
print("\n--- evaluate with weighted metrics ---")

m_ow = evaluate_ranker(ow_groups, w_ow)
check("Has weighted_top1_accuracy", "weighted_top1_accuracy" in m_ow)
check("Has win_weighted_decisions", "win_weighted_decisions" in m_ow)
check("Has loss_weighted_decisions", "loss_weighted_decisions" in m_ow)
check("Has unknown_outcome_decisions", "unknown_outcome_decisions" in m_ow)
check("win_decisions count", m_ow["win_weighted_decisions"] == 1)
check("loss_decisions count", m_ow["loss_weighted_decisions"] == 1)

# ===================================================================
print("\n--- save with training_config ---")

with tempfile.TemporaryDirectory() as td:
    path = os.path.join(td, "ow.json")
    tc = {"epochs": 5, "lr": 0.01, "use_outcome_weighting": True,
          "sample_weighting": "win=1.0,loss=0.3,draw=0.5,unknown=0.7"}
    save_weights(path, {"a": 0.5}, {"top1_accuracy": 0.9}, tc)
    loaded = load_weights(path)
    check("enabled=False", loaded["enabled"] == False)
    check("mode=outcome_weighted_offline", loaded["mode"] == "outcome_weighted_offline")
    check("training_config present", "training_config" in loaded)
    check("output valid JSON", isinstance(json.dumps(loaded), str))

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
