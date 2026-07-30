# 開発プロセステンプレート（`.claude/`）

クリーンアーキテクチャ + TDD で開発を進めるための、エージェント・スキル・
ツールの一式です。 **プロジェクト非依存のテンプレート** として作られており、
プロジェクト固有の値は `CLAUDE.md` の「プロジェクトプロファイル」に集約されます。

## 設計思想

1. **環境・行動・知覚のループ**: エージェントは会話の記憶ではなく環境
   （リポジトリ・ノート・コマンド結果）を正として動く。行動は必ず Tool を通す
2. **行動できないなら道具を作る**: 実行したい行動を遂行するツールが無ければ、
   場当たりの回避ではなくツールを新設する（`tool-authoring`）
3. **決定論的な操作を増やす**: LLM に考えさせるプロセスを最小化する。
   判断はチェックリスト・テンプレート・機械検証に置き換えていく
4. **コンテキストエンジニアリング**: 重い読み込み・長いログはサブエージェントが
   引き受け、親には要約だけを返す。状態は会話ではなく `.steering/` に置く
5. **記録して改善する**: 環境・行動・知覚を `.steering/` に記録し、
   後から `/improve-process` でプロセス自体を改善する

## 2 つのレーン

このテンプレートは **重さの違う 2 本の道** を持つ。依頼が来たら
まずどちらのレーンかを決める。

| | 工房レーン（`workshop/`） | 本開発レーン（`docs/` + ソースルート） |
|---|---|---|
| 起点 | 思いつき・その場の困りごと | 全体構想のフェーズ計画 |
| 単位 | ツール 1 本 / ノート 1 本 | フェーズ（P##） |
| 前工程 | なし | 要求仕様書 → 設計書 → 作業計画 |
| 構造 | 1 ディレクトリ完結。層構成なし | 4 層クリーンアーキテクチャ |
| テスト | 必須（テスト先行） | 必須（TDD + 統合テスト） |
| 文書 | `README.md` 1 枚 | 要求・設計・現状設計・リファレンス・マニュアル |
| 入口 | `/tool` `/note` `/workshop` | `/add-feature P##` |
| 所要 | 数十分 | 数時間〜数日 |

**工房レーンで省くのは前工程と構造であって、テストではない。**
1 行の `summary` に収まる思いつきは工房、フェーズ計画に載るものは本開発。
迷ったら工房で作り、育ったら `/promote` で上げる。
レーンの定義・status・昇格判断は `skills/workshop/SKILL.md` が正。

## 新しいプロジェクトでの始め方

```
1. この .claude/ と CLAUDE.md（テンプレート版）をプロジェクトにコピーする
2. /setup-project        … CLAUDE.md のプロジェクトプロファイルを確定
3. /tool …  /note …      … 思いついた道具とノートを工房に貯める（軽い方）
4. /add-feature P01      … 最初のフェーズを要求仕様から通しで実装（重い方）
5. /improve-process      … 数フェーズ回したらプロセスを改善する
```

工房レーンだけを使うなら手順 4 は要らない。プロファイルの
「コマンド」「ディレクトリ構成」だけ埋まっていれば `/tool` は動く。

### プロジェクト固有の値を書く場所（テンプレート側に埋め込まない）

| 内容 | 書く場所 |
|---|---|
| 言語・コマンド・パス・層構成・家風・安全機構 | `CLAUDE.md` のプロジェクトプロファイル |
| 実行環境（コンテナ・許可する外部通信） | `.devcontainer/`（`allowed-domains.txt` ほか） |
| ディレクトリ構造のスナップショット | `.claude/skills/repository-structure/template.md` |
| 「core 無変更」の検査対象 | `.claude/core_files.txt` |
| 変異テストの仕様 | `.claude/mutations/P##-<対象>.json` |
| 許可コマンド（共有 / 個人）・フックの配線 | `.claude/settings.json` / `.claude/settings.local.json` |
| フックが守るパス・拒否するコマンド | `.claude/hooks/protected_paths.txt` / `denied_commands.txt` |
| 工房の成果物（ツール・ノート） | `workshop/`（テンプレートには含めない） |

これら 8 つ以外に固有の値が現れたら、それはテンプレートの汚染。
プロファイルへ追い出すか、参照の形（「プロファイルの◯◯表を見る」）に直す。

`.claude/templates/workshop/` は雛形の本体（`new_tool.ps1` /
`new_note.ps1` が読む）。 **プロジェクト固有ではなくテンプレートの一部** で、
主言語の雛形を足したいときはここへ `tool-main.<lang>` と
`tool-test.<lang>` を追加する。

## 開発フロー

```
要求仕様書 → 設計書 → 作業計画 → TDD 実装 → 実装検証 → 統合テスト → 文書同期 → 振り返り
```

| 工程 | 成果物 | スキル / エージェント |
|---|---|---|
| 要求仕様 | `docs/requirements/P##-*.md` | requirements-definition |
| 設計 | `docs/design/proposals/P##-*.md` | functional-design / impact-analyzer |
| 作業計画 | `.steering/<dir>/tasklist.md` | steering（計画モード） |
| TDD 実装 | ソース・テスト・マイクロコミット | steering（実装モード）/ tdd-implementer |
| 実装検証 | 検証レポート | implementation-validator / security-checker |
| 統合テスト | 統合テスト・受け入れ条件の対応表 | integration-tester |
| 文書同期 | 現状設計書・リファレンス・マニュアル | architecture-design / doc-syncer |
| 振り返り | プロセス改善提案 | steering（振り返りモード） |

この表はフェーズ（P##）ごとに回る工程。その前段に **工程0: 全体構想**
（`docs/concept.md` / concept-definition スキル）があり、こちらは
プロジェクトに 1 回だけ書く。方針が変わったときだけ更新する。

要求仕様書の **受け入れ条件** が、統合テストの契約になります。
この 1 本の線（要求 → 設計の充足方針表 → 統合テスト）がトレーサビリティの
背骨であり、`/check-docs` はこの線の欠落を検出します。

## 構成

### コマンド（`.claude/commands/`）

| コマンド | レーン | 用途 |
|---|---|---|
| `/tool <説明>` | 工房 | 思いついた小さなツールを 1 本作りきる |
| `/note <内容>` | 工房 | 調べたこと・罠・決定・思いつきをノートに残す |
| `/workshop [list\|search\|tidy]` | 工房 | 工房の一覧・検索・棚卸し |
| `/promote <tool> P##` | 橋渡し | 育った工房ツールを本開発レーンへ昇格 |
| `/setup-project` | 共通 | プロジェクトプロファイルの確定と骨組みの作成 |
| `/add-feature P##` | 本開発 | フェーズを要求仕様から文書反映まで通しで実行 |
| `/check-docs` | 本開発 | 文書の存在・整合・トレーサビリティ・同期漏れの点検 |
| `/review-docs <path>` | 本開発 | 個別文書の詳細レビュー |
| `/improve-process` | 共通 | 記録を分析してエージェント・スキル・ツールを改善 |
| `/local-mode [check\|on\|off]` | 共通 | ローカル LLM で駆動するときの適合検査とモード切り替え |

### エージェント（`.claude/agents/`）

共通プロトコルは `report-protocol.md`（知覚-行動ループ・レポート形式）。

| 種別 | エージェント |
|---|---|
| 指揮 | `orchestrator` |
| 調査 | `impact-analyzer`・`file-finder`・`dependency-checker`・`log-analyzer` |
| 実装 | `tdd-implementer` |
| 実行 | `test-runner`・`build-executor` |
| 検証 | `implementation-validator`・`integration-tester`・`code-reviewer`・`security-checker`・`test-analyzer` |
| 文書 | `doc-syncer`・`doc-reviewer` |
| **工房** | `tool-smith`（ツールを 1 本作りきる）・`note-keeper`（工房の棚卸し） |

工房レーンの 2 本は **レポート駆動を使わない** （`.steering/` を作らない）。
成果物と git 履歴が記録であり、ノートの往復は間接費になるため。
継承するのは `report-protocol.md` の 0 節（知覚-行動ループ）のみ。

### スキル（`.claude/skills/`）

| スキル | レーン | 用途 |
|---|---|---|
| `workshop` | 工房 | レーンの正（置き場所・命名・status・カタログ・棚卸し・昇格判断） |
| `quick-tool` | 工房 | ツール 1 本を作りきる 8 手順 |
| `note-taking` | 工房 | ノート 1 本の手順と記録先の判定 |
| `writing-conventions` | 共通 | 文書の記法（Markdown・数式と図表の番号・作図言語・マニュアル） |
| `development-guidelines` | 共通 | コーディング・テスト・プロセスの規約 |
| `concept-definition` | 本開発 | 全体構想の作成・更新（工程0。狙い・非目標・割り切り・脅威モデル・フェーズ計画） |
| `requirements-definition` | 本開発 | 要求仕様書の作成（受け入れ条件の書き方） |
| `functional-design` | 本開発 | 実装前設計書の作成 |
| `architecture-design` | 本開発 | 現状設計書の更新 |
| `repository-structure` | 本開発 | 新規ファイルの配置判定 |
| `steering` | 本開発 | 作業計画・進捗管理・振り返り |
| `glossary-creation` | 本開発 | 用語集の作成・更新 |
| `tool-authoring` | 共通 | **開発プロセス自体** の道具（`.claude/tools/`）の新設フロー |

> `quick-tool`（`workshop/tools/`）と `tool-authoring`（`.claude/tools/`）は
> 別物。前者はユーザーの作業を助ける道具で、思いついたら作ってよい。
> 後者は開発プロセスを機械化する道具で、反復性・決定論性・事故実績の
> 3 つを満たすときだけ作る。

### ツール（`.claude/tools/`）

決定論的な操作のスクリプト。 **一覧と使い方は `tool-authoring` スキルの
「ツール一覧」を正とする** （下表は索引）。

| ツール | 用途 | 前提 |
|---|---|---|
| `check_diagrams.ps1` | Mermaid / PlantUML / Graphviz の図を構文検証 | PowerShell・各作図ツールチェーン |
| `check_numbering.ps1` | 数式・図・表の番号（DUP / GAP / UNREF / DANGL）を検証 | PowerShell |
| `check_mermaid.ps1` | Mermaid 専用の旧ツール（互換のため残置） | PowerShell |
| `check_doc_examples.py` | マニュアルの Python 例を実行して出力を照合 | Python プロジェクト |
| `check_unchanged.py` | 中核ファイルの「core 無変更」を検証 | git・`core_files.txt` の記入 |
| `mutate.py` | 変異テストでテストの有効性を検証 | 非 0 で失敗を返すテストコマンド |
| `check_llm_endpoint.py` | ローカル LLM のエンドポイントが Claude Code を駆動できるか検査 | 変換プロキシ（Anthropic 形式） |
| `new_tool.ps1` | 工房ツールの雛形を生成（README・実装・テストの 3 点） | PowerShell・`.claude/templates/workshop/` |
| `new_note.ps1` | 工房ノートの雛形を生成（日付 + slug） | PowerShell・同上 |
| `index_workshop.ps1` | `CATALOG.md` と `notes/INDEX.md` を再生成（`-Check` で差分検出） | PowerShell |

`.py` ツールの前置コマンドは、プロファイルの
「`.claude/tools/` の Python ツール実行」に書いた値を使う（推測しない）。

### ローカル LLM 対応（`.claude/local-llm/`）

**既定は Claude Code の基盤モデル（Opus / Sonnet / Haiku）** 。
gemma・qwen などのローカルモデルで駆動するときだけ、ここを使う。

| ファイル | 役割 |
|---|---|
| `README.md` | 接続手順・環境変数・トラブル対応（正） |
| `env.example.ps1` / `env.example.sh` | 接続先とモデルの環境変数の雛形 |
| `settings.json` | `claude --settings` で重ねる設定（拡張思考の無効化・出力上限など） |
| `policy.md` | 小型モデル運用規則（1 ターン 1 タスク・無停止禁止・再開手順） |

切り替えは `/local-mode`。適合検査は `.claude/tools/check_llm_endpoint.py`
（`tools` が落ちる構成では Claude Code は動かない）。
モードの状態は `.steering/local-mode.md` の有無で表し、
SessionStart フックが毎回報告する（会話ではなく環境に状態を置く）。

### フック（`.claude/hooks/`）

ツールは「LLM が呼べば走る」もの、フックは **ハーネスが必ず走らせる**
もの。守り漏れが許されない検査・記録・通知をここに置く。
配線は `.claude/settings.json` の `hooks`、詳細は
`.claude/hooks/README.md` を正とする。

| フック | イベント | 役割 |
|---|---|---|
| `pre-tool-guard.ps1` | PreToolUse | 保護パスの編集・破壊的コマンドを拒否 |
| `post-edit-markdown.ps1` | PostToolUse | 編集した Markdown の番号（+図）を検証 |
| `post-edit-lint.ps1` | PostToolUse | 編集したソースに整形・lint を掛ける（未配線） |
| `notify.ps1` | Notification | 入力待ちを音で知らせる |
| `stop-uncommitted.ps1` | Stop | 未コミットのまま終わったら知らせる |
| `session-start-context.ps1` | SessionStart | ブランチ・未コミット・プロファイル未整備を文脈へ注入 |

## 育て方

このテンプレートは使うほど良くなるように作られています。

- フェーズごとの振り返りで **プロセス改善提案** を必ず書く
  （tasklist.md の表。出典は `reports/` の知覚・行動ログ）
- 数フェーズごとに `/improve-process` を実行し、提案を実際の変更に落とす
- 改善は「その場の指示」ではなく **定義** に対して行う。次に同じ迷いが
  起きないようにして初めて育ったことになる
- プロジェクト固有の学びは `CLAUDE.md` のプロファイルへ、プロセス一般の
  学びは `.claude/` のテンプレートへ振り分ける
