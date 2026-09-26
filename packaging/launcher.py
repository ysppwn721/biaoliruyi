"""Cross-platform frozen entry point for the Zhilian local workbench."""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1]


def user_data_dir() -> Path:
    home = Path.home()
    if sys.platform.startswith("win"):
        return Path(os.getenv("LOCALAPPDATA", home / "AppData" / "Local")) / "Zhilian" / "data"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Zhilian" / "data"
    return Path(os.getenv("XDG_DATA_HOME", home / ".local" / "share")) / "zhilian"


def main() -> None:
    root = bundle_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.environ.setdefault("ZHILIAN_HOST", "127.0.0.1")
    os.environ.setdefault("ZHILIAN_PORT", "8765")
    os.environ.setdefault("ZHILIAN_DATA_DIR", str(user_data_dir()))
    Path(os.environ["ZHILIAN_DATA_DIR"]).mkdir(parents=True, exist_ok=True)

    from zhilian.app import load_environment

    load_environment()
    import uvicorn

    host = os.environ["ZHILIAN_HOST"]
    port = int(os.environ["ZHILIAN_PORT"])
    url = f"http://127.0.0.1:{port}"
    if os.getenv("ZHILIAN_NO_BROWSER", "0").lower() not in {"1", "true", "yes", "on"}:
        threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(url)), daemon=True).start()
    print(f"Zhilian is running at {url}; data directory: {os.environ['ZHILIAN_DATA_DIR']}")
    uvicorn.run("zhilian.app:app", host=host, port=port, log_level=os.getenv("ZHILIAN_LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
