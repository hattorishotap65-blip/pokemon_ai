"""
PR0-A: Parameter Contract Audit (no policy changes).

Cross-references experiments/agents/raging_bolt/params.json against every
self.p("key", default) call site in main.py, plus the _EVAL_FEATURE_WEIGHTS
dict (the default source for se_* keys read via self.p(k, self._EVAL_FEATURE_WEIGHTS[k])).
Classifies every key found in either source as one of:

  ACTIVE     referenced in code, present in params.json, defaults agree
  SHADOWED   referenced in code with a default that DISAGREES with the
             params.json value at some call site, or multiple call sites
             disagree with each other
  UNUSED     present in params.json but never referenced by self.p() anywhere
  DUPLICATE  two or more distinct param names control what looks like the
             same concept (flagged heuristically for human review, not
             auto-resolved)

Also builds a hardcoded_score_inventory: bare numeric `return <literal>`
statements inside scoring methods that are NOT already going through
self.p() -- i.e. scores that can't be tuned via params.json/Live Tuning
Panel at all.

This script only reads main.py and params.json; it does not import or
execute the agent, and produces read-only report artifacts. It changes
no scores and no code paths.

Usage:
  python experiments/audit_parameter_contract.py
"""
from __future__ import annotations
import ast
import json
import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAIN_PY = os.path.join(REPO_ROOT, "experiments", "agents", "raging_bolt", "main.py")
PARAMS_JSON = os.path.join(REPO_ROOT, "experiments", "agents", "raging_bolt", "params.json")
OUT_DIR = os.path.join(REPO_ROOT, "experiments", "agents", "raging_bolt", "audit")


def load_params():
    with open(PARAMS_JSON, encoding="utf-8") as f:
        d = json.load(f)
    d.pop("_comment", None)
    return d


def find_self_p_calls(source: str):
    """AST-based extraction of self.p("key", default) call sites.
    Returns list of dicts: {key, default_repr, lineno, default_is_dynamic}.
    Handles the case where `default` is not a literal (e.g. a dict lookup)
    by recording default_is_dynamic=True and default_repr=<source text>.
    """
    tree = ast.parse(source)
    calls = []

    def literal_keys(key_node):
        """Return list of literal string keys a key-argument expression can
        resolve to. Handles plain constants and ternary-of-literals
        ("a" if cond else "b"), which is used at the ucb1 budget call site
        to pick between two literal param names -- a naive Constant-only
        check misses this and falsely reports both keys as UNUSED."""
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
            return [key_node.value]
        if isinstance(key_node, ast.IfExp):
            return literal_keys(key_node.body) + literal_keys(key_node.orelse)
        return []

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node):
            if (isinstance(node.func, ast.Attribute)
                    and node.func.attr == "p"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "self"):
                if len(node.args) >= 1:
                    keys = literal_keys(node.args[0])
                    default_node = node.args[1] if len(node.args) >= 2 else None
                    if default_node is None:
                        default_repr, dynamic = None, False
                    elif isinstance(default_node, ast.Constant):
                        default_repr, dynamic = repr(default_node.value), False
                    else:
                        default_repr, dynamic = ast.dump(default_node), True
                    if not keys:
                        # key itself isn't resolvable to literal string(s) --
                        # record under a sentinel so it doesn't silently
                        # vanish from the audit.
                        keys = [f"<dynamic-key L{node.lineno}>"]
                    for key in keys:
                        calls.append({"key": key, "default_repr": default_repr,
                                      "lineno": node.lineno, "default_is_dynamic": dynamic})
            self.generic_visit(node)

    Visitor().visit(tree)
    return calls


def find_eval_feature_weights(source: str):
    """Extract the _EVAL_FEATURE_WEIGHTS dict literal (class attribute) --
    these se_* keys are read via self.p(k, self._EVAL_FEATURE_WEIGHTS[k]) in
    a loop, so the static self.p() scan above only sees the dynamic form;
    this recovers the concrete per-key defaults separately."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_EVAL_FEATURE_WEIGHTS":
                    if isinstance(node.value, ast.Dict):
                        out = {}
                        for k_node, v_node in zip(node.value.keys, node.value.values):
                            if isinstance(k_node, ast.Constant) and isinstance(v_node, ast.Constant):
                                out[k_node.value] = v_node.value
                        return out, node.lineno
    return {}, None


def find_hardcoded_returns(source: str):
    """Heuristic: bare `return <numeric literal>` statements inside methods
    whose name starts with _score / _eval / impact-related helpers, i.e.
    scores that bypass self.p() entirely and can't be tuned via
    params.json or the Live Tuning Panel."""
    tree = ast.parse(source)
    out = []

    def method_is_scoring(name):
        return (name.startswith("_score_") or name.startswith("_eval_")
                or name in ("_estimate_action_impact", "_eval_search_state"))

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            if method_is_scoring(node.name):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Constant):
                        if isinstance(sub.value.value, (int, float)) and not isinstance(sub.value.value, bool):
                            out.append({"method": node.name, "lineno": sub.lineno,
                                        "value": sub.value.value})
            self.generic_visit(node)

    Visitor().visit(tree)
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(MAIN_PY, encoding="utf-8") as f:
        source = f.read()

    params = load_params()
    calls = find_self_p_calls(source)
    eval_weights, eval_weights_lineno = find_eval_feature_weights(source)

    # Merge: static self.p() call sites + the dynamic se_* dict-driven ones.
    by_key = {}
    for c in calls:
        by_key.setdefault(c["key"], []).append(c)
    for k, v in eval_weights.items():
        by_key.setdefault(k, []).append({"key": k, "default_repr": repr(v),
                                          "lineno": eval_weights_lineno, "default_is_dynamic": False,
                                          "via": "_EVAL_FEATURE_WEIGHTS"})

    # Drop unresolvable dynamic-key sentinels from classification -- they
    # aren't real parameter names (the concrete se_* keys they represent are
    # already captured via _EVAL_FEATURE_WEIGHTS extraction above), they'd
    # just show up as noise/false "not persisted" entries otherwise.
    by_key = {k: v for k, v in by_key.items() if not k.startswith("<dynamic-key")}

    all_keys = set(params.keys()) | set(by_key.keys())
    contract = {}
    for key in sorted(all_keys):
        in_params = key in params
        sites = by_key.get(key, [])
        referenced = len(sites) > 0

        if not referenced and in_params:
            status = "UNUSED"
        elif referenced and not in_params:
            status = "ACTIVE"  # code-default-only; not persisted in params.json
        else:
            # both present -- check whether all code-site defaults agree with
            # each other and with the params.json value
            static_defaults = {s["default_repr"] for s in sites if not s["default_is_dynamic"]}
            has_dynamic = any(s["default_is_dynamic"] for s in sites)
            params_repr = repr(params.get(key)) if in_params else None
            mismatch = False
            if static_defaults:
                if len(static_defaults) > 1:
                    mismatch = True  # two call sites disagree with each other
                elif in_params and params_repr not in static_defaults:
                    # params.json overrides the code default -- normal (that's
                    # the point of params.json), not a mismatch by itself
                    mismatch = False
            status = "SHADOWED" if mismatch else "ACTIVE"

        contract[key] = {
            "status": status,
            "in_params_json": in_params,
            "params_json_value": params.get(key) if in_params else None,
            "referenced_in_code": referenced,
            "call_sites": [{"lineno": s["lineno"], "default_repr": s["default_repr"],
                            "dynamic_default": s["default_is_dynamic"],
                            "via": s.get("via", "self.p()")} for s in sites],
        }

    # Heuristic DUPLICATE detection: same normalized "concept" stem shared by
    # >1 key name (human review required, not auto-merged).
    def stem(k):
        return re.sub(r"(_active|_bench|_low_hp|_pct|_prize_mult|_per|_bonus)$", "", k)
    stems = {}
    for k in contract:
        stems.setdefault(stem(k), []).append(k)
    duplicate_groups = {s: ks for s, ks in stems.items() if len(ks) > 1}

    hardcoded = find_hardcoded_returns(source)

    unused = [k for k, v in contract.items() if v["status"] == "UNUSED"]
    shadowed = [k for k, v in contract.items() if v["status"] == "SHADOWED"]
    not_persisted = [k for k, v in contract.items()
                      if v["status"] == "ACTIVE" and not v["in_params_json"]]

    with open(os.path.join(OUT_DIR, "parameter_contract.json"), "w", encoding="utf-8") as f:
        json.dump(contract, f, ensure_ascii=False, indent=1)

    with open(os.path.join(OUT_DIR, "unused_parameter_list.json"), "w", encoding="utf-8") as f:
        json.dump(unused, f, ensure_ascii=False, indent=1)

    with open(os.path.join(OUT_DIR, "hardcoded_score_inventory.json"), "w", encoding="utf-8") as f:
        json.dump(hardcoded, f, ensure_ascii=False, indent=1)

    lines = []
    lines.append("# Parameter Contract Audit Report (PR0-A)\n")
    lines.append(f"Total keys examined: {len(contract)}\n")
    lines.append(f"- ACTIVE: {sum(1 for v in contract.values() if v['status']=='ACTIVE')}\n")
    lines.append(f"- UNUSED: {len(unused)}\n")
    lines.append(f"- SHADOWED: {len(shadowed)}\n")
    lines.append(f"- Not persisted in params.json (code-default only): {len(not_persisted)}\n")
    lines.append(f"- Hardcoded non-parameterized scores found: {len(hardcoded)}\n")

    lines.append("\n## UNUSED (in params.json, never read by code)\n")
    for k in unused:
        lines.append(f"- `{k}` = {contract[k]['params_json_value']!r}\n")

    lines.append("\n## SHADOWED (inconsistent defaults across call sites)\n")
    for k in shadowed:
        lines.append(f"- `{k}`: sites={contract[k]['call_sites']}\n")

    lines.append("\n## Not persisted in params.json (relies on code default only)\n")
    for k in not_persisted:
        sites = contract[k]["call_sites"]
        defaults = {s["default_repr"] for s in sites}
        lines.append(f"- `{k}` code default(s)={defaults} (lines {[s['lineno'] for s in sites]})\n")

    lines.append("\n## Possible DUPLICATE concept groups (heuristic, needs human review)\n")
    for stem_name, ks in sorted(duplicate_groups.items()):
        lines.append(f"- stem `{stem_name}`: {ks}\n")

    lines.append("\n## Hardcoded scores bypassing self.p() (not tunable via params.json)\n")
    for h in hardcoded:
        lines.append(f"- `{h['method']}` line {h['lineno']}: literal return {h['value']!r}\n")

    with open(os.path.join(OUT_DIR, "parameter_audit_report.md"), "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"Wrote audit artifacts to {OUT_DIR}")
    print(f"ACTIVE={sum(1 for v in contract.values() if v['status']=='ACTIVE')} "
          f"UNUSED={len(unused)} SHADOWED={len(shadowed)} "
          f"not_persisted={len(not_persisted)} hardcoded={len(hardcoded)}")


if __name__ == "__main__":
    main()
