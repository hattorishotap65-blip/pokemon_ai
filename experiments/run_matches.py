"""
Local batch simulation: runs N mirror matches (AI v1 vs AI v0 — same policy, different seeds).

This is a MOCK environment — it exists only to stress-test the AI infrastructure
(logging, fallback, scoring) until the official Kaggle environment is available.
Card-effect logic here is intentionally simplified.

Usage:
    python experiments/run_matches.py              # 100 games, default deck
    python experiments/run_matches.py --n 500
    python experiments/run_matches.py --deck path/to/deck.csv --output results.csv

Connecting to the official environment later:
    Replace MockMatch.run() with a call to the official env's step() loop.
    The PolicyAgent and GameLogger interfaces stay identical.
"""
import argparse
import csv
import os
import sys
import time
import uuid
from datetime import datetime

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.policy import PolicyAgent
from agent.logger import GameLogger
from agent.fallback import fallback_action

_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
_LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")


# ══════════════════════════════════════════════════════════════
# Mock data structures
# ══════════════════════════════════════════════════════════════

class MockPokemon:
    """Minimal Pokemon representation for mock battles."""

    def __init__(self, card_id: str, name: str, max_hp: int, energy_cost: int = 2):
        self.card_id = card_id
        self.name = name
        self.max_hp = max_hp
        self.hp_remaining = max_hp
        self.energy_count = 0
        self.energy_cost = energy_cost

    def to_dict(self) -> dict:
        attacks = []
        if self.energy_count >= self.energy_cost:
            dmg = 120 if "ex" in self.name.lower() else 60
            attacks.append({"name": "attack", "damage": dmg})
        return {
            "card_id": self.card_id,
            "name": self.name,
            "max_hp": self.max_hp,
            "hp_remaining": self.hp_remaining,
            "energy_count": self.energy_count,
            "available_attacks": attacks,
        }


class MockPlayerState:
    """Game state for one player."""

    def __init__(self, deck_list: list, player_id: str):
        self.player_id = player_id
        self.prizes_remaining = 6
        self.prizes_taken = 0
        self.deck_count = 40
        self.hand_count = 7
        self.bench: list[MockPokemon] = []
        # Track energy by card_id so policy.py can score each type individually
        self._energy_pool = [c for c in deck_list if c.get("card_type") == "Energy"]
        self._energy_idx = 0
        self.energy_hand: list[dict] = []
        for _ in range(min(3, len(self._energy_pool))):
            self._draw_energy()
        self.active = self._pick_active(deck_list)

    def _draw_energy(self):
        if self._energy_pool:
            self.energy_hand.append(
                self._energy_pool[self._energy_idx % len(self._energy_pool)]
            )
            self._energy_idx += 1

    @property
    def energy_in_hand(self) -> int:
        return len(self.energy_hand)

    @staticmethod
    def _pick_active(deck_list: list) -> MockPokemon:
        for c in deck_list:
            if c.get("card_type") == "Pokemon":
                name = c.get("card_name", "Unknown")
                is_ex = "ex" in name.lower()
                hp = 260 if is_ex else 110
                cost = 2 if is_ex else 1
                return MockPokemon(str(c["card_id"]), name, hp, cost)
        return MockPokemon("0", "Bulbasaur", 70, 1)

    def to_state_dict(self, opponent: "MockPlayerState") -> dict:
        return {
            "turn": 0,
            "player": self.player_id,
            "prizes_remaining": self.prizes_remaining,
            "prizes_taken": self.prizes_taken,
            "deck_count": self.deck_count,
            "hand_count": self.hand_count,
            "bench": [p.to_dict() for p in self.bench],
            "active_pokemon": self.active.to_dict() if self.active else {},
            "opponent": {
                "prizes_remaining": opponent.prizes_remaining,
                "active_pokemon": opponent.active.to_dict() if opponent.active else {},
                "bench": [p.to_dict() for p in opponent.bench],
                "deck_count": opponent.deck_count,
            },
        }

    def legal_actions(self) -> list:
        actions = []
        # Attack
        if self.active:
            for atk in self.active.to_dict().get("available_attacks", []):
                actions.append({
                    "type": "attack",
                    "damage": atk["damage"],
                    "attack_name": atk["name"],
                })
        # Attach energy — expose card_id so policy can score each type
        seen_energy = set()
        for e in self.energy_hand:
            cid = str(e.get("card_id", ""))
            if cid not in seen_energy:
                actions.append({
                    "type": "attach_energy",
                    "target": "active",
                    "energy_card_id": cid,
                    "energy_card_name": e.get("card_name", ""),
                })
                seen_energy.add(cid)
        # Retreat
        if self.bench:
            actions.append({"type": "retreat", "bench_index": 0})
        # Always available
        actions.append({"type": "end_turn"})
        return actions


# ══════════════════════════════════════════════════════════════
# Single game runner
# ══════════════════════════════════════════════════════════════

class MockMatch:
    MAX_TURNS = 60  # Per player; total 120 half-turns

    def __init__(
        self,
        agent1: PolicyAgent,
        agent2: PolicyAgent,
        deck1: list,
        deck2: list,
        game_id: str = None,
    ):
        self.agents = [agent1, agent2]
        self.decks = [deck1, deck2]
        self.game_id = game_id or str(uuid.uuid4())[:8]
        self.loggers = [
            GameLogger(game_id=f"{self.game_id}_p1", deck_name="deck_v1", agent_version="v1"),
            GameLogger(game_id=f"{self.game_id}_p2", deck_name="deck_v0", agent_version="v0"),
        ]

    def run(self) -> tuple[str, int]:
        """Returns (winner_id, total_half_turns)."""
        states = [
            MockPlayerState(self.decks[0], "p1"),
            MockPlayerState(self.decks[1], "p2"),
        ]
        current = 0  # 0 or 1

        for half_turn in range(self.MAX_TURNS * 2):
            opp = 1 - current
            result = self._half_turn(
                self.agents[current],
                states[current],
                states[opp],
                self.loggers[current],
                f"p{current+1}",
            )
            if result:
                winner = result
                for i, pid in enumerate(("p1", "p2")):
                    r = "win" if pid == winner else "loss"
                    self.loggers[i].log_result(r, half_turn)
                return winner, half_turn
            current = opp

        # Timeout → draw
        for lg in self.loggers:
            lg.log_result("draw", self.MAX_TURNS * 2)
        return "draw", self.MAX_TURNS * 2

    def _half_turn(
        self,
        agent: PolicyAgent,
        me: MockPlayerState,
        opp: MockPlayerState,
        logger: GameLogger,
        player_id: str,
    ) -> str | None:
        state_dict = me.to_state_dict(opp)
        actions = me.legal_actions()

        t0 = time.time()
        error = None
        selected = None
        score = 0.0
        reason = "unknown"

        try:
            selected, score, reason = agent.select_action(state_dict, actions)
        except Exception as exc:
            error = str(exc)
            selected = fallback_action(actions)
            reason = "fallback"

        elapsed_ms = int((time.time() - t0) * 1000)
        logger.log(state_dict, actions, selected, score, reason, error, elapsed_ms)

        return self._apply(selected, me, opp, player_id)

    @staticmethod
    def _apply(action: dict, me: MockPlayerState, opp: MockPlayerState, player_id: str) -> str | None:
        t = action.get("type", "end_turn")

        if t == "attack":
            damage = action.get("damage", 60)
            if opp.active:
                opp.active.hp_remaining -= damage
                if opp.active.hp_remaining <= 0:
                    me.prizes_remaining -= 1
                    me.prizes_taken += 1
                    if opp.bench:
                        opp.active = opp.bench.pop(0)
                    else:
                        return player_id  # opponent has no Pokemon left
                    if me.prizes_remaining <= 0:
                        return player_id  # all prizes taken

        elif t == "attach_energy":
            energy_cid = str(action.get("energy_card_id", ""))
            if me.active and me.energy_hand:
                # Remove the chosen energy from hand (first matching card_id)
                for i, e in enumerate(me.energy_hand):
                    if not energy_cid or str(e.get("card_id", "")) == energy_cid:
                        me.energy_hand.pop(i)
                        break
                me.active.energy_count += 1
                me._draw_energy()  # replenish from pool

        elif t == "retreat" and me.bench:
            idx = action.get("bench_index", 0)
            me.bench[idx], me.active = me.active, me.bench[idx]

        # Deck-out check
        me.deck_count -= 1
        if me.deck_count <= 0:
            opp_id = "p2" if player_id == "p1" else "p1"
            return opp_id

        return None


# ══════════════════════════════════════════════════════════════
# Deck loader
# ══════════════════════════════════════════════════════════════

def load_deck(deck_csv: str, knowledge_csv: str = None) -> list:
    knowledge: dict[str, dict] = {}
    if knowledge_csv and os.path.exists(knowledge_csv):
        with open(knowledge_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                knowledge[str(row["card_id"])] = row

    deck = []
    with open(deck_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = str(row.get("card_id", ""))
            info = knowledge.get(cid, {})
            count = int(row.get("count", 1))
            for _ in range(count):
                deck.append({
                    "card_id": cid,
                    "card_name": row.get("card_name", info.get("card_name", "")),
                    "card_type": info.get("card_type", "Unknown"),
                    "role": info.get("role", "unknown"),
                })
    return deck


# ══════════════════════════════════════════════════════════════
# Batch runner
# ══════════════════════════════════════════════════════════════

def run_batch(n_games: int, deck_csv: str, output_csv: str):
    knowledge_csv = os.path.join(_PROJECT_ROOT, "data", "card_knowledge.csv")
    deck = load_deck(deck_csv, knowledge_csv)

    agent1 = PolicyAgent()
    agent2 = PolicyAgent()

    rows = []
    p1_wins = p2_wins = draws = errors = total_turns = 0

    print(f"Running {n_games} games  deck={deck_csv}")
    t_start = time.time()

    for i in range(n_games):
        gid = f"g{i:04d}"
        try:
            match = MockMatch(agent1, agent2, deck, deck, game_id=gid)
            winner, turns = match.run()
            total_turns += turns
            if winner == "p1":
                p1_wins += 1
            elif winner == "p2":
                p2_wins += 1
            else:
                draws += 1
            rows.append({"game_id": gid, "winner": winner, "turns": turns, "error": ""})
        except Exception as exc:
            errors += 1
            rows.append({"game_id": gid, "winner": "error", "turns": 0, "error": str(exc)})

        if (i + 1) % max(1, n_games // 10) == 0:
            pct = (i + 1) / n_games * 100
            print(f"  {i+1:>5}/{n_games}  ({pct:.0f}%)")

    elapsed = time.time() - t_start
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["game_id", "winner", "turns", "error"])
        writer.writeheader()
        writer.writerows(rows)

    n = n_games
    avg_turns = total_turns / n if n else 0
    print(f"\n{'='*44}")
    print(f"{'Results':^44}")
    print(f"{'='*44}")
    print(f"  Games played : {n}")
    print(f"  P1 wins      : {p1_wins:>4}  ({p1_wins/n*100:5.1f}%)")
    print(f"  P2 wins      : {p2_wins:>4}  ({p2_wins/n*100:5.1f}%)")
    print(f"  Draws        : {draws:>4}  ({draws/n*100:5.1f}%)")
    print(f"  Errors       : {errors:>4}  ({errors/n*100:5.1f}%)")
    print(f"  Avg turns    : {avg_turns:.1f}")
    print(f"  Elapsed      : {elapsed:.1f}s  ({elapsed/n*1000:.0f}ms/game)")
    print(f"  Results      → {output_csv}")


# ══════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run batch PTCG AI matches locally")
    parser.add_argument("--n", type=int, default=100, help="Number of games (default 100)")
    parser.add_argument("--deck", type=str, default=None, help="Path to deck.csv")
    parser.add_argument("--output", type=str, default=None, help="Output results CSV path")
    args = parser.parse_args()

    deck_path = args.deck or os.path.join(_PROJECT_ROOT, "deck.csv")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or os.path.join(_LOG_DIR, f"results_{stamp}.csv")

    os.makedirs(_LOG_DIR, exist_ok=True)
    run_batch(args.n, deck_path, output_path)
