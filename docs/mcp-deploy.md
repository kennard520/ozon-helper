# Ozon MCP 部署文档

这份文档用于把 `ozon-helper` 的 MCP 服务部署到服务器，并接入 ChatGPT 官网的自定义 MCP 连接器。

## 1. 当前推荐方案

ChatGPT 官网要求 MCP 地址必须是公网 HTTPS。推荐结构：

```text
ChatGPT
  -> https://indistinguishably-schorlaceous-serafina.ngrok-free.dev/mcp
  -> ngrok 固定域名
  -> 服务器 110.42.226.37:8586
  -> Docker 容器 ozon-mcp
  -> MySQL / OSS / Ozon 配置
```

当前推荐给 ChatGPT 填写的服务器 URL：

```text
https://indistinguishably-schorlaceous-serafina.ngrok-free.dev/mcp
```

`https://mcp.ryda.top/mcp` 也可以作为正式域名方案，但需要 443/80 正常通、证书正常、域名解析和云厂商访问限制都放行。

## 2. MCP 两种入口

项目里有两个命令：

```bash
ozon-mcp
ozon-mcp-chatgpt
```

推荐 ChatGPT 使用：

```bash
ozon-mcp-chatgpt
```

原因：它是精简工具集，不暴露旧的后端 AI/worker 一键流程，避免 ChatGPT 调错工具。

本地默认地址：

```text
http://127.0.0.1:8586/mcp
```

服务器默认端口：

```text
8586
```

## 3. 本地运行

在仓库根目录执行：

```bash
python -m uv sync --package ozon-mcp
python -m uv run --package ozon-mcp ozon-mcp-chatgpt
```

如果要让外部访问：

```bash
set OZON_MCP_HOST=0.0.0.0
set OZON_MCP_PORT=8586
set OZON_MCP_USER_ID=1
set OZON_MCP_ALLOWED_HOSTS=127.0.0.1:*,localhost:*
python -m uv run --package ozon-mcp ozon-mcp-chatgpt
```

Windows PowerShell 写法：

```powershell
$env:OZON_MCP_HOST="0.0.0.0"
$env:OZON_MCP_PORT="8586"
$env:OZON_MCP_USER_ID="1"
$env:OZON_MCP_ALLOWED_HOSTS="127.0.0.1:*,localhost:*"
python -m uv run --package ozon-mcp ozon-mcp-chatgpt
```

## 4. Docker 镜像构建

根目录的 `Dockerfile` 已经包含 `apps/mcp_server`。

先构建前端，因为 Dockerfile 会复制 `apps/webui/frontend/dist`：

```bash
cd apps/webui/frontend
npm install
npm run build
cd ../../..
```

构建镜像：

```bash
docker build -t ozon-mcp:chatgpt-minimal .
```

## 5. 服务器 Docker 启动

先准备环境变量文件，例如 `/opt/ozon-helper/.env.mcp`：

```env
OZON_MYSQL_HOST=你的 MySQL 地址
OZON_MYSQL_PORT=3306
OZON_MYSQL_USER=你的 MySQL 用户
OZON_MYSQL_PASSWORD=你的 MySQL 密码
OZON_MYSQL_DB=ozon

OZON_MCP_HOST=0.0.0.0
OZON_MCP_PORT=8586
OZON_MCP_USER_ID=1
OZON_MCP_ALLOWED_HOSTS=indistinguishably-schorlaceous-serafina.ngrok-free.dev,mcp.ryda.top,127.0.0.1:*,localhost:*,110.42.226.37:*
```

注意：`.env.mcp` 里会有密码，不要提交到 git。

启动容器：

```bash
docker rm -f ozon-mcp || true
docker run -d \
  --name ozon-mcp \
  --restart unless-stopped \
  --env-file /opt/ozon-helper/.env.mcp \
  -p 8586:8586 \
  ozon-mcp:chatgpt-minimal \
  uv run --package ozon-mcp ozon-mcp-chatgpt
```

查看日志：

```bash
docker logs -f --tail=100 ozon-mcp
```

## 6. ngrok 固定域名

服务器安装并登录 ngrok 后，启动：

```bash
ngrok http --url=indistinguishably-schorlaceous-serafina.ngrok-free.dev 8586
```

推荐用 systemd 托管：

```ini
[Unit]
Description=Ozon MCP ngrok tunnel
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/ngrok http --url=indistinguishably-schorlaceous-serafina.ngrok-free.dev 8586 --log=stdout --log-format=json --log-level=info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

保存为：

```text
/etc/systemd/system/ozon-mcp-ngrok.service
```

启用：

```bash
systemctl daemon-reload
systemctl enable --now ozon-mcp-ngrok.service
systemctl status ozon-mcp-ngrok.service
```

## 7. 健康检查

MCP 是 JSON-RPC，不是普通网页。不要只用浏览器打开判断。

本机检查：

```bash
curl -sS http://127.0.0.1:8586/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'
```

公网检查：

```bash
curl -sS https://indistinguishably-schorlaceous-serafina.ngrok-free.dev/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'
```

正常会看到类似：

```json
{
  "serverInfo": {
    "name": "ozon-helper-chatgpt"
  }
}
```

查看工具列表：

```bash
curl -sS https://indistinguishably-schorlaceous-serafina.ngrok-free.dev/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

## 8. ChatGPT 官网怎么填

创建自定义 MCP 应用时：

```text
名称：ozon
描述：Ozon 商品草稿助手。可读取草稿和变体，分析店铺数据与关键词，生成标题、描述、属性、富文本和图片，并保存回草稿；发布前只做检查和预览，不自动发布。
连接：服务器 URL
URL：https://indistinguishably-schorlaceous-serafina.ngrok-free.dev/mcp
身份验证：未授权
```

创建后，在对话里可以这样说：

```text
调用 ozon，列出草稿。
```

或：

```text
调用 ozon，读取草稿 1117，分析商品，选择合适 Ozon 类目，生成俄语标题、描述、属性、图片方案和富文本，只保存草稿，不发布。
```

## 9. 常见问题

### ChatGPT 显示 connection failed

按顺序查：

```bash
docker ps | grep ozon-mcp
docker logs --tail=100 ozon-mcp
systemctl status ozon-mcp-ngrok.service
curl -I https://indistinguishably-schorlaceous-serafina.ngrok-free.dev
```

再用 JSON-RPC curl 检查 `/mcp`。

### ChatGPT 还是显示旧的 43 个工具

通常是 ChatGPT 连接器缓存或连到了旧 URL。

处理：

1. 删除旧 MCP 应用。
2. 用新的 URL 重新创建。
3. 确认 URL 是 `https://indistinguishably-schorlaceous-serafina.ngrok-free.dev/mcp`。
4. 让 ChatGPT 重新“查找可用工具”。

### 加端口报错

ChatGPT 里优先填不带端口的 HTTPS 地址：

```text
https://indistinguishably-schorlaceous-serafina.ngrok-free.dev/mcp
```

如果用自己的域名，推荐用 443 反代到内网 8586，而不是让 ChatGPT 直接连 `:8586` 或 `:8443`。

### DNS rebinding / Host not allowed

把公网域名加入：

```env
OZON_MCP_ALLOWED_HOSTS=你的域名,127.0.0.1:*,localhost:*
```

然后重启容器。

### 图片生成接口不可用

`openai_generate_product_image` 依赖 webui 里的图片 API/OSS 配置。先在 webui 后台确认：

1. OSS 配置可用。
2. 图片 API key/base_url/model 已配置。
3. 草稿图库能正常上传图片。

## 10. 更新部署

代码改完后：

```bash
cd apps/webui/frontend
npm run build
cd ../../..
docker build -t ozon-mcp:chatgpt-minimal .
docker rm -f ozon-mcp || true
docker run -d \
  --name ozon-mcp \
  --restart unless-stopped \
  --env-file /opt/ozon-helper/.env.mcp \
  -p 8586:8586 \
  ozon-mcp:chatgpt-minimal \
  uv run --package ozon-mcp ozon-mcp-chatgpt
```

确认：

```bash
docker logs --tail=100 ozon-mcp
systemctl status ozon-mcp-ngrok.service
```

## 11. 发布安全

ChatGPT 精简版 MCP 不暴露真正发布工具 `publish_draft`。

它可以做：

- 读取草稿和变体
- 商品理解
- 类目/属性
- 标题/描述
- 图片生成并挂回图库
- 富文本
- 发布前检查
- 发布 payload 预览

真正发布仍建议在 webui 里人工确认后执行。
