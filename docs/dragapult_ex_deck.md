# Dragapult ex デッキ — リファレンス

記録日: 2026-06-18

---

## デッキリスト (60枚)

| 枚数 | カード名               | カードID |
|------|----------------------|---------|
| 4    | Dreepy               | 119     |
| 4    | Drakloak             | 120     |
| 3    | Dragapult ex         | 121     |
| 2    | Duskull              | 131     |
| 2    | Dusclops             | 132     |
| 1    | Dusknoir             | 133     |
| 1    | Munkidori            | 112     |
| 1    | Fezandipiti ex       | 140     |
| 1    | Budew                | 235     |
| 1    | Meowth ex            | 1071    |
| 4    | Buddy-Buddy Poffin   | 1086    |
| 4    | Ultra Ball           | 1121    |
| 2    | Rare Candy           | 1079    |
| 2    | Night Stretcher      | 1097    |
| 4    | Lillie's Determination | 1227  |
| 3    | Crispin              | 1198    |
| 3    | Boss's Orders        | 1182    |
| 4    | Crushing Hammer      | 1120    |
| 1    | Unfair Stamp (ACE SPEC) | 1080 |
| 1    | Handheld Fan         | 1161    |
| 2    | Jamming Tower        | 1246    |
| 4    | Basic Fire Energy    | 2       |
| 4    | Basic Psychic Energy | 5       |
| 2    | Basic Dark Energy    | 7       |

---

## 勝ち筋 (Win Condition)

### メインプラン: ダメカン蓄積 + ファントムダイブで多面処理

1. **序盤**: Dreepy を2体以上展開（Buddy-Buddy Poffin 優先）
2. **中盤**: Drakloak → Dragapult ex へ進化（Rare Candy 可）
3. **攻撃**: Phantom Dive で場全体に6個ダメカンを分散配置
   - 複数ターンかけてベンチを60ダメージ蓄積 → まとめて KO
   - 1ターンで複数プライズを取る「多面KO」が強み

### サブプラン: Dusknoir の Ominous Diploma

- Duskull → Dusclops → Dusknoir に進化するたびに2ダメカン蓄積
- Phantom Dive と組み合わせて KO ラインを早める

### Munkidori の役割

- 相手がエネルギーを付けるたびにダメカン1個追加（能力）
- 条件: Munkidori 自身に悪エネルギーを1枚付ける必要がある

---

## エネルギー配分ルール

### 付けていいポケモン

| エネルギー種 | ID | 貼り先 | 理由 |
|------------|-----|--------|------|
| 炎 (Fire)   | 2  | Dragapult ライン (Dreepy/Drakloak/Dragapult ex) | Phantom Dive のコスト [R][P]any |
| 超 (Psychic) | 5 | Dragapult ライン | 同上 |
| 悪 (Dark)   | 7  | Munkidori のみ | 能力発動条件 |

### 絶対に付けないポケモン

| ポケモン | 理由 |
|---------|------|
| Duskull / Dusclops / Dusknoir | 攻撃役ではない、エネルギー不要 |
| Budew | エネルギー不要 |
| Fezandipiti ex | サポート役 |
| Meowth ex | サポート役 |

### Phantom Dive の攻撃条件

```
炎エネルギー x1 以上
超エネルギー x1 以上
合計 3 枚以上
```

単純な枚数ではなく **色条件込み** で判定（悪エネ3枚では打てない）

---

## 各カードの役割

| カード | role | 用途 |
|--------|------|------|
| Dragapult ex | main_attacker | Phantom Dive でダメカン6個分散 |
| Dreepy / Drakloak | evolution_base / evolve_bridge | 進化ライン |
| Dusknoir | search_engine + sub_attacker | Ominous Diploma でダメカン蓄積 |
| Duskull / Dusclops | evolution_base | 進化ライン |
| Munkidori | setup | 相手エネ付けにダメカン反応 |
| Fezandipiti ex | search_engine | 手札補充 |
| Budew | basic_setup | 序盤の盾・エネ遅延 |
| Buddy-Buddy Poffin | search | Dreepy/Duskull をベンチへ |
| Rare Candy | evolve | Dreepy → Dragapult ex へ飛ばす |
| Crispin | energy_accel | 炎エネルギーを2枚手から付ける |
| Boss's Orders | disruption | ベンチの弱いポケモンを引き出す |
| Crushing Hammer | disruption | 相手エネルギー除去（コインあり） |
| Jamming Tower | disruption | ex の特性を止める |
| Handheld Fan | tool | Dragapult ex に付けて自由退場 |
| Unfair Stamp | disruption (ACE SPEC) | 相手の手札を2枚に |
| Lillie's Determination | draw_refresh | 手札シャッフル+7枚ドロー |

---

## エージェント実装の注意点

### 攻撃可能判定 (turn_plan.py)

Dragapult ex (ID=121) の `can_now` / `can_with_attach` は**色ベース**で判定:

```python
def _can_dragapult_attack_now(pokemon):
    etypes = _get_pokemon_energy_types(pokemon)
    return FIRE in etypes and PSYCHIC in etypes and len(etypes) >= 3

def _can_dragapult_attack_with_attach(pokemon, hand, card_table, energy_attached):
    if energy_attached: return False
    etypes = _get_pokemon_energy_types(pokemon)
    for h_type in _get_hand_energy_types(hand, card_table):
        future = etypes + [h_type]
        if FIRE in future and PSYCHIC in future and len(future) >= 3:
            return True
    return False
```

### エネルギー貼り先スコアリング (dragapult_rules.py)

`score_energy_attachment(energy_cid, target_cid, state)` で実装:

- Fire/Psychic → Dragapult ライン: +20 (未充足なら +10)
- Dark → Munkidori: +20 (悪エネ未付きなら +8)
- Dark → Dragapult ライン: -12 (色ミスマッチ)
- Fire/Psychic → Munkidori: -15
- Any → Dusk ライン: -20
- Any → Budew / Support EX: -15

### セットアップ優先順位 (dragapult_rules.py _score_poffin_bench)

```
Dreepy 0枚 → +100 (最優先)
Dreepy 1枚 → +90
Duskull (Dreepy≥2の後) → +75
Dreepy 2枚+ → +60
Duskull (Dreepy<2) → +40 (後回し)
```

### Setup Pokemon フィルタ (turn_plan.py)

以下はKOできる時だけ攻撃計画に含める:
```python
_SETUP_MON_IDS = {119, 131, 112, 235}  # Dreepy, Duskull, Munkidori, Budew
```

---

## 対 Crustle 耐久デッキ の対策

Dwebble (344) が見えたら:
- Boss's Orders でベンチの Dwebble を引き出す (+5 bonus)
- Phantom Dive のダメカンを Dwebble に優先集中
- Jamming Tower で Hero's Cape 貫通 (max_hp > 140 で判定)
- Crushing Hammer でエネルギー除去 (Crustle は多エネ必要)
