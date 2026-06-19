"""
Lookahead planner.

select() replaces the simple greedy policy with a two-stage evaluation:

  Stage 1 — Immediate: score every legal action via PolicyAgent._score()
  Stage 2 — Lookahead: for the top-K immediate candidates, execute each
             action in the search engine and evaluate the resulting board.

Final score formula
-------------------
  final = immediate_score
        + future_score        * FUTURE_WEIGHT
        - future_threat       * THREAT_WEIGHT
        - ko_risk             (current active HP ratio)
        - resource_loss       (discard penalty)
        + prize_race_bonus    (prize differential)

If the search engine is unavailable or the deadline is breached,
_heuristic_future() fills in an approximate future score so that the
greedy policy ranking is still improved by partial lookahead information.

Time budget
-----------
  TOP_K_CANDIDATES  = 5      candidates evaluated with lookahead
  TIME_BUDGET_MS    = 400    total ms budget per call (includes rollout)
  FALLBACK_GUARD_MS = 60     minimum remaining ms needed before rollout
"""

import time
from typing import TYPE_CHECKING, Callable

from agent.card_knowledge import CardKnowledge
from agent.evaluator import BoardEvaluator
from agent.opponent_model import OpponentModel

if TYPE_CHECKING:
    from cg.api import Observation

TOP_K_CANDIDATES  = 5
TIME_BUDGET_MS    = 400
FALLBACK_GUARD_MS = 60
FUTURE_WEIGHT     = 0.7
THREAT_WEIGHT     = 0.8

# OptionType integers (same as policy.py)
_OT_ATTACK  = 13
_OT_EVOLVE  = 9
_OT_ATTACH  = 8
_OT_PLAY    = 7
_OT_DISCARD = 11
_OT_END     = 14


class Planner:
    def __init__(
        self,
        knowledge: CardKnowledge,
        evaluator: BoardEvaluator,
        opp_model: OpponentModel,
        attack_data: dict,
    ):
        self.knowledge   = knowledge
        self.evaluator   = evaluator
        self.opp_model   = opp_model
        self.attack_data = attack_data or {}
        self._rollout_ok: bool | None = None  # lazy

        # Per-call diagnostics — populated by select(), consumed by main.py logging
        self.last_final_scores:  dict[int, float] = {}
        self.last_future_scores: dict[int, float] = {}
        self.last_threat_scores: dict[int, float] = {}
        self.last_rollout_used:  bool             = False

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def select(
        self,
        state: dict,
        opt_dicts: list[dict],
        immediate_scores: list[float],
        max_count: int,
        min_count: int,
        obs: "Observation | None"     = None,
        known_deck: list[int] | None  = None,
        card_table: dict | None       = None,
        board_to_state: Callable | None = None,
    ) -> list[int]:
        """
        Return sorted list of best option indices (len between min_count and max_count).

        Parameters
        ----------
        state           : board state dict from _board_to_state()
        opt_dicts       : all legal actions as plain dicts
        immediate_scores: per-action immediate score from policy._score()
        obs             : typed Observation from to_observation_class()  (for rollout)
        known_deck      : our deck card IDs                              (for rollout)
        card_table      : cardId -> CardData                             (for rollout)
        board_to_state  : _board_to_state() callable                    (for rollout)
        """
        n = len(opt_dicts)
        if min_count == max_count == n:
            return list(range(n))

        deadline = time.time() + TIME_BUDGET_MS / 1000.0

        # ---- Stage 1: pick top-K by immediate score ----
        ranked_imm = sorted(range(n), key=lambda i: -immediate_scores[i])
        top_k      = ranked_imm[:TOP_K_CANDIDATES]

        # ---- Stage 2: rollout for top-K candidates ----
        future_obs_map: dict[int, "Observation"] = {}
        if (
            self._rollout_available()
            and obs is not None
            and known_deck is not None
            and time.time() + FALLBACK_GUARD_MS / 1000.0 < deadline
        ):
            try:
                from agent.rollout import evaluate_candidates
                future_obs_map = evaluate_candidates(
                    obs, known_deck, top_k, card_table or {}, deadline
                )
            except Exception:
                pass

        # ---- Stage 3: compute final score per candidate ----
        # Board-level terms computed once from the current position.
        # We use DELTAS (future - current) so that every candidate is penalised
        # only for the *change* it causes, not for the absolute board value.
        # This prevents top-K candidates from being unfairly disadvantaged vs
        # non-top-K candidates that kept their raw immediate_score intact.
        current_board   = self.evaluator.evaluate(state)
        current_threat  = self.opp_model.evaluate_threat(state)
        ko_risk         = self._ko_risk(state)
        prize_race      = self._prize_race(state)

        final:   dict[int, float] = {}
        futures: dict[int, float] = {}
        threats: dict[int, float] = {}

        for idx in range(n):
            imm = immediate_scores[idx]

            if idx in top_k:
                future_obs = future_obs_map.get(idx)
                future_score, future_threat = self._eval_future(
                    future_obs, state, opt_dicts[idx], board_to_state,
                    current_threat, current_board
                )
                future_delta = future_score - current_board
                threat_delta = future_threat - current_threat
            else:
                # Non-top-K: heuristic delta, zero threat change assumption
                future_delta = self._heuristic_future(opt_dicts[idx])
                threat_delta = 0.0
                future_score = current_board + future_delta
                future_threat = current_threat

            resource = self._resource_loss(state, opt_dicts[idx])

            # Uniform formula for ALL candidates
            final[idx] = (
                imm
                + future_delta * FUTURE_WEIGHT
                - threat_delta * THREAT_WEIGHT
                - ko_risk
                - resource
                + prize_race
            )

            futures[idx] = round(future_score, 3)
            threats[idx] = round(future_threat, 3)

        # Persist for main.py logging
        self.last_final_scores  = final
        self.last_future_scores = futures
        self.last_threat_scores = threats
        self.last_rollout_used  = bool(future_obs_map)

        ranked = sorted(range(n), key=lambda i: -final[i])
        result = ranked[:max_count]

        if len(result) < min_count:
            extras = [i for i in range(n) if i not in result]
            result += extras[: min_count - len(result)]

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rollout_available(self) -> bool:
        if self._rollout_ok is None:
            try:
                from agent.rollout import is_available
                self._rollout_ok = is_available()
            except Exception:
                self._rollout_ok = False
        return self._rollout_ok

    def _eval_future(
        self,
        future_obs: "Observation | None",
        current_state: dict,
        action: dict,
        board_to_state: Callable | None,
        current_threat: float,
        current_board: float = 0.0,
    ) -> "tuple[float, float]":
        """
        Return (future_board_score, future_threat_score).
        Falls back to heuristic estimates if rollout data is unavailable.
        """
        if future_obs is not None and future_obs.current is not None and board_to_state is not None:
            try:
                future_state  = board_to_state(future_obs.current)
                board_score   = self.evaluator.evaluate(future_state)
                threat_score  = self.opp_model.evaluate_threat(future_state)
                return board_score, threat_score
            except Exception:
                pass

        # Heuristic fallback: return current + relative gain so delta stays small
        return current_board + self._heuristic_future(action), current_threat

    def _heuristic_future(self, action: dict) -> float:
        """Approximate future value without rollout, based on action type."""
        t = action.get("type")
        if t == _OT_ATTACK:  return 5.0
        if t == _OT_EVOLVE:  return 4.0
        if t == _OT_ATTACH:  return 3.0
        if t == _OT_PLAY:    return 2.0
        if t == _OT_END:     return 0.0
        return 1.0

    def _ko_risk(self, state: dict) -> float:
        """Penalty when our active Pokemon has low HP (KO risk next turn)."""
        active = state.get("active_pokemon", {})
        hp     = active.get("hp_remaining", 9999)
        max_hp = active.get("max_hp", 1) or 1
        ratio  = hp / max_hp
        if ratio <= 0.25: return 8.0
        if ratio <= 0.50: return 4.0
        return 0.0

    def _resource_loss(self, state: dict, action: dict) -> float:
        """Penalty for discarding high-value cards."""
        if action.get("type") != _OT_DISCARD:
            return 0.0
        cid = str(action.get("cardId") or "")
        return float(self.knowledge.discard_penalty(cid))

    def _prize_race(self, state: dict) -> float:
        """Bonus for being ahead in the prize race."""
        my_prizes  = state.get("prizes_remaining", 6)
        opp_prizes = state.get("opponent", {}).get("prizes_remaining", 6)
        return (opp_prizes - my_prizes) * 2.0
