# 本地启动 WebUI

## 本地精简版（WB/Ozon 采集 → 编辑 → 发布）

双击根目录 `start-lite.bat`。首次运行会同步 Python 依赖、安装并构建前端，服务就绪后自动打开浏览器。只运行 WebUI，不需要 MySQL、MCP、RabbitMQ、AI 或独立 worker。

1. 首次网页登录使用 `admin / admin`；在「店铺管理」填写 Ozon Client ID 和 API Key。
2. 在「系统设置」填写 RUB/CNY 汇率、选择店铺合同币。
3. Chrome/Edge 扩展管理页开启开发者模式，加载项目下的 `ozon-seller-helper-ext` 文件夹。
4. 插件弹窗选择「本地软件」并登录同一本地账号。在 WB/Ozon 商品页点击采集，自动打开对应草稿。
5. 编辑俄语标题、描述、类目、必填特征、价格和图片。点击「发布到 Ozon」时先保存，再显示发布预览供确认。

WB 及本机上传的图片会由插件转存到卖家媒体库，需要同一浏览器已登录 `seller.ozon.ru`。上传失败时保持待上传状态，可在插件点击「重试待上传图片」。Ozon 原生图片可直接使用。本版不发布视频及富文本，采集的原内容保留在草稿原始数据中。

精简版使用 `apps/webui/data/lite/products.db`，不会覆盖原库；仅加载可选的 `.env.lite.local`，不加载 `.env.local`。继承的 MySQL 配置不会改变精简版数据库，监听地址固定为回环地址。本版不自动发布、不扣发布费用。

常用命令：`./start-lite.ps1 -SkipSync`（跳过依赖同步）、`./start-lite.ps1 -ForceFrontendBuild`（代码更新后重建界面）。默认 8585；冲突时自动换候选端口，插件自动探测。

「已提交，平台处理中」表示 Seller API 已接收任务；只有确认结果成功才显示「发布成功」。实际采集依赖源站页面可访问，实际发布依赖有效店铺凭证。

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
