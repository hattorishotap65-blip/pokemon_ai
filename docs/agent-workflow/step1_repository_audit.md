# Step 1 現状調査結果

調査日: 2026-07-28

対象: `pokemon_card_ai`
目的: Claude CodeとCodexによるマルチエージェント開発方式を安全に追加できるか確認する

## 1. Gitの状態

現在のブランチ: `fix/tuning-panel-value-revert`

- HEAD: `67928b2`
- upstreamより5コミット先行、遅れ0
- staged: なし
- unstaged: 追跡済み6ファイルが削除扱い
- untracked: 56ファイル

### 未コミット変更

`reference/extracted/cg/`配下の以下6ファイルが削除扱いになっている。

- `__init__.py`
- `api.py`
- `game.py`
- `libcg.so`
- `sim.py`
- `utils.py`

未追跡ファイルの内訳:

- `docs/*`: 4ファイル
- `experiments/agents/raging_bolt/*`: 3ファイル
- `experiments/web/agents/**`: 42ファイル
- `experiments/web/value_dataset*`: 4ファイル
- `top_lucario`関連: 2ファイル
- `experiments/golden_canonical_hash.py`: 1ファイル

### 注意点

- `reference/extracted/cg/`はアクセス拒否も発生しているため、実際の削除かWindows側から不可視なのか確定できない。
- 未追跡ファイルが多いため、`git add .`は使用しない。
- 今後の設定追加では対象パスを明示して個別にstageする。
- 先行5コミットにはPR0-AからPR0-Cまでの監査基盤変更が含まれる。

## 2. リポジトリ構成

### 主要構成

- `main.py`、`deck.csv`、`params.json`: 現行提出用ファイル
- `experiments/agents/raging_bolt/`: 現行エージェントの開発元
- `agent/`、`data/`: 旧エージェント構成
- `experiments/`: 対戦、学習、監査、Web UI、テスト
- `experiments/test_*.py`: 実質的なテスト群
- `tools/`: データ生成、評価、提出支援
- `scripts/`: テスト・探索用シェルスクリプト
- `configs/`: ML・パラメータ探索設定
- `docs/`: 設計、進捗、実験記録、ロードマップ
- `reference/`: cabt/cg実行ライブラリ
- `logs/`、`reports/`、`artifacts/`: 生成結果
- `.github/workflows/`: CI

プロジェクトルート:

```text
<repository-root>
```

入れ子のGitリポジトリはなく、検出された`.git`はルートの1個だけ。

## 3. 既存エージェント設定

### 存在するもの

- `CLAUDE.md`
- `AGENTS.md`
- `.claude/scheduled_tasks.lock`
- `experiments/agents/raging_bolt/HANDOFF.md`

### 存在しないもの

- `CLAUDE.local.md`
- `.mcp.json`
- `.claude/agents/`
- `.claude/skills/`
- `.claude/settings.json`
- `.codex/`
- `CODEX.md`

### 各ファイルの役割

- `CLAUDE.md`: Claude Code向け永続ルール。現行Raging Bolt構成を記載。
- `AGENTS.md`: Codex向け永続ルール。ただし旧Iono's Kilowattrel構成を記載。
- `HANDOFF.md`: Raging Boltの検証結果、禁止済み施策、PR0-AからPR0-Cまでの進捗。
- `.claude/scheduled_tasks.lock`: Claude実行時の一時状態。Gitのローカル除外設定で無視されている。

### 競合の可能性

`CLAUDE.md`と`AGENTS.md`で以下が一致していない。

- 現行デッキ
- 提出構成
- エントリーポイント
- 使用するエージェント構成

さらに、`CLAUDE.md`にはビルド時にRaging Bolt側から自動反映すると記載されているが、実際の`build_submission.py`はルートの3ファイルをそのままアーカイブしている。

両ファイルを無条件に統合・上書きしてはならない。

## 4. 既存ドキュメント

### 利用できる既存資料

- `README.md`: 構成、起動、データ処理、Web UI
- `docs/phase_plan_profile_strategy.md`: フェーズ開発ルールとClaude Code実行テンプレート
- `docs/current_status.md`: 過去の実装・検証状況
- `experiments/agents/raging_bolt/HANDOFF.md`: 現在のRaging Bolt進捗
- `docs/experiments/`: 実験単位の設計・結果
- `docs/instructions/`: 過去の実装依頼・PDCA手順
- 性能改善メモ・診断ロードマップ

### 新しいワークフロー文書と重複しそうな資料

- `phase_plan_profile_strategy.md`のClaude Code実行テンプレート
- `HANDOFF.md`の引き継ぎ方式
- 性能改善メモ内の「Codexへ渡す依頼」
- ChatGPT提案メモ内の「Claude Codeへ渡す依頼例」
- `docs/instructions/`の作業依頼形式

新しい`agent-workflow`文書では、アプリの性能改善案を複製せず、役割分担、成果物形式、レビュー手順だけを扱う。

## 5. 開発・検証方法

### 使用技術

- 主言語: Python 3
- 補助: Bash、HTML、JavaScript
- Web: Python標準ライブラリ`http.server`
- シミュレータ: Linux共有ライブラリ`cg/libcg.so`
- パッケージ管理: `pip`
- 依存定義: `tools/requirements.txt`

統一された`pyproject.toml`やlockファイルはない。

### 起動

```bash
python3 experiments/web/launch.py
python3 experiments/web/launch.py --port 8001
```

### 対戦・分析

```bash
python experiments/run_matches.py --n 100
python experiments/analyze_logs.py
```

### テスト

```bash
bash scripts/run_all_tests.sh
```

ただし、このスクリプトが実行するテストは29件で、CIは57件のテストと追加CLI smoke testを実行する。CIのほうが検証範囲が広い。

### Lint・型チェック

- Ruff、Flake8、Black等のLint設定・コマンドは確認できなかった。
- mypy、Pyright等の型チェック設定・コマンドは確認できなかった。

### 主な実行環境

WSL/Linuxが主な実行環境。

- READMEにWSL想定と記載
- `libcg.so`を使用
- Bashスクリプトを使用
- CIはUbuntu
- WindowsはIDE・ブラウザ側として利用

## 6. 秘密情報とGit管理

### 調査結果

- 追跡済み・作業ツリー内に`.env`、秘密鍵、認証JSONは検出されなかった。
- APIキーの実値は検出されなかった。
- `PTCG_API_KEY`は環境変数として受け取る設計。
- READMEの`YOUR_KEY`はプレースホルダー。

### 注意点

- ルート`.gitignore`は`.env`、認証ファイル、`.mcp.json`内のローカル設定を無視しない。
- Claudeの一時ファイルは`.git/info/exclude`で除外されているが、他のcloneへ共有されない。
- `.claude/scheduled_tasks.lock`にはsession IDとPIDがあり、テンプレートへ含めてはならない。
- `.mcp.json`は秘密情報を含まない場合に限ってGit管理する。APIキー、トークン、個人固有パスは記載せず、必要な場合も環境変数名だけを参照する。
- OpenAI APIおよびAnthropic APIのAPIキー認証・従量課金は使用せず、ログイン済みのChatGPT Plus版Codex CLIとClaude Codeのサブスクリプション枠だけを使用する。
- Webのチューニングログには自由記述の`note`があるため、個人情報を書かない運用が必要。

## 7. 導入可否

判定: **条件付きで導入可能**

追加予定ディレクトリの多くは未使用で、入れ子Gitもないため、追加型の導入は可能。

ただし、以下を先に解決する必要がある。

- `CLAUDE.md`と`AGENTS.md`の世代不一致
- ビルド説明と実装の不一致
- 大量の未追跡ファイル
- `reference/extracted/cg/`の削除・アクセス拒否
- ローカル除外設定が他cloneへ共有されない問題

### 追加候補別の判断

| 対象 | 判断 |
|---|---|
| `CLAUDE.md` | 既存へ小規模統合。上書き禁止 |
| `AGENTS.md` | 既存へ小規模統合。ただし旧構成の扱いを先に決定 |
| `.mcp.json` | 秘密情報、APIキー、トークン、個人固有パスを含まない場合のみ新規作成・Git管理可能。初期導入では延期推奨 |
| `.claude/agents/` | 新規作成可能。既存lockへ触れない |
| `.claude/skills/multi-agent-design/` | 新規作成可能 |
| `docs/agent-workflow/` | 安全に新規作成可能 |
| `docs/decisions/` | 安全に新規作成可能 |

## 8. Step 2で変更してよい範囲

Step 2では、新しいワークフロー機能を追加する前に既存エージェント指示を整合させる。

### 既存ファイルへの変更候補

1. 現在の正本がRaging Bolt構成であることを、現行コード、提出物、`HANDOFF.md`から確認して明記する。
2. `AGENTS.md`の旧Iono's Kilowattrel構成を、正本と確認したRaging Bolt構成へ更新する。
3. `CLAUDE.md`の`build_submission.py`に関する説明を、実際のスクリプトの動作と一致させる。
4. Claude CodeとCodexに共通する開発ルールを一致させる。

`CLAUDE.md`と`AGENTS.md`は上書きせず、既存の有効なルールを保持したまま差分を小さくする。

### Step 3以降の新規作成候補

- `docs/agent-workflow/README.md`
- `docs/agent-workflow/review-protocol.md`
- `docs/decisions/0001-multi-agent-workflow-boundary.md`
- `README.md`への案内リンク
- `.mcp.json`
- `.claude/agents/`
- `.claude/skills/multi-agent-design/`
- `.claude/.gitignore`

### 変更してはいけないファイル

- `main.py`
- `deck.csv`
- `params.json`
- `agent/`
- `data/`
- `experiments/`
- `configs/`
- `reference/`
- `submission.tar.gz`
- 調査開始時点から存在する未追跡・削除扱いファイル

Step 2ではアプリコード、AI評価ロジック、UI、設定値、データを変更しない。

## 9. 懸念事項

### High

- `CLAUDE.md`と`AGENTS.md`が異なる現行構成を指示している。
- `CLAUDE.md`のビルド説明と`build_submission.py`が一致しない。
- `cg/`の6ファイルが削除扱いかつアクセス不能。
- 56件の未追跡ファイルがあり、誤stageの危険が高い。

### Medium

- ブランチがリモートより5コミット先行。
- CIとローカルテストランナーの範囲が不一致。
- `.env`等が`.gitignore`にない。
- Claude一時ファイルの除外がローカルGit設定だけ。
- `core.autocrlf=true`かつ`.gitattributes`がなく、Windows/WSL間で改行差分が出る可能性がある。
- 進捗文書が複数あり、正本が分かりにくい。

### Low

- `.mcp.json`、agents、skills、workflow文書の名前衝突はない。
- 入れ子Gitはない。
- ドキュメントだけの先行導入はアプリ挙動へ影響しない。

## 10. 推奨するStep 2

最初に、既存エージェント指示の整合を行う。

1. 現在の正本をRaging Bolt構成と確定する。
2. `AGENTS.md`の旧Iono's Kilowattrel構成を更新する。
3. `CLAUDE.md`の`build_submission.py`に関する誤説明を修正する。
4. Claude CodeとCodex間の共通ルールを一致させる。
5. アプリコードを変更していないことを差分で確認する。

既存指示の整合を確認した後、次の順序で導入する。

1. 共通ワークフロー文書
2. `.mcp.json`
3. `.claude/agents/`
4. `.claude/skills/multi-agent-design/`

`.mcp.json`は秘密情報を含まない場合のみGit管理し、OpenAI APIおよびAnthropic APIのAPIキー認証・従量課金は使用しない。

## 調査時の変更確認

Step 1の開始時と終了時で、以下のGit状態が一致した。

- HEAD: `67928b2`
- staged: 0
- unstaged削除: 6
- untracked: 56
- branch ahead: 5

Step 1の調査ではファイルの作成・変更・削除を行っていない。
