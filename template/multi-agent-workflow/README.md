# Multi-agent Workflow Template

Claude Code を Implementation Owner とし、Claude Code project subagents による read-only 監査・設計と、Codex MCP による独立設計・Red Team・Final Audit を組み合わせた、設計と実装の権限分離型マルチエージェント開発ワークフローを、別のソフトウェアプロジェクトへ導入するためのテンプレートパッケージである。

このファイルおよびパッケージ内の各文書本文は日本語で記述する。ただし、ファイル名・ディレクトリ名・JSONキー・CLI名・プレースホルダー名・論理ロール名は英語のまま使用する。全文を英訳する方針ではない。

## このバージョン（0.3.0）の位置づけ

**このパッケージは、既存のdesign-only統合設計に、汎用Outcome Improvement Cycleをopt-inで追加した。** テンプレート内容と静的 `manifest.json`、read-only verifier（`tools/verify_workflow_template.py`）、および外部Evidence専用の決定論的read-only Gatekeeper（`tools/outcome_gatekeeper.py`）をsource repository内のunittestで検証する。既存`multi-agent-design` Skillとverifierの責務は変更していない。次は、このバージョンに含まれない。

- 自動インストーラー — このパッケージ自体は、ファイルを自動生成・自動配置するプログラムではない
- apply / update / uninstall 機能 — 導入・更新・削除を自動化する機能は存在しない
- ファイルの自動上書き — 導入先に既存ファイルがあっても、自動的に上書きすることは一切ない
- `.mcp.json` の自動 merge — 導入先に既存の `.mcp.json` がある場合、自動的な構造的マージは行わない。手動で内容を確認し、必要な設定を手動で反映する
- プロジェクトルール文書（`CLAUDE.md` / `AGENTS.md` 相当のファイル）への自動挿入 — `PROJECT_RULES_SNIPPET.md` は手動で参照・貼り付けする参考断片であり、既存ファイルへの自動追記は行わない
- 実際のproduction repositoryへの本番導入実績 — 使い捨てのdisposable sample targetによるportability trial（詳細は「Portability validation」節を参照）は実施済みだが、実際の別プロジェクト・production repositoryへ本番導入した実績は、このバージョンの時点では存在しない（未検証）。cross-OS portability（Windows以外の環境）も未検証
- 外部evaluatorまたはアプリ本体 — Gatekeeperは既に生成されたEvidenceを比較するだけで、測定を実行しない
- example Profileの本番基準化 — Pokemon AIとRAGの例は`example_only`であり、実運用defaultではない
- heterogeneous independent review — 0.3.0はsame-model bootstrapであり、異種モデル監査は未完了

`tools/verify_workflow_template.py`（read-only verifier）を同梱している。verifierは**状態を報告するだけ**であり、コピー・マージ・書き込みは一切行わない（詳細は「検証CLI（verifier）」節を参照）。**手動導入の前に、導入先プロジェクトの既存ファイルとの競合を、利用者自身が `git status` / `git diff`、および必要に応じてverifierの `plan` 出力で確認する必要がある。**

## ディレクトリ構成

```text
template/multi-agent-workflow/
├── README.md                              (this file)
├── PLACEHOLDERS.md                        (placeholder reference)
├── VERSION                                (package version, semver)
├── CHANGELOG.md                           (package version history)
├── manifest.json                          (static package inventory)
├── PROJECT_RULES_SNIPPET.md               (manual-paste reference snippet)
├── .gitattributes                         (package-local Git attributes: * -text)
├── .mcp.json                              (verbatim — Codex MCP server config)
├── .claude/
│   ├── agents/
│   │   ├── requirements-auditor.md        (verbatim)
│   │   ├── simplifier.md                  (verbatim)
│   │   ├── claude-architect.md            (verbatim)
│   │   └── design-judge.md                (verbatim)
│   └── skills/
│       ├── {{DESIGN_SKILL_NAME}}/
│       │   └── SKILL.md                   (generified)
│       └── outcome-improvement-cycle/
│           └── SKILL.md                   (generic, opt-in)
├── examples/
│   └── app-profiles/
│       ├── pokemon-ai.example.json        (example_only)
│       └── rag-quality.example.json       (example_only)
├── tools/
│   ├── verify_workflow_template.py        (package read-only verifier)
│   └── outcome_gatekeeper.py              (adoptable read-only gate)
└── docs/
    ├── agent-workflow/
    │   ├── README.md                      (generified)
    │   ├── review-protocol.md             (generified)
    │   ├── quality-first-token-policy.md  (generified)
    │   ├── mcp-connection.md              (generified)
    │   ├── subagents.md                   (generified)
    │   ├── multi-agent-design-skill.md    (generified)
    │   ├── outcome-improvement-cycle.md   (generic)
    │   ├── app-profile.md                 (generic JSON contract)
    │   ├── git-safety.md                  (new)
    │   ├── troubleshooting.md             (new)
    │   ├── repository-audit-template.md   (new, empty skeleton)
    │   └── trial-log-template.md          (new, empty skeleton)
    └── decisions/
        └── {{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md  (generified)
```

`tools/verify_workflow_template.py`（package verifier）の`adoption_mode`は`REFERENCE_ONLY`であり、パッケージ内から実行する。`tools/outcome_gatekeeper.py`は導入先に同名ファイルがない場合だけ手動コピー候補となる`COPY_IF_ABSENT`である。どちらも書込み機能を持たない。

`.gitattributes`（内容は `* -text` の1行のみ）は、このパッケージを配布している**このリポジトリ内**で、`core.autocrlf` の設定やOSにかかわらず、fresh clone / fresh checkout後のワーキングツリーのバイト列がGit blobのバイト列（および `manifest.json` に記録されたSHA-256）と一致するよう保護するためのpackage-localな設定である。`adoption_mode` は `PACKAGE_METADATA` であり、導入先リポジトリへコピーする対象ではない。導入先リポジトリへ手動配置されたファイルには、導入先リポジトリ自身のGit attributes・`core.autocrlf` 設定が適用され得る。導入先でcommit後にfresh checkoutした場合の厳密なバイト一致は、導入先リポジトリの改行コード方針に依存する。**adopter側の改行コード方針を自動的に設定することは、このバージョンの対象外である。** 詳細は今後のproduction-likeな導入試験で別途確認する。

`manifest.json` の `files` は31件であり、うち `manifest.json` 自身（自己参照のため `sha256: null`）を除く30件がSHA-256比較の対象である。

`{{DESIGN_SKILL_NAME}}` と `{{ADR_NUMBER}}` は、実際のディレクトリ名・ファイル名そのものに使われているプレースホルダーである。導入時に、実際の値へリネームする必要がある（詳細は `PLACEHOLDERS.md` を参照）。

## プレースホルダー

このパッケージ内の各文書には `{{...}}` 形式のプレースホルダーが含まれる。一覧・意味・必須/任意・例・使用ファイル・未解決時の扱いは `PLACEHOLDERS.md` を参照すること。プレースホルダーは必要最小限に絞っており、ユーザー名を含む絶対パスの具体例は記載していない。

## manifestの導入先マッピング

`manifest.json` の各 `files` エントリには、`path`（パッケージ内でのファイル位置）に加えて、`target_path`（導入先での候補位置）と `adoption_mode`（そのファイルの扱い方の分類）が記録されている。これらは、同梱の検証CLI（verifier）が「導入先の何と比較すべきか」を機械的に判断するために実際に読み込む情報であり、**自動処理の許可を意味しない。**

- **`path`**: このパッケージ内でのファイルの相対位置
- **`target_path`**: 導入先リポジトリのルートから見た候補となる相対位置。`null` の場合、そのファイルは導入先リポジトリの特定ファイルと比較する対象ではない
- **`adoption_mode`**: 次の5種類のいずれか

| adoption_mode | 意味 |
|---|---|
| `PACKAGE_METADATA` | テンプレート配布物自体の管理情報。導入先とのファイル比較対象にしない |
| `COPY_IF_ABSENT` | 導入先に存在しなければ手動コピーの候補。既存ファイルを自動上書きしない |
| `MANUAL_REVIEW` | 既存内容との競合可能性が高いため、必ず人が内容を確認して統合する。自動mergeしない |
| `REFERENCE_ONLY` | 参考資料・手動作業用の断片。導入先への配置対象にしない |
| `TEMPLATE_RENAME` | テンプレート側のファイル名と導入先での名前が異なる。`target_path` に示した名前で手動作成する候補 |

**重要な注意**:

- `adoption_mode` はいずれも、検証CLI（verifier）や他のツールが**自動的にコピー・マージ・リネームしてよいという許可を意味しない**。同梱のverifierは状態を報告するだけであり、書き込みは一切行わない（詳細は「検証CLI（verifier）」節を参照）
- `COPY_IF_ABSENT` であっても、実際のコピーは利用者が手動で行う。導入先に同名ファイルがすでに存在する場合、自動的に上書きしない
- `MANUAL_REVIEW`（`.mcp.json` が該当）は、導入先に既存の `.mcp.json` がある可能性が高いため、内容を人が読み比べ、必要なサーバー設定だけを判断して統合することを前提とする
- `TEMPLATE_RENAME`（ADRテンプレートが該当）は、パッケージ内のファイル名（`{{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md`）と、導入先で実際に使うファイル名（`{{ADR_NUMBER}}-multi-agent-workflow-boundary.md`、`.template` を含まない）が異なることを示す。導入先での作成は手動で行う
- `PACKAGE_METADATA` と `REFERENCE_ONLY` は、いずれも導入先リポジトリへ配置する対象ではない（`target_path` は常に `null`）

## 手動導入の流れ（このバージョンの時点）

verifierは状態を報告するだけであり、実際のコピー・置換・統合はすべて利用者が手動で行う。

0. （任意・推奨）`python tools/verify_workflow_template.py source-integrity` をこのパッケージ内で実行し、パッケージ自体がmanifestと整合していることを確認する。
1. 導入先プロジェクトの `git status` / `git diff` を確認し、`manifest.json` が導入候補として示す `target_path` と既存ファイルが衝突しないか、利用者自身が確認する。加えて、`python tools/verify_workflow_template.py plan --target-root <導入先パス> --set ...` を実行し、ファイルごとの状態（MISSING/IDENTICAL/DIFFERENT/INVALID/UNRESOLVED_PLACEHOLDER）を事前に確認してもよい（詳細は「検証CLI（verifier）」節を参照）。
2. `manifest.json` の各 `files` エントリを個別に確認し、`adoption_mode` に従って手動で扱う。`COPY_IF_ABSENT` は導入先の `target_path` が存在しない場合だけコピーする。`TEMPLATE_RENAME` はrename後の `target_path` に手動作成する。`MANUAL_REVIEW` はこの段階で一括コピーせず、手順4で扱う。`PACKAGE_METADATA` と `REFERENCE_ONLY` は導入先へ配置しない。
3. `PLACEHOLDERS.md` を参照し、各プレースホルダーを導入先プロジェクトの実際の値へ手動で置き換える（`{{DESIGN_SKILL_NAME}}` と `{{ADR_NUMBER}}` は、ディレクトリ名・ファイル名そのもののリネームを含む）。
4. `MANUAL_REVIEW` 対象の `.mcp.json` は、導入先での有無にかかわらず内容を人が確認する。既存 `.mcp.json` がある場合は、自動マージや上書きを行わず、必要なサーバー設定だけを人が判断して統合する。存在しない場合も、内容を確認した上で手動作成する。
5. `PROJECT_RULES_SNIPPET.md` を参照し、導入先プロジェクトの既存ルール文書（`CLAUDE.md` / `AGENTS.md` 相当）に、必要な部分だけを人が判断して手動で貼り付ける。既存ルールを上書きしない。
6. 導入先プロジェクトで Claude Code を再起動し、MCPサーバーの承認プロンプトを確認した上で承認し、`.claude/agents/` の4エージェントと `{{DESIGN_SKILL_NAME}}` Skill が利用可能であることを、利用者自身が手動で確認する（手順は `docs/agent-workflow/mcp-connection.md` / `subagents.md` / `multi-agent-design-skill.md` を参照）。
7. `git status` / `git diff` を再確認し、意図した差分だけが生じていることを確認した上で、個別のファイルだけを `git add <file>` でstageする。`git add .` や `git add -A` は使用しない。commit・push・PR作成・mergeは、このテンプレート自体が推奨・自動化するものではなく、利用者自身の判断で行う。

## Portability validation（disposable sample targetでの移植試験）

このバージョンで、以下2種類の**使い捨て（disposable）sample target**に対して、上記「手動導入の流れ」の内容をoperator（人）が手動で実行し、`plan` サブコマンドで確認する試験を1回実施した。実施環境はWindows環境1件のみである。

検証したtarget:

1. **fresh non-Git target** — Gitリポジトリではない空のディレクトリ
2. **pre-existing dirty Git target** — 既存の `.mcp.json` / `.claude/agents/simplifier.md` / `README.md` をcommit済みで、未追跡ファイル（dirty状態）も含むGitリポジトリ

### fresh non-Git targetで確認したこと

- 導入前の `plan` では、比較対象15件のうち15件が `MISSING` として報告された
- `COPY_IF_ABSENT` 対象をoperatorが手動で作成した
- `MANUAL_REVIEW` 対象（`.mcp.json`）を、人がJSON構造を確認した上で配置した（自動配置ではない）
- `TEMPLATE_RENAME` 対象（ADRテンプレート）を、rename後の `target_path` へ手動作成した
- `PACKAGE_METADATA` 分類のファイルは配置しなかった
- `REFERENCE_ONLY` 分類のファイルは配置しなかった
- 導入後の `plan` では、15件中15件が `IDENTICAL` として報告された
- `MANUAL_REVIEW` 対象が存在するため、`IDENTICAL` であっても `plan` のexit codeは1のままだった（人の確認を必要とする設計であり、失敗ではない）
- Gitリポジトリではないtargetでも `plan` は動作した（`.git` の有無に依存しない）
- targetの1ファイルへ意図的な変更（末尾改行の追加）を加えたところ、`plan` は該当ファイルを `DIFFERENT` として検出した
- 変更を元の（プレースホルダー置換後の）正しい内容へ戻したところ、`plan` は再び `IDENTICAL` として報告した

### pre-existing dirty Git targetで確認したこと

- 既存ファイルを自動上書きしなかった（`COPY_IF_ABSENT` 対象のうち、targetにすでに存在した1件は、`plan` で `DIFFERENT` と報告され続けた状態のまま保護された）
- `.mcp.json` を自動マージしなかった
- targetに既存のMCP server設定を維持したまま、operatorが手動で新規server entryを統合できることを確認した（JSONとして再parseし、既存keyとの衝突がないことを確認した上で追記した）
- 手動merge後の `.mcp.json` は、パッケージ原本との厳密なbyte comparisonでは `DIFFERENT` のままであり得ることを確認した
- 既存のrepository-owned文書（`.claude/agents/simplifier.md` 相当）も、上書きせず保護したため `DIFFERENT` のままであり、これは正常な結果であることを確認した
- targetのdirty状態（未追跡ファイル）を `plan` が変更しないことを確認した（実行前後でファイル内容・`git status` の出力が同一だった）
- `plan` がGit管理情報（`.git` 配下）へ一切書き込まないことを確認した

**「manual mergeの結果がpackage原本とDIFFERENTのままであること」は失敗ではない。** verifierは次を判断しない。

- JSONのsemantic equivalence（意味的な同値性）
- manual mergeの組織的・運用的な妥当性
- repository-owned policyと導入テンプレートのどちらを優先すべきかという判断
- 人が行った統合内容そのものの正しさ

verifierが判断するのは、プレースホルダー置換後のpackage bytesと、target側の実ファイルbytesとの**厳密な一致・不一致**だけである。

### 確認済み / 未確認の範囲

確認済み:

- disposable fresh non-Git target
- disposable existing dirty Git target
- 上記「手動導入の流れ」に沿った手動導入フロー
- strict byte comparison（プレースホルダー置換後の厳密なバイト一致判定）
- drift検出（意図しない変更が `DIFFERENT` として検出されること）
- read-only verification（verifierがtargetへ一切書き込まないこと）
- 既存ファイル保護（`COPY_IF_ABSENT` 対象・`MANUAL_REVIEW` 対象のいずれも自動上書きしないこと）

未確認:

- 実際のproduction repositoryへの導入
- 導入先固有の運用ルール・組織ポリシーとの整合
- cross-OS portability（Linux/macOS等、Windows以外の環境）
- 導入先リポジトリ側の改行コード方針（`.gitattributes` / `core.autocrlf`）との整合、および導入先でのcommit・fresh checkout後のバイト一致
- normalization-sensitiveなファイルシステムでの挙動（「パス安全性」節の既知の制限を参照）
- semantic mergeの正しさ（`.mcp.json` 等の意味的な統合が妥当かどうかは、常に人が判断する）
- 大規模パッケージ・大量ファイルでの導入
- 同時書き込み（concurrent mutation）下でのTOCTOUの完全な排除（「TOCTOU（既知の制限）」節を参照）

## Binary-safe manual adoption（推奨実装）

portability trial中に、プレースホルダー置換をtext modeでのread/writeとして実装すると、内容が意味的には同じに見えても、改行コード（CRLF/LF）が意図せず変換され、`plan` が `DIFFERENT` として報告する事象を確認した。これは verifierの誤検出ではなく、**プレースホルダー置換後の厳密なバイト一致**という設計どおりの検出である（「状態分類（5種類のみ）」節を参照）。

手動導入時は、次のbinary-preservingな方針を推奨する。

**プレースホルダーを含まないファイル**:

- raw bytesとしてコピーする（`shutil.copyfile` 等）
- text modeで読み込んで再保存しない
- newline・末尾改行・BOM・空白のいずれも変えない

**プレースホルダーを含むUTF-8テキストファイル**:

1. `read_bytes()` でファイル全体をbytesとして読み込む
2. UTF-8としてdecodeする
3. `TOKEN_RE.sub()` を1回だけ実行し、元の本文中に存在する完全一致のプレースホルダートークンを単一パスで置換する。置換値は再走査せず、再帰的に展開しない
4. UTF-8としてencodeし直す
5. `write_bytes()` でbytesのまま書き込む

避けるべきこと:

- universal newline変換（text modeでの読み込みによる自動変換を含む）
- CRLF/LFの正規化
- JSON・Markdownの再format（インデント・改行位置の変更を含む）
- 末尾改行の追加・削除
- 汎用的なwhitespace normalization
- 元のencodingからの変更

以下は、上記の方針をPython標準ライブラリのみで示す参考例である。

```python
import re
import unicodedata
from pathlib import Path

TOKEN_RE = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")
DISALLOWED_VALUE_CATEGORIES = {"Cc", "Zl", "Zp"}


def validate_placeholder_value(value: str) -> None:
    if (
        value == ""
        or "{{" in value
        or "}}" in value
        or any(
            unicodedata.category(char) in DISALLOWED_VALUE_CATEGORIES
            for char in value
        )
    ):
        raise ValueError("unsafe placeholder value")


def adopt_file(
    src: Path,
    dst: Path,
    placeholders: dict[str, str],
) -> None:
    if dst.exists():
        raise FileExistsError(
            "destination already exists; refusing to overwrite"
        )

    raw = src.read_bytes()

    if placeholders:
        for value in placeholders.values():
            validate_placeholder_value(value)

        text = raw.decode("utf-8")

        def replace_token(match: re.Match[str]) -> str:
            name = match.group(1)
            return placeholders.get(name, match.group(0))

        rendered = TOKEN_RE.sub(replace_token, text)

        if TOKEN_RE.search(rendered):
            raise ValueError(
                "unresolved placeholder remains after substitution"
            )

        raw = rendered.encode("utf-8")

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(raw)
```

この参考例について、次を明記する。

- **自動installerとして提供しない**。このパッケージ自体にapply scriptとして同梱しない
- targetを自動上書きしない（`dst.exists()` の場合は例外を送出して停止する）
- 実行前にtarget側の存在確認を行う
- `MANUAL_REVIEW` 対象（`.mcp.json`）には使用しない。既存ファイルとの統合は、常に人が内容を読んで判断する
- あくまでoperator（人）が手元で使う参考例であり、`tools/verify_workflow_template.py` の一部でも、パッケージが自動実行するコードでもない

コード例が満たす性質:

- `read_bytes` / `write_bytes` によるbinary-safeな読み書き
- 厳密なUTF-8 decode/encode
- 完全一致するプレースホルダートークンのみを置換する
- 置換後に未解決のプレースホルダーが残っていないかを確認する
- destinationがすでに存在する場合は書き込まずに停止する
- absolute pathや秘密情報を出力しない
- `subprocess` を使用しない
- Git操作を一切行わない

## セキュリティ・境界に関する方針

- full model ID（特定バージョンのモデル識別子）はこのパッケージのどこにも固定しない。`.claude/agents/*.md` の `model:` はエイリアス（例: `haiku` / `sonnet` / `opus`）のみを使用する
- APIキー・トークン・認証情報は、このパッケージのどこにも保存しない
- Agent ID・threadId・MCP task ID は、実行時の一時的な識別子であり、このパッケージのどこにも記録しない
- ユーザー名を含む絶対パスは、このパッケージのどこにも記載しない
- `git add .` / `git add -A` は使用しない。対象ファイルだけを個別にstageする
- `git stash` / `git reset` / `git checkout` による変更破棄 / `git clean` を、安全なロールバック手段として扱わない（詳細は `docs/agent-workflow/git-safety.md` を参照）
- commit・push・PR作成・mergeを自動実行しない。すべて利用者の明示的な判断・操作に委ねる
- 入れ子のGitリポジトリを作らない

## バージョニング方針

このパッケージは [Semantic Versioning](https://semver.org/)（`MAJOR.MINOR.PATCH`）に従う。

- **MAJOR**: 生成されるファイル構成・プレースホルダー契約に互換性のない変更がある場合
- **MINOR**: 後方互換性のある機能追加（例: 検証CLIの新規追加）がある場合
- **PATCH**: 文言修正・誤字修正・非破壊的な内容修正がある場合

バージョンの単一の正本は `VERSION` ファイルであり、変更履歴は `CHANGELOG.md` に記録する。導入先プロジェクトへの自動アップデート機能は存在しない。

## 将来のv2の条件

自動apply・自動update・自動uninstallを含むより自動化された仕組み（v2）は、次の両方が確認された場合にのみ検討する。

- 2件以上の、実際に異なるプロジェクトへの実導入試験が行われていること
- それらの試験を通じて、手作業による更新・アンインストールが繰り返し発生する現実の問題であると確認されていること

このバージョンの時点では、上記のいずれも確認されていない。「Portability validation」節のdisposable sample targetでの試験は、手動導入フロー・verifierの挙動確認を目的としたものであり、上記の「実際に異なるプロジェクトへの実導入試験」には該当しない。

## Outcome Gatekeeper

`tools/outcome_gatekeeper.py`は、導入先でversioned App Profileと外部Evidence Bundleを比較するPython標準ライブラリだけのread-only CLIである。Profile形式と制御フローは次を参照する。

- [`docs/agent-workflow/app-profile.md`](docs/agent-workflow/app-profile.md)
- [`docs/agent-workflow/outcome-improvement-cycle.md`](docs/agent-workflow/outcome-improvement-cycle.md)
- [`.claude/skills/outcome-improvement-cycle/SKILL.md`](.claude/skills/outcome-improvement-cycle/SKILL.md)

Gatekeeperは評価command、Profile文字列、module、URLを実行しない。subprocess、network、Git、write APIを持たず、stdoutへ判定JSONを返すだけである。Schema v1.1ではpermission依存矛盾とallowed/prohibited path競合をfail-closedにし、Cycle ID、固定Primary/Fallback、Evidence round、immutable artifact bindingを検証する。delta CIは合成せず、外部Evaluator生成の`delta_stats`だけを使用する。`example_only` Profileはvalidate/digestできるがevaluateは`BLOCKED`になる。

```bash
python -B tools/outcome_gatekeeper.py validate-profile examples/app-profiles/rag-quality.example.json
python -B tools/outcome_gatekeeper.py digest-profile examples/app-profiles/rag-quality.example.json
```

外部evaluatorはパッケージに含まれない。実運用Profileのbaseline、dataset、protocol、threshold、Evidence量をサンプルから推測してはならない。

source repositoryでの回帰検証は次を個別に実行する。配布先では、採用したProfileとproject固有testを別途追加する。

```bash
python -B -m unittest experiments.test_outcome_gatekeeper -v
python -B -m unittest discover -s experiments -p "test_verify_workflow_template.py" -v
python -B template/multi-agent-workflow/tools/verify_workflow_template.py source-integrity
```

## 検証CLI（verifier）

`tools/verify_workflow_template.py` は、Python標準ライブラリのみを使用した**完全read-only**の診断ツールである。パッケージルートは、このスクリプト自身の場所（`Path(__file__).resolve().parents[1]`）から解決するため、実行時のカレントディレクトリに依存しない。

**この節の内容を要約すると**: verifierは状態を報告するだけで、コピー・apply・install・update・uninstall・merge・backup・rename・remove・delete・ファイル作成・Git操作・`subprocess` 実行のいずれも行わない。verifier自体は `adoption_mode: REFERENCE_ONLY` であり、導入先リポジトリへ自動的にコピーされる対象ではない。

### サブコマンド

#### `source-integrity`

パッケージ自身の内容を `manifest.json` と照合する。導入先（target-root）は関与しない。

```bash
python -B template/multi-agent-workflow/tools/verify_workflow_template.py source-integrity
```

確認内容: manifestの構造検証、manifest内全pathの安全性検証、全パッケージファイルの存在確認、SHA-256整合確認（`manifest.json` 自身を除く）、プレースホルダー宣言との整合確認、adoption_modeとtarget_pathの整合確認、パッケージ内symlink/junction/reparse redirectの拒否、パッケージ外へのpath逸脱拒否、manifest自身のsha256がnullであることの確認、**manifest.filesに登録されていないファイルの検出**（下記参照）。

**`manifest.json` 自身のcontainment検証（bootstrap検証）**: `manifest.json` は特別扱いされる読み込み専用ファイルではなく、他の全パッケージファイルと同じcontainment検査（symlink/junction/reparse pointの拒否、パッケージ外への逸脱拒否、パッケージ内の別位置へのinternal redirect拒否、途中のすべてのpath要素の検査、大文字小文字の衝突検出）を、`stat`・読み取り・JSONパースより**前に**通過する必要がある。この検証は、まだmanifestを読み込めていない**bootstrap段階**で行われるため、他のper-fileやscanの検出結果とは異なり、**通常のファイル別report・summaryを作成する前に処理全体を停止する。**

`manifest.json` 自身がsymlink/junction/reparse pointである場合、またはcontainment逸脱（パッケージ外へのredirect・パッケージ内の別位置への内部redirect・途中ディレクトリのredirect等）が検出された場合は、他のファイルと同じ理由コード（例: `CONTAINMENT_ERROR`、`CASE_COLLISION`）を用いつつ、`[BLOCKED] reason: <固定reason code>` として表示し、exit 8で即座に停止する。**この場合、`[BLOCKING_ERROR]` は使用せず、`blocking_errors` を含むsummary自体が一切表示されないことがある**（summaryはmanifest読み込み成功後にのみ作成されるため）。`manifest.json` 本文・redirect先の絶対パスは、いずれも表示しない。`manifest.json` が存在しない場合は exit 3（`[BLOCKED] reason: MANIFEST_MISSING`）、通常ファイルではない場合（ディレクトリ・special file）は `MANIFEST_IS_DIRECTORY` / `MANIFEST_SPECIAL_FILE`（`[BLOCKED]`、exit 4）として拒否する。

**bootstrap failureと、manifestロード後のblocking findingの違い**は次のとおりである。

| 段階 | 表示 | summary | 対象 |
|---|---|---|---|
| manifest bootstrap（`manifest.json` 自身の読み込み前検証） | `[BLOCKED] reason: <固定reason code>` | 表示されないことがある（summary生成前に停止する場合を含む） | `manifest.json` 自身のcontainment・存在・種別 |
| manifestロード後のper-file検査・package scan | `[BLOCKING_ERROR]` | `blocking_errors` へ加算（詳細は「`INVALID`と`BLOCKING_ERROR`の区別」を参照） | 個々のpackage file・target file・未登録エントリのcontainment/I-O問題 |

つまり、`manifest.json` 自身に対するcontainment違反は常に `[BLOCKED]` であり `[BLOCKING_ERROR]` ではない。一方、`manifest.json` の読み込みに成功した**後**の個々のファイル（宣言済みpackage file、target file、未登録エントリ）に対するcontainment/I-O安全境界の問題は `[BLOCKING_ERROR]` として表示され `blocking_errors` へ加算される。両者はいずれもexit 8である点は共通するが、表示形式・summaryの有無が異なる。

**manifest未登録ファイルの検出**: `source-integrity` は、`manifest.json` を静的パッケージ在庫の正本として扱い、パッケージルート配下を再帰的に（read-only、symlink/junction/reparse pointは追跡しない）走査し、manifestの `files` に登録されていない通常ファイルを検出する。`.DS_Store`・`desktop.ini`・`Thumbs.db`・`*.pyc`・`__pycache__` 配下のファイル・エディタのバックアップファイル・一時ファイル等を含め、暗黙のignore一覧は設けない——これらも登録されていなければ検出対象となる。未登録の通常ファイルが見つかった場合は `INVALID`（reason: `UNLISTED_PACKAGE_FILE`、exit 4）として報告し、安全な相対パスのみを表示する（ファイル本文・絶対パスは表示しない）。未登録のFIFO・socket・デバイスファイル等の非通常ファイルが見つかった場合は `INVALID`（reason: `UNLISTED_SPECIAL_FILE`、exit 4）として区別して報告する（登録済みの非通常ファイルを指す `SPECIAL_FILE` reasonとは意味的に区別している）。未登録のsymlink/junction/reparse pointが見つかった場合はcontainmentの懸念として `[BLOCKING_ERROR]`（exit 8）で拒否する（詳細は「INVALIDとBLOCKING_ERRORの区別」を参照）。**自動削除・自動manifest登録は行わない。** 生成物や不要ファイルが意図せず混入した場合、それをmanifestへ登録するか削除するかは、利用者・実装者が判断する。空のディレクトリは、それ自体を理由にINVALIDとしない。パッケージルート走査の件数上限については「リソース上限」の「package scan entry budget」を参照。

**`INVALID`と`BLOCKING_ERROR`の区別**: このツールは、比較状態としての5状態（`MISSING`/`IDENTICAL`/`DIFFERENT`/`INVALID`/`UNRESOLVED_PLACEHOLDER`）とは別に、表示専用の `[BLOCKING_ERROR]` という報告分類を持つ。

- **`[INVALID]`**: package metadata・content・type等の非blockingな不正（サイズ超過・UTF-8でない・ディレクトリ/special fileが declared path にある・宣言されていないplaceholder等）。summaryの `invalid` カウンタへ加算される。exit 4の要因。
- **`[BLOCKING_ERROR]`**: containment逸脱・symlink/junction/reparse redirect・I/O安全境界に関する問題。summaryの `blocking_errors` カウンタへ加算される。1件以上あればexit 8（`8 > 4 > 3 > 1 > 0` の優先順位は維持）。

**同じfindingが `invalid` と `blocking_errors` の両方へ加算されることはない。** 表示された `[INVALID]` 行の件数はsummaryの `invalid` と一致し、表示された `[BLOCKING_ERROR]` 行の件数はsummaryの `blocking_errors` と一致する。正常なパッケージでの `source-integrity` 実行時は `blocking_errors: 0` となる。

#### `plan`

パッケージの内容（プレースホルダー置換後）を、指定した導入先（target-root）の実ファイルと比較する。**比較のみで、一切書き込まない。**

```bash
python -B template/multi-agent-workflow/tools/verify_workflow_template.py plan \
  --target-root <TARGET_ROOT> \
  --set PROJECT_NAME=example \
  --set DEFAULT_BRANCH=main \
  --set MCP_SERVER_NAME=codex-reviewer \
  --set CODEX_COMMAND=codex \
  --set DESIGN_SKILL_NAME=multi-agent-design \
  --set ADR_NUMBER=0001 \
  --set TEST_COMMANDS="python -m unittest" \
  --set PROTECTED_PATHS="src/,config/" \
  --set PROJECT_SPECIFIC_DOCS="docs/project.md"
```

`--set NAME=VALUE` は繰り返し指定できる。NAMEに波括弧は付けない。**`--set` の値には、APIキー・トークン・パスワード・個人情報等の秘密情報をいかなるプレースホルダーに対しても絶対に渡さないこと。**

値の表示範囲は、そのプレースホルダーが `target_path` を構成するかどうかで異なる。

- **ファイル本文専用のプレースホルダー**（例: `PROJECT_NAME`、`TEST_COMMANDS`、`PROTECTED_PATHS`、`PROJECT_SPECIFIC_DOCS` 等、ファイル内容にのみ現れるもの）の値は、標準出力へ一切表示されない
- **`target_path` を構成するプレースホルダー**（現時点では `DESIGN_SKILL_NAME` と `ADR_NUMBER`）の値は、レンダリング後の**相対** target path の一部として `target:` 行に表示され得る。これは導入計画の表示に本質的に必要な情報であり、値単体・`NAME=VALUE` 形式では表示しない
- 未解決のプレースホルダー**名**（`NAME`）は表示されることがあるが、利用者が渡した**値**が単独で表示されることはない
- target rootの絶対パスは、いずれの場合も表示せず、常に `<target-root>` と表記する
- **`--set` の値は、ファイル本文専用か `target_path` 構成用かを問わず、すべてのプレースホルダーについて次を満たす必要がある**: 空文字ではないこと、制御文字（NUL、C0/C1制御文字、CR、LF、tab、vertical tab、form feed等）やUnicode行区切り（U+2028）・段落区切り（U+2029）を含まないこと、`{{`・`}}` を含まないこと。いずれかに違反した場合はusage error（exit 2）であり、値そのものは表示されない。これは標準出力レポートへの偽の行注入を防ぐための制約である。`target_path` を構成するプレースホルダーには、上記に加えてパス要素としての安全性検証（`/`・`\`・`:`・`.`・`..`の拒否）がさらに適用される

`manifest.json` の `adoption_mode` を正本として、比較対象の判定が変わる:

| adoption_mode | plan での扱い |
|---|---|
| `PACKAGE_METADATA` | 導入先と比較しない（`skipped_by_mode` に集計） |
| `REFERENCE_ONLY` | 導入先と比較しない（`skipped_by_mode` に集計） |
| `COPY_IF_ABSENT` | `target_path` を解決し比較する。自動コピーはしない |
| `MANUAL_REVIEW`（`.mcp.json`） | `target_path` を解決し比較する。結果が`IDENTICAL`であっても`manual_review_required`としてexit 1になる。自動mergeはしない |
| `TEMPLATE_RENAME`（ADRテンプレート） | manifestの`target_path`（プレースホルダー解決後の名前）で比較する。ファイル作成・renameはしない |

### 状態分類（5種類のみ）

`MISSING` / `IDENTICAL` / `DIFFERENT` / `INVALID` / `UNRESOLVED_PLACEHOLDER`。比較は**プレースホルダー置換後の厳密なバイト一致**であり、CRLF/LF・末尾改行・空白・JSON・Markdown・YAML frontmatterのいずれも正規化しない。したがってCRLFとLFの違いも `DIFFERENT` になる。この結果は、どちらが正しい・正本かを判断するものではない。

`PACKAGE_METADATA` / `REFERENCE_ONLY` に分類されたファイルは、この5状態の対象外（`SKIPPED`、`skipped_by_mode` に集計）である。

`BLOCKING_ERROR` はこの5状態のいずれでもない、別枠のblocking report分類である（containment逸脱・symlink/junction/reparse redirect・I/O安全境界の問題を表示・集計するためのもの、`blocking_errors` に集計）。詳細は「`INVALID`と`BLOCKING_ERROR`の区別」を参照。

### exit code

| code | 意味 |
|---|---|
| 0 | すべて成功条件を満たす |
| 1 | driftまたは人の対応が必要（`plan`: **target側**のMISSING/DIFFERENT/UNRESOLVED_PLACEHOLDER、または`MANUAL_REVIEW`対象が存在する場合。`source-integrity`: hash drift） |
| 2 | CLI usage error |
| 3 | 必要なpackage required file・manifest・target rootが存在しない |
| 4 | INVALIDまたはmalformed |
| 8 | I/Oまたはcontainment/symlink/junction/reparse error |

集約優先順位: `8 > 4 > 3 > 1 > 0`。

**package側とtarget側で「MISSING」の扱いが異なる点に注意**: manifestが要求する**package側**の必須ファイルが存在しない場合は、`source-integrity`・`plan`のいずれでも exit 3（パッケージ自体の欠落は前提条件違反として扱う）。一方、**target側**のファイルが存在しない場合（`plan`で導入先にまだコピーされていない、通常の状態）は exit 1（人の対応が必要な差分として扱う）。両者とも表示上の状態ラベルは `[MISSING]` だが、`reason` 欄で `PACKAGE_FILE_MISSING` と `TARGET_MISSING` を区別しており、集計・exit codeもこの区別に従う。manifest自体の構造不正・不正なメタデータは exit 4、symlink/junction/reparse経由の実際の迂回やI/Oエラーは exit 8。

### `source-integrity` summaryの各項目

`source-integrity` の末尾summaryには、次のキーが表示される。**`compared` と `hash_compared` は同じ意味ではない**点に注意すること。

| キー | 意味 |
|---|---|
| `compared` | `manifest.json` 自身を除く、パッケージ内ファイルのうち処理を試みた件数（結果がMISSING/INVALID等であっても加算される） |
| `identical` | 状態が `IDENTICAL` だった件数 |
| `missing` | 状態が `MISSING`（パッケージ側ファイルの欠落）だった件数 |
| `different` | 状態が `DIFFERENT`（hash不一致）だった件数 |
| `invalid` | 状態が `INVALID`（非blocking）だった件数（サイズ超過・UTF-8でない・ディレクトリ/special file・宣言されていないプレースホルダー・未登録の通常ファイル/非通常ファイル等を含む）。containment/symlink/junction/reparse/I/O由来のblockingな問題は含まない（`blocking_errors` を参照） |
| `blocking_errors` | containment逸脱・symlink/junction/reparse redirect・I/O安全境界に関する、blockingな問題の件数（`[BLOCKING_ERROR]` として表示される）。1件以上あれば exit 8。`invalid` とは二重計上しない（詳細は「`INVALID`と`BLOCKING_ERROR`の区別」を参照） |
| `unresolved_placeholder` | source-integrityでは通常 `0`（`plan` 固有の状態） |
| `skipped_by_mode` | source-integrityでは常に `0`（`adoption_mode` による対象外扱いは `plan` 固有の概念であり、`manifest.json` 自身のSKIPPEDとは別概念） |
| `manual_review_required` | source-integrityでは常に `0`（`plan` 固有の概念） |
| `hash_compared` | **実際にSHA-256比較が完了した**件数のみ。`compared` に含まれていても、MISSING・INVALID（サイズ超過・宣言なしプレースホルダー等）・BLOCKING_ERROR（containment等）はここに含めない |
| `hash_matched` | `hash_compared` のうち、比較の結果ハッシュが一致した件数（`identical` の内訳と一致する） |
| `hash_mismatched` | `hash_compared` のうち、比較の結果ハッシュが不一致だった件数（`different` の内訳と一致する） |
| `self_hash_omitted` | `manifest.json` 自身の件数。常に `1`。**`manifest.json` 自身は自己のSHA-256を比較しない**（`sha256` フィールドが `null` である設計のため） |
| `manifest_valid` | manifest全体の構造検証（存在・サイズ上限・UTF-8・JSON構文・必須フィールド・self-hashルール・files/placeholders/adoption_mode等の整合）を通過していれば `1`。**ハッシュ一致件数ではない**、boolean相当の値。**個々のpackage fileがMISSING/INVALIDであるかどうかとは独立**しており、manifestの構造自体が妥当である限り、他の集計がどうであっても `1` のままである（例: 必須ファイルが1件MISSINGでも `manifest_valid: 1` かつ `final_exit: 3`）。manifestの構造自体が不正な場合はこのsummary自体が出力される前に `[BLOCKED]` として停止し、exit 4 となる |
| `unlisted_package_files` | manifestの `files` に登録されていない通常ファイルの件数（`UNLISTED_PACKAGE_FILE` reasonで報告された件数、`invalid` の内訳の一部）。symlink/reparse由来の未登録エントリはこの件数には含まれず、`[BLOCKING_ERROR]`（`blocking_errors`、exit 8）として別途報告される |
| `final_exit` | このコマンド呼び出し全体のexit code |

正常なパッケージ実行時の期待値: `compared: 30` / `identical: 30` / `invalid: 0` / `blocking_errors: 0` / `hash_compared: 30` / `hash_matched: 30` / `hash_mismatched: 0` / `self_hash_omitted: 1` / `manifest_valid: 1` / `unlisted_package_files: 0` / `final_exit: 0`。

### パス安全性

Windows・Linux・macOSを考慮し、少なくとも次を拒否する: 絶対パス、`..` traversal、UNC path、drive-relative path、target/package root外へのlexical escape、real path解決後のroot外escape、target root自体・対象ファイル・**manifest.json自身**・**途中のすべてのディレクトリ要素**がsymlink/junction/reparse pointである場合、内部redirect、FIFO/socket/device等のspecial file。`manifest.json` 自身も他の全パッケージファイルと同じcontainment検査を、読み取り前に通過する（詳細は「`source-integrity`」節の「`manifest.json` 自身のcontainment検証」を参照）。

**manifestのcanonicalなpath区切り文字**: `manifest.json` の `files[].path` および `target_path` は、プラットフォーム非依存のcanonical形式として**forward slash（`/`）のみ**を許可する。バックスラッシュ（`\`）を1文字でも含む `path` / `target_path` は、区切り文字として黙って解釈せず、`INVALID`（`path` は reason: `UNSAFE_PACKAGE_PATH`、`target_path` は reason: `UNSAFE_TARGET_PATH`、いずれも exit 4）として拒否する。これは、パッケージルート配下の未登録ファイル走査が常にforward slash区切りの相対パスを生成するため、区切り文字の表記揺れによって「登録済みのはずのファイルが走査側では未登録として検出される」といった食い違いを避けるためである。この検証は、`--set` で渡すplaceholder VALUE単体のパス要素検証（値の中に `/` や `\` を含めない、という別の検証）とは独立している。

**case-insensitive環境での衝突検出は、target_pathの最終ファイル名だけでなく、パスを構成する全ての既存パス要素（中間ディレクトリを含む）に適用する。** 各要素について、その親ディレクトリの実際のエントリ名を列挙し、大文字小文字を無視した比較（`casefold`）で一致するが完全一致（大文字小文字を含む）はしない場合、`CASE_COLLISION` として拒否する（exit 8）。containment検査は全経路で共通のヘルパーを使うが、表示は経路によって異なる——通常のpackage file・target fileに対する検出は `[BLOCKING_ERROR]`（`blocking_errors` へ加算）、`manifest.json` 自身に対する検出は `[BLOCKED]`（bootstrap段階、summary前に停止）である（詳細は「`manifest.json` 自身のcontainment検証（bootstrap検証）」を参照）。target rootはGitリポジトリでなくてもよく、verifierはGitコマンドを一切実行しない。

**既知の制限（Unicode正規化）**: ファイルシステムによっては、Unicode正規化形式（NFC/NFD等）の違いが、上記のcase-collision判定（`casefold` による名前比較）へ影響する可能性がある。この現象はWindows・Linux、および現在の開発・テスト環境では再現していない。normalization-sensitiveなファイルシステム（例: 一部のmacOS環境）における実際の挙動確認は、future portability trial（将来の移植試験）の対象とする。この制限に対する自動修正・自動renameは行わない。特定のOS・ファイルシステムの組み合わせについて「完全対応済み」とは主張しない。

### リソース上限

| 項目 | 上限 |
|---|---|
| manifest最大サイズ | 1 MiB |
| manifest files最大件数 | 500 |
| 1ファイル最大サイズ | 5 MiB |
| 1回の実行で読む合計最大サイズ | 50 MiB |
| 相対パス最大階層 | 64 |
| placeholder最大件数 | 100 |

上限超過は `INVALID` として報告する（エラーで停止させない）。`manifest.json` 自身を読み取ったバイト数も、1回の実行で読む合計最大サイズ（50 MiB）の集計へ含める（二重計上はしない）。

上限超過時の主なreason codeは次のとおり。実際に出力されるreason code名を正本とし、下表と実装が食い違う場合はコード側（`tools/verify_workflow_template.py` の各定数・エラー分岐）を正とする。

| 上限 | 主なreason code |
|---|---|
| manifest最大サイズ（1 MiB） | `MANIFEST_TOO_LARGE` |
| manifest files最大件数（500） | `MANIFEST_TOO_MANY_FILES` |
| 1ファイル最大サイズ（5 MiB） | `FILE_TOO_LARGE` |
| 1回の実行で読む合計最大サイズ（50 MiB） | `TOTAL_READ_LIMIT_EXCEEDED` |
| 相対パス最大階層（64） | `PATH_TOO_DEEP` |
| package scan entry budget（500、下記参照） | `TOO_MANY_PACKAGE_FILES` |
| placeholder最大件数（100） | `MANIFEST_TOO_MANY_PLACEHOLDERS` |

**package scan entry budget（`TOO_MANY_PACKAGE_FILES`）**: `source-integrity` のunlisted-file走査（「manifest未登録ファイルの検出」参照）が1回の実行で調べるエントリ数の上限は500である。これは `manifest.json` の `files` に登録できる最大件数（`MANIFEST_TOO_MANY_FILES`、こちらは別の上限）とは異なる、**走査が実際にディスク上で調べたエントリの総数**の上限であり、以下をすべて含む——通常ファイルだけでなく、ディレクトリ、symlink/junction/reparse point、FIFO/socket/device等のspecial entryも1件としてカウントする。500エントリまでは許可し、501件目のエントリを受理する前に走査全体を停止する（`TOO_MANY_PACKAGE_FILES` は1回の実行につき最大1件のみ報告し、それ以降の兄弟・親ディレクトリ・別branchは走査しない）。暗黙のignore一覧は設けていないため、無関係な生成物（`__pycache__` 等）もこの上限の対象になり得る。上限超過はINVALID（非blocking、exit 4）として報告し、対象ファイルの自動削除・自動manifest登録は一切行わない。

標準出力に表示してよいもの: package/target相対path（`target_path`を構成するプレースホルダー値を含むレンダリング後の相対パス）、adoption_mode、状態、固定reason code、件数、SHA-256、未解決プレースホルダー名。表示しないもの: ファイル本文、ファイル本文専用プレースホルダーのVALUE、秘密情報らしい部分文字列、APIキー・トークン、target rootの絶対パス（常に `<target-root>` と表記）、ユーザー名を含むパス、生の例外メッセージに含まれる絶対パス、不正ファイルの内容、argparseのエラーメッセージに含まれる生のCLI引数文字列（下記参照）。

**CLI引数エラーの非開示**: `argparse` の既定の挙動は、不正な引数やその値をエラーメッセージへそのまま含めることがある。本ツールは `ArgumentParser` を安全なサブクラスへ差し替え、usage error時は常に固定された安全なメッセージ（`usage error: INVALID_CLI_ARGUMENTS` 等）だけを表示し、利用者が実際に入力した引数文字列や値を一切含めない。`--help`/`-h` の出力は通常どおり表示される。

### read-only境界

verifierは、コピー・apply・install・update・uninstall・merge・backup・rename・remove・delete・mkdir・tempfileによる対象リポジトリへの書き込み・ファイルレポート出力・Git操作・`subprocess`・shell command実行・commit・push・PR・mergeのいずれも行わない。Python標準ライブラリのみを使用し、`subprocess` モジュールをimportしない。

### TOCTOU（既知の制限）

パスの安全性確認と、その後の実際の読み取りの間には、理論上のcheck-then-open競合（TOCTOU）が残る。本ツールは (1) read-only、(2) ローカル単一利用者向け、(3) point-in-timeのレポートであり、(4) マルチテナントの信頼境界ではないという前提の下、この制限をv1のスコープ外として許容している。TOCTOUを完全に排除する低レベルなfd処理は、このバージョンの対象外である。

## 検討し不採用とした配布方式

- **ドキュメントとサンプルのみで自動化を一切持たない方式**: 導入完全性を確認する手段が一切なくなるため、単独の配布方式としては不採用とした
- **フルの対話型インストーラーを最初から持つ方式**: 導入先の任意パスへ自動的に書き込みを行う機能は、read-only verifierによる状態確認すら実運用実績がない現時点では時期尚早と判断し、不採用とした
- **グローバルなプラグインとしての導入**: このワークフローはプロジェクトごとのGit・指示境界を扱うため、プロジェクトスコープで確認可能なファイル群として導入する方式を優先し、グローバル導入は不採用とした

## 関連文書

- [PLACEHOLDERS.md](PLACEHOLDERS.md) — プレースホルダー一覧
- [manifest.json](manifest.json) — 静的パッケージ在庫
- [PROJECT_RULES_SNIPPET.md](PROJECT_RULES_SNIPPET.md) — 手動貼り付け用の参考断片
- [docs/agent-workflow/README.md](docs/agent-workflow/README.md) — ワークフロー本体の入口文書
- [docs/agent-workflow/git-safety.md](docs/agent-workflow/git-safety.md) — Git安全チェックリスト
- [docs/agent-workflow/troubleshooting.md](docs/agent-workflow/troubleshooting.md) — トラブルシューティング
- [docs/agent-workflow/outcome-improvement-cycle.md](docs/agent-workflow/outcome-improvement-cycle.md) — 汎用の設計・実装・評価・採否サイクル
- [docs/agent-workflow/app-profile.md](docs/agent-workflow/app-profile.md) — App ProfileとEvidence Bundleのstrict JSON契約
- [examples/app-profiles/pokemon-ai.example.json](examples/app-profiles/pokemon-ai.example.json) — Pokemon AIのexample-only Profile
- [examples/app-profiles/rag-quality.example.json](examples/app-profiles/rag-quality.example.json) — RAG品質のexample-only Profile
