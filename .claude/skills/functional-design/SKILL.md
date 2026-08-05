---
name: functional-design
description: 設計書を書くスキル。既定は毎スライスの薄い設計書（docs/design/S##-<name>.md。構造を表す図と構成10行と判断の記録）。不可逆・外部公開・安全機構・データ形式が絡むスライスだけ、厚い実装前設計書（docs/design/proposals/S##-<name>.md）を書く。
allowed-tools: Read, Write, Edit, Bash
---

# 設計書作成スキル（functional-design）

設計書は **7 点セットの 2 番目** 。 **どのスライスでも必ず 1 枚書く** 。
省くのは分量であって、設計書という成果物そのものではない
（正: `agile-process/deliverables.md`）。

厚さは 2 段階ある。

| | 薄い設計書（既定） | 厚い設計書（例外） |
|---|---|---|
| 置き場所 | `docs/design/S##-<name>.md` | `docs/design/proposals/S##-<name>.md` |
| 分量 | 図を 1 枚 ＋ 構成 10 行 ＋ 判断の記録 3 行 | 制限なし（仕様の充足方針まで） |
| 入力 | 要求 HTML（`docs/usdm/src/S##-*.html`） | 要求仕様書（`docs/requirements/S##-*.md`） |
| 雛形 | `./template-thin.md` | `./template.md` ＋ `./guide.md` |
| いつ | **毎スライス** | 不可逆・外部公開・安全機構・データ形式・3 回失敗 |

判定条件の正は `agile-process` の「いつ厚く書くか」。
どれにも当てはまらないなら **薄い方** 。迷ったら薄い方。

## 前提（書き始める前に読む）

1. `CLAUDE.md`（プロファイル）—— 層構成・命名規則・家風パターン
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

## 図は必須（L1 でも 1 枚）

文章 10 行より、正しい 1 枚のほうが速く読めて誤解が少ない。

| 成熟度 | 入れる図 |
|---|---|
| L1 | 層と依存の向き（`flowchart TD`。契約は破線） |
| L2 | ＋ 主経路（シーケンス図・状態遷移図・データフロー図から 1 つ） |
| L3 | `docs/design.md` へ統合し、クラス図と SysML の要求図を足す |

記法・色・凡例の規約は `writing-conventions/guides/diagrams.md` が正。
**書いたら必ず構文検証する** （手作業の目視で代用しない）:

```
powershell -File .claude/tools/check_diagrams.ps1 -Path docs/design/S##-<name>.md
```

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

- [ ] **図が 1 枚以上あり、構文検証が通っている**
- [ ] **「判断の記録」に理由・他の選択肢・メリデメが書かれている**
- [ ] 層の配置が内向きだけになっているか（`application` → `infrastructure`
      の直接 import が無いか）
- [ ] 外部 I/O に契約があるか／外部 I/O が無いのに契約を作っていないか
- [ ] L1 の上限（図を 1 枚 ＋ 10 行 ＋ 3 行）を超えていないか
      —— 超えたらスライスを分割する
- [ ] 要求 HTML のトレース表の「設計」列を埋めたか
- [ ] `**強調**` の前後に半角スペースがあるか
- [ ] （厚い経路）要求仕様書の仕様がすべて「仕様の充足方針」表にあるか
