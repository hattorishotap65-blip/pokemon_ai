"""Tests for the session-only runtime parameter override store in live_tuning.py."""
import copy
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


BASE_PARAMS = {
    "eval_no_backup_risk": -400,
    "score_supporter_crispin": 1030,
    "score_attack_bellowing_thunder": 840,
    "use_value_model": False,
}


def setup():
    lt.reset_runtime_overrides()


# === set/get/reset ===
print("=== set / get / reset ===")
setup()
params_snapshot = copy.deepcopy(BASE_PARAMS)
ok, err = lt.set_runtime_override(BASE_PARAMS, "eval_no_backup_risk", -500)
check("set: accepted", ok is True and err is None)
check("get: contains override", lt.get_runtime_overrides().get("eval_no_backup_risk") == -500)
check("params.json dict not mutated", BASE_PARAMS == params_snapshot)

lt.reset_runtime_overrides()
check("reset: overrides cleared", lt.get_runtime_overrides() == {})
check("params.json dict still not mutated after reset", BASE_PARAMS == params_snapshot)

# === effective_params layering ===
print("\n=== effective_params ===")
setup()
lt.set_runtime_override(BASE_PARAMS, "score_supporter_crispin", 1080)
eff = lt.effective_params(BASE_PARAMS)
check("effective_params: override wins", eff["score_supporter_crispin"] == 1080)
check("effective_params: untouched key preserved", eff["eval_no_backup_risk"] == -400)
check("effective_params: base dict untouched", BASE_PARAMS["score_supporter_crispin"] == 1030)

# === unknown param rejected ===
print("\n=== unknown param rejected ===")
setup()
ok, err = lt.set_runtime_override(BASE_PARAMS, "score_totally_made_up", 999)
check("unknown param: rejected", ok is False)
check("unknown param: error message present", bool(err))
check("unknown param: not staged", "score_totally_made_up" not in lt.get_runtime_overrides())

# === non-numeric value rejected ===
print("\n=== non-numeric value rejected ===")
setup()
for bad_value in ["-500", None, [1, 2], {"x": 1}, float("nan"), float("inf")]:
    ok, err = lt.set_runtime_override(BASE_PARAMS, "eval_no_backup_risk", bad_value)
    check("non-numeric rejected: %r" % (bad_value,), ok is False)
check("non-numeric: nothing staged", lt.get_runtime_overrides() == {})

# === bool rejected even though bool is an int subclass in Python ===
print("\n=== bool rejected ===")
setup()
ok, err = lt.set_runtime_override(BASE_PARAMS, "use_value_model", True)
check("bool value: rejected", ok is False)

# === invalid param name (injection-style keys) rejected ===
print("\n=== invalid param name rejected ===")
setup()
for bad_key in ["__import__", "os.system", "eval(1)", "", "1leading_digit", "a;b"]:
    ok, err = lt.set_runtime_override(BASE_PARAMS, bad_key, 1)
    check("invalid key rejected: %r" % (bad_key,), ok is False)

# === validate_param_update is a pure check (no side effects) ===
print("\n=== validate_param_update purity ===")
setup()
ok, err = lt.validate_param_update(BASE_PARAMS, "eval_no_backup_risk", -999)
check("validate: would accept", ok is True)
check("validate: did not stage anything", lt.get_runtime_overrides() == {})

# === append_tuning_log writes valid jsonl, never raises ===
print("\n=== append_tuning_log ===")
with tempfile.TemporaryDirectory() as tmp:
    log_path = os.path.join(tmp, "session_tuning_log.jsonl")
    entry = lt.build_tuning_log_entry(
        game_id="g1", turn=3, live_review={"category": "no_next_attacker", "risk_flags": ["no_next_attacker"],
                                            "human_action": "Crispin"},
        param="eval_no_backup_risk", old_value=-400, new_value=-500,
        preview={"before": {"recommended_action": "Bellowing Thunder", "top_candidates": []},
                 "after": {"recommended_action": "Crispin", "top_candidates": []}},
    )
    check("entry: ai_action_before", entry["ai_action_before"] == "Bellowing Thunder")
    check("entry: ai_action_after", entry["ai_action_after"] == "Crispin")
    check("entry: param/old/new", entry["param"] == "eval_no_backup_risk" and
          entry["old_value"] == -400 and entry["new_value"] == -500)
    check("entry: review fields default blank", entry["review_label"] == "" and entry["confidence"] == "")

    ok = lt.append_tuning_log(entry, path=log_path)
    check("append: returns True", ok is True)
    check("append: file created", os.path.exists(log_path))
    with open(log_path, encoding="utf-8") as f:
        lines = [json.loads(l) for l in f if l.strip()]
    check("append: 1 line written", len(lines) == 1)
    check("append: round-trips param", lines[0]["param"] == "eval_no_backup_risk")

    # second append + unwritable path don't raise
    ok2 = lt.append_tuning_log(entry, path=log_path)
    check("append twice: still ok, 2 lines", ok2 is True)
    with open(log_path, encoding="utf-8") as f:
        check("append: 2 lines after second write", sum(1 for l in f if l.strip()) == 2)

    bad_ok = lt.append_tuning_log(entry, path=os.path.join(tmp, "nope", "..", "*?<>", "x.jsonl"))
    check("append to bad path: no crash", isinstance(bad_ok, bool))

print("\n%d/%d passed" % (_t - _f, _t))
if _f:
    sys.exit(1)
