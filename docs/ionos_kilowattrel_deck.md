# Iono's Kilowattrel デッキ — ナレッジテンプレート

記録日: 2026-06-18
バージョン: v1

---

## 0. デッキリスト

| 枚数 | カード名 | カードID | 備考 |
|------|---------|---------|------|
| 3 | Iono's Voltorb | 265 | |
| 3 | Iono's Tadbulb | 268 | |
| 3 | Iono's Bellibolt ex | 269 | Stage1 ex |
| 3 | Iono's Wattrel | 270 | |
| 3 | Iono's Kilowattrel | 271 | Stage1 |
| 3 | Buddy-Buddy Poffin | 1086 | |
| 2 | Night Stretcher | 1097 | |
| 1 | Max Rod | 1110 | |
| 1 | Energy Retrieval | 1118 | |
| 3 | Ultra Ball | 1121 | |
| 2 | Poké Pad | 1152 | |
| 4 | Lillie's Determination | 1227 | |
| 4 | Canari | 1233 | |
| 3 | Levincia | 1254 | Stadium |
| 22 | Basic Lightning Energy | 4 | |

**合計: 60枚 / ACE SPEC: なし**

---

## 1. 勝ち筋 (Win Condition)

たねポケモンを複数展開
↓
雷エネルギーを毎ターン貼る
↓
Iono’s Bellibolt ex / Iono’s Kilowattrel に進化
↓
先に攻撃し続ける
↓
Energy Retrieval / Night Stretcher / Max Rod で息切れを防ぐ
↓
相手が2進化や複雑な準備をしている間にサイドを先行する

### メインプラン

- 手順1: Buddy-Buddy Poffin / Ultra Ball で Tadbulb + Voltorb をベンチ展開
- 手順2: Lightning エネルギーを手貼り → Voltorb で序盤攻撃 / Tadbulb → Bellibolt ex 進化
- 手順3: Bellibolt ex のエネルギー加速で全 Iono's ポケモンに雷エネを分散 → Voltorb 打点上昇 → プライズ先行

### サブプラン / 代替ルート

- Bellibolt ex ラインが取れない場合: Wattrel → Kilowattrel ラインで継戦
- Energy Retrieval / Night Stretcher / Max Rod で息切れを防ぎながら攻撃し続ける

### ゲームの流れ (フェーズ)

| フェーズ | ターン目安 | やること |
|---------|-----------|---------|
| 序盤 (SETUP) | T1-T3 | ベンチ展開、Lightning エネ付け |
| 中盤 (MID)   | T4-T6 | 進化、攻撃開始 |
| 終盤 (LATE)  | T7+   | プライズレース締め |

---

## 2. デッキ全体の役割分担

### アーキタイプ

主軸:
Iono’s Voltorb
Iono’s Tadbulb
Iono’s Bellibolt ex
Iono’s Wattrel
Iono’s Kilowattrel

展開:
Buddy-Buddy Poffin
Ultra Ball

継戦:
Energy Retrieval
Night Stretcher
Max Rod

ドロー・安定:
Lillie's Determination
Canari
Poké Pad
Levincia

エネルギー:
Basic {L} Energy 22枚

### 主要シナジー

1. Voltorb (265) + 全 Iono's ポケモンへの Lightning 分散 → 打点 20 + 20×(場の雷エネ合計) でスケール
2. Iono's Wattrel → Iono's Kilowattrel 進化ライン
3. Iono's Tadbulb → Iono's Bellibolt ex 進化ライン

---

## 3. card_knowledge の考え方

### role 設計方針
1. 雷エネルギーは基本的に価値が高い
2. たね展開を最優先
3. 1進化アタッカーへの進化を高評価
4. 攻撃可能なポケモンを優先
5. エネルギーが付いているポケモンを守る・育てる
6. 回収札は中盤以降に高評価
7. 手札事故時は Lillie's / Canari / Levincia を高評価

### スコア設計方針

- `use_score`: プレイする優先度 (0-10)
- `search_score`: サーチで持ってくる優先度 (0-10)
- `bench_score`: ベンチに置く優先度 (0-10)
- `energy_attach_score`: エネルギーを貼る優先度 (0-10)
- `discard_penalty`: 捨てたくない度 (0-10)

---

## 4. ポケモン別 knowledge
knowledge設定:

card_id: 265
card_name: Iono’s Voltorb
role: basic_attacker
sub_role: early_pressure
stage: basic
is_ex: false
priority: high
phase: early
bench_score: high
search_score: high
energy_attach_score: high
attack_score: high
keep_score: high
discard_penalty: high

AI上の扱い:

初手Active候補として評価する
Buddy-Buddy Poffinで出す候補にする
序盤から攻撃できるなら高評価する
Basic {L} Energy の貼り先として評価する
雑にUltra BallやLillieのコストで捨てない
Bellibolt exラインが用意できていない場合の序盤アタッカーとして扱う

評価ルール:

場にアタッカーがいない場合、Voltorbを高評価
Voltorbにエネルギーを貼ることで攻撃できるなら大きく加点
すでにBellibolt exやKilowattrelが攻撃準備できている場合は、Voltorbへの過剰エネルギー添付は抑制
後続が不足している場合はベンチ展開を評価

推奨スコア目安:

bench_score: 85
search_score: 80
energy_attach_score: 85
attack_score: 90
keep_score: 80
discard_penalty: 80

役割:

Iono’s Bellibolt ex の進化元
最重要の展開札
ベンチ優先対象
エネルギーを貼って進化後の攻撃準備を作る対象

knowledge設定:

card_id: 268
card_name: Iono’s Tadbulb
role: evolution_base
sub_role: bellibolt_base
stage: basic
is_ex: false
evolves_to: 269
evolves_to_ex: true
priority: very_high
phase: early
bench_score: very_high
search_score: very_high
energy_attach_score: high
attack_score: low_medium
keep_score: very_high
discard_penalty: very_high

AI上の扱い:

Buddy-Buddy Poffinで最優先級に出す
Iono’s Bellibolt ex が手札や山札に見えるならさらに高評価
進化元なので序盤にベンチへ置く
Basic {L} Energy を貼って、進化後すぐ攻撃できる形を作る
可能な限り捨てない
盤面にTadbulbがいない場合、Bellibolt exの価値は下げる

評価ルール:

ベンチにTadbulbがいない場合、Tadbulb展開を最優先
手札にBellibolt exがある場合、Tadbulbのbench_scoreをさらに加点
Tadbulbにエネルギーを貼ることで、次ターンBellibolt exの攻撃準備に近づくなら高評価
すでにTadbulbが2体以上いる場合は、追加TadbulbよりVoltorb/Wattrel展開を優先してよい

推奨スコア目安:

bench_score: 95
search_score: 85
energy_attach_score: 80
attack_score: 50
keep_score: 85
discard_penalty: 90
evolution_base_score: 95

役割:

メイン1進化exアタッカー
中盤以降の主力
2サイドを取られるリスクはあるが、攻撃性能が高い中心カード

knowledge設定:

card_id: 269
card_name: Iono’s Bellibolt ex
role: main_attacker
sub_role: stage1_ex
stage: stage1
is_ex: true
evolves_from: 268
priority: very_high
phase: early_mid
bench_score: none
search_score: very_high
energy_attach_score: very_high
attack_score: very_high
evolution_score: very_high
keep_score: very_high
discard_penalty: very_high
prize_value: 2

AI上の扱い:

Tadbulbが場にいる場合、進化を高評価する
エネルギーが付いているTadbulbから進化できるなら特に高評価
攻撃可能になるなら最優先級で進化・エネルギー添付する
メインアタッカーとして扱う
ただし1体だけに依存せず、後続TadbulbやWattrelも準備する
Ultra Ballで探す最優先候補にする

評価ルール:

Tadbulbが場にいる場合、Bellibolt exのsearch_score/evolution_scoreを高評価
進化後すぐ攻撃できる場合、進化行動を大きく加点
Bellibolt exが攻撃可能なら、攻撃アクションを高評価
Bellibolt exがすでに攻撃可能な場合、過剰なエネルギー添付は控えめにする
Bellibolt exが倒されそうな場合、後続育成を優先する

推奨スコア目安:

search_score: 95
evolution_score: 100
energy_attach_score: 95
attack_score: 100
keep_score: 95
discard_penalty: 100
main_attacker_score: 100

役割:

Iono’s Kilowattrel の進化元
サブ展開札
Belliboltラインが不十分な場合の第2プラン
ベンチに置いて次の攻撃役へつなげるカード

knowledge設定:

card_id: 270
card_name: Iono’s Wattrel
role: evolution_base
sub_role: kilowattrel_base
stage: basic
is_ex: false
evolves_to: 271
evolves_to_ex: false
priority: medium_high
phase: early
bench_score: high
search_score: medium_high
energy_attach_score: medium_high
attack_score: medium
keep_score: high
discard_penalty: high

AI上の扱い:

TadbulbやVoltorbの次点で展開する
Kilowattrelが手札にある、または山札から探せる場合は高評価
Bellibolt exラインが立たない場合のサブプランとして使う
ベンチが空いていれば置く価値がある
エネルギーを貼る対象としても一定評価する
ただしTadbulbより優先しすぎない

評価ルール:

Tadbulbがすでに場にいる場合、Wattrel展開を上げる
Kilowattrelが手札にある場合、Wattrelのbench_scoreを加点
Belliboltラインが弱い場合、Wattrelラインを第2プランとして評価
Wattrelにエネルギーを貼ることで次ターンKilowattrelの攻撃に近づくなら加点
ベンチが埋まりそうな場合は、Tadbulb / Voltorb を優先

推奨スコア目安:

bench_score: 80
search_score: 75
energy_attach_score: 70
attack_score: 50
keep_score: 75
discard_penalty: 80
evolution_base_score: 80

役割:

1進化サブアタッカー
Bellibolt exに依存しすぎないための第2アタッカー
中盤以降の継戦役

knowledge設定:

card_id: 271
card_name: Iono’s Kilowattrel
role: sub_attacker
sub_role: stage1_attacker
stage: stage1
is_ex: false
evolves_from: 270
priority: high
phase: mid
bench_score: none
search_score: high
energy_attach_score: high
attack_score: high
evolution_score: high
keep_score: high
discard_penalty: very_high

AI上の扱い:

Wattrelが場にいるなら進化候補にする
Bellibolt exが用意できない場合の重要な攻撃役として扱う
エネルギーが付いているWattrelから進化できるなら高評価
Bellibolt exが倒された後の後続として評価する
Ultra Ballで探す候補にする
雑に捨てない

評価ルール:

Wattrelが場にいる場合、Kilowattrelのsearch_score/evolution_scoreを高評価
進化後すぐ攻撃できるなら大きく加点
Bellibolt exが場にいない、または倒されそうな場合はKilowattrelの優先度を上げる
非exアタッカーとしてサイドレース上有利な場面では評価を上げる
攻撃可能なら毎ターン攻撃候補として扱う

推奨スコア目安:

search_score: 80
evolution_score: 90
energy_attach_score: 85
attack_score: 90
keep_score: 85
discard_penalty: 90
sub_attacker_score: 85

序盤のPoffin/ベンチ展開優先順位:

Iono’s Tadbulb
Iono’s Voltorb
Iono’s Wattrel

基本パターン:

Tadbulbがいない → Tadbulb最優先
TadbulbがいてVoltorbがいない → Voltorb
TadbulbとVoltorbがいる → Wattrel
Bellibolt exが手札にある → Tadbulbをさらに優先
Kilowattrelが手札にある → Wattrelの優先度を上げる
Iono’s Tadbulb → Iono’s Bellibolt ex
Iono’s Wattrel → Iono’s Kilowattrel

進化評価ルール:

進化後に攻撃可能なら最優先
進化元にエネルギーが付いているなら高評価
手札に進化先がある場合、進化元を守る・残す評価を上げる
Bellibolt exはメイン勝ち筋なので、Tadbulbがいるなら高評価
Kilowattrelはサブ勝ち筋として、Belliboltラインが弱い時に評価を上げる

Basic {L} Energy の貼り先優先順位:

このターン攻撃できるポケモン
1枚貼れば攻撃できるポケモン
Iono’s Bellibolt ex
Iono’s Tadbulb
Iono’s Kilowattrel
Iono’s Wattrel
Iono’s Voltorb
すでに十分エネルギーが付いたポケモン

注意:

電気単色なので色事故は少ない
ただし1体だけに過剰エネルギーを貼りすぎない
Bellibolt exが完成している場合は、後続のTadbulb / Wattrel / Voltorbにもエネルギーを回す
毎ターンエネルギーを貼ることを高評価する
攻撃できるポケモンを作ることを最優先する
Iono’s Bellibolt ex
Iono’s Kilowattrel
Iono’s Voltorb
その他、攻撃可能なポケモン

攻撃評価ルール:

KOできる相手がいるなら攻撃を高評価
サイドを取れるならさらに高評価
2サイド取れるexをKOできるなら最優先
攻撃可能なポケモンがいるなら、不要な準備より攻撃を優先
ただし攻撃前に進化・エネルギー添付・展開で明確に有利になる行動があるなら先に行う

捨てないカード:

Iono’s Bellibolt ex
Iono’s Tadbulb
Iono’s Kilowattrel
Iono’s Wattrel
場に進化元がいる場合の対応する進化先
後続が足りない場合のVoltorb

比較的捨ててもよいカード:

余剰のBasic {L} Energy
盤面に十分な進化ラインがある場合の余剰たね
中盤以降で役割が薄い展開札

注意:

Bellibolt exラインが1セットしかない時は、Tadbulb/Bellibolt exを捨てない
Wattrel/Kilowattrelラインが1セットしかない時も同様
エネルギーは22枚あるため、Ultra Ball等のコストにしやすい
ただし手貼り用エネルギーが手札に0枚になる捨て方は避ける

この電気デッキのポケモン別knowledgeは以下の思想で設定してください。

Iono’s Tadbulb はBellibolt exの進化元として最重要
Iono’s Bellibolt ex はメインアタッカー
Iono’s Voltorb は序盤アタッカー兼展開補助
Iono’s Wattrel はKilowattrelへの進化元
Iono’s Kilowattrel はサブアタッカー
Basic {L} Energy は攻撃に近いポケモンへ積極的に貼る
1体だけに過剰投資せず、後続アタッカーを準備する
毎ターン攻撃できる状態を最優先する


## 5. Trainer / Supporter の knowledge

knowledge設定:

card_id: 1086
card_name: Buddy-Buddy Poffin
card_type: Trainer
trainer_type: Item
role: basic_search
sub_role: early_setup
priority: very_high
phase: early
use_score: very_high
keep_score: high
search_score: none
discard_penalty: very_high

AI上の扱い:

序盤は最優先で使う
手札にある場合、基本的に温存せず使用する
ベンチが空いているなら高評価
Iono’s Tadbulb が場にいない場合は、Tadbulbを最優先で出す
Tadbulbがすでにいる場合は、Voltorb / Wattrelを展開する
ベンチが埋まりそうな場合は、TadbulbとVoltorbを優先する

Poffinで出す優先順位:

Iono’s Tadbulb
Iono’s Voltorb
Iono’s Wattrel

評価ルール:

自分の場にIono’s Tadbulbがいない場合、Poffin使用を大きく加点
手札にIono’s Bellibolt exがある場合、Tadbulbを出す価値をさらに加点
自分の場に攻撃役がいない場合、Voltorbを出す価値を加点
手札にIono’s Kilowattrelがある場合、Wattrelを出す価値を加点
ベンチが満杯の場合は使用しない
序盤にPoffinをUltra BallやLillieのコストにしない

推奨スコア目安:

use_score: 100
keep_score: 90
discard_penalty: 95
early_setup_bonus: 30
tadbulb_missing_bonus: 35
attacker_missing_bonus: 25

役割:

進化先サーチ
Iono’s Bellibolt ex / Iono’s Kilowattrel を探すカード
足りないポケモンを補うカード

knowledge設定:

card_id: 1121
card_name: Ultra Ball
card_type: Trainer
trainer_type: Item
role: evolution_search
sub_role: setup
priority: high
phase: early_mid
use_score: high
keep_score: high
discard_penalty: medium_high

AI上の扱い:

進化先が不足している時に高評価
Tadbulbが場にいる場合、Iono’s Bellibolt exを探す
Wattrelが場にいる場合、Iono’s Kilowattrelを探す
攻撃役がいない場合、攻撃可能に近いポケモンを探す
コストには余剰エネルギーや重複カードを優先する
唯一の進化ラインや重要な進化先を捨てない

探す優先順位:

Iono’s Bellibolt ex
Iono’s Kilowattrel
Iono’s Tadbulb
Iono’s Voltorb
Iono’s Wattrel

評価ルール:

Tadbulbが場にいてBellibolt exが手札にない場合、Ultra Ball使用を高評価
Wattrelが場にいてKilowattrelが手札にない場合、Ultra Ball使用を高評価
攻撃可能なポケモンを作れるなら大きく加点
手札が十分に強い場合は無理に使わない
エネルギーは多めに採用されているため、余剰Basic {L} Energyはコスト候補にしてよい
ただし手貼り用エネルギーが0枚になる捨て方は避ける

推奨スコア目安:

use_score: 90
keep_score: 80
discard_penalty: 65
search_bellibolt_score: 95
search_kilowattrel_score: 85
search_missing_basic_score: 75

役割:

手札リセット
ドロー安定札
事故回避カード
進化ラインやエネルギーへアクセスするカード

knowledge設定:

card_id: 1227
card_name: Lillie's Determination
card_type: Trainer
trainer_type: Supporter
role: draw_supporter
sub_role: hand_refresh
priority: high
phase: all
use_score: high
keep_score: medium_high
discard_penalty: medium_high

AI上の扱い:

手札が弱い時に高評価
進化先がない時に高評価
たね展開ができていない時に高評価
エネルギーしかない手札で高評価
攻撃役が作れない時に高評価
すでに必要札が揃っている場合は使用を抑制する
Supporter権を使うため、Canariと比較してより有効な方を選ぶ

使うべき場面:

手札にIono’s Bellibolt ex / Iono’s Kilowattrelがない
TadbulbやWattrelは場にいるが進化先がない
たねポケモンが少ない
手札がエネルギーに偏っている
攻撃可能なポケモンを作れない
次のアクションが少ない

使わない方がよい場面:

手札にBellibolt exがあり、Tadbulbが場にいる
手札にPoffin / Ultra Ball / 進化先 / エネルギーが揃っている
すでにこのターン攻撃準備ができている
Canariの方が明確に有効
重要カードを山札に戻してしまうリスクが高い

評価ルール:

hand_qualityが低い時に大きく加点
setup_missingが多い時に加点
進化先不足なら加点
エネルギー不足なら加点
重要カードが手札に揃っている時は減点
Supporter使用済みなら使用不可として扱う

推奨スコア目安:

use_score: 85
keep_score: 75
discard_penalty: 65
bad_hand_bonus: 30
missing_evolution_bonus: 25
hand_already_good_penalty: -25

役割:

デッキエンジン
安定化Supporter
展開・継戦補助
手札や場を整えるカード

knowledge設定:

card_id: 1233
card_name: Canari
card_type: Trainer
trainer_type: Supporter
role: engine_supporter
sub_role: stability
priority: high
phase: all
use_score: high
keep_score: medium_high
discard_penalty: medium

AI上の扱い:

安定化Supporterとして高評価
盤面が弱い時に使用を検討する
攻撃役・進化先・エネルギーが不足している時に高評価
Lillieと同じSupporter枠なので、手札状況に応じて比較する
すでに盤面が完成している場合は優先度を下げる

使うべき場面:

たね展開が足りない
進化先が足りない
攻撃役が用意できていない
後続アタッカーがいない
手札の選択肢が少ない
中盤以降で継戦札が必要

使わない方がよい場面:

すでに攻撃可能なアタッカーがいて、他の行動で十分
Lillieの方が手札改善に向いている
このターンBoss系や別Supporterが必要な場合
Supporter使用済み

評価ルール:

setup不足時に加点
後続不足時に加点
攻撃役がいない時に加点
hand_qualityが低い時に加点
盤面が完成している時は減点
Supporter権の使用価値を比較する

推奨スコア目安:

use_score: 85
keep_score: 75
discard_penalty: 60
setup_missing_bonus: 25
no_attacker_bonus: 25
follow_up_attacker_missing_bonus: 20

役割:

スタジアムエンジン
展開安定札
Iono’s系の動きを支える場カード

knowledge設定:

card_id: 1254
card_name: Levincia
card_type: Trainer
trainer_type: Stadium
role: engine_stadium
sub_role: lightning_engine
priority: high
phase: all
use_score: high
keep_score: medium
discard_penalty: medium

AI上の扱い:

序盤から中盤にかけて高評価
場にスタジアムがないなら使用を検討する
相手の有利なスタジアムを上書きできるなら加点
自分の展開や攻撃準備に役立つ場合は高評価
すでに自分のLevinciaが場にある場合、重複使用はしない
手札に複数ある場合は1枚をコストにしてよい

使うべき場面:

自分の場にスタジアムがない
相手のスタジアムを上書きしたい
序盤の展開が弱い
手札が細い
進化ラインやエネルギーへアクセスしたい
継続的なエンジンが必要

使わない方がよい場面:

すでにLevinciaが場にある
使っても盤面が変わらない
手札コストとして使った方が有効
他の行動で攻撃準備が完了する

評価ルール:

自分のスタジアムが場にない場合に加点
相手スタジアムを上書きできる場合に加点
序盤は高評価
中盤以降は盤面不足時に評価
重複Levinciaはコスト候補

推奨スコア目安:

use_score: 80
keep_score: 65
discard_penalty: 50
no_stadium_bonus: 20
counter_stadium_bonus: 20
duplicate_penalty: -15

役割:

Supporter回収
Lillie's Determination / Canari へのアクセス補助
中盤以降の安定化カード

knowledge設定:

card_id: 1152
card_name: Poké Pad
card_type: Trainer
trainer_type: Item
role: supporter_recovery
sub_role: consistency
priority: medium
phase: all
use_score: medium
keep_score: medium
discard_penalty: low_medium

AI上の扱い:

Supporterが不足している場合に評価
トラッシュに有効なSupporterがある場合に高評価
Lillie / Canariを戻せるなら評価
序盤で他に強い展開札がある場合は優先度低め
手札が強い場合は無理に使わない
余剰ならUltra Ball等のコスト候補

使うべき場面:

トラッシュにLillie's Determinationがある
トラッシュにCanariがある
次ターン以降のSupporterが不足している
手札が細く、Supporterへアクセスしたい
中盤以降で継戦したい

使わない方がよい場面:

トラッシュに有効なSupporterがない
現在の手札で十分動ける
ほかの展開札を先に使うべき
序盤でPoffin / Ultra Ball / Energy attachが優先される

評価ルール:

トラッシュにSupporterがある場合に加点
次ターンのSupporterがない場合に加点
中盤以降で評価を上げる
序盤はPoffinやUltra Ballより低評価
有効対象がない場合は低評価

推奨スコア目安:

use_score: 65
keep_score: 55
discard_penalty: 40
supporter_in_discard_bonus: 25
no_supporter_next_turn_bonus: 15
no_target_penalty: -30

役割:

ポケモン回収
倒された進化ラインの復帰
後続アタッカーの再利用
中盤以降のリソース補助

knowledge設定:

card_id: 1097
card_name: Night Stretcher
card_type: Trainer
trainer_type: Item
role: pokemon_recovery
sub_role: resource_recovery
priority: medium_high
phase: mid_late
use_score: medium_high
keep_score: medium
discard_penalty: medium

AI上の扱い:

序盤は温存寄り
トラッシュに重要ポケモンがある時に高評価
Bellibolt ex / Tadbulb / Kilowattrel / Wattrel を戻す
後続アタッカー不足時に高評価
盤面が十分なら無理に使わない

戻す優先順位:

Iono’s Bellibolt ex
Iono’s Tadbulb
Iono’s Kilowattrel
Iono’s Wattrel
Iono’s Voltorb

使うべき場面:

メインアタッカーが倒された
Bellibolt exラインが不足している
後続アタッカーがいない
トラッシュに重要進化先がある
中盤以降でリソースを戻す必要がある

使わない方がよい場面:

トラッシュに重要ポケモンがない
序盤でまだ回収対象がない
手札や場に十分な後続がある
今使っても盤面が改善しない

評価ルール:

Bellibolt exがトラッシュにある場合に加点
Tadbulb不足時にTadbulb回収を加点
後続アタッカー不足時に加点
有効対象がない場合は低評価
序盤は使用を抑制

推奨スコア目安:

use_score: 75
keep_score: 65
discard_penalty: 55
recover_main_attacker_bonus: 30
recover_evolution_base_bonus: 25
no_target_penalty: -35

役割:

リソース回復
ポケモン・エネルギーの山札戻し
長期戦の継戦補助
デッキ切れ・リソース切れ対策

knowledge設定:

card_id: 1110
card_name: Max Rod
card_type: Trainer
trainer_type: Item
role: resource_recovery
sub_role: deck_recovery
priority: medium
phase: mid_late
use_score: medium
keep_score: medium
discard_penalty: low_medium

AI上の扱い:

序盤は基本的に温存
中盤以降、トラッシュに重要ポケモンやエネルギーが多い時に使う
エネルギーが大量に落ちている場合に評価
Bellibolt ex / Kilowattrel / 進化元を戻す価値がある
山札に戻すため、即手札に欲しい場合はNight Stretcher等と比較する

戻す優先対象:

Iono’s Bellibolt ex
Iono’s Tadbulb
Iono’s Kilowattrel
Iono’s Wattrel
Basic {L} Energy
Iono’s Voltorb

使うべき場面:

トラッシュに重要ポケモンが複数ある
エネルギーが多く落ちている
後続アタッカーが不足している
山札リソースを回復したい
終盤に攻撃継続が必要

使わない方がよい場面:

序盤でトラッシュが少ない
戻す対象が弱い
今すぐ必要なカードを山札に戻すだけで終わる
手札に戻す方が強い局面

評価ルール:

トラッシュの重要カード枚数が多いほど加点
エネルギーが多く落ちている場合に加点
Bellibolt exラインが落ちている場合に加点
序盤は低評価
有効対象が少ない場合は使わない

推奨スコア目安:

use_score: 70
keep_score: 60
discard_penalty: 45
many_resources_in_discard_bonus: 25
energy_recovery_bonus: 20
early_game_penalty: -25

役割:

雷エネルギー回収
攻撃継続補助
手貼り用エネルギー確保
中盤以降の息切れ防止

knowledge設定:

card_id: 1118
card_name: Energy Retrieval
card_type: Trainer
trainer_type: Item
role: energy_recovery
sub_role: lightning_energy_recovery
priority: medium_high
phase: mid_late
use_score: medium_high
keep_score: medium
discard_penalty: medium

AI上の扱い:

序盤は無理に使わない
トラッシュにBasic {L} Energyがある場合に評価
手札にエネルギーがない時に高評価
次の攻撃役にエネルギーを貼りたい時に高評価
攻撃継続に必要なら使用する
手札に十分エネルギーがある場合は使わない

使うべき場面:

手札にBasic {L} Energyがない
トラッシュにBasic {L} Energyが2枚以上ある
このターン手貼りしたい
次の攻撃役を育てたい
攻撃継続に必要
中盤以降でエネルギーが不足している

使わない方がよい場面:

トラッシュにエネルギーがない
手札に十分エネルギーがある
序盤でまだ必要ない
使ってもこのターンの行動が改善しない

評価ルール:

手札エネルギー0枚なら大きく加点
トラッシュに雷エネルギー2枚以上なら加点
攻撃可能化に直接つながるなら大きく加点
すでに手札エネルギーが多いなら減点
トラッシュ対象なしなら使用不可に近い評価

推奨スコア目安:

use_score: 75
keep_score: 60
discard_penalty: 55
no_energy_in_hand_bonus: 30
two_energy_in_discard_bonus: 25
attack_enable_bonus: 30
no_target_penalty: -40

序盤:

Buddy-Buddy Poffin
Ultra Ball
Levincia
Lillie's Determination
Canari
Poké Pad
Night Stretcher
Max Rod
Energy Retrieval

中盤:

攻撃を成立させるUltra Ball / Energy Retrieval
Lillie's Determination / Canari
Levincia
Night Stretcher
Poké Pad
Max Rod
余剰Poffin

終盤:

サイド取得に直結するカード
Energy Retrieval
Night Stretcher
Max Rod
Lillie's Determination / Canari
Poké Pad
Levincia

Lillie's Determinationを優先する場面:

手札全体が弱い
必要札が複数足りない
進化先がない
エネルギーがない
たね展開が弱い

Canariを優先する場面:

盤面や継戦を整えたい
後続アタッカーが不足している
Lillieで重要札を戻したくない
現在の手札をある程度維持したい
中盤以降の安定化をしたい

Supporterを使わない場面:

すでに攻撃準備が完了している
Poffin / Ultra Ball / Energy attach / Evolution で十分動ける
手札に重要札が揃っている
Supporter使用で手札の質が下がる可能性が高い

Poffin:

序盤最優先
ベンチが空いているなら基本使用
Tadbulb / Voltorb / Wattrelを並べる

Ultra Ball:

進化先を探す
Bellibolt ex最優先
次点でKilowattrel
コストは余剰エネルギー優先

Energy Retrieval:

エネルギー不足時に使う
攻撃継続に直結するなら高評価

Night Stretcher:

倒されたアタッカーや進化ラインを戻す
中盤以降に評価

Max Rod:

複数リソースが落ちた時に使う
序盤は低評価

Poké Pad:

有効なSupporterがトラッシュにある時に評価
序盤はPoffin/Ultra Ballより低評価

Ultra Ball等のコストにしやすいカード:

余剰Basic {L} Energy
2枚目以降のLevincia
序盤以降の余剰Poffin
対象がないEnergy Retrieval
対象がないNight Stretcher
対象がないPoké Pad
重複したSupporter

捨てないカード:

唯一のBuddy-Buddy Poffin
必要なUltra Ball
手札が弱い時のLillie's Determination
後続不足時のCanari
有効な進化先を探せるカード
手貼り用最後のBasic {L} Energy

注意:

エネルギーは22枚あるためコストにしやすい
ただし手貼り用エネルギーを0枚にしない
Bellibolt exラインが揃っていない時はUltra Ballを大切にする
序盤のPoffinは捨てない
Supporterは1ターン1回なので、使用価値を比較する

Trainer / Supporter knowledge の基本思想:

Buddy-Buddy Poffinは序盤最重要
Ultra BallはBellibolt ex / Kilowattrelを探す
Lillie's Determinationは手札事故回避
Canariは安定化と継戦補助
LevinciaはエンジンStadium
Energy Retrievalは中盤以降の攻撃継続
Night Stretcherは倒された進化ラインの復帰
Max Rodは長期戦のリソース回復
Poké PadはSupporter再利用
序盤は展開、以降は毎ターン攻撃と後続準備を優先する

### サポーター制限 (1ターン1枚)

- supporter_played チェックが必要: `sub_role = "supporter"`
- 対象: Lillie's Determination (1227), Canari (1233)

---

## 6. エネルギーの knowledge

role: main_energy
phase: all
keep_score: medium
energy_attach_score: very_high
discard_penalty: low_medium

### エネルギー付与の考え方

1. このターン攻撃できるポケモン
2. 1枚貼れば攻撃できるポケモン
3. 進化後に攻撃役になるポケモン
4. エネルギー付きの進化元
5. 後続アタッカー

---

## 7. エネルギー添付ロジック

電気デッキでは、エネルギーの色判定は基本的に単純です。

使用するエネルギーは Basic {L} Energy、カードID=4 を中心に扱います。

このデッキでは、Basic {L} Energy を貼る目的を以下の4つに分けます。

1. このターン攻撃可能にする
2. 次ターン攻撃可能に近づける
3. Iono’s Voltorb の打点を上げる
4. 後続アタッカーを育てる

Iono’s Voltorb は攻撃役として扱います。

Voltorbは序盤から攻撃できるポケモンであり、場のIono’sポケモン全体についている雷エネルギー枚数により打点が伸びるため、Voltorbへのエネルギー添付は有益です。

ただし、Voltorb本人に3枚以上エネルギーを集中させるより、Tadbulb / Bellibolt ex / Wattrel / Kilowattrel に分散した方が、後続育成とVoltorbの打点上昇を両立しやすくなります。

そのため、Voltorbへの1枚目・2枚目は高評価、3枚目以降は状況次第で過剰添付として減点します。

### 基本方針

Basic {L} Energy の貼り先優先順位:

1. この添付で攻撃可能になるポケモン
2. 1枚貼れば次ターン攻撃可能に近づくポケモン
3. Iono’s Voltorb
4. Iono’s Bellibolt ex
5. Iono’s Kilowattrel
6. Iono’s Tadbulb
7. Iono’s Wattrel
8. すでに十分エネルギーが付いているポケモン

注意:

* 毎ターンエネルギーを貼ることを高評価する
* 攻撃できるポケモンを作ることを最優先する
* 1体だけに過剰投資しない
* Bellibolt exが完成している場合は、後続のTadbulb / Wattrel / Voltorbにもエネルギーを回す
* Voltorbの打点は、Iono’sポケモン全体の雷エネルギー枚数で伸びる
* 非Iono’sポケモンには基本的に貼らない

### 付けてよいポケモン

| エネルギー          | 対象                         | 基本スコア | 理由                                     |
| -------------- | -------------------------- | ----- | -------------------------------------- |
| ID=4 Lightning | ID=265 Iono’s Voltorb      | +18   | 序盤アタッカー。2エネで攻撃可能になり、テンポを取れる            |
| ID=4 Lightning | ID=268 Iono’s Tadbulb      | +12   | Bellibolt exへ進化後に引き継ぎ、エネルギー加速エンジン準備になる |
| ID=4 Lightning | ID=269 Iono’s Bellibolt ex | +20   | エネルギー加速エンジン兼大型アタッカー。攻撃準備にもなる           |
| ID=4 Lightning | ID=270 Iono’s Wattrel      | +10   | Kilowattrelへ進化後に引き継ぐ                   |
| ID=4 Lightning | ID=271 Iono’s Kilowattrel  | +18   | サブアタッカー。攻撃と手札補助の準備になる                  |

### 条件付き加点

| 条件                          | 加点  | 理由                        |
| --------------------------- | --- | ------------------------- |
| この添付で攻撃可能になる                | +35 | 最優先。即攻撃につながる              |
| この添付で次ターン攻撃可能に近づく           | +25 | 次ターンの攻撃準備になる              |
| ActiveのVoltorbが2エネ未満        | +25 | Voltorbを攻撃可能にする           |
| 場に攻撃可能ポケモンがいない              | +20 | まず攻撃役を作る                  |
| Bellibolt exが場にいて、手札に雷エネが多い | +15 | エネルギー加速でVoltorb打点を伸ばせる    |
| 後続アタッカーがいない                 | +15 | 1体目が倒された後の保険になる           |
| Iono’sポケモン全体の雷エネ数が少ない       | +10 | Voltorbの打点が不足している         |
| 進化元に貼ることで進化後すぐ攻撃に近づく        | +15 | Tadbulb / Wattrel の価値を上げる |

### 過剰添付として減点するケース

| エネルギー / 対象                         | スコア | 理由                                         |
| ---------------------------------- | --- | ------------------------------------------ |
| Lightning → Voltorb 3枚目以降          | -10 | Voltorb本人は2エネで攻撃可能。3枚目以降は他のIono’sポケモンへ回したい |
| Lightning → Voltorb 3枚目以降、かつ後続が未準備 | -20 | 後続育成を阻害する                                  |
| Lightning → Bellibolt ex 5枚目以降     | -10 | 攻撃に必要な枚数を超えやすい                             |
| Lightning → Kilowattrel 4枚目以降      | -10 | 攻撃に必要な枚数を超えやすい                             |
| Lightning → すでに十分エネルギーがあるポケモン      | -10 | 攻撃成立に寄与しにくい                                |
| Lightning → 倒されそうな低HPポケモン          | -15 | エネルギー損失リスクが高い                              |
| Lightning → 非Iono’sポケモン            | -20 | Voltorbの打点上昇に寄与しない                         |

### Voltorbへのエネルギー添付ルール

| 状況                         | スコア | 理由                     |
| -------------------------- | --- | ---------------------- |
| Voltorb 0エネ → 1エネ          | +18 | 序盤アタッカー準備              |
| Voltorb 1エネ → 2エネ          | +35 | 攻撃可能になるため高評価           |
| Voltorb 2エネ以上 → 追加         | -10 | 基本は過剰。ほかのIono’sポケモンへ回す |
| Voltorb 2エネ以上 → 追加、かつ後続未準備 | -20 | 後続育成を優先する              |

### Any → Voltorb の扱い

「Any → Voltorb は有害」という扱いはしません。

Voltorbは攻撃役です。

ただし、Lightning以外のエネルギーや、Voltorbへの3枚目以降のエネルギー添付は状況次第で過剰として扱います。

結論:

* Lightning → Voltorb 1枚目: 有益
* Lightning → Voltorb 2枚目: 高評価
* Lightning → Voltorb 3枚目以降: 原則低評価
* 後続未準備ならVoltorbへの追加エネルギーはさらに減点

---

## 攻撃可能判定

攻撃可能判定は、まずゲーム側が提示する合法手を最優先します。

select.option に Attack があり、remainEnergyCost が 0 なら攻撃可能と判定します。

カードIDごとの固定エネルギー条件は fallback としてのみ使います。

### 基本方針

```python
def can_attack_now(pokemon, state, select=None):
    # 1. 最優先: 環境が提示する合法手で判定
    if select is not None:
        if pokemon_is_active(pokemon, state):
            for opt in select.get("option", []):
                if opt.get("type") == "Attack":
                    if select.get("remainEnergyCost", 0) == 0:
                        return True

    # 2. fallback: knowledge上の攻撃必要エネ数で判定
    return can_attack_by_energy_count(pokemon)
```

### fallback用の攻撃条件

電気単色なので、基本的には雷エネルギー枚数で近似します。

```python
LIGHTNING = 4

ATTACK_REQUIREMENTS = {
    265: {
        "name": "Iono's Voltorb",
        "required_total_energy": 2,
        "required_lightning_energy": 0,
        "role": "early_main_attacker",
    },
    269: {
        "name": "Iono's Bellibolt ex",
        "required_total_energy": 4,
        "required_lightning_energy": 3,
        "role": "engine_attacker",
    },
    271: {
        "name": "Iono's Kilowattrel",
        "required_total_energy": 3,
        "required_lightning_energy": 1,
        "role": "sub_attacker",
    },
}
```

注意:

* Voltorbは攻撃コスト自体は無色2個なので、雷エネルギー2枚で攻撃可能と近似してよい
* Voltorbの打点は、自分のIono’sポケモン全体についている雷エネルギー枚数で上がる
* Bellibolt exは攻撃後に次の自分の番に攻撃できない制約があるため、可能なら合法手ベースで判定する
* Kilowattrelは攻撃だけでなく、手札補助の役割も持つ

---

## Voltorb打点評価ロジック

Iono’s Voltorb の攻撃評価では、自分のIono’sポケモン全体についている雷エネルギー枚数を評価します。

```python
IONO_POKEMON_IDS = {265, 268, 269, 270, 271}
LIGHTNING = 4

def count_lightning_on_iono_pokemon(state):
    total = 0

    for p in own_active_and_bench(state):
        cid = int(p.get("id") or p.get("card_id"))
        if cid not in IONO_POKEMON_IDS:
            continue

        energy_types = p.get("energy_types") or p.get("energies") or []
        for e in energy_types:
            if int(e) == LIGHTNING:
                total += 1

    return total


def estimate_voltorb_damage(state):
    lightning_count = count_lightning_on_iono_pokemon(state)
    return 20 + 20 * lightning_count
```

### Voltorb攻撃評価

```python
def score_voltorb_attack(state, target):
    damage = estimate_voltorb_damage(state)
    score = 0
    reason = []

    score += damage * 0.1
    reason.append("voltorb_scaling_damage")

    if can_ko(target, damage):
        score += 40
        reason.append("voltorb_can_ko")

    if target.get("is_ex"):
        score += 20
        reason.append("target_ex")

    if count_lightning_on_iono_pokemon(state) >= 5:
        score += 15
        reason.append("high_iono_energy_count")

    return score, "|".join(reason)
```

---

## Bellibolt ex エネルギー加速ロジック

Iono’s Bellibolt ex が場にいる場合、手札のBasic {L} EnergyをIono’sポケモンへ付ける行動を高評価します。

ただし、1体だけに集中しすぎず、以下の優先度で分配します。

### Bellibolt ex のエネルギー加速先優先順位

1. Active Voltorb が2エネ未満なら Voltorb
2. 攻撃可能に近い Kilowattrel
3. 攻撃可能に近い Bellibolt ex
4. 後続のTadbulb
5. 後続のWattrel
6. Voltorb打点を伸ばすためのIono’sポケモン
7. すでに十分エネルギーが付いたポケモンは後回し

```python
def score_bellibolt_energy_attach(energy_cid, target, state):
    score = 0
    reason = []

    target_id = int(target.get("id") or target.get("card_id"))
    energy_count = len(target.get("energies") or target.get("energy_types") or [])

    if energy_cid != 4:
        return -20, "not_lightning_energy"

    if target_id not in IONO_POKEMON_IDS:
        return -20, "not_iono_pokemon"

    if target_id == 265:
        if energy_count < 2:
            score += 35
            reason.append("enable_voltorb_attack")
        else:
            score -= 10
            reason.append("avoid_over_attach_voltorb")

    elif target_id == 271:
        if energy_count < 3:
            score += 22
            reason.append("prepare_kilowattrel_attack")
        else:
            score -= 10
            reason.append("avoid_over_attach_kilowattrel")

    elif target_id == 269:
        if energy_count < 4:
            score += 22
            reason.append("prepare_bellibolt_attack")
        else:
            score -= 10
            reason.append("avoid_over_attach_bellibolt")

    elif target_id == 268:
        score += 14
        reason.append("prepare_bellibolt_base")

    elif target_id == 270:
        score += 12
        reason.append("prepare_kilowattrel_base")

    # Voltorbの打点上昇としての価値
    score += 8
    reason.append("increase_voltorb_damage")

    return score, "|".join(reason)
```

---

## 8. 攻撃・ターゲット方針

### 攻撃優先ターゲット

1. 今KOできる相手
2. 2サイド取れるex
3. エネルギーが多く付いている相手
4. 次ターン攻撃してきそうな相手
5. 低HPの進化元
6. ベンチの弱いポケモン
7. HPが高く、今倒せない大型ポケモン

### このデッキ側の攻撃優先順位

1. Iono’s Voltorb
2. Iono’s Bellibolt ex
3. Iono’s Kilowattrel

理由:

* Voltorbは非exであり、場のIono’sポケモン全体の雷エネ数で打点が伸びる
* Bellibolt exはエネルギー加速エンジンであり、大型アタッカーでもある
* Kilowattrelはサブアタッカー兼手札補助

### 攻撃評価ルール

* Voltorbが攻撃可能で、KOできるなら高評価
* Voltorbの推定打点が高いなら攻撃を高評価
* Bellibolt exは高打点だが、攻撃後制約があるため、合法手に出ている場合のみ攻撃候補にする
* Kilowattrelはサブアタッカーとして評価
* 攻撃前にBellibolt exのエネルギー加速でVoltorb打点を伸ばせるなら、加速後に攻撃する
* KOできるなら攻撃を優先
* ただし攻撃前に進化・エネルギー加速・手貼りで明確に打点が伸びるなら、先に実行する

### ターゲットスコアリング

```python
def score_attack_target(target, state, estimated_damage):
    score = 0
    reason = []

    prizes = 2 if target.get("is_ex") else 1
    hp = target.get("hp", target.get("remaining_hp", 0))
    energy_count = len(target.get("energies") or target.get("energy_types") or [])

    if estimated_damage >= hp:
        score += 1000 * prizes
        reason.append("can_take_prize")

    if target.get("is_ex") and estimated_damage >= hp:
        score += 500
        reason.append("ko_ex_target")

    if energy_count >= 2:
        score += 150
        reason.append("target_has_energy")

    if hp <= 70 and estimated_damage >= hp:
        score += 200
        reason.append("easy_low_hp_ko")

    if target.get("stage") == "basic" and target.get("evolves_to_ex"):
        score += 150
        reason.append("remove_ex_evolution_base")

    if estimated_damage < hp and target.get("is_ex") and hp > 180:
        score -= 100
        reason.append("avoid_unfinished_big_ex")

    return score, "|".join(reason)
```

---

## 9. AIの行動優先度

### 行動優先順位

1. ゲームエンドKOが可能なら攻撃
2. 攻撃前にBellibolt exのエネルギー加速でKO可能になるなら、先にエネルギー加速
3. 2枚プライズが取れるKOが可能なら攻撃
4. Voltorbが攻撃可能で打点が十分なら攻撃
5. Bellibolt exへ進化できるなら進化
6. Kilowattrelへ進化できるなら進化
7. PoffinでTadbulb / Voltorb / Wattrelを展開
8. Ultra BallでBellibolt ex / Kilowattrelを探す
9. Basic {L} Energyを攻撃に近いIono’sポケモンへ貼る
10. Lillie's Determination / Canari / Levinciaで手札と盤面を整える
11. Energy Retrieval / Night Stretcher / Max Rodで継戦
12. End

### セットアップ優先順位

初期Active:

1. Iono’s Voltorb
2. Iono’s Wattrel
3. Iono’s Tadbulb

理由:

* Voltorbは序盤アタッカーとして使える
* Wattrelは進化元だが、Kilowattrelに進化できる
* TadbulbはBellibolt exの進化元なので、できればベンチで守りたい

ベンチ展開:

1. Iono’s Tadbulb
2. Iono’s Voltorb
3. Iono’s Wattrel

理由:

* TadbulbはBellibolt exに進化するため最重要
* Voltorbは序盤攻撃役
* WattrelはKilowattrelへのサブライン

### Poffin使用時の優先順位

基本:

1. Tadbulb
2. Voltorb
3. Wattrel

条件付き:

* ActiveにVoltorbがいない → Voltorbを高評価
* 手札にBellibolt exがある → Tadbulbを高評価
* 手札にKilowattrelがある → Wattrelを高評価
* ベンチにTadbulbが0体 → Tadbulb最優先
* ベンチに攻撃役が0体 → Voltorb優先

---

## 10. 実装チェックリスト (デッキ切り替え時の確認手順)

> デッキをIono's Kilowattrel電気デッキへ切り替える際に変更・確認が必要なファイルと手順。

### Step 1: deck.csv 確認

完了条件:

- [x] 合計 60枚
- [x] Iono's Voltorb (265) × 3
- [x] Iono's Tadbulb (268) × 3
- [x] Iono's Bellibolt ex (269) × 3
- [x] Iono's Wattrel (270) × 3
- [x] Iono's Kilowattrel (271) × 3
- [x] Basic Lightning Energy (ID=4) × 22
- [x] ACE SPEC なし

### Step 2: data/deck_profile.json 更新

完了条件:

- [x] `deck_id` を `"ionos_kilowattrel"` に更新
- [x] `primary_win_condition` を `"Iono's Voltorb scales damage via total Lightning on Iono's Pokemon; Bellibolt ex accelerates energy; take prizes before opponent sets up"` に更新
- [x] `main_attackers: [265, 269]`
- [x] `sub_attackers: [271]`
- [x] `setup_cards: [268, 270]`
- [x] `energy_engine: [269]`

### Step 3: data/card_knowledge.csv 登録

完了条件:

- [x] 265 Iono's Voltorb — `role=basic_attacker`, `bench_score=9`, `energy_attach_score=9`
- [x] 268 Iono's Tadbulb — `role=evolution_base`, `bench_score=9`, `energy_attach_score=8`, `evolution_score=9`
- [x] 269 Iono's Bellibolt ex — `role=main_attacker`, `ex=true`, `energy_attach_score=9`, `evolution_score=10`
- [x] 270 Iono's Wattrel — `role=evolution_base`, `bench_score=8`, `energy_attach_score=7`
- [x] 271 Iono's Kilowattrel — `role=sub_attacker`, `energy_attach_score=8`, `evolution_score=9`
- [x] 4 Basic Lightning Energy — `role=main_energy`, `priority=high`, `energy_attach_score=9`, `keep_score=5`, `search_score=7`
- [x] 1086 Buddy-Buddy Poffin — `role=basic_search`
- [x] 1097 Night Stretcher — `role=pokemon_recovery`
- [x] 1110 Max Rod — `role=resource_recovery`
- [x] 1118 Energy Retrieval — `role=energy_recovery`
- [x] 1121 Ultra Ball — `role=evolution_search`
- [x] 1152 Poké Pad — `role=supporter_recovery`
- [x] 1227 Lillie's Determination — `role=draw` (sub_role=supporter)
- [x] 1233 Canari — `role=draw` (sub_role=supporter)
- [x] 1254 Levincia — `role=engine_stadium`

### Step 4: agent/ionos_rules.py 作成

完了条件:

- [x] ファイル `agent/ionos_rules.py` を作成
- [x] カードID定数を定義

  ```python
  _VOLTORB = "265"
  _TADBULB = "268"
  _BELLIBOLT_EX = "269"
  _WATTREL = "270"
  _KILOWATTREL = "271"
  _LIGHTNING_ENERGY = "4"
  IONO_POKEMON_IDS = {265, 268, 269, 270, 271}
  ```

- [x] 以下の関数を実装:
  - `is_iono_pokemon(cid) -> bool`
  - `is_lightning_energy(cid) -> bool`
  - `count_lightning_on_iono_pokemon(state) -> int`
  - `estimate_voltorb_damage(state) -> int`
  - `score_voltorb_attack(state, target) -> tuple[float, str]`
  - `score_energy_attachment(energy_cid, target_cid, state) -> tuple[float, str]`
  - `score_bellibolt_energy_attach(energy_cid, target, state) -> tuple[float, str]`
  - `score_bonus(action, state, knowledge) -> tuple[float, str]`

### Step 5: score_energy_attachment 実装

実装すべきスコア表:

| 対象 (target_cid) | 条件 | スコア |
|-----------------|------|-------|
| 265 Voltorb | 0 → 1エネ | +18 |
| 265 Voltorb | 1 → 2エネ (攻撃可能化) | +35 |
| 265 Voltorb | 2エネ以上 → 追加 | -10 |
| 265 Voltorb | 2エネ以上 → 追加、後続未準備 | -20 |
| 269 Bellibolt ex | <4エネ | +20 |
| 269 Bellibolt ex | ≥4エネ | -10 |
| 271 Kilowattrel | <3エネ | +18 |
| 271 Kilowattrel | ≥3エネ | -10 |
| 268 Tadbulb | (常時) | +12 |
| 270 Wattrel | (常時) | +10 |
| 非Iono'sポケモン | (常時) | -20 |
| 全Iono'sポケモン | (常時、Voltorb打点上昇) | +5 |

完了条件:

- [x] 上記スコア表を実装
- [x] 非Lightning EnergyはすべてIono'sポケモンへの添付に −20
- [x] `return (score, reason_str)` 形式で返す

### Step 6: Voltorb打点スケーリング実装

実装すべきロジック (Section「Voltorb打点評価ロジック」参照):

```python
IONO_POKEMON_IDS = {265, 268, 269, 270, 271}
LIGHTNING = 4

def count_lightning_on_iono_pokemon(state):
    total = 0
    for p in own_active_and_bench(state):
        cid = int(p.get("id") or p.get("card_id"))
        if cid not in IONO_POKEMON_IDS:
            continue
        energy_types = p.get("energy_types") or p.get("energies") or []
        for e in energy_types:
            if int(e) == LIGHTNING:
                total += 1
    return total

def estimate_voltorb_damage(state):
    return 20 + 20 * count_lightning_on_iono_pokemon(state)
```

完了条件:

- [x] `count_lightning_on_iono_pokemon(state)` が全Iono'sポケモンの雷エネ数を合計する
- [x] `estimate_voltorb_damage(state)` が `20 + 20 × 合計` を返す
- [x] `score_voltorb_attack(state, target)` がKO可能時に大きく加点する

### Step 7: score_bellibolt_energy_attach 実装

実装すべき関数 (Section「Bellibolt ex エネルギー加速ロジック」参照):

```python
def score_bellibolt_energy_attach(energy_cid, target, state):
    # energy_cidが4(Lightning)以外 → -20
    # target_idが非Iono's → -20
    # target_id == 265 (Voltorb): energy_count < 2 → +35, else -10
    # target_id == 271 (Kilowattrel): energy_count < 3 → +22, else -10
    # target_id == 269 (Bellibolt ex): energy_count < 4 → +22, else -10
    # target_id == 268 (Tadbulb): +14
    # target_id == 270 (Wattrel): +12
    # 全Iono's Lightning → +8 (Voltorb打点上昇)
    return score, reason_str
```

完了条件:

- [x] 上記ロジックを実装
- [x] `(score, reason_str)` 形式で返す

### Step 8: agent/policy.py インポート変更

完了条件:

- [x] `from agent.ionos_rules import score_bonus` に変更
- [x] 旧 `from agent.dragapult_rules import score_bonus` を削除

### Step 9: agent/turn_plan.py 更新

完了条件:

- [x] `_SETUP_MON_IDS` を更新

  ```python
  _SETUP_MON_IDS = {268, 270}  # Tadbulb, Wattrel — 純粋な進化前のみ
  ```

  ※ Voltorb (265) は序盤アタッカーなので SETUP_MON_IDS には含めない

- [x] `_ATTACK_REQUIREMENTS` を更新 (fallback用。合法手判定が優先)

  ```python
  _ATTACK_REQUIREMENTS = {265: 2, 269: 4, 271: 3}
  ```

  詳細辞書形式 (ドキュメント用参照:「攻撃可能判定」セクション):

  ```python
  ATTACK_REQUIREMENTS = {
      265: {
          "name": "Iono's Voltorb",
          "required_total_energy": 2,
          "required_lightning_energy": 0,
          "role": "early_main_attacker",
      },
      269: {
          "name": "Iono's Bellibolt ex",
          "required_total_energy": 4,
          "required_lightning_energy": 3,
          "role": "engine_attacker",
      },
      271: {
          "name": "Iono's Kilowattrel",
          "required_total_energy": 3,
          "required_lightning_energy": 1,
          "role": "sub_attacker",
      },
  }
  ```

- [x] Dragapult固有の定数・関数を削除
  - 削除済み: `_DRAGAPULT_EX_ID`, `_FIRE_TYPE`, `_PSYCHIC_TYPE`, `_DRAGAPULT_ENERGY_REQ`
  - 削除済み: `_can_dragapult_attack_now()`, `_can_dragapult_attack_with_attach()`

### Step 10: main.py 更新

完了条件:

- [x] `DECK_NAME` を `"ionos_kilowattrel"` に更新

### Step 11: build_submission.py 更新

完了条件:

- [x] `('agent/ionos_rules.py', 'agent/ionos_rules.py')` をリストに追加
- [x] `('agent/dragapult_rules.py', ...)` をリストから削除

### Step 12: Dragapult固有ロジックの削除・無効化

完了条件:

- [x] `agent/dragapult_rules.py` を `build_submission.py` のリストから除外
- [x] `agent/turn_plan.py` から Dragapult固有コードを削除 (Step 9 で実施)
- [x] `agent/policy.py` のインポートを更新 (Step 8 で実施)
- [x] `data/deck_profile.json` を Iono's Kilowattrel 用に書き換え (Step 2 で実施)
- [x] `CLAUDE.md` のエネルギー配分ルールセクションを Iono's Lightning 用に更新

### Step 13: ロギング

完了条件:

- [ ] ターン開始時に `estimate_voltorb_damage(state)` の推定値をログ出力
- [ ] Bellibolt ex のAbility使用時に加速先ポケモンと雷エネ数をログ出力
- [ ] エネルギー添付アクション時に `score_energy_attachment` のスコアと reason_str をログ出力
- [ ] `agent/logger.py` にVoltorb打点推定ログを追加

---

## 要確認だった部分の結論

### ID=4 Lightning → ID=265 Voltorb

結論:

* 付けてよい
* Voltorbは攻撃役として扱う
* 特に2枚目までは高評価
* 3枚目以降は過剰になりやすいため、ほかのIono’sポケモンへ回す

スコア:

* Voltorb 0エネ → 1エネ: +18
* Voltorb 1エネ → 2エネ: +35
* Voltorb 2エネ以上 → 追加: -10
* Voltorb 2エネ以上、後続未準備 → 追加: -20

理由:

* Voltorbは序盤から攻撃できる
* 場のIono’sポケモン全体の雷エネルギー枚数で打点が伸びる
* ただしVoltorb本人に3枚以上貼るより、Bellibolt ex / Kilowattrel / Tadbulb / Wattrelへ分散した方が後続育成と打点上昇を両立しやすい

### Any → Voltorb は有害か

結論:

* 有害ではない
* 「Any → Voltorb harmful」は削除
* 代わりに「Voltorbへの3枚目以降は状況次第で過剰」と扱う

### 攻撃可能判定

結論:

* まず合法手を使う
* fallbackとしてカードごとの必要エネ数を持つ

fallback:

* Voltorb: 2エネ
* Kilowattrel: 3エネ
* Bellibolt ex: 4エネ

### 電気デッキで最も重要な思想

* Bellibolt exは単なるアタッカーではなく、エネルギー加速エンジン
* Voltorbは序盤アタッカーかつスケーリングアタッカー
* 雷エネルギーはIono’sポケモン全体に分散してもVoltorbの打点上昇に貢献する
* 1体だけに過剰投資せず、攻撃役と後続を同時に作る
