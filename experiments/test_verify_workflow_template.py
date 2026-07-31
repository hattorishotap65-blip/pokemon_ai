"""Tests for template/multi-agent-workflow/tools/verify_workflow_template.py.

Read-only tests only: nothing here writes into the real repository or the
real template package. All fixture packages/targets are built under
tempfile.TemporaryDirectory(). Run with:

    python -B -m unittest discover -s experiments -p "test_verify_workflow_template.py" -v
"""

from __future__ import annotations

import builtins
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "template" / "multi-agent-workflow"
VERIFIER_PATH = PACKAGE_ROOT / "tools" / "verify_workflow_template.py"


def _load_verifier_module():
    spec = importlib.util.spec_from_file_location("verify_workflow_template", VERIFIER_PATH)
    module = importlib.util.module_from_spec(spec)
    # dataclasses needs the module registered in sys.modules before exec.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vwt = _load_verifier_module()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _hash_tree(root: Path) -> dict:
    """Return {relpath: sha256} for every regular file under root."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for fn in filenames:
            p = Path(dirpath) / fn
            rel = str(p.relative_to(root))
            out[rel] = _sha256(p.read_bytes())
    return out


def _run(argv):
    """Call main() in-process, capturing stdout+stderr. Returns (exit_code, combined_text)."""
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        code = vwt.main(argv)
    return code, out_buf.getvalue() + err_buf.getvalue()


def _run_source_integrity_on(package_root: Path):
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        code = vwt.run_source_integrity(package_root)
    return code, out_buf.getvalue() + err_buf.getvalue()


def _run_plan_on(package_root: Path, target_root: Path, set_pairs):
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        code = vwt.run_plan(package_root, str(target_root), set_pairs)
    return code, out_buf.getvalue() + err_buf.getvalue()


_WRITEISH_MODE_CHARS = set("wax+")


def _mode_is_writeish(mode) -> bool:
    if not isinstance(mode, str):
        return False
    return any(c in _WRITEISH_MODE_CHARS for c in mode)


@contextlib.contextmanager
def _forbid_write_operations():
    """Patch every plausible write/create/delete/rename API so that calling
    any of them raises AssertionError, while read-mode file access continues
    to work normally. Intended to be applied only around the verifier's own
    call, not around test fixture setup."""
    real_open = builtins.open
    real_path_open = Path.open
    real_os_open = os.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if _mode_is_writeish(mode):
            raise AssertionError(f"open() called with write-ish mode: {mode!r}")
        return real_open(file, mode, *args, **kwargs)

    def guarded_path_open(self, mode="r", *args, **kwargs):
        if _mode_is_writeish(mode):
            raise AssertionError(f"Path.open() called with write-ish mode: {mode!r}")
        return real_path_open(self, mode, *args, **kwargs)

    write_flags = (
        os.O_WRONLY | os.O_RDWR
        | getattr(os, "O_CREAT", 0) | getattr(os, "O_APPEND", 0) | getattr(os, "O_TRUNC", 0)
    )

    def guarded_os_open(path, flags, *args, **kwargs):
        if flags & write_flags:
            raise AssertionError(f"os.open() called with write-ish flags: {flags!r}")
        return real_os_open(path, flags, *args, **kwargs)

    with mock.patch.object(builtins, "open", guarded_open), \
         mock.patch.object(Path, "open", guarded_path_open), \
         mock.patch.object(os, "open", guarded_os_open), \
         mock.patch.object(Path, "write_bytes", side_effect=AssertionError("Path.write_bytes called")), \
         mock.patch.object(Path, "write_text", side_effect=AssertionError("Path.write_text called")), \
         mock.patch.object(os, "mkdir", side_effect=AssertionError("os.mkdir called")), \
         mock.patch.object(os, "makedirs", side_effect=AssertionError("os.makedirs called")), \
         mock.patch.object(os, "remove", side_effect=AssertionError("os.remove called")), \
         mock.patch.object(os, "unlink", side_effect=AssertionError("os.unlink called")), \
         mock.patch.object(os, "replace", side_effect=AssertionError("os.replace called")), \
         mock.patch.object(os, "rename", side_effect=AssertionError("os.rename called")), \
         mock.patch.object(shutil, "copy", side_effect=AssertionError("shutil.copy called")), \
         mock.patch.object(shutil, "copy2", side_effect=AssertionError("shutil.copy2 called")), \
         mock.patch.object(shutil, "copytree", side_effect=AssertionError("shutil.copytree called")), \
         mock.patch.object(tempfile, "NamedTemporaryFile",
                            side_effect=AssertionError("tempfile.NamedTemporaryFile called")), \
         mock.patch.object(tempfile, "TemporaryFile",
                            side_effect=AssertionError("tempfile.TemporaryFile called")):
        yield


BASE_DOC_CONTENT = b"Hello {{PROJECT_NAME}}.\n"


def _minimal_manifest_dict(extra_files=None, extra_placeholders=None, doc_sha256=None):
    files = [
        {
            "path": "doc.md",
            "classification": "WORKFLOW_DOC",
            "content_mode": "NEW",
            "sha256": doc_sha256 if doc_sha256 is not None else _sha256(BASE_DOC_CONTENT),
            "required": True,
            "notes": "test doc",
            "target_path": "doc.md",
            "adoption_mode": "COPY_IF_ABSENT",
        },
        {
            "path": "manifest.json",
            "classification": "PACKAGE_METADATA",
            "content_mode": "NEW",
            "sha256": None,
            "required": True,
            "notes": "self-referential hash intentionally omitted",
            "target_path": None,
            "adoption_mode": "PACKAGE_METADATA",
        },
    ]
    if extra_files:
        files.extend(extra_files)
    return {
        "template_version": "0.0.0-test",
        "generated_from": "unit test fixture",
        "verification_status": "UNVERIFIED_IMPLEMENTATION",
        "files": files,
        "exclusions": [],
        "placeholders": ["{{PROJECT_NAME}}"] + (extra_placeholders or []),
    }


def _build_minimal_package(tmp_path: Path, manifest_dict=None, manifest_bytes=None,
                            doc_content=BASE_DOC_CONTENT, write_doc=True):
    root = tmp_path / "pkg"
    root.mkdir(parents=True, exist_ok=True)
    if write_doc:
        _write(root / "doc.md", doc_content)
    if manifest_bytes is not None:
        _write(root / "manifest.json", manifest_bytes)
    else:
        if manifest_dict is None:
            manifest_dict = _minimal_manifest_dict()
        _write(root / "manifest.json", json.dumps(manifest_dict).encode("utf-8"))
    return root


class SourceIntegrityTests(unittest.TestCase):
    """Area A: source-integrity."""

    def test_ok_manifest_exit_0(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 0)
            self.assertIn("final_exit: 0", out)

    def test_hash_match_is_identical(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 0)
            self.assertIn("[IDENTICAL]", out)
            self.assertIn("package: doc.md", out)

    def test_hash_drift_exit_1(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            # Mutate the file after the manifest was written with the original hash.
            _write(root / "doc.md", b"mutated content\n")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 1)
            self.assertIn("[DIFFERENT]", out)
            self.assertIn("HASH_DRIFT", out)
            # A hash mismatch still completed a real comparison: it counts
            # toward hash_compared/hash_mismatched, not toward invalid/missing.
            self.assertIn("hash_compared: 1", out)
            self.assertIn("hash_mismatched: 1", out)
            self.assertIn("hash_matched: 0", out)

    def test_missing_package_file_exit_3(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            (root / "doc.md").unlink()
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 3)
            self.assertIn("[MISSING]", out)
            # A MISSING file never reached a real comparison.
            self.assertIn("hash_compared: 0", out)

    def test_malformed_json_exit_4(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td), manifest_bytes=b"{not json")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("MANIFEST_MALFORMED_JSON", out)

    def test_manifest_too_large_exit_4(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "pkg"
            root.mkdir()
            _write(root / "doc.md", BASE_DOC_CONTENT)
            huge = b'{"pad": "' + b"x" * (vwt.MAX_MANIFEST_BYTES + 1) + b'"}'
            _write(root / "manifest.json", huge)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("MANIFEST_TOO_LARGE", out)

    def test_too_many_files_exit_4(self):
        with tempfile.TemporaryDirectory() as td:
            extra = []
            for i in range(vwt.MAX_MANIFEST_FILES):
                extra.append({
                    "path": f"extra{i}.md", "classification": "WORKFLOW_DOC",
                    "content_mode": "NEW", "sha256": "0" * 64, "required": True,
                    "notes": "x", "target_path": f"extra{i}.md",
                    "adoption_mode": "COPY_IF_ABSENT",
                })
            manifest = _minimal_manifest_dict(extra_files=extra)
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("MANIFEST_TOO_MANY_FILES", out)

    def test_duplicate_path_exit_4(self):
        with tempfile.TemporaryDirectory() as td:
            dup = [{
                "path": "doc.md", "classification": "WORKFLOW_DOC", "content_mode": "NEW",
                "sha256": _sha256(BASE_DOC_CONTENT), "required": True, "notes": "dup",
                "target_path": "doc.md", "adoption_mode": "COPY_IF_ABSENT",
            }]
            manifest = _minimal_manifest_dict(extra_files=dup)
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("DUPLICATE_MANIFEST_PATH", out)

    def test_unsafe_package_path_exit_4(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["path"] = "../escape.md"
            root = _build_minimal_package(Path(td), manifest_dict=manifest, write_doc=False)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("UNSAFE_PACKAGE_PATH", out)

    def test_self_hash_not_null_exit_4(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            for e in manifest["files"]:
                if e["path"] == "manifest.json":
                    e["sha256"] = "0" * 64
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("MANIFEST_SELF_HASH_NOT_NULL", out)

    def test_self_entry_missing_exit_4(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"] = [e for e in manifest["files"] if e["path"] != "manifest.json"]
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("MANIFEST_SELF_ENTRY_MISSING", out)

    def test_invalid_sha256_format_exit_4(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["sha256"] = "not-a-hash"
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("INVALID_SHA256_FORMAT", out)

    def test_unknown_classification_exit_4(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["classification"] = "NOT_A_REAL_CLASS"
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("UNKNOWN_CLASSIFICATION", out)

    def test_unknown_adoption_mode_exit_4(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["adoption_mode"] = "AUTO_INSTALL"
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("UNKNOWN_ADOPTION_MODE", out)

    def test_adoption_mode_target_path_mismatch_metadata_with_target(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["adoption_mode"] = "PACKAGE_METADATA"
            # target_path stays non-null -> mismatch
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("ADOPTION_MODE_TARGET_PATH_MISMATCH", out)

    def test_adoption_mode_target_path_mismatch_copy_without_target(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["target_path"] = None
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("ADOPTION_MODE_TARGET_PATH_MISMATCH", out)

    def test_undeclared_placeholder_in_target_path_exit_4(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["target_path"] = "{{UNDECLARED_NAME}}/doc.md"
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("UNDECLARED_PLACEHOLDER_IN_TARGET_PATH", out)

    def test_too_many_placeholders_exit_4(self):
        with tempfile.TemporaryDirectory() as td:
            extra_ph = [f"{{{{NAME{i}}}}}" for i in range(vwt.MAX_PLACEHOLDERS)]
            manifest = _minimal_manifest_dict(extra_placeholders=extra_ph)
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("MANIFEST_TOO_MANY_PLACEHOLDERS", out)


class CliTests(unittest.TestCase):
    """Area B: CLI."""

    def test_help_exit_0(self):
        code, _ = _run(["--help"])
        self.assertEqual(code, 0)

    def test_unknown_subcommand_exit_2(self):
        code, _ = _run(["not-a-real-subcommand"])
        self.assertEqual(code, 2)

    def test_plan_missing_target_root_argument_exit_2(self):
        code, _ = _run(["plan"])
        self.assertEqual(code, 2)

    def test_plan_nonexistent_target_root_directory_exit_3(self):
        with tempfile.TemporaryDirectory() as td:
            nonexistent = Path(td) / "does-not-exist"
            code, out = _run_plan_on(PACKAGE_ROOT, nonexistent, [])
            self.assertEqual(code, 3)

    def test_malformed_set_missing_equals_exit_2(self):
        with tempfile.TemporaryDirectory() as td:
            code, out = _run_plan_on(PACKAGE_ROOT, Path(td), ["PROJECT_NAME_NO_EQUALS"])
            self.assertEqual(code, 2)
            self.assertIn("MALFORMED_SET_ARGUMENT", out)

    def test_unknown_set_key_exit_2(self):
        with tempfile.TemporaryDirectory() as td:
            code, out = _run_plan_on(PACKAGE_ROOT, Path(td), ["NOT_A_DECLARED_NAME=value"])
            self.assertEqual(code, 2)
            self.assertIn("UNKNOWN_SET_NAME", out)

    def test_duplicate_set_key_exit_2(self):
        with tempfile.TemporaryDirectory() as td:
            code, out = _run_plan_on(PACKAGE_ROOT, Path(td),
                                      ["PROJECT_NAME=a", "PROJECT_NAME=b"])
            self.assertEqual(code, 2)
            self.assertIn("DUPLICATE_SET_NAME", out)

    def test_empty_set_value_exit_2(self):
        with tempfile.TemporaryDirectory() as td:
            code, out = _run_plan_on(PACKAGE_ROOT, Path(td), ["PROJECT_NAME="])
            self.assertEqual(code, 2)
            self.assertIn("EMPTY_SET_VALUE", out)

    def test_set_value_with_open_braces_exit_2(self):
        with tempfile.TemporaryDirectory() as td:
            code, out = _run_plan_on(PACKAGE_ROOT, Path(td), ["PROJECT_NAME=a{{b"])
            self.assertEqual(code, 2)
            self.assertIn("UNSAFE_SET_VALUE", out)

    def test_set_value_with_close_braces_exit_2(self):
        with tempfile.TemporaryDirectory() as td:
            code, out = _run_plan_on(PACKAGE_ROOT, Path(td), ["PROJECT_NAME=a}}b"])
            self.assertEqual(code, 2)
            self.assertIn("UNSAFE_SET_VALUE", out)

    def test_usage_error_exit_code_constant_is_2(self):
        self.assertEqual(vwt.EXIT_USAGE, 2)

    def test_source_integrity_cwd_independent(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as td:
            os.chdir(td)
            try:
                code, out = _run(["source-integrity"])
            finally:
                os.chdir(original_cwd)
        self.assertEqual(code, 0)
        self.assertIn("final_exit: 0", out)


class StateClassificationTests(unittest.TestCase):
    """Area C: 5-state classification + skip/manual-review + summary."""

    def _fresh_target(self, td):
        target = Path(td) / "target"
        target.mkdir()
        return target

    def test_state_identical(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = self._fresh_target(td)
            _write(target / "doc.md", b"Hello example.\n")
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertIn("[IDENTICAL]", out)
            self.assertEqual(code, 0)

    def test_state_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = self._fresh_target(td)
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertIn("[MISSING]", out)
            self.assertEqual(code, 1)

    def test_state_different(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = self._fresh_target(td)
            _write(target / "doc.md", b"totally different\n")
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertIn("[DIFFERENT]", out)
            self.assertEqual(code, 1)

    def test_state_invalid_via_special_file(self):
        if os.name == "nt":
            self.skipTest("FIFO creation not supported on Windows")
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = self._fresh_target(td)
            try:
                os.mkfifo(str(target / "doc.md"))
            except (AttributeError, OSError):
                self.skipTest("mkfifo unavailable in this environment")
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertIn("[INVALID]", out)
            self.assertEqual(code, 4)

    def test_state_unresolved_placeholder(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = self._fresh_target(td)
            code, out = _run_plan_on(root, target, [])  # PROJECT_NAME not supplied
            self.assertIn("[UNRESOLVED_PLACEHOLDER]", out)
            self.assertEqual(code, 1)

    def test_manual_review_identical_still_forces_exit_1(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["adoption_mode"] = "MANUAL_REVIEW"
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            target = self._fresh_target(td)
            _write(target / "doc.md", b"Hello example.\n")
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertIn("[IDENTICAL]", out)
            self.assertIn("manual_review_required: 1", out)
            self.assertEqual(code, 1)

    def test_package_metadata_is_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = self._fresh_target(td)
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertIn("[SKIPPED]", out)
            self.assertIn("skipped_by_mode: 1", out)

    def test_reference_only_is_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["adoption_mode"] = "REFERENCE_ONLY"
            manifest["files"][0]["target_path"] = None
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            target = self._fresh_target(td)
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(out.count("skipped_by_mode: 2"), 1)  # doc + manifest itself

    def test_template_rename_state(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["adoption_mode"] = "TEMPLATE_RENAME"
            manifest["files"][0]["target_path"] = "renamed-{{PROJECT_NAME}}.md"
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            target = self._fresh_target(td)
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertIn("target: renamed-example.md", out)
            self.assertIn("[MISSING]", out)

    def test_summary_counts_are_accurate(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = self._fresh_target(td)
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertIn("compared: 1", out)
            self.assertIn("missing: 1", out)
            self.assertIn("skipped_by_mode: 1", out)

    def test_plan_package_required_file_missing_forces_exit_3(self):
        # A package file the manifest lists is missing from the package
        # itself (a broken/incomplete package) -- distinct from a normal
        # "not yet copied to target" MISSING, which is exit 1.
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td), write_doc=False)
            target = self._fresh_target(td)
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 3)
            self.assertIn("[MISSING]", out)
            self.assertIn("reason: PACKAGE_FILE_MISSING", out)

    def test_plan_target_missing_is_exit_1_not_exit_3(self):
        # Sanity check contrasting with the above: an ordinary target-side
        # MISSING (ordinary un-adopted file) must stay exit 1.
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = self._fresh_target(td)
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 1)
            self.assertIn("reason: TARGET_MISSING", out)


class PathSafetyTests(unittest.TestCase):
    """Area D: path safety (manifest-level lexical checks + runtime containment)."""

    def _package_with_target_path(self, td, target_path):
        manifest = _minimal_manifest_dict()
        manifest["files"][0]["target_path"] = target_path
        return _build_minimal_package(Path(td), manifest_dict=manifest)

    def test_parent_traversal_in_target_path_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._package_with_target_path(td, "../escape.md")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("UNSAFE_TARGET_PATH", out)

    def test_posix_absolute_target_path_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._package_with_target_path(td, "/etc/passwd")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("UNSAFE_TARGET_PATH", out)

    def test_windows_absolute_target_path_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._package_with_target_path(td, "C:\\Windows\\System32\\evil.md")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("UNSAFE_TARGET_PATH", out)

    def test_unc_target_path_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._package_with_target_path(td, "\\\\server\\share\\evil.md")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("UNSAFE_TARGET_PATH", out)

    def test_drive_relative_target_path_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._package_with_target_path(td, "C:evil.md")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("UNSAFE_TARGET_PATH", out)

    def test_max_path_depth_exceeded_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            deep = "/".join(["d"] * (vwt.MAX_PATH_DEPTH + 1)) + "/doc.md"
            root = self._package_with_target_path(td, deep)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("UNSAFE_TARGET_PATH", out)

    def test_paths_with_spaces_are_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["path"] = "docs/my doc.md"
            manifest["files"][0]["target_path"] = "docs/my doc.md"
            root = Path(td) / "pkg"
            root.mkdir()
            _write(root / "docs" / "my doc.md", BASE_DOC_CONTENT)
            _write(root / "manifest.json", json.dumps(manifest).encode("utf-8"))
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 0)

    def test_non_ascii_paths_are_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["path"] = "docs/日本語.md"
            manifest["files"][0]["target_path"] = "docs/日本語.md"
            root = Path(td) / "pkg"
            root.mkdir()
            _write(root / "docs" / "日本語.md", BASE_DOC_CONTENT)
            _write(root / "manifest.json", json.dumps(manifest).encode("utf-8"))
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 0)

    # --- containment: mock-based, deterministic, never skipped ---

    def test_target_root_symlink_rejected_mock(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "target"
            target.mkdir()
            with mock.patch("os.path.islink", return_value=True):
                code, out = _run_plan_on(PACKAGE_ROOT, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 8)

    def test_intermediate_directory_symlink_rejected_mock(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()

            real_islink = os.path.islink

            def fake_islink(path):
                if str(path).endswith("doc.md") is False and "target" in str(path):
                    return True
                return real_islink(path)

            with mock.patch("os.path.islink", side_effect=fake_islink):
                code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 8)

    def test_internal_redirect_rejected_mock(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()
            _write(target / "doc.md", b"Hello example.\n")

            elsewhere = Path(td) / "elsewhere"
            elsewhere.mkdir()

            real_realpath = os.path.realpath

            def fake_realpath(path):
                if str(path).endswith("doc.md"):
                    return str(elsewhere / "doc.md")
                return real_realpath(path)

            with mock.patch("os.path.realpath", side_effect=fake_realpath):
                code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 8)
            self.assertIn("CONTAINMENT_ERROR", out)

    def test_case_collision_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["path"] = "Doc.md"
            manifest["files"][0]["target_path"] = "Doc.md"
            root = Path(td) / "pkg"
            root.mkdir()
            _write(root / "Doc.md", BASE_DOC_CONTENT)
            _write(root / "manifest.json", json.dumps(manifest).encode("utf-8"))
            target = Path(td) / "target"
            target.mkdir()
            # actual on-disk casing differs from manifest's declared casing
            _write(target / "doc.md", b"Hello example.\n")
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            if os.name == "nt":
                self.assertEqual(code, 8)
                self.assertIn("CASE_COLLISION", out)
                self.assertIn("package: Doc.md", out)
                self.assertIn("mode: COPY_IF_ABSENT", out)
            else:
                # case-sensitive filesystem: "Doc.md" and "doc.md" are genuinely
                # different files, so the expected target is simply absent.
                self.assertEqual(code, 1)
                self.assertEqual(out.count("[MISSING]"), 1)
                self.assertIn("reason: TARGET_MISSING", out)

    # --- containment: real symlink attempts, explicit skip if unsupported ---

    def test_target_file_symlink_rejected_real(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()
            elsewhere = Path(td) / "elsewhere.md"
            _write(elsewhere, b"Hello example.\n")
            link_path = target / "doc.md"
            try:
                os.symlink(str(elsewhere), str(link_path))
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation not permitted in this environment")
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 8)
            self.assertIn("CONTAINMENT_ERROR", out)

    def test_target_root_symlink_rejected_real(self):
        with tempfile.TemporaryDirectory() as td:
            real_dir = Path(td) / "real_target"
            real_dir.mkdir()
            link_dir = Path(td) / "link_target"
            try:
                os.symlink(str(real_dir), str(link_dir), target_is_directory=True)
            except (OSError, NotImplementedError, TypeError):
                self.skipTest("symlink creation not permitted in this environment")
            code, out = _run_plan_on(PACKAGE_ROOT, link_dir, ["PROJECT_NAME=example"])
            self.assertEqual(code, 8)


class ResourceAndFormatTests(unittest.TestCase):
    """Area E: resource limits and byte-exact comparison semantics."""

    def test_package_file_too_large_is_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            big_content = b"x" * (vwt.MAX_FILE_BYTES + 1)
            manifest = _minimal_manifest_dict(doc_sha256=_sha256(big_content))
            root = _build_minimal_package(Path(td), manifest_dict=manifest,
                                            doc_content=big_content)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("FILE_TOO_LARGE", out)
            # Oversized files never reach the hash comparison step.
            self.assertIn("hash_compared: 0", out)

    def test_total_read_limit_exceeded_is_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            chunk = b"y" * (vwt.MAX_FILE_BYTES)
            n_files_needed = (vwt.MAX_TOTAL_READ_BYTES // vwt.MAX_FILE_BYTES) + 2
            extra = []
            root = Path(td) / "pkg"
            root.mkdir()
            for i in range(n_files_needed):
                fname = f"big{i}.md"
                _write(root / fname, chunk)
                extra.append({
                    "path": fname, "classification": "WORKFLOW_DOC", "content_mode": "NEW",
                    "sha256": _sha256(chunk), "required": True, "notes": "x",
                    "target_path": fname, "adoption_mode": "COPY_IF_ABSENT",
                })
            manifest = _minimal_manifest_dict(extra_files=extra)
            _write(root / "doc.md", BASE_DOC_CONTENT)
            _write(root / "manifest.json", json.dumps(manifest).encode("utf-8"))
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("TOTAL_READ_LIMIT_EXCEEDED", out)

    def test_package_file_not_utf8_is_invalid_in_plan(self):
        with tempfile.TemporaryDirectory() as td:
            bad_bytes = b"\xff\xfe\x00broken"
            manifest = _minimal_manifest_dict(doc_sha256=_sha256(bad_bytes))
            root = _build_minimal_package(Path(td), manifest_dict=manifest, doc_content=bad_bytes)
            target = Path(td) / "target"
            target.mkdir()
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertIn("[INVALID]", out)
            self.assertIn("PACKAGE_FILE_NOT_UTF8", out)
            self.assertEqual(code, 4)

    def test_crlf_vs_lf_is_different_not_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()
            _write(target / "doc.md", b"Hello example.\r\n")
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertIn("[DIFFERENT]", out)
            self.assertEqual(code, 1)

    def test_trailing_newline_difference_is_different_not_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()
            _write(target / "doc.md", b"Hello example.")  # no trailing newline
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertIn("[DIFFERENT]", out)

    def test_malformed_target_directory_reports_invalid_without_body(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()
            (target / "doc.md").mkdir()  # target path is a directory, not a file
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertIn("[INVALID]", out)
            self.assertIn("TARGET_IS_DIRECTORY", out)
            self.assertEqual(code, 4)


class NonDisclosureTests(unittest.TestCase):
    """Area F: non-disclosure of secrets, values, absolute paths, and file bodies."""

    def test_secret_like_content_not_in_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            secret_content = b"API_KEY=sk-super-secret-value-12345\n"
            manifest = _minimal_manifest_dict(doc_sha256=_sha256(secret_content))
            root = _build_minimal_package(Path(td), manifest_dict=manifest,
                                            doc_content=secret_content)
            target = Path(td) / "target"
            target.mkdir()
            _write(target / "doc.md", b"different\n")
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertNotIn("sk-super-secret-value-12345", out)
            self.assertNotIn("API_KEY", out)

    def test_set_value_not_in_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=super-secret-project-name"])
            self.assertNotIn("super-secret-project-name", out)

    def test_target_root_absolute_path_not_in_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            # Empty target -> doc.md is genuinely absent there; confirm the
            # expected state/exit is what we think it is, not just that a
            # string is absent from an otherwise-unchecked run.
            self.assertEqual(code, 1)
            self.assertIn("[MISSING]", out)
            self.assertIn("reason: TARGET_MISSING", out)
            self.assertNotIn(str(target), out)
            self.assertNotIn(str(td), out)

    def test_oserror_does_not_leak_absolute_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            missing_target = Path(td) / "does-not-exist-at-all"
            code, out = _run_plan_on(root, missing_target, ["PROJECT_NAME=example"])
            self.assertNotIn(str(missing_target), out)
            self.assertIn(vwt.TARGET_ROOT_DISPLAY, out)

    def test_file_body_not_in_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            distinctive = b"UNIQUE_BODY_MARKER_YWERT_98123\n"
            manifest = _minimal_manifest_dict(doc_sha256=_sha256(distinctive))
            root = _build_minimal_package(Path(td), manifest_dict=manifest,
                                            doc_content=distinctive)
            code, out = _run_source_integrity_on(root)
            self.assertNotIn("UNIQUE_BODY_MARKER_YWERT_98123", out)


class ReadOnlyTests(unittest.TestCase):
    """Area G: the tool never writes anything, anywhere."""

    def test_real_package_tree_hashes_unchanged_after_source_integrity(self):
        before = _hash_tree(PACKAGE_ROOT)
        code, _ = _run_source_integrity_on(PACKAGE_ROOT)
        after = _hash_tree(PACKAGE_ROOT)
        self.assertEqual(before, after)

    def test_real_package_tree_hashes_unchanged_after_plan(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "target"
            target.mkdir()
            before = _hash_tree(PACKAGE_ROOT)
            _run_plan_on(PACKAGE_ROOT, target, [
                "PROJECT_NAME=example", "DEFAULT_BRANCH=main",
                "MCP_SERVER_NAME=codex-reviewer", "CODEX_COMMAND=codex",
                "DESIGN_SKILL_NAME=multi-agent-design", "ADR_NUMBER=0001",
                "TEST_COMMANDS=python -m unittest", "PROTECTED_PATHS=src/,config/",
                "PROJECT_SPECIFIC_DOCS=docs/project.md",
            ])
            after = _hash_tree(PACKAGE_ROOT)
            self.assertEqual(before, after)

    def test_target_tree_hashes_unchanged_after_plan(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()
            _write(target / "doc.md", b"Hello example.\n")
            _write(target / "unrelated.txt", b"leave me alone\n")
            before = _hash_tree(target)
            _run_plan_on(root, target, ["PROJECT_NAME=example"])
            after = _hash_tree(target)
            self.assertEqual(before, after)

    def test_no_new_files_created_in_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()
            before = set(os.listdir(target))
            _run_plan_on(root, target, ["PROJECT_NAME=example"])
            after = set(os.listdir(target))
            self.assertEqual(before, after)

    def test_no_write_apis_invoked(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()
            _write(target / "doc.md", b"Hello example.\n")

            # Fixture is fully prepared above; the guard is applied only
            # around the verifier's own plan() call.
            with _forbid_write_operations():
                code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 0)
            self.assertIn("[IDENTICAL]", out)

    def test_no_write_apis_invoked_source_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            with _forbid_write_operations():
                code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 0)
            self.assertIn("final_exit: 0", out)

    def test_no_write_apis_invoked_on_real_package(self):
        with _forbid_write_operations():
            code, out = _run_source_integrity_on(PACKAGE_ROOT)
        self.assertEqual(code, 0)

    def test_verifier_source_does_not_import_subprocess(self):
        import ast
        source = VERIFIER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_names.add(node.module)
        self.assertNotIn("subprocess", imported_names)

    def test_verifier_module_has_no_subprocess_reference_loaded(self):
        self.assertFalse(hasattr(vwt, "subprocess"))

    def test_works_with_non_git_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"  # deliberately not a git repository
            target.mkdir()
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertIn("[MISSING]", out)

    def test_dirty_target_directory_not_modified(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()
            _write(target / "doc.md", b"unrelated pre-existing dirty content\n")
            _write(target / "another_dirty_file.txt", b"pre-existing\n")
            before = _hash_tree(target)
            _run_plan_on(root, target, ["PROJECT_NAME=example"])
            after = _hash_tree(target)
            self.assertEqual(before, after)


class UnlistedPackageFileTests(unittest.TestCase):
    """source-integrity's detection of package-root files that exist on
    disk but are not declared in manifest.json's files list."""

    def test_root_level_unlisted_file_is_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            _write(root / "stray_extra_file.md", b"not in the manifest\n")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("[INVALID]", out)
            self.assertIn("package: stray_extra_file.md", out)
            self.assertIn("reason: UNLISTED_PACKAGE_FILE", out)
            self.assertIn("mode: UNLISTED", out)
            self.assertIn("unlisted_package_files: 1", out)

    def test_deep_directory_unlisted_file_is_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            _write(root / "a" / "b" / "c" / "stray.md", b"deep and unlisted\n")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("package: a/b/c/stray.md", out)
            self.assertIn("reason: UNLISTED_PACKAGE_FILE", out)

    def test_unlisted_file_with_secret_like_content_is_not_disclosed(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            secret_body = b"API_KEY=sk-STRAY-FILE-SECRET-77123\n"
            _write(root / "leftover_credentials.env", secret_body)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertNotIn("sk-STRAY-FILE-SECRET-77123", out)
            self.assertNotIn("API_KEY", out)
            self.assertIn("package: leftover_credentials.env", out)
            self.assertIn("reason: UNLISTED_PACKAGE_FILE", out)

    def test_unlisted_pycache_file_is_not_implicitly_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            _write(root / "tools" / "__pycache__" / "something.cpython-312.pyc", b"\x00fakebytecode")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("reason: UNLISTED_PACKAGE_FILE", out)
            self.assertIn("__pycache__", out)

    def test_unlisted_symlink_redirect_is_blocking_exit_8_mock(self):
        # Deterministic, non-skip: mocks os.path.islink to make one specific
        # unlisted entry appear as a symlink/reparse point, and confirms the
        # full run_source_integrity pipeline aggregates this to exit 8.
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            _write(root / "sneaky_entry.md", b"placeholder content\n")

            real_islink = os.path.islink

            def fake_islink(path):
                if str(path).endswith("sneaky_entry.md"):
                    return True
                return real_islink(path)

            with mock.patch("os.path.islink", side_effect=fake_islink):
                code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 8)
            self.assertIn("CONTAINMENT_ERROR", out)
            self.assertIn("sneaky_entry.md", out)

    def test_no_unlisted_files_when_package_matches_manifest_exactly(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))  # exactly doc.md + manifest.json
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 0)
            self.assertIn("unlisted_package_files: 0", out)

    def test_real_package_has_no_unlisted_files(self):
        code, out = _run_source_integrity_on(PACKAGE_ROOT)
        self.assertIn("unlisted_package_files: 0", out)

    def test_scan_does_not_modify_package_tree(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            _write(root / "stray.md", b"unlisted\n")
            before = _hash_tree(root)
            _run_source_integrity_on(root)
            after = _hash_tree(root)
            self.assertEqual(before, after)

    def test_real_package_scan_does_not_modify_tree(self):
        before = _hash_tree(PACKAGE_ROOT)
        _run_source_integrity_on(PACKAGE_ROOT)
        after = _hash_tree(PACKAGE_ROOT)
        self.assertEqual(before, after)


class RealRepositorySmokeTests(unittest.TestCase):
    """A few checks against the real, shipped package (read-only)."""

    def test_manifest_file_count_is_24(self):
        with open(PACKAGE_ROOT / "manifest.json", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data["files"]), 25)

    def test_real_package_source_integrity_passes(self):
        code, out = _run_source_integrity_on(PACKAGE_ROOT)
        self.assertEqual(code, 0)
        self.assertIn("final_exit: 0", out)

    def test_release_inventory_regression_v0_1_0(self):
        """Pins the exact expected source-integrity summary for the current
        shipped package (v0.1.1, 25 manifest entries). This is a
        release-inventory regression test: if a future version adds,
        removes, or changes a manifest entry, these expected values MUST be
        updated deliberately in the same change -- a silent mismatch here
        means the package's own self-consistency picture has drifted from
        what this test suite assumes."""
        code, out = _run_source_integrity_on(PACKAGE_ROOT)
        self.assertEqual(code, 0)
        # manifest.json itself: SKIPPED, not counted as hash-compared.
        idx = out.index("package: manifest.json")
        block_start = out.rfind("[", 0, idx)
        self.assertTrue(out[block_start:idx].startswith("[SKIPPED]"))
        self.assertIn("reason: SELF_HASH_INTENTIONALLY_OMITTED", out)
        # Exact expected summary for v0.1.1's 25-entry manifest
        # (24 real files + manifest.json itself).
        for expected_line in (
            "compared: 24",
            "identical: 24",
            "missing: 0",
            "different: 0",
            "invalid: 0",
            "blocking_errors: 0",
            "unresolved_placeholder: 0",
            "skipped_by_mode: 0",
            "manual_review_required: 0",
            "hash_compared: 24",
            "hash_matched: 24",
            "hash_mismatched: 0",
            "self_hash_omitted: 1",
            "manifest_valid: 1",
            "unlisted_package_files: 0",
            "final_exit: 0",
        ):
            self.assertIn(expected_line, out, f"expected summary line missing: {expected_line!r}")

    def test_gitattributes_content_is_exactly_star_minus_text(self):
        self.assertEqual((PACKAGE_ROOT / ".gitattributes").read_bytes(), b"* -text\n")

    def test_gitattributes_manifest_entry_is_package_metadata(self):
        with open(PACKAGE_ROOT / "manifest.json", encoding="utf-8") as f:
            data = json.load(f)
        matches = [e for e in data["files"] if e["path"] == ".gitattributes"]
        self.assertEqual(len(matches), 1)
        entry = matches[0]
        self.assertEqual(entry["classification"], "PACKAGE_METADATA")
        self.assertEqual(entry["content_mode"], "NEW")
        self.assertEqual(entry["adoption_mode"], "PACKAGE_METADATA")
        self.assertIsNone(entry["target_path"])
        self.assertIs(entry["required"], True)
        self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(entry["sha256"], _sha256((PACKAGE_ROOT / ".gitattributes").read_bytes()))


class ManifestSelfEntryTests(unittest.TestCase):
    """Area G1: manifest.json's own self-hash-omitted entry, displayed and
    counted distinctly from files that actually underwent a SHA-256
    comparison (Major M2 fix)."""

    def test_self_entry_is_skipped_not_identical(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 0)
            # The [SKIPPED] block for manifest.json must be distinct from
            # any [IDENTICAL] block.
            idx = out.index("package: manifest.json")
            block_start = out.rfind("[", 0, idx)
            block = out[block_start:idx + 200]
            self.assertTrue(block.startswith("[SKIPPED]"), block[:40])

    def test_self_entry_reason_is_self_hash_intentionally_omitted(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            code, out = _run_source_integrity_on(root)
            self.assertIn("reason: SELF_HASH_INTENTIONALLY_OMITTED", out)

    def test_self_entry_not_counted_in_identical_or_hash_compared(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))  # 1 real file (doc.md) + self entry
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 0)
            self.assertIn("compared: 1", out)
            self.assertIn("identical: 1", out)
            self.assertIn("hash_compared: 1", out)
            self.assertIn("hash_matched: 1", out)
            self.assertIn("hash_mismatched: 0", out)

    def test_self_hash_omitted_count_is_1(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            code, out = _run_source_integrity_on(root)
            self.assertIn("self_hash_omitted: 1", out)

    def test_manifest_valid_is_1_on_happy_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            code, out = _run_source_integrity_on(root)
            self.assertIn("manifest_valid: 1", out)

    def test_manifest_valid_independence_case_a_missing_package_file(self):
        # Case A: the manifest ITSELF is perfectly valid; only a required
        # package file happens to be missing from disk. manifest_valid must
        # stay 1 -- it describes the manifest's own structure, not the
        # health of the files it lists.
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td), write_doc=False)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 3)
            self.assertIn("manifest_valid: 1", out)
            self.assertIn("missing: 1", out)

    def test_manifest_valid_independence_case_b_invalid_package_file(self):
        # Case B: the manifest itself is valid; a package file is INVALID
        # (oversized). manifest_valid must still be 1.
        with tempfile.TemporaryDirectory() as td:
            big_content = b"x" * (vwt.MAX_FILE_BYTES + 1)
            manifest = _minimal_manifest_dict(doc_sha256=_sha256(big_content))
            root = _build_minimal_package(Path(td), manifest_dict=manifest,
                                            doc_content=big_content)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("manifest_valid: 1", out)
            self.assertIn("invalid: 1", out)

    def test_manifest_valid_independence_case_c_manifest_itself_invalid(self):
        # Case C: the manifest's own structure is invalid. Per this
        # verifier's design, a structurally-invalid manifest aborts before
        # any summary (including manifest_valid) is ever printed -- there is
        # no unsafe partial summary. Confirm exit 4 and that no "summary:"
        # block (and therefore no manifest_valid line at all) is produced.
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td), manifest_bytes=b"{not valid json")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertNotIn("summary:", out)
            self.assertNotIn("manifest_valid", out)
            self.assertIn("MANIFEST_MALFORMED_JSON", out)

    def test_hash_compared_excludes_missing_and_invalid_entries(self):
        # A package with one hash-comparable file, one MISSING file, and one
        # INVALID (oversized) file: hash_compared must reflect only the one
        # entry that actually completed a SHA-256 comparison.
        with tempfile.TemporaryDirectory() as td:
            big_content = b"z" * (vwt.MAX_FILE_BYTES + 1)
            extra = [{
                "path": "missing.md", "classification": "WORKFLOW_DOC", "content_mode": "NEW",
                "sha256": "0" * 64, "required": True, "notes": "x",
                "target_path": "missing.md", "adoption_mode": "COPY_IF_ABSENT",
            }, {
                "path": "big.md", "classification": "WORKFLOW_DOC", "content_mode": "NEW",
                "sha256": _sha256(big_content), "required": True, "notes": "x",
                "target_path": "big.md", "adoption_mode": "COPY_IF_ABSENT",
            }]
            manifest = _minimal_manifest_dict(extra_files=extra)
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            _write(root / "big.md", big_content)
            # "missing.md" is deliberately not written.
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)  # INVALID (big.md) outranks MISSING
            self.assertIn("compared: 3", out)
            self.assertIn("hash_compared: 1", out)
            self.assertIn("hash_matched: 1", out)
            self.assertIn("hash_mismatched: 0", out)

    def test_happy_path_exit_0_with_all_new_summary_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 0)
            self.assertIn("hash_compared: 1", out)
            self.assertIn("hash_matched: 1", out)
            self.assertIn("hash_mismatched: 0", out)
            self.assertIn("self_hash_omitted: 1", out)
            self.assertIn("manifest_valid: 1", out)
            self.assertIn("final_exit: 0", out)

    def test_manifest_structurally_invalid_is_exit_4_not_masked_by_self_entry(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            for e in manifest["files"]:
                if e["path"] == "manifest.json":
                    e["notes"] = "wrong phrase entirely"
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("MANIFEST_SELF_NOTES_MISSING_PHRASE", out)

    def test_real_package_self_entry_display(self):
        code, out = _run_source_integrity_on(PACKAGE_ROOT)
        self.assertIn("reason: SELF_HASH_INTENTIONALLY_OMITTED", out)
        idx = out.index("package: manifest.json")
        block_start = out.rfind("[", 0, idx)
        self.assertTrue(out[block_start:idx].startswith("[SKIPPED]"))


class PlaceholderValueSafetyTests(unittest.TestCase):
    """Area G2: --set VALUE defenses (Major M3 fix) -- both the general
    control-character/separator/brace check applied to every value, and the
    additional path-element check applied to target_path-constituting
    placeholders (DESIGN_SKILL_NAME, ADR_NUMBER in the real package)."""

    # (value, should_be_rejected)
    GENERAL_CASES = [
        ("\x00", True, "NUL"),
        ("\r", True, "CR"),
        ("\n", True, "LF"),
        ("\r\n", True, "CRLF"),
        ("\t", True, "tab"),
        ("\x0b", True, "vertical tab"),
        ("\x0c", True, "form feed"),
        ("\x9b", True, "C1 control character"),
        ("\u2028", True, "U+2028 line separator"),
        ("\u2029", True, "U+2029 paragraph separator"),
        ("\x1b[31mred\x1b[0m", True, "ANSI escape sequence (contains ESC, a C0 control char)"),
        ("a{{b", True, "double open brace"),
        ("a}}b", True, "double close brace"),
        ("", True, "empty value"),
        ("plain-ascii-value", False, "normal ASCII single element"),
        ("日本語プロジェクト", False, "normal Japanese text"),
    ]

    def test_general_value_defenses(self):
        for value, should_reject, label in self.GENERAL_CASES:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as td:
                    code, out = _run_plan_on(PACKAGE_ROOT, Path(td), [f"PROJECT_NAME={value}"])
                    if should_reject:
                        self.assertEqual(code, 2, f"{label!r} should be rejected, out={out!r}")
                        # A bare "" or whitespace/newline-only value is a
                        # substring of virtually any text (including the
                        # print()-added newlines themselves), so the
                        # not-leaked check below is only meaningful for
                        # values with visible, distinctive content.
                        if value.strip("\r\n\t\x0b\x0c ") != "":
                            self.assertNotIn(value, out)
                    else:
                        self.assertNotEqual(code, 2, f"{label!r} should NOT be a usage error")

    # (value, should_be_rejected, label)
    PATH_PLACEHOLDER_CASES = [
        ("/", True, "POSIX separator alone"),
        ("\\", True, "backslash alone"),
        ("..", True, "parent traversal"),
        (".", True, "dot"),
        ("/etc/passwd", True, "POSIX absolute"),
        ("C:\\Windows\\System32", True, "Windows absolute"),
        ("\\\\server\\share", True, "UNC"),
        ("C:evil", True, "drive-relative"),
        ("\r", True, "CR"),
        ("\n", True, "LF"),
        ("\r\n", True, "CRLF"),
        ("\t", True, "tab"),
        ("\x0b", True, "vertical tab"),
        ("\x0c", True, "form feed"),
        ("\x9b", True, "C1 control character"),
        ("\u2028", True, "U+2028"),
        ("\u2029", True, "U+2029"),
        ("\x1b[31m", True, "ANSI escape sequence"),
        ("a{{b", True, "double open brace"),
        ("a}}b", True, "double close brace"),
        ("", True, "empty value"),
        ("multi-agent-design", False, "normal ASCII single element"),
        ("設計スキル", False, "normal Japanese single element"),
    ]

    def test_path_placeholder_value_defenses(self):
        for value, should_reject, label in self.PATH_PLACEHOLDER_CASES:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as td:
                    code, out = _run_plan_on(PACKAGE_ROOT, Path(td), [f"DESIGN_SKILL_NAME={value}"])
                    if should_reject:
                        self.assertEqual(code, 2, f"{label!r} should be rejected, out={out!r}")
                        # A bare "" or whitespace/newline-only value is a
                        # substring of virtually any text (including the
                        # print()-added newlines themselves), so the
                        # not-leaked check below is only meaningful for
                        # values with visible, distinctive content.
                        if value.strip("\r\n\t\x0b\x0c ") != "":
                            self.assertNotIn(value, out)
                    else:
                        self.assertNotEqual(code, 2, f"{label!r} should NOT be a usage error, out={out!r}")

    def test_rejected_value_never_reaches_stdout_or_stderr(self):
        distinctive = "INJECTION-MARKER-8231\ninjected: line"
        with tempfile.TemporaryDirectory() as td:
            code, out = _run_plan_on(PACKAGE_ROOT, Path(td), [f"PROJECT_NAME={distinctive}"])
            self.assertEqual(code, 2)
            self.assertNotIn("INJECTION-MARKER-8231", out)
            self.assertNotIn("injected: line", out)

    def test_report_line_injection_via_newline_is_rejected_not_silently_rendered(self):
        # An attempt to forge a fake status block via an embedded newline in
        # a path-placeholder value must be rejected outright (usage error),
        # never rendered into the report.
        forged = "0001\n[IDENTICAL]\npackage: fake.md\ntarget: fake.md\nmode: COPY_IF_ABSENT\nreason: BYTE_IDENTICAL"
        with tempfile.TemporaryDirectory() as td:
            code, out = _run_plan_on(PACKAGE_ROOT, Path(td), [f"ADR_NUMBER={forged}"])
            self.assertEqual(code, 2)
            self.assertNotIn("fake.md", out)
            self.assertNotIn("[IDENTICAL]\npackage: fake.md", out)


class CliNonDisclosureTests(unittest.TestCase):
    """Test gap 1 (argparse non-disclosure) and Test gap 2 (control-character
    reason codes), added during the second round of interim design-judge
    findings. These go through main()/argparse directly via _run(), not
    run_plan() directly, since argparse's own error() path is exactly what
    is being verified here."""

    SECRET = "sk-SECRET-LOOKING-TOKEN-99182"
    ABS_PATH_LIKE = r"C:\Users\someone\.ssh\id_rsa"
    CONTROL_PAYLOAD = "line1\nline2\x1b[31mFAKE[INVALID]\x1b[0m"

    def _assert_argparse_failure_is_safe(self, argv, forbidden_strings):
        code, out = _run(argv)
        self.assertEqual(code, 2, f"expected usage error, got exit {code}, out={out!r}")
        # A single fixed, safe message -- never argparse's own "unrecognized
        # arguments: <raw input>" style echo of what was actually typed.
        self.assertIn("INVALID_CLI_ARGUMENTS", out)
        self.assertNotIn("unrecognized arguments:", out)
        for forbidden in forbidden_strings:
            self.assertNotIn(forbidden, out)
        return out

    def test_unknown_option_with_secret_like_string_is_not_disclosed(self):
        with tempfile.TemporaryDirectory() as td:
            self._assert_argparse_failure_is_safe(
                ["plan", "--target-root", td, f"--totally-unknown-option={self.SECRET}"],
                [self.SECRET],
            )

    def test_malformed_set_value_with_secret_like_string_is_not_disclosed(self):
        # Note: without a "--set" prefix, "PROJECT_NAME=..." is an
        # unrecognized positional argument, so this is actually rejected by
        # _SafeArgumentParser.error() (argparse's own path), not by
        # run_plan's _parse_set_args. The non-disclosure requirement is the
        # same either way, and _parse_set_args' own rejection path (a
        # genuine "--set NAME=value_with_braces" value) is covered directly
        # by PlaceholderValueSafetyTests.test_general_value_defenses above.
        with tempfile.TemporaryDirectory() as td:
            code, out = _run(["plan", "--target-root", td, f"PROJECT_NAME={self.SECRET}extra{{{{brace"])
            self.assertEqual(code, 2)
            self.assertNotIn(self.SECRET, out)

    def test_invalid_argument_with_absolute_path_is_not_disclosed(self):
        with tempfile.TemporaryDirectory() as td:
            self._assert_argparse_failure_is_safe(
                ["plan", "--target-root", td, f"--{self.ABS_PATH_LIKE}"],
                [self.ABS_PATH_LIKE, "someone"],
            )

    def test_invalid_argument_with_newline_or_control_chars_is_not_disclosed(self):
        with tempfile.TemporaryDirectory() as td:
            self._assert_argparse_failure_is_safe(
                ["plan", "--target-root", td, f"--bogus={self.CONTROL_PAYLOAD}"],
                ["FAKE", "line2"],
            )

    def test_unknown_subcommand_with_secret_like_string_is_not_disclosed(self):
        code, out = _run([f"not-a-real-subcommand-{self.SECRET}"])
        self.assertEqual(code, 2)
        self.assertNotIn(self.SECRET, out)
        self.assertIn("INVALID_CLI_ARGUMENTS", out)

    def test_help_still_works_normally(self):
        code, out = _run(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("verify_workflow_template.py", out)

    # --- Test gap 2: explicit reason codes for control-character rejection ---

    CONTROL_REASON_CASES = [
        ("\n", "LF"),
        ("\r", "CR"),
        ("\t", "tab"),
        ("\x9b", "C1 control character"),
        ("\u2028", "U+2028 line separator"),
        ("\u2029", "U+2029 paragraph separator"),
        ("\x1b[31mred\x1b[0m", "ANSI escape sequence"),
    ]

    def test_general_value_control_character_reason_code(self):
        for value, label in self.CONTROL_REASON_CASES:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as td:
                    code, out = _run_plan_on(PACKAGE_ROOT, Path(td), [f"PROJECT_NAME={value}"])
                    self.assertEqual(code, 2, f"{label!r} should be exit 2, out={out!r}")
                    self.assertIn("CONTROL_CHARACTER_IN_SET_VALUE", out, f"{label!r} missing reason code")
                    if value.strip("\r\n\t\x0b\x0c ") != "":
                        self.assertNotIn(value, out)
                    # No forged status/reason line must appear.
                    self.assertNotIn("[IDENTICAL]", out)
                    self.assertNotIn("[DIFFERENT]", out)

    def test_path_placeholder_control_character_reason_code(self):
        # A control character in ANY --set value (including one used as a
        # target_path element) is rejected by the general --set parser
        # (_parse_set_args) before path-placeholder-specific validation is
        # even reached -- so the general reason code applies here too.
        # _is_unsafe_path_placeholder_value's own control-character check
        # exists as defense in depth for a differently-ordered code path,
        # but is not the one that fires for a pure control character today.
        for value, label in self.CONTROL_REASON_CASES:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as td:
                    code, out = _run_plan_on(PACKAGE_ROOT, Path(td), [f"DESIGN_SKILL_NAME={value}"])
                    self.assertEqual(code, 2, f"{label!r} should be exit 2, out={out!r}")
                    self.assertIn("CONTROL_CHARACTER_IN_SET_VALUE", out, f"{label!r} missing reason code")
                    if value.strip("\r\n\t\x0b\x0c ") != "":
                        self.assertNotIn(value, out)
                    self.assertNotIn("[IDENTICAL]", out)
                    self.assertNotIn("[DIFFERENT]", out)

    def test_path_placeholder_non_control_path_violation_reason_code(self):
        # Exercises _is_unsafe_path_placeholder_value's own path-specific
        # checks (reached only for values that pass the general control-
        # character/brace check but are still unsafe as a single path
        # element).
        cases = [
            ("/", "COLON_IN_VALUE_or_separator"),
            ("..", "DOTDOT_VALUE"),
            (".", "DOT_VALUE"),
            ("a:b", "COLON_IN_VALUE"),
        ]
        for value, label in cases:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as td:
                    code, out = _run_plan_on(PACKAGE_ROOT, Path(td), [f"DESIGN_SKILL_NAME={value}"])
                    self.assertEqual(code, 2, f"{label!r} should be exit 2, out={out!r}")
                    self.assertNotIn(value, out)


class Gap3RedirectPipelineTests(unittest.TestCase):
    """Area G3 (additional): mock-based redirect scenarios that confirm the
    FULL plan()/source-integrity() pipeline aggregates to exit 8, not just
    that the helper function returns a reason string in isolation."""

    def test_package_file_redirect_reaches_exit_8_via_source_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            elsewhere = Path(td) / "elsewhere"
            elsewhere.mkdir()
            _write(elsewhere / "doc.md", b"redirected content\n")

            real_realpath = os.path.realpath

            def fake_realpath(path):
                if str(path).endswith("doc.md") and "elsewhere" not in str(path):
                    return str(elsewhere / "doc.md")
                return real_realpath(path)

            with mock.patch("os.path.realpath", side_effect=fake_realpath):
                code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 8)
            self.assertIn("CONTAINMENT_ERROR", out)

    def test_genuine_intermediate_directory_redirect_via_multi_component_path(self):
        # Unlike a root-level redirect, this uses an actual multi-component
        # target_path ("sub/doc.md") and fakes only the intermediate "sub"
        # component as a reparse point -- not the root, not the leaf.
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["target_path"] = "sub/doc.md"
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            target = Path(td) / "target"
            (target / "sub").mkdir(parents=True)
            _write(target / "sub" / "doc.md", b"Hello example.\n")

            real_islink = os.path.islink

            def fake_islink(path):
                p = str(path)
                if p.endswith(os.path.join("target", "sub")):
                    return True
                return real_islink(path)

            with mock.patch("os.path.islink", side_effect=fake_islink):
                code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 8)
            self.assertIn("CONTAINMENT_ERROR", out)

    def test_root_external_escape_reaches_exit_8(self):
        # Real path resolves to a location entirely outside both package
        # root and target root -- not merely a different spot inside target.
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()
            _write(target / "doc.md", b"Hello example.\n")

            outside = Path(tempfile.gettempdir()) / "vwt_test_outside_root_marker"

            real_realpath = os.path.realpath

            def fake_realpath(path):
                if str(path).endswith("doc.md") and "target" in str(path):
                    return str(outside)
                return real_realpath(path)

            with mock.patch("os.path.realpath", side_effect=fake_realpath):
                code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 8)
            self.assertIn("CONTAINMENT_ERROR", out)
            self.assertNotIn(str(outside), out)

    @unittest.skipUnless(os.name == "nt", "Windows-specific reparse-point attribute branch")
    def test_windows_reparse_point_attribute_branch_reaches_exit_8(self):
        # Exercises the st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT
        # branch specifically (distinct from os.path.islink/isjunction),
        # which real symlink/junction creation cannot reliably exercise on
        # a non-elevated Windows account.
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()
            _write(target / "doc.md", b"Hello example.\n")

            real_lstat = os.lstat
            reparse_bit = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

            class _FakeStatResult:
                def __init__(self, real_result):
                    self._real = real_result
                    self.st_file_attributes = reparse_bit

                def __getattr__(self, name):
                    return getattr(self._real, name)

            def fake_lstat(path):
                real_result = real_lstat(path)
                if str(path).endswith("doc.md") and "target" in str(path):
                    return _FakeStatResult(real_result)
                return real_result

            with mock.patch("os.path.islink", return_value=False), \
                 mock.patch("os.lstat", side_effect=fake_lstat):
                code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 8)
            self.assertIn("CONTAINMENT_ERROR", out)


class UndeclaredContentPlaceholderTests(unittest.TestCase):
    """Area G4: an undeclared {{...}}-style token inside file *content*
    (distinct from one inside target_path, already covered elsewhere)."""

    def _manifest_with_mode(self, mode, target_path="doc.md"):
        manifest = _minimal_manifest_dict()
        manifest["files"][0]["adoption_mode"] = mode
        manifest["files"][0]["target_path"] = target_path
        return manifest

    def test_copy_if_absent_undeclared_content_placeholder_is_invalid_in_plan(self):
        content = b"Hello {{PROJECT_NAME}} and {{UNKNOWN_TOKEN}}.\n"
        with tempfile.TemporaryDirectory() as td:
            manifest = self._manifest_with_mode("COPY_IF_ABSENT")
            manifest["files"][0]["sha256"] = _sha256(content)
            root = _build_minimal_package(Path(td), manifest_dict=manifest, doc_content=content)
            target = Path(td) / "target"
            target.mkdir()
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 4)
            self.assertIn("[INVALID]", out)
            self.assertIn("UNDECLARED_PLACEHOLDER", out)
            # The file body itself (including its literal token text) must
            # never be printed, regardless of the token name.
            self.assertNotIn(content.decode(), out)

    def test_manual_review_undeclared_content_placeholder_is_invalid_in_plan(self):
        content = b"{{UNKNOWN_TOKEN}}\n"
        with tempfile.TemporaryDirectory() as td:
            manifest = self._manifest_with_mode("MANUAL_REVIEW", target_path=".mcp.json")
            manifest["files"][0]["path"] = ".mcp.json"
            manifest["files"][0]["sha256"] = _sha256(content)
            root = Path(td) / "pkg"
            root.mkdir()
            _write(root / ".mcp.json", content)
            _write(root / "manifest.json", json.dumps(manifest).encode("utf-8"))
            target = Path(td) / "target"
            target.mkdir()
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 4)
            self.assertIn("[INVALID]", out)
            self.assertIn("UNDECLARED_PLACEHOLDER", out)
            self.assertNotIn(content.decode(), out)

    def test_template_rename_undeclared_content_placeholder_is_invalid_in_plan(self):
        content = b"{{UNKNOWN_TOKEN}}\n"
        with tempfile.TemporaryDirectory() as td:
            manifest = self._manifest_with_mode("TEMPLATE_RENAME", target_path="renamed.md")
            manifest["files"][0]["sha256"] = _sha256(content)
            root = _build_minimal_package(Path(td), manifest_dict=manifest, doc_content=content)
            target = Path(td) / "target"
            target.mkdir()
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 4)
            self.assertIn("UNDECLARED_PLACEHOLDER", out)

    def test_source_integrity_detects_undeclared_content_placeholder(self):
        content = b"Hello {{PROJECT_NAME}} and {{UNKNOWN_TOKEN}}.\n"
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["sha256"] = _sha256(content)
            root = _build_minimal_package(Path(td), manifest_dict=manifest, doc_content=content)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("[INVALID]", out)
            self.assertIn("UNDECLARED_PLACEHOLDER", out)
            # An undeclared-placeholder rejection happens before the hash
            # comparison step, so it must not count as hash_compared.
            self.assertIn("hash_compared: 0", out)

    def test_declared_content_placeholder_alone_is_not_flagged(self):
        # Sanity check: a file using only declared placeholders must not be
        # flagged by the new content-scan.
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))  # BASE_DOC_CONTENT uses {{PROJECT_NAME}} only
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 0)
            self.assertNotIn("UNDECLARED_PLACEHOLDER", out)


class ManifestContainmentTests(unittest.TestCase):
    """Correction Pass 1 / Major fix: manifest.json itself must pass the
    same containment check as every other package file, before it is ever
    stat()'d or read. Note: manifest.json's own path is always the single
    root-level component "manifest.json" (it has no intermediate directory
    of its own), so a dedicated "manifest intermediate-directory redirect"
    scenario does not structurally exist for it. Coverage for that category
    of redirect is instead provided generically for multi-component paths
    by Gap3RedirectPipelineTests; test_manifest_containment_reuses_shared_helper
    below confirms manifest.json's bootstrap check goes through the exact
    same helper (no duplicated/divergent logic), so that generic coverage
    applies to manifest.json as well.
    """

    # --- real symlink: skip only if this environment cannot create one ---

    def test_manifest_external_symlink_rejected_real(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "pkg"
            root.mkdir()
            _write(root / "doc.md", BASE_DOC_CONTENT)
            outside = Path(td) / "outside"
            outside.mkdir()
            distinctive = b'{"redirected": "MANIFEST-EXTERNAL-REDIRECT-MARKER-5521"}'
            _write(outside / "real_manifest.json", distinctive)
            link_path = root / "manifest.json"
            try:
                os.symlink(str(outside / "real_manifest.json"), str(link_path))
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation not permitted in this environment")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 8)
            self.assertIn("CONTAINMENT_ERROR", out)
            self.assertNotIn("MANIFEST-EXTERNAL-REDIRECT-MARKER-5521", out)
            self.assertNotIn(str(outside), out)

    def test_manifest_internal_symlink_rejected_real(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "pkg"
            root.mkdir()
            _write(root / "doc.md", BASE_DOC_CONTENT)
            internal_dir = root / "internal_other_location"
            internal_dir.mkdir()
            _write(internal_dir / "real_manifest.json", b'{"redirected": "internal"}')
            link_path = root / "manifest.json"
            try:
                os.symlink(str(internal_dir / "real_manifest.json"), str(link_path))
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation not permitted in this environment")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 8)
            self.assertIn("CONTAINMENT_ERROR", out)

    # --- deterministic mock tests: never skipped ---

    def test_manifest_final_path_symlink_rejected_mock(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            real_islink = os.path.islink

            def fake_islink(path):
                if str(path).endswith("manifest.json"):
                    return True
                return real_islink(path)

            with mock.patch("os.path.islink", side_effect=fake_islink):
                code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 8)
            self.assertIn("CONTAINMENT_ERROR", out)

    def test_manifest_internal_redirect_rejected_mock(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            internal_elsewhere = root / "internal_elsewhere"
            internal_elsewhere.mkdir()
            _write(internal_elsewhere / "manifest.json", b'{"other": true}')

            real_realpath = os.path.realpath

            def fake_realpath(path):
                if str(path).endswith("manifest.json") and "internal_elsewhere" not in str(path):
                    return str(internal_elsewhere / "manifest.json")
                return real_realpath(path)

            with mock.patch("os.path.realpath", side_effect=fake_realpath):
                code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 8)
            self.assertIn("CONTAINMENT_ERROR", out)

    def test_manifest_root_external_redirect_rejected_mock(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            outside = Path(tempfile.gettempdir()) / "vwt_test_manifest_outside_marker"

            real_realpath = os.path.realpath

            def fake_realpath(path):
                if str(path).endswith("manifest.json") and str(root) in str(path):
                    return str(outside)
                return real_realpath(path)

            with mock.patch("os.path.realpath", side_effect=fake_realpath):
                code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 8)
            self.assertIn("CONTAINMENT_ERROR", out)
            self.assertNotIn(str(outside), out)

    def test_manifest_external_redirect_rejected_via_plan_mock(self):
        # Confirms the `plan` subcommand (not only source-integrity) also
        # calls the now-protected load_manifest() before doing anything else.
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()
            outside = Path(td) / "outside"
            outside.mkdir()
            _write(outside / "manifest.json", b'{"other": true}')

            real_realpath = os.path.realpath

            def fake_realpath(path):
                if str(path).endswith("manifest.json") and "outside" not in str(path):
                    return str(outside / "manifest.json")
                return real_realpath(path)

            with mock.patch("os.path.realpath", side_effect=fake_realpath):
                code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 8)
            self.assertIn("CONTAINMENT_ERROR", out)

    @unittest.skipUnless(os.name == "nt", "Windows-specific reparse-point attribute branch")
    def test_manifest_windows_reparse_point_attribute_reaches_exit_8(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            real_lstat = os.lstat
            reparse_bit = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

            class _FakeStatResult:
                def __init__(self, real_result):
                    self._real = real_result
                    self.st_file_attributes = reparse_bit

                def __getattr__(self, name):
                    return getattr(self._real, name)

            def fake_lstat(path):
                real_result = real_lstat(path)
                if str(path).endswith("manifest.json"):
                    return _FakeStatResult(real_result)
                return real_result

            with mock.patch("os.path.islink", return_value=False), \
                 mock.patch("os.lstat", side_effect=fake_lstat):
                code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 8)
            self.assertIn("CONTAINMENT_ERROR", out)

    def test_manifest_containment_reuses_shared_helper(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            calls = []
            real_fn = vwt._resolve_and_check_containment

            def spy(root_arg, rel_path_str):
                calls.append((root_arg, rel_path_str))
                return real_fn(root_arg, rel_path_str)

            with mock.patch.object(vwt, "_resolve_and_check_containment", side_effect=spy):
                code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 0)
            self.assertIn((root, "manifest.json"), calls)

    # --- bootstrap non-containment failure modes ---

    def test_manifest_json_missing_exit_3(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "pkg"
            root.mkdir()
            _write(root / "doc.md", BASE_DOC_CONTENT)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 3)
            self.assertIn("MANIFEST_MISSING", out)

    def test_manifest_json_is_directory_exit_4(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            (root / "manifest.json").unlink()
            (root / "manifest.json").mkdir()
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("MANIFEST_IS_DIRECTORY", out)

    def test_manifest_json_special_file_exit_4(self):
        if os.name == "nt":
            self.skipTest("FIFO creation not supported on Windows")
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            (root / "manifest.json").unlink()
            try:
                os.mkfifo(str(root / "manifest.json"))
            except (AttributeError, OSError):
                self.skipTest("mkfifo unavailable in this environment")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("MANIFEST_SPECIAL_FILE", out)

    # --- normal-file regression (Task C: happy path unaffected by the fix) ---

    def test_normal_manifest_source_integrity_still_exit_0(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 0)
            self.assertIn("manifest_valid: 1", out)
            self.assertIn("self_hash_omitted: 1", out)
            self.assertIn("blocking_errors: 0", out)

    def test_real_package_still_passes_after_manifest_containment_fix(self):
        code, out = _run_source_integrity_on(PACKAGE_ROOT)
        self.assertEqual(code, 0)
        self.assertIn("manifest_valid: 1", out)
        self.assertIn("self_hash_omitted: 1", out)
        self.assertIn("blocking_errors: 0", out)


class ScanEntryLimitBoundaryTests(unittest.TestCase):
    """Minor fix: the package-root scan's MAX_MANIFEST_FILES boundary was
    off-by-one (a 501st on-disk entry was silently accepted). These pin the
    exact 499/500/501 boundary."""

    def _build_package_with_n_root_entries(self, td, total_entries):
        # total_entries counts every entry the scan will see directly under
        # package root: doc.md + manifest.json (2 required, declared) plus
        # enough extra undeclared flat files to reach total_entries. Extra
        # files are named so they sort after "doc.md"/"manifest.json"
        # alphabetically, keeping scan order predictable.
        root = _build_minimal_package(Path(td))
        extra_count = total_entries - 2
        for i in range(extra_count):
            _write(root / f"zfile{i:04d}.md", f"extra {i}".encode())
        return root, extra_count

    def test_499_entries_below_limit_not_flagged_as_too_many(self):
        with tempfile.TemporaryDirectory() as td:
            root, extra_count = self._build_package_with_n_root_entries(td, 499)
            code, out = _run_source_integrity_on(root)
            self.assertNotIn("TOO_MANY_PACKAGE_FILES", out)
            self.assertIn(f"unlisted_package_files: {extra_count}", out)

    def test_500_entries_at_limit_still_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            root, extra_count = self._build_package_with_n_root_entries(td, 500)
            code, out = _run_source_integrity_on(root)
            self.assertNotIn("TOO_MANY_PACKAGE_FILES", out)
            self.assertIn(f"unlisted_package_files: {extra_count}", out)

    def test_501_entries_exceeds_limit_exit_4(self):
        with tempfile.TemporaryDirectory() as td:
            root, extra_count = self._build_package_with_n_root_entries(td, 501)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            # Exactly one TOO_MANY_PACKAGE_FILES line -- no repeated spam.
            self.assertEqual(out.count("TOO_MANY_PACKAGE_FILES"), 1)
            # Early bail-out: the scan stops at the 501st entry, so not
            # every one of the extra files gets its own UNLISTED report.
            self.assertLess(out.count("UNLISTED_PACKAGE_FILE"), extra_count)


class _ScandirSpecialFileProxy:
    """Wraps a real os.DirEntry so one named entry reports a non-regular,
    non-directory st_mode from .stat(), without needing a real FIFO/socket/
    device file (which is unavailable or restricted on some platforms)."""

    def __init__(self, real_entry, special_name):
        self._real = real_entry
        self._special_name = special_name

    @property
    def name(self):
        return self._real.name

    def is_dir(self, follow_symlinks=False):
        return self._real.is_dir(follow_symlinks=follow_symlinks)

    def stat(self, follow_symlinks=False):
        if self._real.name == self._special_name:
            class _FakeStat:
                st_mode = 0  # neither S_ISREG nor S_ISDIR nor a symlink bit
            return _FakeStat()
        return self._real.stat(follow_symlinks=follow_symlinks)


class UnlistedSpecialFileTests(unittest.TestCase):
    """Minor fix: an unlisted non-regular file must be reported as
    UNLISTED_SPECIAL_FILE, distinct from UNLISTED_PACKAGE_FILE (which is
    for unlisted regular files)."""

    def test_unlisted_special_file_fifo_real(self):
        if os.name == "nt":
            self.skipTest("FIFO creation not supported on Windows")
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            try:
                os.mkfifo(str(root / "stray_fifo"))
            except (AttributeError, OSError):
                self.skipTest("mkfifo unavailable in this environment")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("reason: UNLISTED_SPECIAL_FILE", out)
            self.assertNotIn("reason: UNLISTED_PACKAGE_FILE", out)

    def test_unlisted_special_file_mock_non_skip(self):
        # Deterministic, never skipped (unlike the FIFO test above).
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            _write(root / "stray_thing", b"placeholder")

            real_scandir = os.scandir

            def fake_scandir(path):
                return [_ScandirSpecialFileProxy(e, "stray_thing") for e in real_scandir(path)]

            with mock.patch("os.scandir", side_effect=fake_scandir):
                code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("reason: UNLISTED_SPECIAL_FILE", out)
            self.assertNotIn("reason: UNLISTED_PACKAGE_FILE", out)
            self.assertIn("package: stray_thing", out)


class InvalidSummaryCounterConsistencyTests(unittest.TestCase):
    """Minor fix: scan-detected non-blocking problems must be folded into
    the summary's `invalid` counter so a displayed [INVALID] line always
    has a matching count; blocking containment errors must not be
    double-counted into `invalid`."""

    def test_single_unlisted_regular_file_increments_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            _write(root / "stray.md", b"unlisted content")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("invalid: 1", out)
            self.assertIn("unlisted_package_files: 1", out)

    def test_multiple_unlisted_files_invalid_matches_count(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            _write(root / "stray1.md", b"a")
            _write(root / "stray2.md", b"b")
            _write(root / "stray3.md", b"c")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("invalid: 3", out)
            self.assertIn("unlisted_package_files: 3", out)

    def test_unlisted_special_file_increments_invalid_not_unlisted_package_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            _write(root / "stray_thing", b"placeholder")

            real_scandir = os.scandir

            def fake_scandir(path):
                return [_ScandirSpecialFileProxy(e, "stray_thing") for e in real_scandir(path)]

            with mock.patch("os.scandir", side_effect=fake_scandir):
                code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("invalid: 1", out)
            self.assertIn("unlisted_package_files: 0", out)

    def test_blocking_unlisted_redirect_not_double_counted_in_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            _write(root / "sneaky_entry.md", b"placeholder content\n")

            real_islink = os.path.islink

            def fake_islink(path):
                if str(path).endswith("sneaky_entry.md"):
                    return True
                return real_islink(path)

            with mock.patch("os.path.islink", side_effect=fake_islink):
                code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 8)
            self.assertIn("invalid: 0", out)
            self.assertIn("blocking_errors: 1", out)
            self.assertIn("[BLOCKING_ERROR]", out)
            self.assertNotIn("[INVALID]", out)


class ManifestPathSeparatorTests(unittest.TestCase):
    """Minor fix: manifest path/target_path must use forward slash only;
    a backslash is rejected as INVALID rather than silently treated as a
    separator."""

    def test_manifest_path_with_backslash_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["path"] = "docs\\doc.md"
            root = _build_minimal_package(Path(td), manifest_dict=manifest, write_doc=False)
            _write(root / "docs" / "doc.md", BASE_DOC_CONTENT)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("UNSAFE_PACKAGE_PATH", out)

    def test_target_path_with_backslash_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["target_path"] = "docs\\doc.md"
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("UNSAFE_TARGET_PATH", out)

    def test_rendered_target_path_with_backslash_rejected_in_plan(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["target_path"] = "docs\\doc.md"
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            target = Path(td) / "target"
            target.mkdir()
            code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 4)
            self.assertIn("UNSAFE_TARGET_PATH", out)

    def test_forward_slash_path_still_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = _minimal_manifest_dict()
            manifest["files"][0]["path"] = "docs/doc.md"
            manifest["files"][0]["target_path"] = "docs/doc.md"
            root = Path(td) / "pkg"
            root.mkdir()
            _write(root / "docs" / "doc.md", BASE_DOC_CONTENT)
            _write(root / "manifest.json", json.dumps(manifest).encode("utf-8"))
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 0)

    def test_existing_windows_absolute_unc_drive_relative_still_rejected(self):
        # Regression guard: the new backslash check must not change the
        # existing (already-correct) rejection of these forms.
        cases = ["C:\\Windows\\System32\\evil.md", "\\\\server\\share\\evil.md", "C:evil.md"]
        for target_path in cases:
            with self.subTest(target_path=target_path):
                with tempfile.TemporaryDirectory() as td:
                    manifest = _minimal_manifest_dict()
                    manifest["files"][0]["target_path"] = target_path
                    root = _build_minimal_package(Path(td), manifest_dict=manifest)
                    code, out = _run_source_integrity_on(root)
                    self.assertEqual(code, 4)
                    self.assertIn("UNSAFE_TARGET_PATH", out)


class BlockingErrorDisplayAndCounterTests(unittest.TestCase):
    """Correction Pass 2 / Test gap 1: blocking findings must be displayed
    as [BLOCKING_ERROR] (not [INVALID]) and counted in `blocking_errors`
    (not `invalid`), with the displayed line count for each label matching
    its own summary counter exactly, and the same finding never counted in
    both. Cases A-D as specified."""

    def test_case_a_only_blocking_redirect(self):
        # Unlisted symlink/reparse (internal-redirect-shaped) finding, no
        # other unlisted/invalid finding present.
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            _write(root / "sneaky_entry.md", b"placeholder content\n")

            real_islink = os.path.islink

            def fake_islink(path):
                if str(path).endswith("sneaky_entry.md"):
                    return True
                return real_islink(path)

            with mock.patch("os.path.islink", side_effect=fake_islink):
                code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 8)
            self.assertIn("[BLOCKING_ERROR]", out)
            self.assertIn("blocking_errors: 1", out)
            self.assertIn("invalid: 0", out)
            self.assertNotIn("[INVALID]", out)

    def test_case_b_blocking_and_invalid_together(self):
        # A root-external-redirect-shaped blocking finding AND an ordinary
        # unlisted regular file both present in the same run.
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            _write(root / "sneaky_entry.md", b"placeholder content\n")
            _write(root / "stray.md", b"unlisted content\n")

            real_islink = os.path.islink

            def fake_islink(path):
                if str(path).endswith("sneaky_entry.md"):
                    return True
                return real_islink(path)

            with mock.patch("os.path.islink", side_effect=fake_islink):
                code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 8)
            self.assertIn("blocking_errors: 1", out)
            self.assertIn("invalid: 1", out)
            # Each displayed status label's line count matches its own
            # summary counter exactly.
            self.assertEqual(out.count("[BLOCKING_ERROR]"), 1)
            self.assertEqual(out.count("[INVALID]"), 1)

    def test_case_c_only_invalid_no_blocking(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            _write(root / "stray.md", b"unlisted content\n")
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertIn("[INVALID]", out)
            self.assertIn("invalid: 1", out)
            self.assertIn("blocking_errors: 0", out)
            self.assertNotIn("[BLOCKING_ERROR]", out)

    def test_case_d_normal_package(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 0)
            self.assertIn("blocking_errors: 0", out)
            self.assertIn("invalid: 0", out)
            self.assertNotIn("[BLOCKING_ERROR]", out)
            self.assertNotIn("[INVALID]", out)

    def test_case_d_real_package(self):
        code, out = _run_source_integrity_on(PACKAGE_ROOT)
        self.assertEqual(code, 0)
        self.assertIn("blocking_errors: 0", out)
        self.assertIn("invalid: 0", out)
        self.assertNotIn("[BLOCKING_ERROR]", out)

    def test_blocking_per_file_containment_finding_via_plan(self):
        # The same BLOCKING_ERROR/blocking_errors separation must also hold
        # for the plan subcommand's per-file containment check (not only
        # source-integrity's unlisted-file scan).
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()

            real_islink = os.path.islink

            def fake_islink(path):
                if str(path).endswith("doc.md") and "target" not in str(path):
                    return True
                return real_islink(path)

            with mock.patch("os.path.islink", side_effect=fake_islink):
                code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])
            self.assertEqual(code, 8)
            self.assertIn("[BLOCKING_ERROR]", out)
            self.assertIn("blocking_errors: 1", out)
            self.assertIn("invalid: 0", out)
            self.assertNotIn("[INVALID]", out)


class NestedScanLimitTests(unittest.TestCase):
    """Correction Pass 2 / Test gap 2: the package scan's entry budget
    (MAX_MANIFEST_FILES) must be enforced correctly across a genuinely
    nested/recursive directory tree, report TOO_MANY_PACKAGE_FILES exactly
    once per run, and stop scanning further branches immediately once the
    budget is exceeded -- not just within the flat, single-directory
    fixtures in ScanEntryLimitBoundaryTests (kept unchanged above)."""

    def test_nested_499_entries_below_limit_not_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            sub = root / "sub"
            sub.mkdir()
            # 1 entry for "sub" itself + 497 files inside it = 498 extra
            # entries; + doc.md + manifest.json = 500... use 496 files so
            # the nested total (1 + 496 + 2 = 499) stays strictly below.
            for i in range(496):
                _write(sub / f"file{i:04d}.md", b"x")
            code, out = _run_source_integrity_on(root)
            self.assertNotIn("TOO_MANY_PACKAGE_FILES", out)

    def test_nested_500_entries_at_limit_still_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            sub = root / "sub"
            sub.mkdir()
            # 1 (sub dir) + 497 files + 2 (doc.md, manifest.json) = 500.
            for i in range(497):
                _write(sub / f"file{i:04d}.md", b"x")
            code, out = _run_source_integrity_on(root)
            self.assertNotIn("TOO_MANY_PACKAGE_FILES", out)

    def test_nested_501_all_other_entries_declared_invalid_is_exactly_one(self):
        # Every on-disk entry other than the one that trips the budget is
        # declared in the manifest and byte-identical, so the ONLY finding
        # is the budget itself: invalid ends up exactly 1.
        with tempfile.TemporaryDirectory() as td:
            n_extra = 497  # + doc.md + manifest.json + "sub" dir = 500 clean entries
            extra_content = b"x"
            extra_entries = [{
                "path": f"sub/file{i:04d}.md", "classification": "WORKFLOW_DOC",
                "content_mode": "NEW", "sha256": _sha256(extra_content), "required": True,
                "notes": "x", "target_path": f"sub/file{i:04d}.md",
                "adoption_mode": "COPY_IF_ABSENT",
            } for i in range(n_extra)]
            manifest = _minimal_manifest_dict(extra_files=extra_entries)
            root = _build_minimal_package(Path(td), manifest_dict=manifest)
            sub = root / "sub"
            sub.mkdir()
            for i in range(n_extra):
                _write(sub / f"file{i:04d}.md", extra_content)
            # The 501st on-disk entry: undeclared, but sorts after
            # everything above ("sub" < "zzz_undeclared...") so it is
            # examined last and never individually classified.
            _write(root / "zzz_undeclared_501st.md", b"never inspected")

            code, out = _run_source_integrity_on(root)
            self.assertEqual(code, 4)
            self.assertEqual(out.count("TOO_MANY_PACKAGE_FILES"), 1)
            self.assertIn("invalid: 1", out)
            self.assertIn("blocking_errors: 0", out)
            self.assertNotIn("zzz_undeclared_501st.md", out)

    def test_nested_multiple_deep_branches_stops_early_no_duplicate_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            branch_a = root / "branchA"
            branch_a.mkdir()
            for i in range(510):
                _write(branch_a / f"file{i:04d}.md", b"x")
            branch_b = root / "branchB"
            branch_b.mkdir()
            for i in range(5):
                _write(branch_b / f"bfile{i}.md", b"x")
            branch_c = root / "branchC"
            branch_c.mkdir()
            for i in range(5):
                _write(branch_c / f"cfile{i}.md", b"x")

            real_scandir = os.scandir
            scanned_dirs = []

            def spy_scandir(path):
                scanned_dirs.append(str(path))
                return real_scandir(path)

            before = _hash_tree(root)
            with mock.patch("os.scandir", side_effect=spy_scandir):
                code, out = _run_source_integrity_on(root)
            after = _hash_tree(root)

            self.assertEqual(code, 4)
            # Exactly one TOO_MANY_PACKAGE_FILES -- no duplicate reporting
            # from an ancestor continuing to iterate remaining siblings.
            self.assertEqual(out.count("TOO_MANY_PACKAGE_FILES"), 1)
            # branchB and branchC were never scanned at all: only root's
            # own directory and branchA's were ever passed to scandir.
            self.assertFalse(any(str(branch_b) in d for d in scanned_dirs))
            self.assertFalse(any(str(branch_c) in d for d in scanned_dirs))
            self.assertNotIn("bfile0.md", out)
            self.assertNotIn("cfile0.md", out)
            # Read-only: the fixture tree itself is unchanged.
            self.assertEqual(before, after)

    def test_nested_scan_tree_unchanged_after_499_500_fixtures(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            sub = root / "sub"
            sub.mkdir()
            for i in range(497):
                _write(sub / f"file{i:04d}.md", b"x")
            before = _hash_tree(root)
            _run_source_integrity_on(root)
            after = _hash_tree(root)
            self.assertEqual(before, after)


class ManifestBootstrapDisplayTests(unittest.TestCase):
    """Acceptance Patch: manifest.json's own containment failure is a
    bootstrap-stage failure (detected before the manifest can even be
    parsed), so it is displayed as [BLOCKED] -- never [BLOCKING_ERROR] --
    and no summary (and therefore no `blocking_errors` counter) is ever
    printed for it, since the summary is only built after a manifest has
    successfully loaded. This is distinct from a per-file or scan-detected
    blocking finding AFTER a successful manifest load, which is displayed
    as [BLOCKING_ERROR] and counted in `blocking_errors` (covered by
    BlockingErrorDisplayAndCounterTests). Both go through the exact same
    top-level entry points a real invocation uses (run_source_integrity /
    run_plan via _run_source_integrity_on / _run_plan_on), not an isolated
    helper call."""

    def test_manifest_bootstrap_failure_is_blocked_not_blocking_error_source_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            outside = Path(tempfile.gettempdir()) / "vwt_bootstrap_outside_SECRET_MARKER_8231"

            real_realpath = os.path.realpath

            def fake_realpath(path):
                if str(path).endswith("manifest.json") and str(root) in str(path):
                    return str(outside)
                return real_realpath(path)

            with mock.patch("os.path.realpath", side_effect=fake_realpath):
                code, out = _run_source_integrity_on(root)

            self.assertEqual(code, 8)
            self.assertIn("[BLOCKED]", out)
            self.assertIn("reason: CONTAINMENT_ERROR", out)
            self.assertNotIn("[BLOCKING_ERROR]", out)
            self.assertNotIn("summary:", out)
            self.assertNotIn("blocking_errors", out)
            self.assertNotIn(str(root), out)
            self.assertNotIn(str(outside), out)
            self.assertNotIn("SECRET_MARKER_8231", out)

    def test_manifest_bootstrap_failure_is_blocked_not_blocking_error_plan(self):
        with tempfile.TemporaryDirectory() as td:
            root = _build_minimal_package(Path(td))
            target = Path(td) / "target"
            target.mkdir()
            outside = Path(tempfile.gettempdir()) / "vwt_bootstrap_outside_plan_SECRET_MARKER_9142"

            real_realpath = os.path.realpath

            def fake_realpath(path):
                if str(path).endswith("manifest.json") and str(root) in str(path):
                    return str(outside)
                return real_realpath(path)

            with mock.patch("os.path.realpath", side_effect=fake_realpath):
                code, out = _run_plan_on(root, target, ["PROJECT_NAME=example"])

            self.assertEqual(code, 8)
            self.assertIn("[BLOCKED]", out)
            self.assertIn("reason: CONTAINMENT_ERROR", out)
            self.assertNotIn("[BLOCKING_ERROR]", out)
            self.assertNotIn("summary:", out)
            self.assertNotIn("blocking_errors", out)
            self.assertNotIn(str(target), out)
            self.assertNotIn(str(root), out)
            self.assertNotIn(str(outside), out)
            self.assertNotIn("SECRET_MARKER_9142", out)


if __name__ == "__main__":
    unittest.main()
