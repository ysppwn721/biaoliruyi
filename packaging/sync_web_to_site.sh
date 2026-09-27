#!/usr/bin/env bash
# 把前端源码 web/ 同步到站点副本 site/static/。
#
# 为什么需要这个脚本
# ------------------
# 应用（FastAPI）从 web/ 提供界面，而 Cloudflare Worker 从 site/ 提供静态站；
# 两者曾各自被手工修改，导致 site/static/app.js 比 web/app.js 落后 3664 字节
# （缺 appendDocuments、semantic=1、zhilian-auto-export 三处功能），线上演示站
# 因此跑的是旧前端。没有任何构建步骤做同步，这就是"改了一处忘了另一处"的结构性
# 隐患。
#
# 规则：**web/ 是唯一真源**。改前端只改 web/，然后跑本脚本同步。
#
#   bash packaging/sync_web_to_site.sh          # 同步
#   bash packaging/sync_web_to_site.sh --check  # 只校验，有漂移则退出码 1（供 CI 用）
set -euo pipefail

ROOT="$(cd "$(dirname "$(realpath "$0")")/.." && pwd)"
SRC="$ROOT/web"
DST="$ROOT/site/static"
FILES=(index.html style.css app.js)
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

[ -d "$SRC" ] || { echo "缺少源码目录: $SRC" >&2; exit 2; }
mkdir -p "$DST"

drift=0
for f in "${FILES[@]}"; do
  if [ ! -f "$SRC/$f" ]; then
    echo "  跳过（源码缺失）: $f" >&2
    continue
  fi
  if [ -f "$DST/$f" ] && cmp -s "$SRC/$f" "$DST/$f"; then
    echo "  ✅ 一致      $f"
    continue
  fi
  if [ "$CHECK" = "1" ]; then
    echo "  ❌ 已漂移    $f（web/ 与 site/static/ 不同；跑本脚本同步）" >&2
    drift=1
  else
    cp -f "$SRC/$f" "$DST/$f"
    echo "  ⇄ 已同步    $f"
  fi
done

if [ "$CHECK" = "1" ] && [ "$drift" = "1" ]; then
  echo
  echo "前端两份不一致：site/ 是部署目录，web/ 才是源码。请运行：" >&2
  echo "  bash packaging/sync_web_to_site.sh" >&2
  exit 1
fi

if [ "$CHECK" = "0" ]; then
  echo
  echo "同步完成。site/static/ 现在是 web/ 的副本。"
  echo "提醒：部署站点时 Worker 读取 site/，因此同步后需要 npx wrangler deploy。"
fi
