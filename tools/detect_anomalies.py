"""
Anomaly detection for Pokemon TCG battle logs.

Deck-agnostic: uses deck_profile roles/evolves_from/evolves_to/policy when
available, falls back to universal option-type rules otherwise.

Universal rules:
  type=10 -> Ability (NOT turn-ending)
  type=12 -> Retreat (NEVER treated as Attack)
  type=13 + attackId -> Attack (turn-ending)
  type=14 -> End (turn-ending)
"""
from __future__ import annotations
import json
from typing import Any

_OT_ABILITY = 10
_OT_RETREAT = 12
_OT_ATTACK  = 13
_OT_END     = 14


def _is_attack(opt: dict) -> bool:
    return opt.get("type") == _OT_ATTACK and opt.get("attackId") is not None


def _is_ability(opt: dict) -> bool:
    return opt.get("type") == _OT_ABILITY


def _is_retreat(opt: dict) -> bool:
    return opt.get("type") == _OT_RETREAT


def _is_end(opt: dict) -> bool:
    return opt.get("type") == _OT_END


def _classify_option(opt: dict) -> str:
    if _is_attack(opt):  return "attack"
    if _is_ability(opt): return "ability"
    if _is_retreat(opt): return "retreat"
    if _is_end(opt):     return "end"
    t = opt.get("type")
    return f"type_{t}" if t is not None else "unknown"


# ---------------------------------------------------------------------------
# Log normalization
# ---------------------------------------------------------------------------

def normalize_event(raw: dict, filename: str = "") -> dict | None:
    """Convert a raw log record into a normalized event dict."""
    if "game_id" not in raw and "gameId" not in raw:
        return None

    candidates = raw.get("top_candidates") or raw.get("candidates") or []
    ss = raw.get("state_summary") or {}

    selected = next((c for c in candidates if c.get("selected")), None)
    has_attack = any(
        (c.get("is_attack") or (_is_attack(c))) for c in candidates
    )
    attack_ids = [
        c.get("attackId") or c.get("attack_id")
        for c in candidates
        if c.get("is_attack") or _is_attack(c)
    ]
    attack_ids = [a for a in attack_ids if a is not None]

    sel_type  = None
    sel_class = None
    sel_cid   = None
    sel_cname = None
    if selected:
        sel_type = selected.get("option_type") or selected.get("type")
        sel_class = selected.get("option_class") or _classify_option(selected)
        sel_cid   = selected.get("resolved_card_id")
        sel_cname = selected.get("resolved_card_name")

    return {
        "file":               filename,
        "game_id":            raw.get("game_id") or raw.get("gameId") or "unknown",
        "turn":               raw.get("turn", 0),
        "game_turn":          raw.get("game_turn") or ss.get("turn") or raw.get("turn", 0),
        "player":             ss.get("your_index", 0),
        "phase":              "select_action",
        "active_id":          ss.get("active_card_id"),
        "active_name":        ss.get("active_card_name"),
        "active_energy_count": ss.get("active_energy", 0),
        "hand_count":         ss.get("hand_count", 0),
        "select_type":        raw.get("select_type"),
        "select_context":     raw.get("select_context"),
        "available_options":  candidates,
        "selected_option":    selected or {},
        "selected_option_type":  sel_type,
        "selected_option_class": sel_class,
        "selected_card_id":      sel_cid,
        "selected_card_name":    sel_cname,
        "has_legal_attack":  has_attack,
        "has_retreat_option": any(
            (c.get("is_retreat") or _is_retreat(c)) for c in candidates
        ),
        "available_attack_ids": attack_ids,
        "reason":            raw.get("reason", ""),
        "selected_score":    raw.get("selected_score"),
        "opp_active_hp":     ss.get("opp_active_hp"),
        "bench_count":       ss.get("bench_count", 0),
        # deck_log fields for bench inference
        "bellibolt_in_play":    (raw.get("deck_log") or {}).get("bellibolt", {}).get("bellibolt_in_play", False),
        "bellibolt_is_active":  (raw.get("deck_log") or {}).get("bellibolt", {}).get("bellibolt_is_active", False),
        # Voltorb scaling data
        "iono_lightning_count": (raw.get("deck_log") or {}).get("voltorb", {}).get("iono_lightning_count"),
        "estimated_voltorb_damage": (raw.get("deck_log") or {}).get("voltorb", {}).get("estimated_voltorb_damage"),
    }


# ---------------------------------------------------------------------------
# Deck profile helpers
# ---------------------------------------------------------------------------

class DeckProfile:
    """Thin wrapper around deck_profile.json for role/policy lookups."""

    def __init__(self, data: dict | None = None):
        self._data = data or {}
        self._roles: dict[str, str] = {}
        self._evolves_from: dict[str, int] = {}
        self._evolves_to: dict[str, int] = {}
        self._attack_req: dict[str, int] = {}
        self._overattach_after: dict[str, int] = {}
        self._main_attackers: set[str] = set()
        self._sub_attackers: set[str] = set()
        self._setup_cards: set[str] = set()
        self._voltorb_policy: dict = {}
        self._iono_pokemon_ids: set[str] = set()
        self._build_indexes()

    def _build_indexes(self):
        d = self._data
        for cid in d.get("main_attackers", []):
            s = str(cid)
            self._main_attackers.add(s)
            self._roles[s] = "main_attacker"
        for cid in d.get("sub_attackers", []):
            s = str(cid)
            self._sub_attackers.add(s)
            self._roles.setdefault(s, "sub_attacker")
        for cid in d.get("setup_cards", []):
            s = str(cid)
            self._setup_cards.add(s)
            self._roles.setdefault(s, "evolution_base")
        for cid in d.get("energy_engine", []):
            self._roles.setdefault(str(cid), "energy_engine")
        for cid in d.get("draw_engine", []):
            self._roles.setdefault(str(cid), "draw_support")
        for cid in d.get("backup_attackers", []):
            s = str(cid)
            self._sub_attackers.add(s)
            self._roles.setdefault(s, "backup_attacker")

        vsp = d.get("voltorb_scaling_policy") or {}
        self._voltorb_policy = vsp
        for cid in vsp.get("count_lightning_energy_on_card_ids", []):
            self._iono_pokemon_ids.add(str(cid))
        main_scaler = vsp.get("main_scaling_attacker")
        if main_scaler:
            self._main_attackers.add(str(main_scaler))

        cards = d.get("cards") or {}
        for cid_str, info in cards.items():
            if isinstance(info, dict):
                if "role" in info:
                    self._roles[cid_str] = info["role"]
                ef = info.get("evolves_from")
                if ef is not None:
                    self._evolves_from[cid_str] = int(ef)
                et = info.get("evolves_to")
                if et is not None:
                    self._evolves_to[cid_str] = int(et)
                req = info.get("attack_energy_required")
                if req is not None:
                    self._attack_req[cid_str] = int(req)
                oa = info.get("avoid_overattach_after")
                if oa is not None:
                    self._overattach_after[cid_str] = int(oa)

    def role(self, cid) -> str:
        return self._roles.get(str(cid), "")

    def is_attacker(self, cid) -> bool:
        s = str(cid)
        return s in self._main_attackers or s in self._sub_attackers

    def evolves_from(self, cid):
        return self._evolves_from.get(str(cid))

    def attack_energy_required(self, cid):
        return self._attack_req.get(str(cid))

    def overattach_after(self, cid):
        return self._overattach_after.get(str(cid))

    @property
    def deck_id(self) -> str:
        return self._data.get("deck_id", "unknown")

    @property
    def voltorb_scaling_attacker(self) -> str | None:
        cid = self._voltorb_policy.get("main_scaling_attacker")
        return str(cid) if cid else None

    @property
    def voltorb_attack_req(self) -> int:
        return int(self._voltorb_policy.get("required_lightning_to_attack", 2))

    @property
    def voltorb_high_damage_threshold(self) -> int:
        return int(self._voltorb_policy.get("estimated_damage_high_threshold", 120))

    @property
    def iono_pokemon_ids(self) -> set[str]:
        return self._iono_pokemon_ids


# ---------------------------------------------------------------------------
# Turn tracking
# ---------------------------------------------------------------------------

def group_events_by_turn(events: list[dict]) -> dict:
    """Group normalized events by (game_id, game_turn) for turn tracking."""
    turns: dict[tuple, list] = {}
    for ev in events:
        key = (ev["game_id"], ev["game_turn"])
        turns.setdefault(key, []).append(ev)
    return turns


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

_ANOMALY_COUNTER = 0


def _next_id() -> str:
    global _ANOMALY_COUNTER
    _ANOMALY_COUNTER += 1
    return f"A{_ANOMALY_COUNTER:04d}"


def _anomaly(
    severity: str, atype: str, ev: dict, *,
    expected: str = "", actual: str = "", why: str = "",
    confidence: str = "medium",
    suggested_fix_area: list | None = None,
    extra: dict | None = None,
) -> dict:
    a = {
        "id":                    _next_id(),
        "severity":              severity,
        "type":                  atype,
        "file":                  ev.get("file", ""),
        "game_id":               ev.get("game_id", "unknown"),
        "turn":                  ev.get("game_turn", ev.get("turn", 0)),
        "player":                ev.get("player", 0),
        "active_id":             ev.get("active_id"),
        "active_name":           ev.get("active_name"),
        "active_energy_count":   ev.get("active_energy_count"),
        "selected_option_type":  ev.get("selected_option_type"),
        "selected_option_class": ev.get("selected_option_class"),
        "available_attack_ids":  ev.get("available_attack_ids", []),
        "expected_action":       expected,
        "actual_action":         actual,
        "why_suspicious":        why,
        "confidence":            confidence,
        "suggested_fix_area":    suggested_fix_area or [],
        "related_events":        [],
    }
    if extra:
        a.update(extra)
    return a


def detect_single_event_anomalies(ev: dict, profile: DeckProfile) -> list[dict]:
    """Detect anomalies that can be determined from a single select event."""
    results = []
    sel = ev.get("selected_option") or {}
    has_atk = ev.get("has_legal_attack")
    sel_class = ev.get("selected_option_class", "")

    # --- end_when_attack_available ---
    if has_atk and sel_class == "end":
        results.append(_anomaly(
            "critical", "end_when_attack_available", ev,
            expected="attack", actual="end",
            why="End was selected while a legal Attack option existed.",
            confidence="high",
            suggested_fix_area=[
                "turn_rule_engine.py",
                "policy.py final_score integration",
            ],
        ))

    # --- retreat_when_attack_available ---
    if has_atk and sel_class == "retreat":
        results.append(_anomaly(
            "high", "retreat_when_attack_available", ev,
            expected="attack", actual="retreat",
            why="Retreat was selected while a legal Attack option existed.",
            confidence="high",
            suggested_fix_area=[
                "ionos_rules.py retreat_suppression",
                "turn_rule_engine.py",
            ],
        ))

    # --- overattach_to_ready_attacker ---
    if ev.get("selected_option_type") == 8:
        cid = str(ev.get("selected_card_id") or "")
        target_cid = str(sel.get("resolved_card_id") or "")
        active_cid = str(ev.get("active_id") or "")
        active_en  = ev.get("active_energy_count", 0) or 0
        req = profile.attack_energy_required(active_cid)
        oa  = profile.overattach_after(active_cid)
        if oa is not None and active_en >= oa:
            results.append(_anomaly(
                "medium", "overattach_to_ready_attacker", ev,
                expected="attach_to_other_target",
                actual=f"attach_to_{active_cid}_energy_{active_en}",
                why=f"Energy attached to a Pokemon that already has {active_en} energy (overattach threshold: {oa}).",
                confidence="medium",
                suggested_fix_area=[
                    "ionos_rules.py score_energy_attachment",
                    "deck_profile.json energy policy",
                ],
            ))

    # --- stage1_without_base_search (TO_HAND context) ---
    if ev.get("select_context") == 7:
        sel_cid = str(ev.get("selected_card_id") or "")
        base = profile.evolves_from(sel_cid)
        if base is not None:
            opts = ev.get("available_options") or []
            # Check candidates for base presence context - simplified check
            results.append(_anomaly(
                "high", "stage1_without_base_search", ev,
                expected=f"search_for_base_{base}_or_basic",
                actual=f"searched_stage1_{sel_cid}",
                why=f"Stage 1 Pokemon (evolves from {base}) was searched, but base may not be in play.",
                confidence="low",
                suggested_fix_area=[
                    "ionos_rules.py search_target_scoring",
                    "deck_profile.json search policy",
                ],
            ))

    return results


def detect_turn_anomalies(
    turn_events: list[dict], profile: DeckProfile
) -> list[dict]:
    """Detect anomalies across a full game turn (multiple selects)."""
    results = []
    if not turn_events:
        return results

    attack_available_in_turn = any(ev.get("has_legal_attack") for ev in turn_events)
    attack_selected_in_turn  = any(
        ev.get("selected_option_class") == "attack" for ev in turn_events
    )
    ability_used_in_turn     = any(
        ev.get("selected_option_class") == "ability" for ev in turn_events
    )

    # --- attack_available_but_no_attack (turn-level) ---
    if attack_available_in_turn and not attack_selected_in_turn:
        last_ev = turn_events[-1]
        results.append(_anomaly(
            "high", "attack_available_but_no_attack", last_ev,
            expected="attack", actual=last_ev.get("selected_option_class", "unknown"),
            why="A legal attack was available during this turn, but the turn ended without attacking.",
            confidence="high",
            suggested_fix_area=[
                "turn_rule_engine.py",
                "policy.py final_score integration",
                "ionos_rules.py score_bonus attack rules",
            ],
        ))

    # --- ability_without_followup_attack ---
    if ability_used_in_turn and attack_available_in_turn and not attack_selected_in_turn:
        ability_ev = next(
            (ev for ev in turn_events if ev.get("selected_option_class") == "ability"),
            turn_events[-1],
        )
        results.append(_anomaly(
            "medium", "ability_without_followup_attack", ability_ev,
            expected="ability_then_attack",
            actual="ability_then_no_attack",
            why="Ability was used and a legal attack was available, but the turn ended without attacking.",
            confidence="medium",
            suggested_fix_area=[
                "ionos_rules.py ability scoring",
                "policy.py action priority",
            ],
        ))

    # --- ability_breaks_attack_ready_state ---
    for i, ev in enumerate(turn_events):
        if ev.get("selected_option_class") != "ability":
            continue
        cid = str(ev.get("selected_card_id") or "")
        role = profile.role(cid)
        if role in ("draw_support", "sub_attacker"):
            if ev.get("has_legal_attack"):
                prev_can_attack = ev.get("has_legal_attack")
                next_evts = turn_events[i+1:]
                next_no_attack = next_evts and not any(
                    nev.get("has_legal_attack") for nev in next_evts
                )
                if prev_can_attack and next_no_attack:
                    results.append(_anomaly(
                        "high", "ability_breaks_attack_ready_state", ev,
                        expected="attack_or_safe_ability",
                        actual=f"ability_{cid}_broke_attack_state",
                        why="Ability usage appears to have broken the attack-ready state.",
                        confidence="low",
                        suggested_fix_area=[
                            "ionos_rules.py ability scoring",
                            "deck_profile.json ability_policy",
                        ],
                    ))

    # --- stronger_ready_bench_attacker_not_promoted ---
    # Only flag when active is a NON-attacker (evolution_base, draw_support, etc.)
    # and the turn is past early setup (game_turn >= 3).
    # An attacker that simply lacks energy is normal and not flagged here.
    if not attack_available_in_turn and not attack_selected_in_turn:
        retreat_available_in_turn = any(ev.get("has_retreat_option") for ev in turn_events)
        if retreat_available_in_turn:
            last_ev     = turn_events[-1]
            game_turn   = last_ev.get("game_turn", 0) or 0
            active_cid  = str(last_ev.get("active_id") or "")
            active_en   = last_ev.get("active_energy_count", 0) or 0
            bench_count = last_ev.get("bench_count", 0) or 0

            active_is_attacker = profile.is_attacker(active_cid)
            active_role = profile.role(active_cid) or "unknown"

            # Only flag non-attackers stuck in active, after early setup
            if not active_is_attacker and bench_count > 0 and game_turn >= 3:
                confidence = "medium"
                bb_in_play   = last_ev.get("bellibolt_in_play", False)
                bb_is_active = last_ev.get("bellibolt_is_active", False)
                if bb_in_play and not bb_is_active:
                    confidence = "high"

                results.append(_anomaly(
                    "medium", "stronger_ready_bench_attacker_not_promoted", last_ev,
                    expected="retreat_to_bench_attacker",
                    actual=f"stayed_with_{active_role}_{active_cid}",
                    why=(
                        f"Non-attacker ({active_cid}, role={active_role}) is active on turn {game_turn}. "
                        f"Retreat was available with {bench_count} bench Pokemon, "
                        f"but no switch to an attacker occurred."
                    ),
                    confidence=confidence,
                    suggested_fix_area=[
                        "policy.py _score_retreat",
                        "ionos_rules.py retreat scoring",
                        "deck_profile.json switch_policy",
                    ],
                ))

    # --- ko_available_but_no_attack ---
    for ev in turn_events:
        if not ev.get("has_legal_attack"):
            continue
        opp_hp = ev.get("opp_active_hp")
        if opp_hp is None or opp_hp <= 0:
            continue
        sel = ev.get("selected_option") or {}
        vt_atk_score = sel.get("voltorb_attack_score", 0)
        reason = ev.get("reason", "")
        if "can_ko" in reason and ev.get("selected_option_class") != "attack":
            results.append(_anomaly(
                "critical", "ko_available_but_no_attack", ev,
                expected="attack_for_ko",
                actual=ev.get("selected_option_class", "unknown"),
                why=f"A KO was likely available (opponent HP: {opp_hp}) but attack was not selected.",
                confidence="medium",
                suggested_fix_area=[
                    "policy.py _score_attack ko_opponent",
                    "ionos_rules.py attack rules",
                ],
            ))
            break

    # --- voltorb_scaling_attack_underused ---
    voltorb_cid = profile.voltorb_scaling_attacker
    if voltorb_cid and attack_available_in_turn and not attack_selected_in_turn:
        for ev in turn_events:
            if not ev.get("has_legal_attack"):
                continue
            active_cid = str(ev.get("active_id") or "")
            est_dmg    = ev.get("estimated_voltorb_damage")
            lightning  = ev.get("iono_lightning_count")
            if active_cid == voltorb_cid and est_dmg is not None and est_dmg > 0:
                threshold = profile.voltorb_high_damage_threshold
                confidence = "high" if est_dmg >= threshold else "medium" if est_dmg >= 60 else "low"
                results.append(_anomaly(
                    "medium", "voltorb_scaling_attack_underused", ev,
                    expected="attack_with_voltorb_scaling_damage",
                    actual=ev.get("selected_option_class", "unknown"),
                    why=(
                        f"Voltorb was active with estimated damage {est_dmg} "
                        f"({lightning or '?'} Lightning on Iono's Pokemon) "
                        f"but the turn ended without attacking."
                    ),
                    confidence=confidence,
                    suggested_fix_area=[
                        "ionos_rules.py score_voltorb_attack",
                        "data/deck_profile.json voltorb_scaling_policy",
                    ],
                    extra={"estimated_voltorb_damage": est_dmg,
                           "iono_lightning_count": lightning},
                ))
                break

    # --- best_damage_attacker_not_selected ---
    if attack_selected_in_turn and voltorb_cid:
        for ev in turn_events:
            if ev.get("selected_option_class") != "attack":
                continue
            active_cid = str(ev.get("active_id") or "")
            est_dmg    = ev.get("estimated_voltorb_damage")
            if active_cid != voltorb_cid and est_dmg is not None and est_dmg >= profile.voltorb_high_damage_threshold:
                results.append(_anomaly(
                    "low", "best_damage_attacker_not_selected", ev,
                    expected=f"consider_voltorb_scaling_attack_{est_dmg}dmg",
                    actual=f"attacked_with_{active_cid}",
                    why=(
                        f"Attacked with {active_cid} instead of Voltorb. "
                        f"Voltorb estimated damage was {est_dmg} (high scaling), "
                        f"which may have been a better prize-race option."
                    ),
                    confidence="low",
                    suggested_fix_area=[
                        "ionos_rules.py attacker selection",
                        "data/deck_profile.json attacker_selection_policy",
                    ],
                    extra={"estimated_voltorb_damage": est_dmg,
                           "actual_attacker": active_cid},
                ))
                break

    return results


def detect_all_anomalies(
    events: list[dict], profile: DeckProfile
) -> list[dict]:
    """Run all anomaly detection on a list of normalized events."""
    global _ANOMALY_COUNTER
    _ANOMALY_COUNTER = 0

    all_anomalies = []

    # Single-event anomalies
    for ev in events:
        all_anomalies.extend(detect_single_event_anomalies(ev, profile))

    # Turn-level anomalies
    turns = group_events_by_turn(events)
    for _key, turn_events in sorted(turns.items()):
        all_anomalies.extend(detect_turn_anomalies(turn_events, profile))

    # Deduplicate by (type, game_id, turn) - keep highest severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    seen: dict[tuple, dict] = {}
    for a in all_anomalies:
        key = (a["type"], a["game_id"], a["turn"])
        if key not in seen or severity_order.get(a["severity"], 9) < severity_order.get(seen[key]["severity"], 9):
            seen[key] = a
    deduped = sorted(seen.values(), key=lambda x: (severity_order.get(x["severity"], 9), x["turn"]))

    # Re-number
    for i, a in enumerate(deduped, 1):
        a["id"] = f"A{i:04d}"

    return deduped


def build_summary(anomalies: list[dict], files_count: int, events: list[dict]) -> dict:
    """Build summary statistics from anomaly list."""
    from collections import Counter
    sev_counts = Counter(a["severity"] for a in anomalies)
    type_counts = Counter(a["type"] for a in anomalies)
    game_ids = set(ev["game_id"] for ev in events)
    game_turns = set((ev["game_id"], ev["game_turn"]) for ev in events)

    summary = {
        "files":       files_count,
        "games":       len(game_ids),
        "turns":       len(game_turns),
        "actions":     len(events),
        "anomalies_total": len(anomalies),
        "critical":    sev_counts.get("critical", 0),
        "high":        sev_counts.get("high", 0),
        "medium":      sev_counts.get("medium", 0),
        "low":         sev_counts.get("low", 0),
        "info":        sev_counts.get("info", 0),
    }
    for atype in [
        "attack_available_but_no_attack",
        "end_when_attack_available",
        "retreat_when_attack_available",
        "ability_without_followup_attack",
        "high_value_attack_not_used",
        "ko_available_but_no_attack",
        "ability_breaks_attack_ready_state",
        "overattach_to_ready_attacker",
        "stage1_without_base_search",
        "duplicate_stage1_search",
        "low_value_search",
        "discarded_protected_card",
        "stronger_ready_bench_attacker_not_promoted",
        "voltorb_scaling_attack_underused",
        "best_damage_attacker_not_selected",
    ]:
        summary[atype] = type_counts.get(atype, 0)

    return summary
