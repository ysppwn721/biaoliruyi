# -*- mode: python ; coding: utf-8 -*-
"""Linux 原生包专用 spec（信创适配用）。

与 `zhilian.spec` 的差别只有一处，但很关键：

  **Linux 变体不打包 pywebview（webview / pythonnet / clr_loader / bottle /
  proxy_tools）。**

原因：`packaging/launcher.py` 在 pywebview 不可用时会自动回退到系统浏览器
（见 launcher.py 的 desktop_mode 分支），所以去掉它功能不缺。而 Linux 上
pywebview 会牵出 GTK/Qt 整套图形栈，实测（objdump）这些库正是产物里
glibc 需求最高的部分：

    libQt5Core.so.5   -> GLIBC_2.35
    libinput.so.10    -> GLIBC_2.35
    libcairo.so.2     -> GLIBC_2.35
    libsystemd.so.0   -> GLIBC_2.34

而国产桌面系统（统信 UOS 20 / 银河麒麟 V10 一系）的 glibc 基线约为 2.28，
带上这些库会直接以 `version 'GLIBC_2.34' not found` 启动失败。

**构建基线也必须在 spec 之外控制**：收集的 Python 与扩展库带有 glibc 版本要求，
因此 Linux 包必须在老 glibc 环境里构建（见 build_legacy_glibc.sh，默认
python:3.10-slim-buster = Debian 10 = glibc 2.28）。在 Ubuntu 22.04（glibc 2.35）
上构建出来的产物上不了国产系统。

两个变体（由环境变量 ZHILIAN_WITH_MODEL 控制）
------------------------------------------------
    ZHILIAN_WITH_MODEL=0（默认）  规则 + 在线 API 模式，约 70-80 MB
    ZHILIAN_WITH_MODEL=1         上述 + 本地 ONNX 语义模型，约 700 MB

**为什么必须分两个变体**：基础包排除了 onnxruntime / numpy / tokenizers 以控制体积，
所以**即使把 560 MB 的模型文件夹放到程序旁边，冻结包里也没有推理引擎**——
`reranker.status()` 会返回 False 并静默退回规则模式，用户以为装上了其实没生效。
要让本地模型真正可用，必须把这三个依赖一起打进去（即 ZHILIAN_WITH_MODEL=1）。
"""
from pathlib import Path
import os
import sys

from PyInstaller.building.build_main import Analysis, BUNDLE, COLLECT, EXE, PYZ

ROOT = Path(SPECPATH).resolve().parent
WITH_MODEL = os.environ.get("ZHILIAN_WITH_MODEL", "0").strip().lower() in {"1", "true", "yes", "on"}
MODEL_DIR = ROOT / "models" / "bge-reranker-v2-m3-onnx-int8"

datas = [
    (str(ROOT / "web"), "web"),
    (str(ROOT / "README.md"), "."),
    (str(ROOT / ".env.example"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
]
if WITH_MODEL:
    if not MODEL_DIR.is_dir():
        raise SystemExit(
            f"ZHILIAN_WITH_MODEL=1 需要模型目录：{MODEL_DIR}\n"
            "请先放入 bge-reranker-v2-m3-onnx-int8（约 560 MB），"
            "或以 ZHILIAN_WITH_MODEL=0 构建基础包。"
        )
    # 放到 Zhilian/models/… —— launcher.py 会自动发现可执行文件旁的 models 目录
    # 并设置 ZHILIAN_LOCAL_RERANKER_PATH / ENABLED，用户无需手工配置。
    datas.append((str(MODEL_DIR), "models/bge-reranker-v2-m3-onnx-int8"))

hiddenimports = [
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
    "multipart", "docx", "pptx", "openpyxl", "pydantic", "fastapi",
]

# 与 zhilian.spec 一致地排除重型可选依赖；额外排除图形后端与 Windows 专用件。
excludes = ["torch", "transformers", "tensorflow", "pytest", "pandas", "matplotlib",
            "IPython", "mcp",
            # —— Linux 变体新增：不打包图形后端 ——
            "webview", "pythonnet", "clr_loader", "bottle", "proxy_tools",
            "tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "gi",
            # 减少无谓的 lxml 子模块与 Pillow 插件（文档工作流用不到）
            "lxml.objectify", "lxml.html", "lxml.isoschematron",
            "PIL.ImageCms", "PIL.WebPImagePlugin"]
if not WITH_MODEL:
    # 基础包：不带本地推理引擎（要装模型请用 ZHILIAN_WITH_MODEL=1 的完整包）
    excludes += ["onnxruntime", "numpy", "tokenizers"]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Zhilian",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=str(ROOT / "web" / "assets" / "brand" / "concept-a.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Zhilian")
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='Zhilian.app', bundle_identifier='space.zhilian.desktop',
                 info_plist={'CFBundleShortVersionString': '0.2.1', 'NSHighResolutionCapable': True})
