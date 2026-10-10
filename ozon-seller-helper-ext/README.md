# Ozon 助手插件（Phase 1.5）

## 本地精简版使用

双击项目根目录 `start-lite.bat`，在 Chrome/Edge 扩展管理页加载本项目的 `ozon-seller-helper-ext` 文件夹（不在 tools 目录）。插件弹窗选择「本地软件」并登录本地账号，首次默认 `admin / admin`。

打开 WB/Ozon 商品页，通过右下角浮层采集；创建草稿后自动打开本机编辑器。WB 图片会转存到 Ozon 卖家媒体库，需同浏览器已登录 `seller.ozon.ru`；插件「重试待上传图片」可触发重试。精简版不需要 OSS 或 AI 服务。

本地连接只探测回环地址，失败不切换远程。切换本地/远程会退出原插件登录；选择远程仍使用原服务器。下方早期 Phase 说明只记录历史，现有 WB/Ozon 采集已实现。

在 **Ozon / 1688 / 拼多多 / Wildberries** 所有页面右下角自动弹出可收起的浮窗。

- **Ozon 商品页**：显示跟卖数 / 被跟最低·最高价 / 卖家链接（同 Phase 1）
- **Ozon 非商品页**：提示「打开商品页查看跟卖」
- **1688 / 拼多多 / Wildberries**：显示「采集进后台（即将上线）」占位按钮（Phase 2 入口，不发网络请求）

浮窗右上角点「收起/展开」可折叠为标题栏。纯前端、零后端、不读 cookie、不连第三方。

## 加载（开发）
1. Chrome/Edge 打开 `chrome://extensions`
2. 右上角开「开发者模式」
3. 「加载已解压的扩展程序」→ 选本目录 `tools/ozon-seller-helper-ext/`
4. 打开任意 `https://www.ozon.ru/`、`https://www.1688.com/`、`https://www.wildberries.ru/` 等页面，右下角出现「Ozon 助手」浮窗
5. 工具栏图标是灰色拼图块，可点 Chrome 右上角 🧩 把「Ozon 助手」固定出来

## 测试
```bash
cd tools/ozon-seller-helper-ext
npm install
npm test
```
