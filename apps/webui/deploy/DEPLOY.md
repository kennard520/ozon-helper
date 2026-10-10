# 部署到服务器（Docker + MySQL）

> 现状:**uv workspace monorepo**(`apps/{webui,image_worker}` + `packages/{ozon_common,ozon_api}`),后端 Docker 跑、数据 MySQL。后端纯 Python(采集走插件、媒体走 OSS、定价走静态表),不需要浏览器/Playwright。

## ⚠️ 部署前必读:数据库迁移
本仓库的 DAL 用 SQLAlchemy + Alembic(`migrations/versions/`)。**`metadata.create_all` 只建缺失的「表」,不会给已存在的表加「列」**。所以升级已有 MySQL 库时,**必须先跑 Alembic 迁移**,否则新代码 SELECT 新列会崩。
- 关键迁移:`0006_in_gallery`(draft_images.in_gallery)、`0007_draft_image_local_url`(draft_images.local_url)、`0008_text_jobs`(文本生成 MQ 任务状态表)、`0009_task_runs`(统一任务进度/失败原因索引)、`0010_task_runs_nullable_draft`(全局后台任务)。
- 上线当前代码前在生产 MySQL 跑:`python -m uv run --package ozon-webui alembic upgrade head`(或容器内 `alembic upgrade head`),并按 `docs/dal-m4-mysql-verification-checklist.md` 核对。
- 全新库:`create_all` 已含全部列,首启自动建表,无需迁移。

## 0. 前提
- Linux 服务器(Ubuntu 22.04+,1C2G 够用)+ Docker。
- 一个 MySQL(可同机 Docker 容器,挂 `ozonnet` 网络)。
- 一个域名,A 记录指向服务器(HTTPS + 插件基本必须)。

## 0.1 当前生产拓扑
- Web 后端/前端主服务部署在 `8.152.196.119`,容器名 `ozon-webui`,对外端口 `8585`。
- Worker 主要部署在 `110.42.226.37`、`124.223.39.167`,容器名通常为 `ozon-text-worker`、`ozon-image-worker`。
- MCP 部署在 `110.42.226.37`,容器名 `ozon-mcp`,端口映射为 `8586`。
- `110.42.226.37`、`124.223.39.167` 已做免密/密码脚本登录；`8.152.196.119` 的 root 登录使用密钥文件:

```text
C:\Users\42918\.ssh\a119.pem
```

部署 Web 热修时优先连 `8.152.196.119`,不要误把 Web 改动只打到 worker/MCP 机器。

## 1. MySQL(若还没有)
```bash
docker network create ozonnet  # 若无
docker run -d --name mysql --restart always --network ozonnet \
  -e MYSQL_ROOT_PASSWORD=<root密码> -e MYSQL_DATABASE=ozon \
  -e MYSQL_USER=ozon -e MYSQL_PASSWORD=<ozon密码> \
  -v /opt/mysql-data:/var/lib/mysql mysql:8
```
> ⚠️ 安全:**MySQL 3306 不要对公网开放**(只挂 docker 内网 ozonnet)。生产 DB 密码勿明文写进入库的文档。

## 2. 构建镜像 + 起后端(redeploy 配方:tarball → build → swap)
本机(或 CI)打包源码 → 传服务器 → docker build → 换容器:
```bash
# 本机:打包当前 HEAD
git archive --format=tar.gz -o /tmp/ozon.tgz HEAD
# 传到服务器后:
mkdir -p /opt/ozon && tar xzf ozon.tgz -C /opt/ozon && cd /opt/ozon
docker build -t ozon-webui:latest .        # 根 Dockerfile(uv workspace 构建)
# 先跑迁移(见上「部署前必读」),再换容器:
docker rm -f ozon-webui 2>/dev/null || true
docker run -d --name ozon-webui --restart always --network ozonnet -p 8585:8585 \
  -e OZON_MYSQL_HOST=mysql -e OZON_MYSQL_PORT=3306 \
  -e OZON_MYSQL_USER=ozon -e OZON_MYSQL_PASSWORD=<ozon密码> -e OZON_MYSQL_DB=ozon \
  -e OSS_ENDPOINT=... -e OSS_BUCKET=... -e OSS_ACCESS_KEY_ID=... -e OSS_ACCESS_KEY_SECRET=... -e OSS_PUBLIC_BASE=... \
  ozon-webui:latest
docker logs -f ozon-webui                   # 看启动
curl -s http://127.0.0.1:8585/api/ext/ping  # 自检
```
> 镜像 `CMD` = `uv run --package ozon-webui ozon-webui`(= `webui/server.py:main`,自动选端口/默认 8585)。前端 `apps/webui/frontend/dist` 已在镜像内(构建产物),由 FastAPI 托管。env 变量名见 `apps/image_worker/.env.template`(webui 复用同名 OZON_MYSQL_*/OSS_*)。

## 3. 图生图 worker(可选,第二容器)
```bash
docker run -d --name ozon-worker --restart always --network ozonnet \
  --env-file /opt/ozon/.env \
  ozon-webui:latest uv run --package ozon-image-worker ozon-worker
```
> 需 RABBITMQ_* + GPTPLUS5_* + OZON_MYSQL_*(见 `.env.template`)。

## 3.1 文本生成 worker(可选,AI 生成内容异步化)
工作台「AI 生成内容」会发布 RabbitMQ `ozon_text_jobs` 消息，并写 `text_jobs` 任务状态；需要单独启动文本 worker 消费：
```bash
docker run -d --name ozon-text-worker --restart always --network ozonnet \
  --env-file /opt/ozon/.env \
  ozon-webui:latest uv run --package ozon-image-worker ozon-text-worker
```
> 文本 worker 与图生图 worker 共用同一个 RabbitMQ broker 和 MySQL；上线前确认已跑 `alembic upgrade head`，且 admin(user_id=1) 设置里有 Ozon Client-Id/Api-Key 与文本 AI 配置。

## 4. HTTPS 反代(Caddy)
```bash
sudo cp apps/webui/deploy/Caddyfile /etc/caddy/Caddyfile   # 域名改成你的,反代到 127.0.0.1:8585
sudo systemctl reload caddy
# 浏览器 https://app.你的域名.com → 登录(首次默认 admin/admin,登录后改密)
```

## 5. 初始化数据 / 配置
- 首启自动建表 + admin/admin + jwt_secret(全新库)。
- OSS:env 注入 或「设置」里配(全局键 user_id=0)。
- 「设置→Ozon 店铺」加店、填 Client-Id/Api-Key(多店存 settings.ozon_stores)。

## 6. 备份(必做)
```bash
# 每天 dump MySQL
echo '0 3 * * * docker exec mysql mysqldump -uozon -p<ozon密码> ozon | gzip > /opt/backup/ozon-$(date +\%F).sql.gz' | crontab -
```

## ⚠️ 收别人用之前(SaaS)
- 后端**明文存** Ozon Api-Key、部分表尚未按 user_id 强隔离。**自用 OK,收陌生用户前**必须做密钥加密 + 全表租户隔离(见 spec)。
- 插件目前连 `127.0.0.1`,远程采集需插件支持配置后端地址(单独插件改动)。
