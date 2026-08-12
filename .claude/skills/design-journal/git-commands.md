# 節目の操作コマンド（PR・マージ・ブランチ）

**どのプロジェクトでも同じ操作の型** 。`design-journal` スキルの一部として
テンプレートに同梱する。プロジェクト固有のもの（実際に打った引数・
そこで詰まったこと）は `docs/journal/commands.md` に足す。

各項目は **何をするか / 実際に打ったもの / 落とし穴** の 3 点で書く。
出力は **実測のみ** を貼る（絶対ルール 7）。得ていないものは
「実測: 未取得」と明記して、次に打ったときに埋める。
実測の出力は、リポジトリ名だけ `<owner>/<repo>` に伏せ、
長い一覧は `...` で省いてある（それ以外は打ったままの文字列）。

> 前提: `gh`（GitHub CLI）が認証済みであること。
> 確認は `gh auth status` 。PowerShell 5.1 では `&&` `||` が使えないので、
> コマンドは 1 行ずつ打つか `;` でつなぐ。

## 1. 出す前に状態を見る

**何をするか**: 未コミットの有無・ブランチ・既に PR があるかを 1 度で確かめる。
これを飛ばすと「同じ PR を 2 本作る」「未コミットのまま push する」が起きる。

```
git status --short
git log --oneline -6
gh pr list --state open --json number,title,headRefName,baseRefName,mergeable,mergeStateStatus
```

実測（このリポジトリ。既に PR がある状態）:

```
[{"baseRefName":"main","headRefName":"feature_05","mergeStateStatus":"CLEAN",
  "mergeable":"MERGEABLE","number":4,
  "title":"プロセス: 追いつけなくなるのを防ぐ 3 本..."}]
```

**落とし穴**

- `mergeable` が `MERGEABLE` でも `mergeStateStatus` が `BLOCKED` なら
  レビュー必須・CI 未完了。 **2 つを両方見る**
- `git status --short` が何も出さないのが正常（クリーン）。
  出力が空でも成功なので、空を失敗と読み違えない

## 2. ローカルとリモートが同じか確かめる

**何をするか**: push 漏れの検出。PR は **リモートの内容** をマージするので、
手元にだけあるコミットは入らない。

```
git rev-parse HEAD origin/<ブランチ>
```

実測（2 行が同じハッシュなら push 済み）:

```
6194a383eaa264a38b6aee40f986d58e53408a3b
6194a383eaa264a38b6aee40f986d58e53408a3b
```

**落とし穴**: `origin/<ブランチ>` は手元のキャッシュ。疑わしいときは先に
`git fetch` してから比べる。

## 3. PR を作る

**何をするか**: ブランチを `main`（既定ブランチ）へ出す。

```
gh pr create --base main --head <ブランチ> --title "<題名>" --body-file <本文.md>
```

実測: 未取得（次に PR を作ったときに出力を貼る）。
成功すると PR の URL が 1 行返る。

**落とし穴**

- **本文は必ず `--body-file` で渡す** 。`--body "..."` に日本語の
  複数行を直接書くと、改行と引用符がシェルで壊れる。
  本文は一時ファイル（スクラッチパッド）に書いてから渡す
- `--head` を省くと現在のブランチが使われる。 **切り替え忘れの事故が多い**
  ので明示する
- 本文には **なぜ** と **却下した案** を書く。差分は GitHub 側で読めるので、
  何を変えたかの列挙だけの本文は価値が低い

## 4. 作った後に PR の中身を直す

**何をするか**: 後からコミットが乗って、題名や本文が実態と合わなくなったとき。

```
gh pr view <番号> --json body --jq .body
gh pr view <番号> --json commits --jq '.commits[].messageHeadline'
gh pr edit <番号> --title "<題名>" --body-file <本文.md>
```

実測（`gh pr edit` の返り）:

```
https://github.com/<owner>/<repo>/pull/4
```

**落とし穴**: レビュー前に本文を直すのは無害だが、
**レビュー後に本文だけ直すとレビュアーの前提が黙って変わる** 。
後から変えたことをコメントで伝える。

## 5. マージする

**何をするか**: PR を既定ブランチへ取り込み、作業ブランチを消す。

```
gh pr merge <番号> --rebase --delete-branch
```

実測（`main` が早送りされている。ファイル一覧の中間は省いた）:

```
From https://github.com/<owner>/<repo>
 * branch            main       -> FETCH_HEAD
   cc472ac..b50bbc2  main       -> origin/main
Updating cc472ac..b50bbc2
Fast-forward
 .claude/README.md                     |  13 +-
 .claude/agents/code-reviewer.md       |   4 +-
 ...
 36 files changed, 1995 insertions(+), 56 deletions(-)
```

### 3 つの取り込み方の選び方（ここが判断点）

| 方式 | 履歴の形 | 選ぶとき | 失うもの |
|---|---|---|---|
| `--rebase` | 直線。コミットがそのまま並ぶ | **1 コミット 1 意図で積んである** とき（このテンプレートの既定） | 「どこからどこまでが 1 つの PR か」の境界 |
| `--squash` | 1 PR = 1 コミット | 途中の試行錯誤を残したくないとき | 途中のコミットメッセージ全部 |
| `--merge` | 分岐と合流が残る | 並行ブランチが多く、分岐の形に意味があるとき | 履歴の読みやすさ（線が増える） |

**このテンプレートは `--rebase` を既定にする。**
理由: 「1 コミット 1 意図・差分 20〜30 行で区切る」を規約にしているので、
コミット 1 つずつが読める単位になっており、潰すと情報が減るため。

**落とし穴**

- **`;` で他のコマンドとつながない。** `gh pr merge` を連結すると
  実行の許可判定に引っかかって止まることがある。 **単独で打つ**
- `--delete-branch` はリモートを消すが、 **手元の `origin/<ブランチ>` の
  参照は残る** 。項目 6 で掃除する
- マージ後は手元が `main` に切り替わり早送りされる。
  作業を続けるなら **新しいブランチを切り直す**

## 6. ブランチを片づける

**何をするか**: 消えたリモートブランチの参照を手元から落とす。

```
git fetch --prune
git branch -a
```

実測:

```
 - [deleted]         (none)     -> origin/feature_05
* main
  remotes/origin/HEAD -> origin/main
  remotes/origin/main
```

**落とし穴**: `--prune` が消すのは **参照だけ** 。
ローカルのブランチ本体は消えないので、`git branch -d <名前>` で別に消す
（`-d` は未マージなら拒否する安全側。`-D` は強制なので理由が無いと使わない）。

## 7. 次の作業ブランチを切る

```
git switch -c <ブランチ>
git branch --show-current
```

実測:

```
Switched to a new branch 'feature_06'
feature_06
```

**落とし穴**: 既定ブランチ（`main`）の上で直接編集しない。
このテンプレートは「既定ブランチでは作業しない」を前提に組んである。

## 8. 既定ブランチを変える（最初に 1 回だけ）

**何をするか**: GitHub 側の既定ブランチを差し替える。
PR の `--base` の既定値・リポジトリを開いたときの表示が変わる。

```
gh api -X PATCH repos/<owner>/<repo> -f default_branch=main
gh repo view --json defaultBranchRef --jq .defaultBranchRef.name
```

実測: 未取得（切り替えたときに出力を貼る）。

**落とし穴**: 既定ブランチを変えても **既に開いている PR の base は
変わらない** 。開いている PR は `gh pr edit <番号> --base main` で個別に直す。

## 9. 戻し方（先に知っておく）

| 何を戻す | コマンド | 注意 |
|---|---|---|
| マージした内容 | `gh pr create` で **打ち消しの PR** を出す | 共有ブランチの履歴改変（`push --force`）はしない |
| まだ push していないコミット | `git reset --soft HEAD~1` | `--hard` は作業内容ごと消える。理由が無いと使わない |
| 間違えて消したブランチ | `git reflog` でハッシュを探して `git switch -c <名前> <ハッシュ>` | reflog は手元にしか無い |

**破壊的操作は必ず確認してから**（絶対ルール 4）。
特に `reset --hard` `push --force` `branch -D` の 3 つは、
打つ前に何が消えるかを言葉にしてから打つ。
