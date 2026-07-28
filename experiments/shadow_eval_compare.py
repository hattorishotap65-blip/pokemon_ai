"""
PR0-C: Shadow evaluator comparison (no unification, no policy change).

Loads a Replay Bundle JSONL (produced by experiments/agents/raging_bolt/
main.py's PR0-B capture -- see experiments/replay_decision.py for how to
generate one) and, for each MAIN-context / maxCount==1 decision, evaluates
the SAME top-K candidates through multiple independent evaluation paths
(see experiments/agents/raging_bolt/audit/evaluator_path_matrix.json for
what each one is and why evaluate_state() / counterfactual_analyzer.py are
excluded):

  - _score_option        (the reference ranking; already in the bundle)
  - _estimate_action_impact  (cheap, no engine call, hidden-sample-independent)
  - _eval_search_state   (one engine rollout per (candidate, hidden sample)
                           pair -- see the paired-sample design and CRN
                           caveat below)
  - value_model.predict_action_value (if the model files are present,
    hidden-sample-independent)

This NEVER calls choose() / choose_with_search() and NEVER changes which
action the agent would pick -- it only calls individual evaluator methods
directly on a reconstructed (replayed) policy, purely to log where the
evaluators agree/disagree on ranking and where their value scales differ.

Paired-sample design (fixed from an earlier version of this script): the
SAME materialized hidden-state sample is applied to every candidate before
moving on to the next sample -- i.e. the outer loop is over samples, the
inner loop is over candidates, each iteration using a fresh
RagingBoltPolicy replaying exactly that one sample. This makes the
comparison paired/apples-to-apples (candidate A and candidate B are always
compared under the same hidden-state guess). The earlier version looped
candidates in the outer position and let each candidate consume the next
tape entry in sequence, so candidate A and candidate B were silently
scored under DIFFERENT hidden samples -- not a valid comparison. Each
candidate's _eval_search_state result is recorded as a list of per-sample
values plus their mean and variance, not a single point value.

CRN caveat (see audit/crn_capability_matrix.json): _eval_search_state's
value depends on an engine rollforward, which is NOT fully deterministic
even under identical materialized hidden samples (manual_coin=False lets
the engine resolve coin-flip effects with its own uncontrollable RNG). The
mean/variance across samples characterizes this noise; still treat any
single sample as a noisy point estimate, not a stable ground truth.

Usage (inside WSL):
  python experiments/shadow_eval_compare.py /tmp/bundles.jsonl \
      --output /tmp/shadow_compare.jsonl --top-k 5 --samples 4
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
import statistics
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_AGENT_DIR = os.path.join(_REPO_ROOT, "experiments", "agents", "raging_bolt")
_AGENT_PATH = os.path.join(_AGENT_DIR, "main.py")
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "reference", "extracted"))
sys.path.insert(0, _AGENT_DIR)  # value_model.py / feature_extractor.py live here


def _load_agent_module(path=_AGENT_PATH):
    spec = importlib.util.spec_from_file_location("raging_bolt_main_shadow", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rank_of(candidate_ids, scored_ids_desc):
    """1-based rank of each candidate id within a list already sorted
    descending by some evaluator's value; ties keep first-seen order."""
    order = {cid: pos + 1 for pos, cid in enumerate(scored_ids_desc)}
    return {cid: order.get(cid) for cid in candidate_ids}


def evaluate_record(mod, record, top_k, n_samples=4, engine_horizon_cap=None):
    from cg.api import to_observation_class, SelectContext, search_begin, search_end, search_step

    if record.get("select_context") != int(SelectContext.MAIN):
        return None
    legal_actions = record.get("legal_actions") or []
    if not legal_actions:
        return None

    obs = to_observation_class(record["obs_dict"])
    select = obs.select
    if not select or not select.option or select.maxCount != 1:
        return None  # _eval_search_state's rollforward path only applies to single-pick decisions

    hidden_samples = record.get("captured_hidden_samples") or []
    samples_to_use = hidden_samples[:n_samples]

    # A throwaway policy instance purely to read state (prizes, self.p(),
    # etc.) that doesn't depend on which hidden sample is active --
    # _estimate_action_impact/value_model/the endgame-horizon check all
    # only need the live obs, never a replayed hidden sample, so this one
    # is never given a replay tape and never calls _predict_hidden().
    ref_policy = mod.RagingBoltPolicy(obs)

    ranked_by_heuristic = sorted(legal_actions, key=lambda a: -(a["heuristic_score"] or 0))
    top = ranked_by_heuristic[:top_k]
    candidate_indices = [a["index"] for a in top]

    heuristic_values = {a["index"]: a["heuristic_score"] for a in top}
    impact_values = {}
    value_model_values = {}
    eval_search_samples = {i: [] for i in candidate_indices}  # per-candidate list, one value per hidden sample
    errors = []

    try:
        from value_model import predict_action_value
        vm_available = True
    except Exception:
        vm_available = False

    endgame = (len(ref_policy.me.prize) <= ref_policy.p("endgame_prize_threshold", 2)
               or len(ref_policy.opponent.prize) <= ref_policy.p("endgame_prize_threshold", 2))
    horizon = 4 if (endgame and ref_policy.p("rule_endgame_deepen", 1)) else 2
    if engine_horizon_cap:
        horizon = min(horizon, engine_horizon_cap)
    sim_opp = True if horizon > 2 else None

    # Hidden-sample-independent evaluators: computed once per candidate,
    # outside the sample loop below.
    for i in candidate_indices:
        opt = select.option[i]
        try:
            impact_values[i] = ref_policy._estimate_action_impact(opt)
        except Exception as e:
            errors.append({"evaluator": "_estimate_action_impact", "index": i, "error": str(e)})

        if vm_available:
            try:
                v = predict_action_value(obs, ref_policy.my_index, opt)
                value_model_values[i] = v
            except Exception as e:
                errors.append({"evaluator": "value_model", "index": i, "error": str(e)})

    # _eval_search_state: outer loop over hidden samples, inner loop over
    # candidates -- the SAME sample is applied to every candidate before
    # moving to the next sample (paired comparison), each via a fresh
    # single-sample replay policy so results are directly comparable.
    for sample in samples_to_use:
        for i in candidate_indices:
            opt_policy = mod.RagingBoltPolicy(obs, replay_hidden_samples=[sample])
            try:
                preds = opt_policy._predict_hidden()  # pops the one sample we just gave it
                root = search_begin(obs, *preds)
                try:
                    ss = search_step(root.searchId, [i])
                    final_state = opt_policy._rollforward(ss, sim_opp=sim_opp, horizon=horizon)
                    value = opt_policy._eval_search_state(final_state, opt_policy.my_index)
                    eval_search_samples[i].append(value)
                finally:
                    search_end()
            except Exception as e:
                errors.append({"evaluator": "_eval_search_state", "index": i, "error": str(e)})

    eval_search_stats = {}
    for i, values in eval_search_samples.items():
        if not values:
            continue
        eval_search_stats[i] = {
            "n_samples": len(values),
            "mean": statistics.mean(values),
            "variance": statistics.pvariance(values) if len(values) > 1 else 0.0,
            "values": values,
        }

    def ranking_desc(values):
        return [i for i, _ in sorted(values.items(), key=lambda kv: -kv[1])]

    def ranking_desc_by_mean(stats):
        return [i for i, _ in sorted(stats.items(), key=lambda kv: -kv[1]["mean"])]

    heuristic_rank = ranking_desc(heuristic_values)
    result = {
        "turn": record.get("turn"),
        "my_index": ref_policy.my_index,
        "candidate_indices": candidate_indices,
        "n_hidden_samples_used": len(samples_to_use),
        "heuristic_score": heuristic_values,
        "estimate_action_impact": impact_values,
        "eval_search_state": eval_search_stats,
        "value_model": value_model_values if vm_available else None,
        "rank_agreement": {
            "estimate_action_impact_top1_matches_heuristic": (
                bool(impact_values) and ranking_desc(impact_values)[0] == heuristic_rank[0]
            ),
            "eval_search_state_top1_matches_heuristic": (
                bool(eval_search_stats) and ranking_desc_by_mean(eval_search_stats)[0] == heuristic_rank[0]
            ),
        },
        "scale_summary": {
            "heuristic_score": {"min": min(heuristic_values.values()), "max": max(heuristic_values.values())} if heuristic_values else None,
            "estimate_action_impact": {"min": min(impact_values.values()), "max": max(impact_values.values())} if impact_values else None,
            "eval_search_state_mean": (
                {"min": min(s["mean"] for s in eval_search_stats.values()), "max": max(s["mean"] for s in eval_search_stats.values())}
                if eval_search_stats else None
            ),
        },
        "errors": errors,
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="PR0-C shadow evaluator comparison (read-only)")
    parser.add_argument("bundle_path", help="Path to a Replay Bundle JSONL file (from PR0-B capture)")
    parser.add_argument("--output", required=True, help="Where to write the shadow-comparison JSONL")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--samples", type=int, default=4,
                         help="Hidden-state samples used per candidate for _eval_search_state "
                              "(same sample applied to every candidate before advancing)")
    parser.add_argument("--limit", type=int, default=0, help="Only process the first N records (0 = all)")
    args = parser.parse_args()

    os.environ.setdefault("POKEMON_AI_EXEC_MODE", "BENCHMARK")
    mod = _load_agent_module()

    with open(args.bundle_path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    if args.limit:
        records = records[:args.limit]

    n_written = 0
    n_skipped = 0
    n_top1_agree_impact = 0
    n_top1_agree_search = 0
    n_compared_impact = 0
    n_compared_search = 0
    with open(args.output, "w", encoding="utf-8") as out:
        for record in records:
            result = evaluate_record(mod, record, args.top_k, n_samples=args.samples)
            if result is None:
                n_skipped += 1
                continue
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            n_written += 1
            if result["estimate_action_impact"]:
                n_compared_impact += 1
                n_top1_agree_impact += int(result["rank_agreement"]["estimate_action_impact_top1_matches_heuristic"])
            if result["eval_search_state"]:
                n_compared_search += 1
                n_top1_agree_search += int(result["rank_agreement"]["eval_search_state_top1_matches_heuristic"])

    print(f"records processed: {len(records)}  written: {n_written}  skipped(non-MAIN or maxCount!=1): {n_skipped}")
    if n_compared_impact:
        print(f"_estimate_action_impact top-1 agreement with heuristic: {n_top1_agree_impact}/{n_compared_impact}")
    if n_compared_search:
        print(f"_eval_search_state top-1 agreement with heuristic: {n_top1_agree_search}/{n_compared_search} "
              f"(ranked by per-candidate mean over {args.samples} paired hidden samples -- "
              f"see per-record variance in the output JSONL, and the CRN caveat in the module docstring)")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
