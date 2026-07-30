# Small implementation trial

## Step 8の目的

Step 8は、Step 7（[`design-only-trial.md`](design-only-trial.md)）でDesign Judgeが提示した統合設計のうち、安全性が高い**read-only check-only v1**だけを実際に実装し、ユーザーが明示承認した範囲を超えずに実装・テスト・監査・commit/push/PRまでを一度通しで実行できるかを確認する試行である。Step 8Aで実装・テスト・Codex Final Auditを実施し、Step 8Bで結果の文書化とcommit/push/PR作成を行った。

## 実施日

2026-07-30

## 実行環境

- sibling worktree: `pokemon_ai_step8`
- branch: `agent/step8-read-only-sync-check`
- base commit: `9a33ddc874aef4a998fc21b7e12792e71694428b`

## Step 7統合設計から承認した範囲

ユーザーは、Step 7の統合設計候補（apply機能なし・write機能なし・同期実行なし・`cg` importなし・stdlibのみ・3状態分類・`build_submission.py`と独立・root外やsymlink/reparse pointへのパス逸脱を拒否・テストは実ファイルへ書き込まない）のうち、**read-only check-only v1のみ**を承認した。将来のapply/write/sync機能の承認ではない。承認範囲は次の2ファイルの作成・編集とローカルテストに限定された。

- `tools/submission_sync.py`
- `experiments/test_submission_sync.py`

commit・push・PR作成・mergeはStep 8Aでは承認されておらず、Step 8Bで別途承認された。

## 実装内容

### CLI使用例

```bash
python tools/submission_sync.py check
python tools/submission_sync.py check --strict
python tools/submission_sync.py check --file main.py
python tools/submission_sync.py check --file deck.csv
python tools/submission_sync.py check --file params.json
```

`--file` は複数回指定可能。未指定時は3件すべてを確認する。標準ライブラリのみを使用し、リポジトリルートは `tools/submission_sync.py` 自身の場所（`Path(__file__).resolve().parents[1]`）から解決するため、実行時のカレントディレクトリに依存しない。

### 固定マッピング

正本・同期方向は決定しない。development candidate（開発元）と root submission（提出用）を対称に比較するだけである。

| logical name | development candidate | root submission |
|---|---|---|
| main.py | `experiments/agents/raging_bolt/main.py` | `main.py` |
| deck.csv | `experiments/decks/raging_bolt_ogerpon.csv` | `deck.csv` |
| params.json | `experiments/agents/raging_bolt/params.json` | `params.json` |

### 3状態分類

- **BYTE_IDENTICAL** — 生バイト列が完全一致
- **SEMANTICALLY_EQUIVALENT** — 生バイト列は異なるが、CRLF/単独CRをLFへ変換し、末尾LFが1個だけ存在するかどうかの差だけを無視した後で一致する（複数の末尾空行は同一扱いにしない）
- **DIFFERENT** — 上記のいずれでもない

比較にはraw bytesのSHA-256を使用し、出力にも表示するが、これはファイルの正当性や正本を決定するものではない。

### 通常checkと--strictの差

| classification | 通常 `check` | `check --strict` |
|---|---|---|
| BYTE_IDENTICAL | success | success |
| SEMANTICALLY_EQUIVALENT | WARN、success | drift、failure |
| DIFFERENT | drift、failure | drift、failure |

### 構造検証

比較状態と独立して、両側それぞれの軽量構造検証を行う。ゲームルール検証（カード名、同名4枚、ACE SPEC等）は行わない。

- **main.py**: UTF-8としてdecode可能、`ast.parse` が成功、top-levelに名前が `agent` の `FunctionDef`/`AsyncFunctionDef` が存在する（importや実行はしない）
- **params.json**: UTF-8としてdecode可能、`json.loads` が成功、top-levelがJSON object
- **deck.csv**: UTF-8としてdecode可能、csv標準ライブラリで読める、空行を許可しない、各行が1列だけ、各値が正の10進整数、非空行がちょうど60行

### exit code

| code | 意味 |
|---|---|
| 0 | 選択した全ファイルが成功条件を満たす |
| 1 | drift（DIFFERENT、または `--strict` 時のSEMANTICALLY_EQUIVALENT） |
| 2 | CLI usage error（argparse: 不正なsubcommand・不正な`--file`） |
| 3 | MISSING（必要ファイルが存在しない） |
| 4 | MALFORMED（UTF-8 decode不可、構文不正、agent未検出、JSON不正、JSON top-level非object、deck.csv構造不正） |
| 8 | I/O_OR_CONTAINMENT（permission error、読み取りI/Oエラー、repo root外への解決、symlink/junction/reparse pointによる想定外解決） |

複数ファイル・複数状態が同時に発生した場合の集約優先順位: `8 > 4 > 3 > 1 > 0`。argparseの usage error（exit 2）は通常のargparse動作として開始前に発生する。

### read-only境界

- write modeでの`open`、`Path.write_text`/`write_bytes`、`shutil.copy`、`os.replace`、`rename`、`unlink`、`mkdir`、リポジトリ内tempfile作成は一切ない
- 自動修正・apply・sync・copy・backup・manifest・journal・JSONレポートファイル出力はない
- 標準出力への表示のみ

### path containment（Windows/Linux対応）

- リポジトリルートのreal path（`os.path.realpath`）を取得する
- 各対象のlexical path（`os.path.abspath`での結合）とreal pathの双方でrepo root配下にあることを確認する（`os.path.commonpath` + `os.path.normcase` でプラットフォーム差を吸収）
- symlink・junction・reparse point等により想定外の場所へ解決される場合は `CONTAINMENT_ERROR`（exit 8）として拒否し、書き込み・作成は行わない
- 固定マッピング以外のパスは処理しない
- 対象ファイルが見つからない場合は `MISSING` として扱う（書き込み・作成はしない）

## テスト結果（マージ前hardening前の初回結果）

**この節はマージ前hardening前の初回結果の記録であり、最終結果ではない。** 最終結果は76 tests、74 pass、2 skip、0 failであり、詳細は本文書の「マージ前hardening（PR #209マージ前修正）」節および「検証状態」節を参照。

実行コマンド:

```bash
python -B -m unittest discover -s experiments -p "test_submission_sync.py" -v
```

初回結果（マージ前hardening前）: **66 tests、65 pass、1 skip、0 fail**。

### symlinkテスト1件skipの理由（初回結果時点）

初回結果の時点では、`test_symlink_escaping_root_is_rejected` が、実行環境（Windowsでシンボリックリンク作成に必要な権限/Developer Modeが有効でない）でシンボリックリンクを作成できなかったため、`self.skipTest(...)` により明示的にskipされた。これは機能の失敗ではなく、環境上の制約による事前スキップである。他のcontainmentテスト（root外への相対パス拒否、通常の相対パスの受理）はskipなしで成功している。マージ前hardeningでsymlinkベースのテストが1件追加され、最終的なskipは2件になった（詳細は「マージ前hardening」節を参照）。

## 実CLI結果

| コマンド | 結果 | exit code |
|---|---|---|
| `check --file params.json` | BYTE_IDENTICAL | 0 |
| `check --file deck.csv` | BYTE_IDENTICAL | 0 |
| `check --file main.py` | DIFFERENT | 1 |
| `check`（3件） | main.py DIFFERENT、他2件 BYTE_IDENTICAL | 1 |
| `check --strict`（3件） | main.py DIFFERENT、他2件 BYTE_IDENTICAL | 1 |

`main.py` の開発元とルート版の差分は、Step 7の設計時点での確認結果（PR0-A/PR0-Bのテレメトリ・リプレイ基盤が開発元にのみ存在する）と一致している。`--strict` は今回のリポジトリ状態にSEMANTICALLY_EQUIVALENTなペアが存在しないため、通常 `check` と同じ結果になった。上記5コマンドはマージ前hardening後にも再実行し、同じ結果・同じexit codeであることを確認済み。

## SHA-256不変確認

実装前後（マージ前hardening前後を含む）で、次の6ファイルのSHA-256ハッシュがすべて一致することを確認した。

- `main.py`
- `deck.csv`
- `params.json`
- `experiments/agents/raging_bolt/main.py`
- `experiments/agents/raging_bolt/params.json`
- `experiments/decks/raging_bolt_ogerpon.csv`

## Codex Final Audit結果

### 初回

Verdict: `CHANGES_REQUIRED`

- Blocker 2件（うち1件は誤検出）
- Major 5件

### 修正内容

- モジュールdocstring・コメントから「authoritative」という表現を除去し、「canonical or correct」等の言い回しへ変更
- OSErrorメッセージから絶対パスが漏洩しないよう、`strerror` のみを使うサニタイズ処理を追加
- `exists()`/`is_file()` 呼び出しを `OSError` に対して個別にtry/exceptし、IO_ERRORとして扱うよう修正
- deck.csv構造検証で `csv.Error` を捕捉し、MALFORMEDとして報告するよう修正
- exit code優先順位（`8 > 4 > 3 > 1 > 0`）を直接検証するテストを追加
- WARN・DRIFT・summary・reasonの出力内容を検証するテストを追加

### 誤検出として押し戻した事項

Codexは出力ラベル `development:` / `submission:` をBlockerとして指摘したが、これはユーザーの確定指示内に記載された出力例そのものと一致しており、根拠を示して押し戻した。同一Codex threadでの再監査により、Codex自身がこのBlocker判定を撤回した。

### codex-replyでの再監査と最終Verdict

修正内容を同一Codex threadへ`codex-reply`で提示し再監査を依頼した結果、**最終Verdict: `APPROVE`**（Blocker 0件、Major 0件）となった。

## 残存TOCTOUリスク

`resolve_and_check()` によるcontainment確認と、その後のファイル読み取りの間には、理論上のcheck-then-open競合（TOCTOU）が残る。この点はコード中にコメントで明示した上で、次の理由から今回のv1スコープでは許容とした（Codexも再監査でこの判断に同意している）。

- write/apply機能が存在しないread-only診断ツールである
- 対象はローカル単一ユーザーが自ら管理するリポジトリであり、マルチテナントの信頼境界ではない
- stdlibのみという制約下で、より低レベルなfdベースのopen+fstatシーケンスを追加することは、この段階では過剰な複雑化になる

## Evidence limitation

Codex Final Auditorはread-only監査であり、Codex自身はテスト・実CLI・Git操作・SHA-256確認を実行していない。テスト結果・実CLI結果・SHA-256不変確認・git状態は、実装者（親Claude Codeセッション）が実行した結果をCodexがコード読解によって確認したものである。

## Known Unknown

Step 7から引き継がれ、Step 8では意思決定を追加していない事項:

- `deck.csv` の正本候補が複数系統（ルート `deck.csv`、`experiments/decks/raging_bolt_ogerpon.csv`、`tools/deck_builder.py` が生成するルート `deck.csv`、`data/deck.csv`）存在する件
- `main.py` の開発元・ルート間の差分をpromote/stripする方針
- `params.json` の正本
- `CLAUDE.md` の `regulation`/`AreaType` 関連の記述と実装の不一致

これらについて、本ツールは出力に反映するのみで、判断や書き込みは一切行わない。

## 対象外（本ツールが行わないこと）

- 自動同期ツールではない
- apply機能はない
- 正本決定ツールではない
- driftを修正しない
- `main.py` の差分は修正していない
- `deck.csv`、`params.json` は変更していない
- `build_submission.py` は実行していない
- `submission.tar.gz` は作成していない
- `cg` をimportしていない
- `main.py` をimport・実行していない
- CIへの組み込みは未実施
- 将来のwrite/apply機能を承認したものではない

## commit/push/PR前の状態

Step 8A完了時点では、`tools/submission_sync.py` と `experiments/test_submission_sync.py` は未追跡のままcommitされていなかった。Step 8Bでこれらと本文書を含む5ファイルをstageし、静的確認・再テスト後にcommit・push・PR作成を行った（PR #209）。

## マージ前hardening（PR #209マージ前修正）

PR #209のマージ前に、次の3件の追加修正を行った。変更可能ファイルは `tools/submission_sync.py`・`experiments/test_submission_sync.py`・本文書のみで、README・ADR・CI・アプリコード（`main.py`/`deck.csv`/`params.json`/`build_submission.py`）は変更していない。

### 内部symlink redirect拒否

修正前の `resolve_and_check()` は、symlink/junction/reparse point解決後のreal pathが「repo root配下のどこか」であれば受理していた。これは不十分で、固定rel_path（例: `main.py`、または `experiments/agents/raging_bolt/main.py` の中間ディレクトリ）を指すsymlinkが、**リポジトリ内の別の場所にある別ファイル**（例: `experiments/agents/raging_bolt/alt/main.py`）へ静かにリダイレクトしていても、単純な「root配下か」チェックだけでは検出できなかった。

修正後は、real path解決後に「root real pathへ未解決のrel_pathを結合した期待位置」を計算し、実際のreal pathがその期待位置と**完全一致**することまで確認する。一致しない場合は `CONTAINMENT_ERROR`（exit 8）として拒否する。repo root自体がsymlinkの場合を考慮し、期待位置はroot real path基準で計算する。`os.path.normcase`/`os.path.normpath` によりWindows/Linuxの差を吸収する。

### deck.csvのstrict CSV解析

修正前は、ファイル全体の物理行リストを1回の `csv.reader()` へ渡していた。この方式には実際の欠陥があり、ある物理行で引用符が閉じられていない場合、Pythonのcsv標準ライブラリは次以降の物理行を同一の論理フィールドへ静かに継続してしまう。結果として、本来の物理行数と異なる行数のファイルが「ちょうど60行」チェックを通過してしまう可能性があった（61物理行のファイルが60論理行として誤って合格する具体例で再現・検証済み）。

修正後は、各物理行を個別に厳格解析する（`csv.reader([line], strict=True)` を1行ずつ）。これにより、単一物理行内で閉じられていない引用符・複数行にまたがる引用フィールド・複数列・空行・正の10進整数以外の値を、いずれもMALFORMED（exit 4）として検出する。通常の引用済み整数（例: `"63"`）は、CSV解析後に引用符が外れた値が正の10進整数であれば引き続き許可する。

### 不正値の非表示

修正前は、不正なdeck.csv値のreasonへ元の値そのもの（`{value!r}`）を含めていた。不正な内容は利用者・攻撃者が自由に書き込める内容であり、そのまま標準出力へ反映するのは望ましくない。修正後は、行番号のみを示し、値そのもの・先頭文字・部分文字列は一切含めない（`row {line_no} is not a positive decimal integer`）。

### 追加後のテスト総数と結果

`python -B -m unittest discover -s experiments -p "test_submission_sync.py" -v` の結果、テスト総数は **76件（74 pass / 2 skip / 0 fail）** に増加した。追加した主なテスト:

- symlinkによる内部リダイレクト拒否（実symlink作成不能な環境では明示的skip）
- `unittest.mock` で `os.path.realpath` を差し替えた、非skipの決定的な内部リダイレクト拒否テスト（最終パス要素・中間ディレクトリの両方）
- リダイレクトなしの通常ケースが引き続き受理されることを確認する回帰用テスト
- 閉じられていない引用符1件のMALFORMED化（validate_structure・CLI exit 4の双方）
- 61物理行が60論理行へ折り畳まれる回帰ケースのMALFORMED化（validate_structure・CLI exit 4の双方）
- secret風の文字列を不正値として与え、reason・PairReport相当の出力・CLI標準出力のいずれにも元の文字列が含まれないことを確認するテスト

skipは2件で、いずれも実行環境（Windows、symlink作成に必要な権限/Developer Mode制約）による明示的skipであり、機能失敗ではない。同じ安全性の性質は、`unittest.mock` を用いた非skipの決定的テストで別途検証済み。

### Final Auditor結果

修正後、Codex Final Auditorを新規read-only threadで実行した。重点確認事項（内部symlink redirect拒否、unclosed quote/multiline CSVの拒否、不正値の非表示、read-only境界維持、exit code維持、対象外変更なし）をすべて確認した上で、**最終Verdict: `APPROVE`**（Blocker 0件、Major 0件、Minor 0件）となった。Test gapとして、`PairReport` のフィールドへの直接アサーションがCLI出力経由の間接検証に留まっている点、secret文字列の完全一致以外の部分文字列レベルでの網羅までは検証していない点、正の引用済み整数の受理を明示的に確認する回帰テストがない点が指摘されたが、いずれもマージを妨げるものではないとされた。

## Step 9は未実施

Step 9（再利用可能なテンプレート抽出）はこの文書の時点では未実施である。

## 検証状態

**Verified**

read-only check-only v1の実装・Codex Final Auditorによる2回の監査（初回CHANGES_REQUIRED→修正→再監査APPROVE）・PR #209の作成、およびマージ前hardening（内部symlink redirect拒否・deck.csvのstrict CSV解析・不正値の非表示）とその追加テスト（76件、74 pass / 2 skip / 0 fail）・別スレッドでのCodex Final Auditor再監査（APPROVE）を、実機で確認した。実リポジトリに対する実CLI確認と、対象6ファイルの実装前後SHA-256不変確認も、hardening前後の双方で実施した。
