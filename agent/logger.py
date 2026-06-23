"""
Logs every action decision to logs/game_<id>.jsonl.
Each line is a self-contained JSON object for easy analysis.
"""
import json
import os
import uuid
from datetime import datetime, timezone

try:
    _LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
except NameError:
    _LOG_DIR = '/kaggle_simulations/agent/logs'


class GameLogger:
    def __init__(self, game_id: str = None, deck_name: str = "default", agent_version: str = "v1"):
        try:
            os.makedirs(_LOG_DIR, exist_ok=True)
        except OSError:
            pass  # Read-only filesystem (e.g. Kaggle sandbox) — logging silently disabled
        self.game_id = game_id or str(uuid.uuid4())[:8]
        self.deck_name = deck_name
        self.agent_version = agent_version
        self._turn = 0
        self._path = os.path.join(_LOG_DIR, f"game_{self.game_id}.jsonl")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(
        self,
        state: dict,
        legal_actions: list,
        selected_action,
        selected_score: float,
        reason: str,
        error: str = None,
        time_ms: int = 0,
        result: str = None,
        adv_info: dict = None,
        # Enhanced fields (optional, added by main.py when available)
        select_type: int = None,
        select_context: int = None,
        resolved_card_id: str = None,
        resolved_card_name: str = None,
        planner_used: bool = False,
        rollout_success: bool = False,
        candidates: list = None,
        selected_number: int = None,
        optional_skip_reason: str = None,
        plan_log: dict = None,
        deck_log: dict = None,
    ):
        self._turn += 1
        entry = {
            "game_id":             self.game_id,
            "turn":                self._turn,
            "game_turn":           state.get("turn", 0),
            "state_summary":       self._summarize(state),
            "legal_actions_count": len(legal_actions),
            "legal_option_summary": self._legal_option_summary(legal_actions),
            "selected_action":     selected_action,
            "selected_score":      round(float(selected_score), 4),
            "reason":              reason,
            "error":               error,
            "time_ms":             time_ms,
            "result":              result,
            "prizes_taken":        state.get("prizes_taken", 0),
            "deck_name":           self.deck_name,
            "agent_version":       self.agent_version,
            "ts":                  datetime.now(timezone.utc).isoformat(),
            # Selection metadata
            "select_type":         select_type,
            "select_context":      select_context,
            "resolved_card_id":    resolved_card_id,
            "resolved_card_name":  resolved_card_name,
            "planner_used":           planner_used,
            "rollout_success":        rollout_success,
            "selected_number":        selected_number,
            "optional_skip_reason":   optional_skip_reason,
        }
        # Candidate options (trimmed to top-8 to keep log size manageable)
        if candidates:
            top = sorted(candidates, key=lambda c: -c.get("final_score", c.get("raw_score", 0.0)))[:8]
            entry["top_candidates"] = top

        if plan_log:
            entry["plan"] = plan_log

        if deck_log:
            entry["deck_log"] = deck_log

        # Optional advantage / win-condition fields (only when available)
        if adv_info:
            entry.update({
                "current_phase":              adv_info.get("phase"),
                "archetype":                  adv_info.get("archetype"),
                "card_adv_score":             adv_info.get("card_adv"),
                "board_adv_score":            adv_info.get("board_adv"),
                "energy_adv_score":           adv_info.get("energy_adv"),
                "tempo_adv_score":            adv_info.get("tempo_adv"),
                "prize_adv_score":            adv_info.get("prize_adv"),
                "resource_adv_score":         adv_info.get("resource_adv"),
                "risk_reduction_adv_score":   adv_info.get("risk_reduction_adv"),
                "concept_weighted_adv_score": adv_info.get("total"),
                "plan_progress_score":        adv_info.get("plan_progress"),
                "missing_plan_pieces":        adv_info.get("missing_pieces"),
            })
        self._write(entry)

    def log_result(self, result: str, total_turns: int, opp_cards_seen: list = None):
        entry = {
            "game_id": self.game_id,
            "event": "game_end",
            "result": result,
            "total_turns": total_turns,
            "deck_name": self.deck_name,
            "agent_version": self.agent_version,
            "opp_cards_seen": opp_cards_seen or [],
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._write(entry)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _write(self, entry: dict):
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass  # Silently skip if filesystem is read-only

    @staticmethod
    def _legal_option_summary(legal_actions: list) -> dict:
        counts = {"attack": 0, "end": 0, "attach": 0, "ability": 0, "play": 0, "other": 0}
        for a in legal_actions:
            t = a.get("type")
            if t == 13:
                counts["attack"] += 1
            elif t == 14:
                counts["end"] += 1
            elif t == 8:
                counts["attach"] += 1
            elif t == 10:
                counts["ability"] += 1
            elif t in (3, 7):
                counts["play"] += 1
            else:
                counts["other"] += 1
        return {
            "total": len(legal_actions),
            "attack": counts["attack"],
            "end": counts["end"],
            "attach": counts["attach"],
            "ability": counts["ability"],
            "play": counts["play"],
            "has_attack": counts["attack"] > 0,
            "has_end": counts["end"] > 0,
        }

    @staticmethod
    def _summarize(state: dict) -> dict:
        opp = state.get("opponent", {})
        active = state.get("active_pokemon", {})
        opp_active = opp.get("active_pokemon", {})
        return {
            "turn": state.get("turn", 0),
            "prizes_remaining": state.get("prizes_remaining", 6),
            "deck_count": state.get("deck_count", 0),
            "hand_count": state.get("hand_count", 0),
            "bench_count": len(state.get("bench", [])),
            "active_card_id": active.get("card_id", ""),
            "active_hp": active.get("hp_remaining", 0),
            "active_energy": active.get("energy_count", 0),
            "opp_prizes": opp.get("prizes_remaining", 6),
            "opp_active_card_id": opp_active.get("card_id", ""),
            "opp_active_hp": opp_active.get("hp_remaining", 0),
        }
