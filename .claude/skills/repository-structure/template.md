# ディレクトリ構成の標準形（雛形）

> **実物のツリーはここに書かない。** 実物は
> `docs/structure.md`（`build_structure.py` の生成物）が正。
> このファイルは **到達点の型** で、どこに何を置くかを決めるときに読む。
>
> **標準形を先に作らない。** 下のツリーは到達点であり、初期状態ではない。
> 骨組みの段階で要るのは、`docs/` の 8 点セット 1 スライス分と、
> 4 層に 1 ファイルずつ、そして E2E テスト 1 本だけ。

```
{リポジトリ名}/
├── CLAUDE.md                  # 開発規約 + プロジェクトプロファイル（正）
├── {依存定義}                 # 例: pyproject.toml / package.json / go.mod
├── {ロックファイル}           # 例: uv.lock / package-lock.json
├── README.md
├── docs/
│   ├── concept.md             # ゴールと完走の定義（最初に作る）
│   ├── backlog.md             # スライス・成熟度・負債（進捗の正）
│   ├── usdm/src/              # ① 要求仕様書 S##-*.html（＋トレース表）
│   ├── design/                # ② 設計書 S##-*.md（図・判断の記録）
│   │   └── proposals/         #    実装前設計書（厚い経路のみ）
│   ├── test-reports/          # ⑥ テスト結果まとめ S##-*.md
│   ├── manual.md              # ⑦ マニュアル（共通 3 節 + S## 節）
│   ├── slices/                # ハブ S##-*.md（8 点への索引・実績・手抜き）
│   ├── decisions/             # ADR-###-*.md（スライスを越える判断）
│   ├── structure.md           # ディレクトリ構成（生成物）
│   ├── status.html            # 現在地の 1 画面（生成物・gitignore）
│   ├── design.md              # 現状設計 1 枚（L3 に上げるときに作る）
│   ├── reference.md           # クラス・関数一覧とテスト件数（L3・任意）
│   ├── glossary.md            # 用語集（用語の齟齬が起きたら作る）
│   └── requirements/          # 要求仕様書 S##-*.md（厚い経路のみ）
├── {ソースルート}/            # 例: src/<pkg>/
│   ├── presentation/          # UI・入出力・CLI
│   ├── application/           # ユースケース ＋ **契約（Port）**
│   ├── domain/                # 業務ロジック・値（標準ライブラリのみ）
│   ├── infrastructure/        # 契約の実装（ファイル・DB・ネットワーク）
│   └── {配線}                 # Composition Root（例: container.py）
├── {テストルート}/            # ソースをミラー（例: test/）
│   ├── presentation/ application/ domain/ infrastructure/
│   ├── fakes/                 # 契約のフェイク実装（本番コードに混ぜない）
│   ├── e2e/                   # 統合テスト（骨組みの 1 本目はここ）
│   └── {アーキテクチャテスト} # 依存ルールの機械検証（例: test_architecture.py）
├── .claude/                   # エージェント・スキル・ツール（プロセスの定義）
└── .steering/                 # 作業ノート（gitignore 対象）
```

## まだ無いもの

> 標準形にはあるが、このプロジェクトではまだ作っていないものを列挙する。
> **必要になった成熟度で作る** 。無ければ「なし」と書く。
> ただし **8 点セットは「まだ無い」に入れられない**（着手したら必ずある）。

- {例: `docs/decisions/` —— スライスを越える判断が出たら作る}
- {例: `docs/design.md` —— 最初の L3 到達時に作る}
- {例: アーキテクチャテスト —— L2 で導入する}
- {例: `docs/glossary.md` —— 用語の齟齬が実際に起きたら作る}

## 依存ルール（再掲）

**内向きの依存だけ。外部 I/O は契約を介す。** この 2 つ。

```
presentation → application → domain
                    ┆            ↑
                  契約(Port)     ┆
                    ↑            ┆
              infrastructure ────┘
                    ↑
            Composition Root（実装を注入）
```

- `application` → `infrastructure` の直接 import は **違反**
  （契約経由にする）
- `infrastructure` → `application` の契約 は違反ではない（実装が契約を知る）
- `domain` が標準ライブラリのみに依存することは常に守る
- 契約にするのは外部の世界に触るものだけ（純粋な計算に契約を切らない）

外部ライブラリも層で縛る（どのライブラリをどの層に許すかは
プロファイルの「層構成」表が正）。

違反は プロファイルの「アーキテクチャテスト」コマンドで落ちる
（L1 では契約 1 本まで。残った違反は負債表への記録で足りる）。
