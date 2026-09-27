#!/usr/bin/env bash
# 在固定 glibc 基线的容器里构建 Linux x86_64 原生包（信创适配）。
#
# 为什么必须这样构建
# ------------------
# PyInstaller 收集的 Python 与扩展库可能要求构建机的 glibc 版本。经 objdump 实测，在 Ubuntu 22.04
# （glibc 2.35）上构建的包里有约 105 个捆绑库要求 glibc > 2.28，其中
# libpython3.10.so.1.0 要求 GLIBC_2.35——在统信 UOS 20 / 银河麒麟 V10 这类
# Debian 10 一系（glibc ≈2.28）的系统上会直接
#     version `GLIBC_2.34' not found
# 启动失败。
#
# 本脚本用 python:3.10-slim-buster（Debian 10，glibc 2.28）作为构建基线，
# 与国产桌面系统的基线对齐；产物再用干净的 debian:10 容器做**启动验收**。
#
# 用法
#   bash packaging/build_legacy_glibc.sh              # 构建基础包 + 完整包，并各自验收
#   VARIANTS=base bash packaging/build_legacy_glibc.sh   # 只出基础包（不含本地模型）
#   VARIANTS=full bash packaging/build_legacy_glibc.sh   # 只出完整包（含 560MB 模型）
#   IMAGE=quay.io/pypa/manylinux2014_x86_64 bash ...     # 更保守：glibc 2.17 基线
#
# 注意：需要 Docker（本机 Windows 无 Docker 时，请在 Linux 机器上执行）。
set -euo pipefail

ROOT="$(cd "$(dirname "$(realpath "$0")")/.." && pwd)"
cd "$ROOT"

IMAGE="${IMAGE:-python:3.10-slim-buster}"
VERIFY_IMAGE="${VERIFY_IMAGE:-debian:10}"
PIP_INDEX="${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}"
VERSION="${VERSION:-0.2.1}"
PLATFORM="linux-x86_64"
VARIANTS="${VARIANTS:-base full}"

# 基础包只装应用本体需要的依赖（不含本地重排模型三项）：
# 与 zhilian-linux.spec 的 excludes 保持一致，避免装了又被排除。
DEPS=(fastapi uvicorn python-multipart openpyxl python-docx python-pptx httpx pyinstaller)
# 完整包额外需要本地推理引擎，否则模型文件放进去也用不了（会静默退回规则模式）。
MODEL_DEPS=(onnxruntime numpy tokenizers)

build_variant() {
  local variant="$1" with_model="$2" out="$3"
  echo
  echo "==================================================================="
  echo "==> 变体 $variant（ZHILIAN_WITH_MODEL=$with_model）"
  echo "==================================================================="
  local deps=("${DEPS[@]}")
  if [ "$with_model" = "1" ]; then deps+=("${MODEL_DEPS[@]}"); fi

  docker run --rm -e ZHILIAN_WITH_MODEL="$with_model" -v "$ROOT":/w -w /w "$IMAGE" bash -lc "
    set -e
    # PyInstaller 在 Linux 上依赖 objdump（binutils）。Debian 10(buster) 已 EOL，
    # 官方源迁到 archive.debian.org（在德国，从国内访问极慢甚至卡死），
    # 因此改用**国内归档镜像**，并用 http（容器里没有 curl，也避免证书问题）。
    # 直接把源写死再让 apt-get update 当探测：装成功就 break。
    if ! command -v objdump >/dev/null 2>&1; then
      for m in http://mirrors.aliyun.com/debian-archive/debian http://mirrors.ustc.edu.cn/debian-archive/debian; do
        printf 'deb %s buster main\n' \"\$m\" > /etc/apt/sources.list
        apt-get -o Acquire::Check-Valid-Until=false -o Acquire::Retries=2 -o Acquire::http::Timeout=25 update -qq >/dev/null 2>&1 \
          && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends binutils >/dev/null 2>&1 \
          && command -v objdump >/dev/null 2>&1 && break
      done
    fi
    command -v objdump >/dev/null 2>&1 || { echo '  ❌ 无法安装 binutils（objdump），PyInstaller 无法继续'; exit 1; }
    echo \"  objdump: \$(objdump --version | head -1)\"
    pip install -q --no-cache-dir -i '$PIP_INDEX' ${deps[*]}
    python -m PyInstaller --clean --noconfirm packaging/zhilian-linux.spec
    # python-docx opens parts/../templates/*.xml. The frozen archive keeps
    # modules in PYZ, so the intermediate parts directory must also exist.
    mkdir -p dist/Zhilian/_internal/docx/parts dist/Zhilian/_internal/pptx/parts
    find dist/Zhilian -type f -iname '*avif*' -delete 2>/dev/null || true
    find dist/Zhilian -type f -iname '*imagingft*' -delete 2>/dev/null || true
    cp packaging/install_native_linux.sh dist/Zhilian/install.sh
    cp packaging/uninstall_native_linux.sh dist/Zhilian/uninstall.sh
    ldd --version | head -1
  "

  mkdir -p artifacts
  tar -czf "$out" -C dist Zhilian
  echo "    产物: $out  ($(du -h "$out" | cut -f1))"

  echo "==> 验收：在干净的老 glibc 容器($VERIFY_IMAGE)里启动并请求 /api/health"
  docker run --rm -v "$ROOT/$out":/pkg.tar.gz "$VERIFY_IMAGE" bash -lc "
    set -e
    ldd --version | head -1
    mkdir -p /x && tar -xzf /pkg.tar.gz -C /x
    cd /x/Zhilian
    ZHILIAN_HOST=127.0.0.1 ZHILIAN_PORT=8766 ZHILIAN_DATA_DIR=/tmp/d \
      ./Zhilian --no-browser > /tmp/log 2>&1 &
    for i in \$(seq 1 40); do
      # A clean debian image has neither curl nor Python. Use bash TCP with
      # a bounded read so the verification needs no package installation.
      code=\$(timeout 2 bash -c 'exec 3<>/dev/tcp/127.0.0.1/8766; printf \"GET /api/health HTTP/1.0\\r\\nHost: localhost\\r\\n\\r\\n\" >&3; read -r -t 1 protocol status rest <&3; printf \"%s\" \"\$status\"' 2>/dev/null || true)
      [ \"\$code\" = '200' ] && { echo '  ✅ 老 glibc 环境启动成功，/api/health 返回 200'; break; }
      sleep 0.5
    done
    [ \"\$code\" = '200' ] || { echo '  ❌ 启动失败，日志：'; tail -20 /tmp/log; exit 1; }
    # 完整包要额外确认推理引擎真的在包里（这正是基础包做不到的那件事）
    if [ '$with_model' = '1' ]; then
      found=\$(find /x/Zhilian -maxdepth 3 -iname 'model_int8.onnx' | head -1)
      [ -n \"\$found\" ] && echo \"  ✅ 模型已随包分发: \$found\" || { echo '  ❌ 未找到模型文件'; exit 1; }
      python3 -c 'import sys; sys.path.insert(0,\"/x/Zhilian/_internal\"); import onnxruntime; print(\"  ✅ onnxruntime 可用:\", onnxruntime.__version__)' 2>/dev/null \
        || echo '  ⚠️ 无法在该容器内验证 onnxruntime（缺 libgomp 属正常，真机再验）'
    fi
  "
}

for v in $VARIANTS; do
  case "$v" in
    base) build_variant base 0 "artifacts/Zhilian-${VERSION}-${PLATFORM}-glibc228.tar.gz" ;;
    full) build_variant full 1 "artifacts/Zhilian-${VERSION}-${PLATFORM}-glibc228-with-model.tar.gz" ;;
    *) echo "未知变体: $v" >&2; exit 2 ;;
  esac
done

echo
echo "完成。"
echo "  仅生成 VARIANTS=$VARIANTS 指定的产物；以 artifacts 中实际文件为准。"
echo "  构建基线: $IMAGE     验收环境: $VERIFY_IMAGE"
echo "  下一步  : 拷进 UOS / 麒麟 虚拟机，执行 bash install.sh 后启动。"
