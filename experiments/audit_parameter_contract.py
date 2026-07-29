"""
PR0-A.1: Parameter Contract correctness audit (no policy changes).

The audit is deliberately static: it reads the Raging Bolt agent and its
params.json, but never imports or executes the agent.  It distinguishes:

* code reference: a self.p("key", default) call exists;
* decision effect: the enclosing scoring result is observed by a caller;
* current-config reachability: known guards enable/disable the call today.

Those are not interchangeable.  In particular, a parameter referenced by a
dead scoring result must not be reported as decision-active.

Usage:
  python experiments/audit_parameter_contract.py
"""
from __future__ import annotations

import ast
import argparse
import hashlib
import json
import os
import re
import subprocess
from collections import defaultdict


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAIN_PY = os.path.join(
    REPO_ROOT, "experiments", "agents", "raging_bolt", "main.py"
)
PARAMS_JSON = os.path.join(
    REPO_ROOT, "experiments", "agents", "raging_bolt", "params.json"
)
OUT_DIR = os.path.join(
    REPO_ROOT, "experiments", "agents", "raging_bolt", "audit"
)

CONTRACT_SCHEMA_VERSION = 3
CONTRACT_STATUSES = (
    "ACTIVE",
    "REFERENCED_UNVERIFIED",
    "EXPERIMENTAL",
    "DEPRECATED",
    "UNUSED",
    "SHADOWED",
)
ARTIFACT_FILENAMES = (
    "parameter_contract.json",
    "unused_parameter_list.json",
    "hardcoded_score_inventory.json",
    "parameter_audit_report.md",
)


def load_params(path=PARAMS_JSON):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.pop("_comment", None)
    return data


def load_inputs(source_ref=None):
    """Load inputs plus immutable provenance for the analyzed source."""
    if source_ref is None:
        with open(MAIN_PY, "rb") as f:
            source_bytes = f.read()
        with open(PARAMS_JSON, "rb") as f:
            params_bytes = f.read()
        resolved_commit = None
        requested_ref = "worktree"
    else:
        resolved = subprocess.run(
            ["git", "rev-parse", "--verify", f"{source_ref}^{{commit}}"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        resolved_commit = resolved.stdout.strip()
        requested_ref = source_ref

        main_rel = os.path.relpath(MAIN_PY, REPO_ROOT).replace("\\", "/")
        params_rel = os.path.relpath(PARAMS_JSON, REPO_ROOT).replace("\\", "/")

        def git_show(relative_path):
            result = subprocess.run(
                ["git", "show", f"{resolved_commit}:{relative_path}"],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
            )
            return result.stdout

        source_bytes = git_show(main_rel)
        params_bytes = git_show(params_rel)

    source = source_bytes.decode("utf-8")
    params = json.loads(params_bytes.decode("utf-8"))
    params.pop("_comment", None)
    effective_params_text = json.dumps(
        params, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    provenance = {
        "source_ref_requested": requested_ref,
        "source_commit": resolved_commit,
        "main_py_sha256": _sha256_bytes(source_bytes),
        "params_json_raw_sha256": _sha256_bytes(params_bytes),
        "effective_params_sha256": _sha256_text(effective_params_text),
    }
    return source, params, provenance


def _literal_keys(node):
    """Return every literal key represented by a simple key expression."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _literal_keys(node.body) + _literal_keys(node.orelse)
    return []


def _constant_value(node):
    if isinstance(node, ast.Constant):
        return node.value, True
    try:
        return ast.literal_eval(node), True
    except (ValueError, TypeError):
        return None, False


def _self_p_spec(node):
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "p"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        and node.args
    ):
        return None

    keys = _literal_keys(node.args[0])
    default_node = node.args[1] if len(node.args) >= 2 else None
    if default_node is None:
        default_value, default_is_static, default_repr = None, True, None
    else:
        default_value, default_is_static = _constant_value(default_node)
        default_repr = (
            repr(default_value)
            if default_is_static
            else ast.dump(default_node, include_attributes=False)
        )
    return {
        "keys": keys,
        "default_value": default_value,
        "default_repr": default_repr,
        "default_is_dynamic": not default_is_static,
    }


def _invert_guard(guard):
    inverse = dict(guard)
    inverse["expected_truthy"] = not guard["expected_truthy"]
    return inverse


def _guard_from_test(node):
    """Recognize `if self.p(...)` and `if not self.p(...)` guards."""
    spec = _self_p_spec(node)
    if spec and len(spec["keys"]) == 1:
        return {
            "key": spec["keys"][0],
            "expected_truthy": True,
            "default_value": spec["default_value"],
            "default_is_dynamic": spec["default_is_dynamic"],
            "source": "if_guard",
        }
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        inner = _guard_from_test(node.operand)
        if inner:
            return _invert_guard(inner)
    return None


def _block_always_terminates(statements):
    if not statements:
        return False
    last = statements[-1]
    if isinstance(last, (ast.Return, ast.Raise)):
        return True
    if isinstance(last, ast.If) and last.orelse:
        return (
            _block_always_terminates(last.body)
            and _block_always_terminates(last.orelse)
        )
    return False


def find_self_p_calls(source):
    """Extract self.p call sites with function and static guard context."""
    tree = ast.parse(source)
    calls = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.function_stack = []
            self.guard_stack = []

        def visit_FunctionDef(self, node):
            self.function_stack.append(node.name)
            for statement in node.body:
                self.visit(statement)
            self.function_stack.pop()

        def visit_If(self, node):
            # The gate parameter itself is evaluated before its own guard.
            self.visit(node.test)
            guard = _guard_from_test(node.test)
            if guard:
                self.guard_stack.append(guard)
            for statement in node.body:
                self.visit(statement)
            if guard:
                self.guard_stack.pop()

            if guard:
                self.guard_stack.append(_invert_guard(guard))
            for statement in node.orelse:
                self.visit(statement)
            if guard:
                self.guard_stack.pop()

        def visit_Call(self, node):
            spec = _self_p_spec(node)
            if spec:
                keys = spec["keys"] or [f"<dynamic-key L{node.lineno}>"]
                for key in keys:
                    calls.append(
                        {
                            "key": key,
                            "default_value": spec["default_value"],
                            "default_repr": spec["default_repr"],
                            "default_is_dynamic": spec["default_is_dynamic"],
                            "lineno": node.lineno,
                            "function": (
                                self.function_stack[-1]
                                if self.function_stack
                                else "<module>"
                            ),
                            "guards": [dict(g) for g in self.guard_stack],
                        }
                    )
            self.generic_visit(node)

    Visitor().visit(tree)

    # Recognize a common early-return gate:
    #   if self.p("new_path", 0):
    #       return ...
    #   ... legacy path ...
    # Calls after the if are guarded by NOT new_path even without an `else`.
    for function in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        for statement in function.body:
            if not isinstance(statement, ast.If) or statement.orelse:
                continue
            guard = _guard_from_test(statement.test)
            if not guard or not _block_always_terminates(statement.body):
                continue
            after_guard = _invert_guard(guard)
            after_guard["source"] = "post_early_return"
            end_line = getattr(statement, "end_lineno", statement.lineno)
            for call in calls:
                if call["function"] == function.name and call["lineno"] > end_line:
                    if after_guard not in call["guards"]:
                        call["guards"].append(dict(after_guard))

    return calls


def find_eval_feature_weights(source):
    """Extract concrete defaults hidden behind the dynamic se_* lookup."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name)
            and target.id == "_EVAL_FEATURE_WEIGHTS"
            for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        result = {}
        for key_node, value_node in zip(node.value.keys, node.value.values):
            key, key_ok = _constant_value(key_node)
            value, value_ok = _constant_value(value_node)
            if key_ok and value_ok and isinstance(key, str):
                result[key] = value
        return result, node.lineno
    return {}, None


def find_method_return_usage(source):
    """Describe whether self.method() return values are consumed by callers."""
    tree = ast.parse(source)
    parent = {}
    enclosing_function = {}

    def index(node, current_function=None):
        if isinstance(node, ast.FunctionDef):
            current_function = node
        enclosing_function[node] = current_function
        for child in ast.iter_child_nodes(node):
            parent[child] = node
            index(child, current_function)

    index(tree)
    loads_by_function = defaultdict(set)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            function = enclosing_function.get(node)
            if function:
                loads_by_function[function.name].add(node.id)

    usage = defaultdict(list)
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ):
            continue
        method = node.func.attr
        caller = enclosing_function.get(node)
        direct_parent = parent.get(node)
        if (
            isinstance(direct_parent, ast.Assign)
            and direct_parent.value is node
            and all(isinstance(target, ast.Name) for target in direct_parent.targets)
        ):
            target_names = [target.id for target in direct_parent.targets]
            is_loaded = any(
                target in loads_by_function.get(caller.name if caller else "", set())
                for target in target_names
            )
            kind = "assigned_and_read" if is_loaded else "assigned_but_never_read"
        elif isinstance(direct_parent, ast.Expr):
            kind = "discarded"
        else:
            kind = "consumed"
        usage[method].append(
            {
                "caller": caller.name if caller else "<module>",
                "lineno": node.lineno,
                "usage": kind,
            }
        )
    return dict(usage)


def find_dead_scoring_methods(source):
    usage = find_method_return_usage(source)

    def scoring_method(name):
        return (
            name == "evaluate_state"
            or name.startswith("_score_")
            or name.startswith("_eval_")
            or name == "_estimate_action_impact"
        )

    dead = {}
    for method, sites in usage.items():
        if not scoring_method(method):
            continue
        if sites and all(
            site["usage"] in ("assigned_but_never_read", "discarded")
            for site in sites
        ):
            dead[method] = sites
    return dead


def find_hardcoded_numeric_literals(source):
    """Inventory numeric literals in scoring methods, excluding self.p calls.

    This is intentionally a review inventory, not a claim that every literal
    is a score. `context_kind` and `expression` let a reviewer distinguish
    score weights from structural constants and thresholds.
    """
    tree = ast.parse(source)
    parent = {}

    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    def scoring_method(name):
        return (
            name == "evaluate_state"
            or name.startswith("_score_")
            or name.startswith("_eval_")
            or name == "_estimate_action_impact"
        )

    def inside_self_p(node):
        cursor = node
        while cursor in parent:
            cursor = parent[cursor]
            if _self_p_spec(cursor):
                return True
            if isinstance(cursor, ast.stmt):
                return False
        return False

    def nearest_statement(node):
        cursor = node
        while cursor in parent:
            cursor = parent[cursor]
            if isinstance(cursor, ast.stmt):
                return cursor
        return None

    items = []
    seen = set()
    for function in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        if not scoring_method(function.name):
            continue
        for node in ast.walk(function):
            if not (
                isinstance(node, ast.Constant)
                and isinstance(node.value, (int, float))
                and not isinstance(node.value, bool)
            ):
                continue
            if inside_self_p(node):
                continue

            value = node.value
            value_node = node
            direct_parent = parent.get(node)
            if isinstance(direct_parent, ast.UnaryOp) and isinstance(
                direct_parent.op, ast.USub
            ):
                value = -value
                value_node = direct_parent

            statement = nearest_statement(value_node)
            if statement is None:
                continue
            key = (
                function.name,
                value_node.lineno,
                getattr(value_node, "col_offset", -1),
                value,
            )
            if key in seen:
                continue
            seen.add(key)
            expression = ast.get_source_segment(source, statement) or ""
            items.append(
                {
                    "method": function.name,
                    "lineno": value_node.lineno,
                    "value": value,
                    "classification": "UNCLASSIFIED_NUMERIC_LITERAL",
                    "context_kind": type(statement).__name__,
                    "expression": " ".join(expression.split())[:240],
                }
            )
    return sorted(items, key=lambda item: (item["lineno"], item["method"]))


def _json_type(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _guard_result(guard, params):
    if guard["key"] in params:
        value = params[guard["key"]]
        source = "params.json"
    elif not guard["default_is_dynamic"]:
        value = guard["default_value"]
        source = "code_default"
    else:
        return {
            **guard,
            "current_value": None,
            "value_source": "unknown",
            "holds": None,
        }
    return {
        **guard,
        "current_value": value,
        "value_source": source,
        "holds": bool(value) == guard["expected_truthy"],
    }


def _current_config_reachability(sites, params, decision_effect):
    if decision_effect == "NO_OBSERVED_DECISION_EFFECT":
        return "NO_OBSERVED_DECISION_EFFECT", []

    evaluated_sites = []
    for site in sites:
        guard_results = [_guard_result(g, params) for g in site.get("guards", [])]
        if not guard_results:
            site_state = "POTENTIALLY_REACHABLE"
        elif any(result["holds"] is False for result in guard_results):
            site_state = "DISABLED_BY_CURRENT_CONFIG"
        elif all(result["holds"] is True for result in guard_results):
            site_state = "REACHABLE_UNDER_CURRENT_CONFIG"
        else:
            site_state = "UNKNOWN"
        evaluated_sites.append(
            {
                "lineno": site["lineno"],
                "state": site_state,
                "guards": guard_results,
            }
        )

    states = {site["state"] for site in evaluated_sites}
    if "POTENTIALLY_REACHABLE" in states or "REACHABLE_UNDER_CURRENT_CONFIG" in states:
        overall = "POTENTIALLY_REACHABLE"
    elif states == {"DISABLED_BY_CURRENT_CONFIG"}:
        overall = "DISABLED_BY_CURRENT_CONFIG"
    else:
        overall = "UNKNOWN"
    return overall, evaluated_sites


def _concept_stem(key):
    return re.sub(
        r"(_active|_bench|_low_hp|_pct|_prize_mult|_per|_bonus)$", "", key
    )


def _runtime_override_contract(in_params, value):
    """Describe the existing Live Tuning endpoint's actual acceptance rule."""
    if not in_params:
        return {
            "runtime_override": False,
            "runtime_override_api_supported": False,
            "runtime_override_numeric_family_compatible": None,
            "runtime_override_declared_type_preserved": None,
            "runtime_override_accepted_types": [],
            "runtime_override_validation": None,
            "override_source": "not_exposed_by_params_json",
        }

    # validate_param_update() checks the submitted value, but not its type
    # against the base value's type. Therefore even a boolean base key can be
    # mutated by submitting numeric 0/1; that capability is real but not
    # type-safe.
    base_is_numeric = isinstance(value, (int, float)) and not isinstance(
        value, bool
    )
    # In JSON Schema terms, an integer is also a number, but a number is not
    # necessarily an integer. The endpoint accepts either for every exposed
    # key, so only a base key declared as "number" is guaranteed to stay
    # inside its declared type.
    declared_type_preserved = _json_type(value) == "number"
    return {
        "runtime_override": True,
        "runtime_override_api_supported": True,
        "runtime_override_numeric_family_compatible": base_is_numeric,
        "runtime_override_declared_type_preserved": declared_type_preserved,
        "runtime_override_accepted_types": ["integer", "number"],
        "runtime_override_validation": (
            "submitted value must be a finite non-boolean number; "
            "the base parameter type is not checked"
        ),
        "override_source": (
            "experiments.web.server:/runtime_params mutates module.P "
            "for this session"
        ),
    }


def build_audit(source, params):
    """Build all audit structures without filesystem writes."""
    calls = find_self_p_calls(source)
    eval_weights, eval_weights_lineno = find_eval_feature_weights(source)
    dead_methods = find_dead_scoring_methods(source)

    by_key = defaultdict(list)
    for call in calls:
        if not call["key"].startswith("<dynamic-key"):
            by_key[call["key"]].append(call)
    for key, value in eval_weights.items():
        by_key[key].append(
            {
                "key": key,
                "default_value": value,
                "default_repr": repr(value),
                "default_is_dynamic": False,
                "lineno": eval_weights_lineno,
                "function": "_eval_search_state",
                "guards": [],
                "via": "_EVAL_FEATURE_WEIGHTS",
            }
        )

    all_keys = sorted(set(params) | set(by_key))
    contract = {}
    for key in all_keys:
        sites = by_key.get(key, [])
        in_params = key in params
        referenced = bool(sites)
        functions = sorted({site["function"] for site in sites})
        all_sites_dead = bool(sites) and all(
            site["function"] in dead_methods for site in sites
        )

        static_defaults = {
            site["default_repr"]
            for site in sites
            if not site["default_is_dynamic"]
        }
        conflicting_defaults = len(static_defaults) > 1

        if not referenced and in_params:
            status = "UNUSED"
            shadow_reason = None
        elif all_sites_dead:
            status = "SHADOWED"
            shadow_reason = "enclosing_scoring_result_is_not_consumed"
        else:
            # ACTIVE means a value change has been shown to change a
            # production decision. This static audit cannot supply that
            # counterfactual evidence, even when return-value data flow is
            # visible, so it must not over-claim ACTIVE.
            status = "REFERENCED_UNVERIFIED"
            shadow_reason = None

        decision_effect = (
            "NO_OBSERVED_DECISION_EFFECT"
            if all_sites_dead
            else "STATICALLY_DECISION_RELEVANT"
            if referenced
            else "NO_CODE_REFERENCE"
        )
        config_reachability, site_reachability = _current_config_reachability(
            sites, params, decision_effect
        )

        type_source = params.get(key) if in_params else None
        if not in_params:
            default_values = [
                site["default_value"]
                for site in sites
                if not site["default_is_dynamic"]
            ]
            if default_values and all(
                _json_type(value) == _json_type(default_values[0])
                for value in default_values
            ):
                type_source = default_values[0]

        flags = []
        if referenced and not in_params:
            flags.append("CODE_DEFAULT_ONLY")
        if config_reachability == "DISABLED_BY_CURRENT_CONFIG":
            flags.append("CURRENT_CONFIG_DISABLED")
        if decision_effect == "NO_OBSERVED_DECISION_EFFECT":
            flags.append("NO_OBSERVED_DECISION_EFFECT")
        if conflicting_defaults:
            flags.append("CONFLICTING_CODE_DEFAULTS")

        override_contract = _runtime_override_contract(
            in_params, params.get(key)
        )
        if (
            override_contract["runtime_override_api_supported"]
            and not override_contract[
                "runtime_override_declared_type_preserved"
            ]
        ):
            flags.append("RUNTIME_OVERRIDE_DECLARED_TYPE_NOT_ENFORCED")
        if (
            override_contract["runtime_override_api_supported"]
            and not override_contract[
                "runtime_override_numeric_family_compatible"
            ]
        ):
            flags.append("RUNTIME_OVERRIDE_NUMERIC_FAMILY_MISMATCH")
        contract[key] = {
            "name": key,
            "status": status,
            "classifications": [status],
            "flags": flags,
            "type": _json_type(type_source),
            "unit": None,
            "min": None,
            "max": None,
            "used_by": functions,
            **override_contract,
            "description": None,
            "in_params_json": in_params,
            "params_json_value": params.get(key) if in_params else None,
            "referenced_in_code": referenced,
            "decision_effect": decision_effect,
            "runtime_decision_effect_verified": False,
            "activation_evidence": (
                "none"
                if decision_effect != "STATICALLY_DECISION_RELEVANT"
                else "static_shallow_return_usage_only"
            ),
            "current_config_reachability": config_reachability,
            "shadow_reason": shadow_reason,
            "call_sites": [
                {
                    "lineno": site["lineno"],
                    "function": site["function"],
                    "default_value": site["default_value"],
                    "default_repr": site["default_repr"],
                    "dynamic_default": site["default_is_dynamic"],
                    "via": site.get("via", "self.p()"),
                    "guards": site.get("guards", []),
                }
                for site in sites
            ],
            "site_reachability": site_reachability,
        }

    stems = defaultdict(list)
    for key in contract:
        stems[_concept_stem(key)].append(key)
    duplicate_groups = {
        stem: keys for stem, keys in stems.items() if len(keys) > 1
    }
    for stem, keys in duplicate_groups.items():
        for key in keys:
            contract[key]["flags"].append("DUPLICATE_CANDIDATE")
            contract[key]["classifications"].append("DUPLICATE")
            contract[key]["duplicate_group"] = stem

    hardcoded = find_hardcoded_numeric_literals(source)
    return {
        "contract": contract,
        "duplicate_groups": duplicate_groups,
        "hardcoded": hardcoded,
        "dead_methods": dead_methods,
    }


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def render_report(audit):
    contract = audit["contract"]
    hardcoded = audit["hardcoded"]
    status_counts = {
        status: sum(1 for item in contract.values() if item["status"] == status)
        for status in CONTRACT_STATUSES
    }
    unused = [key for key, item in contract.items() if item["status"] == "UNUSED"]
    shadowed = [
        key for key, item in contract.items() if item["status"] == "SHADOWED"
    ]
    not_persisted = [
        key
        for key, item in contract.items()
        if item["referenced_in_code"] and not item["in_params_json"]
    ]
    current_disabled = [
        key
        for key, item in contract.items()
        if item["current_config_reachability"] == "DISABLED_BY_CURRENT_CONFIG"
    ]
    override_supported = [
        key
        for key, item in contract.items()
        if item["runtime_override_api_supported"]
    ]
    override_declared_type_risk = [
        key
        for key, item in contract.items()
        if item["runtime_override_api_supported"]
        and not item["runtime_override_declared_type_preserved"]
    ]
    override_numeric_family_risk = [
        key
        for key, item in contract.items()
        if item["runtime_override_api_supported"]
        and not item["runtime_override_numeric_family_compatible"]
    ]

    lines = [
        "# Parameter Contract Audit Report (PR0-A.1)\n",
        "\n",
        "This is a static contract audit. `code reference`, `decision effect`, "
        "and `current-config reachability` are reported separately; none is "
        "silently treated as proof of the others.\n",
        "\n",
        "`ACTIVE` requires runtime counterfactual evidence that changing a "
        "parameter changes candidate rank or the selected action. Static "
        "references are deliberately reported as `REFERENCED_UNVERIFIED`.\n",
        "\n",
        f"Total keys examined: {len(contract)}\n",
    ]
    for status in CONTRACT_STATUSES:
        lines.append(f"- {status}: {status_counts[status]}\n")
    lines.extend(
        [
            f"- Code-default only: {len(not_persisted)}\n",
            f"- Current-config disabled: {len(current_disabled)}\n",
            f"- Runtime override API-supported: {len(override_supported)}\n",
            "- Runtime override declared-type not enforced: "
            f"{len(override_declared_type_risk)}\n",
            "- Runtime override numeric-family mismatch: "
            f"{len(override_numeric_family_risk)}\n",
            f"- Hardcoded numeric literals requiring review: {len(hardcoded)}\n",
            "\n",
            "Schema metadata (`unit`, `min`, `max`, `description`) remains "
            "`null` unless supported by an explicit source. The audit does "
            "not invent constraints.\n",
        ]
    )

    lines.append("\n## Runtime Override declared-type risks\n")
    for key in override_declared_type_risk:
        lines.append(
            f"- `{key}`: base type={contract[key]['type']!r}; the endpoint "
            "accepts both integer and non-integer numeric values.\n"
        )

    lines.append("\n## SHADOWED / no observed decision effect\n")
    for key in shadowed:
        item = contract[key]
        lines.append(
            f"- `{key}`: reason={item['shadow_reason']}, "
            f"used_by={item['used_by']}\n"
        )

    lines.append(
        "\n## UNUSED (present in params.json, no supported read in audited agent)\n"
    )
    for key in unused:
        lines.append(f"- `{key}` = {contract[key]['params_json_value']!r}\n")

    lines.append("\n## Current configuration disables the guarded call site\n")
    for key in current_disabled:
        lines.append(f"- `{key}`: {contract[key]['site_reachability']}\n")

    lines.append("\n## Code-default only (not persisted in params.json)\n")
    for key in not_persisted:
        item = contract[key]
        defaults = {
            site["default_repr"] for site in item["call_sites"]
        }
        lines.append(
            f"- `{key}` code default(s)={defaults} "
            f"(sites={[(s['function'], s['lineno']) for s in item['call_sites']]})\n"
        )

    lines.append("\n## Possible DUPLICATE concepts (human review required)\n")
    for stem, keys in sorted(audit["duplicate_groups"].items()):
        lines.append(f"- stem `{stem}`: {keys}\n")

    lines.append(
        "\n## Hardcoded numeric literals in scoring methods "
        "(structural constants included)\n"
    )
    for item in hardcoded:
        lines.append(
            f"- `{item['method']}` line {item['lineno']}: "
            f"{item['value']!r} [{item['context_kind']}] "
            f"`{item['expression']}`\n"
        )
    return "".join(lines)


def _default_provenance(source, params):
    effective_params_text = json.dumps(
        params, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        "source_ref_requested": "synthetic_or_caller_supplied",
        "source_commit": None,
        "main_py_sha256": _sha256_text(source),
        "params_json_raw_sha256": None,
        "effective_params_sha256": _sha256_text(effective_params_text),
    }


def build_artifact_contents(source, params, audit, provenance=None):
    """Render every artifact deterministically without touching the filesystem."""
    provenance = provenance or _default_provenance(source, params)
    contract_document = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "source": {
            **provenance,
            "main_py": os.path.relpath(MAIN_PY, REPO_ROOT).replace("\\", "/"),
            "params_json": os.path.relpath(PARAMS_JSON, REPO_ROOT).replace(
                "\\", "/"
            ),
        },
        "status_definitions": {
            "ACTIVE": "Runtime counterfactual evidence shows a candidate-rank or selected-action effect; never inferred by this static audit alone.",
            "REFERENCED_UNVERIFIED": "A static reference and shallow return-value path exist, but runtime decision effect has not been verified.",
            "EXPERIMENTAL": "Explicitly marked experimental (none inferred automatically).",
            "DEPRECATED": "Explicitly marked deprecated (none inferred automatically).",
            "UNUSED": "Present in params.json but no supported parameter read was found in the audited agent source.",
            "SHADOWED": "Referenced, but an unconsumed scoring result prevents an observed decision effect.",
            "DUPLICATE": "Non-exclusive review flag for a possible duplicate concept.",
        },
        "decision_effect_definitions": {
            "STATICALLY_DECISION_RELEVANT": "Shallow static return-use analysis found a possible path; this is not runtime proof.",
            "NO_OBSERVED_DECISION_EFFECT": "The enclosing scoring result is discarded or assigned without a later read.",
            "NO_CODE_REFERENCE": "No supported parameter read was found in the audited agent source; repository-wide tooling is outside this scan.",
        },
        "parameters": audit["contract"],
    }

    unused = [
        key
        for key, item in audit["contract"].items()
        if item["status"] == "UNUSED"
    ]
    return {
        "parameter_contract.json": (
            json.dumps(contract_document, ensure_ascii=False, indent=2) + "\n"
        ),
        "unused_parameter_list.json": (
            json.dumps(unused, ensure_ascii=False, indent=2) + "\n"
        ),
        "hardcoded_score_inventory.json": (
            json.dumps(audit["hardcoded"], ensure_ascii=False, indent=2) + "\n"
        ),
        "parameter_audit_report.md": render_report(audit),
    }


def write_artifacts(
    source, params, audit, out_dir=OUT_DIR, provenance=None
):
    os.makedirs(out_dir, exist_ok=True)
    contents = build_artifact_contents(source, params, audit, provenance)
    for filename in ARTIFACT_FILENAMES:
        with open(
            os.path.join(out_dir, filename),
            "w",
            encoding="utf-8",
            newline="\n",
        ) as f:
            f.write(contents[filename])


def find_artifact_mismatches(
    source, params, audit, out_dir=OUT_DIR, provenance=None
):
    expected = build_artifact_contents(source, params, audit, provenance)
    mismatches = []
    for filename in ARTIFACT_FILENAMES:
        path = os.path.join(out_dir, filename)
        if not os.path.exists(path):
            mismatches.append(f"{filename}: missing")
            continue
        with open(path, "rb") as f:
            actual = f.read()
        if actual != expected[filename].encode("utf-8"):
            mismatches.append(f"{filename}: differs")
    return mismatches


def main():
    parser = argparse.ArgumentParser(
        description="Generate the Raging Bolt Parameter Contract audit"
    )
    parser.add_argument(
        "--source-ref",
        help=(
            "Read main.py and params.json from this git revision instead of "
            "the dirty worktree (for example: HEAD)."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; fail if checked-in artifacts differ.",
    )
    args = parser.parse_args()

    source, params, provenance = load_inputs(args.source_ref)
    audit = build_audit(source, params)
    if args.check:
        mismatches = find_artifact_mismatches(
            source, params, audit, provenance=provenance
        )
        if mismatches:
            for mismatch in mismatches:
                print(f"MISMATCH: {mismatch}")
            raise SystemExit(1)
        print(f"Audit artifacts match {OUT_DIR}")
    else:
        write_artifacts(source, params, audit, provenance=provenance)
        print(f"Wrote audit artifacts to {OUT_DIR}")

    counts = defaultdict(int)
    for item in audit["contract"].values():
        counts[item["status"]] += 1
    print(
        " ".join(f"{status}={counts[status]}" for status in CONTRACT_STATUSES)
        + f" hardcoded={len(audit['hardcoded'])}"
    )


if __name__ == "__main__":
    main()
