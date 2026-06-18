# Ozon 商品助手

Ozon 跨境上品助手：采集竞品/1688 → AI 生成俄语卡片 → 智能定价 → 发布到 Ozon → 备货发货。多店、多用户、钱包计费。

## 组成

| 目录 | 说明 |
|---|---|
| `ozon-listing-webui/` | 主程序：FastAPI 后端 + Vue3/Element Plus 前端（后端托管前端 dist） |
| `ozon-seller-helper-ext/` | 浏览器插件（Chromium MV3）：在 Ozon/WB/1688/拼多多页面就地采集，推送到后端 |
| `ozon_api/` | Ozon Seller API 轻客户端（纯标准库），被后端 analytics 调用 |

> 架构：采集走插件、媒体托管走阿里云 OSS、发布走 Ozon 官方 API（Api-Key）。后端**不需要浏览器/Playwright**。

## 本地运行

```bash
# 后端
cd ozon-listing-webui
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# ozon_api 在同级目录，后端自动加进 sys.path
PYTHONPATH=. python run_api.py            # 本机自动选端口，插件自动发现

# 前端（首次/改完前端）
cd frontend && npm install && npm run build

# 测试
python -m unittest discover -s tests       # 后端
cd frontend && npm run test                # 前端
cd ../ozon-seller-helper-ext && npx vitest run   # 插件
```

## 部署到服务器

见 [`ozon-listing-webui/deploy/DEPLOY.md`](ozon-listing-webui/deploy/DEPLOY.md)。要点：
- 设 `WEBUI_HOST=0.0.0.0 WEBUI_PORT=8585`，Caddy/Nginx 反代 + HTTPS，systemd 守护。
- `data/products.db` 含密钥+草稿，务必持久化 + 定时备份。

## 待办（拆分自 kuajing 后）

- **插件连远程后端**：`bridge.js` 目前只连 `127.0.0.1`，部署到服务器后需支持配置后端地址。
- **SaaS 安全**：收陌生付费用户前，需做 Api-Key 静态加密 + 全表 user_id 真隔离。
