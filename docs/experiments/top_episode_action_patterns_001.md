# Top Episode Action Patterns 001

## Purpose

上位agentの行動パターンを分析し、現在の自分のagentとの差分を特定する。
いきなり挙動変更はせず、次の改善候補を数字で決める。

## Background

| PR | Description |
|----|-------------|
| #155 | area_fix_only submission candidate (現在の本命) |
| #157 | Kaggle discussion ML insights — 上位ログ分析が最も現実的と判断 |

#157 の調査で判明した方針:
- 純粋 ML/RL は heuristic に勝てていない (最高 25%)
- MCTS は 1秒で ~10 rollouts が限界
- Daily Top Episodes / self-play ログの分析利用は公式許可済み
- 上位agentの行動を分析して heuristic を改善するのが現実的

## Data Sources

| Source | Format | Use |
|--------|--------|-----|
| Self-play logs (`logs/game_gNNNNN.jsonl`) | JSONL | 自分のagentの行動分析 |
| action_feature_logging 出力 | JSONL (feature rows) | 同上 (別形式) |
| Kaggle Daily Top Episodes | JSON | 上位agentの行動分析 (今後取得) |

## Analysis Script

```bash
# Self-play logs (direct)
python experiments/analyze_top_episode_patterns.py \
    --from-range 280000 280050 \
    --label own_agent \
    --output artifacts/own_agent_action_patterns.json

# Feature JSONL
python experiments/analyze_top_episode_patterns.py \
    --input artifacts/area_fix_only_submission_smoke_50g.jsonl \
    --label own_agent \
    --output artifacts/own_agent_feature_patterns.json

# Top episodes (when available)
python experiments/analyze_top_episode_patterns.py \
    --input artifacts/top_episode_sample.jsonl \
    --label top_agents \
    --output artifacts/top_episode_patterns.json
```

## Our Agent Analysis (50g, area_fix_only)

### Action Distribution

| Action | Count | % |
|--------|-------|---|
| CARD | 4166 | 43.3% |
| ABILITY | 1513 | 15.7% |
| PLAY | 1234 | 12.8% |
| ATTACK | 608 | 6.3% |
| ATTACH | 600 | 6.2% |
| END | 515 | 5.4% |
| EVOLVE | 305 | 3.2% |
| ENERGY | 294 | 3.1% |
| RETREAT | 162 | 1.7% |

### Key Rates

| Metric | Value |
|--------|-------|
| Attack when legal | 608/683 (89.0%) |
| KO capture rate | 120/121 (99.2%) |
| miss_KO | 1 |
| END when legal attack | 0 (0.0%) |
| Attach to active | 298/600 (49.7%) |
| Active energy starved | 188 |
| Bench oversetup | 37 |
| zero_damage attack | 0 |
| Completed attacker unused | 0 |

### Phase Distribution

| Phase | ATTACK | ATTACH | END | PLAY | EVOLVE | RETREAT | ABILITY |
|-------|--------|--------|-----|------|--------|---------|---------|
| early (1-3) | 34 | 128 | 116 | 324 | 26 | 0 | 36 |
| mid (4-8) | 134 | 116 | 104 | 200 | 80 | 0 | 176 |
| late (9+) | 440 | 356 | 295 | 710 | 199 | 162 | 1301 |

## Top Agent Analysis

_To be filled when Daily Top Episodes data is processed._

| Metric | Top Agents | Our Agent | Gap |
|--------|-----------|-----------|-----|
| KO capture rate | TBD | 99.2% | TBD |
| Attack when legal | TBD | 89.0% | TBD |
| Attach to active rate | TBD | 49.7% | TBD |
| END when legal attack | TBD | 0.0% | TBD |
| Active energy starved | TBD | 188 | TBD |
| Bench oversetup | TBD | 37 | TBD |
| Early ATTACK count | TBD | 34 | TBD |
| Early ATTACH count | TBD | 128 | TBD |

## Initial Observations (Our Agent)

### Strengths
- KO capture rate 99.2% — ほぼ全ての KO 機会を活用
- END when legal attack = 0 — 攻撃可能時に END を選んでいない
- zero_damage attack = 0 — 無駄な攻撃なし

### Concerns
- **Active energy starved = 188** — activeが攻撃に必要なエネルギーに届いていない状態で bench に attach している回数が多い
- **Bench oversetup = 37** — bench に 3+ attach / active に 1 以下の状態が発生
- **Attach to active rate = 49.7%** — ほぼ半々。上位agentと比較して active 優先度が足りるか要確認
- **Early ATTACK = 34** — early phase での攻撃回数が少ない (50g で 34 = ゲームあたり 0.68 回)
- **Attack when legal = 89.0%** — 11% の場面で攻撃可能なのに他の行動を選んでいる

## Improvement Candidates (Not Implemented Yet)

次PRで実装を検討する候補:

| 優先度 | 改善案 | 根拠 |
|--------|--------|------|
| 高 | Active energy starved を減らす — active attacker にエネを優先 | 188 回の starved attach は多い |
| 高 | Early attack count を増やす — 序盤で攻撃準備を加速 | ゲームあたり 0.68 回は少ない可能性 |
| 中 | Bench oversetup を減らす — active 未完成時の bench attach を抑制 | 37 回の oversetup |
| 中 | Attack when legal rate を上げる — 89% → 95%+ を目標 | 11% の非攻撃判断の妥当性を検証 |
| 低 | Attach to active rate を上げる — 50% → 60%+ | 上位agentとの比較次第 |

## Next Steps

1. Daily Top Episodes データを取得して上位agentの行動パターンを分析
2. 上記比較表を埋める
3. Gap が大きい項目を特定
4. 改善候補の優先順位を確定
5. 実装PRを作成 (1つずつ小さく)

## What This PR Does NOT Do

- runtime policy を変更しない
- ML hybrid score を変更しない
- submission.tar.gz を再作成しない
- leaderboard に提出しない
