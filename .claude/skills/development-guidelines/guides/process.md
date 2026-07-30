# プロセスガイド

CLAUDE.md の開発フローを手順として展開したガイド。

## 開発の全体フロー

```
要求仕様書 → 設計書 → 作業計画 → TDD 実装 → 実装検証 → 統合テスト → 文書同期 → 振り返り
```

| 工程 | 成果物 | 使うスキル / エージェント |
|---|---|---|
| 要求仕様 | `docs/requirements/P##-*.md` | requirements-definition |
| 設計 | `docs/design/proposals/P##-*.md` | functional-design |
| 作業計画 | `.steering/<dir>/tasklist.md` | steering（計画モード） |
| TDD 実装 | ソース・テスト・マイクロコミット | steering（実装モード）/ tdd-implementer |
| 実装検証 | `reports/NN-implementation-validator.md` | implementation-validator |
| 統合テスト | 統合テスト・対応表 | integration-tester |
| 文書同期 | 現状設計書・リファレンス・マニュアル | architecture-design / doc-syncer |
| 振り返り | tasklist.md の振り返り・プロセス改善提案 | steering（振り返りモード） |

各工程は前工程の成果物を入力とする。前工程を飛ばさない
（「設計書なしで実装」「受け入れ条件なしで統合テスト」は禁止）。

## TDD サイクル（Red → Green → Refactor）

1. **Red**: テストを先に書き、プロファイルのテストコマンドで失敗を確認する
   （失敗確認を飛ばさない。テストが最初から通る = テストが仕様を
   検証していない疑い）
2. **Green**: 要求を満たす必要最小限の実装でテストを通す
3. **Refactor**: 全緑を保ったまま整理する
4. コミットしてから次の最小ステップへ

## マイクロコミット

- 1コミット = 1つの意図（アトミック）。関連のない変更を混ぜない
- 目安: 差分が20〜30行を超える、または無関係な複数の関数にまたがるなら
  コミットのタイミングが遅すぎる
- コミット前に必ず全テストの緑を確認する
- 先回りの実装・過剰な作り込みは禁止（今の要求に必要な最小限のみ）

## コミットメッセージ規約

書式の正はプロファイル。既定（日本語）は次のとおり:

- 1行目: 変更内容の要約（何をしたか）。接頭辞の例:
  `要求:`（要求仕様書）/ `設計:`（設計書・現状設計書）/ `実装:`（コード）/
  `テスト:`（統合テスト）/ `docs:`（文書同期）
- 本文: 「何を・どのファイルに・なぜ」を箇条書きで具体的に。テスト結果も書く

```
実装: Spinner クラス（背景スレッド・冪等 stop）を追加（P25 その2）

- presentation/spinner.py に Spinner クラスを追加
- 背景スレッドで FRAMES を巡回描画し、stop() は二度呼んでも安全（冪等）
- test/presentation/test_spinner.py にテスト4件を追加（Red→Green 確認）
- テスト: 415 passed / 6 skipped
```

- Windows / PowerShell 5.1 環境では here-string（`@'…'@`）でコミットし、
  メッセージに二重引用符（"）を含めない（引数分解事故の既知の教訓）

## 設計書との同期

1. **要求**: 受け入れ条件を確定させる（requirements-definition）
2. **設計**: 図面先行で設計書を作成し、設計だけでコミット（functional-design）
3. **実装**: 設計書の「テスト観点」をテストコードに翻訳するところから
   TDD で進める（steering でタスク管理）
4. **矛盾したら**: 設計と実装が食い違う判断はユーザーに確認し、
   設計書を先に直してから実装する（勝手にどちらかへ合わせない）
5. **反映**: 実装完了時に doc-syncer のチェックリストで文書を同期する

## 文書の記法

文書の記法規約（Markdown・数式と図表の番号・作図言語・マニュアル）の正は
**`writing-conventions` スキル** 。ここでは重複させない。

作業前に必ず読むもの:

- 本文を書く: `writing-conventions/guides/markdown.md`
- 数式・図・表を出す: `writing-conventions/guides/numbering.md`
- 図を描く: `writing-conventions/guides/diagrams.md`
- マニュアルを更新する: `writing-conventions/guides/manual.md`

検証コマンド（NG が出たまま完了としない）:

```
powershell -File .claude/tools/check_numbering.ps1 -Path <file.md|dir>
powershell -File .claude/tools/check_diagrams.ps1 -Path <file.md|dir>
```

## ブランチ・PR

- ブランチ戦略・既定ブランチ名はプロファイル参照
- push・PR 作成はユーザーの明示的な指示があるときのみ行う
