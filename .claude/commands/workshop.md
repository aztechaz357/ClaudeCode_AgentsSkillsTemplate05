---
description: 工房レーンの一覧・検索・棚卸し（/workshop list|search <語>|tidy）
---

# 工房を見る・探す・整える

引数: `list` / `search <語>` / `tidy`（省略時は `list`）

工房レーン（`workshop/`）の成果物を扱う。レーンの定義は
`.claude/skills/workshop/SKILL.md` を正とする。

## 共通の前処理

```
powershell -File .claude/tools/index_workshop.ps1 -Check
```

- 終了コード 0: そのまま進む
- 終了コード 1（`STALE` / `BROKEN-FRONTMATTER`）: `-Check` なしで再生成し、
  それでも `BROKEN-FRONTMATTER` が残るなら `tidy` を案内する
- 終了コード 2（`workshop/` が無い）: まだ工房が空である旨を伝え、
  `/tool` または `/note` を案内して終了する

## `list`

`workshop/CATALOG.md` と `workshop/notes/INDEX.md` を読み、ユーザーに示す。

- ツールは `status` 別にまとめる（`working` / `stable` を先、
  `draft` は「未完成」として後ろ、`retired` は件数のみ）
- ノートは新しい順に 10 件まで。それ以上は件数で示す
- 最後に 1 行で「`draft` のまま放置されているものが N 件」を添える
  （0 件なら書かない）

## `search <語>`

工房から関連する成果物を探す。

1. `CATALOG.md` / `INDEX.md` の `summary`・`title`・`tags` を Grep
2. ヒットが少なければ `workshop/tools/*/README.md` と
   `workshop/notes/*.md` の本文も Grep する
3. **日本語・英語の両方のキーで探す** （ノートは日本語で書かれている）

結果は「ツール」「ノート」に分け、各 1 行の説明とパスを付けて示す。

**0 件でも黙って終わらない。** 試したキーを示し、
「無い」という事実を伝えたうえで `/tool` または `/note` を案内する。

## `tidy`

Task ツールで note-keeper サブエージェントを起動する:

- subagent_type: "note-keeper"（未登録の環境では general-purpose を使い、
  最初に `.claude/agents/note-keeper.md` と
  `.claude/skills/workshop/SKILL.md` を読むよう指示する）
- description: "Tidy the workshop"
- prompt: "`workshop/` の棚卸しをしてください。
  `.claude/agents/note-keeper.md` の検査と修正の順序（索引のズレ →
  front matter の不備 → 重複 → タグ寄せ → 関連リンク → 放置された成果物 →
  再生成とコミット）に従ってください。削除はせず、判断を要するもの
  （ツールの統合・draft の廃棄・summary の書き直し）は提案までにとどめて
  報告してください。"

サブエージェントの応答を受けたら、ユーザーには次を示す:

1. 検査件数と修正の内訳
2. **要判断の項目**（ツールの統合・`draft` の扱い）—— ここはユーザーに聞く
3. ツール化の候補として挙がった `idea` ノート（あれば `/tool` を案内）
4. 未作成の参照先（次に書くべきノートの候補）

## 実行の目安

- `list` / `search`: いつでも
- `tidy`: 月に 1 回、または `CATALOG.md` が 20 行を超えたとき
