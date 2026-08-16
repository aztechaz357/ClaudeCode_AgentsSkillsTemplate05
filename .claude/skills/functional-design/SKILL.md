---
name: functional-design
description: 設計書を書くスキル。既定は毎スライスの薄い設計書（docs/design/S##-<name>.md。構造を表す図と構成10行と判断の記録）。不可逆・外部公開・安全機構・データ形式が絡むスライスだけ、厚い実装前設計書（docs/design/proposals/S##-<name>.md）を書く。
allowed-tools: Read, Write, Edit, Bash
---

# 設計書作成スキル（functional-design）

設計書は **8 点セットの 2 番目** 。 **どのスライスでも必ず 1 枚書く** 。
省くのは分量であって、設計書という成果物そのものではない
（正: `agile-process/deliverables.md`）。

厚さは 2 段階ある。

| | 薄い設計書（既定） | 厚い設計書（例外） |
|---|---|---|
| 置き場所 | `docs/design/S##-<name>.md` | `docs/design/proposals/S##-<name>.md` |
| 分量 | **4 種の図（各 5 ノードまで）** ＋ 構成 10 行 ＋ 主張の表 ＋ 判断の記録 3 行 | 制限なし（仕様の充足方針まで） |
| 入力 | 要求 HTML（`docs/usdm/src/S##-*.html`） | 要求仕様書（`docs/requirements/S##-*.md`） |
| 雛形 | `./template-thin.md` | `./template.md` ＋ `./guide.md` |
| いつ | **毎スライス** | 不可逆・外部公開・安全機構・データ形式・3 回失敗 |

判定条件の正は `agile-process` の「いつ厚く書くか」。
どれにも当てはまらないなら **薄い方** 。迷ったら薄い方。

## 前提（書き始める前に読む）

1. `CLAUDE.md`（プロファイル）—— 層構成・命名規則・設計の型
2. **対象の要求**（`docs/usdm/src/S##-*.html`。厚い経路では
   `docs/requirements/S##-*.md`）—— 設計の入力
3. `.claude/skills/layered-architecture/SKILL.md` —— 層と契約の正
4. `.claude/skills/writing-conventions/guides/diagrams.md` —— 図の記法と見た目
5. `docs/design.md`（現状設計。あれば）—— 既存構造との整合

## 層の扱い（クリーンアーキテクチャ）

配置の正は `layered-architecture` 。要点だけ:

- 依存は内向きだけ。 **`application` は `infrastructure` を直接 import しない**
- **外部 I/O（ファイル・DB・ネットワーク・時刻・乱数）は契約（Port）を介す** 。
  契約は使う側（application）に置き、実装を infrastructure に置き、
  Composition Root で注入する
- `domain` は標準ライブラリのみ。純粋さを崩さない
- **外部 I/O が無いなら契約を切らない** 。実装 1 つに 1 対 1 の
  インタフェースを作るのは意味の無い中間層（禁止）

契約を切った / 切らなかったの両方を「判断の記録」に残す。

## 図は 4 種すべて必須（L1 でも 4 枚）

**人は絵で理解する。** 文章 10 行より、正しい 1 枚のほうが速く読めて
誤解が少ない。設計書には次の 4 枚を **成熟度にかかわらず常に** 置く。

| # | 図 | 記法 | 何が見えるか | 実装から逆生成 |
|---|---|---|---|---|
| 1 | **クラス図** | `classDiagram` | 何があるか（構造・継承・保持） | **できる**（`build_uml.py`） |
| 2 | **フローチャート** | `flowchart TD` | どう流れるか（層・依存・分岐） | できる（`build_arch.py`） |
| 3 | **シーケンス図** | `sequenceDiagram` | 誰が誰を呼ぶか（時間の順） | 一部（呼び出し関係のみ） |
| 4 | **状態遷移図** | `stateDiagram-v2` | いつ何に変わるか | **できない**（下記） |

4 つが揃って初めて「構造・流れ・時間・状態」が埋まる。
1 つ欠けると、その軸だけが文章に戻り、そこが読まれなくなる。

### L1 で 4 枚描くのは重い —— 薄くしてよいのは中身

**枚数は削らない。1 枚あたりを薄くする。**

| 成熟度 | 1 枚あたりの上限 |
|---|---|
| L1 | **ノード 5 個まで** 。主経路だけ。分岐・失敗経路は描かない |
| L2 | 制限なし。失敗経路と境界を足す |
| L3 | `docs/design.md` へ統合する |

L1 の 4 枚は合計 20 ノードで収まる。 **超えたらスライスが大きすぎる** 。

**状態の無いスライスでも状態遷移図を省かない** ——
`[*] --> 完了` の 2 状態でよい。 **「状態が無い」という設計判断を図で示す**
ことに意味がある（後で状態が増えたとき、増えたことが図の差分で分かる）。

記法・色・凡例の規約は `writing-conventions/guides/diagrams.md` が正。
**書いたら必ず構文検証する** （手作業の目視で代用しない）:

```
powershell -File .claude/tools/check_mermaid_ids.ps1 -Path docs/design/S##-<name>.md
powershell -File .claude/tools/check_diagrams.ps1 -Path docs/design/S##-<name>.md
```

### 実装から逆に描いて突き合わせる

設計書の図は「こうしたい」であり、実装がそのとおりとは限らない。
実装側から同じ 4 種を起こして比較する（正: `Skill('architecture-drift')`）:

```
<ツール実行コマンド> .claude/tools/build_uml.py <ソースルート> --kind class
<ツール実行コマンド> .claude/tools/build_arch.py <ソースルート>
<ツール実行コマンド> .claude/tools/diff_arch.py <ソースルート>
```

**状態遷移図だけは実装から起こせない**（任意のコードから状態機械は
一般に復元できない）。代わりに **名前の対応を見る** ——
図に書いた状態名が実装の列挙型・定数に存在するかを目で確かめる。
できないことをできるふりにしない。

## 判断の記録は省略禁止

設計書の価値の半分はここにある。 **採用した理由・他の選択肢・
それぞれのメリットとデメリット** を書く（書式は `./template-thin.md`）。

- 却下案が思いつかない判断は「他の選択肢: 検討していない」と正直に書く
  （嘘の比較を作らない）
- スライスを越えて効く判断は `docs/decisions/ADR-###-<name>.md` へ 1 枚で

## 出力先と採番

```
docs/design/S##-<name>.md             （既定。毎スライス 1 枚）
docs/design/proposals/S##-<name>.md   （厚い経路のときだけ追加）
docs/decisions/ADR-###-<name>.md      （スライスを越える判断）
```

- S## は要求（`docs/usdm/src/S##-*.html`）と同じ番号を使う
- 作成と同時に、要求 HTML の **トレース表の「設計」列** に
  `docs/design/S##-<name>.md#<見出し>` を書く（線をつなぐのは書いた人の仕事）
- ハブ（`docs/slices/S##-*.md`）からもリンクする
- 厚い経路の設計書は、実装完了時に冒頭を「✅ 実装済み・反映済み」に更新する

## 品質チェック（作成後）

- [ ] **4 種の図がすべてあり、構文検証が通っている**
      （`classDiagram` / `flowchart TD` / `sequenceDiagram` / `stateDiagram-v2`）
- [ ] **「主張（契約式）」の表がある**（`Skill('verifiable-claims')`）——
      事後条件が 1 本以上、場合分けが `⊔` で閉じ、 **反例の形** が書いてある
- [ ] **「判断の記録」に理由・他の選択肢・メリデメが書かれている**
- [ ] 層の配置が内向きだけになっているか（`application` → `infrastructure`
      の直接 import が無いか）
- [ ] 外部 I/O に契約があるか／外部 I/O が無いのに契約を作っていないか
- [ ] L1 の上限（1 枚あたり 5 ノード ＋ 10 行 ＋ 3 行）を超えていないか
      —— 超えたらスライスを分割する（ **枚数は削らない** ）
- [ ] 要求 HTML のトレース表の「設計」列を埋めたか
- [ ] `**強調**` の前後に半角スペースがあるか
- [ ] （厚い経路）要求仕様書の仕様がすべて「仕様の充足方針」表にあるか
