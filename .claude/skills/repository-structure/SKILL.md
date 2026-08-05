---
name: repository-structure
description: リポジトリのディレクトリ構造と新規ファイルの配置規則。ソース・テスト・文書の置き場所と構造スナップショットを持つ。新しいファイルをどこに置くか迷ったときに使用。
allowed-tools: Read, Write
---

# リポジトリ構造・配置スキル

新規ファイルの置き場所を決めるためのガイド。
実際のパスはプロファイルの「ディレクトリ構成」表を正とする
（矛盾があればプロファイルが勝つ）。

## 層の判定は別スキル

ソースコードをどの層に置くかは
**`layered-architecture` スキルを正とする** （ここでは重複させない）。

要点だけ: 上から順に問い、最初に該当した層へ置く。

1. 標準ライブラリ以外に依存しない計算・値・判定か → domain
2. 外部（ファイル・DB・ネットワーク・OS）に触るか → infrastructure
   （＋ application に契約を 1 本足す）
3. 複数の部品を順に呼んで 1 つの仕事を成立させるか → application
4. 利用者に見せる・受け取るか → presentation
5. どの実装を使うか選んでいるか → Composition Root

**L1 でも 4 層に分ける** （1 層 1 ファイルでよい）。分けるのは安いが、
通した後に層へ割り直すのはテストごと書き直しになるため高い。
契約を切るのは高いので、外部 I/O があるスライスだけ 1 本にする。
`utils/` は作らない（作ると全部そこへ流れ込む）。

## 文書の置き場所

反復開発の既定の文書構成。 **①〜⑦ は 7 点セット**
（正: `agile-process/deliverables.md`）。

| 文書 | パス | いつ作るか |
|---|---|---|
| ゴールと完走の定義 | `docs/concept.md` | 最初（一行 + 完走の定義だけでよい） |
| バックログ（進捗の正） | `docs/backlog.md` | ゴール定義の直後 |
| ① 要求仕様書（USDM。手書きの正） | `docs/usdm/src/S##-<name>.html` / `Q##-<name>.html` | **各スライスで必ず** |
| ② 設計書（図・判断の記録） | `docs/design/S##-<name>.md` | **各スライスで必ず** |
| ⑥ テスト結果まとめ | `docs/test-reports/S##-<name>.md` | **各スライスで必ず** |
| ⑦ マニュアル | `docs/manual.md` | **骨組みで作り、各スライスで追記** |
| ハブ（7 点への索引・実績・手抜き） | `docs/slices/S##-<name>.md` | 各スライスに着手するとき |
| 判断の記録（スライスを越えるもの） | `docs/decisions/ADR-###-<name>.md` | 2 つ以上のスライスが従う判断をしたとき |
| 要求一覧（生成物・gitignore） | `docs/usdm/index.html` | `build_usdm.py` が生成 |
| ディレクトリ構成（生成物） | `docs/structure.md` | `build_structure.py` が生成 |
| 現在地の 1 画面（生成物・gitignore） | `docs/status.html` | `build_status.py` が生成 |
| 現状設計（1 枚） | `docs/design.md` | **L3 に上げるときだけ** |
| リファレンス | `docs/reference.md` | L3。無くてもよい |
| 用語集 | `docs/glossary.md` | 用語の齟齬が実際に起きたとき |
| 要求仕様書（厚い経路） | `docs/requirements/S##-<name>.md` | `/add-feature` のときだけ |
| 実装前設計書（厚い経路） | `docs/design/proposals/S##-<name>.md` | 同上 |
| 工房の成果物 | `workshop/tools/` `workshop/notes/` | 思いついたとき |

**7 点セット以外は先に作らない。** `docs/design.md`・`docs/reference.md`・
`docs/glossary.md` は、必要になった時点で作る（空のファイルを置かない）。
7 点セットは着手したスライスでは常にそろっているのが正常。

## テストの配置

- テストルートはプロファイル参照。L2 以上ではソースの構成をミラーする
- E2E / 統合テストは専用ディレクトリに分ける（プロファイルの「統合テスト」）
- 層に属さないテスト: アーキテクチャテスト（逆流の機械検証）・設定のテスト
- **骨組みの E2E は消さない** 。以降の全反復の安全網になる

## ディレクトリを増やすときの手順

1. 設計書（`docs/design/S##-*.md`）の構成にディレクトリを書く
2. 実装時にテスト側にも同名ディレクトリを作る（ミラー維持）
3. **構成を再生成する**（手で書き写さない）:

   ```
   <ツール実行コマンド> .claude/tools/build_structure.py
   ```

4. 説明を足したいときは `.claude/structure-notes.txt` に
   `パス <TAB> 説明` を 1 行書く（ツールがツリーに差し込む）

## 現在の構造（生成物が正）

**手書きのスナップショットは持たない。** 実物から生成する。

| | 役割 |
|---|---|
| `docs/structure.md` | **実物のツリー**（生成物。手で編集しない） |
| `./template.md` | 標準形の雛形（到達点の型。初期状態ではない） |

古くなっていないかは終了コードで分かる:

```
<ツール実行コマンド> .claude/tools/build_structure.py --check
```

STALE が返ったら再生成する（実物が常に正）。
