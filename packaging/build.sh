#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(dirname "$(realpath "$0")")")"

PYTHON="${PYTHON:-python3}"
"$PYTHON" -m PyInstaller --clean --noconfirm packaging/zhilian.spec
# Pillow's optional AVIF codec is not used by the document workflow.
find dist/Zhilian -type f -iname '*avif*' -delete 2>/dev/null || true
find dist/Zhilian -type f -iname '*imagingft*' -delete 2>/dev/null || true
cp packaging/start_portable.bat dist/Zhilian/start_portable.bat
version="0.2.1"
mkdir -p artifacts
platform="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
archive="artifacts/Zhilian-${version}-${platform}.tar.gz"
rm -f "$archive"
tar -czf "$archive" -C dist Zhilian
printf 'Created %s\n' "$archive"
