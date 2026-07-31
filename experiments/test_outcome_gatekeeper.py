import ast
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "outcome_gatekeeper.py"
TEMPLATE_TOOL_PATH = ROOT / "template" / "multi-agent-workflow" / "tools" / "outcome_gatekeeper.py"
POKEMON_PROFILE = ROOT / "profiles" / "outcome" / "pokemon-ai.example.json"
TEMPLATE_POKEMON_PROFILE = (
    ROOT / "template" / "multi-agent-workflow" / "examples" / "app-profiles" / "pokemon-ai.example.json"
)
RAG_PROFILE = (
    ROOT / "template" / "multi-agent-workflow" / "examples" / "app-profiles" / "rag-quality.example.json"
)
CLAUDE_REVIEW_PACK = ROOT / "docs" / "pr-215-claude-heterogeneous-review-pack.md"

spec = importlib.util.spec_from_file_location("outcome_gatekeeper", TOOL_PATH)
gate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gate)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def active_profile(path=POKEMON_PROFILE):
    profile = load_json(path)
    profile["status"] = "active"
    profile["unresolved_unknowns"] = []
    profile["baseline"] = {"artifact_id": "baseline-v1", "immutable_ref": "commit-abc123"}
    return profile


def passing_stats(metric):
    direction = metric["direction"]
    if direction == "maximize":
        value = "0.6"
    elif direction in {"minimize", "threshold"}:
        value = "0"
    elif direction == "target":
        value = "0.8"
    else:
        value = "0.5"
    return {"estimate": value, "lower": value, "upper": value}


def decimal_text(value):
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def make_evidence(
    profile,
    stage="screening",
    candidate=None,
    role="primary",
    evidence_round=0,
    candidate_ref=None,
):
    stage_profile = profile["stages"][stage]
    target = next(
        value for value in profile["evaluation_targets"]
        if value["id"] == stage_profile["evaluation_target_id"]
    )
    cells = []
    for metric in profile["metrics"]:
        for segment_id in metric["required_segments"]:
            baseline_stats = {"estimate": "0.5", "lower": "0.5", "upper": "0.5"}
            candidate_stats = passing_stats(metric)
            delta_stats = {
                "estimate": decimal_text(Decimal(candidate_stats["estimate"]) - Decimal("0.5")),
                "lower": decimal_text(Decimal(candidate_stats["lower"]) - Decimal("0.5")),
                "upper": decimal_text(Decimal(candidate_stats["upper"]) - Decimal("0.5")),
            }
            cells.append({
                "metric_id": metric["id"],
                "segment_id": segment_id,
                "observations": stage_profile["min_observations_per_segment"],
                "baseline_stats": baseline_stats,
                "candidate_stats": candidate_stats,
                "delta_stats": delta_stats,
            })
    candidate_id = candidate or profile["cycle"][f"{role}_candidate_id"]
    candidate_ref = candidate_ref or f"immutable-{candidate_id}"
    return {
        "schema_version": "1.1",
        "evidence_id": f"{stage}-{role}-round-{evidence_round}",
        "stage": stage,
        "profile_id": profile["profile_id"],
        "profile_version": profile["profile_version"],
        "profile_sha256": gate.profile_digest(profile),
        "cycle_id": profile["cycle"]["cycle_id"],
        "candidate_role": role,
        "evidence_round": evidence_round,
        "candidate_artifact": {"artifact_id": candidate_id, "immutable_ref": candidate_ref},
        "baseline_artifact": copy.deepcopy(profile["baseline"]),
        "evaluation_target_id": target["id"],
        "dataset_identity": {
            "id": target["dataset_id"],
            "version": target["dataset_version"],
            "sha256": target["dataset_sha256"],
        },
        "protocol_identity": target["protocol_id"],
        "uncertainty": {
            "method": stage_profile["uncertainty"]["method"],
            "confidence_level": stage_profile["uncertainty"]["confidence_level"],
        },
        "total_observations": stage_profile["min_total_observations"],
        "cells": cells,
    }


def cell(evidence, metric_id, segment_id="overall"):
    return next(
        value for value in evidence["cells"]
        if value["metric_id"] == metric_id and value["segment_id"] == segment_id
    )


def set_candidate(evidence, metric_id, estimate, lower=None, upper=None, segment_id="overall"):
    target = cell(evidence, metric_id, segment_id)
    candidate_stats = {
        "estimate": estimate,
        "lower": lower if lower is not None else estimate,
        "upper": upper if upper is not None else estimate,
    }
    target["candidate_stats"] = candidate_stats
    baseline = target["baseline_stats"]
    target["delta_stats"] = {
        "estimate": decimal_text(Decimal(candidate_stats["estimate"]) - Decimal(baseline["estimate"])),
        "lower": decimal_text(Decimal(candidate_stats["lower"]) - Decimal(baseline["upper"])),
        "upper": decimal_text(Decimal(candidate_stats["upper"]) - Decimal(baseline["lower"])),
    }


def set_delta(evidence, metric_id, estimate, lower=None, upper=None, segment_id="overall"):
    target = cell(evidence, metric_id, segment_id)
    target["delta_stats"] = {
        "estimate": estimate,
        "lower": lower if lower is not None else estimate,
        "upper": upper if upper is not None else estimate,
    }


class SampleProfileTests(unittest.TestCase):
    def test_pokemon_examples_validate_and_are_semantically_identical(self):
        root_profile = load_json(POKEMON_PROFILE)
        template_profile = load_json(TEMPLATE_POKEMON_PROFILE)
        gate.validate_profile(root_profile)
        gate.validate_profile(template_profile)
        self.assertEqual(gate.profile_digest(root_profile), gate.profile_digest(template_profile))

    def test_rag_example_validates_and_is_non_pokemon_application(self):
        profile = load_json(RAG_PROFILE)
        gate.validate_profile(profile)
        self.assertEqual(profile["profile_id"], "rag.quality.example")
        self.assertIn("hallucination_rate", {metric["id"] for metric in profile["metrics"]})

    def test_shipped_examples_are_example_only(self):
        for path in (POKEMON_PROFILE, TEMPLATE_POKEMON_PROFILE, RAG_PROFILE):
            self.assertEqual(load_json(path)["status"], "example_only")

    def test_example_only_evaluation_is_blocked(self):
        profile = load_json(POKEMON_PROFILE)
        result = gate.evaluate(profile, {})
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("EXAMPLE_PROFILE_NOT_EVALUABLE", result["reasons"])

    def test_all_five_directions_are_represented(self):
        directions = {
            metric["direction"]
            for path in (POKEMON_PROFILE, RAG_PROFILE)
            for metric in load_json(path)["metrics"]
        }
        self.assertEqual(directions, {"maximize", "minimize", "target", "threshold", "range"})

    def test_pokemon_profile_includes_megastarmie_segment(self):
        profile = load_json(POKEMON_PROFILE)
        self.assertIn("opponent-megastarmie", {segment["id"] for segment in profile["segments"]})
        primary = next(metric for metric in profile["metrics"] if metric["role"] == "primary")
        self.assertIn("opponent-megastarmie", primary["required_segments"])


class ProfileValidationTests(unittest.TestCase):
    def setUp(self):
        self.profile = active_profile()

    def assert_invalid(self, mutate, code=None):
        profile = copy.deepcopy(self.profile)
        mutate(profile)
        with self.assertRaises(gate.GateError) as caught:
            gate.validate_profile(profile)
        if code:
            self.assertEqual(caught.exception.code, code)

    def test_missing_required_top_level_field(self):
        self.assert_invalid(lambda p: p.pop("objective"), "PROFILE_FIELDS_INVALID")

    def test_empty_profile_is_rejected(self):
        with self.assertRaises(gate.GateError) as caught:
            gate.validate_profile({})
        self.assertEqual(caught.exception.code, "PROFILE_FIELDS_INVALID")

    def test_unknown_top_level_field(self):
        self.assert_invalid(lambda p: p.update({"command": "touch marker"}), "PROFILE_FIELDS_INVALID")

    def test_primary_must_be_exactly_one(self):
        self.assert_invalid(lambda p: p["metrics"][1].update({"role": "primary"}), "METRIC_CARDINALITY_INVALID")

    def test_guardrail_is_required(self):
        self.assert_invalid(
            lambda p: p.update({"metrics": [p["metrics"][0]]}),
            "METRIC_CARDINALITY_INVALID",
        )

    def test_direction_enum_is_exact(self):
        self.assert_invalid(lambda p: p["metrics"][0].update({"direction": "higher"}), "METRIC_DIRECTION_INVALID")

    def test_criteria_cover_every_metric_segment(self):
        self.assert_invalid(lambda p: p["stages"]["screening"]["criteria"].pop(), "CRITERION_COVERAGE_INCOMPLETE")

    def test_catastrophic_criterion_must_use_metric_required_segment(self):
        def mutate(profile):
            criterion = copy.deepcopy(profile["stages"]["screening"]["catastrophic_criteria"][0])
            criterion["metric_id"] = "error_rate"
            profile["stages"]["screening"]["catastrophic_criteria"] = [criterion]

        self.assert_invalid(mutate, "CATASTROPHIC_0_METRIC_SEGMENT_NOT_REQUIRED")

    def test_refinement_and_fallback_are_bounded(self):
        self.assert_invalid(lambda p: p["tournament"].update({"refinement_rounds": 2}), "REFINEMENT_ROUNDS_INTEGER_INVALID")
        self.assert_invalid(lambda p: p["tournament"].update({"fallback_candidates": 2}), "FALLBACK_CANDIDATES_INTEGER_INVALID")

    def test_bool_is_not_an_integer(self):
        self.assert_invalid(lambda p: p["tournament"].update({"max_design_minutes": True}), "MAX_DESIGN_MINUTES_INTEGER_INVALID")

    def test_noncanonical_decimal_is_rejected(self):
        self.assert_invalid(
            lambda p: p["stages"]["screening"]["criteria"][0]["parameters"].update({"limit": "0.00"}),
            "CRITERION_0_parameters_limit_DECIMAL_INVALID",
        )

    def test_permission_cannot_be_broadened(self):
        self.assert_invalid(lambda p: p["permissions"].update({"merge": "automatic"}), "PERMISSION_VALUE_INVALID")

    def test_permission_dependencies_cannot_contradict_each_other(self):
        self.assert_invalid(
            lambda p: p["permissions"].update({"implementation": "denied"}),
            "PERMISSION_DEPENDENCY_CONFLICT",
        )
        self.assert_invalid(
            lambda p: p["permissions"].update({"commit": "denied"}),
            "PERMISSION_DEPENDENCY_CONFLICT",
        )

    def test_unsafe_profile_path_is_rejected(self):
        self.assert_invalid(lambda p: p["change_scope"]["allowed_paths"].append("../escape"), "ALLOWED_PATH_PATH_UNSAFE")

    def test_allowed_and_prohibited_paths_may_not_overlap(self):
        self.assert_invalid(
            lambda p: p["change_scope"]["prohibited_paths"].append(
                "experiments/agents/raging_bolt/main.py"
            ),
            "CHANGE_SCOPE_PATH_CONFLICT",
        )
        self.assert_invalid(
            lambda p: p["change_scope"]["prohibited_paths"].append("experiments/agents"),
            "CHANGE_SCOPE_PATH_CONFLICT",
        )
        self.assert_invalid(
            lambda p: p["change_scope"]["allowed_paths"].append("experiments"),
            "CHANGE_SCOPE_PATH_CONFLICT",
        )
        self.assert_invalid(
            lambda p: p["change_scope"]["prohibited_paths"].append(
                "EXPERIMENTS/AGENTS/RAGING_BOLT/MAIN.PY"
            ),
            "CHANGE_SCOPE_PATH_CONFLICT",
        )

    def test_artifact_binding_requires_exactly_one_immutable_locator(self):
        self.assert_invalid(
            lambda p: p["baseline"].update({"sha256": "a" * 64}),
            "BASELINE_FIELDS_INVALID",
        )
        self.assert_invalid(
            lambda p: p.update({"baseline": {"artifact_id": "baseline-v1"}}),
            "BASELINE_FIELDS_INVALID",
        )

    def test_cycle_fixes_primary_and_fallback_candidates(self):
        self.assert_invalid(
            lambda p: p["cycle"].update({"fallback_candidate_id": p["cycle"]["primary_candidate_id"]}),
            "CANDIDATE_ROLE_ID_CONFLICT",
        )
        self.assert_invalid(
            lambda p: p["tournament"].update({"fallback_candidates": 0}),
            "FALLBACK_CANDIDATE_CONTRACT_CONFLICT",
        )

    def test_unresolved_unknown_blocks_active_evaluation(self):
        self.profile["unresolved_unknowns"] = [
            {"field": "threshold", "impact": "Not fixed", "blocking": True}
        ]
        result = gate.evaluate(self.profile, make_evidence(self.profile))
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("UNRESOLVED_UNKNOWNS", result["reasons"])


class DeterministicEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.profile = active_profile()
        self.screening = make_evidence(self.profile, "screening")

    def fallback_evidence(self):
        primary_failure = copy.deepcopy(self.screening)
        set_candidate(primary_failure, "external_league_win_rate", "0.4")
        fallback_screening = make_evidence(self.profile, "screening", role="fallback")
        fallback_confirmation = make_evidence(self.profile, "confirmation", role="fallback")
        return primary_failure, fallback_screening, fallback_confirmation

    def test_screening_passes_to_confirmation(self):
        result = gate.evaluate(self.profile, self.screening)
        self.assertEqual(result["verdict"], "PASS_TO_CONFIRMATION")
        self.assertFalse(result["fallback_allowed"])

    def test_confirmation_pass_is_only_final_pass(self):
        confirmation = make_evidence(self.profile, "confirmation")
        result = gate.evaluate(self.profile, self.screening, confirmation)
        self.assertEqual(result["verdict"], "PASS")
        self.assertTrue(result["eligible_actions"]["commit"])
        self.assertTrue(result["eligible_actions"]["push"])
        self.assertTrue(result["eligible_actions"]["pull_request"])
        self.assertFalse(result["eligible_actions"]["merge"])

    def test_maximize_primary_failure_allows_one_fallback(self):
        set_candidate(self.screening, "external_league_win_rate", "0.4")
        result = gate.evaluate(self.profile, self.screening)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertTrue(result["fallback_allowed"])

    def test_minimize_guardrail_failure_does_not_allow_fallback(self):
        set_candidate(self.screening, "error_rate", "0.02")
        result = gate.evaluate(self.profile, self.screening)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertFalse(result["fallback_allowed"])

    def test_threshold_guardrail_boundary_and_failure(self):
        self.assertEqual(gate.evaluate(self.profile, self.screening)["verdict"], "PASS_TO_CONFIRMATION")
        set_candidate(self.screening, "illegal_action_rate", "0.01")
        self.assertEqual(gate.evaluate(self.profile, self.screening)["verdict"], "FAIL")

    def test_range_guardrail_failure(self):
        set_candidate(self.screening, "p95_decision_time", "0.6")
        self.assertEqual(gate.evaluate(self.profile, self.screening)["verdict"], "FAIL")

    def test_target_direction_pass_and_failure(self):
        profile = active_profile(RAG_PROFILE)
        screening = make_evidence(profile, "screening")
        self.assertEqual(gate.evaluate(profile, screening)["verdict"], "PASS_TO_CONFIRMATION")
        set_candidate(screening, "answer_correctness", "0.4")
        self.assertEqual(gate.evaluate(profile, screening)["verdict"], "FAIL")

    def test_catastrophic_segment_regression_fails_without_fallback(self):
        set_candidate(self.screening, "external_league_win_rate", "0.2", segment_id="opponent-lucario")
        result = gate.evaluate(self.profile, self.screening)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertFalse(result["fallback_allowed"])
        self.assertTrue(any(reason.startswith("CATASTROPHIC_REGRESSION") for reason in result["reasons"]))

    def test_missing_cell_is_insufficient_not_fail(self):
        self.screening["cells"].pop()
        result = gate.evaluate(self.profile, self.screening)
        self.assertEqual(result["verdict"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(result["fallback_allowed"])

    def test_observation_shortage_is_insufficient(self):
        self.screening["total_observations"] = 1
        result = gate.evaluate(self.profile, self.screening)
        self.assertEqual(result["verdict"], "INSUFFICIENT_EVIDENCE")

    def test_duplicate_cell_is_blocked(self):
        self.screening["cells"].append(copy.deepcopy(self.screening["cells"][0]))
        result = gate.evaluate(self.profile, self.screening)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("EVIDENCE_CELL_DUPLICATE", result["reasons"])

    def test_missing_external_delta_stats_is_blocked(self):
        cell(self.screening, "external_league_win_rate").pop("delta_stats")
        result = gate.evaluate(self.profile, self.screening)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("EVIDENCE_CELL_FIELDS_INVALID", result["reasons"])

    def test_external_delta_stats_are_used_without_gatekeeper_synthesis(self):
        set_candidate(self.screening, "external_league_win_rate", "0.4")
        set_delta(self.screening, "external_league_win_rate", "0.1")
        result = gate.evaluate(self.profile, self.screening)
        self.assertEqual(result["verdict"], "PASS_TO_CONFIRMATION")

    def test_extra_metric_segment_cell_is_blocked(self):
        extra = copy.deepcopy(cell(self.screening, "error_rate", "overall"))
        extra["segment_id"] = "opponent-lucario"
        self.screening["cells"].append(extra)
        result = gate.evaluate(self.profile, self.screening)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertTrue(any(reason.startswith("EXTRA_CELL") for reason in result["reasons"]))

    def test_profile_digest_mismatch_is_blocked(self):
        self.screening["profile_sha256"] = "f" * 64
        result = gate.evaluate(self.profile, self.screening)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("PROFILE_DIGEST_MISMATCH", result["reasons"])

    def test_dataset_and_protocol_mismatch_are_blocked(self):
        self.screening["dataset_identity"]["id"] = "other-dataset"
        self.screening["protocol_identity"] = "other-protocol"
        result = gate.evaluate(self.profile, self.screening)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("DATASET_IDENTITY_MISMATCH", result["reasons"])
        self.assertIn("PROTOCOL_IDENTITY_MISMATCH", result["reasons"])

    def test_uncertainty_method_and_confidence_must_match(self):
        self.screening["uncertainty"] = {"method": "other-method", "confidence_level": "0.9"}
        result = gate.evaluate(self.profile, self.screening)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("UNCERTAINTY_IDENTITY_MISMATCH", result["reasons"])

    def test_candidate_may_not_equal_baseline(self):
        self.screening["candidate_artifact"] = copy.deepcopy(self.screening["baseline_artifact"])
        result = gate.evaluate(self.profile, self.screening)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("CANDIDATE_EQUALS_BASELINE", result["reasons"])

    def test_baseline_artifact_must_match_profile(self):
        self.screening["baseline_artifact"]["immutable_ref"] = "other-baseline-ref"
        result = gate.evaluate(self.profile, self.screening)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("BASELINE_ARTIFACT_MISMATCH", result["reasons"])

    def test_cycle_candidate_role_and_round_are_fixed(self):
        cycle_mismatch = copy.deepcopy(self.screening)
        cycle_mismatch["cycle_id"] = "other-cycle"
        self.assertIn("CYCLE_ID_MISMATCH", gate.evaluate(self.profile, cycle_mismatch)["reasons"])

        candidate_mismatch = copy.deepcopy(self.screening)
        candidate_mismatch["candidate_artifact"]["artifact_id"] = "other-candidate"
        self.assertIn("CANDIDATE_IDENTITY_MISMATCH", gate.evaluate(self.profile, candidate_mismatch)["reasons"])

        round_overflow = copy.deepcopy(self.screening)
        round_overflow["evidence_round"] = self.profile["tournament"]["additional_evidence_rounds"] + 1
        self.assertIn("EVIDENCE_ROUND_INTEGER_INVALID", gate.evaluate(self.profile, round_overflow)["reasons"])

    def test_fallback_requires_authorizing_primary_failure(self):
        fallback = make_evidence(self.profile, role="fallback")
        blocked = gate.evaluate(self.profile, fallback)
        self.assertEqual(blocked["verdict"], "BLOCKED")
        self.assertIn("FALLBACK_PRIMARY_EVIDENCE_REQUIRED", blocked["reasons"])

        primary_failure = copy.deepcopy(self.screening)
        set_candidate(primary_failure, "external_league_win_rate", "0.4")
        authorized = gate.evaluate(self.profile, fallback, primary_screening_evidence=primary_failure)
        self.assertEqual(authorized["verdict"], "PASS_TO_CONFIRMATION")

        same_artifact = copy.deepcopy(fallback)
        same_artifact["candidate_artifact"]["immutable_ref"] = primary_failure["candidate_artifact"]["immutable_ref"]
        collision = gate.evaluate(self.profile, same_artifact, primary_screening_evidence=primary_failure)
        self.assertEqual(collision["verdict"], "BLOCKED")
        self.assertIn("PRIMARY_FALLBACK_ARTIFACT_COLLISION", collision["reasons"])

        malformed = copy.deepcopy(fallback)
        malformed.pop("candidate_artifact")
        malformed_result = gate.evaluate(self.profile, malformed, primary_screening_evidence=primary_failure)
        self.assertEqual(malformed_result["verdict"], "BLOCKED")
        self.assertIn("EVIDENCE_FIELDS_INVALID", malformed_result["reasons"])

    def test_fallback_end_to_end_confirmation_pass_releases_non_merge_actions(self):
        primary_failure, fallback_screening, fallback_confirmation = self.fallback_evidence()

        primary_result = gate.evaluate(self.profile, primary_failure)
        self.assertEqual(primary_result["verdict"], "FAIL")
        self.assertEqual(
            primary_result["reasons"],
            ["CRITERION_FAILED:external_league_win_rate:overall"],
        )
        self.assertTrue(primary_result["fallback_allowed"])
        self.assertTrue(all(
            result["passed"]
            for result in primary_result["metric_results"]
            if result["role"] == "guardrail"
        ))

        screening_result = gate.evaluate(
            self.profile,
            fallback_screening,
            primary_screening_evidence=primary_failure,
        )
        self.assertEqual(screening_result["verdict"], "PASS_TO_CONFIRMATION")
        self.assertEqual(
            fallback_confirmation["candidate_artifact"],
            fallback_screening["candidate_artifact"],
        )

        confirmation_result = gate.evaluate(
            self.profile,
            fallback_screening,
            fallback_confirmation,
            primary_screening_evidence=primary_failure,
        )
        self.assertEqual(confirmation_result["verdict"], "PASS")
        self.assertTrue(confirmation_result["eligible_actions"]["commit"])
        self.assertTrue(confirmation_result["eligible_actions"]["push"])
        self.assertTrue(confirmation_result["eligible_actions"]["pull_request"])
        self.assertFalse(confirmation_result["eligible_actions"]["merge"])

    def test_fallback_confirmation_rejects_primary_artifact(self):
        primary_failure, fallback_screening, confirmation = self.fallback_evidence()
        confirmation["candidate_artifact"] = copy.deepcopy(primary_failure["candidate_artifact"])
        result = gate.evaluate(
            self.profile,
            fallback_screening,
            confirmation,
            primary_screening_evidence=primary_failure,
        )
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("CANDIDATE_IDENTITY_MISMATCH", result["reasons"])

    def test_fallback_confirmation_rejects_primary_role(self):
        primary_failure, fallback_screening, confirmation = self.fallback_evidence()
        confirmation["candidate_role"] = "primary"
        result = gate.evaluate(
            self.profile,
            fallback_screening,
            confirmation,
            primary_screening_evidence=primary_failure,
        )
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("CANDIDATE_IDENTITY_MISMATCH", result["reasons"])

    def test_fallback_confirmation_rejects_cycle_change(self):
        primary_failure, fallback_screening, confirmation = self.fallback_evidence()
        confirmation["cycle_id"] = "other-cycle"
        result = gate.evaluate(
            self.profile,
            fallback_screening,
            confirmation,
            primary_screening_evidence=primary_failure,
        )
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("CYCLE_ID_MISMATCH", result["reasons"])

    def test_fallback_confirmation_rejects_candidate_artifact_change(self):
        primary_failure, fallback_screening, confirmation = self.fallback_evidence()
        confirmation["candidate_artifact"]["immutable_ref"] = "other-fallback-ref"
        result = gate.evaluate(
            self.profile,
            fallback_screening,
            confirmation,
            primary_screening_evidence=primary_failure,
        )
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("CONFIRMATION_CANDIDATE_ARTIFACT_MISMATCH", result["reasons"])

    def test_fallback_confirmation_rejects_baseline_change(self):
        primary_failure, fallback_screening, confirmation = self.fallback_evidence()
        confirmation["baseline_artifact"]["immutable_ref"] = "other-baseline-ref"
        result = gate.evaluate(
            self.profile,
            fallback_screening,
            confirmation,
            primary_screening_evidence=primary_failure,
        )
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("BASELINE_ARTIFACT_MISMATCH", result["reasons"])

    def test_fallback_confirmation_rejects_dataset_or_protocol_change(self):
        for field in ("dataset", "protocol"):
            with self.subTest(field=field):
                primary_failure, fallback_screening, confirmation = self.fallback_evidence()
                if field == "dataset":
                    confirmation["dataset_identity"]["id"] = "other-dataset"
                else:
                    confirmation["protocol_identity"] = "other-protocol"
                result = gate.evaluate(
                    self.profile,
                    fallback_screening,
                    confirmation,
                    primary_screening_evidence=primary_failure,
                )
                self.assertEqual(result["verdict"], "BLOCKED")
                expected_reason = (
                    "DATASET_IDENTITY_MISMATCH"
                    if field == "dataset"
                    else "PROTOCOL_IDENTITY_MISMATCH"
                )
                self.assertIn(expected_reason, result["reasons"])

    def test_fallback_confirmation_requires_primary_failure_evidence(self):
        _, fallback_screening, confirmation = self.fallback_evidence()
        result = gate.evaluate(self.profile, fallback_screening, confirmation)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("FALLBACK_PRIMARY_EVIDENCE_REQUIRED", result["reasons"])

    def test_confirmation_candidate_artifact_must_match_screening(self):
        confirmation = make_evidence(self.profile, "confirmation")
        confirmation["candidate_artifact"]["immutable_ref"] = "different-candidate-ref"
        result = gate.evaluate(self.profile, self.screening, confirmation)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("CONFIRMATION_CANDIDATE_ARTIFACT_MISMATCH", result["reasons"])

    def test_malformed_confirmation_is_blocked_without_exception(self):
        confirmation = make_evidence(self.profile, "confirmation")
        confirmation.pop("candidate_artifact")
        result = gate.evaluate(self.profile, self.screening, confirmation)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn("EVIDENCE_FIELDS_INVALID", result["reasons"])

    def test_sha256_artifact_bindings_are_supported(self):
        profile = active_profile()
        profile["baseline"] = {"artifact_id": "baseline-v1", "sha256": "a" * 64}
        screening = make_evidence(profile)
        confirmation = make_evidence(profile, "confirmation")
        candidate = {
            "artifact_id": profile["cycle"]["primary_candidate_id"],
            "sha256": "b" * 64,
        }
        screening["candidate_artifact"] = copy.deepcopy(candidate)
        confirmation["candidate_artifact"] = copy.deepcopy(candidate)
        result = gate.evaluate(profile, screening, confirmation)
        self.assertEqual(result["verdict"], "PASS")

    def test_invalid_permission_or_scope_contract_returns_blocked(self):
        permission_profile = copy.deepcopy(self.profile)
        permission_profile["permissions"]["implementation"] = "denied"
        permission_result = gate.evaluate(permission_profile, {})
        self.assertEqual(permission_result["verdict"], "BLOCKED")
        self.assertIn("PERMISSION_DEPENDENCY_CONFLICT", permission_result["reasons"])

        scope_profile = copy.deepcopy(self.profile)
        scope_profile["change_scope"]["prohibited_paths"].append(
            scope_profile["change_scope"]["allowed_paths"][0]
        )
        scope_result = gate.evaluate(scope_profile, {})
        self.assertEqual(scope_result["verdict"], "BLOCKED")
        self.assertIn("CHANGE_SCOPE_PATH_CONFLICT", scope_result["reasons"])

    def test_same_input_has_same_result(self):
        first = gate.evaluate(self.profile, self.screening)
        second = gate.evaluate(copy.deepcopy(self.profile), copy.deepcopy(self.screening))
        self.assertEqual(first, second)


class CanonicalAndCliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(TOOL_PATH), *map(str, args)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_digest_is_key_order_and_whitespace_independent(self):
        profile = load_json(POKEMON_PROFILE)
        reversed_profile = dict(reversed(list(profile.items())))
        self.assertEqual(gate.profile_digest(profile), gate.profile_digest(reversed_profile))

    def test_semantic_change_changes_digest(self):
        profile = load_json(POKEMON_PROFILE)
        other = copy.deepcopy(profile)
        other["objective"]["description"] += " changed"
        self.assertNotEqual(gate.profile_digest(profile), gate.profile_digest(other))

    def test_validate_and_digest_cli(self):
        validated = self.run_cli("validate-profile", POKEMON_PROFILE)
        self.assertEqual(validated.returncode, 0, validated.stderr)
        self.assertTrue(json.loads(validated.stdout)["valid"])
        digested = self.run_cli("digest-profile", POKEMON_PROFILE)
        self.assertEqual(digested.returncode, 0, digested.stderr)
        self.assertRegex(json.loads(digested.stdout)["digest"], r"^[0-9a-f]{64}$")

    def test_cli_evaluate_exit_codes(self):
        profile = active_profile()
        evidence = make_evidence(profile)
        confirmation = make_evidence(profile, "confirmation")
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            profile_path = td_path / "profile.json"
            evidence_path = td_path / "evidence.json"
            confirmation_path = td_path / "confirmation.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            confirmation_path.write_text(json.dumps(confirmation), encoding="utf-8")
            result = self.run_cli("evaluate", "--profile", profile_path, "--evidence", evidence_path)
            self.assertEqual(result.returncode, 10, result.stderr)
            self.assertEqual(json.loads(result.stdout)["verdict"], "PASS_TO_CONFIRMATION")

            result = self.run_cli(
                "evaluate", "--profile", profile_path, "--evidence", evidence_path,
                "--confirmation-evidence", confirmation_path,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["verdict"], "PASS")

            failed = copy.deepcopy(evidence)
            set_candidate(failed, "external_league_win_rate", "0.4")
            evidence_path.write_text(json.dumps(failed), encoding="utf-8")
            result = self.run_cli("evaluate", "--profile", profile_path, "--evidence", evidence_path)
            self.assertEqual(result.returncode, 20, result.stderr)
            self.assertEqual(json.loads(result.stdout)["verdict"], "FAIL")

            insufficient = copy.deepcopy(evidence)
            insufficient["cells"].pop()
            evidence_path.write_text(json.dumps(insufficient), encoding="utf-8")
            result = self.run_cli("evaluate", "--profile", profile_path, "--evidence", evidence_path)
            self.assertEqual(result.returncode, 30, result.stderr)
            self.assertEqual(json.loads(result.stdout)["verdict"], "INSUFFICIENT_EVIDENCE")

            blocked = copy.deepcopy(evidence)
            blocked["profile_sha256"] = "f" * 64
            evidence_path.write_text(json.dumps(blocked), encoding="utf-8")
            result = self.run_cli("evaluate", "--profile", profile_path, "--evidence", evidence_path)
            self.assertEqual(result.returncode, 40, result.stderr)
            self.assertEqual(json.loads(result.stdout)["verdict"], "BLOCKED")

    def test_duplicate_key_nan_and_bom_are_rejected(self):
        payloads = [
            b'{"schema_version":"1.0","schema_version":"1.0"}',
            b'{"value":NaN}',
            b'\xef\xbb\xbf{}',
        ]
        with tempfile.TemporaryDirectory() as td:
            for index, payload in enumerate(payloads):
                path = Path(td) / f"bad-{index}.json"
                path.write_bytes(payload)
                result = self.run_cli("validate-profile", path)
                self.assertEqual(result.returncode, 40)
                self.assertEqual(json.loads(result.stdout)["verdict"], "BLOCKED")

    def test_invalid_catastrophic_metric_segment_is_blocked_without_traceback(self):
        profile = active_profile()
        criterion = copy.deepcopy(profile["stages"]["screening"]["catastrophic_criteria"][0])
        criterion["metric_id"] = "error_rate"
        profile["stages"]["screening"]["catastrophic_criteria"] = [criterion]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            result = self.run_cli("validate-profile", path)
        self.assertEqual(result.returncode, 40)
        self.assertEqual(json.loads(result.stdout)["verdict"], "BLOCKED")
        self.assertNotIn("Traceback", result.stderr)

    def test_shell_metacharacters_are_data_and_no_marker_is_created(self):
        profile = load_json(POKEMON_PROFILE)
        marker_name = "outcome_gatekeeper_must_not_create_this_marker"
        marker = ROOT / marker_name
        profile["objective"]["description"] = f"; touch {marker_name}; $(whoami)"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            result = self.run_cli("validate-profile", path)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())

    def test_cli_is_read_only_for_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "profile.json"
            path.write_bytes(POKEMON_PROFILE.read_bytes())
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            result = self.run_cli("digest-profile", path)
            after = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(result.returncode, 0)
            self.assertEqual(before, after)
            self.assertEqual({item.name for item in Path(td).iterdir()}, {"profile.json"})

    def test_no_output_option_exists(self):
        result = self.run_cli("validate-profile", POKEMON_PROFILE, "--output", "result.json")
        self.assertEqual(result.returncode, 40)
        self.assertFalse((ROOT / "result.json").exists())


class SafetyAndTemplateTests(unittest.TestCase):
    def test_gatekeeper_has_no_dangerous_imports_or_calls(self):
        tree = ast.parse(TOOL_PATH.read_text(encoding="utf-8"))
        imported = set()
        calls = []
        direct_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
                    direct_calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)
        self.assertTrue({"subprocess", "socket", "urllib", "requests", "shutil"}.isdisjoint(imported))
        self.assertTrue({"eval", "exec", "compile", "open"}.isdisjoint(direct_calls))
        self.assertTrue({"system", "popen", "write_text", "write_bytes"}.isdisjoint(calls))

    def test_root_and_template_gatekeeper_are_text_identical_across_eol_policy(self):
        self.assertEqual(
            TOOL_PATH.read_text(encoding="utf-8").replace("\r\n", "\n"),
            TEMPLATE_TOOL_PATH.read_text(encoding="utf-8").replace("\r\n", "\n"),
        )

    def test_generic_docs_and_skill_are_text_identical_across_eol_policy(self):
        pairs = [
            (
                ROOT / "docs" / "agent-workflow" / "app-profile.md",
                ROOT / "template" / "multi-agent-workflow" / "docs" / "agent-workflow" / "app-profile.md",
            ),
            (
                ROOT / "docs" / "agent-workflow" / "outcome-improvement-cycle.md",
                ROOT / "template" / "multi-agent-workflow" / "docs" / "agent-workflow" / "outcome-improvement-cycle.md",
            ),
            (
                ROOT / ".claude" / "skills" / "outcome-improvement-cycle" / "SKILL.md",
                ROOT / "template" / "multi-agent-workflow" / ".claude" / "skills" / "outcome-improvement-cycle" / "SKILL.md",
            ),
        ]
        for source, mirror in pairs:
            self.assertEqual(
                source.read_text(encoding="utf-8").replace("\r\n", "\n"),
                mirror.read_text(encoding="utf-8").replace("\r\n", "\n"),
                source.name,
            )

    def test_claude_skill_frontmatter_and_entrypoints(self):
        skill = (ROOT / ".claude" / "skills" / "outcome-improvement-cycle" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertTrue(skill.startswith("---\nname: outcome-improvement-cycle\n"))
        self.assertIn("user-invocable: true", skill)
        self.assertIn("docs/agent-workflow/outcome-improvement-cycle.md", skill)
        self.assertIn("tools/outcome_gatekeeper.py", skill)

    def test_rule_document_references_exist(self):
        for path in (
            ROOT / "docs" / "agent-workflow" / "outcome-improvement-cycle.md",
            ROOT / "docs" / "agent-workflow" / "app-profile.md",
            POKEMON_PROFILE,
        ):
            self.assertTrue(path.is_file(), path)

    def test_github_actions_runs_gatekeeper_and_template_tests(self):
        workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        marker = "  outcome-workflow-linux:\n"
        self.assertEqual(workflow.count(marker), 1)
        outcome_job = workflow.split(marker, 1)[1]
        self.assertIn("runs-on: ubuntu-latest", outcome_job)
        self.assertNotIn("needs: test", outcome_job)
        self.assertIn("python -B -m unittest experiments.test_outcome_gatekeeper -v", outcome_job)
        self.assertIn(
            'python -B -m unittest discover -s experiments -p "test_verify_workflow_template.py" -v',
            outcome_job,
        )
        self.assertIn(
            "python -B template/multi-agent-workflow/tools/verify_workflow_template.py source-integrity",
            outcome_job,
        )

    def test_claude_review_pack_requires_independent_diff_review(self):
        pack = CLAUDE_REVIEW_PACK.read_text(encoding="utf-8")
        for heading in (
            "## PR purpose and scope",
            "## Architecture to verify",
            "## Trust boundary to verify",
            "## Schema v1.1 review map",
            "## State transition to verify",
            "## Previous findings and claimed changes to inspect",
            "## Known limitations",
            "## Read-only review checklist",
            "## Exact review and test commands",
        ):
            self.assertIn(heading, pack)
        self.assertIn("not review evidence", pack)
        self.assertIn("Claude must inspect the actual PR diff", pack)
        self.assertIn("A prior Codex audit result is not evidence", pack)
        self.assertIn("Review must remain read-only", pack)


if __name__ == "__main__":
    unittest.main()
