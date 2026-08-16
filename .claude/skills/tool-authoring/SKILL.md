---
name: tool-authoring
description: 開発プロセスに新しい行動（ツール）を追加するときの手順書。エージェント → スキル → ツールの順で作る。エージェントから「ツール不足」の報告を受けたとき、同じ操作を 2 回以上手作業で繰り返したときに読み込む。
allowed-tools: Read, Write, Edit, Bash
---

# ツール新設スキル（tool-authoring）

エージェントの行動は **常に Tool を通す**（`report-protocol.md` の
知覚-行動ループ）。既存の Tool（Read / Write / Edit / Bash / Task）だけで
表現しにくい決定論的な操作は、`.claude/tools/` のスクリプトとして
ツール化し、Bash / PowerShell 経由で呼び出す。

**ツールを増やすことは、LLM に考えさせるプロセスを減らすこと** です。
手順を自然言語で書いて毎回 LLM に解釈させるより、スクリプトにして
終了コードで判定するほうが決定論的で速く、事故が起きません。

## ツール化の判断基準

次のすべてを満たすときだけ作る（安易に増やさない）:

1. **反復性**: 同じ操作が 2 回以上（複数スライス・複数エージェントで）必要
2. **決定論性**: 同じ入力に対して同じ出力・同じ終了コードを返せる操作である
3. **事故実績または事故リスク**: 手作業・場当たりのワンライナーで
   間違えた実績がある（例: Markdown 抽出のエンコーディング事故、
   テスト件数の手計算誤記）

判断に迷ったら、steering の振り返り（プロセス改善提案）に候補として
記録しておき、次に同じ状況が来たら作る。

## 作成順序（必ずこの順。逆順・省略の禁止）

1. **エージェント**: そのツールを「誰が・どの工程で」使うかを特定し、
   `.claude/agents/` の該当エージェント定義に使用箇所を明記する
   （利用者の決まっていないツールは作らない）
2. **スキル**: 本ファイル末尾の「ツール一覧」に行を追加し、
   用途・使い方（コマンド例）・終了コードの意味を書く（手順書が正）
3. **ツール**: `.claude/tools/<name>.<ext>` として実装する。要件:
   - 決定論的（同じ入力 → 同じ出力）・冪等（繰り返し実行しても安全）
   - 引数で対象を明示し、暗黙の状態（カレントディレクトリの仮定等）に
     依存しない
   - 終了コード: 成功 0 / 失敗 非 0（呼び出し側が機械判定できること）
   - 読み取り専用が原則。書き込む場合は対象を引数で限定し、
     破壊的操作（削除・上書き）は行わないか、明示フラグを必須にする
4. **検証**: 実データで「成功するケース」「失敗するケース」「対象が無い
   ケース」を最低 1 回ずつ実行し、出力と終了コードを確認する
5. **コミット**: エージェント定義の更新・スキルの追記・ツール本体を
   同じ作業のまとまりでコミットする

## ツールにするか、フックにするか

ツールは **LLM が呼んだときだけ** 走る。呼び忘れが致命的な検査は、
`.claude/hooks/` のフックにしてハーネスに強制させる。

| | ツール（`.claude/tools/`） | フック（`.claude/hooks/`） |
|---|---|---|
| 起動 | LLM が Bash / PowerShell 経由で呼ぶ | イベント発生時に必ず走る |
| 向く仕事 | 判断の材料を出す検査・変換 | 守り漏れが許されない禁止・記録・通知 |
| 失敗の影響 | 呼ばなければ何も起きない | セッション全体に影響（速度・詰まり） |

フックの候補になる条件は「イベント駆動」「漏れると損害が大きい」
「毎回走っても速い」の 3 つ。作り方・入出力契約・検証手順は
`.claude/hooks/README.md` を正とする（本スキルでは重複させない）。

## 実装言語の選び方

- **PowerShell（`.ps1`）**: Windows 環境で完結する操作。下の PS5.1 注意点を守る
- **Python 等（`.py`）**: 文字列処理・構造解析が主体の操作。
  プロジェクトの実行環境に依存する場合はプロファイルの実行コマンドを使う
- **シェル（`.sh`）**: POSIX 環境が前提のプロジェクト

### PowerShell 5.1 の既知の落とし穴（Windows 環境の必読事項）

- `Get-Content` は既定 ANSI で日本語が化ける。ファイル読み書きは
  `[System.IO.File]::ReadAllText/WriteAllText` ＋ UTF-8 エンコーディング指定を使う
- **`.ps1` 本体は ASCII のみで書く**: PS5.1 は BOM 無し UTF-8 の `.ps1` を
  ANSI として解釈し、日本語コメントの多バイト文字が直後の改行を飲み込んで
  **次の行の文（代入等）を壊す** 。日本語の説明は本スキルとエージェント定義側に書く
- `&&` / `||` / 三項演算子は使えない。`;` と `if ($?)` で書く

## ツール一覧（`.claude/tools/`）

`.py` のツールを起動する前置コマンドは **プロファイルの
「`.claude/tools/` の Python ツール実行」** を使う（下表では
`<ツール実行コマンド>` と表記。`python` / `uv run python` を推測しない）。

| ツール | 用途 | 使い方 | 終了コード | 利用エージェント |
|---|---|---|---|---|
| `check_diagrams.ps1` | Markdown 内の全図ブロック（mermaid / plantuml / dot）を UTF-8 安全に抽出し、各ツールチェーンで構文検証する | `powershell -File .claude/tools/check_diagrams.ps1 -Path <file.md\|dir>` | 全ブロック OK なら 0（ブロック無しも 0）。NG が 1 つでもあれば 1。引数・環境エラーは 2 | orchestrator（設計）・doc-syncer（文書同期）・implementation-validator・doc-reviewer |
| `check_numbering.ps1` | 数式・図・表の番号（DUP / GAP / UNREF / DANGL）を検証する | `powershell -File .claude/tools/check_numbering.ps1 -Path <file.md\|dir>` | 違反なしなら 0。1 つでもあれば 1 | 要求・設計を書く工程すべて・doc-syncer・doc-reviewer |
| `check_mermaid.ps1` | Mermaid 専用の旧ツール（`check_diagrams.ps1` の前身。既存呼び出しの互換のために残す） | `powershell -File .claude/tools/check_mermaid.ps1 -Path <file.md>` | 全ブロック OK なら 0。NG があれば 1 | 新規の検証では使わない |
| `check_py_names.ps1` | Python の関数定義（`def` / `async def`）の名前に非 ASCII が無いか検証する。三重引用符の中の `def` は数えない。識別子は ASCII、説明は docstring という規約の機械化（`development-guidelines/guides/implementation.md`） | `powershell -File .claude/tools/check_py_names.ps1 -Path <file.py\|dir>` | 違反なしなら 0（`.py` が無いときも 0）。1 つでもあれば 1。引数エラーは 2 | PostToolUse フック（編集のたび）・coder・unit-tester・code-reviewer |
| `check_mermaid_ids.ps1` | mermaid の flowchart のノード id だけを高速に検査する（雛形の `{}` が id に入っている・非 ASCII の id・括弧の不一致）。full の構文検証（`check_diagrams.ps1`）は 1 ファイル約 5 秒で毎編集に掛けられないため、フックから常時走らせる軽い方として作った | `powershell -File .claude/tools/check_mermaid_ids.ps1 -Path <file.md\|dir>` | 違反なしなら 0（図が無いときも 0）。1 つでもあれば 1。対象が無いときは 2 | PostToolUse フック（編集のたび）・designer・doc-syncer |
| `check_doc_examples.py` | Markdown 内の ` ```python ` 例を実行し、直後の出力ブロックと照合する（Python プロジェクト専用） | `<ツール実行コマンド> .claude/tools/check_doc_examples.py docs/manual.md` | 全て一致なら 0（`N compared` を出力）。不一致・実行失敗は 1。引数エラーは 2 | doc-syncer（マニュアル更新）・doc-reviewer |
| `check_unchanged.py` | `.claude/core_files.txt` に列挙した中核ファイルが、指定コミット以降で無変更であることを検証する（設計の型「core 無変更」の機械検証） | `<ツール実行コマンド> .claude/tools/check_unchanged.py --since <commit> [--include-worktree]` | 全て無変更なら 0。変更があれば 1。一覧が無い / 空 / 存在しないパスは 2 | coder（実装ループ完了時）・implementation-validator |
| `mutate.py` | 実装に意図的な変異を加え、テストが検出できるか（KILLED / SURVIVED）を確認する | `<ツール実行コマンド> .claude/tools/mutate.py --spec .claude/mutations/S##-<対象>.json [--test-command "<テストコマンド>"]` | 全て KILLED なら 0。SURVIVED があれば 1。引数エラーは 2 | unit-tester（Red を確保できなかったとき）・test-analyzer |
| `build_usdm.py` | 手書きの要求 HTML（USDM 記法。`skills/usdm/` が正）を検証し、束ねた要求一覧（外部参照ゼロの自己完結 HTML・折りたたみと絞り込みつき）を生成する。理由の欠落・仕様 0 件・仕様番号の不整合・番号の重複・S##/Q## と要求番号の不一致・品質要求の評価尺度の欠落を検出する | `<ツール実行コマンド> .claude/tools/build_usdm.py [--source <dir>...] [--out <html>] [--check]` | 違反なく生成できたら 0（`--check` では最新）。違反または STALE は 1。引数エラー・対象 0 件は 2 | slice-definition を使う工程すべて・doc-syncer（記録）・doc-reviewer・orchestrator（現在地の把握） |
| `check_deliverables.py` | バックログに載る L1 以上の各スライスについて、成果物 8 点セット（`agile-process/deliverables.md`）がそろっているかを検査する。要求仕様書・設計書（図と「判断の記録」を含む）・テスト結果まとめ（実測の出力を含む）・ハブ・マニュアル（共通 3 節と S## の節）・雛形の残りを見る | `<ツール実行コマンド> .claude/tools/check_deliverables.py [<root>] [--slice S##]` | 全てそろっていれば 0。欠けがあれば 1。バックログが無い・対象が無いは 2 | doc-syncer（記録）・implementation-validator（検証）・`/check-docs`・`/iterate` の完了条件 |
| `build_structure.py` | 実物のディレクトリツリーから `docs/structure.md` を生成する。手書きのスナップショットが実物とずれる事故を構造的に防ぐ。説明は `.claude/structure-notes.txt` に書く（生成物に日時は入れない） | `<ツール実行コマンド> .claude/tools/build_structure.py [<root>] [--depth N] [--check]` | 生成できたら 0（`--check` では最新）。STALE は 1。引数エラーは 2 | doc-syncer（構造を変えた反復）・`/check-docs`・repository-structure を読む工程 |
| `build_status.py` | 開発の現在地（ゴール・成熟度・8 点セットの充足マトリクス・ **主張の台帳（⊢ / ⊬。⊬ が先頭）** ・負債・直近のコミットとレポート）を 1 画面の自己完結 HTML `docs/status.html` にまとめる。ユーザーが会話を追わなくても大枠を掴めるようにするためのもの | `<ツール実行コマンド> .claude/tools/build_status.py [<root>] [--out <html>]` | 生成できたら 0。バックログが無い・引数エラーは 2 | `/status`・orchestrator（反復の区切り）・`/iterate` の完了報告 |
| `build_arch.py` | Python の import から実際の依存図（Mermaid）を起こし、層のルール（内向きの依存だけ）に反する辺を検出する。ノード id はモジュールパスなので設計書の図と機械比較できる | `<ツール実行コマンド> .claude/tools/build_arch.py <ソースルート> [--out <md>]` | 0 = 逆流なし。1 = 逆流あり。2 = ルートが無い / `.py` が 0 件（Python 以外は未対応） | `/arch actual`・dependency-checker・refactorer |
| `diff_arch.py` | 設計書の図（`docs/design/*.md` の mermaid）と実物を集合比較し、一致 / 未実装（灰）/ **実装にだけある（黄）** / 逆流（赤）を 1 枚に色分けする | `<ツール実行コマンド> .claude/tools/diff_arch.py <ソースルート> [--design <dir>] [--out <md>]` | 0 = 乖離なし。1 = 乖離あり。2 = 設計書 / 図が無い・比較できない | `/arch`・`/iterate` 段8（L2 以上）・`/refactor` の前・implementation-validator |
| `build_digest.py` | 既読地点（`.steering/last-reviewed`）から HEAD までの変更を、影響度（高 = ADR・設計・要求・規約・依存 / 中 = 実装 / 低 = テスト・記録）で分類し、後戻りコストの高い順に並べたダイジェストを出す。低いものは件数だけにして読む量を増やさない | `<ツール実行コマンド> .claude/tools/build_digest.py [--since <ref>] [--mark]` | 0 = 未読なし（または `--mark` 成功）。1 = 未読あり。2 = git の失敗・引数エラー | `/catchup`・SessionStart フック（未読数の通知）・code-reviewer（レビュー範囲の決定） |
| `issue_mode.py` | チケットの置き場所を、プロファイルの「チケット追跡」節の `- 使用:` の 1 行から読む / 書き換える。判定不能を `github` に倒さないことで、誤送信を構造的に防ぐ | `<ツール実行コマンド> .claude/tools/issue_mode.py [--set github\|gitlab\|local\|off] [--repo owner/repo] [--host <gitlab のホスト>]` | 0 = github。1 = off。2 = 判定不能。 **3 = local。4 = gitlab** （`0 以外 = 使わない` と読まない） | `issue-manager`・`/issue` の全モード・`/iterate` の段0 と段8 |
| `sync_issues.py` | `docs/backlog.md` の S## / D## と Issue（GitHub / GitLab）の差分（作成・更新・クローズ・再オープン・外部起票の取り込み候補）を計算する。既定は dry-run で、`--apply` のときだけ `gh` / `glab` を呼ぶ。 **差分の計算は 1 つを共有し、CLI の違いは `Forge` に閉じ込める** | `<ツール実行コマンド> .claude/tools/sync_issues.py [--apply] [--include-done] [--print-commands] [--issues-json <path>]` | 0 = 差分なし / 反映成功。1 = 差分あり（未送信）または反映失敗。2 = `使用: off`・バックログ無し・リポジトリ未設定 | `issue-manager`・`/issue status`・`/issue sync` |
| `check_llm_endpoint.py` | ローカル LLM のエンドポイントが Claude Code を駆動できるか（messages / system / tools / streaming）を実際に投げて検査する | `<ツール実行コマンド> .claude/tools/check_llm_endpoint.py --model <モデル名>` | 全項目合格なら 0。落ちた項目があれば 1。base URL / モデル未指定は 2 | `/local-mode check`（ローカル LLM 駆動時のみ） |

変異仕様（`.claude/mutations/`）の書式は `.claude/mutations/README.md`。

### 候補（未実装。必要になったら本フローで作成）

- `count_tests.*`: リファレンスのテスト件数表向けに、全体とファイル別の
  収集件数を一括出力する（doc-syncer のチェックリスト項目5の決定論化）
- `check_layers.*`: 依存ルールの機械検証をプロジェクト非依存に行う
  （言語ごとのアーキテクチャテストで足りるならそちらを優先）
- `check_traceability.*`: 要求仕様書に書かれた仕様と設計書の充足方針表・
  統合テスト名の対応漏れを検出する（工程間トレーサビリティの決定論化）


## ツールを作ったら必ず確認すること

**「正常系が通った」だけで完成としない。** ツールは検査のために作る以上、
 **検査対象の異常を意図的に作り、検出できることを確かめる** 。

- [ ] 検出すべき異常を作って、実際に検出できること（終了コードも確認）
- [ ] 正常な入力で誤検出しないこと
- [ ] **日本語を含む入出力で動くこと** —— Windows では子プロセスの
      標準出力が既定でコンソールのコードページ（cp932）になり、
      日本語で `UnicodeDecodeError` になる。`PYTHONIOENCODING=utf-8` を
      子プロセスへ渡す
- [ ] 検査が空振りしていないこと —— 「対象が 0 件」「置換対象が見つからない」
      を成功として返すと、永遠に緑のまま何も検査しないツールになる。
      これらはエラーとして扱う
- [ ] ファイルを書き換えるツールは、失敗時・中断時にも復元されること

> 実例: 番号検証ツールとマニュアル例の照合ツールは、どちらも導入直後に
> 「検出できていない」ことが変異で発覚した。期待値を改ざんしても OK を
> 返す状態だった。
