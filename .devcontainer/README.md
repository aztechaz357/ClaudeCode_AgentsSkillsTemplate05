# Dev Container（Claude Code をサンドボックスで動かす）

Claude Code を **Dev Container の中** で動かし、さらに **Claude Code 自身の
サンドボックス** を有効にするための一式です。狙いは 3 つ。

1. **開発環境が整っている** —— このテンプレートの規約が要求する検証
   （PowerShell ツール・図の検証・Python ツール）が最初から動く
2. **勝手に環境を壊されない** —— 壊せる範囲がコンテナとワークスペースに
   限られ、ホストには届かない
3. **危険な外部通信をしない** —— 既定拒否の送信許可リストを 2 段で持つ

## 防御の 3 層

| 層 | 実体 | 何を守るか | 守らないもの |
|---|---|---|---|
| 1. コンテナ | Docker + `devcontainer.json` | ホストのファイル・OS・他プロジェクト | マウントしたワークスペース自体 |
| 2. 送信ファイアウォール | `init-firewall.sh`（iptables + ipset） | コンテナ全体の外向き通信（エージェントが起動した任意のプロセスを含む） | 許可ドメイン内での振る舞い |
| 3. Claude Code サンドボックス | `claude-user-settings.json`（bubblewrap + プロキシ） | Claude が実行する個々のコマンドのファイル/通信 | Claude を経由しない操作 |

**なぜ 2 と 3 の両方が要るのか** —— 2 は IP ベースなので、許可ドメインの
CDN が IP を変えると通らなくなる代わりに、 **Claude を通さない通信も含めて**
コンテナから出るすべてを止められる。3 は名前ベースで正確だが、
**Claude が起動したコマンドにしか効かない** 。層が違うので併用する。

層 1 だけでは「コンテナの中から外部へ何でも送れる」状態が残り、
層 3 だけでは「サンドボックス外のプロセス」が抜け道になる。

## 使い方

### VS Code

1. Docker Desktop（または Docker Engine）を起動する
2. このリポジトリを VS Code で開き、 **Reopen in Container** を実行する
3. 初回は `post-create.sh` が Claude Code の導入・`powershell` の配線・
   サンドボックス設定の配置を行う（数分）
4. コンテナ内のターミナルで `claude` を起動し、初回のみログインする
   （認証情報は名前付きボリューム `/home/vscode/.claude` に残るので、
   リビルドしても消えない）

### CLI

```bash
npm install -g @devcontainers/cli
devcontainer up --workspace-folder .
devcontainer exec --workspace-folder . claude
```

## 効いていることを確かめる

**「たぶん効いている」で運用しない。** コンテナ内で次を実行する。

```bash
# 層 2: 許可外は落ちる / 許可先は届く（init-firewall.sh 自身も毎回検証する）
curl -sS --max-time 5 https://example.com          ; echo "blocked? exit=$?"   # 非 0 が正
curl -s -o /dev/null -w '%{http_code}\n' https://api.anthropic.com             # 数字が出れば OK

# 層 3: サンドボックスの前提が揃っているか
command -v bwrap && command -v socat
cat ~/.claude/settings.json | jq '.sandbox.enabled, .sandbox.network.strictAllowlist'

# 開発環境: テンプレートのツールが動くか
powershell -NoProfile -File .claude/tools/check_numbering.ps1 -Path CLAUDE.md
powershell -NoProfile -File .claude/tools/check_diagrams.ps1 -Path docs
```

ファイアウォールを張り直したいとき（長時間セッションで CDN の IP が
変わった場合など）:

```bash
sudo /usr/local/bin/init-firewall.sh
```

## 調整する

| 変えたいもの | 触る場所 | 反映 |
|---|---|---|
| 送信を許可するドメイン（層 2） | `allowed-domains.txt` | **リビルド** （実行時に緩められないよう、イメージに焼き込む） |
| サンドボックスの許可ドメイン（層 3） | `claude-user-settings.json` | コンテナ内 `~/.claude/settings.json` を更新するか、ボリュームを消して再作成 |
| Mermaid / PlantUML の同梱 | `devcontainer.json` の `build.args`（`WITH_MERMAID` / `WITH_PLANTUML`） | リビルド |
| sudo の全面禁止 | `build.args` に `"LOCK_DOWN_SUDO": "true"` | リビルド |
| ベースイメージ・言語ランタイム | `build.args.BASE_IMAGE` / `features` | リビルド |

層 2 と層 3 のドメイン一覧は **別々の仕組み** なので、片方だけ足すと
片方で止まる。増やすときは両方に書く。

### sudo の扱い

既定では `vscode` に sudo が残っている（人間が `apt install` できるように）。
Claude には `permissions.deny` の `Bash(sudo:*)` `Bash(iptables:*)` などで
届かないようにしてある。 **より強く締めるなら** `LOCK_DOWN_SUDO=true` で
ビルドする —— `post-create.sh` の最後に全面 sudo が外れ、root で実行できるのは
`/usr/local/bin/init-firewall.sh` だけになる（`apt install` も人間ができなくなる）。

## 既知の限界（正直に把握しておくもの）

- **ワークスペースは壊せる** —— リポジトリはバインドマウントなので、
  コンテナ内から消せる。最後の砦は git（コミット済みであること）と、
  `.claude/hooks/pre-tool-guard.ps1` の保護パス
- **IP 許可リストは陳腐化する** —— 層 2 は起動時点の名前解決結果。
  CDN の IP が変わったら張り直す
- **許可したドメインの中は自由** —— 例えば GitHub を許可した以上、
  GitHub への push は技術的に可能。ここを止めたいなら層 3 の
  `permissions.deny` と資格情報の与え方で制御する
- **`--cap-add=NET_ADMIN` が要る** —— ファイアウォールを張るために
  コンテナに権限を渡している。これは「コンテナ内の root がネットワーク設定を
  変えられる」ことも意味する（だから sudo を Claude から遠ざけてある）
- **ホストが Windows の場合の改行** —— `.sh` が CRLF だと Linux で
  `bash\r` エラーになる。`.gitattributes` で LF に固定済み

## ファイル

| ファイル | 役割 |
|---|---|
| `devcontainer.json` | イメージ・features・マウント・ライフサイクルの定義 |
| `Dockerfile` | OS パッケージ（iptables / bubblewrap / graphviz ほか）と uv、ファイアウォールの設置 |
| `post-create.sh` | Claude Code 導入・`powershell` シンボリックリンク・サンドボックス設定の配置 |
| `init-firewall.sh` | 既定拒否 + 許可リストの適用（毎起動・自己検証つき） |
| `allowed-domains.txt` | 層 2 の許可ドメイン（プロジェクト固有） |
| `claude-user-settings.json` | 層 3（サンドボックス）の設定。コンテナ内のユーザー設定として置く |

> `sandbox.network.strictAllowlist` などは **プロジェクト設定では無視され、
> ユーザー設定・管理者設定でしか効かない** 。そのため `.claude/settings.json`
> ではなくコンテナ内の `~/.claude/settings.json` に置いている。
