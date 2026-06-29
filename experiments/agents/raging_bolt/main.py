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
            return 50

        if t == OptionType.YES:
            if self.context == SelectContext.IS_FIRST:
                return 100
            return 500

        if t == OptionType.NO:
            if self.context == SelectContext.IS_FIRST:
                return 900
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
            if cid in (C.ULTRA_BALL, C.BUG_CATCHING_SET, C.TERA_ORB, C.POKEGEAR):
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
            return self.p("score_play_pokemon_raging_bolt", 500)
        if cid == C.TEAL_MASK_OGERPON_EX:
            return self.p("score_play_pokemon_ogerpon", 600)

        if cid == C.CRISPIN:
            if self.energy_in_hand >= 4:
                return 500
            if self.field_ready and self.energy_in_discard >= 1:
                return 1500
            if not self.bolt_ready and self.energy_in_discard >= 1:
                return 1300
            if self.energy_in_discard >= 1:
                return 1100
            return 600

        if cid == C.LILLIE_DETERMINATION:
            if self.field_ready:
                if len(self.hand_ids) <= 3:
                    return 1000
                return 700
            if len(self.hand_ids) <= 2:
                return 1300
            return 1200

        if cid == C.BOSS_ORDERS:
            if self.active_hp_pct <= 20:
                return 200
            best_target = self._best_boss_target()
            if best_target:
                return 1600
            if self.can_ko_with_bt:
                return 400
            return 800

        if self.field_ready:
            if cid == C.ENERGY_RETRIEVAL:
                if self.energy_in_discard >= 2:
                    return 1200
                if self.energy_in_discard >= 1:
                    return 1000
                return 400
            if cid == C.ULTRA_BALL:
                return 600
            if cid == C.POKEGEAR:
                return 500
            if cid == C.BUG_CATCHING_SET:
                return 500
            if cid == C.TERA_ORB:
                return 500
        else:
            if cid == C.ULTRA_BALL:
                return 1100
            if cid == C.BUG_CATCHING_SET:
                return 1100
            if cid == C.TERA_ORB:
                return 1050
            if cid == C.POKEGEAR:
                return 1000
            if cid == C.ENERGY_RETRIEVAL:
                if self.energy_in_discard >= 2:
                    return 900
                return 500

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
            if is_active:
                return 500 + target_energy * 30
            return 400

        if target.id == C.TEAL_MASK_OGERPON_EX:
            if energy_id == C.BASIC_GRASS_ENERGY:
                return 600
            return 400

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
        if self.active_hp_pct <= 30:
            return 400
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
                return 850 if ogre_on_field is None else 400
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
                return 620 if self.energy_in_discard >= 2 else 450
            if c.id == C.POKEMON_CATCHER:
                return 500
            if c.id == C.BUG_CATCHING_SET:
                return 520
            if c.id == C.POKEGEAR:
                return 480
            if c.id == C.UNFAIR_STAMP:
                return 550
            if c.id in BASIC_ENERGY_IDS:
                return 550
            return 400

        if ctx in (SelectContext.DISCARD, SelectContext.DISCARD_ENERGY_CARD):
            energy_id = self._get_energy_type_from_opt(opt) if ctx == SelectContext.DISCARD_ENERGY_CARD else c.id
            is_on_bolt = False
            is_active_bolt = False
            if ctx == SelectContext.DISCARD_ENERGY_CARD:
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
                except Exception:
                    pass
            opp_dmg = self._estimate_opp_damage()
            bolt_will_die = is_active_bolt and self.active and self.active.hp <= opp_dmg
            if bolt_will_die:
                return 900
            if is_on_bolt and energy_id in (C.BASIC_LIGHTNING_ENERGY, C.BASIC_FIGHTING_ENERGY):
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
            return 400

        if ctx == SelectContext.ATTACH_FROM:
            if c.id in BASIC_ENERGY_IDS:
                return 600
            return 400

        if ctx == SelectContext.SETUP_ACTIVE_POKEMON:
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

        if ctx == SelectContext.TO_DECK:
            return 400

        if ctx == SelectContext.TO_HAND_ENERGY:
            if c.id == C.BASIC_GRASS_ENERGY:
                return 700
            if c.id == C.BASIC_LIGHTNING_ENERGY:
                return 600
            if c.id == C.BASIC_FIGHTING_ENERGY:
                return 500
            return 400

        return 400

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
                except Exception:
                    pass
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
            except Exception:
                pass
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
        except Exception:
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

    # ── Shallow Search ──

    def choose_with_search(self):
        """Choose action using shallow search + evaluation."""
        if not self.select.option or self.select.maxCount == 0:
            return []

        if self.context != SelectContext.MAIN:
            return self.choose()

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
                except Exception:
                    pass

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

    policy = RagingBoltPolicy(obs)
    if obs.select.context == SelectContext.MAIN:
        return policy.choose_with_search()
    return policy.choose()
