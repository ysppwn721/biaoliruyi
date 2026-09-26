# 知链跨平台打包

基础包不内置本地 reranker，当前 Windows 便携包约 26MB，启动后即可运行规则、智能体、Word/PPT/Excel 处理和可选 API。解压后可双击 `启动知链.bat` 或 `Zhilian.exe`。`models/bge-reranker-v2-m3-onnx-int8` 是独立的可选模型包，解压到安装包根目录的 `models/` 后再设置 `ZHILIAN_LOCAL_RERANKER_PATH`。

## Windows

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller==6.16.0
.\packaging\build.ps1
```

产物：`artifacts/Zhilian-0.2.1-windows-x64.zip`。解压后运行 `Zhilian/Zhilian.exe`。数据默认写入 `%LOCALAPPDATA%\Zhilian\data`，不会写入安装目录。

## macOS / Linux

在目标系统执行：

```bash
python3 -m pip install -r packaging/requirements.txt
bash packaging/build.sh
```

产物是 `artifacts/Zhilian-0.2.1-darwin-arm64.tar.gz`、`darwin-x86_64.tar.gz` 或 `linux-x86_64.tar.gz`，由目标机器架构决定。macOS 数据写入 `~/Library/Application Support/Zhilian/data`，Linux 数据写入 `$XDG_DATA_HOME/zhilian` 或 `~/.local/share/zhilian`。

## 可选模型包

Windows 执行 `packaging/build_model_bundle.ps1`；macOS/Linux 执行 `bash packaging/build_model_bundle.sh`。模型包与基础包分离，避免离线模型占用基础安装包体积。模型包约 570MB，当前线上默认仍建议 BGE ONNX + 规则收紧候选。

## 安装验收

设置 `ZHILIAN_NO_BROWSER=1` 后启动可用于无界面验收；默认启动会打开 `http://127.0.0.1:8765`。首次验收建议点击“体验演示项目”，完成一次 Excel → Word/PPT 的验证与导出。不要把 `.env` 或任何 API Key 放入压缩包。
