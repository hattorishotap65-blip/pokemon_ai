"""
PR0-B: Single-decision Deterministic Replay CLI.

Loads a Replay Bundle JSONL file (produced by experiments/agents/raging_bolt/
main.py when POKEMON_AI_REPLAY_BUNDLE_PATH is set -- see
_maybe_capture_replay_bundle / build_replay_bundle in that file) and, for each
captured decision, reconstructs the exact same RagingBoltPolicy state
(obs_dict + materialized hidden samples) and re-runs the decision N times.

This is "partial CRN" replay (see
experiments/agents/raging_bolt/audit/crn_capability_matrix.json): the
engine's own internal randomness cannot be seeded, but our own hidden-state
sampling can be captured and replayed exactly, and that is the only
python-side randomness feeding the decision (confirmed: _rng is only ever
touched inside _predict_hidden's call chain).

IMPORTANT, empirically confirmed during PR0-B validation: this guarantees
byte-identical replay for non-MAIN (heuristic-only, no engine call)
decisions, but NOT for MAIN-context decisions that go through
_engine_search_choose. cg.api.search_begin()'s manual_coin parameter
defaults to False, meaning the engine resolves any coin-flip game effect
encountered during the simulated rollforward using its OWN internal RNG --
uncontrollable and unobservable from Python, independent of how exactly the
hidden zones are materialized. So this script reports mismatch rate
separately per select-context class and only treats a non-MAIN mismatch as
a hard failure; a nonzero MAIN-context mismatch rate is expected engine
noise, not a bug in this replay harness.

Usage (inside WSL, where the cg extension is importable):
  # 1. Capture bundles during any existing benchmark run:
  POKEMON_AI_EXEC_MODE=BENCHMARK \
  POKEMON_AI_REPLAY_BUNDLE_PATH=/tmp/bundles.jsonl \
  python experiments/head_to_head.py --agent-a main.py --deck-a deck.csv \
      --agent-b experiments/agents/top_lucario_1084_main.py \
      --deck-b experiments/decks/top_lucario_1084.csv --n 1

  # 2. Replay every captured decision 10x and check determinism:
  python experiments/replay_decision.py /tmp/bundles.jsonl --repeats 10
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_AGENT_PATH = os.path.join(_REPO_ROOT, "experiments", "agents", "raging_bolt", "main.py")
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "reference", "extracted"))


def _load_agent_module(path=_AGENT_PATH):
    spec = importlib.util.spec_from_file_location("raging_bolt_main_replay", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def replay_one(mod, record, repeats):
    """Re-run one captured decision `repeats` times. Returns
    (semantic_ids_per_run, matches_capture, all_runs_identical)."""
    from cg.api import to_observation_class, SelectContext

    obs_dict = record["obs_dict"]
    hidden_samples = record.get("captured_hidden_samples") or []
    recorded_semantic_ids = record.get("decision_semantic_ids") or []
    select_context = record.get("select_context")

    runs = []
    for _ in range(repeats):
        obs = to_observation_class(obs_dict)
        # Fresh policy instance each run, fed a fresh copy of the SAME
        # materialized hidden samples in the same order -- this is the
        # replay contract (see RagingBoltPolicy.__init__ / _predict_hidden).
        policy = mod.RagingBoltPolicy(obs, replay_hidden_samples=list(hidden_samples))
        if select_context == int(SelectContext.MAIN):
            decision = policy.choose_with_search()
        else:
            decision = policy.choose()
        select = obs.select
        sem_ids = [
            mod._semantic_action_id(select.context, select.option[i], policy.my_index)
            for i in (decision or [])
            if select and select.option and 0 <= i < len(select.option)
        ]
        runs.append(sem_ids)

    all_identical = all(r == runs[0] for r in runs)
    matches_capture = runs[0] == recorded_semantic_ids if runs else False
    return runs, matches_capture, all_identical


def main():
    parser = argparse.ArgumentParser(description="Replay captured decisions for determinism check")
    parser.add_argument("bundle_path", help="Path to a Replay Bundle JSONL file")
    parser.add_argument("--repeats", type=int, default=10, help="Replays per captured decision")
    parser.add_argument("--limit", type=int, default=0, help="Only replay the first N records (0 = all)")
    args = parser.parse_args()

    os.environ.setdefault("POKEMON_AI_EXEC_MODE", "DEBUG")

    mod = _load_agent_module()
    from cg.api import SelectContext
    main_ctx = int(SelectContext.MAIN)

    with open(args.bundle_path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    if args.limit:
        records = records[:args.limit]

    stats = {
        "MAIN": {"total": 0, "mismatch_vs_self": 0, "mismatch_vs_capture": 0},
        "NON_MAIN": {"total": 0, "mismatch_vs_self": 0, "mismatch_vs_capture": 0},
    }
    for idx, record in enumerate(records):
        is_main = record.get("select_context") == main_ctx
        bucket = stats["MAIN"] if is_main else stats["NON_MAIN"]
        bucket["total"] += 1
        runs, matches_capture, all_identical = replay_one(mod, record, args.repeats)
        status = "OK" if all_identical and matches_capture else "MISMATCH"
        print(f"[{status}] record {idx}: turn={record.get('turn')} "
              f"ctx={record.get('select_context')} ({'MAIN/engine-search' if is_main else 'non-MAIN/heuristic'}) "
              f"all_identical={all_identical} matches_capture={matches_capture}")
        if not all_identical:
            bucket["mismatch_vs_self"] += 1
            for i, r in enumerate(runs):
                print(f"    run {i}: {r}")
        if not matches_capture:
            bucket["mismatch_vs_capture"] += 1
            print(f"    captured: {record.get('decision_semantic_ids')}")
            print(f"    replayed: {runs[0] if runs else None}")

    print(f"\n=== Determinism summary ===")
    for label, s in stats.items():
        rate = (s["mismatch_vs_self"] / s["total"]) if s["total"] else 0.0
        print(f"[{label}] records={s['total']} repeats/record={args.repeats} "
              f"mismatch_vs_self={s['mismatch_vs_self']}/{s['total']} "
              f"mismatch_vs_capture={s['mismatch_vs_capture']}/{s['total']} "
              f"determinism_mismatch_rate={rate:.4f}")
    print("\nNOTE: non-MAIN (heuristic-only) decisions are expected to be 100%")
    print("reproducible -- any non-MAIN mismatch is a real bug, fail the check.")
    print("MAIN (engine-search) decisions are NOT expected to be 100% reproducible")
    print("-- cg.api.search_begin(manual_coin=False) resolves coin-flip effects via")
    print("the engine's own uncontrollable internal RNG (see crn_capability_matrix.json).")
    print("A nonzero MAIN mismatch rate is expected engine noise, not a harness bug.")

    if stats["NON_MAIN"]["mismatch_vs_self"] or stats["NON_MAIN"]["mismatch_vs_capture"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
