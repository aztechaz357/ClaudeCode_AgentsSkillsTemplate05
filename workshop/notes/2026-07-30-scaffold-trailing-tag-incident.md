---
title: 雛形の末尾に混入した閉じタグが py で初めて露見した件
date: 2026-07-30
tags: [template, incident, workshop]
status: note
related: [2026-07-30-ps51-encoding]
---

# 雛形の末尾に混入した閉じタグが py で初めて露見した件

## 要点

- 書き出した 30 ファイルの末尾に `</content>` の 1 行が本文として残っていた
- `.ps1` `.sh` `.md` では末尾なので **動いてしまい** 、`.py` の import で
  初めて `SyntaxError` として露見した
- 教訓: 雛形は追加した直後に **各言語で 1 回生成して実行する** 。
  「読んで正しそう」は検証ではない

## 背景 / きっかけ

工房レーンの雛形（`.claude/templates/workshop/`）とツール 3 本を追加した。
`.ps1` の雛形は生成して実行し、テストが Red になることまで確認していた。
その後 `csv-diff`（Python）を実装しようとして `pytest` を回したところ、
テストの中身ではなく **collection の時点で** 落ちた。

## 中身

### 出たエラー

```
workshop\tools\csv-diff\test_main.py:10: in <module>
    import main
E     File "...\workshop\tools\csv-diff\main.py", line 48
E       </content>
E       ^
E   SyntaxError: invalid syntax
```

### なぜ ps1 では気づかなかったか

`.ps1` の雛形では `</content>` が `exit` 文より後ろにある。PowerShell は
これをコマンド名のトークンとして構文解析だけ通し、実行が `exit` で
終わるので到達しない。つまり **壊れているのに全部緑に見えていた** 。
Markdown では単に本文の最終行として表示されるだけで、
`check_numbering.ps1` も検出しない。

### 直し方

末尾が `</content>` と一致するファイルだけを対象に、その行を落とす
使い捨てスクリプトを書いた。`-Check` を付けると書き換えずに一覧だけ出す。

```
RESULT: 30 files still carry the marker
RESULT: stripped 30 files
RESULT: clean
```

その後、`new_tool.ps1` で py / ps1 の両方を生成し直して確認した。

```
RESULT: scaffolded 'py-demo' (py, 3 files)
1 passed in 0.69s
```

## 次にやること

- なし。`.claude/templates/` に手を入れたら py / ps1 の両方で
  1 回生成して走らせる、という運用で足りる
