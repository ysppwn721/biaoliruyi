#!/usr/bin/env bash
# Install the PyInstaller Linux bundle without root privileges.
set -eu
umask 077

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$APP_ROOT/zhilian-app"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
CONFIG_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/zhilian"
CONFIG_FILE="$CONFIG_DIR/.env"

[ -x "$SRC_DIR/Zhilian" ] || {
  echo "缺少 Zhilian 可执行文件，安装包不完整。" >&2
  exit 1
}

mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"
rm -rf "$APP_DIR/Zhilian"
mkdir -p "$APP_DIR/Zhilian"
cp -a "$SRC_DIR"/. "$APP_DIR/Zhilian"/

# If the optional model archive was unpacked next to the Zhilian directory,
# include it in the user installation. This keeps the base package small while
# making the separate model download work without manual path guessing.
MODEL_DIR="$SRC_DIR/../models/bge-reranker-v2-m3-onnx-int8"
if [ -d "$MODEL_DIR" ] && [ ! -d "$APP_DIR/Zhilian/models/bge-reranker-v2-m3-onnx-int8" ]; then
  mkdir -p "$APP_DIR/Zhilian/models"
  cp -a "$MODEL_DIR" "$APP_DIR/Zhilian/models/"
fi

# The frozen launcher stores configuration in ~/.local/share/zhilian/.env.
# Enable the local model automatically when it is present; preserve any API
# key or quota settings already written by the user.
MODEL_FILE="$APP_DIR/Zhilian/models/bge-reranker-v2-m3-onnx-int8/onnx/model_int8.onnx"
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_FILE" ]; then
  printf '%s\n' '# Zhilian local configuration; never share API keys.' 'DEEPSEEK_API_KEY=' > "$CONFIG_FILE"
fi
chmod 600 "$CONFIG_FILE"
if [ -f "$MODEL_FILE" ]; then
  sed -e '/^ZHILIAN_LOCAL_RERANKER_ENABLED=/d' \
      -e '/^ZHILIAN_LOCAL_RERANKER_PATH=/d' "$CONFIG_FILE" > "$CONFIG_FILE.tmp"
  printf '%s\n' 'ZHILIAN_LOCAL_RERANKER_ENABLED=1' \
    "ZHILIAN_LOCAL_RERANKER_PATH=$APP_DIR/Zhilian/models/bge-reranker-v2-m3-onnx-int8" >> "$CONFIG_FILE.tmp"
  mv "$CONFIG_FILE.tmp" "$CONFIG_FILE"
fi
chmod 600 "$CONFIG_FILE"

cat > "$BIN_DIR/zhilian" <<EOF
#!/usr/bin/env bash
exec "$APP_DIR/Zhilian/Zhilian" "\$@"
EOF
chmod +x "$BIN_DIR/zhilian"

# 把 BIN_DIR 写进 PATH：统信 UOS / 银河麒麟默认**不会**把 ~/.local/bin 加入 PATH
# （Ubuntu 由 ~/.profile 处理），只在末尾打印提示等于把问题丢给用户——实测麒麟上
# 安装完敲 zhilian 得到"未找到命令"。这里直接追加，幂等且不覆盖已有配置。
case ":$PATH:" in
  *":$BIN_DIR:"*) : ;;   # 当前会话已在 PATH 中
  *)
    for RC in "$HOME/.bashrc" "$HOME/.profile"; do
      [ -e "$RC" ] || continue
      if ! grep -qsF "export PATH=\"$BIN_DIR:\$PATH\"" "$RC"; then
        printf '\n# 知链：把用户级可执行目录加入 PATH（由 install.sh 添加）\nexport PATH="%s:$PATH"\n' "$BIN_DIR" >> "$RC"
      fi
    done
    export PATH="$BIN_DIR:$PATH"
    ;;
esac

for ASSET_ROOT in "$APP_DIR/Zhilian/_internal" "$APP_DIR/Zhilian"; do
  if [ -f "$ASSET_ROOT/web/assets/brand/concept-a-512.png" ]; then
    cp "$ASSET_ROOT/web/assets/brand/concept-a-512.png" "$ICON_DIR/zhilian.png"
    chmod 644 "$ICON_DIR/zhilian.png"
    break
  fi
done

cat > "$DESKTOP_DIR/zhilian.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=知链
Name[en]=Zhilian
Comment=跨文档结论验证与增量修复
Exec="$BIN_DIR/zhilian"
Terminal=true
Categories=Office;Utility;
StartupNotify=false
Icon=$ICON_DIR/zhilian.png
EOF
chmod +x "$DESKTOP_DIR/zhilian.desktop"

echo "安装完成。"
echo "启动命令：$BIN_DIR/zhilian"
echo "项目数据仍保存在：${XDG_DATA_HOME:-$HOME/.local/share}/zhilian"
if case ":$PATH:" in *":$BIN_DIR:"*) true ;; *) false ;; esac; then
  echo "已把 $BIN_DIR 写入 PATH（新开终端或先执行 source ~/.bashrc 后可直接敲 zhilian）。"
else
  echo "当前会话可直接使用上面的完整路径启动。"
fi
