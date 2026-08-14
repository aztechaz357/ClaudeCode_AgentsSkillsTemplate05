# {S## スライス名} 反復ログ

**目標成熟度: {現在 L{n} → 目標 L{n+1}}** ｜
**関与モード: {伴走 / 既定 / 任せる}** ｜
タスク: [tasklist.md](tasklist.md) ｜ 進捗の正: [docs/backlog.md](../../docs/backlog.md)

> **追記だけ。書き換えない。** 方針が変わったら、変わったことを新しい行に
> 足す（消すと経緯が消える）。ユーザーが後から「何がどう決まったか」を
> 追えるようにするための 1 枚。

| 時刻 | 段 | 誰が | 何をした・何を決めた | 触ったもの |
|---|---|---|---|---|
| {HH:MM} | 1 | requirement-writer | {要求 1・仕様 n 条を書いた} | `docs/usdm/src/S##-{name}.html` |
| {HH:MM} | 2 | designer | {採用した案と、却下した案} | `docs/design/S##-{name}.md` |
| {HH:MM} | 3 | unit-tester | {Red n 件を確認} | `{テストルート}/...` |
| {HH:MM} | 4 | coder | {Green n 件。残した手抜き n 件} | `{ソースルート}/...` |
| {HH:MM} | 5 | integration-tester | {E2E n 本。回帰なし} | `{統合テストルート}/...` |
| {HH:MM} | 6 | test-summarizer | {全体 n 件緑・未カバー n 条} | `docs/test-reports/S##-{name}.md` |
| {HH:MM} | 7 | manual-writer | {S## の節を追加} | `docs/manual.md` |
| {HH:MM} | 8 | doc-syncer | {L{n} に更新・負債 n 件を転記} | `docs/backlog.md` ほか |

## ユーザーに出した節目報告

> 出した内容をそのまま残す（会話が流れても後から読めるように）。

1. **段1 の後**: {要求 1 行・理由 1 行・仕様の数}
2. **段2 の後**: {層と契約の要点 ＋ 却下した案}
3. **段8 の後**: {5 行サマリ}

## 止まった / 迷った

> 止まったこと自体が改善の材料。無ければ「なし」。

- {何で詰まり、どう抜けたか。ブロッカーは blockers.md へ}
