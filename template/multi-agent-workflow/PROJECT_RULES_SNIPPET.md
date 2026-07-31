# Project rules snippet（手動貼り付け用）

**このファイルは自動挿入用ではない。** 導入先プロジェクトの既存ルール文書（Claude Code向けの `CLAUDE.md` 相当、Codex向けの `AGENTS.md` 相当のファイルなど）を、利用者自身が確認した上で、必要だと判断した部分だけを手動で貼り付けるための参考断片である。

## 使い方に関する注意

- **自動追記しない**: このファイルの内容を、スクリプトや自動処理によって既存ルール文書へ自動的に追記する仕組みは、このテンプレートには存在しない。人が内容を読み、必要な部分だけを手動でコピーする
- **既存ルールを上書きしない**: 導入先プロジェクトにすでに同種のルールが存在する場合、このファイルの内容で既存の記述を置き換えない
- **競合時は既存プロジェクトのルールを優先する**: このファイルの内容と、導入先プロジェクトの既存ルールが矛盾する場合、どちらを採用するかは人が判断する。このテンプレート側の内容が自動的に優先されることはない

## 貼り付けを検討する内容の例

以下は、`review-protocol.md` / `git-safety.md` / ADRテンプレートで詳しく説明している内容の要約である。詳細はそれぞれの文書を参照し、必要な部分だけを既存ルール文書へ反映すること。

```md
## マルチエージェント開発ワークフロー（要約）

- 全ての変更（設計・実装いずれも）に、ユーザーによる明示的な承認ゲートを設ける。ユーザーが承認するまで実装しない
- Implementation Owner以外の論理ロール（Requirements Auditor、Simplifier、Independent Architect、Alternative Architect、Red Team Reviewer、Design Judge/Integrator、Final Auditor）はread-onlyとする。コードの変更・ファイルの作成/編集/削除・commit/push/PR作成/mergeは行わない
- `git add .` / `git add -A` を使用しない。対象ファイルだけを個別にstageする
- `git stash` / `git reset` / 変更を破棄する `git checkout` / `git clean` を、安全なロールバック手段として扱わない。commit前は明示的な逆編集、commit後はユーザー承認付き `git revert` を使う
- commit・push・PR作成・mergeを自動実行しない。ユーザーの明示的な指示がある場合にのみ、指示された範囲だけ行う
- 入れ子のGitリポジトリを作らない
```

## 関連文書

- [docs/agent-workflow/review-protocol.md](docs/agent-workflow/review-protocol.md)
- [docs/agent-workflow/git-safety.md](docs/agent-workflow/git-safety.md)
- [docs/decisions/{{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md](docs/decisions/{{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md)
