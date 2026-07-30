#!/usr/bin/env bash
# {{NAME}} の動作確認テスト。
#
# 工房レーンでもテストは先に書く。雛形の時点では「未実装で落ちること」を
# Red として確認し、本実装に着手したら実際の仕様のテストへ置き換える。
#
# 終了コード: 0 = 全て合格 / 1 = 不合格あり
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
failed=0

if bash "$here/{{ENTRY}}" >/dev/null 2>&1; then
  echo "NG: {{NAME}} は未実装なのに成功した"
  failed=1
else
  echo "OK: {{NAME}} は未実装のため想定どおり失敗した"
fi

exit "$failed"
