# 開発プロセステンプレート（`.claude/`）

**まず完走 → インクリメンタルに改善** で開発を進めるための、エージェント・
スキル・ツールの一式です。 **プロジェクト非依存のテンプレート** として
作られており、プロジェクト固有の値は `CLAUDE.md` の
「プロジェクトプロファイル」に集約されます。

## 設計思想

1. **動くものが最初の成果物**: 端から端まで通る骨組みを最初に作り切る。
   層の分離・網羅的な仕様・完全な文書は後から足す
2. **完璧を積み上げない**: 1 つを完璧にしてから次へ行くのではなく、
   全スライスを L1（動く）まで上げてから L2（固い）へ上げる
3. **手抜きは許す。隠すのは許さない**: 仮実装・ハードコード・層の逆流は
   負債表に書けば正式に許可される。書かずに残すことだけが規約違反
4. **環境・行動・知覚のループ**: エージェントは会話の記憶ではなく環境
   （リポジトリ・バックログ・コマンド結果）を正として動く。行動は必ず Tool を通す
5. **行動できないなら道具を作る**: 実行したい行動を遂行するツールが無ければ、
   場当たりの回避ではなくツールを新設する（`tool-authoring`）
6. **決定論的な操作を増やす**: LLM に考えさせるプロセスを最小化する。
   判断はチェックリスト・テンプレート・機械検証に置き換えていく
7. **コンテキストエンジニアリング**: 重い読み込み・長いログはサブエージェントが
   引き受け、親には要約だけを返す。状態は会話ではなく `docs/backlog.md` に置く
8. **記録して改善する**: 反復の振り返りを残し、`/improve-process` で
   プロセス自体を改善する

## 成熟度（このテンプレートの背骨）

完了条件は成熟度で段階的に変わります。
**正は `skills/agile-process/maturity.md`** 。

| レベル | 一言 | テスト | 許されること |
|---|---|---|---|
| `L1 動く` | 使える | E2E 1 本 + 芯のユニット | 仮実装・ハードコード・1 ファイル集約・層の逆流（記録必須） |
| `L2 固い` | 壊れない | 受け入れ条件ごとに 1 本以上 | 構造の不揃い・文書の未整備 |
| `L3 整った` | 渡せる | 全緑 + 回帰 | なし（他人に渡すときだけ到達する） |

検証・レビュー・文書同期はすべて **「現在 → 目標」の 1 段だけ** で判定します。
上のレベルの条件で不合格にしないのが、このテンプレートの最重要ルールです。

## 2 つのレーン

| | 工房レーン（`workshop/`） | 反復開発レーン（`docs/` + ソースルート） |
|---|---|---|
| 起点 | 思いつき・その場の困りごと | ゴール（`docs/concept.md`） |
| 単位 | ツール 1 本 / ノート 1 本 | 縦切りスライス（S##） |
| 前工程 | なし | ゴールと完走の定義 → バックログ |
| 構造 | 1 ディレクトリ完結。層構成なし | レイヤード（L1 では 1 ファイル可） |
| テスト | 必須（テスト先行） | 必須（テスト先行 + E2E） |
| 文書 | `README.md` 1 枚 | スライス 1 枚（条件 3 行 + 設計 5 行） |
| 入口 | `/tool` `/note` `/workshop` | `/backlog` `/skeleton` `/iterate` `/refactor` |
| 所要 | 数十分 | 1 反復あたり半日以内 |

**工房レーンで省くのは前工程と構造であって、テストではない。**
1 行の `summary` に収まる思いつきは工房、ゴールに寄与するものは反復開発。
迷ったら工房で作り、育ったら `/promote` で上げる。
レーンの定義・status・昇格判断は `skills/workshop/SKILL.md` が正。

## 新しいプロジェクトでの始め方

```
1. この .claude/ と CLAUDE.md（テンプレート版）をプロジェクトにコピーする
2. /setup-project        … CLAUDE.md のプロジェクトプロファイルを確定
3. /backlog init         … ゴールと完走の定義 → スライス 3〜8 本
4. /skeleton             … 骨組みを作り切る（ここまでは他のことをしない）
5. /iterate              … スライスを 1 本ずつ L1 に上げる（★ここを繰り返す）
6. /refactor             … 負債がたまったら返す
7. /improve-process      … 数反復回したらプロセスを改善する
```

工房レーンだけを使うなら手順 3 以降は要らない。プロファイルの
「コマンド」「ディレクトリ構成」だけ埋まっていれば `/tool` は動く。

### プロジェクト固有の値を書く場所（テンプレート側に埋め込まない）

| 内容 | 書く場所 |
|---|---|
| 言語・コマンド・パス・層構成・家風・安全機構 | `CLAUDE.md` のプロジェクトプロファイル |
| ゴール・完走の定義・非目標 | `docs/concept.md` |
| 進捗・優先順位・負債 | `docs/backlog.md` |
| 実行環境（コンテナ・許可する外部通信） | `.devcontainer/`（`allowed-domains.txt` ほか） |
| ディレクトリ構造のスナップショット | `.claude/skills/repository-structure/template.md` |
| 「core 無変更」の検査対象（L3 到達分のみ） | `.claude/core_files.txt` |
| 変異テストの仕様 | `.claude/mutations/S##-<対象>.json` |
| 許可コマンド（共有 / 個人）・フックの配線 | `.claude/settings.json` / `.claude/settings.local.json` |
| フックが守るパス・拒否するコマンド | `.claude/hooks/protected_paths.txt` / `denied_commands.txt` |
| 工房の成果物（ツール・ノート） | `workshop/`（テンプレートには含めない） |

これら以外に固有の値が現れたら、それはテンプレートの汚染。
プロファイルへ追い出すか、参照の形（「プロファイルの◯◯表を見る」）に直す。

`.claude/templates/workshop/` は雛形の本体（`new_tool.ps1` /
`new_note.ps1` が読む）。 **プロジェクト固有ではなくテンプレートの一部** で、
主言語の雛形を足したいときはここへ `tool-main.<lang>` と
`tool-test.<lang>` を追加する。

## 開発フロー

```
ゴール定義 → バックログ → 骨組み（完走）→ 反復 ⇄ リファクタリング → 完成
```

| 工程 | 成果物 | スキル / エージェント |
|---|---|---|
| ゴール定義 | `docs/concept.md`（一行 + 完走の定義） | concept-definition |
| バックログ | `docs/backlog.md`（スライス 3〜8 本） | agile-process |
| 骨組み | E2E 1 本 + 通る実装 + `docs/slices/S01-*.md` | walking-skeleton / integration-tester |
| 反復（薄く決める） | `docs/slices/S##-*.md` | slice-definition |
| 反復（実装） | ソース・テスト・マイクロコミット | tdd-implementer |
| 反復（通す） | E2E テスト・実物の出力 | integration-tester |
| 反復（検証） | 目標レベルの合否 | implementation-validator / security-checker |
| 反復（記録） | 成熟度・負債表の更新 | doc-syncer（チェックリスト A） |
| リファクタリング | `整理:` コミット群・負債の `済` | refactoring / refactorer |
| L3 へ（渡すとき） | `docs/design.md`・マニュアル | architecture-design / doc-syncer（B） |
| 厚い経路（例外） | 要求仕様書 + 設計書 + tasklist | requirements-definition / functional-design |
| 振り返り | プロセス改善提案 | steering（振り返りモード） |

**前工程を飛ばさないのは最初の 3 つだけ。** 骨組みが通った後は、
反復とリファクタリングを行き来します。

トレーサビリティの背骨は **スライス文書の受け入れ条件 → E2E テスト** の 1 本。
`/check-docs` はこの線の欠落と、バックログと実物の食い違いを検出します。

## 構成

### コマンド（`.claude/commands/`）

| コマンド | レーン | 用途 |
|---|---|---|
| `/backlog [init\|status\|次]` | 反復開発 | ゴールとスライス一覧・現在地・次の一手 |
| `/skeleton` | 反復開発 | 骨組みを作り切る（1 回だけ） |
| `/iterate [S##]` | 反復開発 | **既定の入口** 。成熟度を 1 段上げる |
| `/refactor [D##]` | 反復開発 | 負債を返す（振る舞い不変） |
| `/add-feature [S##]` | 反復開発 | 厚い経路（不可逆・公開・安全・データ形式のみ） |
| `/tool <説明>` | 工房 | 思いついた小さなツールを 1 本作りきる |
| `/note <内容>` | 工房 | 調べたこと・罠・決定・思いつきをノートに残す |
| `/workshop [list\|search\|tidy]` | 工房 | 工房の一覧・検索・棚卸し |
| `/promote <tool> S##` | 橋渡し | 育った工房ツールを反復開発レーンへ昇格 |
| `/setup-project` | 共通 | プロジェクトプロファイルの確定と骨組みの作成 |
| `/check-docs` | 共通 | バックログ・スライス文書・実物の整合の点検 |
| `/review-docs <path>` | 共通 | 個別文書の詳細レビュー |
| `/improve-process` | 共通 | 記録を分析してエージェント・スキル・ツールを改善 |
| `/local-mode [check\|on\|off]` | 共通 | ローカル LLM で駆動するときの適合検査とモード切り替え |

### エージェント（`.claude/agents/`）

共通プロトコルは `report-protocol.md`（知覚-行動ループ・レポート形式）。

| 種別 | エージェント |
|---|---|
| 指揮 | `orchestrator`（バックログから次の一手を 1 つ決める） |
| 調査 | `impact-analyzer`・`file-finder`・`dependency-checker`・`log-analyzer` |
| 実装 | `tdd-implementer` |
| 整理 | `refactorer`（振る舞い不変で負債を返す） |
| 実行 | `test-runner`・`build-executor` |
| 検証 | `implementation-validator`・`integration-tester`・`code-reviewer`・`security-checker`・`test-analyzer` |
| 文書 | `doc-syncer`・`doc-reviewer` |
| **工房** | `tool-smith`（ツールを 1 本作りきる）・`note-keeper`（工房の棚卸し） |

**サブエージェントを起動するときは、プロンプトに目標成熟度
（例: 「現在 L1、目標 L2」）を必ず書く。** 書き忘れると最上位の基準で
判定し、完璧の積み上げが始まる —— このテンプレートで最も多い事故。

工房レーンの 2 本は **レポート駆動を使わない** （`.steering/` を作らない）。
成果物と git 履歴が記録であり、ノートの往復は間接費になるため。
継承するのは `report-protocol.md` の 0 節（知覚-行動ループ）のみ。

### スキル（`.claude/skills/`）

| スキル | レーン | 用途 |
|---|---|---|
| **`agile-process`** | 反復開発 | **プロセスの正** （成熟度・DoD・反復の型・厚く書く判定） |
| `walking-skeleton` | 反復開発 | 骨組みを作り切る手順（E2E 先行） |
| `slice-definition` | 反復開発 | スライス 1 枚（条件 3 行 + 設計 5 行） |
| `refactoring` | 反復開発 | 負債の返し方（緑を保ち 1 手 1 コミット） |
| `layered-architecture` | 反復開発 | 層の正（逆流禁止の 1 ルール・育て方） |
| `concept-definition` | 反復開発 | ゴールと完走の定義 |
| `steering` | 反復開発 | 反復のタスク管理・レポート交換・振り返り |
| `requirements-definition` | 厚い経路 | 要求仕様書（既定ではない） |
| `functional-design` | 厚い経路 | 実装前設計書（既定ではない） |
| `architecture-design` | L3 のみ | 現状設計（`docs/design.md` 1 枚） |
| `glossary-creation` | 共通 | 用語集（必要になったら） |
| `repository-structure` | 共通 | ファイル・文書の置き場所 |
| `development-guidelines` | 共通 | コーディング・テスト・コミットの規約（成熟度別） |
| `writing-conventions` | 共通 | 文書の記法（Markdown・数式と図表の番号・作図言語・マニュアル） |
| `workshop` | 工房 | レーンの正（置き場所・命名・status・カタログ・昇格判断） |
| `quick-tool` | 工房 | ツール 1 本を作りきる 8 手順 |
| `note-taking` | 工房 | ノート 1 本の手順と記録先の判定 |
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
| `check_unchanged.py` | 中核ファイル（L3 到達分）の「core 無変更」を検証 | git・`core_files.txt` の記入 |
| `mutate.py` | 変異テストでテストの有効性を検証 | 非 0 で失敗を返すテストコマンド |
| `check_llm_endpoint.py` | ローカル LLM のエンドポイントが Claude Code を駆動できるか検査 | 変換プロキシ（Anthropic 形式） |
| `new_tool.ps1` | 工房ツールの雛形を生成（README・実装・テストの 3 点） | PowerShell・`.claude/templates/workshop/` |
| `new_note.ps1` | 工房ノートの雛形を生成（日付 + slug） | PowerShell・同上 |
| `index_workshop.ps1` | `CATALOG.md` と `notes/INDEX.md` を再生成（`-Check` で差分検出） | PowerShell |

`.py` ツールの前置コマンドは、プロファイルの
「`.claude/tools/` の Python ツール実行」に書いた値を使う（推測しない）。

図・番号の検証ツールが効くのは **L3 に上げるとき** （L1・L2 のスライス文書に
図は書かない）。

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

- 反復ごとの振り返りで **プロセス改善提案** を必ず書く
  （tasklist.md の表。出典は `reports/` の知覚・行動ログ）
- 特に次の 2 つはこのプロセス特有の失敗なので優先して記録する:
  **目標より上のレベルの作業をした**（成熟度の指示漏れ）/
  **スライスが半日で終わらなかった**（切り方の失敗）
- 数反復ごとに `/improve-process` を実行し、提案を実際の変更に落とす
- 改善は「その場の指示」ではなく **定義** に対して行う。次に同じ迷いが
  起きないようにして初めて育ったことになる
- プロジェクト固有の学びは `CLAUDE.md` のプロファイルへ、プロセス一般の
  学びは `.claude/` のテンプレートへ振り分ける
