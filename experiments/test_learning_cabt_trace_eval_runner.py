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
    build_run_dir, build_advisor_env, run_trace_analysis,
    save_run_metadata, execute_trace_eval, run_command,
    _safe_env_for_metadata,
    _TRACE_SUMMARY, _TRACE_REPORT, _TUNING_RECS, _TUNING_REPORT, _METADATA,
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
rd = build_run_dir(tmp, "test")
check("creates dir", os.path.isdir(rd))
check("contains label", "test" in rd)

rd2 = build_run_dir("", "", run_dir=os.path.join(tmp, "explicit"))
check("explicit run_dir", os.path.isdir(rd2) and "explicit" in rd2)
shutil.rmtree(tmp)

print("\n=== build_advisor_env ===")

base = {"PATH": "/usr/bin", "HOME": "/home/user"}
env_off = build_advisor_env(base_env=base, use_advisor=False)
check("base_env not mutated", "POKEMON_AI_USE_LEARNED_WEIGHTS" not in base)
check("advisor off: key absent", "POKEMON_AI_USE_LEARNED_WEIGHTS" not in env_off)
check("PATH preserved", env_off.get("PATH") == "/usr/bin")

env_on = build_advisor_env(base_env=base, use_advisor=True, trace=True,
                           weights_path="/w.json", trace_path="/t.jsonl")
check("advisor on", env_on.get("POKEMON_AI_USE_LEARNED_WEIGHTS") == "1")
check("trace on", env_on.get("POKEMON_AI_TRACE_LEARNED_WEIGHTS") == "1")
check("weights path", env_on.get("POKEMON_AI_WEIGHTS_PATH") == "/w.json")
check("trace path", env_on.get("POKEMON_AI_TRACE_PATH") == "/t.jsonl")
check("base still clean", "POKEMON_AI_USE_LEARNED_WEIGHTS" not in base)

print("\n=== _safe_env_for_metadata ===")

safe = _safe_env_for_metadata({"POKEMON_AI_X": "1", "PATH": "/bin", "HOME": "/h"})
check("only POKEMON_AI_ keys", "PATH" not in safe and "POKEMON_AI_X" in safe)

print("\n=== run_command ===")

r_skip = run_command(["echo", "hello"], skip=True)
check("skip: returncode=0", r_skip["returncode"] == 0)
check("skip: skipped=True", r_skip["skipped"] is True)

print("\n=== save_run_metadata ===")

tmp2 = tempfile.mkdtemp()
mp = save_run_metadata(tmp2, agent="main.py", command=["echo"], trace_path="/t.jsonl")
check("metadata created", os.path.exists(mp))
with open(mp, encoding="utf-8") as f:
    meta = json.load(f)
check("has run_dir", "run_dir" in meta)
check("has command", meta.get("command") == ["echo"])
check("has trace_path", meta.get("trace_path") == "/t.jsonl")
shutil.rmtree(tmp2)

print("\n=== run_trace_analysis (empty) ===")

tmp3 = tempfile.mkdtemp()
r_empty = run_trace_analysis("/nonexistent.jsonl", tmp3)
check("empty: entries=0", r_empty.get("trace_entries") == 0)
check("empty: summary created", os.path.exists(os.path.join(tmp3, _TRACE_SUMMARY)))
check("empty: report created", os.path.exists(os.path.join(tmp3, _TRACE_REPORT)))
check("empty: recs created", os.path.exists(os.path.join(tmp3, _TUNING_RECS)))
check("empty: tuning report created", os.path.exists(os.path.join(tmp3, _TUNING_REPORT)))
shutil.rmtree(tmp3)

print("\n=== execute_trace_eval (skip-command) ===")

tmp4 = tempfile.mkdtemp()
dr = execute_trace_eval(
    agent="main.py", deck="deck.csv", n=5,
    use_advisor=False, run_dir=os.path.join(tmp4, "run1"),
    skip_command=True,
)
check("skip: run_dir exists", os.path.isdir(dr["run_dir"]))
check("skip: metadata exists", os.path.exists(dr["metadata"]))
check("skip: summary created", os.path.exists(os.path.join(dr["run_dir"], _TRACE_SUMMARY)))
check("skip: report created", os.path.exists(os.path.join(dr["run_dir"], _TRACE_REPORT)))
check("skip: recs created", os.path.exists(os.path.join(dr["run_dir"], _TUNING_RECS)))
check("skip: tuning report created", os.path.exists(os.path.join(dr["run_dir"], _TUNING_REPORT)))
check("skip: metadata has command", "command" in json.load(open(dr["metadata"], encoding="utf-8")))

with open(dr["metadata"], encoding="utf-8") as f:
    m = json.load(f)
check("meta: has trace_path", "trace_path" in m)
check("meta: has result_path", "result_path" in m)
check("meta: has advisor_env", "advisor_env" in m)
check("meta: advisor_env is clean", "PATH" not in m.get("advisor_env", {}))
shutil.rmtree(tmp4)

print("\n=== CLI --help ===")

cli_path = os.path.join(os.path.dirname(__file__), "learning", "run_cabt_trace_eval.py")
r_help = subprocess.run([sys.executable, cli_path, "--help"], capture_output=True, text=True)
check("CLI --help", r_help.returncode == 0)

print("\n=== CLI --skip-command ===")

tmp5 = tempfile.mkdtemp()
r_cli = subprocess.run([
    sys.executable, cli_path,
    "--run-dir", os.path.join(tmp5, "cli_run"),
    "--skip-command", "--label", "ci",
], capture_output=True, text=True)
check("CLI --skip-command succeeds", r_cli.returncode == 0)
check("CLI creates run_metadata", os.path.exists(os.path.join(tmp5, "cli_run", _METADATA)))
check("CLI creates trace_summary", os.path.exists(os.path.join(tmp5, "cli_run", _TRACE_SUMMARY)))
shutil.rmtree(tmp5)

print("\n=== CLI -- custom command ===")

tmp_cmd = tempfile.mkdtemp()
r_cmd = subprocess.run([
    sys.executable, cli_path,
    "--run-dir", os.path.join(tmp_cmd, "cmd_run"),
    "--skip-command",
    "--", "echo", "hello",
], capture_output=True, text=True)
check("CLI -- custom command succeeds", r_cmd.returncode == 0)
shutil.rmtree(tmp_cmd)

print("\n=== CLI --dry-run alias ===")

tmp6 = tempfile.mkdtemp()
r_dry = subprocess.run([
    sys.executable, cli_path,
    "--run-dir", os.path.join(tmp6, "dry"),
    "--dry-run",
], capture_output=True, text=True)
check("CLI --dry-run alias succeeds", r_dry.returncode == 0)
shutil.rmtree(tmp6)

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
