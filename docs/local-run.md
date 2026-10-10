# 本地启动 WebUI

这个项目的前端不需要单独部署。Vue 前端先构建到 `apps/webui/frontend/dist/`，然后由 Python/FastAPI 一起托管。

## 一键启动

在项目根目录运行：

```powershell
.\start-local.bat
```

或者：

```powershell
.\start-local.ps1
```

脚本会做这些事：

1. 如果根目录存在 `.env.local`，先读取里面的环境变量。
2. 执行 `python -m uv sync` 安装/同步 Python 依赖。
3. 如果 `apps/webui/frontend/dist/index.html` 不存在，自动进入前端目录执行 `npm install` 和 `npm run build`。
4. 启动 Python WebUI：`python -m uv run --package ozon-webui ozon-webui`。

启动后看终端输出的地址，默认通常是：

```text
http://127.0.0.1:8585
```

如果 `8585` 被占用，后端会自动选择其它候选端口。

## 常用参数

指定端口：

```powershell
.\start-local.bat -Port 8585
```

跳过 Python 依赖同步：

```powershell
.\start-local.bat -SkipSync
```

跳过前端构建：

```powershell
.\start-local.bat -SkipFrontendBuild
```

强制重新构建前端：

```powershell
.\start-local.bat -ForceFrontendBuild
```

指定其它 env 文件：

```powershell
.\start-local.bat -EnvFile .env.production.local
```

## 数据库配置

数据库连接读取的是环境变量，代码位置：

- `packages/ozon_common/src/ozon_common/dal/engine.py`
- `apps/webui/src/webui/store.py`

规则：

- 设置了 `OZON_MYSQL_HOST`：连接 MySQL。
- 没有设置 `OZON_MYSQL_HOST`：连接本地 SQLite。

本地配置可以复制示例文件：

```powershell
Copy-Item .env.local.example .env.local
```

然后编辑 `.env.local`：

```env
OZON_MYSQL_HOST=生产库地址
OZON_MYSQL_PORT=3306
OZON_MYSQL_USER=ozon
OZON_MYSQL_PASSWORD=生产库密码
OZON_MYSQL_DB=ozon_smoke
```

`.env.local` 已加入 `.gitignore`，不要提交真实密码。

## 手动启动方式

如果不想用脚本，也可以手动执行：

```powershell
cd E:\personal\ozon-helper\apps\webui\frontend
npm install
npm run build

cd E:\personal\ozon-helper
python -m uv sync
python -m uv run --package ozon-webui ozon-webui
```

## 本地测试

后端测试：

```powershell
cd E:\personal\ozon-helper
python -m uv run python -m pytest apps/webui/tests packages --ignore-glob='*_live.py' -q
```

前端测试：

```powershell
cd E:\personal\ozon-helper\apps\webui\frontend
npm run test
```
