#!/usr/bin/env python3
"""Deterministic, read-only App Profile validator and outcome gatekeeper.

The tool consumes evaluation evidence produced by an external evaluator.  It
never runs evaluations, shells, Git, network operations, or file writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = "1.1"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_ITEMS = 1000
MAX_NESTING_DEPTH = 64
MAX_JSON_NODES = 10000
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
DIRECTIONS = {"maximize", "minimize", "target", "threshold", "range"}
VERDICT_EXIT = {
    "PASS": 0,
    "PASS_TO_CONFIRMATION": 10,
    "FAIL": 20,
    "INSUFFICIENT_EVIDENCE": 30,
    "BLOCKED": 40,
}


class GateError(ValueError):
    """A sanitized validation error with a stable reason code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _reject_constant(_value: str) -> None:
    raise GateError("NON_FINITE_JSON_NUMBER")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise GateError("DUPLICATE_JSON_KEY")
        obj[key] = value
    return obj


def _check_structure(value: Any, depth: int = 0, counter: list[int] | None = None) -> None:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > MAX_JSON_NODES or depth > MAX_NESTING_DEPTH:
        raise GateError("JSON_STRUCTURE_TOO_COMPLEX")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 256:
                raise GateError("JSON_KEY_INVALID")
            _check_structure(child, depth + 1, counter)
    elif isinstance(value, list):
        if len(value) > MAX_ITEMS:
            raise GateError("JSON_ARRAY_TOO_LARGE")
        for child in value:
            _check_structure(child, depth + 1, counter)
    elif isinstance(value, str) and len(value) > 16384:
        raise GateError("JSON_STRING_TOO_LARGE")


def _read_json(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise GateError("INPUT_UNREADABLE") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise GateError("INPUT_NOT_REGULAR_FILE")
    if getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        raise GateError("INPUT_REPARSE_POINT")
    if info.st_size > MAX_JSON_BYTES:
        raise GateError("INPUT_TOO_LARGE")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise GateError("INPUT_UNREADABLE") from exc
    if raw.startswith(b"\xef\xbb\xbf"):
        raise GateError("UTF8_BOM_FORBIDDEN")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except GateError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise GateError("INVALID_JSON") from exc
    if not isinstance(value, dict):
        raise GateError("ROOT_MUST_BE_OBJECT")
    _check_structure(value)
    return value


def _object(value: Any, required: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateError(f"{path}_MUST_BE_OBJECT")
    keys = set(value)
    if keys != required:
        raise GateError(f"{path}_FIELDS_INVALID")
    return value


def _array(value: Any, path: str, *, allow_empty: bool = False) -> list[Any]:
    if not isinstance(value, list) or len(value) > MAX_ITEMS:
        raise GateError(f"{path}_ARRAY_INVALID")
    if not allow_empty and not value:
        raise GateError(f"{path}_ARRAY_EMPTY")
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise GateError(f"{path}_TEXT_INVALID")
    if any(ord(char) < 32 for char in value):
        raise GateError(f"{path}_CONTROL_CHARACTER")
    return value


def _identifier(value: Any, path: str) -> str:
    text = _text(value, path)
    if not ID_RE.fullmatch(text):
        raise GateError(f"{path}_ID_INVALID")
    return text


def _decimal(value: Any, path: str) -> Decimal:
    if not isinstance(value, str) or value == "-0" or not DECIMAL_RE.fullmatch(value):
        raise GateError(f"{path}_DECIMAL_INVALID")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise GateError(f"{path}_DECIMAL_INVALID") from exc
    if not number.is_finite():
        raise GateError(f"{path}_DECIMAL_INVALID")
    return number


def _positive_int(value: Any, path: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= maximum):
        raise GateError(f"{path}_INTEGER_INVALID")
    return value


def _bounded_int(value: Any, path: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (minimum <= value <= maximum):
        raise GateError(f"{path}_INTEGER_INVALID")
    return value


def _safe_relative_path(value: Any, path: str) -> str:
    text = _text(value, path)
    if "\\" in text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise GateError(f"{path}_PATH_UNSAFE")
    pure = PurePosixPath(text)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise GateError(f"{path}_PATH_UNSAFE")
    if text.startswith("//") or "\x00" in text:
        raise GateError(f"{path}_PATH_UNSAFE")
    return text


def _artifact_binding(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateError(f"{path}_MUST_BE_OBJECT")
    keys = set(value)
    if keys == {"artifact_id", "immutable_ref"}:
        _identifier(value["artifact_id"], f"{path}_ARTIFACT_ID")
        _text(value["immutable_ref"], f"{path}_IMMUTABLE_REF")
    elif keys == {"artifact_id", "sha256"}:
        _identifier(value["artifact_id"], f"{path}_ARTIFACT_ID")
        if not isinstance(value["sha256"], str) or not SHA256_RE.fullmatch(value["sha256"]):
            raise GateError(f"{path}_SHA256_INVALID")
    else:
        raise GateError(f"{path}_FIELDS_INVALID")
    return value


def _artifact_locator(value: dict[str, Any]) -> tuple[str, str]:
    if "immutable_ref" in value:
        return "immutable_ref", value["immutable_ref"]
    return "sha256", value["sha256"]


def _paths_overlap(left: str, right: str) -> bool:
    left_parts = tuple(part.casefold() for part in PurePosixPath(left).parts)
    right_parts = tuple(part.casefold() for part in PurePosixPath(right).parts)
    shared = min(len(left_parts), len(right_parts))
    return left_parts[:shared] == right_parts[:shared]


def _unique_ids(items: list[dict[str, Any]], key: str, path: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        identifier = _identifier(item.get(key), f"{path}_{key}")
        if identifier in result:
            raise GateError(f"{path}_ID_DUPLICATE")
        result[identifier] = item
    return result


def _validate_parameters(direction: str, value: Any, path: str) -> None:
    if direction in {"maximize", "minimize"}:
        params = _object(value, {"limit"}, path)
        _decimal(params["limit"], f"{path}_limit")
    elif direction == "target":
        params = _object(value, {"target", "tolerance"}, path)
        _decimal(params["target"], f"{path}_target")
        if _decimal(params["tolerance"], f"{path}_tolerance") < 0:
            raise GateError(f"{path}_TOLERANCE_NEGATIVE")
    elif direction == "threshold":
        params = _object(value, {"operator", "limit"}, path)
        if params["operator"] not in {"gte", "lte"}:
            raise GateError(f"{path}_OPERATOR_INVALID")
        _decimal(params["limit"], f"{path}_limit")
    elif direction == "range":
        params = _object(value, {"lower", "upper"}, path)
        lower = _decimal(params["lower"], f"{path}_lower")
        upper = _decimal(params["upper"], f"{path}_upper")
        if lower > upper:
            raise GateError(f"{path}_RANGE_INVERTED")


def _validate_criterion(
    value: Any,
    path: str,
    metrics: dict[str, dict[str, Any]],
    segments: set[str],
) -> tuple[str, str]:
    criterion = _object(
        value,
        {"metric_id", "segment_id", "basis", "statistic", "parameters"},
        path,
    )
    metric_id = _identifier(criterion["metric_id"], f"{path}_metric_id")
    segment_id = _identifier(criterion["segment_id"], f"{path}_segment_id")
    if metric_id not in metrics or segment_id not in segments:
        raise GateError(f"{path}_REFERENCE_INVALID")
    if segment_id not in metrics[metric_id]["required_segments"]:
        raise GateError(f"{path}_METRIC_SEGMENT_NOT_REQUIRED")
    if criterion["basis"] not in {"candidate", "delta"}:
        raise GateError(f"{path}_BASIS_INVALID")
    direction = metrics[metric_id]["direction"]
    expected_statistics = {
        "maximize": {"lower"},
        "minimize": {"upper"},
        "target": {"interval"},
        "threshold": {"estimate", "lower", "upper"},
        "range": {"interval"},
    }[direction]
    if criterion["statistic"] not in expected_statistics:
        raise GateError(f"{path}_STATISTIC_INVALID")
    _validate_parameters(direction, criterion["parameters"], f"{path}_parameters")
    return metric_id, segment_id


def validate_profile(profile: dict[str, Any]) -> dict[str, Any]:
    top = _object(
        profile,
        {
            "schema_version", "profile_id", "profile_version", "status",
            "applicability", "objective", "baseline", "cycle", "evaluation_targets",
            "segments", "metrics", "stages", "tournament", "change_scope",
            "permissions", "reporting", "rejected_hypothesis_memory",
            "unresolved_unknowns",
        },
        "PROFILE",
    )
    if top["schema_version"] != SCHEMA_VERSION:
        raise GateError("SCHEMA_VERSION_UNSUPPORTED")
    _identifier(top["profile_id"], "PROFILE_ID")
    _identifier(top["profile_version"], "PROFILE_VERSION")
    if top["status"] not in {"active", "example_only"}:
        raise GateError("PROFILE_STATUS_INVALID")

    applicability = _object(
        top["applicability"], {"description", "change_kinds", "exclusions"}, "APPLICABILITY"
    )
    _text(applicability["description"], "APPLICABILITY_DESCRIPTION")
    for item in _array(applicability["change_kinds"], "CHANGE_KINDS"):
        _identifier(item, "CHANGE_KIND")
    for item in _array(applicability["exclusions"], "EXCLUSIONS"):
        _text(item, "EXCLUSION")

    objective = _object(top["objective"], {"description", "primary_metric_id"}, "OBJECTIVE")
    _text(objective["description"], "OBJECTIVE_DESCRIPTION")
    primary_reference = _identifier(objective["primary_metric_id"], "PRIMARY_METRIC_REFERENCE")

    _artifact_binding(top["baseline"], "BASELINE")

    target_items = []
    for raw in _array(top["evaluation_targets"], "EVALUATION_TARGETS"):
        target = _object(
            raw,
            {"id", "dataset_id", "dataset_version", "dataset_sha256", "protocol_id"},
            "EVALUATION_TARGET",
        )
        _identifier(target["id"], "EVALUATION_TARGET_ID")
        _identifier(target["dataset_id"], "DATASET_ID")
        _identifier(target["dataset_version"], "DATASET_VERSION")
        if not isinstance(target["dataset_sha256"], str) or not SHA256_RE.fullmatch(target["dataset_sha256"]):
            raise GateError("DATASET_SHA256_INVALID")
        _identifier(target["protocol_id"], "PROTOCOL_ID")
        target_items.append(target)
    targets = _unique_ids(target_items, "id", "EVALUATION_TARGET")

    segment_items = []
    for raw in _array(top["segments"], "SEGMENTS"):
        segment = _object(raw, {"id", "description"}, "SEGMENT")
        _identifier(segment["id"], "SEGMENT_ID")
        _text(segment["description"], "SEGMENT_DESCRIPTION")
        segment_items.append(segment)
    segment_map = _unique_ids(segment_items, "id", "SEGMENT")

    metric_items = []
    primary_count = 0
    guardrail_count = 0
    for raw in _array(top["metrics"], "METRICS"):
        metric = _object(raw, {"id", "role", "direction", "unit", "required_segments"}, "METRIC")
        _identifier(metric["id"], "METRIC_ID")
        if metric["role"] == "primary":
            primary_count += 1
        elif metric["role"] == "guardrail":
            guardrail_count += 1
        else:
            raise GateError("METRIC_ROLE_INVALID")
        if metric["direction"] not in DIRECTIONS:
            raise GateError("METRIC_DIRECTION_INVALID")
        _text(metric["unit"], "METRIC_UNIT")
        required_segments = _array(metric["required_segments"], "METRIC_REQUIRED_SEGMENTS")
        if len(required_segments) != len(set(required_segments)):
            raise GateError("METRIC_SEGMENT_DUPLICATE")
        for segment_id in required_segments:
            if _identifier(segment_id, "METRIC_SEGMENT_ID") not in segment_map:
                raise GateError("METRIC_SEGMENT_UNKNOWN")
        metric_items.append(metric)
    metrics = _unique_ids(metric_items, "id", "METRIC")
    if primary_count != 1 or guardrail_count < 1:
        raise GateError("METRIC_CARDINALITY_INVALID")
    if primary_reference not in metrics or metrics[primary_reference]["role"] != "primary":
        raise GateError("PRIMARY_METRIC_REFERENCE_INVALID")

    stages = _object(top["stages"], {"screening", "confirmation"}, "STAGES")
    for stage_name in ("screening", "confirmation"):
        stage = _object(
            stages[stage_name],
            {
                "evaluation_target_id", "min_total_observations",
                "min_observations_per_segment", "uncertainty", "criteria",
                "catastrophic_criteria",
            },
            f"STAGE_{stage_name.upper()}",
        )
        if _identifier(stage["evaluation_target_id"], "STAGE_TARGET_ID") not in targets:
            raise GateError("STAGE_TARGET_UNKNOWN")
        _positive_int(stage["min_total_observations"], "MIN_TOTAL_OBSERVATIONS", 10**9)
        _positive_int(stage["min_observations_per_segment"], "MIN_SEGMENT_OBSERVATIONS", 10**9)
        uncertainty = _object(
            stage["uncertainty"], {"required", "method", "confidence_level"}, "UNCERTAINTY"
        )
        if uncertainty["required"] is not True:
            raise GateError("UNCERTAINTY_REQUIRED")
        _identifier(uncertainty["method"], "UNCERTAINTY_METHOD")
        confidence = _decimal(uncertainty["confidence_level"], "CONFIDENCE_LEVEL")
        if not (Decimal("0") < confidence < Decimal("1")):
            raise GateError("CONFIDENCE_LEVEL_INVALID")

        seen: set[tuple[str, str]] = set()
        for index, raw in enumerate(_array(stage["criteria"], "CRITERIA")):
            key = _validate_criterion(raw, f"CRITERION_{index}", metrics, set(segment_map))
            if key in seen:
                raise GateError("CRITERION_DUPLICATE")
            seen.add(key)
        expected = {
            (metric_id, segment_id)
            for metric_id, metric in metrics.items()
            for segment_id in metric["required_segments"]
        }
        if seen != expected:
            raise GateError("CRITERION_COVERAGE_INCOMPLETE")

        catastrophic_seen: set[tuple[str, str]] = set()
        for index, raw in enumerate(_array(
            stage["catastrophic_criteria"], "CATASTROPHIC_CRITERIA", allow_empty=True
        )):
            key = _validate_criterion(raw, f"CATASTROPHIC_{index}", metrics, set(segment_map))
            if key in catastrophic_seen:
                raise GateError("CATASTROPHIC_CRITERION_DUPLICATE")
            catastrophic_seen.add(key)

    tournament = _object(
        top["tournament"],
        {
            "independent_proposals", "primary_candidates", "fallback_candidates",
            "refinement_rounds", "additional_evidence_rounds", "max_design_minutes",
            "max_evaluation_minutes",
        },
        "TOURNAMENT",
    )
    if tournament["independent_proposals"] != 2 or isinstance(tournament["independent_proposals"], bool):
        raise GateError("INDEPENDENT_PROPOSAL_COUNT_INVALID")
    if tournament["primary_candidates"] != 1 or isinstance(tournament["primary_candidates"], bool):
        raise GateError("PRIMARY_CANDIDATE_COUNT_INVALID")
    _bounded_int(tournament["fallback_candidates"], "FALLBACK_CANDIDATES", 0, 1)
    _bounded_int(tournament["refinement_rounds"], "REFINEMENT_ROUNDS", 0, 1)
    _bounded_int(tournament["additional_evidence_rounds"], "EVIDENCE_ROUNDS", 0, 3)
    _positive_int(tournament["max_design_minutes"], "MAX_DESIGN_MINUTES", 1440)
    _positive_int(tournament["max_evaluation_minutes"], "MAX_EVALUATION_MINUTES", 10080)

    cycle = _object(
        top["cycle"],
        {"cycle_id", "primary_candidate_id", "fallback_candidate_id"},
        "CYCLE",
    )
    _identifier(cycle["cycle_id"], "CYCLE_ID")
    primary_candidate_id = _identifier(cycle["primary_candidate_id"], "PRIMARY_CANDIDATE_ID")
    fallback_candidate_id = cycle["fallback_candidate_id"]
    if tournament["fallback_candidates"] == 0:
        if fallback_candidate_id is not None:
            raise GateError("FALLBACK_CANDIDATE_CONTRACT_CONFLICT")
    else:
        fallback_candidate_id = _identifier(fallback_candidate_id, "FALLBACK_CANDIDATE_ID")
        if fallback_candidate_id == primary_candidate_id:
            raise GateError("CANDIDATE_ROLE_ID_CONFLICT")

    scope = _object(top["change_scope"], {"allowed_paths", "prohibited_paths"}, "CHANGE_SCOPE")
    allowed_paths = [
        _safe_relative_path(item, "ALLOWED_PATH")
        for item in _array(scope["allowed_paths"], "ALLOWED_PATHS")
    ]
    prohibited_paths = [
        _safe_relative_path(item, "PROHIBITED_PATH")
        for item in _array(scope["prohibited_paths"], "PROHIBITED_PATHS")
    ]
    if len(allowed_paths) != len(set(allowed_paths)):
        raise GateError("ALLOWED_PATH_DUPLICATE")
    if len(prohibited_paths) != len(set(prohibited_paths)):
        raise GateError("PROHIBITED_PATH_DUPLICATE")
    if any(_paths_overlap(allowed, prohibited) for allowed in allowed_paths for prohibited in prohibited_paths):
        raise GateError("CHANGE_SCOPE_PATH_CONFLICT")

    permissions = _object(
        top["permissions"], {"implementation", "commit", "push", "pull_request", "merge"}, "PERMISSIONS"
    )
    permission_enums = {
        "implementation": {"denied", "after_alignment_approve"},
        "commit": {"denied", "after_confirmation_pass"},
        "push": {"denied", "after_confirmation_pass"},
        "pull_request": {"denied", "after_confirmation_pass"},
        "merge": {"denied", "explicit_user_approval_after_heterogeneous_review"},
    }
    for name, allowed in permission_enums.items():
        if permissions[name] not in allowed:
            raise GateError("PERMISSION_VALUE_INVALID")
    permission_order = ("implementation", "commit", "push", "pull_request", "merge")
    for index, name in enumerate(permission_order):
        if permissions[name] != "denied" and any(
            permissions[dependency] == "denied" for dependency in permission_order[:index]
        ):
            raise GateError("PERMISSION_DEPENDENCY_CONFLICT")

    reporting = _object(top["reporting"], {"required_fields", "evidence_registry_required"}, "REPORTING")
    for item in _array(reporting["required_fields"], "REPORTING_FIELDS"):
        _identifier(item, "REPORTING_FIELD")
    if not isinstance(reporting["evidence_registry_required"], bool):
        raise GateError("REPORTING_EVIDENCE_FLAG_INVALID")

    rejected_ids: set[str] = set()
    for raw in _array(top["rejected_hypothesis_memory"], "REJECTED_MEMORY", allow_empty=True):
        item = _object(raw, {"id", "summary", "reason"}, "REJECTED_HYPOTHESIS")
        rejected_id = _identifier(item["id"], "REJECTED_HYPOTHESIS_ID")
        if rejected_id in rejected_ids:
            raise GateError("REJECTED_HYPOTHESIS_ID_DUPLICATE")
        rejected_ids.add(rejected_id)
        _text(item["summary"], "REJECTED_HYPOTHESIS_SUMMARY")
        _text(item["reason"], "REJECTED_HYPOTHESIS_REASON")
    unknown_fields: set[str] = set()
    for raw in _array(top["unresolved_unknowns"], "UNRESOLVED_UNKNOWNS", allow_empty=True):
        item = _object(raw, {"field", "impact", "blocking"}, "UNRESOLVED_UNKNOWN")
        unknown_field = _identifier(item["field"], "UNKNOWN_FIELD")
        if unknown_field in unknown_fields:
            raise GateError("UNKNOWN_FIELD_DUPLICATE")
        unknown_fields.add(unknown_field)
        _text(item["impact"], "UNKNOWN_IMPACT")
        if not isinstance(item["blocking"], bool):
            raise GateError("UNKNOWN_BLOCKING_FLAG_INVALID")
    return profile


def canonical_profile_bytes(profile: dict[str, Any]) -> bytes:
    validate_profile(profile)
    return json.dumps(
        profile,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def profile_digest(profile: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_profile_bytes(profile)).hexdigest()


def _validate_stats(value: Any, path: str) -> dict[str, Decimal]:
    stats_value = _object(value, {"estimate", "lower", "upper"}, path)
    parsed = {name: _decimal(stats_value[name], f"{path}_{name}") for name in stats_value}
    if not (parsed["lower"] <= parsed["estimate"] <= parsed["upper"]):
        raise GateError(f"{path}_INTERVAL_INVALID")
    return parsed


def validate_evidence(evidence: dict[str, Any], profile: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    value = _object(
        evidence,
        {
            "schema_version", "evidence_id", "stage", "profile_id", "profile_version",
            "profile_sha256", "cycle_id", "candidate_role", "evidence_round",
            "candidate_artifact", "baseline_artifact",
            "evaluation_target_id", "dataset_identity", "protocol_identity", "uncertainty",
            "total_observations", "cells",
        },
        "EVIDENCE",
    )
    if value["schema_version"] != SCHEMA_VERSION:
        raise GateError("EVIDENCE_SCHEMA_VERSION_UNSUPPORTED")
    _identifier(value["evidence_id"], "EVIDENCE_ID")
    if value["stage"] not in {"screening", "confirmation"}:
        raise GateError("EVIDENCE_STAGE_INVALID")
    _identifier(value["profile_id"], "EVIDENCE_PROFILE_ID")
    _identifier(value["profile_version"], "EVIDENCE_PROFILE_VERSION")
    if not isinstance(value["profile_sha256"], str) or not SHA256_RE.fullmatch(value["profile_sha256"]):
        raise GateError("PROFILE_SHA256_INVALID")
    _identifier(value["cycle_id"], "EVIDENCE_CYCLE_ID")
    if value["candidate_role"] not in {"primary", "fallback"}:
        raise GateError("CANDIDATE_ROLE_INVALID")
    _bounded_int(
        value["evidence_round"],
        "EVIDENCE_ROUND",
        0,
        profile["tournament"]["additional_evidence_rounds"],
    )
    candidate_artifact = _artifact_binding(value["candidate_artifact"], "CANDIDATE_ARTIFACT")
    baseline_artifact = _artifact_binding(value["baseline_artifact"], "EVIDENCE_BASELINE_ARTIFACT")
    candidate_id = candidate_artifact["artifact_id"]
    baseline_id = baseline_artifact["artifact_id"]
    if candidate_id == baseline_id or _artifact_locator(candidate_artifact) == _artifact_locator(baseline_artifact):
        raise GateError("CANDIDATE_EQUALS_BASELINE")
    _identifier(value["evaluation_target_id"], "EVIDENCE_TARGET_ID")
    dataset = _object(value["dataset_identity"], {"id", "version", "sha256"}, "DATASET_IDENTITY")
    _identifier(dataset["id"], "EVIDENCE_DATASET_ID")
    _identifier(dataset["version"], "EVIDENCE_DATASET_VERSION")
    if not isinstance(dataset["sha256"], str) or not SHA256_RE.fullmatch(dataset["sha256"]):
        raise GateError("EVIDENCE_DATASET_SHA256_INVALID")
    _identifier(value["protocol_identity"], "EVIDENCE_PROTOCOL_ID")
    uncertainty = _object(value["uncertainty"], {"method", "confidence_level"}, "EVIDENCE_UNCERTAINTY")
    _identifier(uncertainty["method"], "EVIDENCE_UNCERTAINTY_METHOD")
    confidence = _decimal(uncertainty["confidence_level"], "EVIDENCE_CONFIDENCE_LEVEL")
    if not (Decimal("0") < confidence < Decimal("1")):
        raise GateError("EVIDENCE_CONFIDENCE_LEVEL_INVALID")
    _positive_int(value["total_observations"], "EVIDENCE_TOTAL_OBSERVATIONS", 10**9)

    metric_ids = {metric["id"] for metric in profile["metrics"]}
    segment_ids = {segment["id"] for segment in profile["segments"]}
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in _array(value["cells"], "EVIDENCE_CELLS", allow_empty=True):
        cell = _object(
            raw,
            {
                "metric_id", "segment_id", "observations", "baseline_stats",
                "candidate_stats", "delta_stats",
            },
            "EVIDENCE_CELL",
        )
        metric_id = _identifier(cell["metric_id"], "CELL_METRIC_ID")
        segment_id = _identifier(cell["segment_id"], "CELL_SEGMENT_ID")
        if metric_id not in metric_ids or segment_id not in segment_ids:
            raise GateError("EVIDENCE_CELL_REFERENCE_UNKNOWN")
        key = (metric_id, segment_id)
        if key in cells:
            raise GateError("EVIDENCE_CELL_DUPLICATE")
        observations = _positive_int(cell["observations"], "CELL_OBSERVATIONS", 10**9)
        cells[key] = {
            "observations": observations,
            "baseline": _validate_stats(cell["baseline_stats"], "BASELINE_STATS"),
            "candidate": _validate_stats(cell["candidate_stats"], "CANDIDATE_STATS"),
            "delta": _validate_stats(cell["delta_stats"], "DELTA_STATS"),
        }
    return cells


def _blocked(profile_id: str | None, candidate_id: str | None, *reasons: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "profile_id": profile_id,
        "candidate_identity": candidate_id,
        "verdict": "BLOCKED",
        "reasons": sorted(set(reasons)),
        "metric_results": [],
        "fallback_allowed": False,
        "eligible_actions": {
            "implementation": False, "commit": False, "push": False,
            "pull_request": False, "merge": False,
        },
    }


def _stats_for_basis(cell: dict[str, Any], basis: str) -> dict[str, Decimal]:
    if basis == "candidate":
        return cell["candidate"]
    return cell["delta"]


def _criterion_pass(criterion: dict[str, Any], metric: dict[str, Any], cell: dict[str, Any]) -> bool:
    stats_value = _stats_for_basis(cell, criterion["basis"])
    params = criterion["parameters"]
    direction = metric["direction"]
    if direction == "maximize":
        return stats_value["lower"] >= _decimal(params["limit"], "LIMIT")
    if direction == "minimize":
        return stats_value["upper"] <= _decimal(params["limit"], "LIMIT")
    if direction == "target":
        target = _decimal(params["target"], "TARGET")
        tolerance = _decimal(params["tolerance"], "TOLERANCE")
        return stats_value["lower"] >= target - tolerance and stats_value["upper"] <= target + tolerance
    if direction == "threshold":
        point = stats_value[criterion["statistic"]]
        limit = _decimal(params["limit"], "LIMIT")
        return point >= limit if params["operator"] == "gte" else point <= limit
    lower = _decimal(params["lower"], "RANGE_LOWER")
    upper = _decimal(params["upper"], "RANGE_UPPER")
    return stats_value["lower"] >= lower and stats_value["upper"] <= upper


def _identity_reasons(profile: dict[str, Any], evidence: dict[str, Any], digest: str, stage: str) -> list[str]:
    reasons: list[str] = []
    if evidence["profile_id"] != profile["profile_id"]:
        reasons.append("PROFILE_ID_MISMATCH")
    if evidence["profile_version"] != profile["profile_version"]:
        reasons.append("PROFILE_VERSION_MISMATCH")
    if evidence["profile_sha256"] != digest:
        reasons.append("PROFILE_DIGEST_MISMATCH")
    if evidence["cycle_id"] != profile["cycle"]["cycle_id"]:
        reasons.append("CYCLE_ID_MISMATCH")
    if evidence["stage"] != stage:
        reasons.append("STAGE_MISMATCH")
    if evidence["baseline_artifact"] != profile["baseline"]:
        reasons.append("BASELINE_ARTIFACT_MISMATCH")
    role = evidence["candidate_role"]
    expected_candidate_id = profile["cycle"][f"{role}_candidate_id"]
    if expected_candidate_id is None:
        reasons.append("FALLBACK_NOT_CONFIGURED")
    elif evidence["candidate_artifact"]["artifact_id"] != expected_candidate_id:
        reasons.append("CANDIDATE_IDENTITY_MISMATCH")
    stage_profile = profile["stages"][stage]
    target_id = stage_profile["evaluation_target_id"]
    if evidence["evaluation_target_id"] != target_id:
        reasons.append("EVALUATION_TARGET_MISMATCH")
        return reasons
    target = next(item for item in profile["evaluation_targets"] if item["id"] == target_id)
    dataset = evidence["dataset_identity"]
    if (
        dataset["id"] != target["dataset_id"]
        or dataset["version"] != target["dataset_version"]
        or dataset["sha256"] != target["dataset_sha256"]
    ):
        reasons.append("DATASET_IDENTITY_MISMATCH")
    if evidence["protocol_identity"] != target["protocol_id"]:
        reasons.append("PROTOCOL_IDENTITY_MISMATCH")
    expected_uncertainty = stage_profile["uncertainty"]
    if (
        evidence["uncertainty"]["method"] != expected_uncertainty["method"]
        or evidence["uncertainty"]["confidence_level"] != expected_uncertainty["confidence_level"]
    ):
        reasons.append("UNCERTAINTY_IDENTITY_MISMATCH")
    return reasons


def _evaluate_stage(
    profile: dict[str, Any], evidence: dict[str, Any], digest: str, stage_name: str
) -> dict[str, Any]:
    candidate_artifact = evidence.get("candidate_artifact") if isinstance(evidence, dict) else None
    candidate_id = candidate_artifact.get("artifact_id") if isinstance(candidate_artifact, dict) else None
    try:
        cells = validate_evidence(evidence, profile)
    except GateError as exc:
        return _blocked(profile["profile_id"], candidate_id, exc.code)
    identity_reasons = _identity_reasons(profile, evidence, digest, stage_name)
    if identity_reasons:
        return _blocked(profile["profile_id"], candidate_id, *identity_reasons)

    stage = profile["stages"][stage_name]
    expected = {
        (metric["id"], segment_id)
        for metric in profile["metrics"]
        for segment_id in metric["required_segments"]
    }
    missing = sorted(expected - set(cells))
    extra = sorted(set(cells) - expected)
    if extra:
        return _blocked(
            profile["profile_id"],
            candidate_id,
            *(f"EXTRA_CELL:{metric}:{segment}" for metric, segment in extra),
        )
    insufficient: list[str] = []
    if evidence["total_observations"] < stage["min_total_observations"]:
        insufficient.append("TOTAL_OBSERVATIONS_INSUFFICIENT")
    if missing:
        insufficient.extend(f"MISSING_CELL:{metric}:{segment}" for metric, segment in missing)
    for key in sorted(expected & set(cells)):
        if cells[key]["observations"] < stage["min_observations_per_segment"]:
            insufficient.append(f"CELL_OBSERVATIONS_INSUFFICIENT:{key[0]}:{key[1]}")
    if insufficient:
        result = _blocked(profile["profile_id"], candidate_id)
        result["verdict"] = "INSUFFICIENT_EVIDENCE"
        result["reasons"] = insufficient
        return result

    metric_map = {metric["id"]: metric for metric in profile["metrics"]}
    metric_results: list[dict[str, Any]] = []
    catastrophic_failures: list[str] = []
    for criterion in stage["catastrophic_criteria"]:
        key = (criterion["metric_id"], criterion["segment_id"])
        if not _criterion_pass(criterion, metric_map[key[0]], cells[key]):
            catastrophic_failures.append(f"CATASTROPHIC_REGRESSION:{key[0]}:{key[1]}")

    failures: list[tuple[str, str, str]] = []
    for criterion in stage["criteria"]:
        key = (criterion["metric_id"], criterion["segment_id"])
        passed = _criterion_pass(criterion, metric_map[key[0]], cells[key])
        metric_results.append({
            "metric_id": key[0],
            "segment_id": key[1],
            "role": metric_map[key[0]]["role"],
            "passed": passed,
        })
        if not passed:
            failures.append((key[0], key[1], metric_map[key[0]]["role"]))
    metric_results.sort(key=lambda item: (item["metric_id"], item["segment_id"]))

    verdict = "PASS_TO_CONFIRMATION" if stage_name == "screening" else "PASS"
    reasons: list[str] = []
    fallback_allowed = False
    if catastrophic_failures:
        verdict = "FAIL"
        reasons = sorted(catastrophic_failures)
    elif failures:
        verdict = "FAIL"
        reasons = sorted(f"CRITERION_FAILED:{metric}:{segment}" for metric, segment, _role in failures)
        fallback_allowed = (
            all(role == "primary" for _metric, _segment, role in failures)
            and profile["tournament"]["fallback_candidates"] == 1
            and stage_name == "screening"
            and evidence["candidate_role"] == "primary"
        )

    permissions = profile["permissions"]
    confirmation_passed = verdict == "PASS" and stage_name == "confirmation"
    eligible_actions = {
        "implementation": False,
        "commit": confirmation_passed and permissions["commit"] == "after_confirmation_pass",
        "push": confirmation_passed and permissions["push"] == "after_confirmation_pass",
        "pull_request": confirmation_passed and permissions["pull_request"] == "after_confirmation_pass",
        "merge": False,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "profile_id": profile["profile_id"],
        "candidate_identity": candidate_id,
        "verdict": verdict,
        "reasons": reasons,
        "metric_results": metric_results,
        "fallback_allowed": fallback_allowed,
        "eligible_actions": eligible_actions,
    }


def evaluate(
    profile: dict[str, Any],
    screening_evidence: dict[str, Any],
    confirmation_evidence: dict[str, Any] | None = None,
    primary_screening_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        validate_profile(profile)
        digest = profile_digest(profile)
    except GateError as exc:
        return _blocked(None, None, exc.code)
    if profile["status"] == "example_only":
        return _blocked(profile["profile_id"], None, "EXAMPLE_PROFILE_NOT_EVALUABLE")
    if profile["unresolved_unknowns"]:
        return _blocked(profile["profile_id"], None, "UNRESOLVED_UNKNOWNS")

    screening = _evaluate_stage(profile, screening_evidence, digest, "screening")
    if screening["verdict"] == "BLOCKED":
        return screening
    requested_role = screening_evidence.get("candidate_role") if isinstance(screening_evidence, dict) else None
    if requested_role == "fallback":
        if primary_screening_evidence is None:
            return _blocked(profile["profile_id"], None, "FALLBACK_PRIMARY_EVIDENCE_REQUIRED")
        primary_result = _evaluate_stage(profile, primary_screening_evidence, digest, "screening")
        if primary_result["verdict"] != "FAIL" or not primary_result["fallback_allowed"]:
            return _blocked(profile["profile_id"], None, "FALLBACK_NOT_AUTHORIZED")
        if _artifact_locator(primary_screening_evidence["candidate_artifact"]) == _artifact_locator(
            screening_evidence.get("candidate_artifact", {})
        ):
            return _blocked(profile["profile_id"], None, "PRIMARY_FALLBACK_ARTIFACT_COLLISION")
    elif primary_screening_evidence is not None:
        return _blocked(profile["profile_id"], None, "PRIMARY_EVIDENCE_UNEXPECTED")

    if confirmation_evidence is None:
        return screening
    if screening["verdict"] != "PASS_TO_CONFIRMATION":
        return _blocked(
            profile["profile_id"],
            screening.get("candidate_identity"),
            "CONFIRMATION_NOT_ALLOWED",
        )
    confirmation = _evaluate_stage(profile, confirmation_evidence, digest, "confirmation")
    if confirmation["verdict"] == "BLOCKED":
        return confirmation
    if confirmation_evidence["candidate_artifact"] != screening_evidence["candidate_artifact"]:
        return _blocked(profile["profile_id"], None, "CONFIRMATION_CANDIDATE_ARTIFACT_MISMATCH")
    if confirmation_evidence["candidate_role"] != screening_evidence["candidate_role"]:
        return _blocked(profile["profile_id"], None, "CONFIRMATION_CANDIDATE_ROLE_MISMATCH")
    return confirmation


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False))


class _Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise GateError("CLI_INVALID")


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description="Read-only deterministic outcome gatekeeper")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_cmd = subparsers.add_parser("validate-profile")
    validate_cmd.add_argument("profile")
    digest_cmd = subparsers.add_parser("digest-profile")
    digest_cmd.add_argument("profile")
    evaluate_cmd = subparsers.add_parser("evaluate")
    evaluate_cmd.add_argument("--profile", required=True)
    evaluate_cmd.add_argument("--evidence", required=True)
    evaluate_cmd.add_argument("--confirmation-evidence")
    evaluate_cmd.add_argument("--primary-screening-evidence")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        if args.command == "validate-profile":
            profile = _read_json(args.profile)
            validate_profile(profile)
            _emit({
                "schema_version": SCHEMA_VERSION,
                "valid": True,
                "profile_id": profile["profile_id"],
                "profile_version": profile["profile_version"],
            })
            return 0
        if args.command == "digest-profile":
            profile = _read_json(args.profile)
            digest = profile_digest(profile)
            _emit({
                "schema_version": SCHEMA_VERSION,
                "profile_id": profile["profile_id"],
                "algorithm": "sha256",
                "digest": digest,
            })
            return 0
        profile = _read_json(args.profile)
        evidence = _read_json(args.evidence)
        confirmation = _read_json(args.confirmation_evidence) if args.confirmation_evidence else None
        primary_screening = (
            _read_json(args.primary_screening_evidence) if args.primary_screening_evidence else None
        )
        result = evaluate(profile, evidence, confirmation, primary_screening)
        _emit(result)
        return VERDICT_EXIT[result["verdict"]]
    except GateError as exc:
        result = _blocked(None, None, exc.code)
        _emit(result)
        return 40
    except Exception:
        result = _blocked(None, None, "UNEXPECTED_INPUT_ERROR")
        _emit(result)
        return 40


if __name__ == "__main__":
    raise SystemExit(main())
