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

Stability notes (see the failure observed in PR#215's CI run 30862433859):
the underlying game has no seed control, so a single attempt can
legitimately finish with zero MAIN/engine-search decisions by chance. To
avoid weakening what this fixture verifies, that specific outcome (child
process exited with return code 0, but produced no qualifying decisions)
gets a small, bounded number of independent retries -- never a lowered
min_main_records, never a silent skip in CI, and never treated the same as
a genuine subprocess crash. A non-zero/abnormal child return code is never
retried: it is raised/skipped immediately, with the child's own stdout and
stderr attached, so the real cause is visible instead of only "0 records
captured". A max_wait_s timeout is not treated as a child crash even though
terminating the child can itself leave a non-zero/signal return code on
Linux -- a fixture-initiated termination is retried like any other clean,
zero-record attempt, and is called out explicitly in the diagnostic
message. The bundle file is also always re-read exactly once more after
the child has fully stopped (whether it exited on its own or was
terminated for a timeout), regardless of which loop-exit path was taken,
so a record flushed by the child between the last poll and process exit is
never silently lost to the fixed polling interval's timing -- this
includes a timeout attempt that happens to have reached min_main_records
by the time of that final read, which still counts as success.
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

_DIAGNOSTIC_TAIL_CHARS = 4000


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


def _count_main_records(bundle_path):
    """Read bundle_path (if it exists yet) and return (count, main_records)
    for the MAIN/engine-search decisions in it (records with a truthy
    "captured_hidden_samples")."""
    if not os.path.exists(bundle_path):
        return 0, []
    with open(bundle_path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    main_records = [r for r in records if r.get("captured_hidden_samples")]
    return len(main_records), main_records


def _read_tail(path, limit=_DIAGNOSTIC_TAIL_CHARS):
    """Best-effort read of a diagnostic log file, truncated to its last
    `limit` characters so a large/runaway subprocess output can't blow up
    an error message. Never raises -- a missing/unreadable log file is
    reported as empty, not as a secondary failure."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return ""
    if len(text) > limit:
        return "...[truncated]...\n" + text[-limit:]
    return text


def _run_capture_attempt(env, attempt_dir, min_main_records, max_wait_s, poll_interval_s):
    """Runs one head_to_head.py subprocess attempt to completion (or until
    terminated for exceeding max_wait_s). Returns a dict with:
    main_records, returncode, timed_out, stdout_text, stderr_text,
    bundle_path.

    The child's stdout/stderr are captured to files (never discarded) so
    an abnormal exit is diagnosable from the raised/skipped message. The
    bundle file is always re-read exactly once more after the subprocess
    has fully stopped, regardless of which loop-exit branch fired -- this
    is what protects against losing a record the child flushed between the
    last poll and process exit, which the fixed poll_interval_s otherwise
    would not have re-checked.
    """
    bundle_path = os.path.join(attempt_dir, "bundle.jsonl")
    stdout_path = os.path.join(attempt_dir, "stdout.log")
    stderr_path = os.path.join(attempt_dir, "stderr.log")

    run_env = dict(env)
    run_env["POKEMON_AI_REPLAY_BUNDLE_PATH"] = bundle_path

    with open(stdout_path, "wb") as out_f, open(stderr_path, "wb") as err_f:
        proc = subprocess.Popen(
            [sys.executable, os.path.join(REPO_ROOT, "experiments", "head_to_head.py"),
             "--agent-a", AGENT_PATH, "--deck-a", DECK_A,
             "--agent-b", AGENT_PATH, "--deck-b", DECK_A, "--n", "1"],
            cwd=REPO_ROOT, env=run_env, stdout=out_f, stderr=err_f,
        )
        timed_out = False
        try:
            deadline = time.monotonic() + max_wait_s
            while True:
                if proc.poll() is not None:
                    break  # process finished (or crashed) on its own
                count, _ = _count_main_records(bundle_path)
                if count >= min_main_records:
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                time.sleep(poll_interval_s)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)

    # Final, unconditional re-read: the process is now guaranteed to have
    # fully stopped, so this observes everything it ever flushed to disk --
    # not just whatever the last mid-loop poll happened to see.
    _, main_records = _count_main_records(bundle_path)

    return {
        "main_records": main_records,
        "returncode": proc.returncode,
        "timed_out": timed_out,
        "stdout_text": _read_tail(stdout_path),
        "stderr_text": _read_tail(stderr_path),
        "bundle_path": bundle_path,
    }


def capture_bundle(min_main_records=1, max_wait_s=240.0, poll_interval_s=2.0, max_attempts=2):
    """Returns (tmpdir, bundle_path, main_records) for the first attempt
    that captures at least `min_main_records` MAIN/engine-search decisions.
    Caller owns tmpdir cleanup (shutil.rmtree). Raises (CI) or skips
    (local) if main.py/its deck are missing, or if no attempt captured a
    qualifying decision.

    A subprocess that exits abnormally *on its own* (non-zero or
    signal-terminated return code, with timed_out False) is never retried
    -- that is a real failure, raised or skipped immediately with the
    subprocess's own stdout/stderr tail attached. A subprocess that exits
    cleanly (return code 0), or that hits the max_wait_s timeout and is
    terminated by this function itself (timed_out True, even if that
    leaves a non-zero/signal return code), but happens to capture zero
    MAIN/engine-search decisions -- possible because the underlying game
    has no seed control -- gets up to `max_attempts` independent tries
    before this raises/skips, since that specific outcome is a property of
    an unseeded random game (or simply a slow attempt), not by itself
    evidence of a defect.
    """
    if not (os.path.exists(AGENT_PATH) and os.path.exists(DECK_A)):
        _fail_or_skip("experiments/agents/raging_bolt/main.py or its deck is missing")

    tmpdir = tempfile.mkdtemp(prefix="pr202_review_fix_test_")
    env = dict(os.environ)
    env["POKEMON_AI_EXEC_MODE"] = "BENCHMARK"

    try:
        attempt_summaries = []
        for attempt in range(1, max_attempts + 1):
            attempt_dir = os.path.join(tmpdir, f"attempt-{attempt}")
            os.makedirs(attempt_dir, exist_ok=True)
            result = _run_capture_attempt(env, attempt_dir, min_main_records, max_wait_s, poll_interval_s)

            if result["main_records"]:
                return tmpdir, result["bundle_path"], result["main_records"]

            # A non-zero/signal return code is only a genuine subprocess
            # crash when the child stopped on its own. When timed_out is
            # true, WE terminated the child for exceeding max_wait_s -- on
            # Linux that routinely leaves a negative (signal-based)
            # returncode (e.g. -15 for SIGTERM), which must not be
            # misclassified as the child crashing by itself.
            if result["returncode"] != 0 and not result["timed_out"]:
                _fail_or_skip(
                    "captured bundle had no MAIN/engine-search decisions to test against -- "
                    f"subprocess exited abnormally on attempt {attempt}/{max_attempts} "
                    f"(return code {result['returncode']}).\n"
                    f"stdout tail:\n{result['stdout_text']}\n"
                    f"stderr tail:\n{result['stderr_text']}"
                )

            if result["timed_out"]:
                attempt_summaries.append(
                    f"attempt {attempt}/{max_attempts}: hit max_wait_s timeout and was "
                    f"terminated by the fixture (return code {result['returncode']}), "
                    "0 MAIN/engine-search records"
                )
            else:
                attempt_summaries.append(
                    f"attempt {attempt}/{max_attempts}: return code 0, 0 MAIN/engine-search records"
                )

        _fail_or_skip(
            "captured bundle had no MAIN/engine-search decisions to test against after "
            f"{max_attempts} attempt(s); no abnormal exit detected on any attempt (a "
            "fixture-initiated timeout termination is not treated as an abnormal exit) -- "
            "consistent with an unseeded game trajectory that never reached a "
            "MAIN/engine-search decision within max_wait_s, not a subprocess crash. "
            + " | ".join(attempt_summaries)
        )
    except BaseException:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise
