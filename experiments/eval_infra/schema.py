"""Data contracts for eval-infra: per-game record validation, metric/segment
ID vocabulary, and stats-cell construction.

Metric/segment IDs are DELIBERATELY aligned (identical literal strings,
where a Profile-equivalent exists) with profiles/outcome/pokemon-ai.example.json
-- this is fixture-only forward compatibility, NOT App Profile activation.
This package never reads, loads, or activates any file under profiles/.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from experiments.eval_infra.stats import IntervalStats

SCHEMA_VERSION = "1"

# Aligned 1:1 with profiles/outcome/pokemon-ai.example.json's metric IDs where
# an equivalent exists there; harness-native IDs otherwise (no Profile
# equivalent for per-decision observation_count or the p50 companion to the
# Profile's p95_decision_time).
METRIC_WIN_RATE = "external_league_win_rate"
METRIC_ERROR_RATE = "error_rate"
METRIC_TIMEOUT_RATE = "timeout_rate"
METRIC_ILLEGAL_ACTION_RATE = "illegal_action_rate"
METRIC_DECISION_TIME_P50_MS = "decision_time_p50_ms"
METRIC_DECISION_TIME_P95_MS = "p95_decision_time"
METRIC_OBSERVATION_COUNT = "observation_count"

METRIC_IDS = (
    METRIC_WIN_RATE, METRIC_ERROR_RATE, METRIC_TIMEOUT_RATE,
    METRIC_ILLEGAL_ACTION_RATE, METRIC_DECISION_TIME_P50_MS,
    METRIC_DECISION_TIME_P95_MS, METRIC_OBSERVATION_COUNT,
)

# Aligned 1:1 with profiles/outcome/pokemon-ai.example.json's segment IDs,
# plus "mirror" which is harness-native and NEVER appears in a league cell
# (mirror is smoke/auxiliary only, per the task's explicit instruction).
SEGMENT_OVERALL = "overall"
SEGMENT_OPPONENT_LUCARIO = "opponent-lucario"
SEGMENT_OPPONENT_DRAGAPULT = "opponent-dragapult"
SEGMENT_OPPONENT_MEGASTARMIE = "opponent-megastarmie"
SEGMENT_FIRST_PLAYER = "first-player"
SEGMENT_SECOND_PLAYER = "second-player"
SEGMENT_MIRROR = "mirror"

LEAGUE_SEGMENT_IDS = (
    SEGMENT_OVERALL, SEGMENT_OPPONENT_LUCARIO, SEGMENT_OPPONENT_DRAGAPULT,
    SEGMENT_OPPONENT_MEGASTARMIE, SEGMENT_FIRST_PLAYER, SEGMENT_SECOND_PLAYER,
)
AUXILIARY_SEGMENT_IDS = (SEGMENT_MIRROR,)

REQUIRED_LEAGUE_OPPONENTS = ("lucario", "dragapult", "megastarmie")

# Matches head_to_head.py's --jsonl-out per-game record shape exactly.
GAME_RECORD_REQUIRED_FIELDS = frozenset({
    "schema_version", "game_index", "first_seat_agent", "label_a", "label_b",
    "termination", "result", "error_actor", "legality", "decisions",
})
GAME_RECORD_TERMINATION_CATEGORIES = frozenset({"result", "error", "timeout"})
GAME_RECORD_LEGALITY_VALUES = frozenset({"legal", "illegal", "unknown"})

# Exact 6-key cell shape required by tools/outcome_gatekeeper.py's
# EVIDENCE_CELL validator -- this package never imports that validator (test-
# only import lives in experiments/test_eval_infra.py), but matches its
# shape so output is a plausible future Evidence cell without activating one.
CELL_REQUIRED_KEYS = frozenset({
    "metric_id", "segment_id", "observations", "baseline_stats",
    "candidate_stats", "delta_stats",
})
STATS_TRIPLE_KEYS = frozenset({"estimate", "lower", "upper"})


class SchemaError(ValueError):
    pass


def validate_game_record(record: dict) -> dict:
    """Structural validation of one head_to_head.py --jsonl-out record.
    Raises SchemaError on any violation. Returns the record unchanged."""
    if not isinstance(record, dict):
        raise SchemaError("GAME_RECORD_NOT_OBJECT")
    missing = GAME_RECORD_REQUIRED_FIELDS - set(record)
    if missing:
        raise SchemaError(f"GAME_RECORD_MISSING_FIELDS:{sorted(missing)}")
    if record["schema_version"] != SCHEMA_VERSION:
        raise SchemaError("GAME_RECORD_SCHEMA_VERSION_UNSUPPORTED")
    if not isinstance(record["game_index"], int) or record["game_index"] < 0:
        raise SchemaError("GAME_RECORD_GAME_INDEX_INVALID")
    if record["first_seat_agent"] not in ("a", "b"):
        raise SchemaError("GAME_RECORD_FIRST_SEAT_AGENT_INVALID")
    termination = record["termination"]
    if not isinstance(termination, dict) or "category" not in termination or "kind" not in termination:
        raise SchemaError("GAME_RECORD_TERMINATION_INVALID")
    if termination["category"] not in GAME_RECORD_TERMINATION_CATEGORIES:
        raise SchemaError("GAME_RECORD_TERMINATION_CATEGORY_INVALID")
    if record["legality"] not in GAME_RECORD_LEGALITY_VALUES:
        raise SchemaError("GAME_RECORD_LEGALITY_INVALID")
    if record["error_actor"] not in ("a", "b", "engine", None):
        raise SchemaError("GAME_RECORD_ERROR_ACTOR_INVALID")
    decisions = record["decisions"]
    if decisions is not None:
        if not isinstance(decisions, list):
            raise SchemaError("GAME_RECORD_DECISIONS_INVALID")
        for d in decisions:
            if not isinstance(d, dict) or "ply" not in d or "duration_ms" not in d or "actor" not in d:
                raise SchemaError("GAME_RECORD_DECISION_ENTRY_INVALID")
            if d["actor"] not in ("a", "b"):
                raise SchemaError("GAME_RECORD_DECISION_ACTOR_INVALID")
    return record


def validate_stats_triple(value: dict, path: str = "STATS") -> dict:
    if not isinstance(value, dict) or set(value) != STATS_TRIPLE_KEYS:
        raise SchemaError(f"{path}_KEYS_INVALID")
    try:
        estimate, lower, upper = Decimal(value["estimate"]), Decimal(value["lower"]), Decimal(value["upper"])
    except Exception as exc:  # noqa: BLE001 - re-raised as a schema error deliberately
        raise SchemaError(f"{path}_DECIMAL_INVALID") from exc
    if not (lower <= estimate <= upper):
        raise SchemaError(f"{path}_INTERVAL_INVALID")
    return value


def build_cell(
    metric_id: str,
    segment_id: str,
    observations: int,
    baseline_stats: IntervalStats | dict,
    candidate_stats: IntervalStats | dict,
    delta_stats: IntervalStats | dict,
) -> dict[str, Any]:
    """Build one Gatekeeper-cell-shaped dict (exact 6 keys). Every metric,
    INCLUDING guardrails (illegal_action_rate, p95_decision_time), always
    gets baseline_stats/candidate_stats/delta_stats -- no metric is exempt.
    A cell with observations <= 0 must never be constructed; the caller
    (raging_bolt_eval.py's summarize) must OMIT the cell entirely instead
    (Gatekeeper's _positive_int requires observations >= 1; a 0-observation
    cell would be rejected as BLOCKED rather than treated as insufficient).
    """
    if observations < 1:
        raise SchemaError("CELL_OBSERVATIONS_MUST_BE_POSITIVE_OR_OMITTED")

    def _as_dict(v):
        return v.as_dict() if isinstance(v, IntervalStats) else v

    baseline_d = validate_stats_triple(_as_dict(baseline_stats), "BASELINE_STATS")
    candidate_d = validate_stats_triple(_as_dict(candidate_stats), "CANDIDATE_STATS")
    delta_d = validate_stats_triple(_as_dict(delta_stats), "DELTA_STATS")

    cell = {
        "metric_id": metric_id,
        "segment_id": segment_id,
        "observations": observations,
        "baseline_stats": baseline_d,
        "candidate_stats": candidate_d,
        "delta_stats": delta_d,
    }
    if set(cell) != CELL_REQUIRED_KEYS:  # defensive; cannot actually happen given the literal above
        raise SchemaError("CELL_KEYS_INVALID")
    return cell
