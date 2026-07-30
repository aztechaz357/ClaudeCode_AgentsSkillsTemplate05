# 図の記法（作図言語）

**アスキーアートによる作図を禁止する。** ずれる・検証できない・
差分が読めないため、図は必ず作図言語で書く。

## 使う作図言語

図の種類ごとに 表 1 の記法を使う。迷ったら Mermaid を選ぶ
（Markdown 上で直接レンダリングされ、最も摩擦が少ない）。

表 1: 図の種類と使う作図言語

| 図の種類 | 記法 | フェンス |
|---|---|---|
| クラス図 | Mermaid `classDiagram` | ` ```mermaid ` |
| コンポーネント図 | Mermaid `flowchart` | ` ```mermaid ` |
| アクティビティ図 | Mermaid `flowchart TD` | ` ```mermaid ` |
| シーケンス図 | Mermaid `sequenceDiagram` | ` ```mermaid ` |
| 状態遷移図 | Mermaid `stateDiagram-v2` | ` ```mermaid ` |
| 結線・経路の配置を細かく制御したい図（ブロック線図・データフロー図） | Graphviz (dot) | ` ```dot ` |
| 上記で表現しきれないもの | PlantUML | ` ```plantuml ` |

**細かい配置制御に Graphviz を使う理由** —— 分岐点・合流点・
フィードバック経路の配置を `rankdir` と `constraint` で制御でき、
Mermaid では表現しきれない図が書けるため。

## 日本語を必ず併記する

認知負荷を下げるため、図は日本語で読めるようにする。

- **ノードのラベルは日本語で書く** 。英語の識別子を使う場合は
  日本語の意味を必ず併記する（ `UserRepository（利用者リポジトリ）` ）
- **信号線・遷移のラベルにも日本語を書く**
  （ `検索条件` `検索結果の一覧` ）
- 物理量には単位を併記する（ `経過時間 dt_s [s]` ）
- 図の意図が一目で分からない箇所には、作図言語のコメント機能で
  補足を入れる（Mermaid は `%%`、Graphviz と PlantUML は `//` ）

## 番号・キャプション・検証

- 図には番号とキャプションを付け、本文から 図 n の形で参照する
  （書式は `guides/numbering.md`）
- **図を書いたり修正したりしたら、必ず図検証ツールを実行する**
  （手作業でのブロック抽出は禁止 —— エンコーディング事故のもと）

```
powershell -File .claude/tools/check_diagrams.ps1 -Path <file.md>
powershell -File .claude/tools/check_diagrams.ps1 -Path docs
```

このツールは Mermaid / PlantUML / Graphviz の 3 言語すべてを
それぞれのツールチェーンで検証する。NG が出たまま作業を完了としない。

> `check_mermaid.ps1` は Mermaid 専用の旧ツール。新規の検証は
> `check_diagrams.ps1` を使う。

## 設計書に最低限入れる図

実装前設計書（`docs/design/proposals/S##-*.md`）には、少なくとも
次の 2 枚を入れる。

- **クラス図** —— 契約と実装の関係、層の所属が分かるもの
- **その機能の主経路を示す図** —— シーケンス図・アクティビティ図・
  データフロー図など、対象に合うもの

## 工房レーンでの扱い

`workshop/` 配下では図は任意。ただし **描くならアスキーアートは禁止**
（この 1 点だけは工房でも必須）。番号とキャプションは、図が 2 枚以上に
なったときに付ける。
