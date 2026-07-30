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

## テスト結果

実行コマンド:

```bash
python -B -m unittest discover -s experiments -p "test_submission_sync.py" -v
```

結果: **66 tests、65 pass、1 skip、0 fail**。

### symlinkテスト1件skipの理由

`test_symlink_escaping_root_is_rejected` は、実行環境（Windowsでシンボリックリンク作成に必要な権限/Developer Modeが有効でない）でシンボリックリンクを作成できなかったため、`self.skipTest(...)` により明示的にskipされた。これは機能の失敗ではなく、環境上の制約による事前スキップである。他のcontainmentテスト（root外への相対パス拒否、通常の相対パスの受理）はskipなしで成功している。

## 実CLI結果

| コマンド | 結果 | exit code |
|---|---|---|
| `check --file params.json` | BYTE_IDENTICAL | 0 |
| `check --file deck.csv` | BYTE_IDENTICAL | 0 |
| `check --file main.py` | DIFFERENT | 1 |
| `check`（3件） | main.py DIFFERENT、他2件 BYTE_IDENTICAL | 1 |
| `check --strict`（3件） | main.py DIFFERENT、他2件 BYTE_IDENTICAL | 1 |

`main.py` の開発元とルート版の差分は、Step 7の設計時点での確認結果（PR0-A/PR0-Bのテレメトリ・リプレイ基盤が開発元にのみ存在する）と一致している。`--strict` は今回のリポジトリ状態にSEMANTICALLY_EQUIVALENTなペアが存在しないため、通常 `check` と同じ結果になった。

## SHA-256不変確認

実装前後で、次の6ファイルのSHA-256ハッシュがすべて一致することを確認した。

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

Step 8A完了時点では、`tools/submission_sync.py` と `experiments/test_submission_sync.py` は未追跡のままcommitされていなかった。Step 8Bでこれらと本文書を含む5ファイルをstageし、静的確認・再テスト後にcommit・push・PR作成を行った。PRはユーザーの明示指示によりmergeしていない。

## Step 9は未実施

Step 9（再利用可能なテンプレート抽出）はこの文書の時点では未実施である。

## 検証状態

**Verified**

read-only check-only v1の実装・66件のテスト（65 pass / 1 skip / 0 fail）・実リポジトリに対する実CLI確認・実装前後のSHA-256不変確認・Codex Final Auditorによる2回の監査（初回CHANGES_REQUIRED→修正→再監査APPROVE）を、実機で確認した。
