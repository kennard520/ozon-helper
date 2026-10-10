# Ozon 助手插件（Phase 1.5）

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
