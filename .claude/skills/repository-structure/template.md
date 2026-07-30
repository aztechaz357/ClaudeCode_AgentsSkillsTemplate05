# 現在のディレクトリ構造（スナップショット）

> **これはテンプレート版の雛形** 。`/setup-project` の「骨組みの作成」で、
> 実物（Glob で確認したツリー）に置き換える。
> 構造に影響する変更をしたら、このスナップショットも更新する。
> 実物と食い違っていたら実物が正。最終更新: {YYYY-MM-DD}（{P## 完了時点}）

```
{リポジトリ名}/
├── CLAUDE.md                  # 開発規約 + プロジェクトプロファイル（正）
├── {依存定義}                 # 例: pyproject.toml / package.json / go.mod
├── {ロックファイル}           # 例: uv.lock / package-lock.json
├── README.md
├── docs/
│   ├── architecture.md        # 全体概要・文書マップ・層構成図
│   ├── roadmap.md             # フェーズ一覧とステータス
│   ├── manual.md              # 取扱説明書（コード例は実行して照合済み）
│   ├── reference.md           # クラス・関数一覧とテスト件数
│   ├── glossary.md            # 用語集
│   ├── requirements/          # 要求仕様書 P##-*.md（工程1の成果物）
│   └── design/
│       ├── 01-domain.md       # 層ごとの現状設計
│       ├── 02-application.md
│       ├── 03-infrastructure.md
│       ├── 04-presentation.md
│       ├── 05-composition-root.md
│       └── proposals/         # 実装前設計書 P##-*.md（工程2の成果物）
├── {ソースルート}/            # 例: src/<pkg>/
│   ├── {Composition Root}     # 全層を知る唯一の場所（例: container.py）
│   ├── domain/                # 契約・エンティティ（標準ライブラリのみ）
│   ├── application/           # ユースケース（domain のみに依存）
│   ├── infrastructure/        # 具体実装（domain + 許可された外部ライブラリ）
│   └── presentation/          # UI・表示（application + domain のエンティティ）
├── {テストルート}/            # ソースをミラー（例: test/）
│   ├── domain/ application/ infrastructure/ presentation/
│   ├── integration/           # 統合テスト（受け入れ条件の検証）
│   └── {アーキテクチャテスト} # 依存ルールの機械検証（例: test_architecture.py）
├── .claude/                   # エージェント・スキル・ツール（プロセスの定義）
└── .steering/                 # 作業ノート（gitignore 対象）
```

## まだ無いもの

> 標準形にはあるが、このプロジェクトではまだ作っていないものを列挙する。
> 必要になった工程で作る。無ければ「なし」と書く。

- {例: `docs/design/03-infrastructure.md` —— 該当層を使うフェーズで作る}
- {例: `docs/glossary.md` —— glossary-creation スキルを使う工程で作る}

## 依存ルール（再掲）

Presentation → Application → Domain ← Infrastructure。
Composition Root のみ全層を知ってよい。

外部ライブラリも層で縛る（どのライブラリをどの層に許すかは
プロファイルの「層構成」表が正）。

違反は プロファイルの「アーキテクチャテスト」コマンドで落ちる。
