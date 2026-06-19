---
name: gen-image
description: AI 文生图 / 图生图。默认用 gpt-image-2-2（gptplus5 网关）生成图片，支持纯文字出图(text2img)和带参考图改图(img2img，如做 Ozon 白底主图)。触发：/gen-image、"生成一张图""画一个""把这张图改成白底主图""帮我做产品图""text2img/img2img"等。
---

# gen-image — AI 出图 Skill（gpt-image-2-2）

## 用途

一条命令调用 **gpt-image-2-2**（gptplus5 OpenAI 兼容网关）生成图片：
- **text2img**：给一句提示词凭空出图
- **img2img**：给一张参考图 + 提示词改图（典型场景：把 1688/竞品图改成 Ozon 纯白底电商主图、换场景、出辅助图）

## 数据来源 / 配置

- 脚本：`.claude/skills/gen-image/generate.py`（纯标准库，无第三方依赖）
- 网关：`https://az.gptplus5.com/v1`（`/images/generations` 文生图、`/images/edits` 图生图）
- API key：环境变量 `GPTPLUS5_API_KEY`，或本目录未入库的 `_secret.json`（`{"api_key": "sk-..."}`）；`GPTPLUS5_BASE_URL` 可覆盖网关
- 默认模型：`gpt-image-2-2`（`--model` 可换 `gpt-image-2` 等）

## 执行步骤

### Step 1: 跑脚本

| 意图 | 命令 |
|---|---|
| 文生图 | `python .claude/skills/gen-image/generate.py "提示词"` |
| 图生图 | `python .claude/skills/gen-image/generate.py "提示词" --image 路径.png` |
| 多张 | 加 `--n 3` |
| 指定尺寸 | 加 `--size 1024x1024`（或 1024x1536 竖图 / 1536x1024 横图） |
| 指定输出名 | 加 `--name 主图` |

- Windows 下先 `$env:PYTHONIOENCODING="utf-8"` 再跑，避免控制台中文乱码。
- 脚本把图存到 `.claude/skills/gen-image/output/`，清单（路径 + token 用量）写到 `_last.json`，stdout 打一行 `OK ...` / `ERROR ...`。
- **不要从 stdout 解析数据**（可能乱码）——下一步用 Read 读 `_last.json`。

### Step 2: Read `_last.json`

结构：`mode`(text2img/img2img) / `model` / `prompt` / `images[]`(每张 path+bytes) / `tokens`(input/output/total) / `ts`。

### Step 3: 展示结果

- 用 Read 工具读 `images[].path` 把图显示给用户看。
- 报一句 token 用量（`tokens.total`）。
- 多张时逐张展示，让用户挑。

## Ozon 图片要求（生成时必须满足）

根据 Ozon 图片规范，出图时遵守：

1. **比例 3:4**（竖图）。非 3:4 会被 Ozon「边缘绘制」补边——出图用 `--size 1024x1536`（最接近竖版；要严格 3:4 可后期裁/补边）。
2. **去水印、去标签**：去掉一切水印、贴标、价签、文字、尺寸标注、logo、二维码。
3. **彩色图、少/无信息图**：不要往图上叠文字说明（AI 写俄/中文必糊）。
4. **商品不要占满整张**：居中留边（约四周 10-15% 留白），别顶满画框。
5. **分辨率 ≤ 3100px**（gpt-image 输出 1024~1536，天然满足）。
6. **背景**：纯白底（主图）或干净生成背景（辅图）。

## Ozon 产品图提示词模板（img2img 常用）

主图（白底、留边、去水印去标签、3:4）：

```
Professional e-commerce product photo, 3:4 vertical framing. Pure solid white
background (#FFFFFF), soft even studio lighting, sharp focus, high detail.
Product centered with comfortable margin — it does NOT fill the whole frame
(~12% padding on all sides). Remove ALL watermarks, stickers, price tags, labels,
text, dimension lines, annotations, logos and QR codes. Color image, no infographic
text overlay. No people.
```

辅助图：把背景句换成具体场景（安装实拍 / 细节微距 / 应用场景 / 配件平铺），其余约束（3:4、去水印去标签、留边、彩色无文字）保持不变。

## 注意

- gpt-image-2-2 偶发上游 **429 限速**（"retry after Ns"），脚本已自动退避重试，属正常。
- img2img 是 **AI 重绘**，比例/细节与实物会有出入；要像素级忠实建议本地抠图，AI 图用作辅图/场景图。
- 模型名是网关侧的，若报 `model_not_found` 换 `gpt-image-2`，或先列模型：网关 `/v1/models`。
- 带俄文/中文的「尺寸信息图」AI 写字几乎必糊，别指望 AI 出带准确文字的图——那种在干净底图上用代码叠真字。
- `output/` 和 `_last.json` 是产物，勿提交（已在本目录 `.gitignore` 忽略）。
