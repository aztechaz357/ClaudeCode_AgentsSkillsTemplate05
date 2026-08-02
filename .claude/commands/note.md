---
description: 調べたこと・踏んだ罠・決めたこと・思いつきをノート1本として工房に残す
---

# ノートを残す

引数: 残したい内容（例: `/note PS5.1 は BOM 無し UTF-8 の .ps1 を ANSI として読む`）

`workshop/notes/YYYY-MM-DD-<slug>.md` にノートを 1 本追加する。
手順の正は `.claude/skills/note-taking/SKILL.md`。

## ステップ1: 記録先を判定する

`note-taking` スキルの「記録先の判定」表で、本当に工房ノートが
正しい行き先かを確認する。次に当てはまるなら **別の場所へ案内する** 。

| 内容 | 案内先 |
|---|---|
| ゴール・完走の定義・非目標・割り切り | `concept-definition`（`docs/concept.md`） |
| 要求・理由・仕様 | `usdm`（`docs/usdm/src/`） |
| スライスの薄い設計・実績 | `slice-definition`（`docs/slices/`） |
| 残した手抜き・負債 | `docs/backlog.md` の負債表（`agile-process`） |
| 反復中の判断・ブロッカー | `steering`（`.steering/`） |
| ツールの使い方 | そのツールの `README.md` |
| 用語の定義 | `glossary-creation`（`docs/glossary.md`） |
| 恒久的な規約 | `CLAUDE.md` または該当スキル |

判定に迷ったら工房ノートでよい（後から移せる）。

## ステップ2: 既存ノートを確認する

`workshop/notes/INDEX.md` を読み、同じ話題のノートを探す。
Grep でタグ・キーワードも当たる。

**あれば新規作成せず、そのノートに日付見出しを付けて追記する。**
同じ話題が複数ファイルに散ることが、ノートが使われなくなる原因。

## ステップ3: 雛形を作る

タイトル・slug・タグ・status を決める。

- `status`: `note`（既定）/ `howto`（手順）/ `idea`（思いつき）/
  `decision`（決めたこと。 **なぜそう決めたか** を必ず書かせる）
- 日本語タイトルのときは `-Slug` を **必ず** 渡す（ASCII なら省略可）

```
powershell -File .claude/tools/new_note.ps1 -Title <タイトル> -Slug <slug> -Tags "a,b"
```

## ステップ4: 中身を書く

1. **「要点」を先に埋める**（3 行以内）。一覧から辿った人が読むのはここだけ。
   要点が書けないなら、まだ書くには早い旨をユーザーに伝える
2. 「背景 / きっかけ」を 1〜2 行
3. 本文。 **コマンド・出力・コードは実際に動かしたものを貼る**
   （推測で書かない）。ユーザーの発言に出力が含まれていればそれを使う
4. 「次にやること」。無ければ「なし」
5. `related` に関連ノート・ツールを結ぶ（リンク先が未作成でもよい）

記法は `writing-conventions`（`**強調**` の前後に半角スペース、
アスキーアートで作図しない）。

## ステップ5: 索引を更新してコミットする

```
powershell -File .claude/tools/index_workshop.ps1
```

```
docs: ノート「<タイトル>」を追加

- workshop/notes/<日付>-<slug>.md を追加（status: <status>）
- 要点: <1行>
- notes/INDEX.md を再生成
```

## ステップ6: ツール化の芽を拾う

書き終えたノートが次のどちらかなら、ユーザーに `/tool` を提案する
（提案するだけ。勝手に作らない）。

- `status: idea` で、具体的な入出力が既に書けている
- 同じ手作業を 2 回以上繰り返していることが本文から読み取れる
