"""
Tests for experiments/learning/cabt_trace_eval_runner.py.

Run: python experiments/test_learning_cabt_trace_eval_runner.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.learning.cabt_trace_eval_runner import (
    build_run_dir, build_env, run_trace_analysis,
    save_run_metadata, execute_trace_eval,
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


print("=== build_run_dir ===")

tmp = tempfile.mkdtemp()
rd = build_run_dir(tmp, "test_label")
check("creates directory", os.path.isdir(rd))
check("contains label", "test_label" in rd)

rd2 = build_run_dir(tmp)
check("works without label", os.path.isdir(rd2))
shutil.rmtree(tmp)

print("\n=== build_env ===")

env_off = build_env(use_advisor=False, trace=False)
check("advisor off: no POKEMON_AI_USE_LEARNED_WEIGHTS", env_off.get("POKEMON_AI_USE_LEARNED_WEIGHTS") is None)
check("trace off: no POKEMON_AI_TRACE_LEARNED_WEIGHTS", env_off.get("POKEMON_AI_TRACE_LEARNED_WEIGHTS") is None)

env_on = build_env(use_advisor=True, trace=True, weights_path="/w.json", trace_path="/t.jsonl")
check("advisor on: POKEMON_AI_USE_LEARNED_WEIGHTS=1", env_on.get("POKEMON_AI_USE_LEARNED_WEIGHTS") == "1")
check("trace on: POKEMON_AI_TRACE_LEARNED_WEIGHTS=1", env_on.get("POKEMON_AI_TRACE_LEARNED_WEIGHTS") == "1")
check("weights path set", env_on.get("POKEMON_AI_WEIGHTS_PATH") == "/w.json")
check("trace path set", env_on.get("POKEMON_AI_TRACE_PATH") == "/t.jsonl")

print("\n=== save_run_metadata ===")

tmp2 = tempfile.mkdtemp()
meta_path = save_run_metadata(tmp2, agent="main.py", n=10, dry_run=True)
check("metadata file created", os.path.exists(meta_path))
with open(meta_path, encoding="utf-8") as f:
    meta = json.load(f)
check("metadata has run_dir", "run_dir" in meta)
check("metadata has ts", "ts" in meta)
check("metadata has agent", meta.get("agent") == "main.py")
shutil.rmtree(tmp2)

print("\n=== run_trace_analysis (empty trace) ===")

tmp3 = tempfile.mkdtemp()
empty_trace = os.path.join(tmp3, "empty.jsonl")
with open(empty_trace, "w") as f:
    pass
result = run_trace_analysis(empty_trace, tmp3)
check("empty trace: trace_entries=0", result.get("trace_entries") == 0)
check("empty trace: summary created", os.path.exists(result.get("trace_summary_path", "")))
shutil.rmtree(tmp3)

print("\n=== run_trace_analysis (sample trace) ===")

tmp4 = tempfile.mkdtemp()
sample_trace = os.path.join(tmp4, "sample.jsonl")
with open(sample_trace, "w", encoding="utf-8") as f:
    f.write(json.dumps({"used_advisor": True, "fallback_reason": None,
                        "advisor_top": "play_crispin", "advisor_top_index": 0,
                        "existing_top_index": 1, "advisor_overrode_existing": True,
                        "advisor_scores": [{"action_id": "play_crispin", "score": 55.0}],
                        "candidates": [{"id": "play_crispin", "type": "supporter"}],
                        "state_summary": {"active": "X"}}) + "\n")
result4 = run_trace_analysis(sample_trace, tmp4)
check("sample trace: trace_entries=1", result4.get("trace_entries") == 1)
check("sample trace: report created", os.path.exists(result4.get("trace_report_path", "")))
check("sample trace: recommendations created", os.path.exists(result4.get("recommendations_path", "")))
check("sample trace: tuning report created", os.path.exists(result4.get("tuning_report_path", "")))
shutil.rmtree(tmp4)

print("\n=== run_trace_analysis (missing trace) ===")

tmp5 = tempfile.mkdtemp()
result5 = run_trace_analysis("/nonexistent.jsonl", tmp5)
check("missing trace: no crash", "trace_entries" in result5)
check("missing trace: 0 entries", result5.get("trace_entries") == 0)
shutil.rmtree(tmp5)

print("\n=== execute_trace_eval (dry-run) ===")

tmp6 = tempfile.mkdtemp()
dr = execute_trace_eval(
    agent="main.py", deck="deck.csv", n=5,
    use_advisor=False, output_base=tmp6, label="drytest", dry_run=True,
)
check("dry-run: returns dict", isinstance(dr, dict))
check("dry-run: run_dir exists", os.path.isdir(dr.get("run_dir", "")))
check("dry-run: metadata exists", os.path.exists(dr.get("metadata", "")))
check("dry-run: self_play returncode", dr.get("self_play", {}).get("returncode") == 0)
shutil.rmtree(tmp6)

print("\n=== CLI --help ===")

cli_path = os.path.join(os.path.dirname(__file__), "..", "experiments", "learning", "run_cabt_trace_eval.py")
if not os.path.exists(cli_path):
    cli_path = os.path.join(os.path.dirname(__file__), "learning", "run_cabt_trace_eval.py")
r_help = subprocess.run([sys.executable, cli_path, "--help"], capture_output=True, text=True)
check("CLI --help succeeds", r_help.returncode == 0)

print("\n=== CLI --dry-run ===")

tmp7 = tempfile.mkdtemp()
r_dry = subprocess.run([
    sys.executable, cli_path,
    "--agent", "main.py", "--deck", "deck.csv",
    "--dry-run", "--label", "ci", "--output-base", tmp7,
], capture_output=True, text=True)
check("CLI --dry-run succeeds", r_dry.returncode == 0)
check("CLI --dry-run creates run dir", any(os.listdir(tmp7)))
shutil.rmtree(tmp7)

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
