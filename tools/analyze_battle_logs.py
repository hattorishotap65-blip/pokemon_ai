"""
Battle Log Diagnostic Pipeline — CLI entry point.

Usage:
  python tools/analyze_battle_logs.py --input battle_logs/inbox --output reports
  python tools/analyze_battle_logs.py --input battle_logs/inbox --output reports --move-processed
  python tools/analyze_battle_logs.py --input battle_logs/inbox --output reports --deck-profile data/deck_profile.json --top 20
  python tools/analyze_battle_logs.py --input logs --output reports --top 20

Reads .json / .jsonl / .log files from the input directory, detects anomalies,
and writes reports to the output directory.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from tools.detect_anomalies import (
    normalize_event, detect_all_anomalies, build_summary, DeckProfile,
)
from tools.generate_anomaly_report import (
    generate_json_report, generate_markdown_report, generate_llm_summary,
)


def _read_log_file(path: str) -> list[dict]:
    """Read a single log file and return raw record dicts."""
    records = []
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return []
        if content.startswith("["):
            records = json.loads(content)
        elif content.startswith("{"):
            try:
                records = [json.loads(content)]
            except json.JSONDecodeError:
                for line in content.splitlines():
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        else:
            for line in content.splitlines():
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception:
        pass
    return records


def _scan_input_dir(input_dir: str) -> tuple[list[str], list[str]]:
    """Scan input dir for log files. Returns (valid_paths, ignored_paths)."""
    valid = []
    ignored = []
    if not os.path.isdir(input_dir):
        return valid, ignored
    for fname in sorted(os.listdir(input_dir)):
        if fname.startswith("."):
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext in (".json", ".jsonl", ".log"):
            valid.append(os.path.join(input_dir, fname))
        else:
            ignored.append(os.path.join(input_dir, fname))
    return valid, ignored


def main():
    parser = argparse.ArgumentParser(description="Battle Log Diagnostic Pipeline")
    parser.add_argument("--input", default="battle_logs/inbox", help="Input directory")
    parser.add_argument("--output", default="reports", help="Output directory")
    parser.add_argument("--deck-profile", default=None, help="Path to deck_profile.json")
    parser.add_argument("--top", type=int, default=20, help="Top N anomalies in report")
    parser.add_argument("--move-processed", action="store_true", help="Move processed files to battle_logs/processed/")
    args = parser.parse_args()

    # Load deck profile
    profile_data = None
    if args.deck_profile and os.path.exists(args.deck_profile):
        try:
            with open(args.deck_profile, encoding="utf-8") as f:
                profile_data = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load deck profile: {e}")
    profile = DeckProfile(profile_data)

    # Scan input
    valid_files, ignored_files = _scan_input_dir(args.input)
    print(f"Input: {args.input}")
    print(f"  Files found: {len(valid_files)}")
    if ignored_files:
        print(f"  Ignored:     {len(ignored_files)}")

    # Read and normalize
    all_events: list[dict] = []
    processed_files: list[str] = []
    bad_files: list[str] = []

    for path in valid_files:
        fname = os.path.basename(path)
        raw_records = _read_log_file(path)
        if not raw_records:
            bad_files.append(path)
            continue
        events_from_file = []
        for rec in raw_records:
            ev = normalize_event(rec, fname)
            if ev is not None:
                events_from_file.append(ev)
        if events_from_file:
            all_events.extend(events_from_file)
            processed_files.append(path)
        else:
            bad_files.append(path)

    print(f"  Normalized events: {len(all_events)}")

    # Detect anomalies
    anomalies = detect_all_anomalies(all_events, profile)
    summary = build_summary(anomalies, len(processed_files), all_events)

    print(f"\nAnomalies detected: {len(anomalies)}")
    for sev in ["critical", "high", "medium", "low", "info"]:
        cnt = summary.get(sev, 0)
        if cnt > 0:
            print(f"  {sev}: {cnt}")

    # Generate reports
    os.makedirs(args.output, exist_ok=True)
    os.makedirs(os.path.join(args.output, "anomaly_reports"), exist_ok=True)

    json_report = generate_json_report(
        anomalies, summary,
        deck_profile_id=profile.deck_id,
        source_dir=args.input,
        ignored_files=[os.path.basename(p) for p in bad_files],
    )
    md_report   = generate_markdown_report(anomalies, summary, top_n=args.top)
    llm_summary = generate_llm_summary(anomalies, summary, top_n=min(args.top, 10))

    # Write latest reports
    json_path = os.path.join(args.output, "latest_anomaly_report.json")
    md_path   = os.path.join(args.output, "latest_anomaly_report.md")
    sum_path  = os.path.join(args.output, "latest_anomaly_summary.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_report)
    with open(sum_path, "w", encoding="utf-8") as f:
        f.write(llm_summary)

    # Write dated report
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dated_path = os.path.join(args.output, "anomaly_reports", f"anomaly_report_{ts}.json")
    with open(dated_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)

    print(f"\nReports written:")
    print(f"  {json_path}")
    print(f"  {md_path}")
    print(f"  {sum_path}")
    print(f"  {dated_path}")

    # Move processed files
    if args.move_processed:
        proc_dir = os.path.join(os.path.dirname(args.input), "processed")
        os.makedirs(proc_dir, exist_ok=True)
        for path in processed_files:
            dst = os.path.join(proc_dir, os.path.basename(path))
            shutil.move(path, dst)
        print(f"\nMoved {len(processed_files)} processed files to {proc_dir}")

    # Move bad files to ignored
    if bad_files:
        ign_dir = os.path.join(os.path.dirname(args.input), "ignored")
        os.makedirs(ign_dir, exist_ok=True)
        for path in bad_files:
            dst = os.path.join(ign_dir, os.path.basename(path))
            try:
                shutil.move(path, dst)
            except Exception:
                pass
        print(f"Moved {len(bad_files)} unreadable files to {ign_dir}")


if __name__ == "__main__":
    main()
