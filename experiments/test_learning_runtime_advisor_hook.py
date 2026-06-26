"""
Tests for experiments/learning/runtime_advisor_hook.py.

Run: python experiments/test_learning_runtime_advisor_hook.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.learning.runtime_advisor_hook import (
    learned_weight_advisor_enabled,
    maybe_rank_with_learned_weights,
    maybe_rank_with_reason,
    reset_cache,
)

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


def _set_env(key, val):
    if val is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = val


print("=== learned_weight_advisor_enabled ===")

_set_env("POKEMON_AI_USE_LEARNED_WEIGHTS", None)
check("unset -> disabled", not learned_weight_advisor_enabled())

_set_env("POKEMON_AI_USE_LEARNED_WEIGHTS", "0")
check("'0' -> disabled", not learned_weight_advisor_enabled())

_set_env("POKEMON_AI_USE_LEARNED_WEIGHTS", "1")
check("'1' -> enabled", learned_weight_advisor_enabled())

_set_env("POKEMON_AI_USE_LEARNED_WEIGHTS", "yes")
check("'yes' -> disabled (only '1' works)", not learned_weight_advisor_enabled())

print("\n=== maybe_rank_with_learned_weights ===")

_set_env("POKEMON_AI_USE_LEARNED_WEIGHTS", None)
reset_cache()
result = maybe_rank_with_learned_weights({}, [{"id": "a"}])
check("disabled -> None", result is None)

_set_env("POKEMON_AI_USE_LEARNED_WEIGHTS", "1")
_set_env("POKEMON_AI_WEIGHTS_PATH", "/nonexistent.json")
_set_env("POKEMON_AI_WEIGHTS_FALLBACK_PATH", None)
reset_cache()
result2 = maybe_rank_with_learned_weights({}, [{"id": "a"}])
check("missing weights file -> None", result2 is None)

_set_env("POKEMON_AI_USE_LEARNED_WEIGHTS", "1")
reset_cache()
result3 = maybe_rank_with_learned_weights({}, [])
check("empty candidates -> None", result3 is None)

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
    json.dump({"use_crispin_value": 55.0, "teal_dance_value": 50.0}, f)
    weights_path = f.name

_set_env("POKEMON_AI_USE_LEARNED_WEIGHTS", "1")
_set_env("POKEMON_AI_WEIGHTS_PATH", weights_path)
reset_cache()

candidates = [
    {"id": "play_crispin", "label": "アカマツを使う", "type": "supporter"},
    {"id": "use_teal_dance", "label": "みどりのまいを使う", "type": "ability"},
]
result4 = maybe_rank_with_learned_weights({}, candidates)
check("valid weights + candidates -> ranked list", result4 is not None and len(result4) == 2)
check("ranked has original_index", result4 is not None and "original_index" in result4[0])

os.unlink(weights_path)

print("\n=== all-zero score fallback ===")

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
    json.dump({"some_unrelated_weight": 99.0}, f)
    zero_path = f.name

_set_env("POKEMON_AI_USE_LEARNED_WEIGHTS", "1")
_set_env("POKEMON_AI_WEIGHTS_PATH", zero_path)
reset_cache()

zero_cands = [{"id": "mystery_action", "label": "unknown thing", "type": "unknown"}]
result_zero = maybe_rank_with_learned_weights({}, zero_cands)
check("all score 0 -> None (fallback)", result_zero is None)
os.unlink(zero_path)

print("\n=== meaningful labels produce scores ===")

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
    json.dump({"use_crispin_value": 55.0, "teal_dance_value": 50.0}, f)
    rich_path = f.name

_set_env("POKEMON_AI_USE_LEARNED_WEIGHTS", "1")
_set_env("POKEMON_AI_WEIGHTS_PATH", rich_path)
reset_cache()

rich_cands = [
    {"id": "play_crispin", "label": "アカマツを使う", "type": "supporter"},
    {"id": "end_turn", "label": "ターン終了", "type": "end"},
]
result_rich = maybe_rank_with_learned_weights({}, rich_cands)
check("meaningful labels -> ranked (not None)", result_rich is not None)
check("crispin scores higher than end", result_rich is not None and result_rich[0]["action_id"] == "play_crispin")
os.unlink(rich_path)

print("\n=== default weights when path unset ===")

_set_env("POKEMON_AI_USE_LEARNED_WEIGHTS", "1")
_set_env("POKEMON_AI_WEIGHTS_PATH", None)
_set_env("POKEMON_AI_WEIGHTS_FALLBACK_PATH", None)
reset_cache()

default_cands = [
    {"id": "play_crispin", "label": "アカマツを使う", "type": "supporter"},
    {"id": "end", "label": "ターン終了", "type": "end"},
]
result_default = maybe_rank_with_learned_weights({}, default_cands)
check("no WEIGHTS_PATH -> uses default params, returns ranked", result_default is not None and len(result_default) > 0)

print("\n=== fallback safety ===")

_set_env("POKEMON_AI_USE_LEARNED_WEIGHTS", "1")
_set_env("POKEMON_AI_WEIGHTS_PATH", "/nonexistent.json")
_set_env("POKEMON_AI_WEIGHTS_FALLBACK_PATH", None)
reset_cache()
result5 = maybe_rank_with_learned_weights({}, [{"id": "x"}])
check("advisor error -> None (no crash)", result5 is None)

print("\n=== maybe_rank_with_reason ===")

_set_env("POKEMON_AI_USE_LEARNED_WEIGHTS", None)
reset_cache()
r, reason = maybe_rank_with_reason({}, [{"id": "a"}])
check("disabled -> reason=advisor_disabled", reason == "advisor_disabled")

_set_env("POKEMON_AI_USE_LEARNED_WEIGHTS", "1")
reset_cache()
r2, reason2 = maybe_rank_with_reason({}, [])
check("empty candidates -> reason=no_candidates", reason2 == "no_candidates")

_set_env("POKEMON_AI_USE_LEARNED_WEIGHTS", "1")
_set_env("POKEMON_AI_WEIGHTS_PATH", "/nonexistent_nowhere.json")
_set_env("POKEMON_AI_WEIGHTS_FALLBACK_PATH", "/also_nonexistent.json")
reset_cache()
r3, reason3 = maybe_rank_with_reason({}, [{"id": "x"}])
check("no weights -> reason=weights_missing", reason3 == "weights_missing")

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
    json.dump({"unrelated_key": 99.0}, f)
    zero_w = f.name
_set_env("POKEMON_AI_WEIGHTS_PATH", zero_w)
reset_cache()
r4, reason4 = maybe_rank_with_reason({}, [{"id": "mystery", "label": "unknown", "type": "unknown"}])
check("all scores zero -> reason=all_scores_zero", reason4 == "all_scores_zero")
os.unlink(zero_w)

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
    json.dump({"use_crispin_value": 55.0}, f)
    good_w = f.name
_set_env("POKEMON_AI_WEIGHTS_PATH", good_w)
reset_cache()
r5, reason5 = maybe_rank_with_reason({}, [{"id": "play_crispin", "label": "アカマツ", "type": "supporter"}])
check("success -> reason=None", reason5 is None)
check("success -> ranked list", r5 is not None and len(r5) == 1)
os.unlink(good_w)

# Cleanup env
for key in ("POKEMON_AI_USE_LEARNED_WEIGHTS", "POKEMON_AI_WEIGHTS_PATH", "POKEMON_AI_WEIGHTS_FALLBACK_PATH"):
    _set_env(key, None)
reset_cache()

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
