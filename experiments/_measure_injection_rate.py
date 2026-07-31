"""One-off script (not part of the test suite) to measure how often
rule_tactical_candidate_guarantees actually injects a candidate during real
MAIN/engine-search decisions -- the Design Judge's mechanism-verification
gate for win-rate-cycle1's Candidate 1. Plays N mirror games under
POKEMON_AI_EXEC_MODE=BENCHMARK and reports get_telemetry() counters.
"""
from __future__ import annotations
import os
import sys

os.environ["POKEMON_AI_EXEC_MODE"] = "BENCHMARK"

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "reference", "extracted"))

import importlib.util


def load_agent_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_deck(path):
    with open(path, encoding="utf-8") as f:
        return [int(l.strip()) for l in f if l.strip()]


def main():
    n_games = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    agent_path = os.path.join(REPO_ROOT, "experiments", "agents", "raging_bolt", "main.py")
    deck_path = os.path.join(REPO_ROOT, "experiments", "decks", "raging_bolt_ogerpon.csv")

    mod = load_agent_module(agent_path, "injection_rate_agent")
    deck = load_deck(deck_path)

    from cg.api import to_observation_class
    from cg.game import battle_finish, battle_select, battle_start

    mod.reset_telemetry()

    for gi in range(n_games):
        obs, sd = battle_start(deck, deck)
        if obs is None:
            continue
        try:
            for _ in range(2000):
                obc = to_observation_class(obs)
                if obc.current.result >= 0:
                    break
                obs = battle_select(mod.agent(obs))
        finally:
            try:
                battle_finish()
            except Exception:
                pass
        print(f"  game {gi + 1}/{n_games} done")

    t = mod.get_telemetry()
    search_attempts = t["search_attempt_count"]
    injections = t["candidate_injection_decision_count"]
    rate = (injections / search_attempts * 100) if search_attempts else 0.0
    print("\n=== injection-rate telemetry over %d games ===" % n_games)
    for k in ("search_attempt_count", "search_success_count", "search_override_count",
              "candidate_injection_decision_count", "candidate_injection_attack_count",
              "candidate_injection_attach_lethal_count", "candidate_injection_retreat_count",
              "terminal_win_rollout_count", "rollout_attempt_count", "rollout_success_count",
              "rollout_error_count"):
        print(f"  {k}: {t[k]}")
    print(f"\n  MAIN search decisions: {search_attempts}")
    print(f"  decisions with >=1 injection: {injections} ({rate:.2f}%)")


if __name__ == "__main__":
    main()
