# ClaudeCode Agents / Skills テンプレート

Claude Code で開発を回すための、エージェント・スキル・コマンド・ツール一式
（`.claude/`）と、規約の雛形（`CLAUDE.md`）です。 **プロジェクト非依存** で、
固有の値は `CLAUDE.md` の「プロジェクトプロファイル」に集約します。

**重さの違う 2 本の道** を持ちます。

| | 工房レーン | 本開発レーン |
|---|---|---|
| 向くもの | 思いついた小さなツール・ノート | 腰を据えて作るプロダクト |
| 前工程 | なし | 要求仕様書 → 設計書 → 作業計画 |
| 構造 | 1 ディレクトリ完結 | 4 層クリーンアーキテクチャ |
| テスト | 必須（テスト先行） | 必須（TDD + 統合テスト） |
| 入口 | `/tool` `/note` `/workshop` | `/add-feature P##` |
| 所要 | 数十分 | 数時間〜数日 |

工房で省くのは前工程と構造であって、テストではありません。
育ったツールは `/promote` で本開発レーンへ上げられます。

## 使い方

```
1. .claude/ と CLAUDE.md を対象プロジェクトへコピーする
2. Claude Code で /setup-project    … プロファイルの {} を実物の値で埋める

   ＜軽い方＞
3. /tool 2つの CSV の差分を出したい  … テスト付きのツールが workshop/ に 1 本できる
4. /note 調べたこと                  … workshop/notes/ に残る
5. /workshop search <語>             … 過去に作ったものを探す

   ＜重い方＞
6. /add-feature P01                 … 要求仕様 → 設計 → TDD → 統合テスト → 文書反映
7. /improve-process                 … 数フェーズごとにプロセス自体を改善する
```

本開発レーンを始めるときは、`CLAUDE.md` に `{` が残っていないこと
（エージェントがコマンドやパスを推測し始めます）。工房レーンだけなら、
プロファイルの「コマンド」「ディレクトリ構成」が埋まっていれば動きます。

## 中身

| 場所 | 内容 |
|---|---|
| `.claude/commands/` | 工房: `/tool` `/note` `/workshop` `/promote` ／ 本開発: `/setup-project` `/add-feature` `/check-docs` `/review-docs` `/improve-process` |
| `.claude/agents/` | 調査・実装・実行・検証・文書のサブエージェント ＋ 工房の `tool-smith` `note-keeper` |
| `.claude/skills/` | 工房（`workshop` `quick-tool` `note-taking`）・記法（`writing-conventions`）・要求定義・設計・構造・規約・steering・ツール新設 |
| `.claude/tools/` | 図・番号・マニュアル例・core 無変更・変異テストの検証スクリプト ＋ 工房の雛形生成と索引 |
| `.claude/templates/` | 工房の雛形（ツールの README・実装・テスト、ノート） |
| `.claude/hooks/` | ハーネスが必ず走らせるフック（保護パスの防護・Markdown 検証・通知・未コミット警告・セッション開始時の状況注入） |
| `.devcontainer/` | Claude Code をサンドボックスで動かす開発コンテナ（コンテナ + 送信ファイアウォール + Claude Code サンドボックスの 3 層） |
| `CLAUDE.md` | プロジェクトプロファイル・絶対ルール・ルーティング（規約の本文はスキル側） |
| `workshop/` | 工房の成果物。このリポジトリ自身の作例（ツール 2 本・ノート 3 本）が入っている。対象プロジェクトへコピーするのは `.claude/` と `CLAUDE.md` だけなので、作例が持ち込まれることはない |

設計思想と開発フローの詳細は `.claude/README.md` を参照。

## 前提環境

- Claude Code
- Windows / PowerShell 5.1 を想定したツールを含む（`.ps1`。Linux では
  `pwsh` に symlink すれば動く —— 開発コンテナが自動で行う）
- 図の検証: Node.js（mermaid-cli）・Graphviz・PlantUML（使う図の分だけ）
- `.py` ツールを使う場合は Python 実行環境

上記を揃えるのが面倒なら、 **開発コンテナを使うのが早い** 。
Docker があれば `Reopen in Container` だけで、ツールが揃い、
かつ AI がホストを壊せず外部へ勝手に通信できない状態になる
（詳細は `.devcontainer/README.md`）。
