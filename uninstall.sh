#!/usr/bin/env bash
# 表里如一 —— Linux 卸载脚本
#
# 默认保留项目数据（.zhilian/），避免误删用户已建立的项目与版本记录。
# 需要连数据一起删除时加 --purge。
set -eu

APP_NAME="biaoliruyi"
APP_CN="表里如一"
PREFIX="${HOME}/.local/share/${APP_NAME}"
BIN_FILE="${HOME}/.local/bin/${APP_NAME}"
DESKTOP_FILE="${HOME}/.local/share/applications/${APP_NAME}.desktop"
ICON_FILE="${HOME}/.local/share/icons/hicolor/256x256/apps/${APP_NAME}.png"

BOLD=$'\033[1m'; RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'
ok()   { printf '%s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
warn() { printf '%s!%s %s\n' "$YELLOW" "$RESET" "$*"; }

PURGE=0
[ "${1:-}" = "--purge" ] && PURGE=1

printf '\n%s卸载 %s%s\n\n' "$BOLD" "$APP_CN" "$RESET"

removed=0
[ -e "$BIN_FILE" ]     && { rm -f "$BIN_FILE";     ok "已删除启动命令"; removed=1; }
[ -e "$DESKTOP_FILE" ] && { rm -f "$DESKTOP_FILE"; ok "已删除桌面菜单项"; removed=1; }
[ -e "$ICON_FILE" ]    && { rm -f "$ICON_FILE";    ok "已删除图标"; removed=1; }

command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "${HOME}/.local/share/applications" >/dev/null 2>&1 || true

if [ -d "$PREFIX" ]; then
    if [ "$PURGE" -eq 1 ]; then
        rm -rf "$PREFIX"
        ok "已删除程序目录与项目数据"
    else
        # 仅删除程序文件，保留 .zhilian 与用户导出成果
        for item in zhilian web tests third_party site .venv; do
            rm -rf "${PREFIX:?}/$item" 2>/dev/null || true
        done
        find "$PREFIX" -maxdepth 1 -type f \( -name '*.py' -o -name '*.sh' -o -name '*.txt' \
             -o -name '*.md' -o -name '*.xlsx' -o -name 'Dockerfile' \) -delete 2>/dev/null || true
        ok "已删除程序文件"
        warn "已保留项目数据：$PREFIX/.zhilian"
        printf '  如需一并删除：%s --purge\n' "$0"
    fi
    removed=1
fi

# 残留进程提示
if pgrep -f "zhilian.*run\.py" >/dev/null 2>&1; then
    warn "检测到仍在运行的服务进程，可执行：pkill -f 'run.py'"
fi

[ "$removed" -eq 1 ] || warn "未发现已安装的 $APP_CN"
printf '\n%s\n' "完成。"
