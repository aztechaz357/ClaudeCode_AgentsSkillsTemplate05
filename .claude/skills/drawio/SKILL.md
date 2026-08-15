---
name: drawio
description: Create or edit a draw.io diagram as a native .drawio file, or export one to PNG / SVG / PDF / a browser URL. Use when the user says draw.io, drawio, drawoi, .drawio, or asks for a diagram delivered as a standalone file or image to hand off, or for shape libraries (AWS, Azure, network, UML detail). Do NOT use for the diagrams inside docs/ documents - those are inline Mermaid fences (skill: writing-conventions).
allowed-tools: Read, Write, Edit, Bash
---

# draw.io 図スキル（drawio）

図を **単体のファイル**（`.drawio` / PNG / SVG / PDF / ブラウザ URL）として
作って渡すためのスキル。文書の中に埋める図はこのスキルの担当ではない。

> **言語について** —— この `SKILL.md` はこのプロジェクトの運用を書くので日本語。
> `guides/` は上流（jgraph/drawio-mcp）由来の内容を含むため英語のまま置く
> （上流が更新されたときに差分を追えるようにするため）。

## 使う場面と使わない場面

**最初に 表 1 を見る。** 判断を誤ると、検証されない図が設計書に入り込む。

表 1: このスキルを使う場面

| 場面 | 使うか | 正しい手段 |
|---|---|---|
| 設計書（`docs/design/S##-*.md`）の 4 種の図 | **使わない** | 文書内の ` ```mermaid ` フェンス |
| 要求仕様書・テスト結果まとめ・ジャーナルの図 | **使わない** | 同上（ジャーナルは `flowchart TD` 必須） |
| `docs/design.md`（L3）の図 | **使わない** | 同上（Mermaid / Graphviz / PlantUML） |
| 図を 1 枚のファイルとして人に渡す | **使う** | `.drawio` または PNG / SVG / PDF |
| 受け取った人が draw.io で手編集する前提の図 | **使う** | `.drawio`（または XML 埋め込み書き出し） |
| AWS / Azure / ネットワークなど図形ライブラリが要る図 | **使う** | XML 直書き |
| モックアップ・ワイヤーフレーム | **使う** | XML 直書き |

**設計書の図に使わない理由** —— 絶対ルール 13 の 4 種の図（クラス図・
フローチャート・シーケンス図・状態遷移図）は、文書内に置いて
`check_diagrams.ps1` と `check_mermaid_ids.ps1` で構文検証する取り決め。
`.drawio` は Markdown 上でレンダリングされず、この 2 つの検証も通らない。
作図言語の正は `.claude/skills/writing-conventions/guides/diagrams.md`。

## 最初にやること: CLI の能力を測る

**このスキルの上流版は Mermaid 経路を既定として推すが、この環境では動かない。**
2026-08-15 に実測した結果が 表 2（draw.io Desktop 29.7.9 /
`C:\Program Files\draw.io\draw.io.exe`）。

表 2: 実測した CLI の対応状況

| やること | 使うもの | 29.7.9 | 実測 |
|---|---|---|---|
| XML → PNG / SVG / PDF（XML 埋め込み） | `-x -f png -e -b 10` | **可** | 1894 バイトの PNG を出力 |
| `.drawio` → ブラウザ URL | Node.js（`zlib`） | **可** | `C:\Program Files\nodejs\node` |
| Mermaid → `.drawio` | `.mmd` を入力に渡す | **不可** | `Error: Export failed: t.mmd` |
| 自動レイアウト（ELK） | `--layout` | **不可** | フラグ自体が無い（`--help` に無く、引数が入力ファイル名と解釈され `input file/directory not found`） |
| 静的画像セル | `--mermaid-image` | **不可** | フラグ自体が無い |

記録を信じずに **毎回測る**。`--layout` の有無が Mermaid 経路の有無と一致する。

```bash
"/c/Program Files/draw.io/draw.io.exe" --help | grep -c -- "--layout"
```

- `0` → **XML 直書きが既定**。座標は自分で決める（自動レイアウトは無い）
- `1` 以上 → `guides/mermaid-and-layout.md` の Mermaid 経路が使える

CLI がそもそも無い場合も XML 直書きにする（`.drawio` か URL で渡す）。
書き出し（PNG / SVG / PDF）だけは CLI が要る。

## 手順

1. **XML を書く** —— `.drawio` に mxGraphModel XML を直接書く（下の
   「XML の基本構造」と `guides/xml.md`）。座標は自分で計算する
2. **渡す形にする**
   - 形式の指定なし → `.drawio` のまま開く
   - `png` / `svg` / `pdf` → XML 埋め込みで書き出し、元の `.drawio` は消す
   - `url` → ブラウザ URL を作って開き、`.drawio` は手元に残す
3. **開く** —— 開けなければ絶対パス（または URL）を表示して手で開いてもらう

コマンドの実体は 表 3 のガイドにある。

## ガイドの索引

表 3: 読むガイド

| 読むとき | ガイド |
|---|---|
| CLI の場所・フラグ・どのシェルで打つか・開き方 | `guides/cli.md` |
| PNG / SVG / PDF に書き出す | `guides/cli.md` |
| ブラウザ URL で渡す | `guides/browser-url.md` |
| Mermaid 経路と ELK レイアウト（対応ビルドのときだけ） | `guides/mermaid-and-layout.md` |
| XML の書き方・スタイル・上流リファレンス | `guides/xml.md` |
| 失敗したとき | `guides/troubleshooting.md` |

## 出力形式の選び方

要求に形式の指定があれば 表 4 から選ぶ。指定が無ければ `.drawio` だけを作る
（書き出しは後からいつでも頼める）。

表 4: 書き出し形式

| 形式 | XML 埋め込み | 用途 |
|---|---|---|
| `png` | 可（`-e`） | どこでも見える。draw.io で再編集できる |
| `svg` | 可（`-e`） | 拡大しても崩れない。再編集できる |
| `pdf` | 可（`-e`） | 印刷用。再編集できる |
| `jpg` | 不可 | 非可逆。埋め込み不可（避ける） |
| `url` | ——  | ブラウザで開く共有用。`.drawio` は手元に残す |

## ファイル名と置き場所

- 内容が分かる名前を小文字とハイフンで付ける（`login-flow`, `database-schema`）
- 書き出しは二重拡張子にする（`name.drawio.png` / `.svg` / `.pdf`）——
  XML が埋め込まれていることの目印
- 書き出しが成功したら中間の `.drawio` は消す（書き出しに全部入っている）
- `url` のときは `.drawio` を残す（URL は窓、ファイルが正）
- 置き場所は、工房レーンなら `workshop/tools/<name>/` か `workshop/notes/`、
  反復開発レーンなら図が属する文書と同じ階層。書き出した画像は
  `.gitignore` の対象（正は `.drawio`）。成果物として配る画像だけ
  `git add -f` で明示的に追跡する

## 図の中身の規約

このプロジェクトの図はすべて **日本語で読める** ようにする
（`writing-conventions/guides/diagrams.md` と同じ規約）。

- ノードのラベルは日本語。英語の識別子には日本語を併記する
  （`UserRepository（利用者リポジトリ）`）
- 線・遷移のラベルにも日本語を書く（`検索条件` `検索結果の一覧`）
- 物理量には単位を併記する（`経過時間 dt_s [s]`）

## XML の基本構造

```xml
<mxGraphModel adaptiveColors="auto">
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
  </root>
</mxGraphModel>
```

- `id="0"` は最下層、`id="1"` は既定の親レイヤ
- 図の要素はすべて `parent="1"`（レイヤを分けるときを除く）
- 辺（edge）の `mxCell` は自己終了タグにしない。必ず
  `<mxGeometry relative="1" as="geometry" />` を子に持たせる

## 絶対に守る 3 つ

1. **XML コメント（`<!-- -->`）を出力に一切入れない** —— トークンを食い、
   パースエラーの原因になり、図には何の意味も無い
2. **属性値の特殊文字をエスケープする** —— `&amp;` `&lt;` `&gt;` `&quot;`
3. **`mxCell` の `id` は必ず一意にする**
