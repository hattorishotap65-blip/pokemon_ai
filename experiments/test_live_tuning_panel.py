"""Tests for the Live Tuning Panel logic in live_tuning.py:
suggested params from live_review, before/after preview, and log entries
that include reviewer label/confidence/note."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "web"))

from experiments.web import live_tuning as lt

PASS = "[PASS]"
FAIL = "[FAIL]"
_f = 0
_t = 0


def check(label, cond):
    global _f, _t
    _t += 1
    print("  %s  %s" % (PASS if cond else FAIL, label))
    if not cond:
        _f += 1


REAL_PARAMS = {
    "eval_no_backup_risk": -400, "eval_active_ko_risk": -400,
    "score_supporter_crispin": 1030, "score_item_energy_retrieval": 900,
    "score_attack_bellowing_thunder": 840, "eval_boss_win": 800,
    "score_supporter_boss": 900, "impact_boss_prize_mult": 300,
    "search_weight_future": 0.3, "score_retreat": 80, "search_weight_risk": 0.1,
}


def setup():
    lt.reset_runtime_overrides()


# === suggest_params_for_live_review: None / empty ===
print("=== suggest_params_for_live_review: empty input ===")
check("None live_review -> []", lt.suggest_params_for_live_review(None) == [])
check("empty dict -> []", lt.suggest_params_for_live_review({}) == [])

# === category-based suggestion ===
print("\n=== category-based suggestion ===")
lr = {"category": "no_next_attacker", "risk_flags": ["no_next_attacker"]}
suggestions = lt.suggest_params_for_live_review(lr, available_params=REAL_PARAMS)
check("no_next_attacker: non-empty", len(suggestions) > 0)
check("no_next_attacker: includes eval_no_backup_risk", "eval_no_backup_risk" in suggestions)
check("no_next_attacker: includes score_supporter_crispin", "score_supporter_crispin" in suggestions)
check("no_next_attacker: all suggestions exist in params", all(s in REAL_PARAMS for s in suggestions))
check("no_next_attacker: no duplicates", len(suggestions) == len(set(suggestions)))

# === suggestions filtered to params that actually exist ===
print("\n=== filtered to available_params ===")
narrow_params = {"eval_no_backup_risk": -400}
suggestions2 = lt.suggest_params_for_live_review(lr, available_params=narrow_params)
check("filtered: only existing key kept", suggestions2 == ["eval_no_backup_risk"])

# === unknown category falls back to risk-flag suggestions only ===
print("\n=== unknown category, known risk flag ===")
lr2 = {"category": "totally_unknown_category", "risk_flags": ["not_enough_energy"]}
suggestions3 = lt.suggest_params_for_live_review(lr2, available_params=REAL_PARAMS)
check("unknown category + known flag: non-empty", len(suggestions3) > 0)
check("unknown category + known flag: relevant param present",
      "score_item_energy_retrieval" in suggestions3)


# === build_tuning_preview: fake compute_fn, before != after ===
print("\n=== build_tuning_preview: changed recommendation ===")
setup()


def _fake_compute(params):
    # AI prefers the attack at default risk, but a harsher eval_no_backup_risk
    # override drags the attack's score below the supporter's.
    risk_penalty = params.get("eval_no_backup_risk", -400)
    attack_score = 3200 + risk_penalty
    supporter_score = params.get("score_supporter_crispin", 1030) + 1500
    return [
        {"label": "Bellowing Thunder", "score": attack_score},
        {"label": "Crispin", "score": supporter_score},
    ]


lt.set_runtime_override(REAL_PARAMS, "eval_no_backup_risk", -1000)
preview = lt.build_tuning_preview(_fake_compute, REAL_PARAMS)
check("preview: before recommends attack", preview["before"]["recommended_action"] == "Bellowing Thunder")
check("preview: after recommends supporter", preview["after"]["recommended_action"] == "Crispin")
check("preview: changed True", preview["changed"] is True)
check("preview: before top_candidates non-empty", len(preview["before"]["top_candidates"]) == 2)
check("preview: after top_candidates non-empty", len(preview["after"]["top_candidates"]) == 2)

# === build_tuning_preview: no overrides -> unchanged ===
print("\n=== build_tuning_preview: no overrides ===")
setup()
preview_same = lt.build_tuning_preview(_fake_compute, REAL_PARAMS)
check("no overrides: changed False", preview_same["changed"] is False)
check("no overrides: before == after action",
      preview_same["before"]["recommended_action"] == preview_same["after"]["recommended_action"])

# === build_tuning_preview: compute_fn raises -> no crash, safe shape ===
print("\n=== build_tuning_preview: exception safety ===")
setup()


def _boom(params):
    raise RuntimeError("policy blew up")


preview_safe = lt.build_tuning_preview(_boom, REAL_PARAMS)
check("compute_fn raises: no exception propagated", isinstance(preview_safe, dict))
check("compute_fn raises: before is empty shape", preview_safe["before"]["recommended_action"] is None)
check("compute_fn raises: after is empty shape", preview_safe["after"]["recommended_action"] is None)
check("compute_fn raises: changed is False (None == None)", preview_safe["changed"] is False)

# === build_tuning_preview: compute_fn returns garbage -> no crash ===
print("\n=== build_tuning_preview: garbage candidates ===")
setup()
garbage_preview = lt.build_tuning_preview(lambda p: "not-a-list", REAL_PARAMS)
check("garbage candidates: no crash", isinstance(garbage_preview, dict))

# === label / confidence / note round-trip through the log entry ===
print("\n=== reviewer label/confidence/note ===")
setup()
entry = lt.build_tuning_log_entry(
    game_id="g7", turn=5, live_review={"category": "no_next_attacker", "risk_flags": ["no_next_attacker"],
                                        "human_action": "Crispin"},
    param="eval_no_backup_risk", old_value=-400, new_value=-1000,
    preview=preview, review_label="human_better", confidence="high", note="次アタッカー不在を回避できた",
)
check("entry: review_label saved", entry["review_label"] == "human_better")
check("entry: confidence saved", entry["confidence"] == "high")
check("entry: note saved", entry["note"] == "次アタッカー不在を回避できた")
check("entry: review_label is a known LABEL", entry["review_label"] in lt.LABELS)
check("entry: confidence is a known CONFIDENCE", entry["confidence"] in lt.CONFIDENCES)

with tempfile.TemporaryDirectory() as tmp:
    log_path = os.path.join(tmp, "session_tuning_log.jsonl")
    lt.append_tuning_log(entry, path=log_path)
    with open(log_path, encoding="utf-8") as f:
        saved = json.loads(f.readline())
    check("saved entry: label persisted", saved["review_label"] == "human_better")
    check("saved entry: note persisted (unicode safe)", saved["note"] == "次アタッカー不在を回避できた")

# === default params.json on disk is never touched by any of this ===
print("\n=== params.json untouched ===")
params_path = os.path.join(os.path.dirname(__file__), "agents", "raging_bolt", "params.json")
if os.path.exists(params_path):
    with open(params_path, encoding="utf-8") as f:
        before_bytes = f.read()
    setup()
    lt.set_runtime_override(REAL_PARAMS, "eval_no_backup_risk", -9999)
    lt.build_tuning_preview(_fake_compute, REAL_PARAMS)
    with open(params_path, encoding="utf-8") as f:
        after_bytes = f.read()
    check("params.json bytes unchanged on disk", before_bytes == after_bytes)
    lt.reset_runtime_overrides()
else:
    check("params.json path exists for this check", False)

print("\n%d/%d passed" % (_t - _f, _t))
if _f:
    sys.exit(1)
