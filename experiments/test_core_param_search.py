"""
Tests for scripts/run_core_param_search.py.

Run: python experiments/test_core_param_search.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from run_core_param_search import (
    _load_searchable, _load_deny, generate_candidates, _CORE_PARAMS,
    format_csv, format_markdown,
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
print("\n--- load searchable params ---")

params = _load_searchable()
check("Loaded 5 core params", len(params) == 5)
for name in _CORE_PARAMS:
    check(f"  {name} present", name in params)

# ===================================================================
print("\n--- deny params exclusion ---")

deny = _load_deny()
check("Deny list loaded", len(deny) > 0)
for name in _CORE_PARAMS:
    check(f"  {name} NOT in deny", name not in deny)

# Known deny params
check("empty_bench_loss_penalty in deny", "empty_bench_loss_penalty" in deny)
check("winning_attack_boost in deny", "winning_attack_boost" in deny)

# ===================================================================
print("\n--- generate candidates ---")

candidates = generate_candidates(params, n_random=2)
check("Candidates generated", len(candidates) > 0)

baseline = candidates[0]
check("First candidate is baseline", baseline["id"] == "baseline")
for name in _CORE_PARAMS:
    check(f"  baseline {name} matches current",
          baseline["params"][name] == params[name]["current"])

# Has low/high variants
ids = [c["id"] for c in candidates]
has_low = any("_low_" in i for i in ids)
has_high = any("_high_" in i for i in ids)
has_random = any("random_" in i for i in ids)
check("Has low variants", has_low)
check("Has high variants", has_high)
check("Has random variants", has_random)

# No deny params in any candidate
for c in candidates:
    for name in c["params"]:
        check(f"  {c['id']}: {name} is core param", name in _CORE_PARAMS)

# ===================================================================
print("\n--- format CSV ---")

csv = format_csv(candidates)
lines = csv.strip().split("\n")
check("CSV has header", "candidate_id" in lines[0])
check("CSV has data rows", len(lines) > 1)
check("CSV header has all params", all(p in lines[0] for p in _CORE_PARAMS))

# ===================================================================
print("\n--- format Markdown ---")

md = format_markdown(candidates)
check("Markdown has title", "Core Parameter Search" in md)
check("Markdown has table", "|" in md)

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
