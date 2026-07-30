# CLAUDE.md

プロジェクト名: {プロジェクト名}
目的: {何を作るか。1〜3 行で書く}
全体構想: {`docs/concept.md` 等。無ければ「なし」}

> **これはテンプレート版** —— `{}` はプレースホルダー。`/setup-project` で
> 実物の値に置き換える。`{` が残っている状態で本開発レーンを始めない
> （エージェントがコマンドやパスを推測し始める）。
>
> このファイルは **プロファイル（固有値）と絶対ルールとルーティングだけ** を
> 持つ。規約の本文はスキル側にあり、下の「ルーティング」から辿る。

## 2 つのレーン

| | 工房レーン（`workshop/`） | 本開発レーン（`docs/` + ソースルート） |
|---|---|---|
| 単位 / 起点 | ツール 1 本・ノート 1 本 / 思いつき | フェーズ（P##）/ 全体構想 |
| 前工程 | なし | 要求仕様書 → 設計書 → 作業計画 |
| 構造 / 文書 | 1 ディレクトリ完結・層構成なし / `README.md` 1 枚 | 4 層クリーンアーキテクチャ / 要求・設計・現状設計・リファレンス・マニュアル |
| テスト | 必須（テスト先行） | 必須（TDD + 統合テスト） |
| 入口 | `/tool` `/note` `/workshop` | `/add-feature P##` |

**依頼が来たらまずどちらのレーンかを決める。** 1 行の `summary` に
収まる思いつきは工房、フェーズ計画に載るものは本開発。
迷ったら工房で作り、育ったら `/promote` で上げる。
レーンの詳細は `.claude/skills/workshop/SKILL.md`。

## プロジェクトプロファイル

> `.claude/` のエージェント・スキルはすべてこの節を正として動く。
> ここに無い値を推測で使うことは禁止。不足に気づいたらここへ追記する。
> **見出しと項目名は変更しない** —— エージェントがこの名前で参照する。

### 言語・スタイル

- 主言語 / バージョン: {例: Python 3.12 / TypeScript 5.x}
- docstring 形式: {例: Google スタイル。日本語で「役割 / Args / Returns」を書く}
- 命名規則: 契約 {例: `Base` 接頭辞} / 実装 {例: `PostgresUserRepository`} /
  定数 {例: `UPPER_SNAKE_CASE`} / {分野特有: 例 物理量は単位を接尾辞に `dt_s`}
- 文書・コミットメッセージの言語: {例: どちらも日本語}

### コマンド

> テスト・ビルド・依存操作は **この表のコマンドだけ** を使う。別の
> パッケージマネージャ・タスクランナーを推測で使わない。未導入のものは
> 「未導入」と書く（空欄にしない —— 推測の原因になる）。

| 用途 | コマンド |
|---|---|
| テスト（全体） | {例: `uv run pytest -q`} |
| テスト（範囲指定） | {例: `uv run pytest <path> -q`} |
| テスト（詳細出力） | {例: `uv run pytest <path> -v --tb=short`} |
| 統合テスト | {例: `uv run pytest test/integration -q`} |
| テスト件数の数え方 | {例: `uv run pytest --collect-only -q`} |
| アーキテクチャテスト | {例: `uv run pytest test/test_architecture.py -v`} |
| lint / typecheck | {例: `uv run ruff check .` / `uv run mypy src`} |
| lint 自動修正 | {例: `uv run ruff check --fix .` / `uv run ruff format .`} |
| ビルド | {例: `uv build`} |
| 依存の同期 / 追加 | {例: `uv sync` / `uv add <pkg>`} |
| 動作確認 | {例: `uv run python -c "import <pkg>; print(<pkg>.__name__)"`} |
| `.claude/tools/` の Python ツール実行 | {例: `uv run python`。未導入なら「未導入」} |

> 最終行は `.claude/tools/*.py` を起動するための前置コマンド。
> エージェントはここに書かれたコマンドだけを使い、`python` / `uv run python`
> を推測しない。

### ディレクトリ構成

| 種別 | パス |
|---|---|
| ソースルート | {例: `src/<pkg>/`} |
| テストルート | {例: `test/`} |
| 統合テスト | {例: `test/integration/`} |
| Composition Root | {例: `src/<pkg>/container.py`} |
| 工房（軽量レーン） | `workshop/`（`tools/` と `notes/`。固定） |
| 探索除外 | {例: `.venv/` `.git/` `__pycache__/` `dist/` `build/` `.steering/` `node_modules/`} |

### 層構成（クリーンアーキテクチャ・本開発レーンのみ）

依存の流れ: **Presentation → Application → Domain ← Infrastructure**

| 層 | パス | import してよいもの |
|---|---|---|
| domain | {例: `src/<pkg>/domain/`} | 標準ライブラリのみ |
| application | {例: `src/<pkg>/application/`} | 標準ライブラリ + domain |
| infrastructure | {例: `src/<pkg>/infrastructure/`} | 標準ライブラリ + domain + {許可する外部ライブラリ} |
| presentation | {例: `src/<pkg>/presentation/`} | 標準ライブラリ + application + domain（エンティティ）+ {許可する外部ライブラリ} |
| Composition Root | {例: `src/<pkg>/container.py`} | 全層（唯一の例外） |

**外部ライブラリの配置方針** —— {どのライブラリをどの層に許すか、その理由}

**{危険な操作の閉じ込め方針}** —— {例: ユーザーコードの `exec` は
infrastructure に限定する。該当が無ければこの項目ごと削除する}

### ドキュメント構成

| 文書 | パス |
|---|---|
| 全体構想 / ロードマップ表 / 全体概要 | `docs/concept.md` / `docs/roadmap.md` / `docs/architecture.md` |
| 要求仕様書 / 実装前設計書 / 現状設計書 | `docs/requirements/P##-*.md` / `docs/design/proposals/P##-*.md` / `docs/design/0N-*.md` |
| リファレンス / マニュアル / 用語集 | `docs/reference.md` / `docs/manual.md` / `docs/glossary.md` |
| 凍結文書（**絶対に更新しない**） | {例: `docs/Note/`。無ければ「なし」} |

> 凍結文書のパスは `.claude/hooks/protected_paths.txt` にも同じものを書く。
> PreToolUse フックが編集を機械的に拒否する。

### 家風パターン

> 繰り返し守る設計の型。実装レビューがここを基準に判定する。3〜5 個に絞る。

- core 無変更: {中核クラス・契約の名前} は既存を書き換えない。機能を増やす
  ときは **契約の実装を足して Composition Root で差し替える** 。中核に
  `if 種別 == ...` の分岐を足すのは禁止（対象は `.claude/core_files.txt`
  に列挙し、`check_unchanged.py` で機械検証する）
- {家風2。例: フェイルソフト —— 想定内の失敗は例外を投げず結果として返す}
- {家風3。例: フェイルクローズ —— 構造的な誤りは実行前に例外で弾く}
- {家風4。例: 表示の分離 —— 中核が返すのは値と構造のみ}

### 安全機構

{守る対象は誰か。例: ローカル専用のツールであり、守る対象は悪意ある
第三者ではなく自分自身のミス。ネットワークに公開するなら脅威モデルを別途書く}

- {安全機構1。例: 実行前検証} / {2. 資源の上限} / {3. 入力検証} /
  {4. 秘密情報を出さない}

> security-checker はこの一覧を検査対象の正とする。
> 該当が無いプロジェクトでは「なし（理由）」と明記する。

### ログ / Git

- ログの出力先・形式: {例: `logs/*.jsonl`。未整備なら「未整備」} /
  可視化コマンド: {例: `uv run python -m <pkg>.tools.viewer`。無ければ「なし」}
- 既定ブランチ: {例: `main`} / ブランチ戦略: {例: `feature` での直列開発}
- push / PR: {例: ユーザーの明示的な指示があるときのみ}

## 絶対ルール

すべてのエージェント（親・サブエージェント）が、両レーンで従う。

1. **環境を正とする**: 会話の記憶ではなく、リポジトリ・ノート・コマンド結果を
   正とする。推測で状態を仮定せず、必ず Tool で確認する
2. **行動は必ず Tool を通す**: テキストに書いただけの結論、実行していない
   コマンドの結果の推測は行動ではない。行動に必要なツールが無ければ
   **まずツールを作る**（`tool-authoring`）
3. **設計と実装が矛盾したら止まる**: 勝手にどちらかへ合わせず、ユーザーに確認する
4. **破壊的操作は必ず確認**: ファイル削除・git の履歴改変・凍結文書への変更
5. **テストは先に書く**: Red を確認してから実装する（工房レーンでも同じ）
6. **編集したらコミットする**: 作業のまとまりごとに。1 コミット 1 意図。
   差分が 20〜30 行を超えたらタイミングが遅い
7. **出力を推測で書かない**: 文書に貼るコマンド出力・実行例は、実際に
   動かして得たものだけを貼る

## ルーティング

**やることが決まったら、まず対応するスキルを読む。** 規約の本文は
すべてスキル側にあり、CLAUDE.md には無い。

| やること | 読むもの |
|---|---|
| ツールをサクッと作る | `.claude/skills/quick-tool/` |
| ノートを残す | `.claude/skills/note-taking/` |
| 工房の置き場所・status・昇格を知る | `.claude/skills/workshop/` |
| 文書を書く（Markdown・数式・図・マニュアル） | `.claude/skills/writing-conventions/` |
| コードを書く・コミットする | `.claude/skills/development-guidelines/` |
| 新規ファイルをどこに置くか決める | `.claude/skills/repository-structure/` |
| 全体構想を決める・見直す | `.claude/skills/concept-definition/` |
| 要求仕様書を書く | `.claude/skills/requirements-definition/` |
| 実装前設計書を書く | `.claude/skills/functional-design/` |
| 現状設計書を更新する | `.claude/skills/architecture-design/` |
| 用語集を更新する | `.claude/skills/glossary-creation/` |
| フェーズの作業計画・進捗・振り返り | `.claude/skills/steering/` |
| 開発プロセスの道具を新設する | `.claude/skills/tool-authoring/` |
| フックを追加・修正する | `.claude/hooks/README.md` |
| 全体の設計思想・フロー・構成を知る | `.claude/README.md` |

### 本開発レーンの流れ

```
要求仕様書 → 設計書 → 作業計画 → TDD 実装 → 実装検証 → 統合テスト → 文書同期 → 振り返り
```

実行は `/add-feature P##`。 **前工程を飛ばさない**
（「設計書なしで実装」「受け入れ条件なしで統合テスト」は禁止）。
工程と担当エージェントの対応表・設計思想・プロセス自体の育て方は
`.claude/README.md` を正とする。
