"""
Analyze game logs from logs/*.jsonl and print improvement insights.

Usage:
    python experiments/analyze_logs.py
    python experiments/analyze_logs.py --log-dir path/to/logs
    python experiments/analyze_logs.py --results path/to/results.csv
"""
import argparse
import csv
import glob
import json
import os
import sys
from collections import Counter, defaultdict

# Force UTF-8 output on Windows to handle box-drawing characters
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
_LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")


# ══════════════════════════════════════════════════════════════
# Loader
# ══════════════════════════════════════════════════════════════

def load_jsonl_logs(log_dir: str) -> tuple[list, list]:
    """Returns (turn_entries, game_end_entries)."""
    turns, ends = [], []
    for path in glob.glob(os.path.join(log_dir, "*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                    if entry.get("event") == "game_end":
                        ends.append(entry)
                    else:
                        turns.append(entry)
                except json.JSONDecodeError:
                    pass
    return turns, ends


def load_results_csv(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ══════════════════════════════════════════════════════════════
# Analysis helpers
# ══════════════════════════════════════════════════════════════

def _pct(n: int, total: int) -> str:
    if total == 0:
        return "  0.0%"
    return f"{n/total*100:5.1f}%"


def _bar(n: int, total: int, width: int = 20) -> str:
    if total == 0:
        return " " * width
    filled = round(n / total * width)
    return "█" * filled + "░" * (width - filled)


def _section(title: str):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


# ══════════════════════════════════════════════════════════════
# Main report
# ══════════════════════════════════════════════════════════════

def analyze(log_dir: str = None, results_csv: str = None):
    log_dir = log_dir or _LOG_DIR
    turns, ends = load_jsonl_logs(log_dir)

    unique_games = len(set(e.get("game_id", "") for e in ends))
    total_turns = len(turns)

    print(f"\n{'═'*50}")
    print(f"  PTCG AI Log Analysis")
    print(f"  Games: {unique_games}   Turns logged: {total_turns}")
    print(f"  Log dir: {log_dir}")
    print(f"{'═'*50}")

    if not ends and not turns:
        print("\n  No log data found. Run experiments/run_matches.py first.")
        return

    # ── Results from results CSV (if provided) ──────────────────
    if results_csv:
        rows = load_results_csv(results_csv)
        if rows:
            _section("Match Results (from results CSV)")
            total = len(rows)
            win_counts = Counter(r["winner"] for r in rows)
            for winner, count in win_counts.most_common():
                bar = _bar(count, total)
                print(f"  {winner:<12} {count:>5}  {_pct(count, total)}  {bar}")
            avg_turns = sum(int(r.get("turns", 0)) for r in rows) / total if total else 0
            errors = sum(1 for r in rows if r.get("winner") == "error")
            print(f"\n  Avg turns : {avg_turns:.1f}")
            print(f"  Errors    : {errors} ({_pct(errors, total)})")

    # ── Win/Loss from JSONL ─────────────────────────────────────
    if ends:
        _section("Win/Loss from game logs")
        result_counts = Counter(e.get("result") for e in ends)
        total_g = len(ends)
        for result, count in result_counts.most_common():
            bar = _bar(count, total_g)
            print(f"  {result:<12} {count:>5}  {_pct(count, total_g)}  {bar}")

        turn_by_result = defaultdict(list)
        for e in ends:
            turn_by_result[e.get("result")].append(e.get("total_turns", 0))
        print()
        for result, ts in turn_by_result.items():
            print(f"  Avg turns ({result}): {sum(ts)/len(ts):.1f}")

    # ── Error rate ───────────────────────────────────────────────
    _section("Error & Fallback Rate")
    error_turns = [t for t in turns if t.get("error")]
    fallback_turns = [t for t in turns if t.get("reason") == "fallback"]
    n = total_turns or 1
    print(f"  Turns with errors   : {len(error_turns):>5}  ({_pct(len(error_turns), n)})")
    print(f"  Fallback used       : {len(fallback_turns):>5}  ({_pct(len(fallback_turns), n)})")
    if error_turns:
        err_counts = Counter(t.get("error", "")[:60] for t in error_turns)
        print("\n  Top errors:")
        for msg, cnt in err_counts.most_common(5):
            print(f"    [{cnt:>4}] {msg}")

    # ── Timeout risk ─────────────────────────────────────────────
    _section("Timeout Risk")
    slow = [t for t in turns if (t.get("time_ms") or 0) > 1000]
    very_slow = [t for t in turns if (t.get("time_ms") or 0) > 5000]
    all_ms = [t.get("time_ms", 0) for t in turns if t.get("time_ms") is not None]
    avg_ms = sum(all_ms) / len(all_ms) if all_ms else 0
    print(f"  Avg decision time   : {avg_ms:.1f} ms")
    print(f"  >1 000 ms           : {len(slow):>5}  ({_pct(len(slow), n)})")
    print(f"  >5 000 ms           : {len(very_slow):>5}  ({_pct(len(very_slow), n)})")

    # ── Action distribution ──────────────────────────────────────
    _section("Action Distribution (by reason)")
    reason_counts = Counter(t.get("reason") for t in turns if t.get("reason"))
    for reason, count in reason_counts.most_common(15):
        bar = _bar(count, total_turns, 15)
        print(f"  {reason:<30} {count:>5}  {_pct(count, n)}  {bar}")

    # ── Attack vs pass rate ──────────────────────────────────────
    _section("Aggression Metrics")
    attack_turns = [t for t in turns if (t.get("reason") or "").startswith("attack")
                    or t.get("reason") in ("ko_opponent", "almost_ko", "winning_ko")]
    end_turns = [t for t in turns if t.get("reason") == "end_turn"]
    energy_turns = [t for t in turns if (t.get("reason") or "").startswith("energy")]
    print(f"  Attack turns        : {len(attack_turns):>5}  ({_pct(len(attack_turns), n)})")
    print(f"  End-turn (pass)     : {len(end_turns):>5}  ({_pct(len(end_turns), n)})")
    print(f"  Energy attach       : {len(energy_turns):>5}  ({_pct(len(energy_turns), n)})")

    energy_reasons = Counter(t.get("reason") for t in energy_turns)
    for reason, count in energy_reasons.most_common():
        print(f"    └─ {reason:<28} {count:>5}")

    # ── Losing game analysis ────────────────────────────────────
    losing_ids = {e.get("game_id") for e in ends if e.get("result") == "loss"}
    losing_turns = [t for t in turns if t.get("game_id") in losing_ids]
    if losing_turns:
        _section(f"Actions in Losing Games ({len(losing_ids)} games)")
        losing_reasons = Counter(t.get("reason") for t in losing_turns if t.get("reason"))
        for reason, count in losing_reasons.most_common(10):
            print(f"  {reason:<30} {count:>5}  {_pct(count, len(losing_turns))}")

    # ── Deck-health signals ──────────────────────────────────────
    _section("Deck Health Signals (from state summaries)")
    low_deck = [t for t in turns
                if (t.get("state_summary") or {}).get("deck_count", 99) <= 5]
    zero_hand = [t for t in turns
                 if (t.get("state_summary") or {}).get("hand_count", 1) == 0]
    no_energy_active = [t for t in turns
                        if (t.get("state_summary") or {}).get("active_energy", 99) == 0]
    print(f"  Turns with deck ≤ 5     : {len(low_deck):>5}  ({_pct(len(low_deck), n)})  ← deck-out risk")
    print(f"  Turns with empty hand   : {len(zero_hand):>5}  ({_pct(len(zero_hand), n)})  ← topdeck mode")
    print(f"  Turns: active 0 energy  : {len(no_energy_active):>5}  ({_pct(len(no_energy_active), n)})  ← energy starve?")

    # ── Prize milestones ────────────────────────────────────────
    _section("Prize Progress")
    prize_snapshots = Counter(
        (t.get("state_summary") or {}).get("prizes_remaining")
        for t in turns
    )
    for prizes in sorted(p for p in prize_snapshots if p is not None):
        count = prize_snapshots[prizes]
        print(f"  Prizes remaining = {prizes}  : {count:>5} turns")

    # ── Advantage score analysis ─────────────────────────────────
    adv_keys = [
        "card_adv_score", "board_adv_score", "energy_adv_score", "tempo_adv_score",
        "prize_adv_score", "resource_adv_score", "risk_reduction_adv_score",
        "concept_weighted_adv_score", "plan_progress_score",
    ]
    adv_turns = [t for t in turns if "concept_weighted_adv_score" in t]
    if adv_turns:
        _section("Advantage Score Breakdown")
        winning_ids = {e.get("game_id") for e in ends if e.get("result") == "win"}
        losing_ids2 = {e.get("game_id") for e in ends if e.get("result") == "loss"}
        win_turns  = [t for t in adv_turns if t.get("game_id") in winning_ids]
        lose_turns = [t for t in adv_turns if t.get("game_id") in losing_ids2]

        print(f"  Turns with adv data: {len(adv_turns)}  (win: {len(win_turns)}  loss: {len(lose_turns)})")

        def _avg(lst, key):
            vals = [t.get(key) for t in lst if t.get(key) is not None]
            return sum(vals) / len(vals) if vals else 0.0

        header = f"  {'metric':<32} {'all':>7} {'win':>7} {'loss':>7}"
        print(f"\n{header}")
        print(f"  {'-'*53}")
        for k in adv_keys:
            a_all  = _avg(adv_turns, k)
            a_win  = _avg(win_turns, k)
            a_loss = _avg(lose_turns, k)
            flag   = "  <-- overweight?" if a_loss > a_win + 0.3 else ""
            print(f"  {k:<32} {a_all:>7.3f} {a_win:>7.3f} {a_loss:>7.3f}{flag}")

        # Phase distribution
        _section("Game Phase Distribution")
        phase_counts = Counter(t.get("current_phase") for t in adv_turns if t.get("current_phase"))
        total_adv = len(adv_turns) or 1
        for phase, cnt in phase_counts.most_common():
            print(f"  {phase:<10} {cnt:>6}  {_pct(cnt, total_adv)}")

        # Missing plan pieces
        _section("Most Common Missing Plan Pieces")
        piece_counts: Counter = Counter()
        for t in adv_turns:
            for piece in (t.get("missing_plan_pieces") or []):
                piece_counts[piece] += 1
        for piece, cnt in piece_counts.most_common(10):
            print(f"  {piece:<35} {cnt:>5}  {_pct(cnt, total_adv)}")

        # plan_progress in losing games
        if lose_turns:
            _section("Plan Progress in Losing Games (by turn)")
            low_prog = [t for t in lose_turns
                        if (t.get("plan_progress_score") or 0) < 3.0]
            print(f"  Turns with plan_progress < 3.0 in losses: {len(low_prog)} / {len(lose_turns)}")
            if low_prog:
                game_turns_low = Counter(t.get("game_turn") for t in low_prog)
                print("  Turns (game_turn) where progress was low:")
                for gt, cnt in sorted(game_turns_low.items()):
                    print(f"    turn {gt}: {cnt} times")

    print(f"\n{'='*50}\n")


# ══════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze PTCG AI game logs")
    parser.add_argument("--log-dir", type=str, default=None, help="Directory containing .jsonl logs")
    parser.add_argument("--results", type=str, default=None, help="Path to results CSV from run_matches.py")
    args = parser.parse_args()

    latest_results = None
    if args.results:
        latest_results = args.results
    else:
        # Auto-detect latest results file
        candidates = glob.glob(os.path.join(_LOG_DIR, "results_*.csv"))
        if candidates:
            latest_results = max(candidates, key=os.path.getmtime)

    analyze(log_dir=args.log_dir, results_csv=latest_results)
