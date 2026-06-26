"""
Trace logging for learned weight advisor decisions.

Default off. Enable with POKEMON_AI_TRACE_LEARNED_WEIGHTS=1.
Never crashes runtime — all errors are silently ignored.
"""
from __future__ import annotations
import json
import os
import time
from typing import Dict, List, Optional

_TRACE_VAR = "POKEMON_AI_TRACE_LEARNED_WEIGHTS"
_TRACE_PATH_VAR = "POKEMON_AI_TRACE_PATH"
_DEFAULT_TRACE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "runtime_traces", "advisor_trace.jsonl",
)


def trace_enabled() -> bool:
    return os.environ.get(_TRACE_VAR) == "1"


def _trace_path() -> str:
    return os.environ.get(_TRACE_PATH_VAR) or _DEFAULT_TRACE_PATH


def build_trace_entry(
    state: dict,
    candidates: list,
    ranked: Optional[list],
    existing_scores: List[float],
    existing_ranked_indices: List[int],
    selected_indices: List[int],
    fallback_reason: Optional[str],
) -> dict:
    """Build a trace entry dict for one decision point."""
    advisor_top = None
    advisor_top_idx = -1
    advisor_scores = []
    if ranked:
        advisor_top = ranked[0].get("action_id", "") if ranked else None
        advisor_top_idx = ranked[0].get("original_index", -1) if ranked else -1
        advisor_scores = [
            {"action_id": r.get("action_id", ""), "score": r.get("score", 0.0),
             "original_index": r.get("original_index", -1)}
            for r in ranked[:5]
        ]

    existing_top_idx = existing_ranked_indices[0] if existing_ranked_indices else -1
    advisor_overrode = (
        fallback_reason is None and ranked is not None
        and advisor_top_idx >= 0 and advisor_top_idx != existing_top_idx
    )

    cand_summary = []
    for c in (candidates or [])[:8]:
        cand_summary.append({
            "id": c.get("id", ""),
            "label": c.get("label", ""),
            "type": c.get("type", ""),
        })

    used_advisor = fallback_reason is None and ranked is not None

    return {
        "ts": time.time(),
        "used_advisor": used_advisor,
        "fallback_reason": fallback_reason,
        "advisor_top": advisor_top,
        "advisor_top_index": advisor_top_idx,
        "existing_top_index": existing_top_idx,
        "advisor_overrode_existing": advisor_overrode,
        "selected_indices": selected_indices[:3],
        "advisor_scores": advisor_scores,
        "existing_scores_top3": [
            {"index": existing_ranked_indices[i], "score": existing_scores[existing_ranked_indices[i]]}
            for i in range(min(3, len(existing_ranked_indices)))
            if existing_ranked_indices[i] < len(existing_scores)
        ] if existing_scores and existing_ranked_indices else [],
        "candidates": cand_summary,
        "n_candidates": len(candidates) if candidates else 0,
        "state_summary": {
            "active": (state or {}).get("active", ""),
            "prizes": (state or {}).get("prizes_remaining", "?"),
            "opp_active": (state or {}).get("opponent_active", ""),
            "opp_prizes": (state or {}).get("opponent_prizes", "?"),
        },
    }


def write_advisor_trace(entry: dict) -> None:
    """Append a trace entry to the trace file. Never raises."""
    if not trace_enabled():
        return
    try:
        path = _trace_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
