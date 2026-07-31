# トラブルシューティング

導入・運用中によく起こりうる事象と、その扱い方をまとめる。各項目に、継承元の文書・節、または「新規ガイダンス」の別を明記する。

**共通の注意**: 診断のためにコマンド出力やログを貼り付ける・共有する場合、APIキー・トークン・認証情報・ユーザー名を含む絶対パス・その他の個人固有情報を出力へ含めない。含まれていないか確認してから共有すること。

## MCP serverが `/mcp` に表示されない

- 症状: Claude Code内の `/mcp` を開いても `{{MCP_SERVER_NAME}}` が一覧に出ない、または `connected` にならない。
- 確認: `.mcp.json` の内容（サーバー名・起動コマンド）、プロジェクトスコープのMCPサーバー承認プロンプトを承認したか、`.mcp.json` 変更後にClaude Codeを再起動したか。
- 継承元: `mcp-connection.md` の「手動確認手順」

## `codex` / `codex-reply` ツールが利用できない

- 症状: `/mcp` では接続済みに見えるが、`codex` / `codex-reply` ツールの呼び出しが失敗する、またはツールとして見つからない。
- 確認: 期待されるMCPツール（`codex`、`codex-reply`）が2つとも表示されているか、Codex CLI自体がログイン済みか。
- 継承元: `mcp-connection.md` の「期待されるMCPツール」節

## subagentが見つからない

- 症状: Agentツールで `requirements-auditor` / `simplifier` / `claude-architect` / `design-judge` を指定しても認識されない。
- 確認: `.claude/agents/` 配下に4ファイルが正しく配置されているか、frontmatterの `name:` フィールドが一致しているか。Claude Codeのバージョンによっては `/agents` の一覧ウィザードが使えない場合があるが、それ自体はAgentツールによる直接起動を妨げない。
- 継承元: `subagents.md` の「手動確認手順」

## Skillが表示されない・起動しない

- 症状: `/{{DESIGN_SKILL_NAME}}` を入力しても認識されない。
- 確認: `.claude/skills/{{DESIGN_SKILL_NAME}}/SKILL.md` の配置パス（ディレクトリ名とfrontmatterの `name:` が一致しているか）、Claude Codeの再起動有無。
- 継承元: `multi-agent-design-skill.md` の「Skillの場所とSkill名」

## Windows Git Bashで `{{CODEX_COMMAND}}` / `claude` コマンドが見つからない

- 症状: Windows Git Bash上で `command -v {{CODEX_COMMAND}}` や `command -v claude` が解決しない、または `codex mcp-server` の起動に失敗する。
- 確認: PowerShellと異なるPATH設定になっていないか、同一環境（同じシェル）内でインストール・確認を行っているか。
- 新規ガイダンスであり、元文書からの直接継承ではない

## read-only roleが書き込みを提案した

- 症状: `requirements-auditor` / `simplifier` / `claude-architect` / `design-judge` の出力テキストが、ファイル編集やコマンド実行を「提案」している。
- 対応: これらのエージェントは `tools: Read, Glob, Grep` のみを許可されており、実際にファイルを編集・実行する権限を持たない。テキストとしての提案があっても、それを実行するかどうかはImplementation Owner（親セッション）およびユーザーの判断に委ねる。実際にツール権限を超えて書き込みが実行された場合は、設計上の誤りとして報告する。
- 継承元: `subagents.md` の「全エージェントread-onlyであること」、および各エージェント定義の `Boundaries` 節

## Evidence limitation（一次証拠を再確認できない）

- 症状: レビュー・設計ロールが、リポジトリのファイルを読めない、またはコマンドを実行できない状態で意見を返している。
- 対応: そのロール自身の出力に、何を確認でき何を確認できなかったかを明記させる。確認できなかった主張は、他の完全確認済み証拠と同列に扱わない。後続のDesign Judgeが、判断に重要な事実を自らRead/Glob/Grepで再確認する。
- 継承元: `multi-agent-design-skill.md` の「Evidence limitation」節

## sandbox環境でリポジトリを読めない

- 症状: Codex MCP呼び出し（`codex` / `codex-reply`）が、sandbox/環境側の問題によりファイル読み取り前に失敗する。
- 対応: 同一スレッドで一度リトライし、非一過性の失敗であれば無理に繰り返さない。読めなかった事実をEvidence limitationとして明記させ、内部整合性のみで評価させる。実際にファイル内容を読めていない主張は、Confirmedとして扱わない。
- 新規ガイダンスであり、元文書からの直接継承ではない（上記「Evidence limitation」節の考え方を、sandbox読み取り失敗という具体的事象へ適用したもの）

## thread継続（`codex-reply`）に失敗した

- 症状: 既存のCodexスレッドへ `codex-reply` で継続しようとしても、応答が得られない、または想定した文脈が失われている。
- 確認: 同一議論の継続には新規スレッドを開かず、既存の `threadId` を使う方針になっているか（`threadId` 自体はファイル・commit・PR本文へ保存しない）。
- 継承元: `multi-agent-design-skill.md` の「Codex threadの再利用方針」

## MCPサーバー承認プロンプトが繰り返し発生する

- 症状: `.mcp.json` を変更するたびに、プロジェクトスコープのMCPサーバー承認プロンプトが再度表示される。
- 対応: 内容を確認した上でユーザーが承認する。これは想定された挙動であり、プロンプトの内容を確認せずに承認しない。
- 継承元: `mcp-connection.md` の「手動確認手順」

## dirty worktree（未コミットの変更がある状態）

- 症状: 作業開始前に `git status --short` が空でない。
- 対応: 既存の変更を破棄せず、その内容を踏まえて作業する。対象タスクに関係のない変更を巻き込んでstage・commitしない。
- 継承元: `git-safety.md` の項目1・2

## 導入先に既存の `.mcp.json` がある場合の競合

- 症状: 導入先プロジェクトにすでに `.mcp.json` が存在し、このテンプレートの `.mcp.json` と内容が異なる。
- 対応: 自動マージは行わない。既存ファイルの内容を人が確認し、必要なサーバー設定（`{{MCP_SERVER_NAME}}` のエントリ）だけを手動で追記するかどうかを判断する。既存の他サーバー設定を消さない。
- 新規ガイダンスであり、元文書からの直接継承ではない

## Plan reports DIFFERENT immediately after manual copy

- 症状: 手動コピー直後にもかかわらず、`plan` が対象ファイルを `DIFFERENT` として報告する。内容を見た目で比較すると同じに見える。
- 主な原因:
  - CRLF/LFの変換（text modeでの読み込み・保存による自動変換を含む）
  - 末尾改行の追加・削除
  - BOMの追加・削除
  - encodingの変更
  - JSON formatterによる再format（インデント・改行位置の変更）
  - Markdown formatterによる再format
  - エディタの保存時自動整形（末尾空白除去・改行コード統一等）
  - プレースホルダー置換処理自体がtext modeの読み書きを経由したことによる変換
- 確認方法:
  - `plan` はファイル本文を表示しない。`plan` は、プレースホルダー置換後のpackage bytesと、target fileのraw bytesを直接比較する（`BYTE_IDENTICAL` / `BYTE_DIFFERENT`）。SHA-256はこの比較には使用しない
  - SHA-256を比較判定に使用するのは `source-integrity`（manifestに登録されたexpected SHA-256と、package fileのSHA-256を比較する）であり、`plan` とは別のサブコマンド・別の比較対象である
  - operatorが原因調査の補助として、source側とtarget側のファイルのSHA-256を別途手元で計算して見比べることは可能だが、これは `plan` 自体の比較アルゴリズムではなく、あくまで人が行う診断作業である
  - ファイル本文や秘密情報らしい内容をログへ出さない
  - newlineやBOMの有無を調べる際も、ファイル本文全体を出力しない（バイト数・改行コードの種類など、必要最小限の情報にとどめる）
  - source側の不変性は、`source-integrity` で確認できる（`plan` ではなく、こちらがSHA-256ベースの比較を行う）
- 対応:
  - プレースホルダーを含まないファイルは、raw byte copyで再配置する
  - プレースホルダーを含むファイルは、bytesとして読み込み・decode・置換・encode・bytesとして書き込む（詳細はREADME.mdの「Binary-safe manual adoption」節を参照）
  - target側のファイルを手動で正しい内容へ修正する
  - `plan` を再実行し、`IDENTICAL` へ戻ったことを確認する
- 継承元: disposable portability trial（README.mdの「Portability validation」節を参照）で確認した事象に基づく新規ガイダンス

## Manual merge remains DIFFERENT

- 症状: `MANUAL_REVIEW` 対象（`.mcp.json`）を、既存のserver設定を保持したまま手動でmergeしたが、`plan` を再実行しても `IDENTICAL` にならず `DIFFERENT` のまま。
- 説明:
  - 既存serverを保持した手動mergeの結果は、パッケージ原本とはbyte-identicalにならないのが通常である
  - `DIFFERENT` と報告されること、およびそれに伴い `plan` のexit codeが1のままであることは、想定される結果であり異常ではない
  - semantic correctness（統合内容が意味的に正しいかどうか）は、常に人が確認する
  - verifierは自動マージや、JSON等のsemantic comparison（意味的な同値判定）を一切行わない。厳密なbyte comparisonのみを行う
- 対応: 統合内容（既存key・新規keyの両方が意図どおり存在するか、JSONとして有効かなど）を人が別途確認する。`DIFFERENT` の解消自体を目標にしない。
- 継承元: disposable portability trial（README.mdの「Portability validation」節を参照）で確認した事象に基づく新規ガイダンス
