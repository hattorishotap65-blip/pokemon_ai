# Play Before Attack 001

## Purpose

Attack when legal が高すぎ (89.8%)、PLAY rate が Top より低い (14% vs 26%) 問題を検証。攻撃可能な場面で PLAY/EVOLVE/ABILITY を先に実行してから攻撃する bonus を試す。

## Background

| Metric | Top Agents | Our #164 | Gap |
|--------|-----------|----------|-----|
| PLAY rate | 26.07% | 14.02% | -12 pt |
| Attack when legal | 31.9% | 89.8% | +58 pt |

## Implementation

`ml_hybrid.py` の `_heuristic_ml_score` に play-before-attack bonus を追加:
- 条件: PLAY/EVOLVE/ABILITY かつ has_legal_attack かつ hand_count >= 4
- Default OFF (`POKEMON_AI_PLAY_BEFORE_ATTACK=0`)

## 100g Results

| Variant | Bonus | PLAY % | Atk when legal | miss_KO | KO capture | attach_active | starved | oversetup |
|---------|-------|--------|----------------|---------|------------|--------------|---------|-----------|
| A baseline | 0 | 12.54% | 87.5% | 7 | 97.3% | 54.5% | 314 | 82 |
| C +0.10 | 0.10 | 12.96% | 87.2% | 5 | 97.5% | 53.0% | 333 | 63 |
| D +0.15 | 0.15 | 12.30% | 87.5% | 11 | 95.4% | 49.4% | 365 | 90 |

All: errors=0, timeouts=0, zero_damage=0, END+legal_attack=0

## Key Finding

**ml_hybrid bonus (+0.05 to +0.15) は PLAY rate をほとんど変えない。**

PLAY rate は A(12.54%) → C(12.96%) で +0.4 pt のみ。Attack when legal も変化なし。

### 原因

#160 と同じ構造的問題:
- PLAY/ATTACK の選択は ionos_rules.py のルールスコア (100-300 pt) で決まる
- ml_hybrid の bonus は正規化後 0-10 pt の範囲で加算されるだけ
- +0.10 の heuristic bonus は全体スコアに対して無視できるほど小さい

### D (+0.15) の悪化

D は miss_KO=11, KO capture=95.4% と悪化。PLAY bonus が attack のスコアバランスを崩し、KO 機会で非 attack 行動が選ばれやすくなった。

## Conclusion

**ml_hybrid 層での play-before-attack bonus は効果なし。** PLAY 優先を改善するには:

1. `ionos_rules.py` で攻撃可能場面の PLAY scoring を直接調整する
2. または `policy.py` の `suppress_attack_if_pre_required()` のような攻撃抑制ロジックを拡張する
3. またはデッキ差として受け入れる (Iono deck は setup が少なく攻撃が早いのが特徴)

## Recommendation

**#164 を本命として維持。** play-before-attack は採用しない。

PLAY rate の差 (14% vs 26%) の大部分はデッキ構成の違い:
- Top agents の多くは Crustle/Dragapult 等の setup 重視デッキ
- Iono's Kilowattrel は比較的早期に攻撃可能になるデッキ
- PLAY rate を Top に近づけることが必ずしも改善にならない
