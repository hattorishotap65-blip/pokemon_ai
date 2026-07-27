from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
import traceback
from collections import Counter, defaultdict

_rng = random.Random(1234)

# ── PR0-A: Strict Benchmark Mode / Telemetry ──────────────────────────────
# PRODUCTION: existing silent-fallback behavior, unchanged (default).
# BENCHMARK:  same control flow as PRODUCTION (never re-raises), but records
#             counters + per-exception detail so fallback/error rates are
#             observable instead of invisible.
# DEBUG:      records the same detail AND re-raises, so a failing decision
#             stops instead of silently falling back.
# Mode is read once at import time; this must never change which action a
# decision returns in PRODUCTION or BENCHMARK mode (Baseline Fingerprint
# Gate) -- only DEBUG intentionally alters behavior (stops on exception).
EXEC_MODE = os.environ.get("POKEMON_AI_EXEC_MODE", "PRODUCTION").upper()
if EXEC_MODE not in ("PRODUCTION", "BENCHMARK", "DEBUG"):
    EXEC_MODE = "PRODUCTION"

_TELEMETRY = {
    "search_attempt_count": 0,
    "search_success_count": 0,
    "search_fallback_count": 0,
    "search_override_count": 0,
    "rollout_attempt_count": 0,
    "rollout_success_count": 0,
    "rollout_error_count": 0,
    "cache_hit_count": 0,
    "cache_miss_count": 0,
    "decision_runtime_ms": [],
    "errors": [],  # only populated in BENCHMARK/DEBUG (see _record_exception)
}


def reset_telemetry():
    """Zero all counters. Call once per game (or per benchmark run) from a
    test harness; never called by the agent itself mid-decision."""
    for k in _TELEMETRY:
        _TELEMETRY[k] = [] if isinstance(_TELEMETRY[k], list) else 0


def get_telemetry():
    """Return a shallow copy snapshot for a test harness to read/serialize."""
    return {k: (list(v) if isinstance(v, list) else v) for k, v in _TELEMETRY.items()}


def _record_exception(stage, exc):
    """Never changes control flow in PRODUCTION/BENCHMARK (caller's existing
    except-block body runs exactly as before this call returns). Only DEBUG
    re-raises. Cheap in PRODUCTION: a single dict increment, no string/hash
    work, so this cannot be the cause of a production behavior or latency
    regression."""
    if EXEC_MODE == "PRODUCTION":
        return
    _TELEMETRY.setdefault("exception_count", 0)
    _TELEMETRY["exception_count"] += 1
    msg = str(exc)
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    _TELEMETRY["errors"].append({
        "stage": stage,
        "error_type": type(exc).__name__,
        "error_message_hash": hashlib.sha256(msg.encode("utf-8", "replace")).hexdigest()[:16],
        "traceback_hash": hashlib.sha256(tb.encode("utf-8", "replace")).hexdigest()[:16],
    })
    if EXEC_MODE == "DEBUG":
        raise exc

from cg.api import (
    AreaType,
    Card,
    CardType,
    EnergyType,
    Observation,
    OptionType,
    Pokemon,
    SelectContext,
    all_card_data,
    to_observation_class,
)


class C:
    RAGING_BOLT_EX = 63
    TEAL_MASK_OGERPON_EX = 96

    BASIC_GRASS_ENERGY = 1
    BASIC_LIGHTNING_ENERGY = 4
    BASIC_FIGHTING_ENERGY = 6

    ULTRA_BALL = 1121
    POKEGEAR = 1122
    SWITCH = 1123
    POKEMON_CATCHER = 1124
    BUG_CATCHING_SET = 1094
    TERA_ORB = 1127
    ENERGY_RETRIEVAL = 1118
    UNFAIR_STAMP = 1080
    BOSS_ORDERS = 1182
    LILLIE_DETERMINATION = 1227
    CRISPIN = 1198
    ENERGY_SEARCH_PRO = 1100   # ACE SPEC: all different-type basic energy from deck
    NIGHT_STRETCHER = 1097     # Pokemon or basic energy from discard to hand
    ENERGY_SEARCH = 1119       # 1 basic energy from deck to hand


BURST_ROAR = 71
BELLOWING_THUNDER = 72
MYRIAD_LEAF_SHOWER = 120

BASIC_ENERGY_IDS = {C.BASIC_GRASS_ENERGY, C.BASIC_LIGHTNING_ENERGY, C.BASIC_FIGHTING_ENERGY}
# All 8 basic energy card IDs in the full pool (Grass/Fire/Water/Lightning/
# Psychic/Fighting/Darkness/Metal) — generic, deck-independent constant used
# to infer an opponent's energy-type mix from public evidence.
ALL_BASIC_ENERGY_IDS = (1, 2, 3, 4, 5, 6, 7, 8)

_PARAMS_PATH = os.environ.get(
    "POKEMON_AI_PARAMS_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "params.json"),
)
if not os.path.exists(_PARAMS_PATH):
    _PARAMS_PATH = os.path.join(os.path.dirname(__file__), "params.json")

DECK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "..", "decks", "raging_bolt_ogerpon.csv")
if not os.path.exists(DECK_PATH):
    DECK_PATH = os.path.join(os.path.dirname(__file__), "deck.csv")
if not os.path.exists(DECK_PATH):
    DECK_PATH = "/kaggle_simulations/agent/deck.csv"

with open(DECK_PATH, "r", encoding="utf-8") as f:
    my_deck = [int(line) for line in f.read().splitlines() if line.strip()]


def _load_params():
    try:
        with open(_PARAMS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


P = _load_params()

all_card = all_card_data()
card_table = {card.cardId: card for card in all_card}

try:
    from cg.api import all_attack as _all_attack
    attack_table = {a.attackId: a for a in _all_attack()}
except Exception:
    attack_table = {}


def _static_opp_max_damage(opp_active, my_active_id):
    """Max damage opponent's active can deal next turn with current energy."""
    if opp_active is None:
        return 0
    opp_data = card_table.get(opp_active.id)
    if not opp_data or not attack_table:
        return 150
    opp_energy = len(opp_active.energies or [])
    max_dmg = 0
    for aid in (opp_data.attacks or []):
        a = attack_table.get(aid)
        if not a:
            continue
        cost = len(a.energies) if a.energies else 0
        if opp_energy >= cost and (a.damage or 0) > max_dmg:
            max_dmg = a.damage or 0
    my_data = card_table.get(my_active_id)
    if my_data and my_data.weakness is not None:
        if getattr(opp_data, 'energyType', None) == my_data.weakness:
            max_dmg *= 2
    return max_dmg

pre_turn = -1
ability_used_teal_dance = False


def get_card(obs, area, index, player_index):
    player = obs.current.players[player_index]
    try:
        if area == AreaType.DECK:
            return obs.select.deck[index]
        if area == AreaType.HAND:
            return player.hand[index]
        if area == AreaType.DISCARD:
            return player.discard[index]
        if area == AreaType.ACTIVE:
            return player.active[index]
        if area == AreaType.BENCH:
            return player.bench[index]
        if area == AreaType.PRIZE:
            return player.prize[index]
        if area == AreaType.STADIUM:
            return obs.current.stadium[index]
        if hasattr(AreaType, 'LOOKING') and area == AreaType.LOOKING:
            return obs.current.looking[index]
    except (IndexError, TypeError):
        pass
    return None


def prize_count(pokemon):
    data = card_table.get(pokemon.id)
    if data is None:
        return 1
    return 3 if data.megaEx else 2 if data.ex else 1


def _count_energy(pokemon):
    return len(pokemon.energies) if pokemon else 0


def _count_basic_energy_in_hand(hand):
    return sum(1 for c in (hand or []) if c.id in BASIC_ENERGY_IDS)


def _count_basic_energy_in_discard(discard):
    return sum(1 for c in (discard or []) if c.id in BASIC_ENERGY_IDS)


def _total_energy_on_field(me):
    total = 0
    for p in (me.active or []):
        total += _count_energy(p)
    for p in (me.bench or []):
        total += _count_energy(p)
    return total


def _find_pokemon_on_field(me, card_id):
    for p in (me.active or []):
        if p and p.id == card_id:
            return p, "active"
    for p in (me.bench or []):
        if p and p.id == card_id:
            return p, "bench"
    return None, None


class RagingBoltPolicy:
    def __init__(self, obs):
        self.obs = obs
        self.state = obs.current
        self.select = obs.select
        self.context = self.select.context
        self.my_index = self.state.yourIndex
        self.op_index = 1 - self.my_index
        self.me = self.state.players[self.my_index]
        self.opponent = self.state.players[self.op_index]
        self.my_prizes = len(self.me.prize)

        self.hand_ids = [c.id for c in (self.me.hand or [])]
        self.hand_counts = defaultdict(int)
        for cid in self.hand_ids:
            self.hand_counts[cid] += 1

        self.active = self.me.active[0] if self.me.active else None
        self.active_id = self.active.id if self.active else 0
        self.active_hp_pct = (
            (self.active.hp * 100 // self.active.maxHp) if self.active and self.active.maxHp > 0 else 100
        )

        self.opp_active = self.opponent.active[0] if self.opponent.active else None
        self.opp_active_hp = self.opp_active.hp if self.opp_active else 0

        self.energy_in_hand = _count_basic_energy_in_hand(self.me.hand)
        self.energy_in_discard = _count_basic_energy_in_discard(self.me.discard)
        self.total_field_energy = _total_energy_on_field(self.me)
        self.grass_in_hand = sum(1 for cid in self.hand_ids if cid == C.BASIC_GRASS_ENERGY)

        self._analyze_field()

    def _analyze_field(self):
        """Pre-compute strategic state for scoring."""
        all_pokemon = list(self.me.active or []) + list(self.me.bench or [])

        self.bt_total_energy = 0
        for p in all_pokemon:
            if p:
                self.bt_total_energy += _count_energy(p)
        self.bt_potential_damage = self.bt_total_energy * 70

        self.can_ko_with_bt = (
            self.active_id == C.RAGING_BOLT_EX
            and self.opp_active
            and self.bt_potential_damage >= self.opp_active_hp
        )

        self.ogerpon_on_field = []
        self.bolt_on_field = []
        for p in all_pokemon:
            if not p:
                continue
            if p.id == C.TEAL_MASK_OGERPON_EX:
                self.ogerpon_on_field.append(p)
            elif p.id == C.RAGING_BOLT_EX:
                self.bolt_on_field.append(p)

        self.bolt_has_lightning = False
        self.bolt_has_fighting = False
        bolt_active = self.active if self.active_id == C.RAGING_BOLT_EX else None
        if bolt_active:
            self.bolt_has_lightning = any(e == 4 for e in bolt_active.energies)
            self.bolt_has_fighting = any(e == 6 for e in bolt_active.energies)

        self.bolt_ready = self.bolt_has_lightning and self.bolt_has_fighting

        self.supporter_used_this_turn = not any(
            opt.type == OptionType.PLAY
            and self._is_supporter(opt)
            for opt in (self.select.option or [])
        ) if self.context == SelectContext.MAIN else True

        self.field_ready = (
            len(self.ogerpon_on_field) >= 1
            and len(self.bolt_on_field) >= 1
            and self.bolt_ready
        )

        self._detect_strategy()

    def _detect_strategy(self):
        """Auto-detect turn_goal and risk_flags from game state."""
        self.goals = set()
        self.risks = set()

        opp_prizes = len(self.opponent.prize)
        my_prizes = len(self.me.prize)

        # === Goals ===
        if self.can_ko_with_bt:
            self.goals.add("take_ko_now")
            opp_prize_val = self._opp_prize_value()
            if opp_prize_val >= 2:
                self.goals.add("take_two_prizes")
        elif self.active_id == C.TEAL_MASK_OGERPON_EX and self.opp_active:
            my_e = _count_energy(self.active) if self.active else 0
            opp_e = _count_energy(self.opp_active) if self.opp_active else 0
            if 30 + (my_e + opp_e) * 30 >= self.opp_active_hp:
                self.goals.add("take_ko_now")
        if my_prizes <= 1:
            self.goals.add("close_game")

        if not self.bolt_ready:
            self.goals.add("prepare_next_turn_attack")

        if not self.ogerpon_on_field or not self.bolt_on_field:
            self.goals.add("setup_board")

        if len(self.hand_ids) <= 3:
            self.goals.add("improve_hand")

        # === Risks ===
        if self.active and self.opp_active:
            opp_max_damage = self._estimate_opp_damage()
            if self.active.hp <= opp_max_damage:
                self.risks.add("active_may_be_ko_next_turn")

        bench_bolt_with_energy = any(
            p and p.id == C.RAGING_BOLT_EX and _count_energy(p) >= 1
            for p in (self.me.bench or [])
        )
        if self.active_id == C.RAGING_BOLT_EX:
            if not bench_bolt_with_energy:
                self.risks.add("no_next_attacker")
        elif self.active_id == C.TEAL_MASK_OGERPON_EX:
            if not any(p and p.id == C.RAGING_BOLT_EX for p in (self.me.bench or [])):
                self.risks.add("no_next_attacker")

        if self.bt_total_energy < 4:
            self.risks.add("not_enough_energy")

        if len(self.hand_ids) <= 4:
            self.risks.add("low_hand")

        if len(self.hand_ids) <= 2:
            self.risks.add("low_hand")

        if my_prizes > opp_prizes + 1:
            self.risks.add("behind_prize_race")

        if self.me.deckCount and self.me.deckCount <= 10:
            self.risks.add("low_deck")

    def _strategy_bonus(self, action_type, card_id=None, attack_id=None):
        """Return score modifier based on detected goals and risks."""
        bonus = 0

        if "take_ko_now" in self.goals:
            if action_type == "attack":
                bonus += 400
            if action_type == "attach" and card_id == C.RAGING_BOLT_EX:
                bonus += 200
            if action_type == "supporter" and card_id == C.BOSS_ORDERS:
                bonus += 300

        if "take_two_prizes" in self.goals:
            if action_type == "attack":
                bonus += 200
            if action_type == "supporter" and card_id == C.BOSS_ORDERS:
                bonus += 500

        if "prepare_next_turn_attack" in self.goals:
            if action_type == "supporter" and card_id == C.CRISPIN:
                bonus += 400
            if action_type == "ability":
                bonus += 200
            if action_type == "attach":
                bonus += 250
            if action_type == "attack" and attack_id == BURST_ROAR:
                bonus -= 200

        if "setup_board" in self.goals:
            if action_type == "play_pokemon":
                bonus += 500
            if action_type == "search_item":
                bonus += 400
            if action_type == "supporter" and card_id == C.LILLIE_DETERMINATION:
                bonus += 300

        if "improve_hand" in self.goals:
            if action_type == "supporter" and card_id == C.LILLIE_DETERMINATION:
                bonus += 400
            if action_type == "supporter" and card_id == C.CRISPIN:
                bonus += 200

        if "close_game" in self.goals:
            if action_type == "attack":
                bonus += 300
            if action_type == "supporter" and card_id == C.BOSS_ORDERS:
                bonus += 500

        if "not_enough_energy" in self.risks:
            if action_type == "supporter" and card_id == C.CRISPIN:
                bonus += 400
            if action_type == "ability":
                bonus += 200
            if action_type == "search_item":
                bonus += 100

        if "active_may_be_ko_next_turn" in self.risks:
            if action_type == "retreat":
                bonus += 300
            if action_type == "attach" and card_id != C.RAGING_BOLT_EX:
                bonus -= 100


        if "behind_prize_race" in self.risks:
            if action_type == "attack":
                bonus += 300
            if action_type == "supporter" and card_id == C.BOSS_ORDERS:
                bonus += 200

        if "low_hand" in self.risks:
            if action_type == "supporter" and card_id == C.LILLIE_DETERMINATION:
                bonus += 300

        return bonus

    def _is_supporter(self, opt):
        c = get_card(self.obs, AreaType.HAND, opt.index, self.my_index)
        if c:
            cd = card_table.get(c.id)
            return cd and cd.cardType == CardType.SUPPORTER
        return False

    def p(self, key, default=0):
        return P.get(key, default)

    def rank(self):
        """Return (ranked_indices, scores_list) for all options."""
        if not self.select.option:
            return [], []
        scores = [self._score_option(i, opt) for i, opt in enumerate(self.select.option)]
        ranked = [i for i, _ in sorted(enumerate(scores), key=lambda x: -x[1])]
        return ranked, scores

    def choose(self):
        if not self.select.option or self.select.maxCount == 0:
            return []

        ranked, scores = self.rank()
        n = len(self.select.option)
        min_c = max(0, min(self.select.minCount, n))
        max_c = max(min_c, min(self.select.maxCount, n))

        result = []
        for i in ranked:
            if len(result) >= max_c:
                break
            if scores[i] > 0 or len(result) < min_c:
                result.append(i)

        if not result and min_c > 0:
            result = list(range(min(min_c, n)))

        return result

    def _score_option(self, i, opt):
        t = opt.type

        if t == OptionType.END:
            return self.p("score_end_turn", 50)

        if t == OptionType.YES:
            if self.context == SelectContext.IS_FIRST:
                return self.p("is_first_yes", 100)
            return 500

        if t == OptionType.NO:
            if self.context == SelectContext.IS_FIRST:
                return self.p("is_first_no", 900)
            return 400

        if t == OptionType.ATTACK:
            base = self._score_attack(opt)
            if opt.attackId == BURST_ROAR:
                return base
            has_play_or_ability = any(
                o.type in (OptionType.PLAY, OptionType.ABILITY)
                for o in self.select.option
            )
            if has_play_or_ability:
                return min(base, 700)
            return base + self._strategy_bonus("attack", attack_id=opt.attackId)

        if t == OptionType.ABILITY:
            base = self._score_ability(i, opt)
            return base + self._strategy_bonus("ability")

        if t == OptionType.PLAY:
            base = self._score_play(i, opt)
            c = get_card(self.obs, AreaType.HAND, opt.index, self.my_index)
            cid = c.id if c else 0
            cd = card_table.get(cid)
            if cd and cd.cardType == CardType.SUPPORTER:
                return base + self._strategy_bonus("supporter", card_id=cid)
            if cd and cd.hp and cd.hp > 0:
                return base + self._strategy_bonus("play_pokemon", card_id=cid)
            if cid in (C.ULTRA_BALL, C.BUG_CATCHING_SET, C.TERA_ORB, C.POKEGEAR,
                       C.ENERGY_SEARCH_PRO, C.NIGHT_STRETCHER, C.ENERGY_SEARCH):
                return base + self._strategy_bonus("search_item", card_id=cid)
            return base

        if t == OptionType.ATTACH:
            base = self._score_attach(i, opt)
            has_supporter = any(
                o.type == OptionType.PLAY and self._is_supporter(o)
                for o in self.select.option
            )
            if has_supporter:
                return min(base, 1100)
            target = get_card(self.obs, getattr(opt, 'inPlayArea', None),
                              getattr(opt, 'inPlayIndex', None), self.my_index)
            return base + self._strategy_bonus("attach", card_id=target.id if target else 0)

        if t == OptionType.RETREAT:
            base = self._score_retreat()
            return base + self._strategy_bonus("retreat")

        if t == OptionType.EVOLVE:
            return 800

        if t in (OptionType.CARD, OptionType.TOOL_CARD, OptionType.ENERGY_CARD):
            return self._score_card_select(i, opt)

        if t == OptionType.ENERGY:
            return self._score_energy_select(i, opt)

        if t == OptionType.NUMBER:
            return self._score_number(opt)

        return 300

    def _score_attack(self, opt):
        aid = opt.attackId

        if aid == BELLOWING_THUNDER:
            if not self.active or self.active_id != C.RAGING_BOLT_EX:
                return 400
            if not self.bolt_ready:
                return 300
            if self.can_ko_with_bt:
                prize = self._opp_prize_value()
                return 2000 + prize * 300
            if self.bt_total_energy >= 4:
                return 1200
            if self.bt_total_energy >= 3:
                return 1000
            return 800

        if aid == MYRIAD_LEAF_SHOWER:
            my_energy = _count_energy(self.active) if self.active else 0
            opp_energy = _count_energy(self.opp_active) if self.opp_active else 0
            total_energy = my_energy + opp_energy
            potential_damage = 30 + total_energy * 30
            if self.opp_active and potential_damage >= self.opp_active_hp:
                prize = self._opp_prize_value()
                return 1800 + prize * 200
            has_bolt_bench = any(p and p.id == C.RAGING_BOLT_EX for p in (self.me.bench or []))
            if has_bolt_bench and self.bt_total_energy >= 3:
                return 400
            return 600 + total_energy * 40

        if aid == BURST_ROAR:
            has_bt = any(o.type == OptionType.ATTACK and o.attackId == BELLOWING_THUNDER
                         for o in self.select.option)
            has_mls = any(o.type == OptionType.ATTACK and o.attackId == MYRIAD_LEAF_SHOWER
                          for o in self.select.option)
            if has_bt or has_mls:
                return 30
            has_play = any(o.type in (OptionType.PLAY, OptionType.ABILITY, OptionType.ATTACH)
                           for o in self.select.option)
            if has_play:
                return 40
            if len(self.hand_ids) <= 1:
                return 500
            return 45

        return 500

    def _score_ability(self, i, opt):
        c = get_card(self.obs, opt.area, opt.index, self.my_index)
        if c and c.id == C.TEAL_MASK_OGERPON_EX:
            if self.grass_in_hand > 0:
                if self.bolt_ready:
                    return 1500
                return 1300
            return 200
        return 500

    def _score_play(self, i, opt):
        c = get_card(self.obs, AreaType.HAND, opt.index, self.my_index)
        if c is None:
            return 300
        cid = c.id

        if cid == C.RAGING_BOLT_EX:
            if not self.bolt_on_field:
                # first Bolt not yet on field: bench it directly over search/draw
                # (observed 2x: human played Bolt over Lillie/Ultra Ball)
                return 1250
            return self.p("score_play_pokemon_raging_bolt", 500)
        if cid == C.TEAL_MASK_OGERPON_EX:
            ogerpon_bench = [p for p in (self.me.bench or []) if p and p.id == C.TEAL_MASK_OGERPON_EX]
            if not self.ogerpon_on_field or not ogerpon_bench:
                # always same high priority as first placement — Ogerpon on bench
                # is essential for Teal Dance draw engine
                return 1100
            return self.p("score_play_pokemon_ogerpon", 600)

        if cid == C.CRISPIN:
            if self.energy_in_hand >= 4:
                return 500
            if self.field_ready and self.energy_in_discard >= 1:
                return 1500
            if not self.bolt_ready and self.energy_in_discard >= 1:
                if self.ogerpon_on_field and self.grass_in_hand > 0 and len(self.hand_ids) <= 3:
                    # hand thin + Teal Dance available: draw via Ogerpon ability first,
                    # attach energy next turn — observed 4x in session_tuning_log.jsonl
                    return 1000
                return 1300
            if self.energy_in_discard >= 1:
                return 1100
            return 600

        if cid == C.LILLIE_DETERMINATION:
            # Lillie draws best on a small hand — exhaust every hand-consuming
            # combo first (Teal Dance draws, energy attach, ER->grass, benching
            # Ogerpon/Bolt, BCS/Tera Orb), THEN refill. Counted generically so
            # the rollforward also sequences the full combo before Lillie.
            pending_plays = 0
            if self.grass_in_hand > 0 and self.ogerpon_on_field:
                pending_plays += 1  # Teal Dance draw still available
            if not getattr(self.state, 'energyAttached', True):
                needs_l = self._field_bolt_missing(4) and C.BASIC_LIGHTNING_ENERGY in self.hand_ids
                needs_f = self._field_bolt_missing(6) and C.BASIC_FIGHTING_ENERGY in self.hand_ids
                if needs_l or needs_f or self.grass_in_hand > 0:
                    pending_plays += 1  # useful free attach unused
            if (C.TEAL_MASK_OGERPON_EX in self.hand_ids or
                    C.BUG_CATCHING_SET in self.hand_ids or
                    C.TERA_ORB in self.hand_ids):
                pending_plays += 1  # can add Ogerpon without a supporter slot
            if C.RAGING_BOLT_EX in self.hand_ids:
                pending_plays += 1  # benchable attacker in hand
            if ((C.ENERGY_RETRIEVAL in self.hand_ids or C.NIGHT_STRETCHER in self.hand_ids)
                    and self.energy_in_discard >= 1):
                pending_plays += 1  # recovers grass to feed Teal Dance
            if C.ENERGY_SEARCH_PRO in self.hand_ids:
                pending_plays += 1  # fetches energy from deck before refilling
            if pending_plays > 0 and self.p("rule_lillie_combo_defer", 1):
                return self.p("lillie_pending_defer_score", 550)  # combos first
            if self.field_ready:
                return 1000 if len(self.hand_ids) <= 3 else 700
            return 1300 if len(self.hand_ids) <= 2 else 1200

        if cid == C.BOSS_ORDERS:
            if self.active_hp_pct <= 20:
                return 200
            best_target = self._best_boss_target()
            if best_target:
                return 1600
            if self.can_ko_with_bt:
                return 400
            return 800

        # Energy Search Pro: one item assembles L+F+G from deck — highest value
        # while the attack cost is incomplete, still fine later for grass restock
        if cid == C.ENERGY_SEARCH_PRO:
            if not self.bolt_ready or not self.field_ready:
                return 1250
            return 600
        if cid == C.NIGHT_STRETCHER:
            # Flexible discard recovery: energy for the BT loop, or a KO'd attacker
            bolt_in_discard = any(c2.id == C.RAGING_BOLT_EX for c2 in (self.me.discard or []))
            if self.energy_in_discard >= 1 or bolt_in_discard:
                return 950 if not self.field_ready else 800
            return 300
        if cid == C.ENERGY_SEARCH:
            if not self.bolt_ready and (self._field_bolt_missing(4) or self._field_bolt_missing(6)):
                return 900  # digs the missing attack-cost type from the deck
            if self.grass_in_hand == 0 and self.ogerpon_on_field:
                return 650
            return 400

        if self.field_ready:
            if cid == C.ENERGY_RETRIEVAL:
                if (self.energy_in_hand >= self.p("er_hold_hand_energy", 3)
                        and self.p("rule_er_hold", 1)):
                    # Hand already flush with energy — save it for after the
                    # next Bellowing Thunder (observed: human ended turn instead)
                    return self.p("er_hold_score", 250)
                if self.energy_in_discard >= self.p("energy_retrieval_threshold", 2):
                    return 1200
                if self.energy_in_discard >= 1:
                    return 1000
                return 400
            if cid == C.BUG_CATCHING_SET:
                return 700  # no hand cost; preferred for finding Ogerpon/energy
            if cid == C.TERA_ORB:
                return 650  # finds Tera Pokemon (Ogerpon); no hand cost
            if cid == C.ULTRA_BALL:
                # Even with the field ready, a 2nd Ogerpon is worth it when the
                # hand has 2+ disposable items to pay the cost (observed: human
                # used Ultra Ball for a 2nd Ogerpon with spare items in hand)
                disposable = sum(1 for h in self.hand_ids
                                 if h in (C.POKEMON_CATCHER, C.POKEGEAR, C.SWITCH, C.UNFAIR_STAMP))
                if len(self.ogerpon_on_field) < 2 and disposable >= 2:
                    return 700
                return 350  # hand cost of 2 cards is too high when field is ready
            if cid == C.POKEGEAR:
                return 500
        else:
            if cid == C.ULTRA_BALL:
                if not self.bolt_on_field or not self.ogerpon_on_field:
                    # A core attacker/engine piece is missing. BCS (1200) and
                    # Tera Orb (1150) still outrank this when in hand, so Ultra
                    # Ball is the fallback Ogerpon access, not the first choice
                    # (observed: human used Ultra Ball for Ogerpon on T2)
                    return 1100
                return 400  # both on field: hand cost of 2 is too high
            if cid == C.BUG_CATCHING_SET:
                return 1200  # finds Ogerpon/Bolt, no discard cost
            if cid == C.TERA_ORB:
                return 1150  # finds Tera Pokemon (Ogerpon), no discard cost
            if cid == C.POKEGEAR:
                return 1000
            if cid == C.ENERGY_RETRIEVAL:
                if self.energy_in_discard >= self.p("energy_retrieval_threshold", 2):
                    return 900
                return 500

        if cid == C.POKEMON_CATCHER:
            if not self.bolt_ready and self.p("rule_catcher_hold", 1):
                # Can't capitalize on the gust this turn — save the Catcher
                # (observed: human ended turn rather than burn it)
                return self.p("catcher_hold_score", 5)
            return self.p("score_item_pokemon_catcher", 300)
        if cid == C.UNFAIR_STAMP:
            return self.p("score_item_unfair_stamp", 600)

        return 300

    def _score_attach(self, i, opt):
        target = get_card(self.obs,
                          getattr(opt, 'inPlayArea', None),
                          getattr(opt, 'inPlayIndex', None),
                          self.my_index)
        if target is None:
            return self.p("score_attach_energy_other", 200)

        # Attach-for-lethal: one more energy anywhere turns Bellowing Thunder
        # into a KO this turn — BT counts all field energy (observed: human
        # attached a surplus F, then attacked for the KO)
        if (self.p("rule_attach_for_lethal", 1)
                and self.active_id == C.RAGING_BOLT_EX and self.bolt_ready
                and self.opp_active and not self.can_ko_with_bt
                and (self.bt_total_energy + 1) * 70 >= self.opp_active_hp):
            return self.p("attach_for_lethal_score", 1800)

        is_active = getattr(opt, 'inPlayArea', None) == AreaType.ACTIVE
        target_energy = _count_energy(target) if target else 0

        energy_card = get_card(self.obs, AreaType.HAND, opt.index, self.my_index)
        energy_id = energy_card.id if energy_card else 0

        if target.id == C.RAGING_BOLT_EX:
            has_lightning = any(e == 4 for e in target.energies) if target else False
            has_fighting = any(e == 6 for e in target.energies) if target else False
            fills_bt_req = (energy_id == C.BASIC_LIGHTNING_ENERGY and not has_lightning) or \
                           (energy_id == C.BASIC_FIGHTING_ENERGY and not has_fighting)
            if fills_bt_req:
                return 1400
            if energy_id == C.BASIC_GRASS_ENERGY:
                return 100
            if is_active and self.active_hp_pct <= self.p("retreat_hp_threshold_pct", 30):
                return self.p("score_attach_energy_raging_bolt_active_low_hp", 350)
            if is_active:
                return 500 + target_energy * 30
            return self.p("score_attach_energy_raging_bolt_bench", 400)

        if target.id == C.TEAL_MASK_OGERPON_EX:
            if energy_id == C.BASIC_GRASS_ENERGY:
                return 600
            # L/F energy on Ogerpon is wasted — it only uses Grass energy
            # (observed: human always attached L energy to Bolt instead)
            return 100

        return self.p("score_attach_energy_other", 200)

    def _score_retreat(self):
        if self.active_id == C.TEAL_MASK_OGERPON_EX:
            bench_bolt_ready = [p for p in (self.me.bench or [])
                                if p and p.id == C.RAGING_BOLT_EX
                                and any(e == 4 for e in p.energies)
                                and any(e == 6 for e in p.energies)]
            if bench_bolt_ready:
                return 1500
        if self.active_id != C.RAGING_BOLT_EX:
            bench_bolt_any = [p for p in (self.me.bench or [])
                              if p and p.id == C.RAGING_BOLT_EX and _count_energy(p) >= 2]
            if bench_bolt_any:
                return 800
        if self.active_hp_pct <= 15:
            bench_any = [p for p in (self.me.bench or []) if p and _count_energy(p) >= 1]
            if bench_any:
                return 900
        if self.active_hp_pct <= self.p("retreat_hp_threshold_pct", 30):
            return self.p("score_retreat_damaged_active", 400)
        return 100

    def _score_card_select(self, i, opt):
        c = get_card(self.obs,
                     getattr(opt, 'area', None) or AreaType.HAND,
                     opt.index, self.my_index)
        if c is None:
            return 300

        ctx = self.context

        if ctx == SelectContext.TO_HAND:
            if c.id == C.RAGING_BOLT_EX:
                bolt_on_field, _ = _find_pokemon_on_field(self.me, C.RAGING_BOLT_EX)
                return 800 if bolt_on_field is None else 400
            if c.id == C.TEAL_MASK_OGERPON_EX:
                ogre_on_field, _ = _find_pokemon_on_field(self.me, C.TEAL_MASK_OGERPON_EX)
                # 2nd+ Ogerpon still beats 2nd Bolt: each adds a Teal Dance per turn
                # (observed: human picked Ogerpon over Bolt when both on field)
                return 850 if ogre_on_field is None else 500
            if c.id == C.CRISPIN:
                return 700 if self.energy_in_hand < 3 else 400
            if c.id == C.LILLIE_DETERMINATION:
                return 650 if len(self.hand_ids) <= 4 else 450
            if c.id == C.BOSS_ORDERS:
                return 750 if self._can_ko_active() else 500
            if c.id == C.ULTRA_BALL:
                return 600
            if c.id == C.TERA_ORB:
                return 580
            if c.id == C.ENERGY_RETRIEVAL:
                return 620 if self.energy_in_discard >= self.p("energy_retrieval_threshold", 2) else 450
            if c.id == C.POKEMON_CATCHER:
                return 500
            if c.id == C.BUG_CATCHING_SET:
                return 520
            if c.id == C.POKEGEAR:
                return 480
            if c.id == C.UNFAIR_STAMP:
                return 550
            if c.id in BASIC_ENERGY_IDS:
                # Need-based with hand-duplicate penalty (observed: hand already
                # held Fighting, human took Grass/Lightning instead)
                return self._score_energy_pick(c.id) + 50
            return 400

        if ctx == SelectContext.DISCARD:
            # Ultra Ball hand-discard cost: discard items first, keep energy especially Grass
            # (observed 4x: human discards Pokegear/Catcher/Tera Orb rather than Grass energy)
            if c.id == C.POKEMON_CATCHER:
                return 850
            if c.id == C.POKEGEAR:
                return 800
            if c.id == C.UNFAIR_STAMP:
                return 750
            if c.id in (C.TERA_ORB, C.BUG_CATCHING_SET):
                return 600
            if c.id == C.ENERGY_RETRIEVAL:
                return 550
            if c.id in (C.RAGING_BOLT_EX, C.TEAL_MASK_OGERPON_EX):
                return 100
            if c.id == C.BASIC_GRASS_ENERGY:
                return 200  # keep Grass for Ogerpon Teal Dance
            if c.id in (C.BASIC_LIGHTNING_ENERGY, C.BASIC_FIGHTING_ENERGY):
                return 300
            if c.id in (C.LILLIE_DETERMINATION, C.CRISPIN):
                return 380
            return 500

        if ctx == SelectContext.DISCARD_ENERGY_CARD:
            energy_id = self._get_energy_type_from_opt(opt)
            is_on_bolt = False
            is_active_bolt = False
            if True:  # always DISCARD_ENERGY_CARD here
                area_d = getattr(opt, 'area', None)
                try:
                    player = self.obs.current.players[self.my_index]
                    poke = None
                    if area_d == AreaType.ACTIVE and player.active:
                        poke = player.active[0]
                        if poke and poke.id == C.RAGING_BOLT_EX:
                            is_active_bolt = True
                    elif area_d == AreaType.BENCH and player.bench and opt.index < len(player.bench):
                        poke = player.bench[opt.index]
                    if poke and poke.id == C.RAGING_BOLT_EX:
                        is_on_bolt = True
                except Exception as _e:
                    _record_exception("discard_energy_bolt_lookup", _e)
            opp_dmg = self._estimate_opp_damage()
            bolt_will_die = is_active_bolt and self.active and self.active.hp <= opp_dmg
            if bolt_will_die:
                return 900
            if is_on_bolt and energy_id in (C.BASIC_LIGHTNING_ENERGY, C.BASIC_FIGHTING_ENERGY):
                # Duplicates of a type are safe to discard — only the last L/F
                # matters for next turn's attack cost (observed: Bolt had L+F+F,
                # human discarded the extra F and kept the L+F core)
                try:
                    etype = 4 if energy_id == C.BASIC_LIGHTNING_ENERGY else 6
                    same_count = sum(1 for e in (poke.energies or []) if e == etype) if poke else 1
                    if same_count >= 2:
                        return 450
                except Exception as _e:
                    _record_exception("discard_energy_dup_count", _e)
                return 50
            last_ko = self.my_prizes <= self._opp_prize_value()
            if last_ko:
                return 700
            if energy_id == C.BASIC_GRASS_ENERGY:
                return 800
            if energy_id in (C.BASIC_LIGHTNING_ENERGY, C.BASIC_FIGHTING_ENERGY):
                return 200
            return 400

        if ctx == SelectContext.ATTACH_TO:
            if c.id == C.TEAL_MASK_OGERPON_EX:
                return 750
            if c.id == C.RAGING_BOLT_EX:
                return 700
            if c.id in BASIC_ENERGY_IDS:
                # Crispin's flow also asks WHICH ENERGY under ATTACH_TO
                # (confirmed via select_context logging) — score by field need
                return self._score_energy_pick(c.id)
            return 400

        if ctx == SelectContext.ATTACH_FROM:
            if c.id in BASIC_ENERGY_IDS:
                return 600
            return 400

        if ctx == SelectContext.SETUP_ACTIVE_POKEMON:
            # Ogerpon leads: tanks early chip while Bolt charges on the bench.
            # (Human preferred Bolt lead, but A/B showed Ogerpon lead wins more:
            # mirror 54-46 against the Bolt-lead variant.)
            if c.id == C.TEAL_MASK_OGERPON_EX:
                return 800
            if c.id == C.RAGING_BOLT_EX:
                return 700
            return 300

        if ctx == SelectContext.SETUP_BENCH_POKEMON:
            if c.id == C.RAGING_BOLT_EX:
                return 800
            if c.id == C.TEAL_MASK_OGERPON_EX:
                return 700
            return 300

        if ctx == SelectContext.SWITCH:
            if c.id == C.RAGING_BOLT_EX:
                bolt_energy = _count_energy(c) if hasattr(c, 'energies') else 0
                return 700 + bolt_energy * 50
            if c.id == C.TEAL_MASK_OGERPON_EX:
                return 600
            return 300

        if ctx == SelectContext.TO_ACTIVE:
            # Replacing fainted active — prefer Bolt (with energy) then Ogerpon
            if c.id == C.RAGING_BOLT_EX:
                bolt_energy = _count_energy(c) if hasattr(c, 'energies') else 0
                return 700 + bolt_energy * 50
            if c.id == C.TEAL_MASK_OGERPON_EX:
                return 600
            return 300

        if ctx == SelectContext.TO_DECK:
            return 400

        if ctx == SelectContext.TO_HAND_ENERGY:
            if not self.bolt_ready:
                if c.id == C.BASIC_LIGHTNING_ENERGY and not self.bolt_has_lightning:
                    return 900
                if c.id == C.BASIC_FIGHTING_ENERGY and not self.bolt_has_fighting:
                    return 900
            if c.id == C.BASIC_GRASS_ENERGY:
                if len(self.ogerpon_on_field) > 0:
                    fighting_in_hand = C.BASIC_FIGHTING_ENERGY in self.hand_ids
                    if not self.bolt_has_fighting and fighting_in_hand:
                        return 950
                    return 800
                return 750  # even without Ogerpon on field, Grass enables Teal Dance soon
            if c.id == C.BASIC_LIGHTNING_ENERGY:
                if self._field_bolt_missing(4):
                    return 750  # a bench Bolt still needs Lightning
                return 500
            if c.id == C.BASIC_FIGHTING_ENERGY:
                if self._field_bolt_missing(6):
                    return 750  # a bench Bolt still needs Fighting
                return 500
            return 400

        # ── Generic fallbacks for unhandled contexts (previously flat 400) ──
        # Selecting one of my field Pokemon (e.g. Crispin attach target)
        area = getattr(opt, 'area', None)
        if area in (AreaType.ACTIVE, AreaType.BENCH):
            return self._score_field_target(c, area)
        # Selecting an energy card (e.g. Crispin's deck pick)
        if c.id in BASIC_ENERGY_IDS:
            return self._score_energy_pick(c.id)

        return 400

    def _field_bolt_missing(self, etype):
        """True if any of my field Raging Bolts lacks this energy type."""
        return any(not any(e == etype for e in (p.energies or []))
                   for p in self.bolt_on_field)

    def _score_field_target(self, c, area):
        """Score a field Pokemon as an effect/attach target (energy delivery).
        Prefer a Bolt still missing its attack cost; avoid loading a dying active
        (observed: AI fed energy to a 30HP active over a healthy bench Bolt)."""
        if c.id == C.RAGING_BOLT_EX:
            missing = (not any(e == 4 for e in (c.energies or []))
                       or not any(e == 6 for e in (c.energies or [])))
            if area == AreaType.ACTIVE and getattr(c, 'hp', 999) <= 60:
                return 300  # likely KO'd next turn — energy would be stranded
            if missing:
                return 800 if area == AreaType.BENCH else 700
            return 500
        if c.id == C.TEAL_MASK_OGERPON_EX:
            return 600
        return 400

    def _score_energy_pick(self, cid):
        """Score picking an energy card (search/retrieval effects): prefer types
        a field Bolt still needs and that the hand doesn't already hold
        (observed: hand had L, human picked F for the attack cost)."""
        score = 500
        need_bonus = self.p("energy_pick_need_bonus", 250)
        if cid == C.BASIC_LIGHTNING_ENERGY and self._field_bolt_missing(4):
            score += need_bonus
        if cid == C.BASIC_FIGHTING_ENERGY and self._field_bolt_missing(6):
            score += need_bonus
        if cid == C.BASIC_GRASS_ENERGY:
            if self.ogerpon_on_field:
                score += self.p("energy_pick_grass_teal_dance", 100)
            if self.grass_in_hand == 0:
                score += self.p("energy_pick_grass_first", 50)
        score -= self.p("energy_pick_dup_penalty", 100) * min(self.hand_counts.get(cid, 0), 2)
        return score

    def _score_energy_select(self, i, opt):
        """Score ENERGY type options (e.g. Bellowing Thunder energy discard)."""
        ctx = self.context
        if ctx in (SelectContext.DISCARD_ENERGY_CARD, SelectContext.DISCARD_ENERGY,
                   getattr(SelectContext, 'DISCARD', -1)):
            energy_type = self._get_energy_type_from_opt(opt)
            last_ko = self.my_prizes <= self._opp_prize_value()
            low_hp = self.active_hp_pct <= 50

            area = getattr(opt, 'area', None)
            is_on_bolt = False
            is_active_bolt = False
            if area is not None:
                poke = None
                try:
                    player = self.obs.current.players[self.my_index]
                    if area == AreaType.ACTIVE and player.active:
                        poke = player.active[0]
                        if poke and poke.id == C.RAGING_BOLT_EX:
                            is_active_bolt = True
                    elif area == AreaType.BENCH and player.bench and opt.index < len(player.bench):
                        poke = player.bench[opt.index]
                except Exception as _e:
                    _record_exception("energy_select_bolt_lookup", _e)
                if poke and poke.id == C.RAGING_BOLT_EX:
                    is_on_bolt = True

            opp_dmg = self._estimate_opp_damage()
            bolt_will_die = is_active_bolt and self.active and self.active.hp <= opp_dmg

            if last_ko:
                if is_on_bolt and energy_type in (C.BASIC_LIGHTNING_ENERGY, C.BASIC_FIGHTING_ENERGY) and not bolt_will_die:
                    return 50
                return 700

            if bolt_will_die:
                return 900

            if energy_type == C.BASIC_GRASS_ENERGY:
                return 800
            if is_on_bolt and energy_type in (C.BASIC_LIGHTNING_ENERGY, C.BASIC_FIGHTING_ENERGY):
                return 50
            if energy_type == C.BASIC_LIGHTNING_ENERGY:
                return 300
            if energy_type == C.BASIC_FIGHTING_ENERGY:
                return 300
            return 500
        # Non-discard energy selections (attach/搬送 effects): pick by field need
        # instead of a flat 400 (observed: AI took Grass over the Fighting the
        # active Bolt still needed for its attack cost)
        etype_cid = self._get_energy_type_from_opt(opt)
        if etype_cid in BASIC_ENERGY_IDS:
            return self._score_energy_pick(etype_cid)
        return 400

    def _get_energy_type_from_opt(self, opt):
        """Get the energy card ID from an ENERGY/ENERGY_CARD option."""
        ei = getattr(opt, 'energyIndex', None)
        area = getattr(opt, 'area', None)
        idx = opt.index
        if ei is not None and area is not None:
            try:
                player = self.obs.current.players[self.my_index]
                poke = None
                if area == AreaType.ACTIVE and player.active:
                    poke = player.active[0]
                elif area == AreaType.BENCH and player.bench and idx < len(player.bench):
                    poke = player.bench[idx]
                if poke:
                    if hasattr(poke, 'energyCards') and poke.energyCards and ei < len(poke.energyCards):
                        return poke.energyCards[ei].id
                    if hasattr(poke, 'energies') and poke.energies and ei < len(poke.energies):
                        etype = poke.energies[ei]
                        ETYPE_TO_CARD = {1: C.BASIC_GRASS_ENERGY, 4: C.BASIC_LIGHTNING_ENERGY, 6: C.BASIC_FIGHTING_ENERGY}
                        return ETYPE_TO_CARD.get(etype, 0)
            except Exception as _e:
                _record_exception("get_energy_type_from_opt", _e)
        return 0

    def _score_number(self, opt):
        num = opt.number if hasattr(opt, 'number') else 0
        ctx = self.context
        if ctx == SelectContext.DRAW_COUNT:
            return 500 + num * 50
        if ctx in (SelectContext.DISCARD_ENERGY_CARD, SelectContext.DISCARD_ENERGY):
            if self.active_id == C.RAGING_BOLT_EX and self.opp_active:
                needed = (self.opp_active_hp + 69) // 70
                last_ko = self.my_prizes <= self._opp_prize_value()
                if last_ko:
                    if num >= needed:
                        return 1000
                    return 500 + num * 70
                if num == needed:
                    return 950
                if num > needed:
                    return 800
                if num >= needed - 1:
                    return 850
                return 500 + num * 70
            return 500 + num * 50
        return 500

    def _estimate_opp_damage(self):
        """Estimate max damage opponent can deal next turn."""
        if not self.opp_active:
            return 0
        opp_data = card_table.get(self.opp_active.id)
        if not opp_data:
            return 200
        opp_energy = _count_energy(self.opp_active)
        try:
            from cg.api import all_attack
            AT_local = {a.attackId: a for a in all_attack()}
        except Exception as _e:
            _record_exception("estimate_opp_damage_attack_table", _e)
            return 200
        max_dmg = 0
        for aid in (opp_data.attacks or []):
            a = AT_local.get(aid)
            if not a:
                continue
            cost = len(a.energies) if a.energies else 0
            if opp_energy >= cost:
                dmg = a.damage if a.damage else 0
                if dmg > max_dmg:
                    max_dmg = dmg
        if max_dmg == 0 and opp_energy >= 1:
            max_dmg = 100
        if max_dmg == 0:
            max_dmg = 50
        my_data = card_table.get(self.active_id)
        if my_data and my_data.weakness:
            opp_type = getattr(opp_data, 'energyType', None)
            if opp_type == my_data.weakness:
                max_dmg *= 2
        return max_dmg

    def _can_bellowing_thunder(self):
        return self.active_id == C.RAGING_BOLT_EX and self.bolt_ready

    def _best_boss_target(self):
        """Check if there's a high-value KO target on opponent's bench."""
        if not self._can_bellowing_thunder():
            return None
        for p in (self.opponent.bench or []):
            if not p:
                continue
            data = card_table.get(p.id)
            if not data:
                continue
            prize = 3 if data.megaEx else 2 if data.ex else 1
            if prize >= 2 and p.hp <= self.bt_potential_damage:
                return p
        return None

    def _opp_prize_value(self):
        if not self.opp_active:
            return 1
        data = card_table.get(self.opp_active.id)
        if data is None:
            return 1
        return 3 if data.megaEx else 2 if data.ex else 1

    def _can_ko_active(self):
        if not self.active or not self.opp_active:
            return False
        if self.active_id == C.RAGING_BOLT_EX:
            return self._can_bellowing_thunder() and self.bt_potential_damage >= self.opp_active_hp
        if self.active_id == C.TEAL_MASK_OGERPON_EX:
            my_e = _count_energy(self.active)
            opp_e = _count_energy(self.opp_active)
            return 30 + (my_e + opp_e) * 30 >= self.opp_active_hp
        return False


    # ── Board Evaluation ──

    def evaluate_state(self):
        """Evaluate current board state as a numeric score.
        Higher = better position for us. All weights from params."""
        score = 0.0
        my_prizes = len(self.me.prize)
        opp_prizes = len(self.opponent.prize)

        score += (6 - my_prizes) * self.p("eval_prize_taken", 200)
        score -= (6 - opp_prizes) * self.p("eval_prize_given", 150)

        if self.bolt_ready:
            score += self.p("eval_bt_ready", 400)
        elif self.bolt_has_lightning or self.bolt_has_fighting:
            score += self.p("eval_bt_partial", 200)

        if self._can_ko_active():
            score += self.p("eval_can_ko", 500) + self._opp_prize_value() * self.p("eval_can_ko_prize_mult", 200)

        if not self._can_ko_active() and self.opp_active:
            if self.bt_potential_damage + 70 >= self.opp_active_hp:
                score += self.p("eval_near_ko", 200)

        score += len(self.ogerpon_on_field) * self.p("eval_ogerpon_value", 150)
        score += self.total_field_energy * self.p("eval_field_energy", 50)
        score += self.grass_in_hand * self.p("eval_grass_in_hand", 80)

        has_supporter = any(cid in (C.CRISPIN, C.LILLIE_DETERMINATION, C.BOSS_ORDERS)
                            for cid in self.hand_ids)
        if has_supporter:
            score += self.p("eval_supporter_in_hand", 100)
        score += min(len(self.hand_ids), 7) * self.p("eval_hand_card", 30)

        if my_prizes <= 2:
            has_boss = C.BOSS_ORDERS in self.hand_ids
            best_target = self._best_boss_target()
            if has_boss and best_target:
                prize_val = prize_count(best_target)
                if my_prizes <= prize_val:
                    score += self.p("eval_boss_win", 800)

        score += len(self.bolt_on_field) * self.p("eval_bolt_on_field", 100)

        bench_bolt_ready = any(
            p and p.id == C.RAGING_BOLT_EX
            and any(e == 4 for e in p.energies)
            and any(e == 6 for e in p.energies)
            for p in (self.me.bench or [])
        )
        if bench_bolt_ready:
            score += self.p("eval_bench_bolt_ready", 300)

        opp_max_dmg = self._estimate_opp_damage()
        if self.active and self.active.hp <= opp_max_dmg:
            score += self.p("eval_active_ko_risk", -300)
            if not bench_bolt_ready:
                score += self.p("eval_no_backup_risk", -200)

        if self.me.deckCount and self.me.deckCount <= 5:
            score += self.p("eval_deck_out_risk", -200)

        bench_ex_count = sum(1 for p in (self.me.bench or [])
                             if p and card_table.get(p.id) and card_table[p.id].ex)
        if bench_ex_count >= 3:
            score += self.p("eval_bench_liability", -100)

        return score

    # ── Opponent Model ──

    def _simulate_opponent_turn(self):
        """Return list of (scenario_name, prize_change, risk_score) tuples."""
        scenarios = []
        if not self.opp_active:
            return [("nothing", 0, 0)]

        opp_max_dmg = self._estimate_opp_damage()

        # Scenario 1: opponent KOs our active
        if self.active and self.active.hp <= opp_max_dmg:
            my_prize_val = prize_count(self.active)
            scenarios.append(("ko_active", my_prize_val, -400))
        else:
            scenarios.append(("damage_active", 0, -100))

        # Scenario 2: opponent uses Boss on bench ex
        bench_targets = []
        for p in (self.me.bench or []):
            if not p:
                continue
            data = card_table.get(p.id)
            if data and data.ex and p.hp <= opp_max_dmg:
                bench_targets.append(p)
        if bench_targets:
            target = max(bench_targets, key=lambda p: prize_count(p))
            scenarios.append(("boss_bench_ko", prize_count(target), -500))

        # Scenario 3: opponent does nothing significant
        scenarios.append(("nothing", 0, 0))

        return scenarios

    # ── Engine Search (real 1-turn lookahead via cg search API) ──

    def _my_unseen_cards(self):
        """My deck+prize contents = full decklist minus everything I can see."""
        remaining = Counter(my_deck)

        def dec(cid):
            if remaining.get(cid, 0) > 0:
                remaining[cid] -= 1

        for c in (self.me.hand or []):
            dec(c.id)
        for c in (self.me.discard or []):
            dec(c.id)
        for p in list(self.me.active or []) + list(self.me.bench or []):
            if not p:
                continue
            dec(p.id)
            for c in (p.energyCards or []):
                dec(c.id)
            for c in (p.tools or []):
                dec(c.id)
            for c in (p.preEvolution or []):
                dec(c.id)
        for c in (self.state.stadium or []):
            if c is not None and getattr(c, 'playerIndex', -1) == self.my_index:
                dec(c.id)

        out = []
        for cid, cnt in remaining.items():
            out.extend([cid] * cnt)
        return out

    def _infer_opp_energy_mix(self):
        """Bayesian estimate of the opponent's basic-energy type distribution
        from public evidence only (energies attached to their Pokemon + basic
        energy cards in their discard). Dirichlet(alpha=1) smoothing over the
        8 basic types -> posterior mean = (count_t + 1) / (total + 8).
        Generic: uses only observable energy-type ids, no opponent-specific
        card/deck knowledge, so it applies to any opponent archetype."""
        counts = Counter()
        opp = self.opponent
        for p in list(opp.active or []) + list(opp.bench or []):
            if not p:
                continue
            for e in (p.energies or []):
                if e in ALL_BASIC_ENERGY_IDS:
                    counts[e] += 1
        for c in (opp.discard or []):
            if c.id in ALL_BASIC_ENERGY_IDS:
                counts[c.id] += 1
        total = sum(counts.values())
        alpha = 1  # weak uniform prior
        types = list(ALL_BASIC_ENERGY_IDS)
        weights = [counts.get(t, 0) + alpha for t in types]
        wsum = sum(weights)
        probs = [w / wsum for w in weights]
        return types, probs

    def _sample_opp_energy(self, n):
        if n <= 0:
            return []
        if not self.p("rule_opp_energy_inference", 1):
            return [C.BASIC_FIGHTING_ENERGY] * n
        types, probs = self._infer_opp_energy_mix()
        return _rng.choices(types, weights=probs, k=n)

    def _predict_hidden(self):
        """Build hidden-zone predictions for search_begin.
        Own deck/prize: decklist minus seen cards, shuffled so repeated calls
        sample different draw orders / prize splits (multi-sample rollouts).
        Opponent zones: Pokemon identity is filler (rollforward stops at our
        turn boundary in the common case), but energy-card filler is sampled
        from a posterior over basic-energy types inferred from what the
        opponent has actually played/discarded, instead of a hardcoded type —
        matters when endgame deepening simulates the opponent's turn."""
        unseen = self._my_unseen_cards()
        _rng.shuffle(unseen)
        n_prize = len(self.me.prize)
        n_deck = self.me.deckCount or 0
        need = n_prize + n_deck
        if len(unseen) < need:
            unseen = unseen + [C.BASIC_LIGHTNING_ENERGY] * (need - len(unseen))
        your_prize = unseen[:n_prize]
        your_deck = unseen[n_prize:n_prize + n_deck]

        opp = self.opponent
        filler_pokemon = C.RAGING_BOLT_EX  # any valid Basic Pokemon card ID
        opp_deck_n = max(0, (opp.deckCount or 0) - 1)
        opp_deck = [filler_pokemon] + self._sample_opp_energy(opp_deck_n)
        opp_prize = self._sample_opp_energy(len(opp.prize))
        opp_hand = self._sample_opp_energy(opp.handCount or 0)
        opp_active = []
        if opp.active and len(opp.active) > 0 and opp.active[0] is None:
            opp_active = [filler_pokemon]
        return your_deck, your_prize, opp_deck, opp_prize, opp_hand, opp_active

    # Default weights for the linear board evaluator. Names match params.json
    # keys (self.p() reads overrides from there). Signs already fold in the
    # "cost" direction (e.g. se_prize_given is negative: more prizes given up
    # is bad) so scoring is a plain sum(feature_i * weight_i) -- this is the
    # same convention a fitted linear-regression weight vector would use
    # (see fit_eval_weights.py / PRML ch.3 ridge-regression tuning).
    _EVAL_FEATURE_WEIGHTS = {
        "se_prize_taken": 900, "se_prize_given": -800, "se_closing": 300,
        "se_opp_closing": -400, "se_field_energy": 60, "se_bolt_ready": 350,
        "se_can_ko": 400, "se_bench_bolt_ready": 250,
        "se_active_dies_prize": -350, "se_active_dies_energy": -40,
        "se_no_backup": -200, "se_disabled": -150, "se_dot": -60,
        "se_opp_damage": 2.0, "se_my_damage": -1.0, "se_bench_damage": -0.6,
        "se_bench_ko_risk": -120, "se_hand_card": 40, "se_refuel_resource": 50,
        "se_ogerpon": 120, "se_board_pokemon": 30, "se_opp_energy": -25,
    }

    def _extract_eval_features(self, state, my_index):
        """Named feature dict for the linear board evaluator. Single source of
        truth shared by the live weighted-sum evaluator (_eval_search_state)
        and the offline weight-fitting script (fit_eval_weights.py), so
        weights fitted from self-play outcome data map directly onto these
        same param names."""
        me = state.players[my_index]
        opp = state.players[1 - my_index]
        f = {}

        f["se_prize_taken"] = float(6 - len(me.prize))
        f["se_prize_given"] = float(6 - len(opp.prize))
        f["se_closing"] = 1.0 if len(me.prize) <= 2 else 0.0
        f["se_opp_closing"] = 1.0 if len(opp.prize) <= 2 else 0.0

        my_all = [p for p in list(me.active or []) + list(me.bench or []) if p]
        opp_all = [p for p in list(opp.active or []) + list(opp.bench or []) if p]
        my_energy = sum(len(p.energies or []) for p in my_all)
        f["se_field_energy"] = float(my_energy)

        act = me.active[0] if me.active else None
        opp_act = opp.active[0] if opp.active else None

        act_bolt_ready = False
        can_ko_now = False
        if act and act.id == C.RAGING_BOLT_EX:
            has_l = any(e == 4 for e in (act.energies or []))
            has_f = any(e == 6 for e in (act.energies or []))
            act_bolt_ready = has_l and has_f
            if act_bolt_ready and opp_act and my_energy * 70 >= opp_act.hp:
                can_ko_now = True
        f["se_bolt_ready"] = 1.0 if act_bolt_ready else 0.0
        f["se_can_ko"] = 1.0 if can_ko_now else 0.0

        bench_bolt_ready = False
        for p in (me.bench or []):
            if p and p.id == C.RAGING_BOLT_EX:
                b_l = any(e == 4 for e in (p.energies or []))
                b_f = any(e == 6 for e in (p.energies or []))
                if b_l and b_f:
                    bench_bolt_ready = True
                    break
        f["se_bench_bolt_ready"] = 1.0 if bench_bolt_ready else 0.0

        active_dies_prize = active_dies_energy = no_backup = 0.0
        if act and opp_act:
            opp_dmg = _static_opp_max_damage(opp_act, act.id)
            if act.hp <= opp_dmg:
                active_dies_prize = float(prize_count(act))
                active_dies_energy = float(len(act.energies or []))
                if not any(p and len(p.energies or []) > 0 for p in (me.bench or [])):
                    no_backup = 1.0
        f["se_active_dies_prize"] = active_dies_prize
        f["se_active_dies_energy"] = active_dies_energy
        f["se_no_backup"] = no_backup

        f["se_disabled"] = 1.0 if (me.paralyzed or me.asleep) else 0.0
        f["se_dot"] = 1.0 if (me.poisoned or me.burned) else 0.0

        f["se_opp_damage"] = float((opp_act.maxHp - opp_act.hp)) if opp_act else 0.0
        f["se_my_damage"] = float((act.maxHp - act.hp)) if act else 0.0

        # ── bench damage (generic bench-snipe / spread awareness) ──
        bench_damage_total = 0.0
        bench_ko_risk_prizes = 0.0
        for p in (me.bench or []):
            if not p:
                continue
            dmg = (p.maxHp or 0) - (p.hp or 0)
            if dmg <= 0:
                continue
            bench_damage_total += dmg
            pdata = card_table.get(p.id)
            if pdata and pdata.ex and (p.hp or 0) <= 60:
                bench_ko_risk_prizes += prize_count(p)
        f["se_bench_damage"] = bench_damage_total
        f["se_bench_ko_risk"] = bench_ko_risk_prizes

        hand_ids = [c.id for c in (me.hand or [])]
        f["se_hand_card"] = float(min(len(hand_ids), 8))
        refuel = sum(1 for cid in hand_ids
                     if cid in (C.CRISPIN, C.ENERGY_RETRIEVAL) or cid in BASIC_ENERGY_IDS)
        f["se_refuel_resource"] = float(min(refuel, 4))

        f["se_ogerpon"] = float(sum(1 for p in my_all if p.id == C.TEAL_MASK_OGERPON_EX))
        f["se_board_pokemon"] = float(len(my_all))
        f["se_opp_energy"] = float(sum(len(p.energies or []) for p in opp_all))
        return f

    def _eval_search_state(self, state, my_index):
        """Static evaluation of a simulated end-of-turn board from my perspective.
        Focus: prize race + can I keep attacking next turn + what do I lose to
        the opponent's response."""
        if state is None:
            return 0.0
        if state.result >= 0:
            return 1_000_000.0 if state.result == my_index else -1_000_000.0
        feats = self._extract_eval_features(state, my_index)
        return sum(v * self.p(k, self._EVAL_FEATURE_WEIGHTS[k]) for k, v in feats.items())

    def _opp_sim_picks(self, sel):
        """Simple adversarial policy for the opponent's simulated turn:
        strongest attack > end turn > forced first options."""
        best_attack = None
        end_idx = None
        for i, o in enumerate(sel.option):
            if o.type == OptionType.ATTACK:
                a = attack_table.get(o.attackId)
                dmg = (a.damage or 0) if a else 0
                if best_attack is None or dmg > best_attack[0]:
                    best_attack = (dmg, i)
            elif o.type == OptionType.END and end_idx is None:
                end_idx = i
        if best_attack is not None and best_attack[0] > 0:
            return [best_attack[1]]
        if end_idx is not None:
            return [end_idx]
        n = len(sel.option)
        need = max(sel.minCount, 1 if sel.maxCount > 0 else 0)
        return list(range(min(need, n, sel.maxCount)))

    def _rollforward(self, search_state, max_steps=None, sim_opp=None, horizon=2):
        """Play out the rest of my turn (heuristic policy), then optionally the
        opponent's response turn (strongest attack), stopping `horizon` turns
        after the current one / at game end. Returns the final State.
        horizon=2: stop at the start of my next turn (default).
        horizon=4: continue through opponent's turn + my next full turn
        (endgame deepening)."""
        from cg.api import search_step
        if sim_opp is None:
            # Default off: benchmarked neutral in the mid-game because the
            # simulated opponent's hand is filler; endgame deepening overrides.
            sim_opp = bool(self.p("engine_search_opp_turn", 0))
        if max_steps is None:
            max_steps = 14 + (16 if (sim_opp or horizon > 2) else 0)
        t0 = self.state.turn
        ss = search_state
        last_state = ss.observation.current if ss.observation else None
        for _ in range(max_steps):
            obs = ss.observation
            if obs is None or obs.current is None:
                break
            last_state = obs.current
            st = obs.current
            if st.result >= 0:
                break
            sel = obs.select
            if sel is None or not sel.option:
                break
            if st.yourIndex == self.my_index:
                if st.turn >= t0 + horizon:
                    break  # evaluation horizon reached
                try:
                    sub = RagingBoltPolicy(obs)
                    picks = sub.choose()
                except Exception as _e:
                    _record_exception("rollforward_my_turn_choose", _e)
                    picks = list(range(min(max(sel.minCount, 1), len(sel.option))))
            else:
                if not sim_opp:
                    break
                try:
                    picks = self._opp_sim_picks(sel)
                except Exception as _e:
                    _record_exception("rollforward_opp_sim_picks", _e)
                    break
            n = len(sel.option)
            picks = [i for i in picks if 0 <= i < n][:sel.maxCount]
            if len(picks) < sel.minCount:
                extra = [i for i in range(n) if i not in picks]
                picks += extra[:sel.minCount - len(picks)]
            ss = search_step(ss.searchId, picks)
        if ss.observation and ss.observation.current is not None:
            last_state = ss.observation.current
        return last_state

    def _engine_search_choose(self, ranked, scores):
        """Real lookahead: apply each top candidate in the engine's search tree,
        greedily finish my turn, evaluate the resulting board, and pick via a
        UCB1 bandit allocation of rollout budget (AIMA ch.5 MCTS selection
        rule, applied to our flat single-ply setting -- root has k
        already-enumerated children with no deeper tree needed, so full MCTS
        collapses to a bandit). Hidden zones are re-shuffled every rollout
        (AIMA's "determinization" treatment of hidden-info games) so
        draw-dependent lines (Lillie, Burst Roar) are averaged over multiple
        possible decks/hands. Returns [index] or None."""
        if self.select.maxCount != 1:
            return None
        from cg.api import search_begin, search_end, search_step
        top_k = min(int(self.p("engine_search_top_k", 5)), len(ranked))
        w_heur = self.p("engine_search_heuristic_weight", 0.15)
        candidates = list(ranked[:top_k])
        # The free energy attach is use-it-or-lose-it: always let the search
        # compare attach-first vs attack-now, even if no attach ranks top-k
        # (observed: AI attacked before attaching, wasting the attach)
        if not any(self.select.option[i].type == OptionType.ATTACH for i in candidates):
            attach_idxs = [i for i in ranked
                           if self.select.option[i].type == OptionType.ATTACH]
            if attach_idxs:
                candidates.append(attach_idxs[0])

        # Endgame deepening: when either side is within 2 prizes of winning,
        # one mistake decides the game and the board is simple enough that a
        # 2-turn lookahead (incl. opponent's strongest response) is meaningful.
        endgame = (len(self.me.prize) <= self.p("endgame_prize_threshold", 2)
                   or len(self.opponent.prize) <= self.p("endgame_prize_threshold", 2))
        horizon = 4 if (endgame and self.p("rule_endgame_deepen", 1)) else 2
        sim_opp = True if horizon > 2 else None

        def rollout_once(i):
            _TELEMETRY["rollout_attempt_count"] += 1
            preds = self._predict_hidden()  # fresh shuffle every rollout
            root = search_begin(self.obs, *preds)
            try:
                ss = search_step(root.searchId, [i])
                final_state = self._rollforward(ss, sim_opp=sim_opp, horizon=horizon)
                value = self._eval_search_state(final_state, self.my_index)
                _TELEMETRY["rollout_success_count"] += 1
                return value
            except Exception:
                _TELEMETRY["rollout_error_count"] += 1
                raise
            finally:
                try:
                    search_end()
                except Exception as _e:
                    _record_exception("engine_search_end_cleanup", _e)

        # Default OFF: 100g confirmation was statistically inconclusive
        # (vs Lucario 16.0% vs 20.0% baseline, z~0.74; mirror 53-47, also not
        # significant) -- neither a clear win nor a clear regression at this
        # sample size. Exploration constant C=200 and rollout budgets
        # (+3 mid-game / +8 endgame) were never calibrated; a proper C sweep
        # is the natural next step before trusting this path either way.
        if self.p("rule_ucb1_search", 0):
            return self._ucb1_choose(candidates, scores, w_heur, endgame, rollout_once)

        # Legacy flat allocation, kept for rollback/ablation: every candidate
        # gets the same fixed number of rollouts, no adaptive reallocation.
        n_samples = max(1, int(self.p("engine_search_samples", 1)))
        if endgame and self.p("rule_endgame_deepen", 1):
            n_samples = max(n_samples, int(self.p("endgame_samples", 2)))
        totals = {i: 0.0 for i in candidates}
        counts = {i: 0 for i in candidates}
        for i in candidates:
            for _ in range(n_samples):
                try:
                    totals[i] += rollout_once(i)
                    counts[i] += 1
                except Exception:
                    continue
        best = None
        for i in candidates:
            if not counts[i]:
                continue
            q = totals[i] / counts[i] + scores[i] * w_heur
            if best is None or q > best[0]:
                best = (q, i)
        return [best[1]] if best else None

    def _ucb1_choose(self, candidates, scores, w_heur, endgame, rollout_once):
        """UCB1 bandit allocation of rollout budget across candidate moves.
        Replaces the earlier one-shot "boost top-2 if close" heuristic
        (rule_adaptive_samples, disabled -- regressed vs Lucario via a
        winner's-curse/selection-bias effect: a single coarse margin check
        could lock a lucky-but-wrong leader in). UCB1 re-evaluates after
        every single new rollout instead, so a leader that only *looked*
        good by variance gets deprioritized as soon as real samples come in,
        rather than being reinforced by one batch decision."""
        N = {i: 0 for i in candidates}
        total = {i: 0.0 for i in candidates}

        # Seed every candidate with one rollout so UCB1 has data to reason
        # about from the start.
        for i in candidates:
            try:
                v = rollout_once(i)
                N[i] += 1
                total[i] += v
            except Exception:
                continue

        extra_budget = int(self.p(
            "ucb1_endgame_extra_rollouts" if endgame else "ucb1_extra_rollouts",
            8 if endgame else 3))
        # C is NOT the textbook sqrt(2) -- that assumes rewards normalized to
        # [0,1]. _eval_search_state scores are raw linear-eval units (order
        # of hundreds), so C must be calibrated to that scale; the old
        # "adaptive_margin" (~120) was already a "how close counts as noise"
        # estimate in the same units -- start near that magnitude and retune
        # via the same A/B benchmark protocol as everything else in this file.
        c = self.p("ucb1_exploration_c", 200.0)

        for _ in range(extra_budget):
            total_n = max(1, sum(N.values()))
            best_i, best_ucb = None, None
            for i in candidates:
                if N[i] == 0:
                    ucb = float("inf")  # never-successfully-sampled -- try it
                else:
                    q = total[i] / N[i]
                    ucb = q + c * math.sqrt(math.log(total_n) / N[i])
                if best_ucb is None or ucb > best_ucb:
                    best_ucb, best_i = ucb, i
            if best_i is None:
                break
            try:
                v = rollout_once(best_i)
                N[best_i] += 1
                total[best_i] += v
            except Exception:
                N[best_i] += 1  # count the attempt so a persistently-erroring
                                 # candidate can't dominate the UCB score forever

        best = None
        for i in candidates:
            if N[i] == 0:
                continue
            q = total[i] / N[i] + scores[i] * w_heur
            if best is None or q > best[0]:
                best = (q, i)
        return [best[1]] if best else None

    # ── Shallow Search ──

    def choose_with_search(self):
        """Choose action using shallow search + evaluation."""
        if not self.select.option or self.select.maxCount == 0:
            return []

        if self.context != SelectContext.MAIN:
            return self.choose()

        if self.p("use_engine_search", 1):
            _TELEMETRY["search_attempt_count"] += 1
            try:
                ranked_e, scores_e = self.rank()
                picked = self._engine_search_choose(ranked_e, scores_e)
                if picked is not None:
                    _TELEMETRY["search_success_count"] += 1
                    if ranked_e and picked[0] != ranked_e[0]:
                        # Search picked something other than the plain
                        # heuristic's top-ranked option -- a cheap proxy for
                        # "search result overrode the heuristic ranking"
                        # (there is no confidence gate yet; see PR3+ Branch
                        # "Search Override Confidence Gate" in the roadmap).
                        _TELEMETRY["search_override_count"] += 1
                    return picked
                _TELEMETRY["search_fallback_count"] += 1
            except Exception as _e:
                _record_exception("engine_search_choose_toplevel", _e)
                _TELEMETRY["search_fallback_count"] += 1
                # fall back to heuristic blend below

        ranked, scores = self.rank()
        n = len(self.select.option)
        min_c = max(0, min(self.select.minCount, n))
        max_c = max(min_c, min(self.select.maxCount, n))

        # Current state evaluation
        current_eval = self.evaluate_state()

        # Opponent risk
        opp_scenarios = self._simulate_opponent_turn()
        avg_risk = sum(s[2] for s in opp_scenarios) / len(opp_scenarios)

        # Evaluate top candidates
        top_k = min(5, n)
        candidates = []
        for rank_pos in range(top_k):
            i = ranked[rank_pos]
            opt = self.select.option[i]
            immediate = scores[i]

            # Estimate future state change
            future_delta = self._estimate_action_impact(opt)

            # Risk adjustment
            risk_adj = 0
            if opt.type == OptionType.ATTACK:
                # After attacking, turn ends - opponent will respond
                risk_adj = avg_risk
            elif opt.type == OptionType.END:
                risk_adj = avg_risk

            w_imm = self.p("search_weight_immediate", 0.6)
            w_fut = self.p("search_weight_future", 0.3)
            w_risk = self.p("search_weight_risk", 0.1)
            final = immediate * w_imm + future_delta * w_fut + risk_adj * w_risk

            if self.p("use_value_model", False):
                try:
                    from value_model import predict_action_value
                    v = predict_action_value(self.obs, self.my_index, opt)
                    if v is not None:
                        w_val = self.p("value_model_weight", 0.2)
                        final += v * w_val * 1000
                except Exception as _e:
                    _record_exception("value_model_predict", _e)

            candidates.append((final, i, immediate, future_delta, risk_adj))

        candidates.sort(key=lambda x: -x[0])

        result = []
        for final, i, _, _, _ in candidates:
            if len(result) >= max_c:
                break
            if final > 0 or len(result) < min_c:
                result.append(i)

        if not result and min_c > 0:
            result = list(range(min(min_c, n)))

        return result

    def _estimate_action_impact(self, opt):
        """Estimate how an action changes board evaluation. All weights from params."""
        t = opt.type
        delta = 0

        if t == OptionType.ATTACK:
            if opt.attackId == BELLOWING_THUNDER:
                if self._can_ko_active():
                    delta += self._opp_prize_value() * self.p("impact_bt_ko_prize_mult", 300)
                    delta += self.bt_total_energy * 30
                else:
                    delta += self.bt_total_energy * self.p("impact_bt_energy_value", 40)
                delta -= self.bt_total_energy * self.p("impact_bt_energy_loss", 20)
            elif opt.attackId == MYRIAD_LEAF_SHOWER:
                my_e = _count_energy(self.active) if self.active else 0
                opp_e = _count_energy(self.opp_active) if self.opp_active else 0
                dmg = 30 + (my_e + opp_e) * 30
                if self.opp_active and dmg >= self.opp_active_hp:
                    delta += self._opp_prize_value() * self.p("impact_mls_ko_prize_mult", 300)
                else:
                    delta += dmg * self.p("impact_mls_damage_mult", 1.5)
            elif opt.attackId == BURST_ROAR:
                delta += self.p("impact_burst_roar_value", 50)
                delta += self.p("impact_burst_roar_penalty", -100)

        elif t == OptionType.ABILITY:
            c = get_card(self.obs, opt.area, opt.index, self.my_index)
            if c and c.id == C.TEAL_MASK_OGERPON_EX and self.grass_in_hand > 0:
                delta += self.p("impact_teal_dance", 150)
                if self.bolt_ready:
                    delta += self.p("impact_teal_dance_bolt_ready", 100)

        elif t == OptionType.PLAY:
            c = get_card(self.obs, AreaType.HAND, opt.index, self.my_index)
            if c:
                if c.id == C.CRISPIN:
                    delta += min(self.energy_in_discard, 3) * self.p("impact_crispin_per_energy", 100)
                    if not self.bolt_ready:
                        delta += self.p("impact_crispin_bolt_bonus", 200)
                elif c.id == C.LILLIE_DETERMINATION:
                    delta += max(0, 6 - len(self.hand_ids)) * self.p("impact_lillie_per_card", 40)
                elif c.id == C.BOSS_ORDERS:
                    best = self._best_boss_target()
                    if best:
                        delta += prize_count(best) * self.p("impact_boss_prize_mult", 300)
                elif c.id == C.RAGING_BOLT_EX:
                    delta += self.p("impact_play_bolt", 200)
                elif c.id == C.TEAL_MASK_OGERPON_EX:
                    delta += self.p("impact_play_ogerpon", 250)
                elif c.id in (C.ULTRA_BALL, C.BUG_CATCHING_SET, C.TERA_ORB):
                    delta += self.p("impact_search_item", 150)
                elif c.id == C.ENERGY_RETRIEVAL:
                    delta += min(self.energy_in_discard, 2) * self.p("impact_energy_retrieval_per", 80)

        elif t == OptionType.ATTACH:
            energy_card = get_card(self.obs, AreaType.HAND, opt.index, self.my_index)
            target = get_card(self.obs, getattr(opt, 'inPlayArea', None),
                              getattr(opt, 'inPlayIndex', None), self.my_index)
            if energy_card and target:
                if target.id == C.RAGING_BOLT_EX:
                    has_l = any(e == 4 for e in target.energies)
                    has_f = any(e == 6 for e in target.energies)
                    if (energy_card.id == C.BASIC_LIGHTNING_ENERGY and not has_l) or \
                       (energy_card.id == C.BASIC_FIGHTING_ENERGY and not has_f):
                        delta += self.p("impact_attach_bt_req", 350)
                    else:
                        delta += self.p("impact_attach_other", 50)
                elif target.id == C.TEAL_MASK_OGERPON_EX:
                    delta += self.p("impact_attach_ogerpon", 80)

        elif t == OptionType.RETREAT:
            if self.active and self.active.hp <= self._estimate_opp_damage():
                delta += self.p("impact_retreat_safety", 200)
            else:
                delta += self.p("impact_retreat_penalty", -50)

        elif t == OptionType.END:
            delta += self.p("impact_end_penalty", -50)

        return delta


def agent(obs_dict):
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return my_deck

    global pre_turn
    global ability_used_teal_dance

    if pre_turn != obs.current.turn:
        pre_turn = obs.current.turn
        ability_used_teal_dance = False

    _t0 = time.monotonic()
    try:
        policy = RagingBoltPolicy(obs)
        if obs.select.context == SelectContext.MAIN:
            return policy.choose_with_search()
        return policy.choose()
    finally:
        _TELEMETRY["decision_runtime_ms"].append((time.monotonic() - _t0) * 1000.0)
