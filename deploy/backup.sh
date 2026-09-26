#!/usr/bin/env bash
# 知链演示环境每日备份。
#
# 备份对象：
#   - 项目数据目录（每个项目一个子目录，含 state.json 与各版本文件）
#   - 服务端 .env（含 DeepSeek 密钥；归档权限 0600，只能 root 读）
# 数据量很小（KB～MB 级），因此直接整目录打包，不做增量。
#
# 用法：
#   bash deploy/backup.sh                 # 打包 + 清理过期归档
#   ZHILIAN_BACKUP_KEEP_DAYS=30 bash deploy/backup.sh
#   bash deploy/backup.sh --list          # 只看现有归档
set -euo pipefail

DATA_DIR="${ZHILIAN_DATA_DIR:-/opt/zhilian/data}"
ENV_FILE="${ZHILIAN_ENV_FILE:-/opt/zhilian/biaoliruyi/.env}"
BACKUP_DIR="${ZHILIAN_BACKUP_DIR:-/opt/zhilian/backups}"
KEEP_DAYS="${ZHILIAN_BACKUP_KEEP_DAYS:-14}"

if [[ "${1:-}" == "--list" ]]; then
    ls -lh "$BACKUP_DIR" 2>/dev/null || echo "尚无备份目录：$BACKUP_DIR"
    exit 0
fi

if [[ ! -d "$DATA_DIR" ]]; then
    echo "数据目录不存在：$DATA_DIR" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="$BACKUP_DIR/zhilian-data-$STAMP.tar.gz"

# 打包时先复制到暂存目录，避免归档到写入一半的 state.json。
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/data"
cp -a "$DATA_DIR/." "$STAGE/data/" 2>/dev/null || true
if [[ -f "$ENV_FILE" ]]; then
    cp -a "$ENV_FILE" "$STAGE/env.backup"
fi
tar -czf "$ARCHIVE" -C "$STAGE" .
chmod 600 "$ARCHIVE"

# 立刻校验归档可读，避免"备份了但打不开"。
if ! tar -tzf "$ARCHIVE" >/dev/null 2>&1; then
    echo "归档校验失败，已删除：$ARCHIVE" >&2
    rm -f "$ARCHIVE"
    exit 1
fi

SIZE="$(du -h "$ARCHIVE" | cut -f1)"
FILES="$(tar -tzf "$ARCHIVE" | wc -l)"
echo "已备份：$ARCHIVE（$SIZE，$FILES 个条目）"

# 清理过期归档
DELETED="$(find "$BACKUP_DIR" -maxdepth 1 -name 'zhilian-data-*.tar.gz' -type f -mtime "+$KEEP_DAYS" -print -delete | wc -l)"
[[ "$DELETED" -gt 0 ]] && echo "已清理 $DELETED 个超过 $KEEP_DAYS 天的归档"
REMAIN="$(find "$BACKUP_DIR" -maxdepth 1 -name 'zhilian-data-*.tar.gz' -type f | wc -l)"
echo "当前保留 $REMAIN 个归档，目录占用 $(du -sh "$BACKUP_DIR" | cut -f1)"
