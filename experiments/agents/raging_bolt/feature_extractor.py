"""Extract board state features for value model training and inference."""
from __future__ import annotations

RAGING_BOLT = 63
OGERPON = 96
CRISPIN = 1198
LILLIE = 1227
BOSS = 1182
ENERGY_RETRIEVAL = 1118
SEARCH_ITEMS = {1121, 1122, 1094, 1127}  # Ultra Ball, Pokegear, Bug Catching, Tera Orb
GRASS = 1
LIGHTNING = 4
FIGHTING = 6


def extract_features(obs, my_index):
    """Extract numeric features from observation. Returns dict."""
    st = obs.current
    me = st.players[my_index]
    opp = st.players[1 - my_index]

    my_act = me.active[0] if me.active else None
    opp_act = opp.active[0] if opp.active else None

    all_mine = list(me.active or []) + list(me.bench or [])

    bolt_count = sum(1 for p in all_mine if p and p.id == RAGING_BOLT)
    ogerpon_count = sum(1 for p in all_mine if p and p.id == OGERPON)

    bolt_has_l = False
    bolt_has_f = False
    if my_act and my_act.id == RAGING_BOLT:
        bolt_has_l = any(e == LIGHTNING for e in my_act.energies)
        bolt_has_f = any(e == FIGHTING for e in my_act.energies)

    bench_bolt_ready = any(
        p and p.id == RAGING_BOLT
        and any(e == LIGHTNING for e in p.energies)
        and any(e == FIGHTING for e in p.energies)
        for p in (me.bench or [])
    )

    total_energy = sum(len(p.energies) for p in all_mine if p)
    grass_on_field = sum(
        sum(1 for e in p.energies if e == GRASS)
        for p in all_mine if p
    )
    lightning_on_field = sum(
        sum(1 for e in p.energies if e == LIGHTNING)
        for p in all_mine if p
    )
    fighting_on_field = sum(
        sum(1 for e in p.energies if e == FIGHTING)
        for p in all_mine if p
    )

    hand_ids = [c.id for c in (me.hand or [])]
    grass_hand = sum(1 for c in hand_ids if c == GRASS)
    lightning_hand = sum(1 for c in hand_ids if c == LIGHTNING)
    fighting_hand = sum(1 for c in hand_ids if c == FIGHTING)

    bt_damage = total_energy * 70
    can_ko = (
        my_act is not None and my_act.id == RAGING_BOLT
        and bolt_has_l and bolt_has_f
        and opp_act is not None and bt_damage >= opp_act.hp
    )
    near_ko = (
        not can_ko and opp_act is not None and bt_damage + 70 >= opp_act.hp
    )

    my_prizes = len(me.prize)
    opp_prizes = len(opp.prize)

    try:
        from cg.api import all_card_data
        CT = {c.cardId: c for c in all_card_data()}
        opp_data = CT.get(opp_act.id) if opp_act else None
        boss_target = False
        if bolt_has_l and bolt_has_f and my_prizes <= 2:
            for p in (opp.bench or []):
                if p:
                    d = CT.get(p.id)
                    if d and d.ex and p.hp <= bt_damage:
                        boss_target = True
                        break
    except Exception:
        boss_target = False

    active_ko_risk = False
    if my_act and opp_act:
        active_ko_risk = my_act.hp <= 200

    no_next_attacker = not bench_bolt_ready and (not my_act or my_act.id != RAGING_BOLT)

    field_ready = (
        ogerpon_count >= 1 and bolt_count >= 1 and bolt_has_l and bolt_has_f
    )

    return {
        "my_prizes": my_prizes,
        "opp_prizes": opp_prizes,
        "prize_diff": my_prizes - opp_prizes,
        "my_active_id": my_act.id if my_act else 0,
        "my_active_hp": my_act.hp if my_act else 0,
        "my_active_hp_pct": (my_act.hp * 100 // my_act.maxHp) if my_act and my_act.maxHp > 0 else 0,
        "opp_active_id": opp_act.id if opp_act else 0,
        "opp_active_hp": opp_act.hp if opp_act else 0,
        "opp_active_hp_pct": (opp_act.hp * 100 // opp_act.maxHp) if opp_act and opp_act.maxHp > 0 else 0,
        "my_bench_count": len([p for p in (me.bench or []) if p]),
        "opp_bench_count": len([p for p in (opp.bench or []) if p]),
        "raging_bolt_count": bolt_count,
        "ogerpon_count": ogerpon_count,
        "active_is_raging_bolt": int(my_act is not None and my_act.id == RAGING_BOLT),
        "active_is_ogerpon": int(my_act is not None and my_act.id == OGERPON),
        "bolt_ready": int(bolt_has_l and bolt_has_f),
        "bolt_has_lightning": int(bolt_has_l),
        "bolt_has_fighting": int(bolt_has_f),
        "bench_bolt_ready": int(bench_bolt_ready),
        "total_field_energy": total_energy,
        "grass_energy_on_field": grass_on_field,
        "lightning_energy_on_field": lightning_on_field,
        "fighting_energy_on_field": fighting_on_field,
        "grass_in_hand": grass_hand,
        "lightning_in_hand": lightning_hand,
        "fighting_in_hand": fighting_hand,
        "hand_size": len(hand_ids),
        "deck_count": me.deckCount if me.deckCount else 0,
        "has_crispin": int(CRISPIN in hand_ids),
        "has_lillie": int(LILLIE in hand_ids),
        "has_boss": int(BOSS in hand_ids),
        "has_energy_retrieval": int(ENERGY_RETRIEVAL in hand_ids),
        "has_search_item": int(any(c in SEARCH_ITEMS for c in hand_ids)),
        "can_ko_active": int(can_ko),
        "near_ko_active": int(near_ko),
        "boss_win_available": int(boss_target),
        "active_ko_risk": int(active_ko_risk),
        "no_next_attacker_risk": int(no_next_attacker),
        "field_ready": int(field_ready),
    }


FEATURE_KEYS = list(extract_features.__code__.co_varnames)[:0] or [
    "my_prizes", "opp_prizes", "prize_diff",
    "my_active_id", "my_active_hp", "my_active_hp_pct",
    "opp_active_id", "opp_active_hp", "opp_active_hp_pct",
    "my_bench_count", "opp_bench_count",
    "raging_bolt_count", "ogerpon_count",
    "active_is_raging_bolt", "active_is_ogerpon",
    "bolt_ready", "bolt_has_lightning", "bolt_has_fighting", "bench_bolt_ready",
    "total_field_energy", "grass_energy_on_field", "lightning_energy_on_field", "fighting_energy_on_field",
    "grass_in_hand", "lightning_in_hand", "fighting_in_hand",
    "hand_size", "deck_count",
    "has_crispin", "has_lillie", "has_boss", "has_energy_retrieval", "has_search_item",
    "can_ko_active", "near_ko_active", "boss_win_available",
    "active_ko_risk", "no_next_attacker_risk", "field_ready",
]
