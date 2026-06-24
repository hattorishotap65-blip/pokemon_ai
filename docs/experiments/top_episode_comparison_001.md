# Top Episode Comparison 001

## Purpose

Kaggle Daily Top Episodes (2026-06-23) の上位 agent と自分の agent を同じ指標で比較し、次の改善候補を数字で決める。

## Data

| Dataset | Source | Episodes | Decisions |
|---------|--------|----------|-----------|
| Top Agents | Kaggle Daily Top Episodes 2026-06-23 | 10 | 2094 |
| Our Agent | Self-play logs 280000-280049 (area_fix_only) | 50 (×2 players) | 9613 |

Top Episodes は上位スコアの agent 同士の対戦ログ。
Our Agent は self-play (同じ agent 同士) のログ。

## Comparison Table

| Metric | Top Agents | Our Agent | Gap | Interpretation |
|--------|-----------|-----------|-----|----------------|
| **Attach to active rate** | **81.3%** | **49.7%** | **-31.6 pt** | **Top は圧倒的に active 優先** |
| Attack when legal | 32.0% | 89.0% | +57.0 pt | デッキ差が大きい (注1) |
| END when legal attack | 0.8% | 0.0% | -0.8 pt | 同等 |
| Active energy starved | 0 | 188 | -188 | **Top は starve 0、我々は 188** |
| Bench oversetup | 1 | 37 | -36 | **Top はほぼなし** |
| zero_damage attack | 0 | 0 | 0 | 同等 |
| Completed attacker unused | 0 | 0 | 0 | 同等 |

注1: Attack when legal の差はデッキ構成の違いが大きい。Top agents のデッキは setup 行動が多く、legal attack がある場面でも他の行動を選ぶ戦略が一般的。我々の Iono's Kilowattrel は attack 優先型なので高い方が正常。

## Action Distribution Comparison

| Action | Top Agents | Top % | Our Agent | Our % | Diff |
|--------|-----------|-------|-----------|-------|------|
| CARD | 846 | 40.4% | 4166 | 43.3% | -2.9 |
| PLAY | 560 | 26.7% | 1234 | 12.8% | **+13.9** |
| ATTACH | 230 | 11.0% | 600 | 6.2% | **+4.7** |
| ATTACK | 192 | 9.2% | 608 | 6.3% | +2.8 |
| EVOLVE | 75 | 3.6% | 305 | 3.2% | +0.4 |
| END | 69 | 3.3% | 515 | 5.4% | **-2.1** |
| ABILITY | 20 | 1.0% | 1513 | 15.7% | **-14.8** |
| RETREAT | 11 | 0.5% | 162 | 1.7% | -1.2 |

注: ABILITY の大きな差は Iono's Kilowattrel デッキの Bellibolt ex ability が多用されるため。
PLAY の差は Top agents がデッキ構成上 trainer / Pokemon 配置が多いため。

## Phase Distribution Comparison

### Early (Turn 1-3)

| Action | Top Agents | Our Agent | Gap |
|--------|-----------|-----------|-----|
| ATTACK | 51 | 34 | +17 |
| ATTACH | 51 | 128 | -77 |
| END | 34 | 116 | -82 |
| PLAY | 173 | 324 | -151 |
| EVOLVE | 12 | 26 | -14 |

### Late (Turn 9+)

| Action | Top Agents | Our Agent | Gap |
|--------|-----------|-----------|-----|
| ATTACK | 98 | 440 | -342 |
| ATTACH | 130 | 356 | -226 |
| END | 10 | 295 | -285 |

注: 絶対数の差はゲーム数の違い (10 vs 50×2) が主因。比率で比較すべき。

## Key Findings

### 1. Attach to active rate: 81.3% vs 49.7% (最大の差分)

Top agents は energy attach の **81.3%** を active Pokemon に集中。我々は **49.7%** でほぼ半々。
これは #152 の loss diagnostics で指摘した「active attacker energy starvation」と一致する。

**上位 agent は active を最優先で育てている。我々は bench に散らしすぎている。**

### 2. Active energy starved: 0 vs 188

Top agents では active が攻撃に必要なエネルギーに届いていない状態で bench に attach するケースが **0**。
我々は **188 回** 発生。

### 3. Bench oversetup: 1 vs 37

Top agents ではほぼゼロ。我々は 37 回。

### 4. END 率が低い

Top agents の END は 3.3% (69/2094)、我々は 5.4% (515/9613)。
Top agents はターン中により多くの行動を取ってから END する傾向がある。

### 5. KO capture rate は比較不可

Episode JSON にはKO 可能性の情報 (reason に "ko" を含むかなど) が含まれていないため、top agents の KO capture rate は測定できない。

## Improvement Candidates (Not Implemented)

| Priority | Improvement | Evidence | Expected Impact |
|----------|-------------|----------|-----------------|
| **1** | **Active energy priority を大幅に上げる** | attach to active 81.3% vs 49.7% | active attacker の育成が加速し、attack 開始が早まる |
| **2** | **Bench attach penalty を入れる (active 未完成時)** | active energy starved 0 vs 188 | bench への無駄な attach を削減 |
| **3** | **END 率を下げる (ターン中の行動を増やす)** | END 3.3% vs 5.4% | ターン中により多くの setup/attach を実行 |

### 具体的な実装方針 (次PR向け)

1. **ionos_rules.py の attach scoring**:
   - active attacker (Voltorb/Bellibolt ex/Kilowattrel) が攻撃に必要なエネに達していない場合、active への attach bonus を大きく引き上げる
   - bench への attach は active が完成するまで penalty を加える

2. **ml_hybrid.py の heuristic**:
   - `attach_to_active + active_is_main_attacker` の bonus を強化
   - `attach_to_bench + active_energy_needed > 0` の penalty を追加

3. **turn_rule_engine.py の END penalty**:
   - 「まだ実行できる行動がある」場合の END penalty を微増

## Caveats

- Top agents は様々なデッキ (Lucario, Crustle, Dragapult 等) を使用。Iono's Kilowattrel との直接比較にはデッキ差のバイアスがある
- Episode 数は 10 と少ない。傾向は参考値
- KO capture rate は episode 形式から測定不可
- attach to active の差 (81.3% vs 49.7%) はデッキ差を考慮してもなお大きい — 最優先の改善ポイント

## Next Steps

1. improvement candidate #1 (active energy priority) を小さく実装する PR を作成
2. 100g self-play で attach to active rate が 70%+ に改善するか確認
3. safety metrics (miss_KO, End+legal_attack 等) が悪化しないことを確認
4. leaderboard で検証

## What This PR Does NOT Do

- runtime policy を変更しない
- ML hybrid score を変更しない
- submission.tar.gz を再作成しない
- leaderboard に提出しない
