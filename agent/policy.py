"""
Core action-selection logic.
Scores every legal action and returns the highest-scoring one.
All scoring is rule-based; no ML involved.

OptionType integers (from cabt API docs):
  NUMBER=0, YES=1, NO=2, CARD=3, TOOL_CARD=4, ENERGY_CARD=5, ENERGY=6,
  PLAY=7, ATTACH=8, EVOLVE=9, ABILITY=10, DISCARD=11,
  RETREAT=12, ATTACK=13, END=14, SKILL=15, SPECIAL_CONDITION=16

Scoring priority (highest to lowest):
  winning KO > KO opponent > attack > evolve > ability/skill
  > search/play > energy to main attacker > draw support
  > retreat to save > end turn > unknown
"""
import importlib
from agent.card_knowledge import CardKnowledge
from agent.evaluator import BoardEvaluator

# OptionType enum values (cabt API)
_OT_NUMBER       = 0
_OT_YES          = 1
_OT_NO           = 2
_OT_CARD         = 3
_OT_TOOL_CARD    = 4
_OT_ENERGY_CARD  = 5
_OT_ENERGY_TYPE  = 6
_OT_PLAY         = 7
_OT_ATTACH       = 8
_OT_EVOLVE       = 9
_OT_ABILITY      = 10
_OT_DISCARD      = 11
_OT_RETREAT      = 12
_OT_ATTACK       = 13
_OT_END          = 14
_OT_SKILL        = 15

_TOOL_CARD_IDS = {"1159", "1161"}  # Hero's Cape, Handheld Fan

_ADV_WEIGHT = 0.4   # default; overridden by weights.json if present

# Default weights (used when weights.json is missing or incomplete)
_DEFAULT_WEIGHTS = {
    "advantage_weight": 0.4,
    "energy_to_plan_bonus": 5.0,
    "energy_to_plan_bonus_no_need": 2.0,
    "attack_suppress_penalty": -30.0,
    "retreat_to_better_attacker_bonus": 1100.0,
}


class PolicyAgent:
    def __init__(self):
        self.knowledge    = CardKnowledge()
        self.evaluator    = BoardEvaluator(self.knowledge)
        self.current_plan = None
        self.deck_profile = self._load_deck_profile()
        self.evaluator.set_deck_profile(self.deck_profile)
        self._attack_data, self._attack_full = self._load_attack_data()
        self._weights = self._load_weights()

    # ------------------------------------------------------------------
    # Weights (loaded from data/weights.json, falls back to defaults)
    # ------------------------------------------------------------------

    def _load_weights(self) -> dict:
        import json, os
        w = dict(_DEFAULT_WEIGHTS)
        try:
            _agent_dir = os.path.dirname(os.path.abspath(__file__))
            for path in (
                os.path.join(_agent_dir, "..", "data", "weights.json"),
                "/kaggle_simulations/agent/data/weights.json",
            ):
                if os.path.exists(path):
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    for k in _DEFAULT_WEIGHTS:
                        if k in data:
                            w[k] = float(data[k])
                    return w
        except Exception:
            pass
        return w

    def w(self, key: str) -> float:
        return self._weights.get(key, _DEFAULT_WEIGHTS.get(key, 0.0))

    # ------------------------------------------------------------------
    # Deck profile (loaded once from data/deck_profile.json)
    # ------------------------------------------------------------------

    def _load_deck_profile(self) -> dict:
        import json, os
        try:
            _agent_dir = os.path.dirname(os.path.abspath(__file__))
            for path in (
                os.path.join(_agent_dir, "..", "data", "deck_profile.json"),
                "/kaggle_simulations/agent/data/deck_profile.json",
            ):
                if os.path.exists(path):
                    with open(path, encoding="utf-8") as f:
                        return json.load(f)
        except Exception:
            pass
        return {}

    # ------------------------------------------------------------------
    # Attack data (loaded once from cabt API)
    # ------------------------------------------------------------------

    def _load_attack_data(self) -> tuple:
        """Pre-load attackId → damage and attackId → full attack object."""
        try:
            from cg.api import all_attack
            attacks = list(all_attack())
            data = {a.attackId: a.damage for a in attacks}
            full = {a.attackId: a for a in attacks}
            return data, full
        except Exception:
            pass
        # Legacy fallback paths
        for mod_path in ('kaggle_environments.envs.cabt.api', 'cabt.api', 'cabt'):
            try:
                mod = importlib.import_module(mod_path)
                attacks = mod.all_attack()
                result = {}
                for a in attacks:
                    if isinstance(a, dict):
                        aid, dmg = a.get("attackId"), a.get("damage", 0)
                    else:
                        aid, dmg = getattr(a, "attackId", None), getattr(a, "damage", 0)
                    if aid is not None:
                        result[aid] = int(dmg or 0)
                return result, {}
            except Exception:
                continue
        return None, {}

    def _get_attack_damage(self, attack_id) -> int:
        if attack_id is None or self._attack_data is None:
            return 0
        return self._attack_data.get(attack_id, 0)

    # ------------------------------------------------------------------
    # Dispatcher — uses OptionType integer keys
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Card ID lookup helpers (cabt PLAY/CARD/ATTACH/EVOLVE omit cardId)
    # ------------------------------------------------------------------

    _AREA_HAND = 2  # AreaType.HAND

    def _cid_from_hand(self, action: dict, state: dict) -> str:
        """
        Resolve cardId.  Priority:
          1. resolved_card_id  (set by main._enrich_options before scoring)
          2. explicit cardId field
          3. hand[index] lookup:
             - PLAY (type=7): area is absent but card always comes from hand
             - CARD/ATTACH/EVOLVE with area=HAND
        """
        pre = action.get("resolved_card_id")
        if pre:
            return str(pre)
        cid = str(action.get("cardId") or "")
        if cid:
            return cid
        area     = action.get("area")
        idx      = action.get("index")
        opt_type = action.get("type")
        # PLAY (7) never carries area but is always from hand
        if (opt_type == 7 or area == self._AREA_HAND) and idx is not None:
            hand = state.get("hand") or []
            if idx < len(hand):
                return str(hand[idx])
        return ""

    # ------------------------------------------------------------------
    # Dispatcher — uses OptionType integer keys
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------

    def _dispatch_fn(self, opt_type):
        return {
            _OT_NUMBER:      self._score_number,
            _OT_ATTACK:      self._score_attack,
            _OT_PLAY:        self._score_play,
            _OT_ATTACH:      self._score_attach,
            _OT_EVOLVE:      self._score_evolve,
            _OT_RETREAT:     self._score_retreat,
            _OT_END:         lambda a, s: (0.5, "end_turn"),
            _OT_ABILITY:     lambda a, s: (6.0, "use_ability"),
            _OT_SKILL:       lambda a, s: (6.0, "use_skill"),
            _OT_CARD:        self._score_card,
            _OT_TOOL_CARD:   self._score_card,
            _OT_ENERGY_CARD: self._score_card,
            _OT_ENERGY_TYPE: lambda a, s: (3.0, "energy_type"),
            _OT_DISCARD:     self._score_discard,
            _OT_YES:         lambda a, s: (3.0, "yes"),
            _OT_NO:          lambda a, s: (1.0, "no"),
        }.get(opt_type)

    def _score_with_breakdown(self, action: dict, state: dict) -> tuple:
        """
        Returns (total_score, reason, breakdown_dict).

        breakdown_dict keys:
          type_score  — score from the type-specific scorer
          adv_score   — concept-weighted advantage contribution
          rule_bonus  — deck-specific bonus from ionos_rules.score_bonus()
          rule_reason — reason string for the rule bonus (empty if no bonus)
        """
        fn = self._dispatch_fn(action.get("type"))
        type_score, reason = fn(action, state) if fn else (0.1, "unknown_action")

        adv = self._advantage_score(action, state)

        rule_bonus  = 0.0
        rule_reason = ""
        try:
            from agent.ionos_rules import score_bonus
            rule_bonus, rule_reason = score_bonus(action, state, self.knowledge)
            if rule_bonus != 0.0 and abs(rule_bonus) >= 3.0:
                reason = rule_reason
        except Exception:
            pass

        turn_rule_score  = 0.0
        turn_rule_reason = ""
        try:
            from agent.turn_rule_engine import rule_score_option
            _opt_dicts = getattr(self, "_current_opt_dicts", None)
            if _opt_dicts:
                turn_rule_score, turn_rule_reason = rule_score_option(
                    action, state, {"option": _opt_dicts}
                )
        except Exception:
            pass

        kilowattrel_ability_score  = 0.0
        kilowattrel_ability_reason = ""
        voltorb_attack_score  = 0.0
        voltorb_attack_reason = ""
        voltorb_safety_score  = 0.0
        voltorb_safety_reason = ""
        try:
            from agent.ionos_rules import (
                score_kilowattrel_ability, score_voltorb_attack, score_voltorb_safety_penalty,
            )
            _opt_dicts2 = getattr(self, "_current_opt_dicts", None)
            _syn_sel    = {"option": _opt_dicts2} if _opt_dicts2 else None
            kilowattrel_ability_score, kilowattrel_ability_reason = score_kilowattrel_ability(
                action, state, _syn_sel
            )
            voltorb_attack_score, voltorb_attack_reason = score_voltorb_attack(
                action, state, _syn_sel
            )
            voltorb_safety_score, voltorb_safety_reason = score_voltorb_safety_penalty(
                action, state, _syn_sel
            )
            for sc, sr in [(kilowattrel_ability_score, kilowattrel_ability_reason),
                           (voltorb_attack_score, voltorb_attack_reason),
                           (voltorb_safety_score, voltorb_safety_reason)]:
                if sc != 0.0 and abs(sc) >= 3.0:
                    reason = sr
        except Exception:
            pass

        total = (type_score + adv + rule_bonus + turn_rule_score
                 + kilowattrel_ability_score
                 + voltorb_attack_score + voltorb_safety_score)
        breakdown = {
            "type_score":               round(type_score, 3),
            "adv_score":                round(adv, 3),
            "rule_bonus":               round(rule_bonus, 3),
            "rule_reason":              rule_reason,
            "turn_rule_score":          round(turn_rule_score, 3),
            "turn_rule_reason":         turn_rule_reason,
            "kilowattrel_ability_score":  round(kilowattrel_ability_score, 3),
            "kilowattrel_ability_reason": kilowattrel_ability_reason,
            "voltorb_attack_score":     round(voltorb_attack_score, 3),
            "voltorb_attack_reason":    voltorb_attack_reason,
            "voltorb_safety_score":     round(voltorb_safety_score, 3),
            "voltorb_safety_reason":    voltorb_safety_reason,
        }
        return total, reason, breakdown

    def _score(self, action: dict, state: dict):
        total, reason, _ = self._score_with_breakdown(action, state)
        return total, reason

    def _advantage_score(self, action: dict, state: dict) -> float:
        try:
            from agent.advantage import evaluate_total_advantage
            from agent.win_condition import detect_current_phase
            phase = detect_current_phase(state)
            return evaluate_total_advantage(
                action, state, self.knowledge, phase, self.deck_profile
            ) * self.w("advantage_weight")
        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # Terminal-action suppression (Attack is turn-ending)
    # ------------------------------------------------------------------

    def _has_unresolved_pre_attack(
        self, plan, state: dict, opt_dicts: list
    ) -> bool:
        """
        Return True when a pre-attack action is both required by the plan
        and actually available in the current legal options.

        If none of the required actions are available, attacking is fine —
        suppressing would cause the agent to do nothing.
        """
        for req in (plan.pre_attack_requirements or []):
            if req == "boss":
                target_cid = str(plan.target_card_id or "")
                opp_active_cid = str(
                    state.get("opponent", {})
                         .get("active_pokemon", {})
                         .get("card_id", "")
                )
                if target_cid and opp_active_cid != target_cid:
                    gust_in_options = any(
                        o.get("type") == _OT_PLAY
                        and self.knowledge.has_tag(
                            str(o.get("resolved_card_id") or ""), "gust"
                        )
                        for o in opt_dicts
                    )
                    if gust_in_options:
                        return True
            elif req == "switch":
                if not state.get("retreated"):
                    if any(o.get("type") == _OT_RETREAT for o in opt_dicts):
                        return True
            elif req == "energy":
                if not state.get("energy_attached"):
                    if any(o.get("type") == _OT_ATTACH for o in opt_dicts):
                        return True

        return False

    def suppress_attack_if_pre_required(
        self, state: dict, opt_dicts: list, scores: list
    ) -> list:
        """
        If pre-attack actions are unmet and achievable, reduce all ATTACK option
        scores by 30 so they fall below every PRE_ATTACK alternative.

        Returns a (possibly modified) copy of the scores list.
        """
        plan = self.current_plan
        if plan is None or not plan.has_plan:
            return scores
        if not self._has_unresolved_pre_attack(plan, state, opt_dicts):
            return scores
        scores = list(scores)
        for i, o in enumerate(opt_dicts):
            if isinstance(o, dict) and o.get("type") == _OT_ATTACK:
                scores[i] += self.w("attack_suppress_penalty")
        return scores

    # ------------------------------------------------------------------
    # Per-type scorers
    # ------------------------------------------------------------------

    def _score_number(self, action: dict, state: dict):
        """
        Score a NUMBER option (OptionType=0, SelectType=COUNT).

        Each option in a COUNT selection carries a different `number` value.
        We score higher numbers higher, with adjustments per context:
          DRAW_COUNT               — prefer max; penalise emptying deck
          DAMAGE_COUNTER_COUNT     — prefer max (more damage spread)
          REMOVE_DAMAGE_COUNTER_COUNT — prefer max (more healing)
          generic                  — prefer any non-zero, then higher
        """
        number = int(action.get("number") or 0)
        ctx    = action.get("select_context")

        if ctx == self._CTX_DRAW_COUNT:
            deck = state.get("deck_count", 20)
            if number == 0:
                return 0.1, "draw_zero"
            # Penalise drawing that would empty the deck (deck-out loss next turn)
            if deck > 0 and number >= deck:
                return float(number) - 15.0, f"draw_risk_{number}"
            return float(number) + 1.0, f"draw_{number}"

        if ctx == self._CTX_DAMAGE_COUNTER_COUNT:
            # Maximise damage counters placed; KO optimisation can be layered on top
            # in a later step once we track which target was selected.
            return float(number) + 1.0, f"damage_counter_{number}"

        if ctx == self._CTX_REMOVE_DAMAGE_COUNTER_COUNT:
            return float(number) + 1.0, f"remove_counter_{number}"

        # Generic count context: prefer any non-zero value, higher is better
        return float(number) + 0.5, f"count_{number}"

    @staticmethod
    def _attack_target_matches_plan(state: dict, plan) -> bool:
        """
        True when the opponent's current active Pokemon is the planned KO target.
        Checks card_id; if serial is available in the plan, also verifies it.
        """
        if plan.target_card_id is None:
            return False
        opp_active = state.get("opponent", {}).get("active_pokemon", {})
        return str(opp_active.get("card_id", "")) == str(plan.target_card_id)

    def _score_attack(self, action: dict, state: dict):
        score  = 10.0
        reason = "attack"

        opp    = state.get("opponent", {}).get("active_pokemon", {})
        opp_hp = opp.get("hp_remaining", 9999)

        attack_id = action.get("attackId")
        damage = self._get_attack_damage(attack_id)

        active_cid = str(state.get("active_pokemon", {}).get("card_id", ""))
        try:
            from agent.effect_engine import estimate_attack_damage
            if active_cid in ("265", "269", "271"):
                damage, _ = estimate_attack_damage(int(active_cid), state)
        except Exception:
            pass

        try:
            from agent.damage_predictor import predict_attack_damage, format_prediction
            my_active = state.get("active_pokemon", {})
            pred = predict_attack_damage(my_active, opp, state)
            if pred["predicted_damage"] == 0 and pred["raw_damage"] > 0:
                score -= 500.0
                reason = format_prediction(pred)
                return score, reason
            if pred["can_ko"] and pred["predicted_damage"] > 0:
                damage = max(damage, pred["predicted_damage"])
        except Exception:
            pass

        if damage > 0 and damage >= opp_hp:
            score += 20.0
            reason = "ko_opponent"
            if state.get("opponent", {}).get("prizes_remaining", 6) == 1:
                score += 30.0
                reason = "winning_ko"
        elif damage > 0 and opp_hp - damage <= 30:
            score += 5.0
            reason = "almost_ko"

        plan = self.current_plan
        if plan is not None and plan.has_plan and attack_id == plan.planned_attack_id:
            score += 5.0
            if plan.ko_expected:
                if self._attack_target_matches_plan(state, plan):
                    # Target is the planned one → full KO bonus
                    score += 3.0
                    reason = "plan_ko_match"
                else:
                    # Attacking the wrong target while a KO plan exists → penalise
                    score -= 6.0
                    reason = "plan_ko_mismatch"
            else:
                reason = "plan_" + reason

        return score, reason

    def _score_play(self, action: dict, state: dict):
        """
        OptionType.PLAY (7) covers both Pokemon-to-bench and Trainer card play.
        Dispatch further based on card_knowledge card_type.
        """
        cid  = self._cid_from_hand(action, state)
        info = self.knowledge.get(cid)
        if info and info.get("card_type") == "Pokemon":
            return self._score_play_pokemon(action, state)
        return self._score_play_trainer(action, state)

    def _score_play_pokemon(self, action: dict, state: dict):
        cid         = self._cid_from_hand(action, state)
        role        = self.knowledge.get_role(cid)
        pw          = self.knowledge.get_priority_weight(cid)
        bench_count = len(state.get("bench", []))

        base = {
            "main_attacker":   8.0,
            "basic_attacker":  8.0,
            "evolution_base":  8.0,
            "basic_setup":     7.0,
            "setup":           7.0,
            "search_engine":   7.0,
            "sub_attacker":    6.0,
            "engine_attacker": 8.0,
        }.get(role, 3.0)

        score = base + pw

        _URGENT_ROLES = {"main_attacker", "basic_attacker", "evolution_base",
                         "basic_setup", "setup", "engine_attacker"}
        if bench_count <= 1 and role in _URGENT_ROLES:
            score += 8.0
        if bench_count >= 5:
            score = -20.0

        return score, f"play_pokemon_{role}"

    def _is_tool_card(self, cid: str) -> bool:
        """True when cid is a Tool card (static list or knowledge-based)."""
        if cid in _TOOL_CARD_IDS:
            return True
        return (
            self.knowledge.get_role(cid) == "tool"
            or self.knowledge.has_tag(cid, "tool")
        )

    def _score_attach(self, action: dict, state: dict):
        """Dispatch ATTACH (type=8) to energy or tool scorer based on card ID."""
        cid = self._cid_from_hand(action, state)
        if cid and self._is_tool_card(cid):
            return self._score_attach_tool(action, state)
        return self._score_attach_energy(action, state)

    def _score_attach_tool(self, action: dict, state: dict):
        """Score attaching a tool card (Handheld Fan = 1161)."""
        cid = self._cid_from_hand(action, state)

        target_area = action.get("inPlayArea")
        target_idx  = action.get("inPlayIndex")

        if target_area == 4:   # ACTIVE
            t_cid = str(state.get("active_pokemon", {}).get("card_id", ""))
        elif target_area == 5 and target_idx is not None:   # BENCH
            bench = state.get("bench", [])
            t_cid = str(bench[target_idx].get("card_id", "")) if target_idx < len(bench) else ""
        else:
            t_cid = ""

        role = self.knowledge.get_role(t_cid) if t_cid else ""
        is_bad_target = role in ("evolution_base", "basic_setup")

        if cid == "1161":   # Handheld Fan — enables free retreat from Active
            if is_bad_target:
                return -8.0, "tool_handheld_fan_bad_target"
            return 2.0, "tool_handheld_fan_generic"

        if cid == "1159":   # Hero's Cape — adds +50 HP
            if role == "main_attacker":
                return 5.0, "tool_heroes_cape_main_attacker"
            if is_bad_target:
                return -8.0, "tool_heroes_cape_bad_target"
            return 2.0, "tool_heroes_cape_generic"

        # Generic tool: prefer main attacker, avoid setup/support
        if role == "main_attacker":
            return 5.0, "tool_generic_main_attacker"
        if is_bad_target:
            return -5.0, "tool_generic_bad_target"
        return 4.0, "tool_attach_generic"

    def _score_attach_energy(self, action: dict, state: dict):
        if state.get("energy_attached"):
            return 0.1, "energy_already_attached"

        energy_cid = self._cid_from_hand(action, state)

        e_attach = self.knowledge.energy_attach_score(energy_cid) if energy_cid else 7
        e_risk   = self.knowledge.risk_score(energy_cid)          if energy_cid else 0
        score    = float(e_attach) - float(e_risk) * 0.5
        reason   = "attach_energy"

        # Determine WHICH Pokemon we're attaching to (active vs bench)
        in_play_area  = action.get("inPlayArea")
        in_play_index = action.get("inPlayIndex")

        if in_play_area == 4:  # ACTIVE
            target_pokemon = state.get("active_pokemon", {})
        elif in_play_area == 5 and in_play_index is not None:  # BENCH
            bench = state.get("bench", [])
            target_pokemon = bench[in_play_index] if in_play_index < len(bench) else {}
        else:
            target_pokemon = state.get("active_pokemon", {})

        pokemon_cid = str(target_pokemon.get("card_id", ""))
        role        = self.knowledge.get_role(pokemon_cid)
        hp          = target_pokemon.get("hp_remaining", 9999)

        if role == "main_attacker":
            score  += 2.0
            reason  = "energy_to_main_attacker"
        elif role in ("basic_setup", "evolution_base", "evolve_bridge"):
            score  -= 2.0
            reason  = "energy_to_setup"

        # Restricted energy (e.g. Team Rocket's) — very low score unless correct type
        if self.knowledge.get_role(energy_cid) == "energy_restricted":
            score  = 1.0
            reason = "energy_restricted_mismatch"

        if hp < 30:
            score  = 1.5
            reason = "energy_risky_low_hp"

        plan = self.current_plan
        if plan is not None and plan.has_plan:
            attaching_to_planned = (
                (plan.attacker_active and in_play_area == 4)
                or (not plan.attacker_active and in_play_area == 5
                    and in_play_index == plan.attacker_idx)
            )
            if attaching_to_planned:
                score += self.w("energy_to_plan_bonus") if plan.need_energy else self.w("energy_to_plan_bonus_no_need")
                reason = "energy_for_plan"

        return score, reason

    def _score_play_trainer(self, action: dict, state: dict):
        cid  = self._cid_from_hand(action, state)
        role = self.knowledge.get_role(cid)
        pw   = self.knowledge.get_priority_weight(cid)

        hand       = state.get("hand_count", 5)
        opp_prizes = state.get("opponent", {}).get("prizes_remaining", 6)

        # Supporter: only one per turn
        if state.get("supporter_played") and self.knowledge.get_sub_role(cid) == "supporter":
            return 0.1, "supporter_already_played"

        base = {
            "search":         7.0,
            "draw":           6.0,
            "draw_refresh":   6.0,   # e.g. Lillie's Determination
            "energy_search":  7.0,
            "energy_accel":   6.0,   # e.g. Crispin, Waitress
            "evolve":         8.0,
            "disruption":     5.0,
            "removal":        5.0,
            "retreat":        4.0,
            "switch":         4.0,
            "energy_support": 5.0,
            "recovery":       3.0,
            "tool":           4.0,
            "heal":           4.0,   # e.g. Cook
            "healing":        4.0,
        }.get(role, 3.0)

        score = base + pw

        if role == "disruption" and opp_prizes <= 2:
            score += 3.0

        if role == "draw" and hand >= 6:
            score -= 2.0

        # Conditional-draw (e.g. Bianca's Devotion) needs search_engine on bench
        if role == "draw" and self.knowledge.get_sub_role(cid) == "conditional_draw":
            bench = state.get("bench", [])
            has_enabler = any(
                self.knowledge.get_role(str(p.get("card_id", ""))) == "search_engine"
                for p in bench
            )
            if not has_enabler:
                return 0.5, "conditional_draw_no_enabler"

        plan = self.current_plan
        if plan is not None and plan.has_plan:
            if plan.need_boss and self.knowledge.has_tag(cid, "gust"):
                score += 5.0
            if plan.need_switch and role == "switch":
                score += 4.0

        return score, f"trainer_{role}"

    def _score_evolve(self, action: dict, state: dict):
        cid  = self._cid_from_hand(action, state)
        role = self.knowledge.get_role(cid)
        pw   = self.knowledge.get_priority_weight(cid)

        base = {"main_attacker": 12.0, "search_engine": 10.0}.get(role, 7.0)
        return base + pw, f"evolve_to_{role}"

    def _score_retreat(self, action: dict, state: dict):
        if state.get("retreated"):
            return 0.1, "already_retreated"

        plan = self.current_plan
        if plan is not None and plan.has_plan and plan.need_switch:
            return 7.0, "retreat_for_plan"

        if self.evaluator.is_active_in_danger(state):
            hp = state.get("active_pokemon", {}).get("hp_remaining", 9999)
            if hp < 30:
                return 7.0, "retreat_save_pokemon"
            return 3.5, "retreat_low_hp"
        return 1.0, "retreat_unnecessary"

    # SelectContext integer constants (mirrors cg/api.py SelectContext)
    _CTX_SETUP_ACTIVE    = 1
    _CTX_SETUP_BENCH     = 2
    _CTX_SWITCH          = 3
    _CTX_TO_ACTIVE       = 4
    _CTX_TO_BENCH        = 5
    _CTX_TO_HAND         = 7
    _CTX_DISCARD         = 8
    # Damage counter / direct damage target selection
    _CTX_DAMAGE_COUNTER          = 13  # Select Pokémon to place damage counters on
    _CTX_DAMAGE_COUNTER_ANY      = 14  # Same, free placement (any Pokémon)
    _CTX_DAMAGE                  = 15  # Select Pokémon to deal direct damage to
    _CTX_REMOVE_DAMAGE_COUNTER   = 16  # Select Pokémon to remove damage counters from
    _CTX_HEAL            = 17
    _CTX_EVOLVES_TO      = 19
    _CTX_ATTACH_FROM              = 21  # "Select the Pokémon to attach the card to"
    _CTX_ATTACH_TO                = 22  # "Select the card to attach to the Pokémon"
    # SelectType.COUNT (8) — NUMBER options
    _CTX_DRAW_COUNT               = 38  # How many cards to draw
    _CTX_DAMAGE_COUNTER_COUNT     = 39  # How many damage counters to place
    _CTX_REMOVE_DAMAGE_COUNTER_COUNT = 40  # How many damage counters to remove

    def _score_card(self, action: dict, state: dict):
        """
        CARD / TOOL_CARD / ENERGY_CARD: dispatch by select_context so the
        same card is evaluated differently depending on what we're doing with it.
        """
        ctx = action.get("select_context")

        if ctx == self._CTX_TO_HAND:
            return self._score_card_to_hand(action, state)
        if ctx == self._CTX_DISCARD:
            return self._score_card_discard(action, state)
        if ctx == self._CTX_EVOLVES_TO:
            return self._score_card_evolves_to(action, state)
        if ctx == self._CTX_ATTACH_FROM:
            return self._score_card_attach_target(action, state)
        if ctx == self._CTX_ATTACH_TO:
            return self._score_card_attach_select(action, state)
        if ctx in (self._CTX_SWITCH, self._CTX_TO_ACTIVE):
            return self._score_card_to_active(action, state)
        if ctx == self._CTX_TO_BENCH:
            return self._score_card_to_bench(action, state)
        if ctx in (self._CTX_DAMAGE_COUNTER, self._CTX_DAMAGE_COUNTER_ANY,
                   self._CTX_DAMAGE):
            return self._score_card_damage_target(action, state)
        if ctx == self._CTX_REMOVE_DAMAGE_COUNTER:
            return self._score_card_remove_damage(action, state)
        if ctx == self._CTX_HEAL:
            return self._score_card_heal(action, state)
        if ctx in (self._CTX_SETUP_ACTIVE, self._CTX_SETUP_BENCH):
            return self._score_card_setup(action, state)

        # Generic fallback — keeps old behaviour for unknown contexts
        cid   = self._cid_from_hand(action, state)
        if not cid:
            return 3.0, "card_generic"
        role  = self.knowledge.get_role(cid)
        pw    = self.knowledge.get_priority_weight(cid)
        use_s = self.knowledge.use_score(cid)
        return float(use_s) + pw, f"card_{role}"

    # ── Context-specific card scorers ──────────────────────────

    def _score_card_to_hand(self, action: dict, state: dict):
        """Pick card to add to hand (search effect result)."""
        cid  = self._cid_from_hand(action, state)
        if not cid:
            return 3.0, "to_hand_generic"
        role   = self.knowledge.get_role(cid)
        pw     = self.knowledge.get_priority_weight(cid)
        score  = float(self.knowledge.search_score(cid)) + pw

        # Boost for cards we urgently need
        if role == "main_attacker":
            score += 4.0
        elif role in ("evolution_base", "basic_setup"):
            score += 3.0
        elif role in ("search", "energy_search", "evolve"):
            score += 2.0

        # Penalise cards we already have enough of
        hand = state.get("hand_count", 0)
        if role == "energy" and hand >= 5:
            score -= 2.0

        return score, f"to_hand_{role}"

    def _score_card_discard(self, action: dict, state: dict):
        """Pick card to discard — low penalty = good discard choice."""
        cid = self._cid_from_hand(action, state)
        if not cid:
            return 5.0, "discard_generic"
        penalty = self.knowledge.discard_penalty(cid)
        role    = self.knowledge.get_role(cid)

        # Never willingly discard main attacker / evolutions / key support
        if role in ("main_attacker",) or self.knowledge.has_tag(cid, "ex"):
            return 0.5, f"discard_keep_{role}"
        if role in ("evolution_base", "basic_setup"):
            return 1.0, "discard_keep_evoline"
        if self.knowledge.discard_penalty(cid) >= 7:
            return 1.5, "discard_keep_highvalue"

        # Low discard_penalty = good to discard
        return 10.0 - float(penalty), f"discard_{role}"

    def _score_card_evolves_to(self, action: dict, state: dict):
        """Pick the card that the active/bench Pokemon will evolve INTO."""
        cid  = self._cid_from_hand(action, state)
        if not cid:
            return 5.0, "evolve_to_generic"
        role = self.knowledge.get_role(cid)
        pw   = self.knowledge.get_priority_weight(cid)
        base = {"main_attacker": 12.0, "search_engine": 10.0}.get(role, 7.0)
        return base + pw, f"evolve_to_{role}"

    def _score_card_attach_target(self, action: dict, state: dict):
        """
        ATTACH_FROM (ctx=21): 'Select the Pokémon to attach the card to.'
        Options are Pokémon on field; their position is given by area/index.
        """
        area = action.get("area")
        idx  = action.get("index")

        target_cid    = ""
        target_energy = 0
        if area == 4:  # ACTIVE
            t_mon         = state.get("active_pokemon") or {}
            target_cid    = str(t_mon.get("card_id", ""))
            target_energy = t_mon.get("energy_count", 0)
        elif area == 5 and idx is not None:  # BENCH
            bench = state.get("bench") or []
            if idx < len(bench):
                t_mon         = bench[idx]
                target_cid    = str(t_mon.get("card_id", ""))
                target_energy = t_mon.get("energy_count", 0)

        if not target_cid:
            return 3.0, "attach_target_generic"

        # Deck-specific scoring takes priority over generic role scoring.
        # In Iono's deck, attachment is always Lightning (single energy type).
        try:
            from agent.ionos_rules import (
                score_energy_attachment, score_bellibolt_energy_attach,
                _bellibolt_on_field, _LIGHTNING_ENERGY,
            )
            if _bellibolt_on_field(state):
                esc, ereason = score_bellibolt_energy_attach(
                    _LIGHTNING_ENERGY, target_cid, state, target_energy)
            else:
                esc, ereason = score_energy_attachment(
                    _LIGHTNING_ENERGY, target_cid, state, target_energy)
            if ereason:
                return esc, f"attach_target_ionos|{ereason}"
        except Exception:
            pass

        # Generic fallback
        role   = self.knowledge.get_role(target_cid)
        pw     = self.knowledge.get_priority_weight(target_cid)
        energy = self.knowledge.energy_attach_score(target_cid)
        score  = float(energy) + pw

        if role == "main_attacker":
            score += 4.0
        elif role in ("evolution_base", "basic_setup"):
            score -= 1.0

        return score, f"attach_target_{role}"

    def _score_card_attach_select(self, action: dict, state: dict):
        """
        ATTACH_TO (ctx=22): 'Select the card to attach to the Pokémon.'
        Options are cards (from hand/elsewhere); scored by the card's attach value.
        """
        cid = self._cid_from_hand(action, state)
        if not cid:
            return 3.0, "attach_select_generic"
        role   = self.knowledge.get_role(cid)
        pw     = self.knowledge.get_priority_weight(cid)
        attach = self.knowledge.energy_attach_score(cid)
        return float(attach) + pw, f"attach_select_{role}"

    def _score_card_to_active(self, action: dict, state: dict):
        """Pick Pokemon to put into Active Spot (switch / promote)."""
        cid = self._cid_from_hand(action, state)
        if not cid:
            # SWITCH context: option IS a bench Pokemon (area=BENCH, not HAND)
            area = action.get("area")
            idx  = action.get("index")
            if area == 5 and idx is not None:
                bench = state.get("bench", [])
                if idx < len(bench):
                    cid = str(bench[idx].get("card_id", ""))
        if not cid:
            return 3.0, "to_active_generic"
        role   = self.knowledge.get_role(cid)
        pw     = self.knowledge.get_priority_weight(cid)

        base = {"main_attacker": 10.0, "sub_attacker": 7.0}.get(role, 3.0)
        score = base + pw

        # Bonus: the candidate has enough energy to attack immediately
        # We can check energy from the bench slot but don't have easy access here;
        # use attack_score as a proxy for readiness
        score += float(self.knowledge.attack_score(cid)) * 0.3

        # Penalise if it's a setup Pokemon (don't want it getting KO'd)
        if role in ("evolution_base", "basic_setup"):
            score = 1.5

        return score, f"to_active_{role}"

    def _score_card_to_bench(self, action: dict, state: dict):
        """Pick Pokemon to put onto Bench."""
        cid  = self._cid_from_hand(action, state)
        if not cid:
            return 3.0, "to_bench_generic"
        role  = self.knowledge.get_role(cid)
        pw    = self.knowledge.get_priority_weight(cid)
        score = float(self.knowledge.bench_score(cid)) + pw

        if len(state.get("bench", [])) >= 5:
            score = 0.5   # bench full

        return score, f"to_bench_{role}"

    def _score_card_heal(self, action: dict, state: dict):
        """
        HEAL (ctx=17): 'Select the Pokémon to heal.'
        Options are Pokémon on field; their position is given by area/index
        (NOT inPlayArea/inPlayIndex — those are for ATTACH type=8 options).
        """
        area = action.get("area")
        idx  = action.get("index")

        if area == 4:  # ACTIVE
            target = state.get("active_pokemon", {})
        elif area == 5 and idx is not None:  # BENCH
            bench = state.get("bench", [])
            target = bench[idx] if idx < len(bench) else {}
        else:
            return 3.0, "heal_unknown"

        max_hp = target.get("max_hp", 1) or 1
        hp_rem = target.get("hp_remaining", max_hp)
        damage = max_hp - hp_rem
        role   = self.knowledge.get_role(str(target.get("card_id", "")))

        if damage == 0:
            return 0.5, "heal_undamaged"  # don't waste heal on full-HP pokemon

        base = 8.0 if role == "main_attacker" else 5.0
        return base + damage / 10.0, f"heal_{role}"

    def _score_card_damage_target(self, action: dict, state: dict):
        """
        DAMAGE_COUNTER (13), DAMAGE_COUNTER_ANY (14), DAMAGE (15):
        Select which Pokémon to place damage counters / deal damage to.

        Priority order:
          1. KO possible with remaining counters     (+50, +10 if Dwebble)
          2. Dwebble (pre-evolution — stop Crustle)  (+30)
          3. Very low HP (≤40)                       (+20)
          4. Low HP (≤80)                            (+10)
          5. Main attacker                           (+15)
          6. Ex Pokémon (2+ prizes)                  (+10)
          7. Bench position bonus                    (+3)
        Penalise own Pokémon (DAMAGE_COUNTER_ANY only): score = 0.5
        """
        area      = action.get("area")
        idx       = action.get("index")
        p_idx     = action.get("playerIndex")
        remain_dc = int(action.get("remain_damage_counter") or 0)

        my_idx  = state.get("your_index", 0)
        opp_idx = 1 - my_idx

        # Determine ownership: assume opponent unless playerIndex says otherwise
        is_own = (p_idx is not None and int(p_idx) == my_idx)

        if is_own:
            # Placing counters on own Pokémon — very rare, strongly penalise
            return 0.5, "damage_own"

        # Opponent's Pokémon
        opp = state.get("opponent", {})
        if area == 4:          # ACTIVE
            target = opp.get("active_pokemon", {})
        elif area == 5 and idx is not None:   # BENCH
            bench = opp.get("bench", [])
            target = bench[idx] if idx < len(bench) else {}
        else:
            return 3.0, "damage_target_generic"

        cid    = str(target.get("card_id", ""))
        hp     = int(target.get("hp_remaining") or 9999)
        role   = self.knowledge.get_role(cid)
        is_ex  = self.knowledge.has_tag(cid, "ex")

        score  = 5.0
        reason = "damage_target"

        # 1. KO target with available damage counters
        if remain_dc > 0 and hp > 0 and hp <= remain_dc * 10:
            score  += 50.0
            reason  = "damage_target_ko"

        # 2–3. Low HP targets (can be KO'd later)
        if hp <= 40:
            score  += 20.0
            if reason == "damage_target":
                reason = "damage_target_hp_40"
        elif hp <= 80:
            score  += 10.0
            if reason == "damage_target":
                reason = "damage_target_hp_80"

        # 5. Main attacker
        if role == "main_attacker":
            score  += 15.0
            if reason == "damage_target":
                reason = "damage_target_main_attacker"

        # 6. Ex Pokémon (extra prizes)
        if is_ex:
            score  += 10.0
            if reason == "damage_target":
                reason = "damage_target_ex"

        # 7. Bench position bonus (prefer spreading to bench)
        if area == 5:
            score += 3.0

        return score, reason

    def _score_card_remove_damage(self, action: dict, state: dict):
        """
        REMOVE_DAMAGE_COUNTER (16): Select which of our Pokémon to remove
        damage counters from.

        Priority: save main attacker in danger > Pokémon near KO > most damaged
        """
        area = action.get("area")
        idx  = action.get("index")

        if area == 4:          # ACTIVE
            target = state.get("active_pokemon", {})
        elif area == 5 and idx is not None:   # BENCH
            bench = state.get("bench", [])
            target = bench[idx] if idx < len(bench) else {}
        else:
            return 3.0, "remove_damage_generic"

        cid    = str(target.get("card_id", ""))
        hp     = int(target.get("hp_remaining") or 9999)
        max_hp = int(target.get("max_hp") or 100) or 100
        damage = max_hp - hp
        role   = self.knowledge.get_role(cid)

        if damage == 0:
            return 0.5, "remove_damage_undamaged"

        score  = 5.0 + damage / 10.0
        reason = "remove_damage"

        if hp <= 30:
            score  += 20.0
            reason  = "remove_damage_save_ko"
        elif hp <= 60:
            score  += 10.0
            reason  = "remove_damage_low_hp"

        if role == "main_attacker":
            score  += 10.0
            reason  = "remove_damage_main_attacker"

        return score, reason

    def _score_card_setup(self, action: dict, state: dict):
        """Pick starting active / bench Pokemon during game setup."""
        cid  = self._cid_from_hand(action, state)
        if not cid:
            return 3.0, "setup_generic"
        role  = self.knowledge.get_role(cid)
        pw    = self.knowledge.get_priority_weight(cid)
        base  = {
            "main_attacker":  8.0,
            "evolution_base": 7.0,
            "basic_setup":    7.0,
            "search_engine":  6.0,
            "sub_attacker":   5.0,
        }.get(role, 3.0)
        return base + pw, f"setup_{role}"

    def _score_discard(self, action: dict, state: dict):
        """
        DISCARD option: prefer discarding low-value cards.
        Higher return score = better choice to discard.
        """
        cid = str(action.get("cardId", ""))
        if not cid:
            return 5.0, "discard_generic"
        penalty = self.knowledge.discard_penalty(cid)
        return 10.0 - float(penalty), f"discard_{cid}"
