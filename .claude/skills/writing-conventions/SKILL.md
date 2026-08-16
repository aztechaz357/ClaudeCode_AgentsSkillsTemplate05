---
name: writing-conventions
description: 文書の記法規約（Markdown・数式と図表の番号・作図言語・マニュアル）の正。要求仕様書・設計書・全体像・マニュアル・ノートを書いたり直したりする前に読み込む。図や数式を書くとき、番号や図の検証で NG が出たときにも読む。
allowed-tools: Read, Write, Edit, Bash
---

# 文書記法規約スキル（writing-conventions）

このプロジェクトで書く **すべての Markdown 文書** が従う記法の正。
CLAUDE.md の規約本文はここに集約されている（CLAUDE.md 側はリンクのみ）。

対象は本開発レーンの文書（`docs/` 配下）と、工房レーンの
`workshop/tools/*/README.md`・`workshop/notes/*.md`。
ただし工房レーンには **番号規約・作図言語規約を強制しない**
（詳細は下の「レーンごとの適用範囲」）。

## ガイドの索引

| 読むとき | ガイド |
|---|---|
| 本文を書く・直すとき（強調・見出し・表・用語） | `guides/markdown.md` |
| 数式・図・表を出すとき（番号とキャプション） | `guides/numbering.md` |
| 図を描くとき（どの作図言語を使うか・日本語併記） | `guides/diagrams.md` |
| マニュアル（`docs/manual.md`）を更新するとき | `guides/manual.md` |

## 絶対に守る 3 つ

この 3 つは違反が機械検出される。NG が出たまま作業を完了としない。

1. **アスキーアートで図を描かない** —— 図は作図言語（Mermaid / Graphviz /
   PlantUML）で書く。`guides/diagrams.md`
2. **プレーンテキストで数式を書かない** —— `sqrt(2/3)` ではなく `$\sqrt{2/3}$` 。
   独立した数式には `\tag{n}` で番号を振る。`guides/numbering.md`
3. **図・表・数式は必ず本文から番号で参照する** —— 参照されない図表は
   不要か説明不足のどちらか。`guides/numbering.md`

## 検証コマンド（手作業の目視確認は禁止）

図や数式・表を書いたり直したりしたら、必ず実行する。

```
powershell -File .claude/tools/check_numbering.ps1 -Path <file.md|dir>
powershell -File .claude/tools/check_diagrams.ps1 -Path <file.md|dir>
```

`check_numbering.ps1` が検出するのは 表 1 の 4 種。すべて規約違反。

表 1: 番号検証ツールが検出する違反

| 記号 | 意味 |
|---|---|
| `DUP` | 同じ番号が 2 回以上定義されている |
| `GAP` | 番号が 1 から始まる連番になっていない（欠番） |
| `UNREF` | 定義されているが本文から参照されていない |
| `DANGL` | 本文から参照されているが定義が無い |

`check_diagrams.ps1` は Mermaid / PlantUML / Graphviz の 3 言語を
それぞれのツールチェーンで構文検証する
（`check_mermaid.ps1` は Mermaid 専用の旧ツール。新規の検証では使わない）。

マニュアルのコード例は `check_doc_examples.py` で実行照合する
（Python プロジェクト。使い方は `guides/manual.md`）。

> PostToolUse フック（`post-edit-markdown.ps1`）が編集後に番号検証を
> 自動で走らせる。フックが走るからといって、書いている最中に
> 規約を無視してよいわけではない —— 手戻りが増えるだけ。

## レーンごとの適用範囲

表 2: レーン別の記法規約の適用

| 規約 | 本開発レーン（`docs/`） | 工房レーン（`workshop/`） |
|---|---|---|
| Markdown 本文（`guides/markdown.md`） | 必須 | 必須 |
| 数式・図・表の番号（`guides/numbering.md`） | 必須 | 任意（図表が 2 個以上なら推奨） |
| 作図言語（`guides/diagrams.md`） | 必須 | アスキーアート禁止のみ必須 |
| マニュアル（`guides/manual.md`） | 必須 | ツールの README がこれに相当（簡易版） |

工房レーンで番号規約を必須にしないのは、思いつきを形にする速度を
落とさないため。工房のツールを `/promote` で本開発レーンへ昇格させる
ときに、表 2 の「必須」をすべて満たす形へ引き上げる。

## チェックリスト（文書を書き終える前）

- [ ] `**強調**` の前後に半角スペースがあるか
- [ ] 図をアスキーアートで描いていないか（作図言語で書いたか）
- [ ] 数式をプレーンテキストで書いていないか（TeX で書いたか）
- [ ] 独立した数式に `\tag{n}` があるか
- [ ] 図に 図 n、表に 表 n のキャプションがあるか（図は下、表は上）
- [ ] すべての図・表・番号付き数式を本文から番号で参照したか
- [ ] 他文書の番号をスライス番号付き（ `式 (S01-1)` ）で参照したか
- [ ] `check_numbering.ps1` と `check_diagrams.ps1` が 0 で通ったか
