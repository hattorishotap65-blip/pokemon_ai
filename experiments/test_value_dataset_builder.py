"""Tests for value_dataset_builder."""
import csv
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "web"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agents", "raging_bolt"))

PASS = "[PASS]"
FAIL = "[FAIL]"
_f = 0
_t = 0

def check(label, cond):
    global _f, _t
    _t += 1
    print("  %s  %s" % (PASS if cond else FAIL, label))
    if not cond: _f += 1

print("=== build_from_traces empty ===")
from experiments.web.value_dataset_builder import build_from_traces
tmp = tempfile.mkdtemp()
empty_dir = os.path.join(tmp, "empty")
os.makedirs(empty_dir)
out = build_from_traces(empty_dir, os.path.join(tmp, "empty.csv"))
check("empty dir: creates file", os.path.exists(out))
with open(out, encoding="utf-8") as f:
    rows = list(csv.reader(f))
check("empty dir: only header", len(rows) == 1)

print("\n=== build_from_traces with data ===")
traces_dir = os.path.join(os.path.dirname(__file__), "web", "human_traces")
if os.path.isdir(traces_dir) and any(f.endswith(".jsonl") for f in os.listdir(traces_dir)):
    out2 = build_from_traces(traces_dir, os.path.join(tmp, "traces.csv"))
    check("traces: creates file", os.path.exists(out2))
    with open(out2, encoding="utf-8") as f:
        rows2 = list(csv.reader(f))
    check("traces: has data rows", len(rows2) > 1)
    check("traces: has result_win col", "result_win" in rows2[0])
else:
    print("  (skipped, no traces)")

import shutil
shutil.rmtree(tmp)

print("\n%d/%d passed" % (_t - _f, _t))
if _f: sys.exit(1)
