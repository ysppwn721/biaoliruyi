# 鸿蒙 PC 与信创系统 · 现场验证清单

目的：用最少的现场时间，把三个未知量测出来——
**(1) 鸿蒙 PC 能不能跑我们的 Linux 版；(2) 浏览器路径能不能用；(3) 文件能不能进能出。**

> 背景：华为鸿蒙 PC 端已上线「融合开发引擎」，官方文档见
> https://consumer.huawei.com/cn/support/content/zh-cn16114608/
> 有报道称其可直接运行 Linux 环境。**若成立，则我们无需为鸿蒙重写 ArkTS 客户端。**
> 但"提供 Linux 环境"的具体形态（完整发行版 / 受限容器 / 能否读写宿主机文件）必须现场确认。

---

## 一、先分清你手上是什么

### ⚠️ 关于模拟器：不需要找"PC 模拟器"，它不存在

鸿蒙 PC 在开发者体系里的设备类型叫 **`2in1`**（二合一）。但华为开发者论坛有两条标题即
此问题的帖子，说明**本地模拟器的设备类型列表里没有 2in1/PC**：

- 「DevEco Studio 没有 2in1 的模拟器」
  https://developer.huawei.com/consumer/cn/forum/topic/0204165579894404091?fid=26
- 「2in1 模拟器支持 mac(m2) 电脑吗？DevEco Studio 模拟器列表内没有」
  https://developer.huawei.com/consumer/cn/forum/topic/0201165605056889231

自查路径：**Device Manager → New Emulator → 看设备类型下拉里有没有 `2in1`**，
并核对官方 26.0.0 版本说明是否新增了模拟器设备类型。

**更重要的是：PC 模拟器本来就验证不了我们要验证的东西。**

| 想验证的 | PC 模拟器 | 原因 |
| --- | --- | --- |
| 融合开发引擎跑 Linux 版 | ❌ | 它是**应用市场里的 App**；模拟器里没有应用市场，也测不出"与宿主机文件系统互通" |
| 文件能否进能出 | ❌ | 模拟器的文件系统是虚拟的，与真机行为不同 |
| **浏览器能否正常用工作台** | ✅ **任意鸿蒙模拟器都行** | **内核同为 ArkWeb** |

**结论：用任意一个鸿蒙模拟器（手机/平板，DevEco 一定提供）打开我们的工作台测浏览器兼容性即可。**

| 形态 | 能否装到现有 Windows 电脑 | 优先级 |
| --- | --- | --- |
| 鸿蒙 PC 系统镜像（ISO） | **基本不行**，镜像不对外开放 | — |
| 鸿蒙电脑真机（MateBook Pro 等） | 不适用 | ⭐ 最优先（能试融合开发引擎） |
| **鸿蒙手机/平板模拟器**（DevEco 自带） | 可下载 | ⭐ **测浏览器内核兼容性，性价比最高** |
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

## 三、路径 B：浏览器直连（保底，**也是性价比最高的一条**）

任何鸿蒙设备打开：

```
https://demo.zhilian.space/
账号 zhilian / zhilian2026
```

> **在模拟器上也能测**：鸿蒙手机/平板模拟器的浏览器与鸿蒙 PC 是**同一套 ArkWeb 内核**，
> 因此不需要 PC 模拟器，用现成的模拟器就能验证掉我们唯一剩下的未知量——
> **内核兼容性**。真机只在需要验证"融合开发引擎跑 Linux 版"时才必要。

需确认：

- [ ] 华为浏览器能正常渲染工作台（ArkWeb 内核）
- [ ] 能唤起文件选择器并上传本地 Excel / Word / PPT
- [ ] 「运行智能体」→ 人工确认 → 导出修复后文件，全流程可用
- [ ] 下载的 docx 能被鸿蒙上的办公软件正常打开、格式完好

这条路径**不需要任何安装包**，且已在我们自己的服务器上验证过。
若它能跑通，鸿蒙就已被覆盖——**竞赛材料里可以如实写"通过浏览器支持鸿蒙"**。

---

## 四、回来要给我的信息

1. 你拿到的是**真机**还是**模拟器**？设备型号与系统版本号。
   （模拟器请注明设备类型是 Phone / Tablet / 还是真有 2in1）
2. 若用真机试了融合开发引擎：`/etc/os-release`、`uname -m`、`python3 -V` 的输出。
3. 路径 B 四项勾选结果（**这一项的优先级高于融合引擎**，因为它是保底能力）。
4. 若试了融合引擎：文件"进能出"三个问题的结果。
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
