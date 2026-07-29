"""Unit tests for PR0-A.1 Parameter Contract correctness."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest


EXPERIMENTS_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(EXPERIMENTS_DIR, ".."))
sys.path.insert(0, EXPERIMENTS_DIR)

import audit_parameter_contract as audit


SYNTHETIC_SOURCE = """
class Policy:
    def p(self, key, default=0):
        return default

    def evaluate_state(self):
        return self.p("dead_eval", 10)

    def _score_option(self, flag=False):
        score = 0
        score += 25
        score += self.p("live_score", 20)
        score += self.p("code_default_only", 3)
        score += self.p("conflicting_default", 1)
        score += self.p("conflicting_default", 2)
        score += self.p("ternary_a" if flag else "ternary_b", 5)
        if self.p("disabled_gate", 0):
            score += self.p("disabled_weight", 7)
        if self.p("new_path", 0):
            return score
        score += self.p("legacy_weight", 9)
        return score * 2

    def choose(self):
        ignored = self.evaluate_state()
        return self._score_option()
"""


SYNTHETIC_PARAMS = {
    "dead_eval": 10,
    "live_score": 20,
    "ternary_a": 5,
    "ternary_b": 5,
    "disabled_gate": 0,
    "disabled_weight": 7,
    "new_path": 1,
    "legacy_weight": 9,
    "unused_param": 123,
}


class ParameterContractUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = audit.build_audit(SYNTHETIC_SOURCE, SYNTHETIC_PARAMS)
        cls.contract = cls.result["contract"]

    def test_ternary_parameter_keys_are_concrete(self):
        self.assertIn("ternary_a", self.contract)
        self.assertIn("ternary_b", self.contract)
        self.assertNotIn("<dynamic-key", " ".join(self.contract))

    def test_dead_scoring_result_is_shadowed(self):
        item = self.contract["dead_eval"]
        self.assertEqual("SHADOWED", item["status"])
        self.assertEqual(
            "NO_OBSERVED_DECISION_EFFECT", item["decision_effect"]
        )
        self.assertEqual(
            "enclosing_scoring_result_is_not_consumed", item["shadow_reason"]
        )

    def test_live_and_unused_parameters_are_separated(self):
        self.assertEqual(
            "REFERENCED_UNVERIFIED",
            self.contract["live_score"]["status"],
        )
        self.assertEqual("UNUSED", self.contract["unused_param"]["status"])

    def test_direct_guard_and_early_return_guard_are_evaluated(self):
        self.assertEqual(
            "DISABLED_BY_CURRENT_CONFIG",
            self.contract["disabled_weight"]["current_config_reachability"],
        )
        self.assertEqual(
            "DISABLED_BY_CURRENT_CONFIG",
            self.contract["legacy_weight"]["current_config_reachability"],
        )
        legacy_guards = self.contract["legacy_weight"]["site_reachability"][0][
            "guards"
        ]
        self.assertTrue(
            any(guard["source"] == "post_early_return" for guard in legacy_guards)
        )

    def test_contract_schema_fields_are_explicit(self):
        item = self.contract["live_score"]
        required = {
            "name",
            "status",
            "classifications",
            "flags",
            "type",
            "unit",
            "min",
            "max",
            "used_by",
            "runtime_override",
            "runtime_override_api_supported",
            "runtime_override_numeric_family_compatible",
            "runtime_override_declared_type_preserved",
            "description",
            "decision_effect",
            "runtime_decision_effect_verified",
            "activation_evidence",
            "current_config_reachability",
        }
        self.assertTrue(required.issubset(item))
        self.assertTrue(item["runtime_override"])
        self.assertTrue(item["runtime_override_api_supported"])
        self.assertTrue(item["runtime_override_numeric_family_compatible"])
        self.assertFalse(item["runtime_override_declared_type_preserved"])
        self.assertIsNone(item["unit"])
        self.assertIsNone(item["min"])
        self.assertIsNone(item["max"])
        self.assertIsNone(item["description"])

    def test_code_default_is_not_exposed_to_live_tuning(self):
        item = self.contract["code_default_only"]
        self.assertFalse(item["runtime_override"])
        self.assertFalse(item["runtime_override_api_supported"])
        self.assertIsNone(
            item["runtime_override_numeric_family_compatible"]
        )
        self.assertIsNone(item["runtime_override_declared_type_preserved"])

    def test_conflicting_defaults_are_flagged_not_assumed_shadowed(self):
        item = self.contract["conflicting_default"]
        self.assertEqual("REFERENCED_UNVERIFIED", item["status"])
        self.assertIn("CONFLICTING_CODE_DEFAULTS", item["flags"])

    def test_hardcoded_inventory_captures_expressions_but_not_param_default(self):
        values = {
            entry["value"]
            for entry in self.result["hardcoded"]
            if entry["method"] == "_score_option"
        }
        self.assertTrue({0, 25, 2}.issubset(values))
        self.assertNotIn(20, values)
        self.assertNotIn(7, values)
        self.assertNotIn(9, values)

    def test_artifact_document_is_versioned_and_round_trips(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audit.write_artifacts(
                SYNTHETIC_SOURCE, SYNTHETIC_PARAMS, self.result, temp_dir
            )
            with open(
                os.path.join(temp_dir, "parameter_contract.json"),
                encoding="utf-8",
            ) as f:
                document = json.load(f)
            self.assertEqual(audit.CONTRACT_SCHEMA_VERSION, document["schema_version"])
            self.assertIn("parameters", document)
            self.assertEqual(
                "SHADOWED", document["parameters"]["dead_eval"]["status"]
            )
            self.assertEqual(
                [],
                audit.find_artifact_mismatches(
                    SYNTHETIC_SOURCE,
                    SYNTHETIC_PARAMS,
                    self.result,
                    temp_dir,
                ),
            )
            with open(
                os.path.join(temp_dir, "parameter_audit_report.md"),
                "a",
                encoding="utf-8",
            ) as f:
                f.write("changed\n")
            self.assertIn(
                "parameter_audit_report.md: differs",
                audit.find_artifact_mismatches(
                    SYNTHETIC_SOURCE,
                    SYNTHETIC_PARAMS,
                    self.result,
                    temp_dir,
                ),
            )


class RealRagingBoltContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contract_path = os.path.join(
            audit.OUT_DIR, "parameter_contract.json"
        )
        with open(contract_path, encoding="utf-8") as f:
            cls.checked_document = json.load(f)
        source_ref = cls.checked_document["source"]["source_commit"]
        try:
            source, params, provenance = audit.load_inputs(source_ref)
        except subprocess.CalledProcessError:
            # actions/checkout is shallow by default. If the pinned source
            # commit is not present, the current files are acceptable only
            # when their raw hashes exactly match the pinned artifact.
            source, params, worktree_provenance = audit.load_inputs()
            pinned = cls.checked_document["source"]
            for hash_name in (
                "main_py_sha256",
                "params_json_raw_sha256",
                "effective_params_sha256",
            ):
                if worktree_provenance[hash_name] != pinned[hash_name]:
                    raise AssertionError(
                        f"shallow checkout source mismatch: {hash_name}"
                    )
            provenance = {
                key: pinned[key]
                for key in (
                    "source_ref_requested",
                    "source_commit",
                    "main_py_sha256",
                    "params_json_raw_sha256",
                    "effective_params_sha256",
                )
            }
        cls.source = source
        cls.params = params
        cls.provenance = provenance
        cls.result = audit.build_audit(source, params)
        cls.contract = cls.result["contract"]

    def test_eval_state_parameters_are_not_reported_decision_active(self):
        eval_items = {
            key: item
            for key, item in self.contract.items()
            if key.startswith("eval_")
        }
        self.assertGreaterEqual(len(eval_items), 19)
        self.assertTrue(
            all(item["status"] == "SHADOWED" for item in eval_items.values())
        )
        self.assertTrue(
            all(
                item["decision_effect"] == "NO_OBSERVED_DECISION_EFFECT"
                for item in eval_items.values()
            )
        )

    def test_search_evaluator_parameters_are_not_overclaimed_active(self):
        self.assertEqual(
            "REFERENCED_UNVERIFIED",
            self.contract["se_prize_taken"]["status"],
        )
        self.assertEqual(
            "STATICALLY_DECISION_RELEVANT",
            self.contract["se_prize_taken"]["decision_effect"],
        )
        self.assertFalse(
            self.contract["se_prize_taken"][
                "runtime_decision_effect_verified"
            ]
        )

    def test_current_config_disabled_paths_are_visible(self):
        self.assertEqual(
            "DISABLED_BY_CURRENT_CONFIG",
            self.contract["value_model_weight"]["current_config_reachability"],
        )
        self.assertEqual(
            "DISABLED_BY_CURRENT_CONFIG",
            self.contract["engine_search_samples"][
                "current_config_reachability"
            ],
        )

    def test_live_tuning_capability_and_type_risks_are_separate(self):
        integer = self.contract["score_supporter_crispin"]
        self.assertTrue(integer["runtime_override_api_supported"])
        self.assertTrue(
            integer["runtime_override_numeric_family_compatible"]
        )
        self.assertFalse(
            integer["runtime_override_declared_type_preserved"]
        )
        self.assertIn(
            "RUNTIME_OVERRIDE_DECLARED_TYPE_NOT_ENFORCED", integer["flags"]
        )

        number = self.contract["ucb1_exploration_c"]
        self.assertTrue(
            number["runtime_override_numeric_family_compatible"]
        )
        self.assertTrue(number["runtime_override_declared_type_preserved"])

        boolean = self.contract["use_value_model"]
        self.assertTrue(boolean["runtime_override_api_supported"])
        self.assertFalse(
            boolean["runtime_override_numeric_family_compatible"]
        )
        self.assertFalse(
            boolean["runtime_override_declared_type_preserved"]
        )
        self.assertIn(
            "RUNTIME_OVERRIDE_NUMERIC_FAMILY_MISMATCH", boolean["flags"]
        )

    def test_checked_artifacts_are_exactly_regenerable(self):
        self.assertIsNotNone(self.provenance["source_commit"])
        self.assertEqual(
            self.provenance["source_commit"],
            self.checked_document["source"]["source_commit"],
        )
        self.assertIn(
            "params_json_raw_sha256", self.checked_document["source"]
        )
        self.assertIn(
            "effective_params_sha256", self.checked_document["source"]
        )
        self.assertEqual(
            [],
            audit.find_artifact_mismatches(
                self.source,
                self.params,
                self.result,
                provenance=self.provenance,
            ),
        )


if __name__ == "__main__":
    unittest.main()
