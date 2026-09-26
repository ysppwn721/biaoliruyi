# 鸿蒙 PC 与信创系统 · 现场验证清单

目的：用最少的现场时间，把三个未知量测出来——
**(1) 鸿蒙 PC 能不能跑我们的 Linux 版；(2) 浏览器路径能不能用；(3) 文件能不能进能出。**

> 背景：华为鸿蒙 PC 端已上线「融合开发引擎」，官方文档见
> https://consumer.huawei.com/cn/support/content/zh-cn16114608/
> 有报道称其可直接运行 Linux 环境。**若成立，则我们无需为鸿蒙重写 ArkTS 客户端。**
> 但"提供 Linux 环境"的具体形态（完整发行版 / 受限容器 / 能否读写宿主机文件）必须现场确认。

---

## 一、先分清你手上是什么

| 形态 | 能否装到现有 Windows 电脑 | 优先级 |
| --- | --- | --- |
| 鸿蒙 PC 系统镜像（ISO） | **基本不行**，镜像不对外开放 | — |
| 鸿蒙电脑真机（MateBook Pro 等） | 不适用 | ⭐ 最优先 |
| DevEco Studio 模拟器 | 可下载，但需确认含 **PC 设备类型** | ⭐ 次优先（无真机时） |
| 华为浏览器（任意设备） | — | ⭐ 随时可测 |

---

## 二、路径 A：融合开发引擎（最值得先试）

在鸿蒙 PC 的**应用市场**安装「融合开发引擎」，打开后逐项确认：

### A1. 环境形态（3 分钟）

```bash
cat /etc/os-release          # 是完整发行版还是精简容器？
uname -m                     # 架构：x86_64 / aarch64
python3 -V                   # 有没有 Python，版本多少（我们要 ≥3.8）
apt-get --version | head -1  # 有没有包管理器（决定能否补依赖）
df -h /                      # 磁盘余量
```

**判读**：
- 有 `python3` 且 ≥3.8 → 大概率能跑，继续 A2
- 只有 busybox / 无包管理器 → 受限容器，走路径 B
- 架构是 aarch64 且能装 pip → 也能跑，但**不要装本地重排模型**（numpy/onnxruntime 可能无轮子）

### A2. 装依赖并启动（10 分钟）

只装精简后的运行时依赖（实测 104 MB，无需 pandas/pdfplumber）：

```bash
# 1) 取代码（或从 U 盘拷入离线包）
git clone --depth 1 https://github.com/ysppwn721/biaoliruyi.git
cd biaoliruyi

# 2) 建虚拟环境（系统不许装 venv 时用自带 Python 直接装）
python3 -m venv .venv && . .venv/bin/activate
pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements-runtime.txt

# 3) 启动（纯规则模式，不需要密钥、不需要联网）
ZHILIAN_HOST=127.0.0.1 ZHILIAN_PORT=8765 python run.py
```

然后本机浏览器打开 `http://127.0.0.1:8765`。

**若 `python-docx / python-pptx` 装不上**（lxml、Pillow 无轮子），改用系统包：
```bash
apt-get install -y python3-lxml python3-pil python3-openssl
```

### A3. 命门验证：文件能不能进能出（最关键，5 分钟）

这一步决定产品在鸿蒙上**是否成立**——我们的核心动作是"读 Excel/Word/PPT → 写回新版本"。

1. 浏览器点「导入我的文件」，选一份 `.xlsx` + 一份 `.docx`，**能否选中宿主机上的真实文件？**
2. 项目建好后点「导出成果」，**能否保存到宿主机可访问的位置（而不是困在容器里）？**
3. 用办公软件打开导出的 docx，**格式是否完好？**

**判读**：第 1、2 步任一失败 → 融合引擎的 Linux 环境与鸿蒙文件系统不通，只能用路径 B。

---

## 三、路径 B：浏览器直连（保底，随时可用）

任何鸿蒙设备（含平板、鸿蒙 PC）打开：

```
https://demo.zhilian.space/
账号 zhilian / zhilian2026
```

需确认：

- [ ] 华为浏览器能正常渲染工作台（ArkWeb 内核）
- [ ] 能上传本地 Excel / Word / PPT
- [ ] 「运行智能体」→ 人工确认 → 导出修复后文件，全流程可用
- [ ] 下载的 docx 能被鸿蒙上的办公软件正常打开

这条路径**不需要任何安装包**，且已在我们自己的服务器上验证过。
若它能跑通，鸿蒙就已被覆盖——**竞赛材料里可以如实写"通过浏览器支持鸿蒙"**。

---

## 四、回来要给我的信息

1. 你拿到的是**真机**还是**模拟器**？设备型号与系统版本号。
2. 融合开发引擎给的 Linux 环境：`/etc/os-release`、`uname -m`、`python3 -V` 的输出。
3. A3 三个问题的结果（能否选到宿主机文件、能否导出到宿主机、格式是否完好）。
4. 路径 B 四项勾选结果。
5. 截图：工作台页面 + 导出的文件在办公软件里打开的界面。

有了这些我就能：确定要不要出鸿蒙专用包；若要，是「轻量 Web 容器 `.hap`」还是别的形态。

---

## 五、顺带一起看的信创系统（UOS / 麒麟）

如果现场也有统信 UOS 或银河麒麟机器，一并测这四项：

```bash
cat /etc/os-release           # 发行版与版本
uname -m                      # x86_64 / aarch64 / loongarch64 / mips64el / sw64
python3 -V                    # 版本（UOS 20 与麒麟 V10 桌面自带 3.7，低于我们要求的 3.8）
python3 -c "import lxml, PIL; print('lxml/PIL 已在系统里')" 2>&1 | tail -1
getstatus 2>/dev/null || which setstatus >/dev/null && echo "存在 kysec 强制访问控制" || echo "无 kysec"
```

**判读**：

| 观察 | 结论 |
| --- | --- |
| `uname -m` = x86_64 | 现有包可直接试装 |
| = aarch64 | 需 aarch64 包；规则模式依赖可从系统仓库拿 |
| = loongarch64 / mips64el / sw64 | **只走规则模式**，本地语义模型上不了 |
| Python 3.7 | 需 PyInstaller 自包含包，不能依赖系统 Python |
| 有 kysec | 安装路径与执行权限可能被拦，需按其策略配置 |
