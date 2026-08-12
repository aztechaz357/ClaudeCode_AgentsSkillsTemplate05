---
description: GitHub Issue 駆動の入口（使う / 使わないの切り替え・同期・起票・取り込み・クローズ）
---

# Issue 駆動（GitHub Issues）

**引数:** `status`（既定）/ `on` / `off` / `sync` / `new <内容>` /
`pull` / `close S##`

規約の正は `.claude/skills/issue-tracking/SKILL.md` 。
**進捗の正は `docs/backlog.md` のまま** で、Issue はその写し（窓）です。

## 最初に必ずやること（全モード共通）

```
<ツール実行コマンド> .claude/tools/issue_mode.py
```

終了コードで分岐する（会話の記憶で判断しない）:

| 終了コード | 意味 | やること |
|---|---|---|
| 0 | `使用: on` | 依頼どおり進む |
| 1 | `使用: off` | `on` 以外の引数なら「off です」と 1 行返して終了 |
| 2 | 節が無い / 値が不正 | 推測で on にせず、`on` を案内して終了 |

## モード: `status`（引数なしのとき）

1. `issue_mode.py` で設定を読む
2. `on` なら差分を出す（送信しない）:

   ```
   <ツール実行コマンド> .claude/tools/sync_issues.py
   ```

3. 3 行で報告する:

   ```
   Issue 追跡: {on / off}（リポジトリ: {owner/repo または なし}）
   差分: 作成 {n} / 更新 {n} / 取り込み候補 {n}
   次: {/issue sync（差分がある） / なし（同期済み）}
   ```

`off` のときは 1 行目だけを返し、`/issue on` の存在を添える。

## モード: `on`（使い始める・途中から切り替える）

1. `gh auth status` と `gh repo view --json nameWithOwner` で
   **認証とリポジトリを確認する** 。どちらかが失敗したらここで止める
   （認証情報は自分で入力しない。ユーザーに `gh auth login` を案内する）
2. 設定を書き換える:

   ```
   <ツール実行コマンド> .claude/tools/issue_mode.py --set on --repo <owner/repo>
   ```

3. ラベルを確認する（`gh label list`）。規約のラベル
   （`slice` / `debt` / `L1` / `L2` / `L3`）に無いものがあれば、
   **作成してよいかユーザーに確認してから** `gh label create` する
4. 差分を出す（`sync_issues.py`。送信しない）
5. 「何本作るか」を提示し、承認を得てから `/issue sync` へ進むよう案内する
   （このコマンドでは作成まで行わない）

既に L3 のスライスは既定では Issue にしない。履歴として残したいときだけ
`sync_issues.py --include-done` を使う（作った直後に閉じる）。

## モード: `off`（やめる・一時的に止める）

1. 開いている Issue を数える（`gh issue list --state open`）
2. 1 本以上あれば、停止コメントを付けてよいか確認する:

   > このリポジトリは Issue 追跡を停止しました。
   > 進捗は `docs/backlog.md` を参照してください。

   承認が得られたら `gh issue comment` で付ける。 **閉じない・消さない**
3. 設定を書き換える:

   ```
   <ツール実行コマンド> .claude/tools/issue_mode.py --set off
   ```

4. 「以後どのエージェントも `gh issue` を呼ばない」ことを 1 行で報告する

## モード: `sync`（バックログ → Issue）

`Task(issue-manager)` を起動する。プロンプトに次を必ず書く:

- 依頼: `docs/backlog.md` と GitHub Issue の差分を同期する
- **承認なしで `--apply` を実行しないこと**
- 差分は「作成 {n} / 更新 {n} / 閉じる {n}」の形で先に提示すること

差分の提示を受けたら、ユーザーに確認してから適用させる。

## モード: `new <内容>`

**バックログを先に更新する** （正はバックログ。Issue から作らない）。

1. `/backlog <内容>` と同じ判定でスライス表か負債表に行を足す
   （ゴールに寄与しないなら「今回のゴールの外」表へ。Issue は作らない）
2. コミットする（接頭辞 `docs:`）
3. `/issue sync` に進む（新しい行が Issue になる）

「Issue だけ作ってバックログに載せない」は行わない —— 正が 2 つになる。

## モード: `pull`（外部起票の取り込み）

`Task(issue-manager)` を起動する。判定基準は `docs/concept.md` のゴール。

1. タイトルが `S##:` / `D##:` で始まらない open Issue を集める
2. 1 本ずつ「寄与する / しない」を判定してバックログへ振り分ける
3. 取り込んだものはタイトルに接頭辞を付けて対応付ける
4. **判定に迷ったものは勝手に決めず、一覧にしてユーザーへ提示する**

## モード: `close S##`

**L3 に到達したスライスだけ閉じる。** `docs/backlog.md` の成熟度を読み、
L3 未満なら閉じずに理由を返す（規約: L1・L2 は完了ではない）。

## 使わないと決めているとき

何も設定しなければ `使用: off` のままで、
**このコマンド以外は Issue に一切触れません** （`/iterate` も `/status` も
挙動が変わらない）。GitHub を使わないプロジェクトでは `/issue` を
一度も実行しなくてよい。

## やってはいけないこと

- 承認なしで `gh issue create` / `edit` / `close` / `comment` を実行する
- Issue に進捗を書いてバックログを更新しない（正が 2 つになる）
- `使用: off` のまま `gh issue` を呼ぶ
- L1・L2 のスライスの Issue を閉じる
- 反復の段ごとに Issue を切る（Issue 1 本 = バックログ 1 行）
