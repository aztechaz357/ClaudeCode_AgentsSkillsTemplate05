# 開発プロセステンプレート（`.claude/`）

**まず完走 → インクリメンタルに改善** で開発を進めるための、エージェント・
スキル・ツールの一式です。 **プロジェクト非依存のテンプレート** として
作られており、プロジェクト固有の値は `CLAUDE.md` の
「プロジェクトプロファイル」に集約されます。

## 設計思想

1. **動くものが最初の成果物**: 端から端まで通る骨組みを最初に作り切る。
   網羅的な仕様・詳細な文書は後の反復で厚くする
2. **省くのは分量であって、成果物の種類ではない**: 要求仕様書・設計書・
   単体テスト・実装・統合テスト・テスト結果まとめ・マニュアルの
   **7 点を毎反復そろえる** 。代わりに 1 枚ずつを極端に薄くする
3. **完璧を積み上げない**: 1 つを完璧にしてから次へ行くのではなく、
   全スライスを L1（動く）まで上げてから L2（固い）へ上げる
4. **手抜きは許す。隠すのは許さない**: 仮実装・ハードコードは
   負債表に書けば正式に許可される。書かずに残すことだけが規約違反
5. **判断は理由と却下案ごと残す**: なぜそう考えたか・他の選択肢・
   メリデメを設計書の「判断の記録」に書く。結論だけの文書は次に触る人に
   同じ検討をやり直させる
6. **環境・行動・知覚のループ**: エージェントは会話の記憶ではなく環境
   （リポジトリ・バックログ・コマンド結果）を正として動く。行動は必ず Tool を通す
7. **行動できないなら道具を作る**: 実行したい行動を遂行するツールが無ければ、
   場当たりの回避ではなくツールを新設する（`tool-authoring`）
8. **決定論的な操作を増やす**: LLM に考えさせるプロセスを最小化する。
   判断はチェックリスト・テンプレート・機械検証に置き換えていく
9. **コンテキストエンジニアリング**: 重い読み込み・長いログはサブエージェントが
   引き受け、親には要約だけを返す。状態は会話ではなく `docs/backlog.md` に置く
10. **記録して改善する**: 反復の振り返りを残し、`/improve-process` で
   プロセス自体を改善する

## 成熟度（このテンプレートの背骨）

完了条件は成熟度で段階的に変わります。
**正は `skills/agile-process/maturity.md`** 。

| レベル | 一言 | テスト | 許されること |
|---|---|---|---|
| `L1 動く` | 使える | E2E 1 本 + 芯のユニット | 仮実装・ハードコード（記録必須） |
| `L2 固い` | 壊れない | 仕様ごとに 1 本以上 | 構造の不揃い・記述の粗さ |
| `L3 整った` | 渡せる | 全緑 + 回帰 | なし（他人に渡すときだけ到達する） |

検証・レビュー・文書同期はすべて **「現在 → 目標」の 1 段だけ** で判定します。
上のレベルの条件で不合格にしないのが、このテンプレートの最重要ルールです。

**どのレベルでも成果物の種類は 7 点で固定** （正: `skills/agile-process/
deliverables.md`）。レベルで変わるのは各成果物の深さだけで、
「L1 だからマニュアルは書かない」のような省略はどのレベルでも認められません。

## 成果物 7 点セット（スライス 1 本が生むもの）

| # | 成果物 | 置き場所 | 担当エージェント |
|---|---|---|---|
| 1 | 要求仕様書 | `docs/usdm/src/S##-*.html`（＋トレース表） | `requirement-writer` |
| 2 | 設計書 | `docs/design/S##-*.md`（図＋判断の記録） | `designer` |
| 3 | 単体テスト | テストルート（Red 確認まで） | `unit-tester` |
| 4 | 実装 | ソースルート（Green まで） | `coder` |
| 5 | 統合テスト | 統合テストルート | `integration-tester` |
| 6 | テスト結果まとめ | `docs/test-reports/S##-*.md` | `test-summarizer` |
| 7 | マニュアル | `docs/manual.md`（共通 3 節＋`## S##`） | `manual-writer` |

そろっているかは目視で数えず、終了コードで判定します:

```
<ツール実行コマンド> .claude/tools/check_deliverables.py   # 7 点の存在と形
<ツール実行コマンド> .claude/tools/build_usdm.py           # 仕様ごとの線（トレース）
```

**1 つでも次の反復へ送ったら、その 1 つは二度と書かれない** ——
このプロセスで最も重い失敗です。

## 2 つのレーン

| | 工房レーン（`workshop/`） | 反復開発レーン（`docs/` + ソースルート） |
|---|---|---|
| 起点 | 思いつき・その場の困りごと | ゴール（`docs/concept.md`） |
| 単位 | ツール 1 本 / ノート 1 本 | 縦切りスライス（S##） |
| 前工程 | なし | ゴールと完走の定義 → バックログ |
| 構造 | 1 ディレクトリ完結。層構成なし | クリーンアーキテクチャ（4 層 + 契約） |
| テスト | 必須（テスト先行） | 必須（テスト先行 + E2E） |
| 文書 | `README.md` 1 枚 | **7 点セット**（要求・設計・テスト結果・マニュアル ほか） |
| 入口 | `/tool` `/note` `/workshop` | `/backlog` `/skeleton` `/iterate` `/status` `/refactor` |
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
6. /status               … 現在地を 1 画面で確認する（いつでも）
7. /refactor             … 負債がたまったら返す
8. /improve-process      … 数反復回したらプロセスを改善する
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
| ディレクトリ構成（生成物） | `docs/structure.md`（`build_structure.py` が生成） |
| ディレクトリの説明（人が書く） | `.claude/structure-notes.txt`（`パス <TAB> 説明`） |
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
| 骨組み | 7 点セット（S01）＋ 4 層と契約 1 本 | walking-skeleton |
| 反復 段1 | `docs/usdm/src/S##-*.html`（要求・理由・仕様） | usdm / requirement-writer |
| 反復 段2 | `docs/design/S##-*.md`（図・層・契約・判断の記録） | functional-design / designer |
| 反復 段3 | 単体テスト（Red 確認まで） | development-guidelines / unit-tester |
| 反復 段4 | 実装（Green まで）・マイクロコミット | layered-architecture / coder |
| 反復 段5 | E2E テスト・実物の出力 | integration-tester |
| 反復 段6 | `docs/test-reports/S##-*.md` | test-reporting / test-summarizer |
| 反復 段7 | `docs/manual.md` の `## S##` 節 | writing-conventions / manual-writer |
| 反復 段8 | 目標レベルの合否・記録の同期 | implementation-validator / doc-syncer |
| リファクタリング | `整理:` コミット群・負債の `済` | refactoring / refactorer |
| L3 へ（渡すとき） | `docs/design.md` へ統合・マニュアルの深化 | architecture-design / doc-syncer（B） |
| 厚い経路（例外） | 網羅した要求仕様書 + 設計書 + tasklist | requirements-definition / functional-design |
| 振り返り | プロセス改善提案 | steering（振り返りモード） |

**前工程を飛ばさないのは最初の 3 つだけ。** 骨組みが通った後は、
反復とリファクタリングを行き来します。

トレーサビリティの背骨は
**要求 →（理由）→ 仕様 → 設計 / 実装 / 単体テスト / 統合テスト / マニュアル** 。
要求は USDM を HTML の表（Excel の USDM テンプレート相当）で書き、
その下の **トレース表** が仕様 1 条から 5 つの成果物へ線を引く。

```
REQ2「列を指定して絞り込みたい」
  └ 理由「実データが 5 万行あり、全件出ると目で探すことになる」
      └ 仕様 2-1 ☑
          ├ 設計       docs/design/S02-filter.md#構成
          ├ 実装       src/tool/application/filter.py::filter_rows
          ├ 単体テスト test/application/test_filter.py::test_完全一致で絞り込む
          ├ 統合テスト test/e2e/test_cli.py::test_列指定で件数が出る
          └ マニュアル docs/manual.md#S02
```

理由の欠落・番号の不整合・ **検証済み（`☑`）の仕様の線の切れ** は
`build_usdm.py` が終了コードで落とす（LLM の判断に頼らない）。
同じツールが全スライスを束ねた **要求一覧 1 枚**（`docs/usdm/index.html`）を
生成する。`check_deliverables.py` はスライス単位で 7 点の存在を、
`/check-docs` はバックログと実物の食い違いを検出します。

## 構成

### コマンド（`.claude/commands/`）

| コマンド | レーン | 用途 |
|---|---|---|
| `/backlog [init\|status\|次]` | 反復開発 | ゴールとスライス一覧・現在地・次の一手 |
| `/skeleton` | 反復開発 | 骨組みを作り切る（1 回だけ） |
| `/iterate [S##]` | 反復開発 | **既定の入口** 。7 点セットをそろえ成熟度を 1 段上げる |
| `/status` | 反復開発 | **現在地を 1 画面に** （ゴール・充足・負債・直近の作業） |
| `/refactor [D##]` | 反復開発 | 負債を返す（振る舞い不変） |
| `/add-feature [S##]` | 反復開発 | 厚い経路（不可逆・公開・安全・データ形式のみ） |
| `/tool <説明>` | 工房 | 思いついた小さなツールを 1 本作りきる |
| `/note <内容>` | 工房 | 調べたこと・罠・決定・思いつきをノートに残す |
| `/workshop [list\|search\|tidy]` | 工房 | 工房の一覧・検索・棚卸し |
| `/promote <tool> S##` | 橋渡し | 育った工房ツールを反復開発レーンへ昇格 |
| `/setup-project` | 共通 | プロジェクトプロファイルの確定と骨組みの作成 |
| `/check-docs` | 共通 | 7 点セット・バックログ・実物の整合の点検（機械検証つき） |
| `/review-docs <path>` | 共通 | 個別文書の詳細レビュー |
| `/improve-process` | 共通 | 記録を分析してエージェント・スキル・ツールを改善 |
| `/local-mode [check\|on\|off]` | 共通 | ローカル LLM で駆動するときの適合検査とモード切り替え |

### エージェント（`.claude/agents/`）

共通プロトコルは `report-protocol.md`（知覚-行動ループ・レポート形式）。

| 種別 | エージェント |
|---|---|
| 指揮 | `orchestrator`（バックログから次の一手を 1 つ決める） |
| **7 点セットの担当（段1〜7）** | `requirement-writer` → `designer` → `unit-tester` → `coder` → `integration-tester` → `test-summarizer` → `manual-writer` |
| 調査 | `impact-analyzer`・`file-finder`・`dependency-checker`・`log-analyzer` |
| 整理 | `refactorer`（振る舞い不変で負債を返す） |
| 実行 | `test-runner`・`build-executor` |
| 検証 | `implementation-validator`・`code-reviewer`・`security-checker`・`test-analyzer` |
| 文書 | `doc-syncer`・`doc-reviewer` |
| **工房** | `tool-smith`（ツールを 1 本作りきる）・`note-keeper`（工房の棚卸し） |

**成果物 1 つにつき担当は 1 体だけ。責務を重ねない。**
特に `unit-tester`（テストを書いて Red まで）と `coder`（Red を消す）を
分けているのは、同じ役が両方を書くと「通しやすいテスト」になるためです。
役割間の受け渡しは `.steering/<反復>/reports/` を通します
（順序と読むべきレポートは `report-protocol.md` の 0.1 節が正）。

**サブエージェントを起動するときは、プロンプトに目標成熟度
（例: 「現在 L1、目標 L2」）を必ず書く。** 書き忘れると最上位の基準で
判定し、完璧の積み上げが始まる —— このテンプレートで最も多い事故。

工房レーンの 2 本は **レポート駆動を使わない** （`.steering/` を作らない）。
成果物と git 履歴が記録であり、ノートの往復は間接費になるため。
継承するのは `report-protocol.md` の 0 節（知覚-行動ループ）のみ。

### スキル（`.claude/skills/`）

| スキル | レーン | 用途 |
|---|---|---|
| **`agile-process`** | 反復開発 | **プロセスの正** （7 点セット・成熟度・DoD・反復の型・厚く書く判定） |
| `walking-skeleton` | 反復開発 | 骨組みを作り切る手順（E2E 先行・4 層と契約の骨格） |
| **`usdm`** | 反復開発 | **要求記述の正**（HTML の表・理由は必須・仕様は番号で導出・ **成果物へのトレース表** ） |
| **`functional-design`** | 反復開発 | **設計書の正**（薄い版 = 毎スライス / 厚い版 = 例外。図と判断の記録） |
| **`test-reporting`** | 反復開発 | **テスト結果まとめの正**（実測のみ・仕様とテストの対応） |
| `slice-definition` | 反復開発 | ハブ 1 枚（7 点への索引・実績・残した手抜き） |
| `refactoring` | 反復開発 | 負債の返し方（緑を保ち 1 手 1 コミット） |
| **`layered-architecture`** | 反復開発 | **構造の正**（クリーンアーキテクチャ。内向きの依存と契約） |
| **`visual-debugging`** | 反復開発 | 構造化トレース・グラフ化・失敗が残す証拠 |
| `concept-definition` | 反復開発 | ゴールと完走の定義 |
| **`steering`** | 反復開発 | **役割間の受け渡し** ・タスク管理・節目報告・振り返り |
| `requirements-definition` | 厚い経路 | 網羅した要求仕様書（既定ではない） |
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
| `build_usdm.py` | 手書きの要求 HTML（`docs/usdm/src/`）を検証し、束ねた要求一覧（自己完結 HTML）を生成する。見た目と操作（折りたたみ・絞り込み・検索）は手書きと共有の `skills/usdm/usdm.css` / `usdm.js`。`--check` で古さを検出 | Python プロジェクト |
| `check_deliverables.py` | スライスごとに **7 点セットがそろっているか** を検査（設計書の図と判断の記録・テスト結果の実測・マニュアルの共通 3 節と `S##` 節・雛形の残りまで見る） | Python プロジェクト |
| `build_structure.py` | 実物のツリーから `docs/structure.md` を生成（`--check` で古さを検出。説明は `.claude/structure-notes.txt`） | Python プロジェクト |
| `build_status.py` | 現在地を 1 画面（`docs/status.html`）にまとめる。ゴール・成熟度の帯・充足マトリクス・負債・直近の作業 | Python プロジェクト |
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
