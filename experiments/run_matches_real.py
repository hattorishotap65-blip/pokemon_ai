"""
Real simulation using libcg.so — Linux / WSL only.

Runs self-play or policy-vs-random matches with the actual cabt game engine.
Two agents are routed by obs.current.yourIndex each selection.

Usage (run inside WSL):
    python experiments/run_matches_real.py
    python experiments/run_matches_real.py --n 100
    python experiments/run_matches_real.py --n 100 --vs random
    python experiments/run_matches_real.py --n 50  --deck data/decks/other.csv
"""
import argparse
import csv
import os
import random
import sys
import time
from collections import defaultdict
from datetime import datetime

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _ROOT)

_LOG_DIR  = os.path.join(_ROOT, "logs")
_DECK_CSV = os.path.join(_ROOT, "deck.csv")


# ---------------------------------------------------------------------------
# Platform guard
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    print("ERROR: libcg.so is a Linux binary. Run this script inside WSL.")
    print("  wsl python experiments/run_matches_real.py --n 50")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Deck loader
# ---------------------------------------------------------------------------

def _load_deck(path: str) -> list[int]:
    cards = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    cards.append(int(line))
                except ValueError:
                    pass
    if len(cards) != 60:
        raise ValueError(f"Deck must be 60 cards, got {len(cards)}: {path}")
    return cards


# ---------------------------------------------------------------------------
# Agent wrappers
# ---------------------------------------------------------------------------

class PolicyRunner:
    """PolicyAgent wrapped for use in a local game loop."""

    def __init__(self, deck: list[int], card_table: dict, attack_full: dict):
        from agent.policy import PolicyAgent
        from main import _board_to_state, _opt_to_dict, _enrich_options
        self.policy      = PolicyAgent()
        self.deck        = deck
        self.card_table  = card_table
        self.attack_full = attack_full
        self._bts        = _board_to_state
        self._otd        = _opt_to_dict
        self._enrich     = _enrich_options

    def act(self, obs) -> list[int]:
        if obs.select is None:
            return self.deck

        options   = obs.select.option or []
        max_count = int(obs.select.maxCount or 1)
        min_count = int(obs.select.minCount or 0)
        n         = len(options)

        if n == 0:
            return []

        # Update turn plan
        try:
            from agent.turn_plan import compute_plan
            self.policy.current_plan = compute_plan(obs, self.card_table, self.attack_full)
        except Exception:
            self.policy.current_plan = None

        state     = self._bts(obs.current)
        opt_dicts = [self._otd(o) for o in options]

        # Enrich with resolved card IDs and select context
        select_ctx = int(getattr(obs.select, "context", 0) or 0)
        try:
            self._enrich(opt_dicts, obs, select_ctx)
        except Exception:
            pass

        # Must select all when no real choice
        if min_count == max_count == n:
            return list(range(n))

        # Cache opt_dicts so _score_with_breakdown() can access turn_rule_engine scores
        self.policy._current_opt_dicts = opt_dicts

        scores = [0.0] * n
        for i, opt in enumerate(opt_dicts):
            try:
                scores[i] = self.policy._score(opt, state)[0]
            except Exception:
                pass

        # Attack suppression
        try:
            scores = self.policy.suppress_attack_if_pre_required(state, opt_dicts, scores)
        except Exception:
            pass

        # Iono's Poffin / ToBench diversity guard (ctx in (2,5), max_count>1)
        try:
            if n > 0 and max_count > 1:
                _ctx0 = opt_dicts[0].get("select_context", -1) if opt_dicts else -1
                if _ctx0 in (2, 5):
                    _IONO_BASICS = {"265", "268", "270"}
                    ranked_d = sorted(enumerate(scores), key=lambda x: -x[1])
                    sel_div: list = []
                    seen_c: set = set()
                    for i, s in ranked_d:
                        if s <= -900.0:
                            continue
                        _cid = str(opt_dicts[i].get("resolved_card_id", ""))
                        if _cid in _IONO_BASICS and _cid in seen_c:
                            continue
                        sel_div.append(i)
                        if _cid in _IONO_BASICS:
                            seen_c.add(_cid)
                        if len(sel_div) >= max_count:
                            break
                    if len(sel_div) < max(min_count, 1):
                        for i, s in ranked_d:
                            if i in sel_div or s <= -900.0:
                                continue
                            sel_div.append(i)
                            if len(sel_div) >= max_count:
                                break
                    if len(sel_div) >= min_count:
                        return sel_div[:max_count]
        except Exception:
            pass

        ranked = sorted(range(n), key=lambda i: -scores[i])
        result = ranked[:max_count]
        if len(result) < min_count:
            extra = [i for i in range(n) if i not in result]
            result += extra[: min_count - len(result)]
        return result


class RandomRunner:
    """Uniformly random agent."""

    def __init__(self, deck: list[int]):
        self.deck = deck

    def act(self, obs) -> list[int]:
        if obs.select is None:
            return self.deck
        options   = obs.select.option or []
        max_count = int(obs.select.maxCount or 1)
        min_count = int(obs.select.minCount or 0)
        n = len(options)
        if n == 0:
            return []
        count = max(min_count, min(max_count, 1))
        return random.sample(range(n), min(count, n))


class MainAgentRunner:
    """
    Thin wrapper that calls main.agent() directly so that GameLogger,
    _select_indices (diversity guard), attack suppression, and the full
    scoring pipeline are all exercised exactly as in the Kaggle submission.
    """

    def __init__(self, deck: list[int]):
        self.deck = deck
        import main as _m
        if _m._policy is None:
            _m._init()
        self._main = _m

    def new_game(self, game_id: str = None):
        """Reset per-game state: fresh GameLogger + opponent tracking."""
        import uuid
        from agent.logger import GameLogger
        gid = game_id or str(uuid.uuid4())[:8]
        self._main._logger = GameLogger(
            game_id=gid,
            deck_name=self._main.DECK_NAME,
            agent_version=self._main.AGENT_VERSION,
        )
        self._main._opp_seen      = {}
        self._main._last_game_turn = 0

    def act_raw(self, obs_dict: dict) -> list[int]:
        return self._main.agent(obs_dict)

    def act(self, obs) -> list[int]:
        return [0]


# ---------------------------------------------------------------------------
# Single game
# ---------------------------------------------------------------------------

def run_one_game(
    agents: list,       # [agent_for_p0, agent_for_p1]
    deck0: list[int],
    deck1: list[int],
    max_selections: int = 600,
) -> tuple[str, int]:
    """
    Run one complete game.
    Returns (winner, selections_made).
    winner: "p0", "p1", "timeout", "error"
    """
    from cg.game import battle_start, battle_select, battle_finish
    from cg.api  import to_observation_class

    try:
        obs_dict, start = battle_start(deck0, deck1)
    except Exception:
        return "error", 0

    if obs_dict is None or not start.battlePtr:
        return "error", 0
    if start.errorPlayer >= 0:
        return "error", 0

    sel_n = 0
    try:
        while sel_n < max_selections:
            obs = to_observation_class(obs_dict)

            # Check game-over
            if obs.current and obs.current.result != -1:
                winner_idx = int(obs.current.result)
                battle_finish()
                return f"p{winner_idx}", sel_n

            # Route to the player who needs to select
            pidx   = int(obs.current.yourIndex or 0) if obs.current else 0
            runner = agents[pidx]
            if hasattr(runner, "act_raw"):
                chosen = runner.act_raw(obs_dict)
            else:
                chosen = runner.act(obs)
            obs_dict = battle_select(chosen)
            sel_n += 1

        # Safety timeout
        battle_finish()
        return "timeout", sel_n

    except Exception:
        try:
            battle_finish()
        except Exception:
            pass
        return "error", sel_n


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

def run_batch(
    n_games: int,
    deck_path: str,
    output_csv: str,
    vs_random: bool = False,
    start_game: int = 0,
):
    from cg.api import all_card_data
    from agent.policy import PolicyAgent

    deck = _load_deck(deck_path)

    # Load card table once (shared across agents)
    try:
        card_table  = {c.cardId: c for c in all_card_data()}
    except Exception:
        card_table  = {}

    # Load attack_full from a temporary PolicyAgent
    _tmp        = PolicyAgent()
    attack_full = getattr(_tmp, "_attack_full", {})
    del _tmp

    # Build agents — use MainAgentRunner for full feature parity with Kaggle submission
    agent_policy = MainAgentRunner(deck)
    agent_opp    = RandomRunner(deck) if vs_random else MainAgentRunner(deck)
    agents       = [agent_policy, agent_opp]

    opp_label = "random" if vs_random else "self"
    print(f"Running {n_games} games  [{opp_label}-play]  deck={os.path.basename(deck_path)}")

    rows          = []
    result_counts: defaultdict = defaultdict(int)
    total_sel     = 0
    t_start       = time.time()
    step          = max(1, n_games // 10)

    for i in range(n_games):
        # Reset per-game state (logger, opponent tracking)
        gid = f"g{start_game + i:04d}"
        for ag in agents:
            if hasattr(ag, "new_game"):
                ag.new_game(gid)
        try:
            winner, sels = run_one_game(agents, deck, deck)
        except Exception as exc:
            winner, sels = "error", 0

        result_counts[winner] += 1
        total_sel += sels
        rows.append({"game": i + 1, "winner": winner, "selections": sels})

        if (i + 1) % step == 0:
            elapsed = time.time() - t_start
            print(f"  {i+1:>5}/{n_games}  ({(i+1)/n_games*100:.0f}%)  {elapsed:.1f}s")

    elapsed = time.time() - t_start

    # Write CSV
    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["game", "winner", "selections"])
        writer.writeheader()
        writer.writerows(rows)

    # Print summary
    n = n_games
    p0_wins = result_counts.get("p0", 0)
    p1_wins = result_counts.get("p1", 0)
    timeouts = result_counts.get("timeout", 0)
    errors   = result_counts.get("error", 0)

    print(f"\n{'='*46}")
    print(f"  Results  ({opp_label}-play)")
    print(f"{'='*46}")
    print(f"  Games          : {n}")
    if vs_random:
        print(f"  Policy wins    : {p0_wins:>4}  ({p0_wins/n*100:5.1f}%)")
        print(f"  Random wins    : {p1_wins:>4}  ({p1_wins/n*100:5.1f}%)")
    else:
        print(f"  P0 wins        : {p0_wins:>4}  ({p0_wins/n*100:5.1f}%)")
        print(f"  P1 wins        : {p1_wins:>4}  ({p1_wins/n*100:5.1f}%)")
    print(f"  Timeouts       : {timeouts:>4}  ({timeouts/n*100:5.1f}%)")
    print(f"  Errors         : {errors:>4}  ({errors/n*100:5.1f}%)")
    print(f"  Avg selections : {total_sel/n:.1f}")
    print(f"  Elapsed        : {elapsed:.1f}s  ({elapsed/n*1000:.0f}ms/game)")
    print(f"  Results CSV    : {output_csv}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real PTCG simulation (Linux/WSL)")
    parser.add_argument("--n",    type=int, default=50,
                        help="Number of games (default 50)")
    parser.add_argument("--deck", type=str, default=None,
                        help="Path to deck.csv (default: deck.csv)")
    parser.add_argument("--out",  type=str, default=None,
                        help="Output CSV path")
    parser.add_argument("--vs",   type=str, default="self",
                        choices=["self", "random"],
                        help="Opponent: self-play (default) or random")
    parser.add_argument("--start-game", type=int, default=0,
                        help="Starting game ID offset (default 0 → g0000)")
    args = parser.parse_args()

    deck_path   = args.deck or _DECK_CSV
    stamp       = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.out  or os.path.join(_LOG_DIR, f"real_{stamp}.csv")

    os.makedirs(_LOG_DIR, exist_ok=True)
    run_batch(args.n, deck_path, output_path,
              vs_random=(args.vs == "random"),
              start_game=args.start_game)
