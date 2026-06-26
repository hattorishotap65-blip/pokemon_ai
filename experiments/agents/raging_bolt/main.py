from __future__ import annotations

import json
import os
from collections import defaultdict

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


BURST_ROAR = 71
BELLOWING_THUNDER = 72
MYRIAD_LEAF_SHOWER = 120

BASIC_ENERGY_IDS = {C.BASIC_GRASS_ENERGY, C.BASIC_LIGHTNING_ENERGY, C.BASIC_FIGHTING_ENERGY}

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

    def p(self, key, default=0):
        return P.get(key, default)

    def choose(self):
        if not self.select.option or self.select.maxCount == 0:
            return []

        n = len(self.select.option)
        min_c = max(0, min(self.select.minCount, n))
        max_c = max(min_c, min(self.select.maxCount, n))

        scores = []
        for i, opt in enumerate(self.select.option):
            scores.append((self._score_option(i, opt), i))

        scores.sort(key=lambda x: -x[0])

        result = []
        for score, i in scores:
            if len(result) >= max_c:
                break
            if score > 0 or len(result) < min_c:
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
                return 900
            return 500

        if t == OptionType.NO:
            if self.context == SelectContext.IS_FIRST:
                return 100
            return 400

        if t == OptionType.ATTACK:
            return self._score_attack(opt)

        if t == OptionType.ABILITY:
            return self._score_ability(i, opt)

        if t == OptionType.PLAY:
            return self._score_play(i, opt)

        if t == OptionType.ATTACH:
            return self._score_attach(i, opt)

        if t == OptionType.RETREAT:
            return self._score_retreat()

        if t == OptionType.EVOLVE:
            return 800

        if t in (OptionType.CARD, OptionType.TOOL_CARD, OptionType.ENERGY_CARD):
            return self._score_card_select(i, opt)

        if t == OptionType.NUMBER:
            return self._score_number(opt)

        return 300

    def _score_attack(self, opt):
        aid = opt.attackId

        if aid == BELLOWING_THUNDER:
            energy_count = _count_energy(self.active) if self.active else 0
            potential_damage = energy_count * 70
            if self.opp_active and potential_damage >= self.opp_active_hp:
                return self.p("score_attack_bellowing_thunder", 900) + 300
            if energy_count >= self.p("bellowing_thunder_base_threshold", 2):
                return self.p("score_attack_bellowing_thunder", 900)
            return self.p("score_attack_bellowing_thunder", 900) - 200

        if aid == MYRIAD_LEAF_SHOWER:
            my_energy = _count_energy(self.active) if self.active else 0
            opp_energy = _count_energy(self.opp_active) if self.opp_active else 0
            total_energy = my_energy + opp_energy
            potential_damage = 30 + total_energy * 30
            if self.opp_active and potential_damage >= self.opp_active_hp:
                return self.p("score_attack_myriad_leaf_shower", 700) + 300
            return self.p("score_attack_myriad_leaf_shower", 700)

        if aid == BURST_ROAR:
            hand_size = len(self.hand_ids)
            if hand_size <= self.p("burst_roar_hand_threshold", 3):
                return self.p("score_attack_burst_roar_low_hand", 800)
            return self.p("score_attack_burst_roar", 400)

        return 500

    def _score_ability(self, i, opt):
        c = get_card(self.obs, opt.area, opt.index, self.my_index)
        if c and c.id == C.TEAL_MASK_OGERPON_EX:
            if self.energy_in_hand > 0:
                return self.p("score_ability_teal_dance", 850)
            return 100
        return 500

    def _score_play(self, i, opt):
        c = get_card(self.obs, AreaType.HAND, opt.index, self.my_index)
        if c is None:
            return 300
        cid = c.id

        if cid == C.RAGING_BOLT_EX:
            return self.p("score_play_pokemon_raging_bolt", 500)
        if cid == C.TEAL_MASK_OGERPON_EX:
            return self.p("score_play_pokemon_ogerpon", 600)

        if cid == C.CRISPIN:
            if self.energy_in_hand >= self.p("crispin_energy_threshold", 3):
                return self.p("score_supporter_crispin_with_energy", 300)
            return self.p("score_supporter_crispin", 700)

        if cid == C.LILLIE_DETERMINATION:
            if len(self.hand_ids) <= self.p("lillie_hand_threshold", 3):
                return self.p("score_supporter_lillie_low_hand", 800)
            return self.p("score_supporter_lillie", 600)

        if cid == C.BOSS_ORDERS:
            if self.opp_active and self._can_ko_active():
                return self.p("score_supporter_boss_can_ko", 1200)
            return self.p("score_supporter_boss", 900)

        if cid == C.ULTRA_BALL:
            return self.p("score_item_ultra_ball", 500)
        if cid == C.POKEGEAR:
            return self.p("score_item_pokegear", 400)
        if cid == C.BUG_CATCHING_SET:
            return self.p("score_item_bug_catching_set", 450)
        if cid == C.TERA_ORB:
            return self.p("score_item_tera_orb", 550)
        if cid == C.ENERGY_RETRIEVAL:
            if self.energy_in_discard >= self.p("energy_retrieval_threshold", 2):
                return self.p("score_item_energy_retrieval_low_energy", 700)
            return self.p("score_item_energy_retrieval", 500)
        if cid == C.POKEMON_CATCHER:
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

        is_active = getattr(opt, 'inPlayArea', None) == AreaType.ACTIVE

        if target.id == C.TEAL_MASK_OGERPON_EX:
            if is_active:
                return self.p("score_attach_energy_ogerpon_active", 700)
            return self.p("score_attach_energy_ogerpon_bench", 500)

        if target.id == C.RAGING_BOLT_EX:
            if is_active:
                return self.p("score_attach_energy_raging_bolt_active", 600)
            return self.p("score_attach_energy_raging_bolt_bench", 400)

        return self.p("score_attach_energy_other", 200)

    def _score_retreat(self):
        if self.active_hp_pct <= self.p("retreat_hp_threshold_pct", 30):
            return self.p("score_retreat_damaged_active", 400)
        return self.p("score_retreat", 100)

    def _score_card_select(self, i, opt):
        c = get_card(self.obs,
                     getattr(opt, 'area', None) or AreaType.HAND,
                     opt.index, self.my_index)
        if c is None:
            return 300

        ctx = self.context

        if ctx == SelectContext.SEARCH_POKEMON:
            if c.id == C.RAGING_BOLT_EX:
                bolt_on_field, _ = _find_pokemon_on_field(self.me, C.RAGING_BOLT_EX)
                return 800 if bolt_on_field is None else 400
            if c.id == C.TEAL_MASK_OGERPON_EX:
                ogre_on_field, _ = _find_pokemon_on_field(self.me, C.TEAL_MASK_OGERPON_EX)
                return 850 if ogre_on_field is None else 400
            return 300

        if ctx == SelectContext.SEARCH_SUPPORTER:
            if c.id == C.CRISPIN:
                return 700
            if c.id == C.LILLIE_DETERMINATION:
                return 600
            if c.id == C.BOSS_ORDERS:
                return 500
            return 400

        if ctx in (SelectContext.DISCARD, SelectContext.DISCARD_ENERGY):
            if c.id in BASIC_ENERGY_IDS:
                return 600
            data = card_table.get(c.id)
            if data and data.cardType in (CardType.BASIC_ENERGY, CardType.SPECIAL_ENERGY):
                return 500
            return 400

        if ctx == SelectContext.SEARCH_BASIC_ENERGY:
            if c.id == C.BASIC_GRASS_ENERGY:
                return 700
            if c.id == C.BASIC_LIGHTNING_ENERGY:
                return 600
            if c.id == C.BASIC_FIGHTING_ENERGY:
                return 500
            return 400

        if hasattr(SelectContext, 'SETUP_ACTIVE_POKEMON') and ctx == SelectContext.SETUP_ACTIVE_POKEMON:
            if c.id == C.TEAL_MASK_OGERPON_EX:
                return 800
            if c.id == C.RAGING_BOLT_EX:
                return 700
            return 300

        if hasattr(SelectContext, 'SETUP_BENCH_POKEMON') and ctx == SelectContext.SETUP_BENCH_POKEMON:
            if c.id == C.RAGING_BOLT_EX:
                return 800
            if c.id == C.TEAL_MASK_OGERPON_EX:
                return 700
            return 300

        if ctx == SelectContext.SWITCH_POKEMON:
            if c.id == C.RAGING_BOLT_EX:
                bolt_energy = _count_energy(c) if hasattr(c, 'energies') else 0
                return 700 + bolt_energy * 50
            if c.id == C.TEAL_MASK_OGERPON_EX:
                return 600
            return 300

        return 400

    def _score_number(self, opt):
        num = opt.number if hasattr(opt, 'number') else 0
        if self.context == SelectContext.DISCARD_ENERGY:
            return 500 + num * 100
        return 500

    def _can_ko_active(self):
        if not self.active or not self.opp_active:
            return False
        if self.active_id == C.RAGING_BOLT_EX:
            energy = _count_energy(self.active)
            return energy * 70 >= self.opp_active_hp
        if self.active_id == C.TEAL_MASK_OGERPON_EX:
            my_e = _count_energy(self.active)
            opp_e = _count_energy(self.opp_active)
            return 30 + (my_e + opp_e) * 30 >= self.opp_active_hp
        return False


def agent(obs_dict):
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return my_deck

    global pre_turn
    global ability_used_teal_dance

    if pre_turn != obs.current.turn:
        pre_turn = obs.current.turn
        ability_used_teal_dance = False

    return RagingBoltPolicy(obs).choose()
