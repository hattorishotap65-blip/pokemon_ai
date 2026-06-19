# Level 5 F0003 Threshold Analysis

## 対象

F0003: bellibolt_over_voltorb_high_damage — 残り31件の追加改善調査

## 調査結果

### 残り31件の Voltorb 推定打点分布

| 打点範囲 | 件数 |
|---------|------|
| 240-259 | 20 |
| 260-279 | 4 |
| 280-299 | 5 |
| 300-319 | 2 |

**全31件が damage >= 240。231-239 の範囲は 0件。**

→ **閾値を 240→230 に下げても追加で拾えるケースは 0件。**

### 問題の本質

現在の F0003 修正は retreat bonus を +80 としているが、turn_rule_engine がretreat に -1000 ペナルティを課すため、合計スコアは **-919** となり、Bellibolt 攻撃 (**+196**) に勝てない。

| レイヤー | Retreat スコア | Attack スコア |
|---------|-------------|-------------|
| type_score | ~1 | ~23 |
| turn_rule | **-1000** | +150 |
| rule_bonus | +80 | +23 |
| **合計** | **-919** | **+196** |

修正コードは **181回発火**しているが、最終スコアで攻撃に負けるため実際にはretreatが選ばれない。

### 実験: bonus を +1200 に引き上げ

turn_rule の -1000 を超えるため +1200 に引き上げてA/Bテスト。

| 指標 | Baseline | Candidate | 判定 |
|------|----------|-----------|------|
| F0003 | 31 (0.62/g) | 25 (0.50/g) | 微改善 |
| retreat_when_attack_available | **0** | **1** | **悪化** |
| voltorb_over_wattrel_missed | 5 | 11 | 悪化 |
| attack_available_but_no_attack | 2 | 3 | 悪化 |

**判定: reject** — retreat bonus を上げすぎると、Bellibolt が不適切なタイミングで retreat する副作用が発生。

### 閾値を 230 に下げるべきか

**不要。** 残り31件は全て damage >= 240 であり、閾値変更では 0件の追加改善。

### なぜ retreat アプローチに限界があるか

`turn_rule_engine` は「攻撃可能なら retreat しない」というルールを -1000 で強制している。これは一般的には正しいが、「より強いアタッカーに交代する retreat」を例外として扱えない。

retreat bonus を +1200 にすると例外を作れるが、条件判定が不完全な場合に不適切な retreat が発生する。

## 代替アプローチ候補

| アプローチ | 方法 | リスク |
|-----------|------|--------|
| turn_rule_engine に pivot 例外を追加 | retreat_when_better_attacker_available を -1000 から除外 | 中（turn_rule の責務分担変更） |
| Bellibolt 攻撃にペナルティ追加 | Voltorb > 230 のとき Bellibolt 攻撃スコアを下げる | 中（攻撃判断全体に影響） |
| TO_ACTIVE/SWITCH 改善 | KO後の promote 時に Voltorb を優先 | 低（retreat 不要） |
| 現状維持 | F0003 は 86→31 で 64% 改善済み | なし |

## 採用判断

**keep_current_threshold**

- 閾値 240、bonus +80 を維持
- F0003 は元の 86 件から **31 件に 64% 削減済み**
- 残り31件はretreat アプローチの限界であり、パラメータ調整では解決困難
- 更なる改善は turn_rule_engine の構造的変更か、Bellibolt 攻撃ペナルティアプローチが必要

## 次の推奨アクション

1. **F0003 は現状で accept** — 十分な改善達成
2. 残り31件は **別チケット** として「turn_rule pivot exception」または「Bellibolt attack penalty」を検討
3. F0002 (voltorb_over_kilowattrel_missed) 102件も同じ retreat 限界に該当するため、同一アプローチで解決可能
