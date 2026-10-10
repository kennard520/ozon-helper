---
name: gen-image
description: "通过 OpenAI 兼容中转站调用 ChatGPT Image / GPT Image，支持创建、参考图修改、蒙版局部修改，面向 Ozon 商品图。"
version: 1.2.0
author: User
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [image, generation, edit, mask, gpt-image, ecommerce, ozon, product-photo]
    related_skills: [comfyui, photoshop, canva, figma]
---

# gen-image — Ozon 商品图出图 Skill

## 目标

用一条命令通过 **OpenAI 兼容中转站** 调用 ChatGPT Image / GPT Image，生成或编辑商品图。

这个 Skill 不只区分“文生图 / 图生图”，而是按商品图工作流分成三类：

| 工作方式 | 脚本 mode | 接口 | 什么时候用 |
|---|---|---|---|
| 创建 | `create` | `/images/generations` | 没有原图，生成场景图、氛围图、概念图 |
| 修改 | `edit` | `/images/edits` | 有产品图，要保持产品参考，整体生成新场景/新构图 |
| 蒙版 | `mask` | `/images/edits` + `mask` | 只改局部，例如换背景、去 logo、修局部、补安装环境 |

## 核心判断规则

做商品图时优先按这个判断：

1. **没有图，只要场景/氛围** → 用 `create`。
2. **有真实产品图，希望商品像实物** → 用 `edit --image 产品图`。
3. **只改一块，产品本体不能动** → 用 `mask --image 原图 --mask 蒙版图`。
4. **主图、细节图、配件图、尺寸图底图** → 优先 `edit` 或 `mask`，不要纯 `create`。
5. **安装图、使用场景图、氛围图** → 可以 `create`，但产品必须一致时仍用 `edit --image`。
6. **俄文、尺寸数字、参数表** → 不建议让 AI 直接写在图里；先出干净底图，再用 Canva / PS / Figma / 前端模板加字。


## Ozon 图片硬性要求（默认必须遵守）

生成 Ozon 商品图时，默认按以下规则执行：

| 项目 | 要求 |
|---|---|
| 文件格式 | JPEG / JPG / PNG / HEIC / WEBP |
| 图片大小 | 单张不超过 10MB |
| 分辨率 | 长边 200–7680 像素 |
| 宽高比 | 优先 3:4；本 Skill 默认 `--size 1024x1536` |
| 主图背景 | 白色或浅色背景；白色/透明商品可用黑色背景 |
| 服装/鞋/配饰背景 | 使用浅灰色 `#f2f3f5` |
| 主图留边 | 产品居中，四周保留安全边距，避免被平台徽章遮挡 |
| 禁止信息 | 不要价格、折扣、联系方式、链接、二维码、购买引导、电话、微信、网址 |
| 禁止画面 | 不要酒精饮料、黑白照片、模糊低质图、生活杂乱背景 |
| 文字策略 | 主图尽量无文字；详情图可后期加俄文，但不要让 AI 直接生成复杂俄文/数字 |

### Ozon 主图安全区

主图要避免商品主体、尺寸数字、卖点图标、重要细节靠近边缘。默认提示词里应加入：

```text
3:4 vertical Ozon product card, product centered, about 12% safe margin on all sides,
important details not close to the corners or edges, no text overlay, no price,
no discount, no contact information, no QR code, no watermark.
```

### 生成后必须检查

1. 是否为 3:4 竖图。
2. 是否为白色/浅色干净背景，或者符合类目背景要求。
3. 主图是否无价格、折扣、联系方式、二维码、购买引导。
4. 产品有没有被裁切，重要细节有没有靠边。
5. 产品主体有没有变形，螺丝孔、线材、接口、配件有没有乱画。
6. 如果有俄文/数字，是否清晰准确；不准就删除，后期排版。


## 安装位置

推荐目录：

```text
.claude/skills/gen-image/
  generate.py
  SKILL.md
  _last.json        # 运行后自动生成，不提交
```

## 环境变量

不要把 API key 写进脚本。请设置环境变量。

### Windows PowerShell

```powershell
setx GPTPLUS5_API_KEY "你的中转站key"
setx GPTPLUS5_BASE_URL "https://az.gptplus5.com/v1"
setx GPTPLUS5_IMAGE_MODEL "gpt-image-1.5"
setx GPTPLUS5_IMAGE_FIELD "image"
```

当前窗口临时生效：

```powershell
$env:GPTPLUS5_API_KEY="你的中转站key"
$env:GPTPLUS5_BASE_URL="https://az.gptplus5.com/v1"
$env:PYTHONIOENCODING="utf-8"
```

### Linux / macOS

```bash
export GPTPLUS5_API_KEY="你的中转站key"
export GPTPLUS5_BASE_URL="https://az.gptplus5.com/v1"
export GPTPLUS5_IMAGE_MODEL="gpt-image-1.5"
export GPTPLUS5_IMAGE_FIELD="image"
```

## 脚本参数

| 参数 | 说明 |
|---|---|
| `prompt` | 生成/修改提示词 |
| `--mode auto/create/edit/mask` | 默认 `auto`，根据是否传 `--image` 和 `--mask` 自动判断 |
| `--image 路径` | 参考图/原图，可重复传多张 |
| `--mask 路径` | 蒙版 PNG，给了就走局部修改 |
| `--image-field image[]` | multipart 图片字段名；官方兼容一般用 `image[]`，部分中转站可改 `image` |
| `--size 1024x1536` | 默认 3:4 竖图，适合 Ozon 商品卡 |
| `--quality low/medium/high/auto` | 画质；批量草图用 low/medium，最终图用 high |
| `--format png/jpeg/webp` | 输出格式；不传默认保存 png |
| `--background transparent/opaque/auto` | 网关支持时生效 |
| `--compression 0-100` | JPEG/WebP 压缩，网关支持时生效 |
| `--n 3` | 一次生成多张 |
| `--out 目录` | 输出目录，默认 `~/Downloads/gen-image/YYYY-MM-DD/` |
| `--name 文件名前缀` | 输出文件名前缀 |
| `--manifest 路径` | `_last.json` 输出路径 |
| `--list-models` | 列出中转站模型 |
| `--dry-run` | 只检查参数，不调用接口 |

## 常用命令

### 1. 创建：无参考图，生成场景/氛围

```bash
python .claude/skills/gen-image/generate.py \
  "Photorealistic Ozon ecommerce image, an electromagnetic lock installed on a transparent glass door in a modern office entrance, clean light background, realistic shadows, no text, no logo, no watermark." \
  --mode create --size 1024x1536 --quality high --n 3 --name 磁力锁_玻璃门场景
```

适合：场景图、氛围图、抽象功能图。  
不适合：要求商品必须和实物完全一致的主图。

### 2. 修改：上传真实产品图，生成安装场景

```bash
python .claude/skills/gen-image/generate.py \
  "Use the uploaded electromagnetic lock as the exact product reference. Create a photorealistic Ozon product card image: the same lock installed on a transparent glass door in a modern office entrance. Keep the lock body shape, screw holes, color, proportions, wiring outlet, bracket structure and metal texture consistent with the reference. No text, no logo, no watermark." \
  --mode edit --image ./磁力锁.png --size 1024x1536 --quality high --n 3 --name 磁力锁_参考图安装
```

适合：你的产品必须尽量像实物时使用。

如果中转站不接受 `image[]` 字段，改成：

```bash
--image-field image[]
```

也可以传多张参考图：

```bash
--image ./正面.png --image ./侧面.png --image ./细节.png
```

### 3. 蒙版：只换背景，产品不动

```bash
python .claude/skills/gen-image/generate.py \
  "Replace only the masked area with a clean modern glass door installation scene. Keep the unmasked electromagnetic lock completely unchanged. Realistic lighting, natural shadows, ecommerce product photo style, no text, no logo." \
  --mode mask --image ./原图.png --mask ./背景蒙版.png --size 1024x1536 --quality high --name 磁力锁_局部换背景
```

适合：去 logo、去中文、只换背景、修局部、补阴影、补安装环境。

## 蒙版要求

最稳规则：

- 原图和 mask 都用 **PNG**。
- 原图和 mask 必须 **同尺寸**。
- mask 必须带 **alpha 通道**。
- 不想改的地方保持不透明/透明的规则取决于中转站实现；实测后固定一种规则写进团队 SOP。
- 选区要比目标区域稍微大一点，但不要覆盖产品关键结构。

脚本会默认检查：PNG、尺寸一致、mask 是否有 alpha。如果你的中转站规则特殊，可以临时加：

```bash
--no-strict-mask
```

## Ozon 十张图推荐调用方式

| 序号 | 图类型 | 推荐 mode | 备注 |
|---|---|---|---|
| 1 | 白底主图 | `edit` / `mask` | 用真实产品图，不要纯创建 |
| 2 | 多角度展示 | `edit` | 保持产品一致 |
| 3 | 细节放大 | `edit` / `mask` | 螺丝孔、接口、线材不能乱画 |
| 4 | 尺寸参数图底图 | `edit` | 数字和俄文后期加 |
| 5 | 配件/套装清单 | `edit` / 拼版 | 不要 AI 乱编配件 |
| 6 | 安装图 | `edit` 优先 | 没有产品要求时才 `create` |
| 7 | 使用场景图 | `create` / `edit` | 产品要一致就传参考图 |
| 8 | 功能演示图 | `create` / `edit` | 防水、承重、吸力等 |
| 9 | 对比卖点图 | `edit` + 设计排版 | 信息后期加更稳 |
| 10 | 总结营销图 | `create` + 设计排版 | 适合做氛围和适用范围 |

## 提示词模板

### 白底主图

```text
Professional e-commerce product photo for Ozon marketplace, 3:4 vertical format.
Pure solid white background (#FFFFFF), soft even studio lighting, sharp focus,
high detail. Product centered with comfortable margin, about 12% padding on all
sides. Keep the real product shape, color, screw holes, joints, ports and material
texture unchanged. No text, no logo, no watermark, no QR code, no price, no discount,
no call-to-action, no people.
```

### 参考图安装场景

```text
Use the uploaded product as the exact product reference. Create a photorealistic
Ozon ecommerce scene showing the same product installed in [scene]. Keep the product
body shape, color, proportions, screw holes, cable outlet, brackets, material texture
and visible details consistent with the reference. Clean commercial lighting,
realistic shadows, 3:4 vertical composition. No text, no logo, no watermark, no people.
```

### 蒙版局部修改

```text
Replace only the masked area with [new background/object/effect]. Keep every unmasked
part completely unchanged, especially the product shape, color, edges, holes, cables,
logos already outside the mask, and material texture. Match lighting and shadow
naturally. No added text, no watermark, no extra objects.
```

## 结果读取

脚本会输出：

- 图片：默认保存到 `~/Downloads/gen-image/YYYY-MM-DD/`
- 清单：`_last.json`

`_last.json` 结构：

```json
{
  "ok": true,
  "mode": "edit",
  "model": "gpt-image-1.5",
  "images": [{"path": "...", "bytes": 123456}],
  "tokens": {"input": 0, "output": 0, "total": 0},
  "ts": "2026-06-20 15:12:53"
}
```

不要从 stdout 解析路径，优先读 `_last.json`。

## 质量控制

生成后必须检查：

- 产品主体有没有变形。
- 螺丝孔、线材、接口、安装支架是否乱画。
- 是否出现品牌、二维码、中文、价格、折扣、联系方式。
- 俄文/数字是否糊；如果糊，删除后用后期排版。
- Ozon 主图是否保持浅色/白色背景、3:4、无促销文字。

## 常见问题

### 1. `model_not_found`

先查模型：

```bash
python .claude/skills/gen-image/generate.py --list-models
```

或者改模型：

```bash
--model gpt-image-2
```

### 2. 429 / 5xx

脚本已经对 429 和 5xx 做退避重试。批量生成时建议减少 `--n` 或降低 `--quality`。

### 3. 中转站不识别图片字段

默认字段按你的中转站 curl 示例使用 `image`。如果某些兼容网关要求官方写法，再试：

```bash
--image-field image[]
```

### 4. 蒙版报错

确认：原图 PNG、mask PNG、尺寸一致、mask 带 alpha。必要时先用 PS/Canva/Figma 重新导出。

## 安全注意

- 不要把 API key 写进 `generate.py`。
- 不要把 `_last.json`、输出图、真实商品原图提交到公开仓库。
- 失败日志不要打印完整请求头或 key。
