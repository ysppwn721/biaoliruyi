# 阿里云同域部署

这套部署让同一个域名同时提供产品首页和真实演示：

- `https://zhilian.space/`：产品介绍、下载和使用说明
- `https://zhilian.space/demo/`：真实知链工作台
- `https://zhilian.space/api/*`、`/static/*`：由 Caddy 转发到 FastAPI

不需要 Quick Tunnel。服务器需要 Docker、Docker Compose，以及安全组放行 TCP 80 和 443。

## 首次部署

在本地项目根目录执行：

```powershell
scp -r deploy site zhilian Dockerfile requirements.txt run.py <SSH用户>@<服务器IP>:/opt/zhilian/
```

然后登录服务器：

```bash
cd /opt/zhilian/deploy
cp .env.example .env
vi .env
docker compose up -d --build
docker compose ps
```

将域名 `zhilian.space` 的 DNS A 记录指向服务器公网 IP。若 DNS 由 Cloudflare 托管，可以开启代理；Caddy 仍会自动申请 HTTPS 证书。域名生效后验证：

```bash
curl -I https://zhilian.space/
curl -u zhilian:<部署密码> https://zhilian.space/api/health
```

浏览器打开 `https://zhilian.space/demo/`，用户名固定为 `zhilian`，密码是 `.env` 中的 `ZHILIAN_ACCESS_PASSWORD`。

## 更新版本

```bash
cd /opt/zhilian
git pull
cd deploy
docker compose up -d --build
```

用户数据保存在 Docker volume `deploy_zhilian_data`，更新镜像不会删除项目数据。不要把 `.env` 提交到 Git，也不要把 API Key 写入站点文件。
