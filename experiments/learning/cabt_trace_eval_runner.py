"""
cabt trace evaluation runner.

Orchestrates: cabt command with advisor env -> trace collection ->
trace analysis -> tuning recommendations. All outputs in a run directory.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from typing import Dict, List, Optional

_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_DIR, "..", ".."))

_TRACE_FILE = "advisor_trace.jsonl"
_RESULT_FILE = "self_play_results.jsonl"
_TRACE_SUMMARY = "advisor_trace_summary.json"
_TRACE_REPORT = "advisor_trace_report.md"
_TUNING_RECS = "tuning_recommendations.json"
_TUNING_REPORT = "tuning_recommendations.md"
_METADATA = "run_metadata.json"


def build_run_dir(base: str, label: str = "", run_dir: str = "") -> str:
    if run_dir:
        os.makedirs(run_dir, exist_ok=True)
        return run_dir
    ts = time.strftime("%Y%m%d_%H%M%S")
    name = "run_%s_%s" % (ts, label) if label else "run_%s" % ts
    path = os.path.join(base, name)
    os.makedirs(path, exist_ok=True)
    return path


def build_advisor_env(
    base_env: Optional[Dict[str, str]] = None,
    use_advisor: bool = False,
    trace: bool = False,
    weights_path: str = "",
    fallback_path: str = "",
    trace_path: str = "",
) -> Dict[str, str]:
    """Build env dict without mutating base_env."""
    env = dict(base_env) if base_env is not None else dict(os.environ)
    if use_advisor:
        env["POKEMON_AI_USE_LEARNED_WEIGHTS"] = "1"
    if trace:
        env["POKEMON_AI_TRACE_LEARNED_WEIGHTS"] = "1"
    if weights_path:
        env["POKEMON_AI_WEIGHTS_PATH"] = weights_path
    if fallback_path:
        env["POKEMON_AI_WEIGHTS_FALLBACK_PATH"] = fallback_path
    if trace_path:
        env["POKEMON_AI_TRACE_PATH"] = trace_path
    return env


def _safe_env_for_metadata(env: Dict[str, str]) -> Dict[str, str]:
    """Extract only POKEMON_AI_* keys for metadata."""
    return {k: v for k, v in env.items() if k.startswith("POKEMON_AI_")}


def run_command(
    command: List[str],
    env: Optional[Dict[str, str]] = None,
    skip: bool = False,
) -> dict:
    """Run a command, or skip and return a stub result."""
    result = {
        "command": command,
        "returncode": 0,
        "stdout": "",
        "stderr": "",
        "skipped": skip,
    }
    if skip:
        return result
    try:
        r = subprocess.run(
            command, capture_output=True, text=True, timeout=600,
            env=env, cwd=_REPO,
        )
        result["returncode"] = r.returncode
        result["stdout"] = r.stdout[-500:] if r.stdout else ""
        result["stderr"] = r.stderr[-500:] if r.stderr else ""
    except subprocess.TimeoutExpired:
        result["returncode"] = -1
        result["stderr"] = "timeout"
    except Exception as ex:
        result["returncode"] = -1
        result["stderr"] = str(ex)[:200]
    return result


def run_trace_analysis(trace_path: str, run_dir: str) -> dict:
    """Run trace analyzer + recommender. Works on empty/missing trace."""
    results = {}
    try:
        sys.path.insert(0, _REPO)
        from experiments.learning.trace_analyzer import load_traces, analyze_traces
        from experiments.learning.trace_analyzer import (
            format_report as format_trace_report, find_override_cases,
        )
        from experiments.learning.trace_recommender import (
            build_tuning_recommendations, render_recommendation_report,
        )

        entries = load_traces(trace_path)
        results["trace_entries"] = len(entries)

        summary = analyze_traces(entries)
        summary_path = os.path.join(run_dir, _TRACE_SUMMARY)
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        results["trace_summary_path"] = summary_path

        overrides = find_override_cases(entries)
        report = format_trace_report(summary, overrides)
        report_path = os.path.join(run_dir, _TRACE_REPORT)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        results["trace_report_path"] = report_path

        recs = build_tuning_recommendations(entries, summary)
        recs_path = os.path.join(run_dir, _TUNING_RECS)
        with open(recs_path, "w", encoding="utf-8") as f:
            json.dump(recs, f, indent=2, ensure_ascii=False)
        results["recommendations_path"] = recs_path

        rec_report = render_recommendation_report(recs)
        rec_report_path = os.path.join(run_dir, _TUNING_REPORT)
        with open(rec_report_path, "w", encoding="utf-8") as f:
            f.write(rec_report)
        results["tuning_report_path"] = rec_report_path

    except Exception as ex:
        results["error"] = str(ex)[:200]
    return results


def save_run_metadata(run_dir: str, **kwargs) -> str:
    meta = {"run_dir": run_dir, "ts": time.time()}
    meta.update(kwargs)
    path = os.path.join(run_dir, _METADATA)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return path


def execute_trace_eval(
    command: Optional[List[str]] = None,
    agent: str = "main.py",
    deck: str = "deck.csv",
    n: int = 10,
    use_advisor: bool = True,
    weights_path: str = "",
    fallback_path: str = "",
    output_base: str = "experiments/learning/trace_eval_runs",
    run_dir: str = "",
    label: str = "",
    skip_command: bool = False,
) -> dict:
    """Full trace evaluation pipeline."""
    rd = build_run_dir(output_base, label, run_dir)

    trace_path = os.path.join(rd, _TRACE_FILE)
    results_path = os.path.join(rd, _RESULT_FILE)

    base_env = dict(os.environ)
    env = build_advisor_env(
        base_env=base_env,
        use_advisor=use_advisor,
        trace=use_advisor,
        weights_path=weights_path,
        fallback_path=fallback_path,
        trace_path=trace_path,
    )

    if command is None:
        command = [
            sys.executable,
            os.path.join(_REPO, "experiments", "run_external_agent.py"),
            "--agent", agent, "--deck", deck,
            "--n", str(n), "--output", results_path,
        ]
        if skip_command:
            command.append("--dry-run")

    cmd_result = run_command(command, env=env, skip=skip_command and "--dry-run" not in command)

    # Always run analysis (produces empty-trace reports if no trace)
    analysis = run_trace_analysis(trace_path, rd)

    meta_path = save_run_metadata(
        rd,
        agent=agent, deck=deck, n=n,
        use_advisor=use_advisor, skip_command=skip_command,
        label=label,
        command=command,
        trace_path=trace_path,
        result_path=results_path,
        weights_path=weights_path,
        advisor_env=_safe_env_for_metadata(env),
        command_result={
            "returncode": cmd_result["returncode"],
            "skipped": cmd_result["skipped"],
        },
        analysis_summary={"trace_entries": analysis.get("trace_entries", 0)},
    )

    return {
        "run_dir": rd,
        "metadata": meta_path,
        "command_result": cmd_result,
        "analysis": analysis,
    }
