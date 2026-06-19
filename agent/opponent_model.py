"""
Evaluates the threat posed by the opponent in a given board state.
Used by Planner to subtract opponent threat from the final action score.
"""


class OpponentModel:
    def __init__(self, knowledge, attack_data):
        self.knowledge = knowledge
        self.attack_data = attack_data or {}

    def evaluate_threat(self, state: dict) -> float:
        opp = state.get("opponent", {})
        active = opp.get("active_pokemon", {})
        score = 0.0

        hp = active.get("hp_remaining", 0)
        energy = active.get("energy_count", 0)
        cid = str(active.get("card_id", ""))

        if cid:
            score += self.knowledge.attack_score(cid) * 0.5
            score += min(energy * 2.0, 6.0)

        for p in opp.get("bench", []) or []:
            pcid = str(p.get("card_id", ""))
            if self.knowledge.get_role(pcid) == "main_attacker":
                score += 3.0

        return score
