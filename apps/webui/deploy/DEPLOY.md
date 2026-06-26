# 部署到服务器（Linux）

后端纯 Python，**不需要浏览器/Playwright/cloakbrowser**（采集走插件、媒体走 OSS、定价走静态表）。

## 0. 前提
- 一台 Linux 服务器（Ubuntu 22.04+，1C2G 够用）。
- 一个域名，A 记录指向服务器 IP（HTTPS + 浏览器插件基本必须域名）。
- 代码里需要 **两个目录一起部署**：`tools/ozon-listing-webui` 和它的同级 `tools/ozon_api`（被 analytics 用）。

## 1. 装系统依赖
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git debian-keyring debian-archive-keyring apt-transport-https curl
# 装 Caddy（自动 HTTPS）
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy.gpg
echo "deb [signed-by=/usr/share/keyrings/caddy.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" | sudo tee /etc/apt/sources.list.d/caddy.list
sudo apt update && sudo apt install -y caddy
```

## 2. 拉代码 + Python 环境
```bash
sudo mkdir -p /opt && cd /opt
git clone <你的仓库地址> kuajing            # 确保含 tools/ozon-listing-webui 与 tools/ozon_api
cd /opt/kuajing/tools/ozon-listing-webui
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 3. 前端构建（dist 不入库）
本地构建后把 `frontend/dist` 传上去，或服务器装 Node 现构建：
```bash
# 服务器现构建（需 Node 18+）
cd frontend && npm ci && npm run build && cd ..
# 或：本地 npm run build 后 scp frontend/dist 到服务器同路径
```

## 4. 起后端（systemd 守护）
```bash
sudo cp deploy/ozon-webui.service /etc/systemd/system/
# 按实际路径改 WorkingDirectory / PYTHONPATH（默认 /opt/kuajing）
sudo systemctl daemon-reload
sudo systemctl enable --now ozon-webui
sudo systemctl status ozon-webui          # 看是否 running
curl -s http://127.0.0.1:8585/api/ext/ping  # 自检
```

## 5. HTTPS 反代
```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile   # 把域名改成你的
sudo systemctl reload caddy
# 浏览器打开 https://app.你的域名.com → 登录(默认 admin/admin，登录后改密)
```

## 6. 初始化数据 / 配置
- 首次启动自动建 `data/products.db`（admin/admin + jwt_secret）。**这库含密钥+草稿，务必持久化+定时备份。**
- OSS 是全局键：在「设置」里配（或直接写 DB `user_id=0`）。
- 在「设置→Ozon 店铺」加店、填 Client-Id/Api-Key。

## 7. 备份（必做）
```bash
# 每天备份 DB
echo '0 3 * * * cp /opt/kuajing/tools/ozon-listing-webui/data/products.db /opt/backup/products-$(date +\%F).db' | crontab -
```

## ⚠️ 还差一步：插件要能连到服务器
插件目前只连 `127.0.0.1`（采集核心流程）。后端搬到服务器后，**插件需要支持配置后端地址**才能从浏览器采集到远程后端。这块是单独的插件改动（`bridge.js`/`background.js`/`popup` 加“后端地址”配置），部署后端本身不依赖它——WebUI 打开即可用，但插件采集要等这步。

## ⚠️ 收别人用之前（SaaS）
- 后端现在**明文存** Ozon Api-Key、且仓库/订单等表尚未按 user_id 强隔离。**自己用 OK，收陌生用户前**必须做密钥加密 + 全表租户隔离（见 spec）。
