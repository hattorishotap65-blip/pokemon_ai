"""Dedicated, fast unit tests for experiments/_review_fix_bundle_fixture.py
itself (not the raging_bolt regression tests that consume it).

These tests never spawn a real head_to_head.py game -- subprocess.Popen is
mocked with a scripted fake process, so the fixture's polling/retry/
diagnostic logic can be verified deterministically and quickly, without
depending on the underlying engine's unseeded randomness. That randomness
is exactly the property that made the real fixture flaky in CI (PR#215,
Actions run 30862433859); it must not also make *these* tests flaky.
"""
from __future__ import annotations
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _review_fix_bundle_fixture as fixture  # noqa: E402


def _main_record_line():
    return json.dumps({"captured_hidden_samples": [{"x": 1}], "turn": 1}) + "\n"


class _FakeProcess:
    """Stand-in for a subprocess.Popen instance.

    poll_sequence: values returned by successive .poll() calls (the last
    value repeats once exhausted). A non-None value simulates the child
    having exited with `returncode`.

    bundle_path / write_on_exit: if set, `write_on_exit` is appended to
    bundle_path the first time .poll() reports a non-None value -- this
    simulates the child flushing its last record at the exact moment it
    exits, which is the race the fixed "always re-read once more after the
    process stops" behavior must survive.
    """

    def __init__(self, poll_sequence, returncode, bundle_path=None, write_on_exit=None):
        self._poll_sequence = list(poll_sequence)
        self._index = 0
        self._returncode_value = returncode
        self.returncode = None
        self._bundle_path = bundle_path
        self._write_on_exit = write_on_exit
        self._exit_write_done = False

    def poll(self):
        if self._index < len(self._poll_sequence):
            value = self._poll_sequence[self._index]
            self._index += 1
        else:
            value = self._poll_sequence[-1]
        if value is not None:
            self.returncode = self._returncode_value
            if self._write_on_exit and not self._exit_write_done and self._bundle_path:
                with open(self._bundle_path, "a", encoding="utf-8") as f:
                    f.write(self._write_on_exit)
                self._exit_write_done = True
        return value

    def wait(self, timeout=None):
        self.returncode = self._returncode_value
        return self._returncode_value

    def terminate(self):
        pass

    def kill(self):
        pass


def _popen_side_effect(scripted_attempts, call_log):
    """Builds a subprocess.Popen replacement driven by `scripted_attempts`,
    a list of dicts (one per successive Popen() call) with optional keys:
    returncode (default 0), poll_sequence (default [returncode]),
    bundle_write (text appended to the bundle when the fake process
    "exits"), stdout_write, stderr_write."""

    def _popen(args, cwd=None, env=None, stdout=None, stderr=None):
        index = len(call_log)
        call_log.append(args)
        spec = scripted_attempts[index]
        if spec.get("stdout_write"):
            stdout.write(spec["stdout_write"].encode("utf-8"))
            stdout.flush()
        if spec.get("stderr_write"):
            stderr.write(spec["stderr_write"].encode("utf-8"))
            stderr.flush()
        returncode = spec.get("returncode", 0)
        return _FakeProcess(
            poll_sequence=spec.get("poll_sequence", [returncode]),
            returncode=returncode,
            bundle_path=env["POKEMON_AI_REPLAY_BUNDLE_PATH"],
            write_on_exit=spec.get("bundle_write"),
        )

    return _popen


class CaptureBundleTests(unittest.TestCase):
    def setUp(self):
        # Make missing-file guard pass regardless of local checkout state.
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(fixture, "AGENT_PATH", __file__).start()
        mock.patch.object(fixture, "DECK_A", __file__).start()

    def _capture(self, scripted_attempts, **kwargs):
        call_log = []
        with mock.patch.object(
            fixture.subprocess, "Popen", side_effect=_popen_side_effect(scripted_attempts, call_log)
        ):
            result = fixture.capture_bundle(**kwargs)
        return result, call_log

    def test_success_on_first_attempt_does_not_retry(self):
        (tmpdir, bundle_path, main_records), calls = self._capture(
            [{"poll_sequence": [None, 0], "bundle_write": _main_record_line()}],
            min_main_records=1,
            poll_interval_s=0.01,
        )
        try:
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(main_records), 1)
            self.assertTrue(os.path.exists(bundle_path))
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_final_reread_recovers_record_written_exactly_at_process_exit(self):
        # poll() reports exit on the very first call -- the polling loop's
        # "if proc.poll() is not None: break" fires before the per-iteration
        # record count check ever runs. Only the mandatory post-loop re-read
        # can see the record written at that same instant.
        (tmpdir, bundle_path, main_records), calls = self._capture(
            [{"poll_sequence": [0], "bundle_write": _main_record_line()}],
            min_main_records=1,
        )
        try:
            self.assertEqual(len(calls), 1, "must not need a retry once the final re-read sees the record")
            self.assertEqual(len(main_records), 1)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_clean_empty_first_attempt_retries_and_succeeds_on_second(self):
        (tmpdir, bundle_path, main_records), calls = self._capture(
            [
                {"poll_sequence": [0]},  # clean exit, zero records
                {"poll_sequence": [0], "bundle_write": _main_record_line()},
            ],
            min_main_records=1,
            max_attempts=2,
        )
        try:
            self.assertEqual(len(calls), 2)
            self.assertEqual(len(main_records), 1)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_all_attempts_clean_but_empty_raises_after_exact_attempt_count(self):
        with mock.patch.object(fixture, "IS_CI", True):
            with self.assertRaises(RuntimeError) as caught:
                self._capture(
                    [{"poll_sequence": [0]}, {"poll_sequence": [0]}],
                    min_main_records=1,
                    max_attempts=2,
                )
        message = str(caught.exception)
        self.assertIn("2 attempt(s)", message)
        self.assertIn("no abnormal exit detected", message)
        self.assertIn("attempt 1/2: return code 0", message)
        self.assertIn("attempt 2/2: return code 0", message)

    def test_all_attempts_clean_but_empty_calls_popen_exactly_max_attempts_times(self):
        call_log = []
        with mock.patch.object(fixture, "IS_CI", True), mock.patch.object(
            fixture.subprocess,
            "Popen",
            side_effect=_popen_side_effect(
                [{"poll_sequence": [0]}, {"poll_sequence": [0]}], call_log
            ),
        ):
            with self.assertRaises(RuntimeError):
                fixture.capture_bundle(min_main_records=1, max_attempts=2)
        self.assertEqual(len(call_log), 2)

    def test_abnormal_exit_raises_immediately_without_retry(self):
        with mock.patch.object(fixture, "IS_CI", True):
            call_log = []
            with mock.patch.object(
                fixture.subprocess,
                "Popen",
                side_effect=_popen_side_effect(
                    [
                        {
                            "poll_sequence": [7],
                            "returncode": 7,
                            "stderr_write": "Traceback (most recent call last):\nRuntimeError: engine boom\n",
                        },
                        {"poll_sequence": [0], "bundle_write": _main_record_line()},
                    ],
                    call_log,
                ),
            ):
                with self.assertRaises(RuntimeError) as caught:
                    fixture.capture_bundle(min_main_records=1, max_attempts=2)
            self.assertEqual(len(call_log), 1, "an abnormal exit must never be retried")
            message = str(caught.exception)
            self.assertIn("return code 7", message)
            self.assertIn("engine boom", message)

    def test_abnormal_exit_outside_ci_skips_instead_of_raising(self):
        with mock.patch.object(fixture, "IS_CI", False):
            with self.assertRaises(unittest.SkipTest):
                self._capture(
                    [{"poll_sequence": [9], "returncode": 9, "stderr_write": "boom"}],
                    min_main_records=1,
                    max_attempts=2,
                )

    def test_timeout_without_records_is_treated_as_clean_and_retried(self):
        # Never exits (poll() always None) and never reaches min_main_records
        # before max_wait_s -- the loop's timeout branch fires, the process
        # is terminated (returncode 0, as if it shut down cleanly), and this
        # must be retried rather than misreported as a crash.
        (tmpdir, bundle_path, main_records), calls = self._capture(
            [
                {"poll_sequence": [None]},  # never exits on its own -> timeout path
                {"poll_sequence": [0], "bundle_write": _main_record_line()},
            ],
            min_main_records=1,
            max_wait_s=0.02,
            poll_interval_s=0.01,
            max_attempts=2,
        )
        try:
            self.assertEqual(len(calls), 2)
            self.assertEqual(len(main_records), 1)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class DiagnosticHelperTests(unittest.TestCase):
    def test_read_tail_missing_file_returns_empty_string(self):
        self.assertEqual(fixture._read_tail("/nonexistent/path/does-not-exist.log"), "")

    def test_read_tail_truncates_long_content(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".log") as f:
            f.write("x" * 10_000)
            path = f.name
        try:
            tail = fixture._read_tail(path, limit=100)
            self.assertLessEqual(len(tail), 100 + len("...[truncated]...\n"))
            self.assertTrue(tail.endswith("x" * 100))
        finally:
            os.remove(path)

    def test_count_main_records_missing_bundle_is_zero(self):
        count, records = fixture._count_main_records("/nonexistent/bundle.jsonl")
        self.assertEqual(count, 0)
        self.assertEqual(records, [])

    def test_count_main_records_ignores_non_main_records(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".jsonl") as f:
            f.write(json.dumps({"turn": 1}) + "\n")
            f.write(_main_record_line())
            f.write("\n")  # blank line must be tolerated
            path = f.name
        try:
            count, records = fixture._count_main_records(path)
            self.assertEqual(count, 1)
            self.assertEqual(len(records), 1)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
