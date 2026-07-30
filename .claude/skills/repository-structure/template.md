# 現在のディレクトリ構造（スナップショット）

> **これはテンプレート版の雛形** 。`/setup-project` の「最小の土台の作成」で、
> 実物（Glob で確認したツリー）に置き換える。
> 構造に影響する変更をしたら、このスナップショットも更新する。
> 実物と食い違っていたら実物が正。最終更新: {YYYY-MM-DD}（{S## 完了時点}）
>
> **標準形を先に作らない。** 下のツリーは到達点であり、初期状態ではない。
> 骨組みの段階では `docs/concept.md`・`docs/backlog.md`・
> `docs/slices/S01-*.md` と、1 ファイルの実装 + E2E テストだけで足りる。

```
{リポジトリ名}/
├── CLAUDE.md                  # 開発規約 + プロジェクトプロファイル（正）
├── {依存定義}                 # 例: pyproject.toml / package.json / go.mod
├── {ロックファイル}           # 例: uv.lock / package-lock.json
├── README.md
├── docs/
│   ├── concept.md             # ゴールと完走の定義（最初に作る）
│   ├── backlog.md             # スライス・成熟度・負債（進捗の正）
│   ├── slices/                # スライス 1 枚 S##-*.md（反復ごとに増える）
│   ├── design.md              # 現状設計 1 枚（L3 に上げるときに作る）
│   ├── reference.md           # クラス・関数一覧とテスト件数（L3・任意）
│   ├── manual.md              # 取扱説明書（他人に渡すときに作る）
│   ├── glossary.md            # 用語集（用語の齟齬が起きたら作る）
│   ├── requirements/          # 要求仕様書 S##-*.md（厚い経路のみ）
│   └── design/proposals/      # 実装前設計書 S##-*.md（厚い経路のみ）
├── {ソースルート}/            # 例: src/<pkg>/
│   ├── presentation/          # UI・入出力・CLI
│   ├── application/           # ユースケース（domain + infrastructure を呼ぶ）
│   ├── domain/                # 業務ロジック・値（標準ライブラリのみ）
│   ├── infrastructure/        # 外部 I/O・ファイル・DB・プロセス
│   └── {配線}                 # 実装を選ぶ場所（必要になったら。例: container.py）
├── {テストルート}/            # ソースをミラー（例: test/）
│   ├── presentation/ application/ domain/ infrastructure/
│   ├── e2e/                   # E2E テスト（骨組みの 1 本目はここ）
│   └── {アーキテクチャテスト} # 逆流の機械検証（L2 以降。例: test_architecture.py）
├── .claude/                   # エージェント・スキル・ツール（プロセスの定義）
└── .steering/                 # 作業ノート（gitignore 対象）
```

## まだ無いもの

> 標準形にはあるが、このプロジェクトではまだ作っていないものを列挙する。
> **必要になった成熟度で作る** 。無ければ「なし」と書く。

- {例: 層ディレクトリ —— L1 では 1 ファイル。L2 の反復で分ける}
- {例: `docs/design.md` —— 最初の L3 到達時に作る}
- {例: アーキテクチャテスト —— L2 で導入する（L1 では逆流が許されるため）}
- {例: `docs/glossary.md` —— 用語の齟齬が実際に起きたら作る}

## 依存ルール（再掲）

**下の層が上の層を import しない。同じ層内で循環しない。** これだけ。

```
presentation → application → domain
                    ↓            ↑
              infrastructure ────┘
```

- `application` → `infrastructure` は違反ではない
  （クリーンアーキテクチャは要求しない）
- `domain` が標準ライブラリのみに依存することは常に守る
- 配線を 1 か所に集める（Composition Root）のは、実装が 3 種類以上に
  増えてからでよい

外部ライブラリも層で縛る（どのライブラリをどの層に許すかは
プロファイルの「層構成」表が正）。

違反は プロファイルの「アーキテクチャテスト」コマンドで落ちる
（L1 のスライスでは逆流も許され、負債表への記録で足りる）。
