"""
Board state evaluation.
Returns a float: higher = more favourable for the acting player.
Used by policy.py to compare positions after hypothetical actions.
"""
from agent.card_knowledge import CardKnowledge

_WIN_CONDITION_WEIGHT = 0.6  # scale factor applied to plan_progress_score


class BoardEvaluator:
    def __init__(self, knowledge: CardKnowledge):
        self.knowledge    = knowledge
        self._deck_profile: dict = {}

    def set_deck_profile(self, profile: dict):
        self._deck_profile = profile or {}

    def evaluate(self, state: dict) -> float:
        score = 0.0
        score += self._prizes(state)
        score += self._active(state)
        score += self._bench(state)
        score += self._hand(state)
        score += self._energy_distribution(state)
        score += self._deck_safety(state)
        score += self._win_condition_progress(state)
        return score

    # ------------------------------------------------------------------
    # Sub-evaluators
    # ------------------------------------------------------------------

    def _prizes(self, state: dict) -> float:
        my_prizes = state.get("prizes_remaining", 6)
        opp_prizes = state.get("opponent", {}).get("prizes_remaining", 6)
        # +5 per prize we've taken, -5 per prize opponent has taken
        return (6 - my_prizes) * 5.0 - (6 - opp_prizes) * 5.0

    def _active(self, state: dict) -> float:
        active = state.get("active_pokemon", {})
        if not active:
            return -10.0  # no active = immediate loss risk

        max_hp = active.get("max_hp", 1) or 1
        hp_rem = active.get("hp_remaining", 0)
        hp_ratio = hp_rem / max_hp

        score = hp_ratio * 3.0

        cid = str(active.get("card_id", ""))
        role = self.knowledge.get_role(cid)
        if role == "main_attacker":
            score += 5.0
            score += min(active.get("energy_count", 0) * 2.0, 6.0)
        elif role == "setup":
            score += 2.0

        return score

    def _bench(self, state: dict) -> float:
        bench = state.get("bench", [])
        count = len(bench)
        score = count * 1.0
        if count >= 5:
            score -= 2.0  # bench full = can't play more basics
        return score

    def _hand(self, state: dict) -> float:
        h = state.get("hand_count", 0)
        if h == 0:
            return -6.0
        if h <= 2:
            return -2.0
        if h <= 5:
            return 1.0
        return 2.0

    def _energy_distribution(self, state: dict) -> float:
        active = state.get("active_pokemon", {})
        cid = str(active.get("card_id", ""))
        role = self.knowledge.get_role(cid)
        if role == "main_attacker":
            return min(active.get("energy_count", 0) * 1.5, 5.0)
        return 0.0

    def _deck_safety(self, state: dict) -> float:
        deck = state.get("deck_count", 60)
        if deck <= 0:
            return -50.0  # deck-out loss
        if deck <= 5:
            return -8.0
        if deck <= 10:
            return -3.0
        return 0.0

    def _win_condition_progress(self, state: dict) -> float:
        """Bonus for being on track toward the deck's win condition."""
        try:
            from agent.win_condition import evaluate_plan_progress
            return evaluate_plan_progress(state, self._deck_profile, self.knowledge) * _WIN_CONDITION_WEIGHT
        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # Convenience predicates used by policy
    # ------------------------------------------------------------------

    def is_active_in_danger(self, state: dict) -> bool:
        hp = state.get("active_pokemon", {}).get("hp_remaining", 9999)
        return hp < 60
