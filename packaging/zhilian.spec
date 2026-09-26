# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.building.build_main import Analysis, COLLECT, EXE, PYZ

ROOT = Path(SPECPATH).resolve().parent
datas = [
    (str(ROOT / "web"), "web"),
    (str(ROOT / "README.md"), "."),
    (str(ROOT / ".env.example"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
]
hiddenimports = [
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
    "multipart", "docx", "pptx", "openpyxl", "pydantic", "fastapi",
]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # The base installer must stay small.  Local reranking is an optional
    # add-on; without these packages reranker.status() safely falls back to
    # deterministic rules/API mode.
    excludes=["torch", "transformers", "tensorflow", "pytest", "onnxruntime", "numpy", "tokenizers", "pandas"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Zhilian",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Zhilian")
