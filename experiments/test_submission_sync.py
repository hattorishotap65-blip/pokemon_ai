"""Unit tests for tools/submission_sync.py (Step 8A read-only check-only v1).

All writes in this test module happen only under tempfile.TemporaryDirectory().
No test opens any real-repository submission file for writing.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = Path(os.path.abspath(os.path.join(EXPERIMENTS_DIR, "..")))
TOOLS_DIR = os.path.join(str(REPO_ROOT), "tools")
sys.path.insert(0, TOOLS_DIR)

import submission_sync as sync  # noqa: E402

# The 6 real files this test suite must never write to.
REAL_TARGETS = [
    REPO_ROOT / "main.py",
    REPO_ROOT / "deck.csv",
    REPO_ROOT / "params.json",
    REPO_ROOT / "experiments" / "agents" / "raging_bolt" / "main.py",
    REPO_ROOT / "experiments" / "agents" / "raging_bolt" / "params.json",
    REPO_ROOT / "experiments" / "decks" / "raging_bolt_ogerpon.csv",
]

VALID_DECK_LINES = (
    ["63"] * 4 + ["96"] * 4 + ["1182"] + ["1227"] * 4 + ["1198"] * 4
    + ["1121"] * 4 + ["1122"] * 4 + ["1124"] * 4 + ["1127"] * 3 + ["1094"] * 4
    + ["1118"] * 3 + ["1080"] + ["1"] * 12 + ["4"] * 4 + ["6"] * 4
)
assert len(VALID_DECK_LINES) == 60


def _valid_deck_text(newline: str = "\n") -> str:
    return newline.join(VALID_DECK_LINES) + newline


def _valid_main_py_text() -> str:
    return "def agent(obs_dict):\n    return []\n"


def _valid_params_json_text() -> str:
    return '{"a": 1}\n'


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _make_pair_repo(tmp: Path, logical_name: str, dev_text: str, root_text: str) -> None:
    """Write a valid-structure pair for exactly one logical name into tmp."""
    dev_rel, root_rel = sync.FIXED_MAPPING[logical_name]
    _write(tmp / dev_rel, dev_text)
    _write(tmp / root_rel, root_text)


class ClassifyBytesTests(unittest.TestCase):
    def test_byte_identical(self):
        self.assertEqual(sync.classify_bytes(b"abc\n", b"abc\n"), sync.Classification.BYTE_IDENTICAL)

    def test_crlf_lf_only_difference_is_semantically_equivalent(self):
        dev = "a\r\nb\r\nc\r\n".encode("utf-8")
        root = "a\nb\nc\n".encode("utf-8")
        self.assertEqual(sync.classify_bytes(dev, root), sync.Classification.SEMANTICALLY_EQUIVALENT)

    def test_trailing_lf_presence_only_difference_is_semantically_equivalent(self):
        self.assertEqual(sync.classify_bytes(b"abc", b"abc\n"), sync.Classification.SEMANTICALLY_EQUIVALENT)

    def test_multiple_trailing_blank_lines_are_not_equivalent(self):
        # "abc\n\n" (one real trailing blank line) vs "abc\n" (no blank line)
        # must NOT be folded together -- only one trailing LF is ignored.
        self.assertEqual(sync.classify_bytes(b"abc\n\n", b"abc\n"), sync.Classification.DIFFERENT)
        self.assertEqual(sync.classify_bytes(b"abc\n\n", b"abc"), sync.Classification.DIFFERENT)

    def test_different(self):
        self.assertEqual(sync.classify_bytes(b"abc", b"xyz"), sync.Classification.DIFFERENT)


class StructuralValidationTests(unittest.TestCase):
    def test_main_py_valid(self):
        self.assertIsNone(sync.validate_structure("main.py", _valid_main_py_text().encode("utf-8")))

    def test_main_py_syntax_error(self):
        reason = sync.validate_structure("main.py", b"def agent(:\n    pass\n")
        self.assertIsNotNone(reason)
        self.assertIn("ast.parse failed", reason)

    def test_main_py_missing_agent_entry_point(self):
        reason = sync.validate_structure("main.py", b"def not_agent():\n    return []\n")
        self.assertIsNotNone(reason)
        self.assertIn("agent", reason)

    def test_params_json_valid(self):
        self.assertIsNone(sync.validate_structure("params.json", _valid_params_json_text().encode("utf-8")))

    def test_params_json_invalid_json(self):
        reason = sync.validate_structure("params.json", b"{not valid json")
        self.assertIsNotNone(reason)
        self.assertIn("json.loads failed", reason)

    def test_params_json_top_level_not_object(self):
        reason = sync.validate_structure("params.json", b"[1, 2, 3]")
        self.assertIsNotNone(reason)
        self.assertIn("not an object", reason)

    def test_deck_csv_valid(self):
        self.assertIsNone(sync.validate_structure("deck.csv", _valid_deck_text().encode("utf-8")))

    def test_deck_csv_fewer_than_60_lines(self):
        text = "\n".join(VALID_DECK_LINES[:59]) + "\n"
        reason = sync.validate_structure("deck.csv", text.encode("utf-8"))
        self.assertIsNotNone(reason)
        self.assertIn("60", reason)

    def test_deck_csv_multiple_columns(self):
        lines = list(VALID_DECK_LINES)
        lines[0] = "63,63"
        text = "\n".join(lines) + "\n"
        reason = sync.validate_structure("deck.csv", text.encode("utf-8"))
        self.assertIsNotNone(reason)
        self.assertIn("columns", reason)

    def test_deck_csv_non_integer_value(self):
        lines = list(VALID_DECK_LINES)
        lines[0] = "abc"
        text = "\n".join(lines) + "\n"
        reason = sync.validate_structure("deck.csv", text.encode("utf-8"))
        self.assertIsNotNone(reason)
        self.assertIn("positive decimal integer", reason)

    def test_deck_csv_zero_or_negative_value(self):
        lines = list(VALID_DECK_LINES)
        lines[0] = "0"
        text = "\n".join(lines) + "\n"
        reason = sync.validate_structure("deck.csv", text.encode("utf-8"))
        self.assertIsNotNone(reason)
        self.assertIn("positive decimal integer", reason)

    def test_invalid_utf8(self):
        reason = sync.validate_structure("params.json", b"\xff\xfe\x00\x01")
        self.assertIsNotNone(reason)
        self.assertIn("utf-8 decode failed", reason)

    def test_deck_csv_blank_line_is_rejected(self):
        lines = list(VALID_DECK_LINES)
        lines.insert(3, "")
        text = "\n".join(lines) + "\n"
        reason = sync.validate_structure("deck.csv", text.encode("utf-8"))
        self.assertIsNotNone(reason)
        self.assertIn("empty line", reason)

    def test_deck_csv_unclosed_quote_is_malformed(self):
        lines = list(VALID_DECK_LINES)
        lines[0] = '"63'  # opening quote never closed on this physical line
        text = "\n".join(lines) + "\n"
        reason = sync.validate_structure("deck.csv", text.encode("utf-8"))
        self.assertIsNotNone(reason)
        self.assertIn("row 1", reason)
        self.assertIn("csv parsing failed", reason)

    def test_deck_csv_quoted_field_spanning_multiple_physical_lines_is_malformed(self):
        # Regression case for the old whole-file csv.reader(text.splitlines())
        # approach: 61 physical lines, where an unterminated quote on
        # physical line 60 silently swallows physical line 61 into the same
        # logical field ("1" + "2" -> "12", still a valid positive int).
        # That collapses 61 physical lines into exactly 60 logical rows, all
        # individually valid -- so the old code's "exactly 60 rows" check
        # would have wrongly PASSED this file, hiding an extra physical
        # line. Per-physical-line strict parsing must reject it instead,
        # since physical line 60 ('"1') is parsed in isolation and has no
        # continuation line available to close its quote.
        lines = ["1"] * 59 + ['"1', '2"']
        self.assertEqual(len(lines), 61)
        text = "\n".join(lines) + "\n"
        reason = sync.validate_structure("deck.csv", text.encode("utf-8"))
        self.assertIsNotNone(reason)
        self.assertIn("row 60", reason)
        self.assertIn("csv parsing failed", reason)

    def test_deck_csv_positive_int_reason_does_not_echo_the_value(self):
        lines = list(VALID_DECK_LINES)
        secret_looking_value = "sk-SUPER-SECRET-TOKEN-1234567890"
        lines[0] = secret_looking_value
        text = "\n".join(lines) + "\n"
        reason = sync.validate_structure("deck.csv", text.encode("utf-8"))
        self.assertIsNotNone(reason)
        self.assertIn("row 1", reason)
        self.assertIn("positive decimal integer", reason)
        self.assertNotIn(secret_looking_value, reason)

    def test_deck_csv_oversized_field_reports_malformed_not_crash(self):
        # A field beyond csv.field_size_limit() makes Python's csv module
        # raise csv.Error; this must surface as a MALFORMED reason, not an
        # uncaught exception propagating out of the CLI.
        oversized = "9" * 200_000
        text = oversized + "\n" + "\n".join(VALID_DECK_LINES[1:]) + "\n"
        reason = sync.validate_structure("deck.csv", text.encode("utf-8"))
        self.assertIsNotNone(reason)
        self.assertIn("csv parsing failed", reason)


class ContainmentTests(unittest.TestCase):
    def test_containment_rejects_path_escaping_root(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            resolved, status = sync.resolve_and_check(tmp, "../outside.txt")
            self.assertEqual(status, "CONTAINMENT_ERROR")
            self.assertIsNone(resolved)

    def test_containment_accepts_normal_relative_path(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            resolved, status = sync.resolve_and_check(tmp, "main.py")
            self.assertEqual(status, "OK")
            self.assertIsNotNone(resolved)

    def test_symlink_escaping_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_str, tempfile.TemporaryDirectory() as outside_str:
            tmp = Path(tmp_str)
            outside = Path(outside_str)
            outside_target = outside / "agents"
            outside_target.mkdir()
            _write(outside_target / "raging_bolt" / "main.py", _valid_main_py_text())

            link_path = tmp / "experiments"
            try:
                os.symlink(str(outside), str(link_path), target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation not permitted in this environment")

            resolved, status = sync.resolve_and_check(tmp, "experiments/agents/raging_bolt/main.py")
            self.assertEqual(status, "CONTAINMENT_ERROR")
            self.assertIsNone(resolved)

    def test_symlink_redirecting_to_a_different_file_inside_repo_is_rejected(self):
        # A symlink at the expected rel_path position that points to a
        # *different* file that also happens to be inside the repo must
        # still be rejected: mere "is the real path under repo root" is not
        # enough, the real path must land at the exact expected position.
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _write(tmp / "other" / "main.py", _valid_main_py_text())

            link_path = tmp / "main.py"
            try:
                os.symlink(str(tmp / "other" / "main.py"), str(link_path))
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation not permitted in this environment")

            resolved, status = sync.resolve_and_check(tmp, "main.py")
            self.assertEqual(status, "CONTAINMENT_ERROR")
            self.assertIsNone(resolved)

    def test_containment_rejects_internal_redirect_via_mocked_realpath(self):
        """Deterministic, non-skipping counterpart to the symlink-based
        tests above: simulates os.path.realpath() resolving a candidate
        (main.py) to a *different* location that is still inside repo_root
        -- as a symlink/junction/reparse point would -- without requiring
        real symlink-creation privileges in the test environment."""
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            root_abs = os.path.abspath(str(tmp))
            root_real = os.path.realpath(root_abs)
            candidate_abs = os.path.abspath(os.path.join(root_abs, "main.py"))
            redirected_real = os.path.join(root_real, "other", "alt_main.py")

            original_realpath = os.path.realpath

            def fake_realpath(path, *args, **kwargs):
                if os.path.normcase(os.path.normpath(str(path))) == os.path.normcase(
                    os.path.normpath(candidate_abs)
                ):
                    return redirected_real
                return original_realpath(path, *args, **kwargs)

            with mock.patch("os.path.realpath", side_effect=fake_realpath):
                resolved, status = sync.resolve_and_check(tmp, "main.py")

            self.assertEqual(status, "CONTAINMENT_ERROR")
            self.assertIsNone(resolved)

    def test_containment_rejects_intermediate_directory_redirect_via_mocked_realpath(self):
        """Same mechanism as above, but simulating a redirect introduced by
        an intermediate directory in the fixed rel_path chain (e.g. the
        'experiments' segment of experiments/agents/raging_bolt/main.py)
        rather than the final path component itself."""
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            root_abs = os.path.abspath(str(tmp))
            root_real = os.path.realpath(root_abs)
            rel_path = "experiments/agents/raging_bolt/main.py"
            candidate_abs = os.path.abspath(os.path.join(root_abs, rel_path))
            redirected_real = os.path.join(root_real, "experiments2", "agents", "raging_bolt", "main.py")

            original_realpath = os.path.realpath

            def fake_realpath(path, *args, **kwargs):
                if os.path.normcase(os.path.normpath(str(path))) == os.path.normcase(
                    os.path.normpath(candidate_abs)
                ):
                    return redirected_real
                return original_realpath(path, *args, **kwargs)

            with mock.patch("os.path.realpath", side_effect=fake_realpath):
                resolved, status = sync.resolve_and_check(tmp, rel_path)

            self.assertEqual(status, "CONTAINMENT_ERROR")
            self.assertIsNone(resolved)

    def test_containment_accepts_exact_expected_real_position(self):
        # Control case for the mocked tests above: when realpath resolves
        # to exactly the expected position (no redirect), the candidate is
        # still accepted.
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _write(tmp / "main.py", _valid_main_py_text())
            resolved, status = sync.resolve_and_check(tmp, "main.py")
            self.assertEqual(status, "OK")
            self.assertIsNotNone(resolved)


class CheckPairTests(unittest.TestCase):
    def test_missing_file_is_missing_status(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _write(tmp / "deck.csv", _valid_deck_text())
            # dev side intentionally absent
            report = sync.check_pair(tmp, "deck.csv")
            self.assertEqual(report.dev_status, "MISSING")
            self.assertEqual(report.root_status, "OK")
            self.assertIsNone(report.classification)
            self.assertEqual(sync.file_exit_category(report, strict=False), sync.EXIT_MISSING)

    def test_directory_in_place_of_file_is_io_error_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            dev_rel, root_rel = sync.FIXED_MAPPING["params.json"]
            (tmp / dev_rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / dev_rel).mkdir()  # a directory where a file is expected
            _write(tmp / root_rel, _valid_params_json_text())
            report = sync.check_pair(tmp, "params.json")
            self.assertEqual(report.dev_status, "IO_ERROR")
            self.assertEqual(sync.file_exit_category(report, strict=False), sync.EXIT_CONTAINMENT)


class FileExitCategoryPriorityTests(unittest.TestCase):
    """Direct, exhaustive checks of the 8 > 4 > 3 > 1 > 0 aggregation
    priority using synthetic PairReport instances (no filesystem needed)."""

    def _report(self, **overrides) -> sync.PairReport:
        base = dict(
            logical_name="x",
            dev_rel_path="dev/x",
            root_rel_path="root/x",
            dev_status="OK",
            root_status="OK",
        )
        base.update(overrides)
        return sync.PairReport(**base)

    def test_containment_error_outranks_everything(self):
        report = self._report(
            dev_status="CONTAINMENT_ERROR",
            dev_malformed_reason="would-be malformed",
            classification=sync.Classification.DIFFERENT,
        )
        self.assertEqual(sync.file_exit_category(report, strict=True), sync.EXIT_CONTAINMENT)

    def test_io_error_outranks_missing_and_drift(self):
        report = self._report(root_status="IO_ERROR", classification=sync.Classification.DIFFERENT)
        self.assertEqual(sync.file_exit_category(report, strict=False), sync.EXIT_CONTAINMENT)

    def test_malformed_outranks_missing(self):
        report = self._report(dev_status="MISSING", root_malformed_reason="bad json")
        self.assertEqual(sync.file_exit_category(report, strict=False), sync.EXIT_MALFORMED)

    def test_malformed_outranks_drift(self):
        report = self._report(dev_malformed_reason="bad json", classification=sync.Classification.DIFFERENT)
        self.assertEqual(sync.file_exit_category(report, strict=False), sync.EXIT_MALFORMED)

    def test_missing_outranks_drift(self):
        report = self._report(root_status="MISSING")
        self.assertEqual(sync.file_exit_category(report, strict=False), sync.EXIT_MISSING)

    def test_different_is_drift(self):
        report = self._report(classification=sync.Classification.DIFFERENT)
        self.assertEqual(sync.file_exit_category(report, strict=False), sync.EXIT_DRIFT)

    def test_byte_identical_is_success(self):
        report = self._report(classification=sync.Classification.BYTE_IDENTICAL)
        self.assertEqual(sync.file_exit_category(report, strict=False), sync.EXIT_SUCCESS)

    def test_aggregation_across_files_takes_the_max_by_priority(self):
        categories = [
            sync.file_exit_category(self._report(classification=sync.Classification.BYTE_IDENTICAL), False),
            sync.file_exit_category(self._report(root_status="MISSING"), False),
            sync.file_exit_category(self._report(dev_malformed_reason="bad"), False),
            sync.file_exit_category(self._report(root_status="CONTAINMENT_ERROR"), False),
        ]
        self.assertEqual(max(categories), sync.EXIT_CONTAINMENT)


class SelectedNamesTests(unittest.TestCase):
    def test_no_file_args_selects_all_three(self):
        self.assertEqual(sync.selected_names(None), list(sync.LOGICAL_NAMES))

    def test_single_file_arg(self):
        self.assertEqual(sync.selected_names(["main.py"]), ["main.py"])

    def test_multiple_file_args_preserve_order_and_dedupe(self):
        self.assertEqual(
            sync.selected_names(["params.json", "main.py", "params.json"]),
            ["params.json", "main.py"],
        )


class MainCliTests(unittest.TestCase):
    def test_byte_identical_pair_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _make_pair_repo(tmp, "params.json", _valid_params_json_text(), _valid_params_json_text())
            code = sync.main(["check", "--file", "params.json"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_SUCCESS)

    def test_semantically_equivalent_exits_zero_without_strict(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _make_pair_repo(tmp, "deck.csv", _valid_deck_text(newline="\r\n"), _valid_deck_text(newline="\n"))
            code = sync.main(["check", "--file", "deck.csv"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_SUCCESS)

    def test_semantically_equivalent_exits_one_with_strict(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _make_pair_repo(tmp, "deck.csv", _valid_deck_text(newline="\r\n"), _valid_deck_text(newline="\n"))
            code = sync.main(["check", "--file", "deck.csv", "--strict"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_DRIFT)

    def test_different_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            # dev keeps the baseline deck; root swaps two entries so content
            # actually differs while remaining structurally valid (60 positive ints).
            dev_text = "\n".join(VALID_DECK_LINES) + "\n"
            root_lines = list(VALID_DECK_LINES)
            root_lines[0] = "96"
            root_lines[4] = "63"
            root_text = "\n".join(root_lines) + "\n"
            _make_pair_repo(tmp, "deck.csv", dev_text, root_text)
            code = sync.main(["check", "--file", "deck.csv"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_DRIFT)

    def test_missing_file_exits_three(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _, root_rel = sync.FIXED_MAPPING["params.json"]
            _write(tmp / root_rel, _valid_params_json_text())
            code = sync.main(["check", "--file", "params.json"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_MISSING)

    def test_invalid_utf8_exits_four(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            dev_rel, root_rel = sync.FIXED_MAPPING["params.json"]
            _write_bytes(tmp / dev_rel, b"\xff\xfe\x00\x01")
            _write(tmp / root_rel, _valid_params_json_text())
            code = sync.main(["check", "--file", "params.json"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_MALFORMED)

    def test_main_py_syntax_error_exits_four(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            dev_rel, root_rel = sync.FIXED_MAPPING["main.py"]
            _write(tmp / dev_rel, "def agent(:\n    pass\n")
            _write(tmp / root_rel, _valid_main_py_text())
            code = sync.main(["check", "--file", "main.py"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_MALFORMED)

    def test_main_py_missing_agent_exits_four(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            dev_rel, root_rel = sync.FIXED_MAPPING["main.py"]
            _write(tmp / dev_rel, "def helper():\n    return []\n")
            _write(tmp / root_rel, _valid_main_py_text())
            code = sync.main(["check", "--file", "main.py"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_MALFORMED)

    def test_params_json_invalid_json_exits_four(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            dev_rel, root_rel = sync.FIXED_MAPPING["params.json"]
            _write(tmp / dev_rel, "{not valid json")
            _write(tmp / root_rel, _valid_params_json_text())
            code = sync.main(["check", "--file", "params.json"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_MALFORMED)

    def test_params_json_top_level_non_object_exits_four(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            dev_rel, root_rel = sync.FIXED_MAPPING["params.json"]
            _write(tmp / dev_rel, "[1, 2, 3]")
            _write(tmp / root_rel, _valid_params_json_text())
            code = sync.main(["check", "--file", "params.json"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_MALFORMED)

    def test_deck_csv_fewer_than_60_lines_exits_four(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            dev_rel, root_rel = sync.FIXED_MAPPING["deck.csv"]
            short_text = "\n".join(VALID_DECK_LINES[:59]) + "\n"
            _write(tmp / dev_rel, short_text)
            _write(tmp / root_rel, _valid_deck_text())
            code = sync.main(["check", "--file", "deck.csv"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_MALFORMED)

    def test_deck_csv_multiple_columns_exits_four(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            dev_rel, root_rel = sync.FIXED_MAPPING["deck.csv"]
            lines = list(VALID_DECK_LINES)
            lines[0] = "63,63"
            _write(tmp / dev_rel, "\n".join(lines) + "\n")
            _write(tmp / root_rel, _valid_deck_text())
            code = sync.main(["check", "--file", "deck.csv"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_MALFORMED)

    def test_deck_csv_unclosed_quote_exits_four(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            dev_rel, root_rel = sync.FIXED_MAPPING["deck.csv"]
            lines = list(VALID_DECK_LINES)
            lines[0] = '"63'
            _write(tmp / dev_rel, "\n".join(lines) + "\n")
            _write(tmp / root_rel, _valid_deck_text())
            code = sync.main(["check", "--file", "deck.csv"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_MALFORMED)

    def test_deck_csv_quoted_multiline_field_exits_four(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            dev_rel, root_rel = sync.FIXED_MAPPING["deck.csv"]
            lines = ["1"] * 59 + ['"1', '2"']
            _write(tmp / dev_rel, "\n".join(lines) + "\n")
            _write(tmp / root_rel, _valid_deck_text())
            code = sync.main(["check", "--file", "deck.csv"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_MALFORMED)

    def test_deck_csv_non_integer_or_non_positive_exits_four(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            dev_rel, root_rel = sync.FIXED_MAPPING["deck.csv"]
            lines = list(VALID_DECK_LINES)
            lines[0] = "0"
            _write(tmp / dev_rel, "\n".join(lines) + "\n")
            _write(tmp / root_rel, _valid_deck_text())
            code = sync.main(["check", "--file", "deck.csv"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_MALFORMED)

    def test_single_file_selection_ignores_absent_unselected_files(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            # Only params.json pair exists; deck.csv/main.py are entirely absent.
            _make_pair_repo(tmp, "params.json", _valid_params_json_text(), _valid_params_json_text())
            code = sync.main(["check", "--file", "params.json"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_SUCCESS)

    def test_multiple_file_selection_checks_only_named_files(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _make_pair_repo(tmp, "params.json", _valid_params_json_text(), _valid_params_json_text())
            _make_pair_repo(tmp, "main.py", _valid_main_py_text(), _valid_main_py_text())
            # deck.csv absent entirely -- must not affect this run.
            code = sync.main(
                ["check", "--file", "params.json", "--file", "main.py"], repo_root=tmp
            )
            self.assertEqual(code, sync.EXIT_SUCCESS)

    def test_no_file_flag_checks_all_three(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _make_pair_repo(tmp, "params.json", _valid_params_json_text(), _valid_params_json_text())
            _make_pair_repo(tmp, "main.py", _valid_main_py_text(), _valid_main_py_text())
            _make_pair_repo(tmp, "deck.csv", _valid_deck_text(), _valid_deck_text())
            code = sync.main(["check"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_SUCCESS)

    def test_invalid_file_choice_exits_two_via_systemexit(self):
        with self.assertRaises(SystemExit) as cm:
            sync.main(["check", "--file", "not_a_real_file.txt"], repo_root=REPO_ROOT)
        self.assertEqual(cm.exception.code, 2)

    def test_invalid_subcommand_exits_two_via_systemexit(self):
        with self.assertRaises(SystemExit) as cm:
            sync.main(["not_a_subcommand"], repo_root=REPO_ROOT)
        self.assertEqual(cm.exception.code, 2)

    def test_priority_malformed_beats_missing_and_drift(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            # params.json: byte-identical (category 0)
            _make_pair_repo(tmp, "params.json", _valid_params_json_text(), _valid_params_json_text())
            # deck.csv: dev side missing (category 3)
            _, deck_root_rel = sync.FIXED_MAPPING["deck.csv"]
            _write(tmp / deck_root_rel, _valid_deck_text())
            # main.py: dev side has a syntax error (category 4), also DIFFERENT in bytes
            main_dev_rel, main_root_rel = sync.FIXED_MAPPING["main.py"]
            _write(tmp / main_dev_rel, "def agent(:\n    pass\n")
            _write(tmp / main_root_rel, _valid_main_py_text())

            code = sync.main(["check"], repo_root=tmp)
            self.assertEqual(code, sync.EXIT_MALFORMED)


class OutputContentTests(unittest.TestCase):
    """Captures stdout to confirm the required per-file fields, the
    normal-vs-strict WARN/DRIFT labeling, and the summary counters are
    actually printed (not just computed internally)."""

    def _run_captured(self, argv: list[str], repo_root: Path) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = sync.main(argv, repo_root=repo_root)
        return code, buf.getvalue()

    def test_required_fields_present_for_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _make_pair_repo(tmp, "params.json", _valid_params_json_text(), _valid_params_json_text())
            code, out = self._run_captured(["check", "--file", "params.json"], tmp)
            self.assertEqual(code, sync.EXIT_SUCCESS)
            self.assertIn("params.json: BYTE_IDENTICAL", out)
            self.assertIn("development: experiments/agents/raging_bolt/params.json", out)
            self.assertIn("submission: params.json", out)
            self.assertIn("validation: OK", out)
            self.assertIn("summary:", out)
            self.assertIn("checked: 1", out)
            self.assertIn("byte_identical: 1", out)
            self.assertIn("overall: SUCCESS", out)

    def test_semantically_equivalent_prints_warn_without_strict(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _make_pair_repo(
                tmp, "deck.csv", _valid_deck_text(newline="\r\n"), _valid_deck_text(newline="\n")
            )
            code, out = self._run_captured(["check", "--file", "deck.csv"], tmp)
            self.assertEqual(code, sync.EXIT_SUCCESS)
            self.assertIn("SEMANTICALLY_EQUIVALENT", out)
            self.assertIn("WARN", out)
            self.assertNotIn("DRIFT", out)

    def test_semantically_equivalent_prints_drift_under_strict(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _make_pair_repo(
                tmp, "deck.csv", _valid_deck_text(newline="\r\n"), _valid_deck_text(newline="\n")
            )
            code, out = self._run_captured(["check", "--file", "deck.csv", "--strict"], tmp)
            self.assertEqual(code, sync.EXIT_DRIFT)
            self.assertIn("SEMANTICALLY_EQUIVALENT", out)
            self.assertIn("DRIFT", out)

    def test_summary_counts_mixed_classifications(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _make_pair_repo(tmp, "params.json", _valid_params_json_text(), _valid_params_json_text())
            _make_pair_repo(tmp, "deck.csv", _valid_deck_text(), _valid_deck_text())
            main_dev_rel, main_root_rel = sync.FIXED_MAPPING["main.py"]
            _write(tmp / main_dev_rel, _valid_main_py_text() + "\n# extra\n")
            _write(tmp / main_root_rel, _valid_main_py_text())
            code, out = self._run_captured(["check"], tmp)
            self.assertEqual(code, sync.EXIT_DRIFT)
            self.assertIn("checked: 3", out)
            self.assertIn("byte_identical: 2", out)
            self.assertIn("different: 1", out)
            self.assertIn("overall: FAILURE (exit 1)", out)

    def test_missing_file_reason_is_printed(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _, root_rel = sync.FIXED_MAPPING["params.json"]
            _write(tmp / root_rel, _valid_params_json_text())
            code, out = self._run_captured(["check", "--file", "params.json"], tmp)
            self.assertEqual(code, sync.EXIT_MISSING)
            self.assertIn("development MISSING", out)

    def test_deck_csv_malformed_value_output_does_not_leak_the_value(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            dev_rel, root_rel = sync.FIXED_MAPPING["deck.csv"]
            secret_looking_value = "sk-SUPER-SECRET-TOKEN-1234567890"
            lines = list(VALID_DECK_LINES)
            lines[0] = secret_looking_value
            _write(tmp / dev_rel, "\n".join(lines) + "\n")
            _write(tmp / root_rel, _valid_deck_text())
            code, out = self._run_captured(["check", "--file", "deck.csv"], tmp)
            self.assertEqual(code, sync.EXIT_MALFORMED)
            self.assertIn("MALFORMED", out)
            self.assertIn("row 1", out)
            self.assertNotIn(secret_looking_value, out)

    def test_permission_style_error_output_does_not_leak_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            dev_rel, root_rel = sync.FIXED_MAPPING["params.json"]
            (tmp / dev_rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / dev_rel).mkdir()  # directory in place of a file -> IO_ERROR
            _write(tmp / root_rel, _valid_params_json_text())
            code, out = self._run_captured(["check", "--file", "params.json"], tmp)
            self.assertEqual(code, sync.EXIT_CONTAINMENT)
            self.assertNotIn(str(tmp), out)


class NoForbiddenBehaviorTests(unittest.TestCase):
    """Static checks that the implementation stays within the approved
    read-only, cg-free, build-free boundary."""

    def test_source_does_not_import_cg(self):
        source = Path(sync.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(source, r"\bimport\s+cg\b")
        self.assertNotRegex(source, r"\bfrom\s+cg\b")

    def test_source_does_not_reference_build_submission(self):
        source = Path(sync.__file__).read_text(encoding="utf-8")
        self.assertNotIn("build_submission", source)

    def test_source_never_creates_submission_tar_gz(self):
        source = Path(sync.__file__).read_text(encoding="utf-8")
        self.assertNotIn("submission.tar.gz", source)
        self.assertNotIn("tarfile", source)

    def test_source_has_no_write_apis(self):
        source = Path(sync.__file__).read_text(encoding="utf-8")
        forbidden_substrings = [
            "write_text(",
            "write_bytes(",
            "shutil.copy",
            "os.replace",
            ".rename(",
            ".unlink(",
            ".mkdir(",
            "tempfile.",
            '"w")',
            "'w')",
            '"wb")',
            "'wb')",
            "os.remove",
        ]
        for needle in forbidden_substrings:
            self.assertNotIn(needle, source, msg=f"forbidden write-capable API found: {needle!r}")

    def test_running_cli_in_tmp_repo_creates_no_submission_tar_gz(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            _make_pair_repo(tmp, "params.json", _valid_params_json_text(), _valid_params_json_text())
            sync.main(["check", "--file", "params.json"], repo_root=tmp)
            self.assertFalse((tmp / "submission.tar.gz").exists())


class RealRepositoryReadOnlyTests(unittest.TestCase):
    """Runs the real CLI against the real repository root (read-only) and
    confirms none of the 6 protected files changed as a result."""

    def test_real_repo_digests_unchanged_after_running_cli(self):
        before = {p: _sha256_of(p) for p in REAL_TARGETS if p.exists()}
        self.assertEqual(len(before), len(REAL_TARGETS), "expected all 6 real target files to exist")

        # Exercise the real CLI end-to-end against the real repo root, read-only.
        sync.main(["check"], repo_root=REPO_ROOT)
        sync.main(["check", "--strict"], repo_root=REPO_ROOT)
        for name in sync.LOGICAL_NAMES:
            sync.main(["check", "--file", name], repo_root=REPO_ROOT)

        after = {p: _sha256_of(p) for p in REAL_TARGETS}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
