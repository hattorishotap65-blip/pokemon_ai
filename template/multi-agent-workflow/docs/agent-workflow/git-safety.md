# Git安全チェックリスト

このワークフローを導入・運用する際に必ず守るGitの安全ルールをまとめたものである。各項目に、継承元の文書・節、または「新規ガイダンス」の別を明記する。

## 1. dirty worktreeを破壊しない

未コミットの変更がある状態（dirty worktree）で作業を開始する場合、その変更を前提として扱い、破棄しない。作業前に `git status` を確認し、既存の変更内容を把握してから進める。

- 継承元: プロジェクトルール文書（CLAUDE.md / AGENTS.md 相当）の「Git安全ルール」および ADR の「Repository and Git boundary」節

## 2. 対象ファイルだけをstageする

commitのために変更をstageする際は、意図した対象ファイルだけを個別に `git add <file>` でstageする。

- 継承元: プロジェクトルール文書（CLAUDE.md / AGENTS.md 相当）の「Git安全ルール」

## 3. `git add .` / `git add -A` を使用しない

対象範囲外のファイルまで意図せずstageすることを防ぐため、`git add .` および `git add -A` は使用しない。

- 継承元: プロジェクトルール文書（CLAUDE.md / AGENTS.md 相当）の「Git安全ルール」および ADR の「Repository and Git boundary」節

## 4. `stash` / `reset` / `checkout` による変更破棄 / `clean` を標準ロールバックにしない

`git stash`、`git reset`、変更を破棄する `git checkout`、`git clean` を、設計・レビュー・実装ロールが「安全なロールバック手段」として提案することはない。これらは、対象タスクに関係のない他の未コミット作業を破壊し得るためである。

- 継承元: `.claude/agents/claude-architect.md` / `simplifier.md` / `design-judge.md` の「Rollback plan conventions」節、および ADR の「Repository and Git boundary」節

## 5. commit前のロールバックは明示的な逆編集

まだcommitが存在しない変更を取り消す場合は、「どのファイルのどの内容を、どう戻すか」を明示した逆編集を行う。「ファイルを元に戻す」のような曖昧な指示にしない。

- 継承元: `.claude/agents/claude-architect.md` / `simplifier.md` / `design-judge.md` の「Rollback plan conventions」節

## 6. commit後のロールバックはユーザー承認付き `git revert`

すでにcommitが存在する変更を取り消す場合は、対象commitをユーザーが明示的に確認・承認した上で `git revert` を使う。どのcommitが対象か自明としない。

- 継承元: `.claude/agents/claude-architect.md` / `simplifier.md` / `design-judge.md` の「Rollback plan conventions」節

## 7. 入れ子のGitリポジトリを作らない

このワークフローの導入・テンプレート配置作業のいずれにおいても、既存リポジトリの内部に新しい `.git` ディレクトリを作らない。

- 継承元: ADR の「Repository and Git boundary」節

## 8. 自動commit / push / PR作成 / mergeをしない

commit・push・PR作成・mergeは、いずれもユーザーの明示的な指示がある場合にのみ、指示された範囲だけを行う。ワークフロー自体が自動的にこれらを実行することはない。mergeは特に、ユーザー自身の判断に委ねる。

- 継承元: プロジェクトルール文書（CLAUDE.md / AGENTS.md 相当）の「Git安全ルール」および ADR の「Repository and Git boundary」節

## 9. sibling worktreeの利用方法

設計専用トライアルや小規模実装トライアルなど、元のリポジトリ/ブランチに影響を与えずに一連の作業を検証したい場合は、同じリポジトリに対する**sibling worktree**（例: 既定ブランチ `{{DEFAULT_BRANCH}}` から分岐した作業ブランチを、`git worktree add ../{{PROJECT_NAME}}-trial <作業ブランチ名>` のように別ディレクトリへ展開する）を使い、元のworktreeとは別のディレクトリ・別のブランチで作業する。入れ子のGitリポジトリを新規に作ることとは異なる。

- 新規ガイダンスであり、元文書からの直接継承ではない

## 10. 元worktreeの既存変更へ触れない

sibling worktreeや別ブランチでの作業中、元のworktreeに存在する未コミットの変更・別ブランチの状態を読み取り以外の方法で変更しない。複数のworktree・ブランチにまたがる作業であっても、対象範囲外のworktreeへは書き込まない。

- 新規ガイダンスであり、元文書からの直接継承ではない（項目1・7の原則をworktreeをまたぐ状況へ拡張したもの）
