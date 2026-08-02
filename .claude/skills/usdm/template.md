## 要求

> 要求の正は下の HTML 1 枚。 **ここに要求の本文を書き写さない**
> （二重管理になり、必ず食い違う）。記法の正は
> `.claude/skills/usdm/SKILL.md` 。

- 要求（USDM）: [docs/usdm/src/S{番号}-{name}.html](../usdm/src/S{番号}-{name}.html)
- 要求一覧（生成物）: [docs/usdm/index.html](../usdm/index.html)

<!--
新しいスライスに着手するときの手順:

1. `.claude/skills/usdm/template.html` を
   `docs/usdm/src/S{番号}-{name}.html` にコピーする
   （品質要求なら `template-quality.html` を `Q##-<name>.html` へ）
2. `{}` を埋める。L1 では 要求 1 個・理由 1 行・仕様 1〜3 条
3. `<ツール実行コマンド> .claude/tools/build_usdm.py` で検証と再生成
4. 上のリンクのパスを実物に合わせる

記入例: `.claude/skills/usdm/example/`（話題沸騰ポット）
-->
