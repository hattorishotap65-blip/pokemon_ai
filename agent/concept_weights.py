"""
Advantage weights per deck archetype and game phase.

Weight > 1.0 = emphasise this advantage type for this archetype/phase.
Weight < 1.0 = de-emphasise it.

Used by advantage.evaluate_total_advantage() to scale each adv value
before summing into the final concept_weighted_advantage_score.
"""

_ADV_KEYS = (
    "card_adv", "board_adv", "energy_adv", "tempo_adv",
    "prize_adv", "resource_adv", "info_adv", "risk_reduction_adv",
)

_DEFAULT: dict[str, float] = {k: 1.0 for k in _ADV_KEYS}

WEIGHTS: dict[str, dict[str, dict[str, float]]] = {
    "aggro": {
        "early": dict(card_adv=0.9,  board_adv=1.1,  energy_adv=1.4, tempo_adv=1.5,
                      prize_adv=1.2,  resource_adv=0.6, info_adv=0.3, risk_reduction_adv=0.7),
        "mid":   dict(card_adv=0.7,  board_adv=0.9,  energy_adv=1.3, tempo_adv=1.6,
                      prize_adv=1.5,  resource_adv=0.5, info_adv=0.3, risk_reduction_adv=0.6),
        "late":  dict(card_adv=0.5,  board_adv=0.6,  energy_adv=1.0, tempo_adv=1.4,
                      prize_adv=1.8,  resource_adv=0.5, info_adv=0.3, risk_reduction_adv=0.7),
    },
    "setup_midrange": {
        "early": dict(card_adv=1.2,  board_adv=1.5,  energy_adv=1.2, tempo_adv=0.9,
                      prize_adv=0.6,  resource_adv=0.8, info_adv=0.5, risk_reduction_adv=1.0),
        "mid":   dict(card_adv=0.9,  board_adv=1.2,  energy_adv=1.2, tempo_adv=1.3,
                      prize_adv=1.3,  resource_adv=0.9, info_adv=0.4, risk_reduction_adv=1.0),
        "late":  dict(card_adv=0.6,  board_adv=0.8,  energy_adv=1.0, tempo_adv=1.1,
                      prize_adv=1.7,  resource_adv=1.2, info_adv=0.4, risk_reduction_adv=1.3),
    },
    "combo": {
        "early": dict(card_adv=1.8,  board_adv=1.2,  energy_adv=0.8, tempo_adv=0.6,
                      prize_adv=0.5,  resource_adv=1.0, info_adv=0.6, risk_reduction_adv=1.2),
        "mid":   dict(card_adv=1.5,  board_adv=1.1,  energy_adv=1.0, tempo_adv=0.8,
                      prize_adv=0.8,  resource_adv=0.9, info_adv=0.5, risk_reduction_adv=1.1),
        "late":  dict(card_adv=1.0,  board_adv=0.8,  energy_adv=1.1, tempo_adv=1.2,
                      prize_adv=1.4,  resource_adv=1.2, info_adv=0.5, risk_reduction_adv=1.3),
    },
    "control": {
        "early": dict(card_adv=1.3,  board_adv=1.0,  energy_adv=0.7, tempo_adv=0.6,
                      prize_adv=0.6,  resource_adv=1.5, info_adv=0.8, risk_reduction_adv=1.6),
        "mid":   dict(card_adv=1.2,  board_adv=0.9,  energy_adv=0.7, tempo_adv=0.7,
                      prize_adv=0.8,  resource_adv=1.6, info_adv=0.7, risk_reduction_adv=1.5),
        "late":  dict(card_adv=0.8,  board_adv=0.7,  energy_adv=0.8, tempo_adv=1.0,
                      prize_adv=1.3,  resource_adv=1.8, info_adv=0.6, risk_reduction_adv=1.8),
    },
    "resource_loop": {
        "early": dict(card_adv=1.2,  board_adv=1.0,  energy_adv=1.2, tempo_adv=0.7,
                      prize_adv=0.7,  resource_adv=1.8, info_adv=0.5, risk_reduction_adv=1.5),
        "mid":   dict(card_adv=1.0,  board_adv=1.0,  energy_adv=1.3, tempo_adv=0.9,
                      prize_adv=1.0,  resource_adv=1.7, info_adv=0.5, risk_reduction_adv=1.4),
        "late":  dict(card_adv=0.8,  board_adv=0.8,  energy_adv=1.2, tempo_adv=1.1,
                      prize_adv=1.3,  resource_adv=2.0, info_adv=0.5, risk_reduction_adv=1.6),
    },
    "prize_race": {
        "early": dict(card_adv=0.9,  board_adv=1.2,  energy_adv=1.3, tempo_adv=1.4,
                      prize_adv=1.4,  resource_adv=0.7, info_adv=0.4, risk_reduction_adv=0.8),
        "mid":   dict(card_adv=0.7,  board_adv=1.0,  energy_adv=1.2, tempo_adv=1.5,
                      prize_adv=1.7,  resource_adv=0.6, info_adv=0.4, risk_reduction_adv=0.7),
        "late":  dict(card_adv=0.5,  board_adv=0.7,  energy_adv=1.0, tempo_adv=1.5,
                      prize_adv=2.0,  resource_adv=0.6, info_adv=0.4, risk_reduction_adv=0.7),
    },
    "stall": {
        "early": dict(card_adv=1.0,  board_adv=0.8,  energy_adv=0.5, tempo_adv=0.4,
                      prize_adv=0.5,  resource_adv=2.0, info_adv=0.8, risk_reduction_adv=2.0),
        "mid":   dict(card_adv=1.0,  board_adv=0.8,  energy_adv=0.5, tempo_adv=0.4,
                      prize_adv=0.7,  resource_adv=2.0, info_adv=0.8, risk_reduction_adv=2.0),
        "late":  dict(card_adv=0.9,  board_adv=0.8,  energy_adv=0.6, tempo_adv=0.5,
                      prize_adv=1.0,  resource_adv=2.0, info_adv=0.8, risk_reduction_adv=2.0),
    },
}


def get_weights(archetype: str, phase: str) -> dict[str, float]:
    """Return adv weights for the given archetype and phase (fallback to defaults)."""
    arch  = WEIGHTS.get(archetype, {})
    phase_w = arch.get(phase, arch.get("mid", {}))
    result = dict(_DEFAULT)
    result.update(phase_w)
    return result


def all_archetypes() -> list[str]:
    return list(WEIGHTS.keys())
