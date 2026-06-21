"""
Build and verify submission.tar.gz.

Usage:
  python tools/build_submission.py
  python tools/build_submission.py --verify-only
  python tools/build_submission.py --check-weight legal_attack_score=250.0
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import tarfile

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_TAR_PATH = os.path.join(_REPO_ROOT, "submission.tar.gz")

_REQUIRED_FILES = [
    "main.py",
    "deck.csv",
    "agent/__init__.py",
    "agent/ionos_rules.py",
    "agent/policy.py",
    "agent/turn_rule_engine.py",
    "agent/evaluator.py",
    "agent/planner.py",
    "data/weights.json",
    "data/card_knowledge.csv",
    "cg/libcg.so",
]

_ALL_FILES = [
    ("main.py", "main.py"),
    ("deck.csv", "deck.csv"),
    ("agent/__init__.py", "agent/__init__.py"),
    ("agent/advantage.py", "agent/advantage.py"),
    ("agent/card_knowledge.py", "agent/card_knowledge.py"),
    ("agent/concept_weights.py", "agent/concept_weights.py"),
    ("agent/ionos_rules.py", "agent/ionos_rules.py"),
    ("agent/evaluator.py", "agent/evaluator.py"),
    ("agent/fallback.py", "agent/fallback.py"),
    ("agent/logger.py", "agent/logger.py"),
    ("agent/opponent_model.py", "agent/opponent_model.py"),
    ("agent/planner.py", "agent/planner.py"),
    ("agent/policy.py", "agent/policy.py"),
    ("agent/rollout.py", "agent/rollout.py"),
    ("agent/turn_plan.py", "agent/turn_plan.py"),
    ("agent/win_condition.py", "agent/win_condition.py"),
    ("agent/effect_engine.py", "agent/effect_engine.py"),
    ("agent/turn_rule_engine.py", "agent/turn_rule_engine.py"),
    ("data/card_knowledge.csv", "data/card_knowledge.csv"),
    ("data/deck_profile.json", "data/deck_profile.json"),
    ("data/card_effects_iono_lightning_recommended_en_ja.json",
     "data/card_effects_iono_lightning_recommended_en_ja.json"),
    ("data/weights.json", "data/weights.json"),
]


def build(repo_root: str = _REPO_ROOT, tar_path: str = _TAR_PATH) -> bool:
    missing = []
    for local, _ in _ALL_FILES:
        full = os.path.join(repo_root, local)
        if not os.path.exists(full):
            missing.append(local)

    cg_dir = os.path.join(repo_root, "reference", "extracted", "cg")
    if not os.path.isdir(cg_dir):
        missing.append("reference/extracted/cg/")

    if missing:
        print("ERROR: Missing files:")
        for m in missing:
            print(f"  {m}")
        return False

    with tarfile.open(tar_path, "w:gz") as tar:
        for local, arc in _ALL_FILES:
            tar.add(os.path.join(repo_root, local), arcname=arc)
            print(f"  + {arc}")
        tar.add(cg_dir, arcname="cg")
        print("  + cg/")

    sz = os.path.getsize(tar_path) // 1024
    print(f"Done -- {sz} KB")
    return True


def verify(tar_path: str = _TAR_PATH, check_weights: dict = None) -> bool:
    if not os.path.exists(tar_path):
        print(f"ERROR: {tar_path} not found")
        return False

    with tarfile.open(tar_path, "r:gz") as tar:
        names = [m.name for m in tar.getmembers()]

        ok = True
        for req in _REQUIRED_FILES:
            if req in names:
                print(f"  OK  {req}")
            else:
                print(f"  MISSING  {req}")
                ok = False

        if check_weights:
            f = tar.extractfile("data/weights.json")
            if f:
                data = json.load(f)
                for k, expected in check_weights.items():
                    actual = data.get(k)
                    if actual == expected:
                        print(f"  OK  weights.{k} = {actual}")
                    else:
                        print(f"  MISMATCH  weights.{k} = {actual} (expected {expected})")
                        ok = False

    sz = os.path.getsize(tar_path) // 1024
    print(f"\nSize: {sz} KB")
    return ok


def main():
    parser = argparse.ArgumentParser(description="Build and verify submission.tar.gz")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--check-weight", action="append", default=[],
                        help="key=value to verify in weights.json (repeatable)")
    args = parser.parse_args()

    check_weights = {}
    for cw in args.check_weight:
        k, v = cw.split("=", 1)
        check_weights[k] = float(v)

    if args.verify_only:
        ok = verify(check_weights=check_weights or None)
    else:
        ok = build()
        if ok:
            print("\nVerifying...")
            ok = verify(check_weights=check_weights or None)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
