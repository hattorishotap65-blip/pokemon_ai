"""
cabt trace evaluation runner.

Orchestrates: cabt self-play with learned advisor env vars ->
trace collection -> trace analysis -> tuning recommendations.

All outputs go to a single run directory.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from typing import Dict, Optional

_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_DIR, "..", ".."))


def build_run_dir(base: str, label: str = "") -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    name = "run_%s_%s" % (ts, label) if label else "run_%s" % ts
    path = os.path.join(base, name)
    os.makedirs(path, exist_ok=True)
    return path


def build_env(
    use_advisor: bool = False,
    trace: bool = False,
    weights_path: str = "",
    fallback_path: str = "",
    trace_path: str = "",
) -> Dict[str, str]:
    """Build env dict for cabt runner subprocess."""
    env = dict(os.environ)
    if use_advisor:
        env["POKEMON_AI_USE_LEARNED_WEIGHTS"] = "1"
    else:
        env.pop("POKEMON_AI_USE_LEARNED_WEIGHTS", None)
    if trace:
        env["POKEMON_AI_TRACE_LEARNED_WEIGHTS"] = "1"
    else:
        env.pop("POKEMON_AI_TRACE_LEARNED_WEIGHTS", None)
    if weights_path:
        env["POKEMON_AI_WEIGHTS_PATH"] = weights_path
    if fallback_path:
        env["POKEMON_AI_WEIGHTS_FALLBACK_PATH"] = fallback_path
    if trace_path:
        env["POKEMON_AI_TRACE_PATH"] = trace_path
    return env


def run_self_play(
    agent: str, deck: str, n: int, output: str,
    env: Optional[Dict[str, str]] = None,
    dry_run: bool = False,
) -> dict:
    """Run cabt self-play via run_external_agent.py."""
    cmd = [
        sys.executable, os.path.join(_REPO, "experiments", "run_external_agent.py"),
        "--agent", agent, "--deck", deck,
        "--n", str(n), "--output", output,
    ]
    if dry_run:
        cmd.append("--dry-run")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
            env=env, cwd=_REPO,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[-500:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else "",
            "output_path": output,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "timeout", "output_path": output}
    except Exception as ex:
        return {"returncode": -1, "stdout": "", "stderr": str(ex)[:200], "output_path": output}


def run_trace_analysis(trace_path: str, run_dir: str) -> dict:
    """Run trace analyzer + recommender on collected trace."""
    results = {}
    try:
        sys.path.insert(0, _REPO)
        from experiments.learning.trace_analyzer import load_traces, analyze_traces
        from experiments.learning.trace_recommender import (
            build_tuning_recommendations, render_recommendation_report,
        )
        from experiments.learning.trace_analyzer import (
            format_report as format_trace_report, find_override_cases,
        )

        entries = load_traces(trace_path)
        results["trace_entries"] = len(entries)

        summary = analyze_traces(entries)
        summary_path = os.path.join(run_dir, "trace_summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        results["trace_summary_path"] = summary_path

        overrides = find_override_cases(entries)
        report = format_trace_report(summary, overrides)
        report_path = os.path.join(run_dir, "trace_report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        results["trace_report_path"] = report_path

        recs = build_tuning_recommendations(entries, summary)
        recs_path = os.path.join(run_dir, "tuning_recommendations.json")
        with open(recs_path, "w", encoding="utf-8") as f:
            json.dump(recs, f, indent=2, ensure_ascii=False)
        results["recommendations_path"] = recs_path

        rec_report = render_recommendation_report(recs)
        rec_report_path = os.path.join(run_dir, "tuning_report.md")
        with open(rec_report_path, "w", encoding="utf-8") as f:
            f.write(rec_report)
        results["tuning_report_path"] = rec_report_path

    except Exception as ex:
        results["error"] = str(ex)[:200]

    return results


def save_run_metadata(run_dir: str, **kwargs) -> str:
    meta = {"run_dir": run_dir, "ts": time.time()}
    meta.update(kwargs)
    path = os.path.join(run_dir, "run_metadata.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return path


def execute_trace_eval(
    agent: str = "main.py",
    deck: str = "deck.csv",
    n: int = 10,
    use_advisor: bool = True,
    weights_path: str = "",
    fallback_path: str = "",
    output_base: str = "experiments/learning/trace_eval_runs",
    label: str = "",
    dry_run: bool = False,
) -> dict:
    """Full trace evaluation pipeline."""
    run_dir = build_run_dir(output_base, label)

    trace_path = os.path.join(run_dir, "advisor_trace.jsonl")
    results_path = os.path.join(run_dir, "self_play_results.jsonl")

    env = build_env(
        use_advisor=use_advisor,
        trace=use_advisor,
        weights_path=weights_path,
        fallback_path=fallback_path,
        trace_path=trace_path,
    )

    sp_result = run_self_play(agent, deck, n, results_path, env=env, dry_run=dry_run)

    analysis = {}
    if not dry_run and os.path.exists(trace_path):
        analysis = run_trace_analysis(trace_path, run_dir)

    meta_path = save_run_metadata(
        run_dir,
        agent=agent, deck=deck, n=n,
        use_advisor=use_advisor, dry_run=dry_run,
        label=label,
        self_play=sp_result,
        analysis=analysis,
    )

    return {
        "run_dir": run_dir,
        "metadata": meta_path,
        "self_play": sp_result,
        "analysis": analysis,
    }
