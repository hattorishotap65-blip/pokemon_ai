# experiments/eval_infra

Generic evaluation/measurement infrastructure for comparing a candidate
`raging_bolt`-style artifact (`main.py` + `deck.csv` + optional `params.json`)
against a baseline artifact over a fixed local sandbox opponent league
(Lucario, Dragapult, Mega Starmie; `mirror` = smoke/auxiliary self-play
only).

## Scope boundary (must read before using)

This package does **not**:

- create or activate an App Profile (`profiles/outcome/*`),
- execute screening or confirmation evaluation as defined by
  `docs/agent-workflow/outcome-improvement-cycle.md`,
- produce Gatekeeper PASS Evidence, or import/call
  `tools/outcome_gatekeeper.py` at runtime (only `experiments/test_eval_infra.py`
  does, as a test-only, read-only drift guard),
- decide any production threshold, baseline commit, or dataset version.

It is measurement infrastructure only, out of scope for any prior-session
"golden"/adjudication/deck-enumeration mechanism a past task may have used;
none of that is created, referenced, or adopted here, and this package does
not create `experiments/golden_canonical_hash.py`. (See F7 below for the one
item from that exclusion list -- self-play "mirror" support -- that turned
out to be an in-scope, required part of this package's own design, not
something excluded.)

`summarize`'s output is a **Measurement Report**, not a Gatekeeper Evidence
Bundle: every cell it emits is shaped exactly like a Gatekeeper Evidence
cell (`metric_id`, `segment_id`, `observations`, `baseline_stats`,
`candidate_stats`, `delta_stats`), but the report omits `profile_id`,
`profile_version`, `profile_sha256`, `cycle_id`, and `evidence_round` --
those only exist once a real, active App Profile and Cycle are bound.
Assembling a Measurement Report plus an active Profile's binding fields
into a Gatekeeper-ready Evidence Bundle is a distinct, later, out-of-scope
step this package does not perform.

## CLI

```
python -m experiments.eval_infra.raging_bolt_eval manifest \
    --candidate-agent PATH --candidate-deck PATH --candidate-artifact-id ID \
    --baseline-agent PATH --baseline-deck PATH --baseline-artifact-id ID \
    [--candidate-params PATH] [--baseline-params PATH] \
    --protocol-id ID --dataset-id ID --dataset-version V --stage {screening,confirmation} \
    [--games-per-worker N] [--wall-timeout-seconds S] --out PATH
    # refuses to overwrite an existing file at PATH. Requires
    # --games-per-worker >= 1 and a finite, strictly positive
    # --wall-timeout-seconds. Both are bound into protocol_identity HERE, at
    # manifest time -- `run` reads them back out of the manifest, it does not
    # accept its own independent values, so the executed protocol can never
    # silently diverge from what comparison_manifest_sha256 identifies. Both
    # `run` and `summarize` independently RECOMPUTE protocol_identity's,
    # dataset_identity's, and comparison_manifest_sha256's own hashes from
    # the manifest file's stored fields and reject the manifest if they no
    # longer match -- so hand-editing a manifest JSON file's contents (e.g.
    # changing games_per_worker) after `manifest` wrote it is detected and
    # rejected, not silently trusted.

python -m experiments.eval_infra.raging_bolt_eval run \
    --manifest PATH --opponent lucario --opponent dragapult --opponent megastarmie [--opponent mirror] \
    --games-per-segment N --jsonl-out DIR [--allow-partial]
    # --games-per-segment must be >= 1. games_per_worker/wall_timeout_seconds
    # come from --manifest itself (see above), not from a `run`-level flag.
    # Before playing any games, re-hashes the candidate/baseline artifact
    # files on disk and aborts if they no longer match the sha256 recorded
    # in --manifest (the artifact changed since `manifest` was run). If an
    # artifact binds a --*-params file, sets POKEMON_AI_PARAMS_PATH to that
    # exact path for the head_to_head.py subprocess (and explicitly clears
    # any inherited value otherwise), so the params file actually used
    # matches the one that was hashed into the manifest.
    # Refuses to write into an already-existing per-(opponent,arm) jsonl
    # file -- use a fresh --jsonl-out directory per run rather than re-using
    # one (prevents silently mixing games from two different runs).
    # After each head_to_head.py subprocess batch, verifies the jsonl file
    # actually gained exactly the requested number of new records; a
    # zero-exit subprocess that wrote the wrong count is treated as an
    # error, not a silent success. On a wall-clock timeout, recounts any
    # records the subprocess had already flushed before hanging (relevant
    # when games_per_worker > 1) rather than assuming none were written.

python -m experiments.eval_infra.raging_bolt_eval summarize \
    --manifest PATH --jsonl-in FILE [--jsonl-in FILE ...] \
    --stage {screening,confirmation} --rng-seed N --out PATH
    # --stage must match --manifest's own stage, and --manifest's own
    # protocol/dataset/comparison hashes are recomputed and verified against
    # its own stored fields (rejects a manifest hand-edited after `manifest`
    # wrote it). --confidence-level is actually used by every stats
    # computation; --bootstrap-replicates and --rng-seed are actually used
    # specifically by the two decision-time latency cells' bootstrap delta
    # (game-level rate cells use confidence-level only, via Wilson/Newcombe,
    # not a bootstrap) -- not merely parsed either way, and all three are
    # recorded in the output report's "measurement_settings" so the report
    # is self-documenting/reproducible. --jsonl-in files must have distinct
    # (opponent_id, arm) identities (derived from their filename, which
    # must carry the FULL 64-hex comparison_manifest_sha256 as its prefix --
    # not a truncated one, to make a renamed/mismatched file materially
    # harder to pass off as belonging to this comparison) and a known
    # opponent_id (lucario/dragapult/megastarmie/mirror); each record's
    # label_a/label_b are cross-checked against the filename's (arm,
    # opponent_id) and rejected on mismatch. illegal_action_rate's
    # denominator excludes records with legality=="unknown" (only
    # legal/illegal records count), matching the three-bucket model in F2.
```

`opponent_pins.json` in this directory is a **static, tracked scaffold that
starts as `{}`**. It is never auto-populated by any script -- entries are
added only by explicit manual edit before running `clone_opponent.py`-backed
opponents, in this shape:

```json
{"dragapult": {"commit_sha": "<40-hex>", "repo_url": "<https URL or local path>",
                "file_paths": ["<repo-relative agent .py>", "<repo-relative deck .csv>"]}}
```

`run` reads `commit_sha` via `opponent_registry.resolve_opponent()` (PARTIAL
until actually cloned) and `repo_url`/`file_paths` directly to invoke
`clone_opponent.clone_and_verify()`, which clones to a temporary directory,
verifies the exact commit, and copies out just the 2 listed files to a
run-scoped destination directory (cleaned up after `run` finishes) so
`head_to_head.py` can actually load them. A pin missing any of `commit_sha`/
`repo_url`/`file_paths`, or with `file_paths` not containing exactly 2
entries (agent, then deck), is treated as unresolvable (skipped/UNAVAILABLE
for that opponent), never partially trusted or silently retried with a
floating/unpinned clone.

`protocol_manifest.json` in this directory is a **static schema/example
template only** (see its own `_comment`/`status` fields) -- real per-run
manifests are always written by the `manifest` subcommand to a
caller-specified `--out` path, never to this tracked file.

## Metric-to-statistical-method mapping

- `external_league_win_rate`, `error_rate`, `timeout_rate`,
  `illegal_action_rate`: each GAME contributes exactly one independent 0/1
  observation (a game terminates the instant an illegal action/error/timeout
  occurs, so there is no meaningful within-game repetition for these four
  metrics given this package's per-game record granularity). Per-arm
  intervals use the Wilson score method; the delta (candidate - baseline)
  uses the Newcombe-Wilson hybrid interval (`stats.newcombe_delta`) built
  from each arm's own Wilson bounds -- the standard method for the
  difference of two independent proportions, not naive interval subtraction.
- `decision_time_p50_ms`, `p95_decision_time`: MULTIPLE, correlated
  observations per game (every decision in a game shares that game's engine
  state and non-deterministic search behavior). Per-arm point estimates are
  the empirical percentile over that arm's own pooled decision durations;
  the delta uses a whole-GAME cluster bootstrap (`stats.game_cluster_bootstrap_delta`,
  10,000 replicates by default, deterministic given `--rng-seed`) that
  resamples whole games (never individual decisions) to avoid understating
  the interval from within-game correlation (pseudo-replication).
- `observation_count`: an exact count (this arm's own recorded decisions,
  summed across the segment's games), reported as a degenerate interval
  (`estimate == lower == upper`) with no fabricated uncertainty.
- Every `head_to_head.py --jsonl-out` decision entry is tagged
  `"actor": "a"` or `"b"`; `run` always invokes `head_to_head.py` with the
  arm under measurement as `--agent-a` and the opponent as `--agent-b`, so
  `summarize`'s decision-time/observation-count computations filter to
  `actor == "a"` only -- the arm's own decisions, never the opponent's.

## Required caveats (from a same-model Design Challenger pass and an
independent, different-model Codex Final Auditor pass; all apply as
documented risk acceptances or known limitations, not defects to silently
work around -- items the Final Auditor found to be actual bugs, not
acceptable caveats, were fixed in the implementation instead of documented
here; see git history for that pass's findings)

- **F1** -- `--first-player` on `experiments/head_to_head.py` controls
  player-index/deck-slot assignment only; it does not by itself confirm
  which side the compiled cabt engine treats as the true "first mover"
  (`Observation.current.firstPlayer` / the `COIN` select event are resolved
  by the engine's own coin-flip mechanic, not read or conditioned on by
  this flag). True first-mover parity across `--first-player a` vs `b`, and
  therefore the precision of the `first-player`/`second-player` segments, is
  unverified pending an L1 Linux run that inspects `obc.current.firstPlayer`
  across paired runs.
- **F2** -- A malformed agent return value raises `ValueError` from
  `cg/game.py`'s `battle_select()` (checked before the engine call), not
  `IndexError`. This harness's per-game record classifies that case's
  `error_actor` as `"engine"` rather than the acting agent, and its
  `legality` as `"unknown"` rather than `"illegal"` -- a known,
  intentional three-bucket-model consequence (legal / illegal / unknown; an
  unconfirmed case is never silently counted as either legal or illegal).
  This means `illegal_action_rate`'s numerator only counts engine-confirmed
  illegal actions (a real `IndexError` from `battle_select`), and a
  malformed-return case is excluded from that rate's denominator entirely
  rather than miscounted -- an undercount risk if malformed returns are
  common, disclosed here rather than silently smoothed over.
- **F3** -- `manifest --games-per-worker > 1` (batching more than one game
  into a single `head_to_head.py` subprocess call) and `run`'s own
  cross-invocation `--first-player` alternation are **mutually exclusive**.
  Combining both is unsupported and unspecified; leave `--games-per-worker`
  at its default of 1 unless you have verified the interaction yourself.
  (`run`'s wall-clock-timeout handling does correctly recount any records a
  timed-out batch had already flushed before hanging, so a timeout with
  `games_per_worker > 1` no longer under-counts already-completed games --
  but the seat-alternation concern above is independent of that fix and
  remains unresolved for `games_per_worker > 1`.)
- **F4** -- `clone_opponent.py`'s hardening threat model is a
  **manually-edited, local, non-network-facing** `opponent_pins.json` --
  it rejects `..`/backslash/drive-letter path components and repo URLs
  starting with `-`, but does **not** implement a full URL-scheme allowlist
  (e.g. restricting to `https://`) against `git clone` argument-injection
  vectors (`ext::`/`fd::` transports). This is a deliberate, documented risk
  acceptance given the low-trust, locally-authored input, not an oversight.
- **F6** -- The tracked `experiments/eval_infra/protocol_manifest.json` is
  a static template (see its own `status` field); real, per-run manifests
  are always written to a caller-specified `manifest --out` path.
- **F8** -- The `--jsonl-out`/`--record-decision-timing` code-path split
  inside `experiments/head_to_head.py`'s game loop (added additively; the
  default no-flags path is untouched) has had its default-off-path safety
  verified by code review and by the Windows-runnable test suite's
  structural/formula-level checks only. It has not yet been exercised by an
  actual cabt game (that requires WSL/Linux; see L1-L3 in
  `experiments/test_eval_infra.py`'s module docstring), so its behavior
  under real engine execution is not yet empirically confirmed.
- **F9** -- No test anywhere in this repository's current CI
  (`.github/workflows/tests.yml`) exercises the real compiled `cg` engine.
  Deferring this package's real-game tests (L1-L3) to a manual/Linux-only
  run continues that existing repository-wide convention; it is not a new
  gap introduced by this package.

(F7 is not listed here: it was a required implementation item -- `mirror`
opponent handling -- not a caveat, and is implemented in
`opponent_registry.py`/`raging_bolt_eval.py`, described in "Opponent
availability" below. F5 was an earlier draft's wording issue about
`game_cluster_bootstrap_delta`'s generality, resolved by the "Metric-to-
statistical-method mapping" section above, which states exactly which
metrics use it and why -- it is not listed as a standalone caveat either.)

## Opponent availability, as of this package's initial implementation

- **Lucario**: `UNAVAILABLE`. `experiments/agents/top_lucario_1084_main.py`
  and `experiments/decks/top_lucario_1084.csv` are a gitignored,
  manually-retained, local-only pair of files with no clone/download path,
  and both are currently absent from this worktree. No substitute or
  inferred deck is ever accepted.
- **Dragapult, Mega Starmie**: `UNAVAILABLE` until `opponent_pins.json` is
  given a real, complete entry (`commit_sha` + `repo_url` + `file_paths`)
  for each, at which point `run` calls `clone_opponent.clone_and_verify()`
  to actually clone, verify, and use it -- requires network access, not
  exercised by this Windows implementation session (see L3).
- **Mirror**: `AVAILABLE`, always. Requires no pin or clone -- each arm
  (baseline/candidate) plays against itself. Reported only in the
  Measurement Report's `diagnostics` block (`mirror_games`), and is
  excluded from every league win-rate/error-rate/etc. cell.

## Tests

See `experiments/test_eval_infra.py`'s module docstring for the full T1-T17
(Windows-runnable now) / L1-L3 (Linux-only, explicitly deferred and not
claimed passing) breakdown.
