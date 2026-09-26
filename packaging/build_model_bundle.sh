#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(dirname "$(realpath "$0")")")"
model="models/bge-reranker-v2-m3-onnx-int8"
test -d "$model" || { echo "Model directory missing: $model" >&2; exit 1; }
mkdir -p artifacts
archive="artifacts/Zhilian-bge-reranker-v2-m3-onnx-int8.tar.gz"
rm -f "$archive"
tar -czf "$archive" "$model"
printf 'Created %s\n' "$archive"
