"""Shared, non-test helper for the PR#202 review-fix regression tests
(experiments/test_raging_bolt_review_fixes.py and
experiments/test_raging_bolt_review_fixes_integration.py).

Deliberately named without a `test_` prefix so unittest/pytest never
collect it as a test module on its own.

Captures one small real Replay Bundle via a short mirror match
(raging_bolt vs itself, using only files tracked in git -- sandbox
opponents like top_lucario_1084 are gitignored/local-only) and stops the
subprocess as soon as enough MAIN/engine-search decisions have been
captured, instead of waiting for a full game to finish.

In CI (GITHUB_ACTIONS/CI env var set), failing to obtain real battle data
is a hard failure (raises RuntimeError), never a silent skip -- a broken
fixture in CI must be visible, not hidden as a passing/skipped run. Outside
CI, the same failure raises unittest.SkipTest, since a local checkout
missing engine access is a legitimate, already-visible environment
difference, not a silent gap in what CI verified.
"""
from __future__ import annotations
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AGENT_PATH = os.path.join(REPO_ROOT, "experiments", "agents", "raging_bolt", "main.py")
DECK_A = os.path.join(REPO_ROOT, "experiments", "decks", "raging_bolt_ogerpon.csv")
SHADOW_SCRIPT = os.path.join(REPO_ROOT, "experiments", "shadow_eval_compare.py")

sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "reference", "extracted"))

IS_CI = bool(os.environ.get("GITHUB_ACTIONS") or os.environ.get("CI"))


def _fail_or_skip(message):
    if IS_CI:
        raise RuntimeError(f"[CI] {message}")
    raise unittest.SkipTest(message)


def load_agent_module(exec_mode, name):
    """Load a fresh copy of main.py under a specific EXEC_MODE. Temporarily
    sets the env var for the duration of module exec (EXEC_MODE is read
    once at import time), then restores whatever was there before."""
    backup = os.environ.get("POKEMON_AI_EXEC_MODE")
    os.environ["POKEMON_AI_EXEC_MODE"] = exec_mode
    try:
        spec = importlib.util.spec_from_file_location(name, AGENT_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if backup is None:
            os.environ.pop("POKEMON_AI_EXEC_MODE", None)
        else:
            os.environ["POKEMON_AI_EXEC_MODE"] = backup
    return mod


def capture_bundle(min_main_records=1, max_wait_s=240.0, poll_interval_s=2.0):
    """Returns (tmpdir, bundle_path, main_records). Caller owns tmpdir
    cleanup (shutil.rmtree). Raises (CI) or skips (local) if main.py/its
    deck are missing, or if no MAIN/engine-search decision was captured."""
    if not (os.path.exists(AGENT_PATH) and os.path.exists(DECK_A)):
        _fail_or_skip("experiments/agents/raging_bolt/main.py or its deck is missing")

    tmpdir = tempfile.mkdtemp(prefix="pr202_review_fix_test_")
    bundle_path = os.path.join(tmpdir, "bundle.jsonl")
    env = dict(os.environ)
    env["POKEMON_AI_EXEC_MODE"] = "BENCHMARK"
    env["POKEMON_AI_REPLAY_BUNDLE_PATH"] = bundle_path

    def _count_main_records():
        if not os.path.exists(bundle_path):
            return 0, []
        with open(bundle_path, encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        main_records = [r for r in records if r.get("captured_hidden_samples")]
        return len(main_records), main_records

    proc = subprocess.Popen(
        [sys.executable, os.path.join(REPO_ROOT, "experiments", "head_to_head.py"),
         "--agent-a", AGENT_PATH, "--deck-a", DECK_A,
         "--agent-b", AGENT_PATH, "--deck-b", DECK_A, "--n", "1"],
        cwd=REPO_ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + max_wait_s
        main_records = []
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break  # game finished on its own before the threshold -- fine, use what's captured
            count, main_records = _count_main_records()
            if count >= min_main_records:
                break
            time.sleep(poll_interval_s)
        else:
            _, main_records = _count_main_records()
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

    if not main_records:
        shutil.rmtree(tmpdir, ignore_errors=True)
        _fail_or_skip("captured bundle had no MAIN/engine-search decisions to test against")

    return tmpdir, bundle_path, main_records
