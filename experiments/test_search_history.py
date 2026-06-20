"""
Unit tests for tools/search_history.py.

Run: python experiments/test_search_history.py
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.search_history import load, save, find_entries, is_explored, should_skip, add_entry

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

# --- load/save ---
print("\n--- load/save ---")

with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
    tmp = f.name
    json.dump({"schema_version": "1.0", "entries": [{"parameter": "x", "value": 1.0, "result": "accept"}]}, f)

data = load(tmp)
check("load existing file", len(data["entries"]) == 1)
check("schema_version present", data["schema_version"] == "1.0")

data2 = load("/nonexistent/path.json")
check("load missing file returns empty", data2["entries"] == [])

# --- find_entries ---
print("\n--- find_entries ---")

sample = {"entries": [
    {"parameter": "a", "value": 1.0, "result": "accept"},
    {"parameter": "a", "value": 2.0, "result": "reject"},
    {"parameter": "b", "value": 1.0, "result": "hold"},
]}

check("find by parameter only", len(find_entries(sample, "a")) == 2)
check("find by parameter+value", len(find_entries(sample, "a", 1.0)) == 1)
check("find nonexistent parameter", len(find_entries(sample, "c")) == 0)
check("find nonexistent value", len(find_entries(sample, "a", 9.0)) == 0)

# --- is_explored ---
print("\n--- is_explored ---")

check("explored=True", is_explored(sample, "a", 1.0))
check("explored=False", not is_explored(sample, "a", 9.0))

# --- should_skip ---
print("\n--- should_skip ---")

skip, reason = should_skip(sample, "a", 1.0)
check("accepted -> skip", skip)
check("accepted reason", "accepted" in reason)

skip, reason = should_skip(sample, "a", 2.0)
check("rejected -> skip", skip)
check("rejected reason", "rejected" in reason)

skip, reason = should_skip(sample, "b", 1.0)
check("held -> no skip", not skip)
check("held reason", "held" in reason)

skip, reason = should_skip(sample, "c", 1.0)
check("not explored -> no skip", not skip)

# --- add_entry ---
print("\n--- add_entry ---")

test_data = {"schema_version": "1.0", "entries": []}
entry = add_entry(test_data, "test_param", 42.0, "accept", "200g",
                  anomalies_per_game=4.5, safety="all_0", reason="test")
check("entry added", len(test_data["entries"]) == 1)
check("parameter correct", entry["parameter"] == "test_param")
check("value correct", entry["value"] == 42.0)
check("result correct", entry["result"] == "accept")
check("stage correct", entry["stage"] == "200g")
check("anomalies correct", entry["anomalies_per_game"] == 4.5)
check("date set", "date" in entry and len(entry["date"]) == 10)

entry2 = add_entry(test_data, "p2", 1.0, "hold", "30g", source_report="r.json")
check("source_report included", entry2.get("source_report") == "r.json")
check("two entries now", len(test_data["entries"]) == 2)

# --- save + reload round-trip ---
print("\n--- round-trip ---")

save(test_data, tmp)
reloaded = load(tmp)
check("round-trip entries count", len(reloaded["entries"]) == 2)
check("round-trip value preserved", reloaded["entries"][0]["value"] == 42.0)

os.unlink(tmp)

# --- real search_history.json ---
print("\n--- real search_history.json ---")

real = load(os.path.join(os.path.dirname(__file__), "..", "reports", "search_history.json"))
check("real file loads", len(real["entries"]) > 0)
check("retreat_bonus=1400 accepted", is_explored(real, "retreat_to_better_attacker_bonus", 1400.0))
check("attack_suppress=-40 accepted", is_explored(real, "attack_suppress_penalty", -40.0))
check("attack_suppress=-20 rejected", is_explored(real, "attack_suppress_penalty", -20.0))

skip, _ = should_skip(real, "retreat_to_better_attacker_bonus", 1400.0)
check("retreat_bonus=1400 should skip", skip)

skip, _ = should_skip(real, "attack_suppress_penalty", -20.0)
check("attack_suppress=-20 should skip", skip)

skip, _ = should_skip(real, "advantage_weight", 0.35)
check("advantage_weight=0.35 held, no skip", not skip)

skip, _ = should_skip(real, "advantage_weight", 0.5)
check("advantage_weight=0.5 not explored, no skip", not skip)

# ---
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
