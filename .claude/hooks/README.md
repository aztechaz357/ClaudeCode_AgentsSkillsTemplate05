# フック（`.claude/hooks/`）

フックは Claude Code のライフサイクルの決まった時点で **必ず実行される
コマンド** です。スキルやエージェント定義が「LLM にそう振る舞ってほしい
お願い」であるのに対し、フックは **ハーネスが強制する** 点が違います。

> このテンプレートの方針「LLM に考えさせるプロセスを小さくする」の
> 最終形がフック。規約に「必ず◯◯する」と書いてあって守り漏れが起きる
> なら、それはフックにできる候補です。

## いつフックにするか（スキル・ツールとの使い分け）

| 手段 | 実行する主体 | 使いどころ |
|---|---|---|
| スキル / エージェント定義 | LLM（読んで従う） | 判断が要る手順・書き方の指針 |
| ツール（`.claude/tools/`） | LLM が呼ぶ | 決定論的な検査・変換。呼ぶかどうかは LLM 次第 |
| **フック（`.claude/hooks/`）** | **ハーネスが必ず呼ぶ** | **守り漏れが許されない検査・記録・通知** |

判断基準は 3 つとも満たすこと。満たさないならツールに留める。

1. **イベント駆動**: 「◯◯したら必ず」と言える時点がある
2. **LLM に任せると漏れる**: 忘れたときの損害が大きい（凍結文書の破壊・
   未コミットのまま終了・破壊的コマンド）
3. **速い**: 毎回走る。数百 ms で終わるか、非同期にできること

## イベント一覧

よく使うのは **PreToolUse・PostToolUse・Notification・Stop** の 4 つ。

| フック名 | タイミング | ブロック可能 | 主な用途 |
|---|---|---|---|
| `PreToolUse` | ツール実行前 | ✓ | 禁止操作の防止、検証 |
| `PermissionRequest` | 確認ダイアログ表示時 | ✓ | ツール実行要求の承認・拒否 |
| `PostToolUse` | ツール実行後 | －（※） | 自動フォーマット、ログ記録 |
| `PostToolUseFailure` | ツール失敗後 | － | 失敗の記録・復旧 |
| `UserPromptSubmit` | プロンプト送信時 | ✓ | プロンプトの前処理・文脈の注入 |
| `Notification` | 通知送信時 | － | カスタム通知 |
| `Stop` | 応答終了時 | ✓（※） | 作業完了の確認・通知 |
| `SubagentStop` | サブエージェント完了時 | － | サブタスク完了の処理 |
| `PreCompact` / `PostCompact` | 圧縮の前後 | － | 圧縮前の状態保存・要約の受け取り |
| `SessionStart` / `SessionEnd` | セッションの開始・終了 | － | 環境の初期化・後始末 |

※ `PostToolUse` は終了コード 2 でツール結果を差し戻せる（実行自体は
済んでいる）。`Stop` は `decision: block` で応答を続行させられるが、
**ループの危険があるため本テンプレートでは使わない** 。

## 入出力の約束

- **入力**: フックの標準入力に JSON が渡る。主なフィールドは
  `session_id` / `cwd` / `hook_event_name` / `tool_name` /
  `tool_input`（`file_path`・`command` など）/ `tool_response`（PostToolUse）
- **終了コード**:
  - `0` … 正常。標準出力が JSON ならその指示に従う
  - `2` … ブロッキングエラー。 **標準エラーが Claude に返る**
  - その他 … 非ブロッキングエラー。標準エラーがユーザーに表示される
- **標準出力（JSON）の主なフィールド**:

  | フィールド | 効果 |
  |---|---|
  | `systemMessage` | ユーザーへメッセージを表示する |
  | `hookSpecificOutput.additionalContext` | Claude の文脈に情報を注入する |
  | `hookSpecificOutput.permissionDecision` | `allow` / `deny` / `ask`（PreToolUse のみ） |
  | `continue` / `stopReason` | ターン自体を止める（多用しない） |

## 同梱フック

`.claude/settings.json` の `hooks` で配線済み（`post-edit-lint.ps1` を除く）。

| スクリプト | イベント | 対象 | 動作 |
|---|---|---|---|
| `pre-tool-guard.ps1` | PreToolUse | `Write` `Edit` `NotebookEdit` `Bash` `PowerShell` | `protected_paths.txt` に一致する編集と、`denied_commands.txt` に一致するコマンドを **deny** する |
| `post-edit-markdown.ps1` | PostToolUse | `Write` `Edit` | 編集された `.md` に番号検証（`-Diagrams` で図検証も）を掛け、NG を Claude に差し戻す |
| `post-edit-python.ps1` | PostToolUse | `Write` `Edit` | 編集された `.py` の識別子に非 ASCII が無いか検査し、NG を Claude に差し戻す |
| `post-edit-lint.ps1` | PostToolUse | `Write` `Edit` | `-Command` で渡した整形・lint を編集ファイルに掛ける（ **未配線** ・下記参照） |
| `notify.ps1` | Notification | — | ビープ音を鳴らす（`-LogPath` で記録も可） |
| `stop-uncommitted.ps1` | Stop | — | 未コミットの変更が残っていたらユーザーに知らせる |
| `session-start-context.ps1` | SessionStart | — | ブランチ・未コミット数・HEAD・プロファイル未整備の警告・最新 steering を文脈へ注入 |

`lib-hook.ps1` はフックではなく共有の部品（`Read-HookPayload` /
`Set-HookOutputUtf8` / `Invoke-HookChecker`）。各フックが `param()` の直後に
`. (Join-Path $PSScriptRoot "lib-hook.ps1")` で読み込む。

### プロジェクト固有の設定ファイル

| ファイル | 内容 |
|---|---|
| `protected_paths.txt` | 編集を拒否するパス（CLAUDE.md プロファイルの「凍結文書」と揃える） |
| `denied_commands.txt` | 拒否する破壊的コマンドのパターン |

どちらも「`*` だけがワイルドカード」のグロブ。パスは先頭一致、
コマンドは部分一致。テンプレート状態では保護パスが空なので、
`/setup-project` で記入する。

### 未配線のフックを有効にする

`post-edit-lint.ps1` はプロジェクトの整形コマンドが必要なため、
配線を意図的に省いてある。`.claude/settings.json` の `PostToolUse` の
`hooks` 配列に次を足す（コマンドはプロファイルの「コマンド」表から取る）。

```json
{
  "type": "command",
  "command": "powershell -NoProfile -File .claude/hooks/post-edit-lint.ps1 -Command \"uv run ruff format\" -Extensions \"py\"",
  "timeout": 60
}
```

### 厳しくする / ゆるめる

- **Markdown 検証で作業を止めたい**: `post-edit-markdown.ps1` に
  `-Blocking` を付ける（終了コード 2 で Claude に修正させる）
- **図の検証も掛けたい**: `-Diagrams` を付ける（`npx` 起動のぶん遅い）
- **一時的に全部止めたい**: `.claude/settings.local.json` に
  `{"disableAllHooks": true}` を書く（共有設定は触らない）
- **特定のフックだけ止めたい**: `.claude/settings.json` の該当エントリを消す

## フックを書くときの規則

ツールと同じ規則（`tool-authoring` スキル）に加えて、フック固有のもの。

1. **フェイルオープン**: フック自身の失敗でセッションを詰まらせない。
   例外は捕まえて標準エラーに出し、終了コード 1（非ブロッキング）で終える
2. **速いこと**: 対象外（拡張子違い・ツール違い）なら **何もせず即 exit 0**
3. **出力は `[Console]::Out.WriteLine`** で書く。PowerShell 5.1 の
   `Write-Output` はリダイレクト時にコンソール幅で折り返し、
   **JSON の文字列中に改行が入って壊れる**（実測で踏んだ）
4. **標準入力は `Read-HookPayload` で読む**（`[Console]::In.ReadToEnd()` は
   使わない）。`[Console]::In` は **コンソールの入力コードページ**
   （日本語環境では cp932）で復号するため、UTF-8 の payload が壊れる。
   cp932 はバイトを 2 つずつ食うので、日本語が奇数バイト続いた直後の
   `\` が先行バイトに吸われ、`"C:\\Users"` が `"C:\Users"` になって
   `ConvertFrom-Json` が「認識できないエスケープ シーケンス」で落ちる。
   **日本語の本文と Windows パスが同居する payload で日常的に起きる**
   （実測: PreToolUse / PostToolUse のフックが約 99% の実行で失敗し、
   保護が無効なまま 1 編集あたり約 1 秒だけを払っていた）
5. **UTF-8 を明示する**: `Set-HookOutputUtf8` を呼ぶ。
   `[Console]::OutputEncoding` が UTF-8 でないと、git などの子プロセス出力と
   自分が出す JSON 中の日本語が cp932 として解釈されて文字化けする
6. **`.ps1` は ASCII のみ** で書く（PS5.1 が BOM 無し UTF-8 を ANSI と
   解釈して次行を壊す）。日本語の説明はこの README とスクリプト外に書く
7. **プロジェクト固有の値を埋め込まない**: パス一覧・コマンドは
   設定ファイルか settings.json の引数として外に出す

### 検証のしかた（必須）

フックは「動かなくても静かに何も起きない」ため、 **作ったら必ず
標準入力を模擬して確かめる** 。同梱フックには回帰テストがある。

```
<ツール実行コマンド> -m unittest discover -s .claude/hooks -p "test_*.py" -v
```

`test_hooks.py` は各フックを実プロセスとして起動し、 **拒否できること** と
**日本語 + Windows パスの payload で落ちないこと** の両方を見る。
後者を持たないと、フックが全滅していても緑のままになる。

手で確かめるときは次のようにする。

```bash
# PreToolUse（拒否されるはず）
echo '{"tool_name":"Bash","cwd":"<repo>","tool_input":{"command":"git reset --hard"}}' \
  | powershell -NoProfile -File .claude/hooks/pre-tool-guard.ps1

# PostToolUse（file_path は JSON エスケープが要る。\\ で書く）
powershell -NoProfile -File .claude/hooks/post-edit-markdown.ps1 < payload.json

# Stop / SessionStart / Notification
echo '{}' | powershell -NoProfile -File .claude/hooks/stop-uncommitted.ps1
```

確認項目:

- [ ] 検出すべきケースで deny / findings が出る（終了コードも確認）
- [ ] 正常なケースで **無出力・exit 0** （誤検出しない）
- [ ] 出力が **1 行の妥当な JSON** である（`python -c "import json,sys;json.load(sys.stdin)"` に通す）
- [ ] 日本語を含む入出力が化けない
- [ ] 設定ファイルが無い・空でも落ちない

### Windows 以外のプロジェクトへ持ち出すとき

同梱フックは PowerShell で書いてある（このテンプレートのツールと同じ流儀）。
POSIX 環境では同じ入出力契約のまま `.sh` / `.py` に置き換え、
`settings.json` の `command` を差し替える。契約（stdin の JSON・
終了コード・stdout の JSON）は OS に依存しない。
