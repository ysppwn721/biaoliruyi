# 推送到 GitHub（照着做即可）

> 现状：本地已有 **8 个提交**，但 **GitHub 上还没有本项目仓库**，本地也未配置远程。
> 所以此前未发生任何推送。本机 `gh`（GitHub CLI）未登录，也没有可用的访问令牌。

## 方案 A：网页建空仓库 + 我推送（最快，约 30 秒）

### 第 1 步：在网页上建一个空仓库

打开 https://github.com/new ，填写：

| 字段 | 填什么 |
| --- | --- |
| Repository name | `biaoliruyi` |
| Description | 可填：跨文档结论一致性治理系统 · 参赛作品 |
| Visibility | 选 **Public** ⚠️ 不要选 Private |
| Initialize this repository with | **全部不勾**（不要 README、不要 .gitignore、不要 license） |

点 **Create repository**。

> **为什么必须建空的**：如果勾了 README 或 .gitignore，远端会先有一个提交，
> 推送时会因历史不一致被拒（提示 `non-fast-forward`），反而更麻烦。

### 第 2 步：告诉我"建好了"

我会自动完成：

```powershell
git remote add origin https://github.com/ysppwn721/biaoliruyi.git
git branch -M master main          # 统一主分支名为 main
git push -u origin main
```

推送用的是 Windows 凭据管理器里**已经存好的 GitHub 凭证**（`git:https://github.com` 与
`api.github.com/ysppwn721` 都有记录），正常情况下**不需要你再登录**。

若凭据已失效，GitHub Desktop 会自动弹窗让你重新授权一次。

---

## 方案 B：先用 gh 登录，我全自动完成（含建仓库）

在你自己的终端里运行：

```powershell
gh auth login
```

按提示选：

1. `GitHub.com`
2. `HTTPS`
3. 认证方式选 `Login with a web browser`
4. 记下屏幕上的一次性代码，回车后会打开浏览器，粘贴代码并授权
5. 授权范围至少包含 `repo`

完成后告诉我，我会一次性完成建仓库、配置远程、推送、并接上 Cloudflare Pages。

---

## 方案 C：只用 GitHub Desktop（不推荐，因为当前它没跟踪本项目）

当前 `%APPDATA%\GitHub Desktop\` 下**没有 `repositories.json`**，
说明这个目录还没被添加到 GitHub Desktop 里，所以界面上没有 Publish 按钮。

要用这条路：

1. GitHub Desktop → `File` → `Add local repository`
2. 路径选 `C:\Users\Administrator\Desktop\华北五省设计`
3. 添加后点 **Publish repository**
4. 弹窗里**取消勾选 `Keep this code private`**
5. Publish

---

## 推送前要确认的三件事

### 1. 不要提交大文件（我已配置好，无需你再操作）

- `models/` 下的 **543MB** ONNX 模型已被忽略 —— GitHub 单文件限 100MB，推上去会直接失败
- `.venv/`、`.zhilian/`、`.env`、测试产物也都已忽略
- 暂存内容中最大文件仅 **0.06MB**（`web/app.js`）

验证命令：

```powershell
git check-ignore -v models .venv .zhilian .env
git ls-files | Measure-Object -Line            # 应约 260 个文件
```

### 2. 确认 `.env` 里没有真实密钥

`.env` 已被忽略、不会上传。但要确认它**没有被复制进任何会被提交的文件**：

```powershell
git grep -n "sk-" -- . ':!site'         # 应无结果
git grep -n "DEEPSEEK_API_KEY=sk"       # 应无结果
```

### 3. 公开仓库意味着内容对所有人生效可见

| 内容 | 建议 |
| --- | --- |
| `zhilian/`、`web/`、`tests/`、`site/` | ✅ 应当公开（大赛要求提交完整源码） |
| `答辩评测/`（评测集与结果） | ✅ 建议公开，这是技术亮点证据 |
| `表里如一_项目综合评审报告.md` 等内部分析 | ⚠️ 自行判断 |
| `.env.example` | ✅ 公开（仅占位符） |

---

## 推送后的下一步

1. **Cloudflare Pages**：连接该仓库 → Build output directory 填 `site`、Build command 留空 → 部署 → 绑定域名
2. **重新打包安装包**：`site/downloads/` 里的包是从**旧交付包**打的，
   而根目录代码已更新（含本地 reranker 三档），需重新打包以免公网版本与代码不一致
