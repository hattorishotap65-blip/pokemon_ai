# Level 5 F0004 Verification Report

## 対象

F0004: bellibolt_attack_probably_correct

## 現在の分類

**no_fix_needed** — Bellibolt ex の固定230ダメージが Voltorb 推定打点以上のため、Bellibolt ex で攻撃する判断は妥当。

## 調査結果

### 1. 分類条件の確認

```
F0003 条件: actual_attacker=269 AND estimated_voltorb_damage > 230
F0004 条件: actual_attacker=269 AND estimated_voltorb_damage <= 230
```

**境界リーク: 0件** — Voltorb 推定打点 > 230 のケースが F0004 に混入していない。

| 項目 | 値 |
|------|-----|
| F0003 最小打点 | 240 |
| F0004 最大打点 | 220 |
| F0004 に damage > 230 混入 | **0件** |

境界は **20ポイントのギャップ（221-239 は発生しない）** があり、明確に分離されている。打点は 20 刻み（20 + 20 × Lightning 枚数）なので、230 は発生しない。

### 2. F0004 の件数と Voltorb 打点分布

| 打点範囲 | 件数 |
|---------|------|
| 120-159 | 25 |
| 160-199 | 45 |
| 200-239 | 83 (全て 200 or 220) |
| **合計** | **153** |

- 全件で Voltorb 推定打点 <= 220
- Bellibolt ex 230 > Voltorb 最大 220 → **Bellibolt の方が単純打点で上**

### 3. 代表ログ確認

| ゲーム | ターン | Active | Voltorb推定打点 | Bellibolt打点 | 判定 |
|--------|--------|--------|---------------|-------------|------|
| g1817 | t=6 | 269 | 220 | 230 | BB > VT → **妥当** |
| g1835 | t=9 | 269 | 220 | 230 | BB > VT → **妥当** |
| g1847 | t=9 | 269 | 220 | 230 | BB > VT → **妥当** |
| g1842 | t=10 | 269 | 220 | 230 | BB > VT → **妥当** |

全件で Bellibolt (230) >= Voltorb推定打点 (120-220)。

### 4. KO 分析

opp_hp が取得できたケースでの KO 能力分析:

| 分類 | 件数 |
|------|------|
| Bellibolt だけ KO 可能 | 0 |
| 両方 KO 可能 | 0 |
| どちらも KO 不可 | 0 |

opp_hp が全件 `?`（ログに未記録）のため KO 分析は不可。ただし、Bellibolt (230) > Voltorb (max 220) なので、Bellibolt の方が KO 可能性は常に高い。

### 5. サイド効率の考察

Voltorb は非 ex（倒されても 1 サイド）、Bellibolt ex は ex（倒されると 2 サイド）。サイド効率だけ見れば Voltorb が有利。

しかし F0004 のケースでは:
- Bellibolt 230 > Voltorb 220 → **打点で Bellibolt が上**
- 10 ダメージ差で交代するメリットは小さい
- retreat にはエネルギーコスト（retreat cost 3）がかかる
- retreat 後に Voltorb が攻撃できるのは次のセレクト

→ **サイド効率を考慮しても、10 打点差のために retreat するのは非合理的**

### 6. F0003/F0004 境界条件

| | F0003 | F0004 |
|---|---|---|
| 条件 | Voltorb > 230 | Voltorb <= 230 |
| 実際の範囲 | 240+ | 120-220 |
| ギャップ | 221-239 は発生しない（20刻み） |
| 判定 | scoring_adjustment | **no_fix_needed** |
| priority | medium | **low** |

境界は明確で混同はない。

### 7. レポート側の確認

`latest_fix_candidates.md` での F0004 の扱い:
- **"No-Fix / Detector Refinement Candidates"** セクションに配置 ✓
- `suggested action: no_fix_needed` ✓
- Fix Candidates セクション（actionable）には含まれていない ✓
- target_files: `[]`（空） ✓

### 8. 安全指標

| 指標 | 値 |
|------|-----|
| attack_available_but_no_attack | 2 (ゲーム分散) |
| end_when_attack_available | 0 |
| retreat_when_attack_available | 0 |
| agent 挙動変更 | **なし** |

## 最終判断

**no_fix_needed**

理由:
1. Bellibolt ex 230 > Voltorb 最大 220 → 全件で Bellibolt の打点が上
2. 10 打点差のために retreat する合理性がない（retreat cost 3）
3. F0003 との境界リーク 0件
4. レポートで no_fix_needed として正しく分類されている
5. actionable fix candidates に含まれていない

## Detector / Report 側の改善

**改善不要。** 現在のレポート出力で:
- F0004 は no_fix_needed として明示
- Fix Candidates セクションには含まれず、"No-Fix / Detector Refinement Candidates" に配置
- 件数が多くても修正対象として扱われない

## 変更ファイル

| ファイル | 変更 |
|---------|------|
| `agent/ionos_rules.py` | **変更なし** |
| `agent/policy.py` | **変更なし** |
| `agent/turn_rule_engine.py` | **変更なし** |
| `deck.csv` | **変更なし** |
| `tools/classify_anomalies.py` | **変更なし** |
| `reports/level5_f0004_verification.md` | 新規作成（このレポート） |
