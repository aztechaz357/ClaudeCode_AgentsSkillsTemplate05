---
description: ローカル LLM（gemma・qwen 等）で駆動するときの検査とモード切り替え
---

# ローカル LLM モード

**引数:** `check`（既定）/ `on` / `off`

既定は Claude Code の基盤モデル。このコマンドは **ローカル LLM に
切り替えたときだけ** 使う。設定手順の全体は `.claude/local-llm/README.md`。

## `check`（引数なしのとき）

接続とモデルの適合を **推測せず機械的に** 確かめる。

1. 環境変数を確認する（`ANTHROPIC_BASE_URL` が空なら基盤モデルで動いている
   ということ。その旨を報告して終了する）

   ```
   powershell -NoProfile -Command "$env:ANTHROPIC_BASE_URL; $env:ANTHROPIC_MODEL"
   ```

2. ブリッジ（`ollama_bridge.py`）を使う構成なら、生きているか確認する。
   落ちていたら「別シェルで `start-bridge.ps1` を起動する」と伝えて止まる

   ```
   curl -s -m 5 http://127.0.0.1:8787/health
   ```

3. エンドポイントを検査する（前置コマンドはプロファイルの
   「`.claude/tools/` の Python ツール実行」）

   ```
   <ツール実行コマンド> .claude/tools/check_llm_endpoint.py
   ```

4. 結果を 3 行で報告する:
   - 4 項目すべて PASS → 「このエンドポイントで駆動できる」
   - `tools` が FAIL → **ここで止める** 。「モデルかプロキシを変えない限り
     Claude Code は動かない」と伝える（性能以前の問題）
   - それ以外の FAIL → `.claude/local-llm/README.md` の「うまく動かないとき」の
     該当行を引用して対処を示す

5. `.steering/local-mode.md` の有無を確認し、モードの現状も報告する

## `on`

小さいモデル向けの進め方に切り替える。

1. `.claude/local-llm/policy.md` を読む（以後この規則に従う）
2. `.steering/` が無ければ作り、`.steering/local-mode.md` を次の内容で書く:

   ```markdown
   # local mode: ON

   有効化: {YYYY-MM-DD HH:MM}
   モデル: {ANTHROPIC_MODEL の値}
   規則: .claude/local-llm/policy.md

   このファイルがある間、全エージェントは小型モデル運用規則に従う。
   ```

3. 以後の進め方を宣言する（この 4 点だけを 4 行で述べる）:
   - 1 ターン 1 タスクで進み、毎回止まって報告する
   - `/add-feature` は無停止で走らせず、ステップごとに停止する
   - サブエージェントは同時に 1 体だけ起動する
   - 判断に迷ったら推測せず質問する

## `off`

1. `.steering/local-mode.md` を削除する
2. 通常の進め方（`/add-feature` の原則無停止）に戻ったことを 1 行で報告する
3. 基盤モデルへ戻すには、シェルの `ANTHROPIC_BASE_URL` などを解除して
   Claude Code を起動し直す必要がある旨を添える（環境変数は
   このコマンドでは変えられない）

## 注意

- **このコマンドは環境変数を書き換えない** 。接続先の切り替えは
  シェル（`.claude/local-llm/env.example.*`）の役割
- `.steering/` は gitignore 対象。モードの状態は環境ごとに独立する
- ローカル LLM で走らせた記録（どこで止まったか）は `.steering/` に残る。
  数反復分たまったら `/improve-process` で、止まりやすい工程を
  ツール化・チェックリスト化する材料にする
