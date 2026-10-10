---
description: 用 gpt-image-2-2 生成图片（文生图 / 图生图）。例：/gen-image 一只戴帽子的柴犬
---

调用 `gen-image` skill 出图。把 `$ARGUMENTS` 当作生成提示词。

- 用户只给文字 → text2img：`python .claude/skills/gen-image/generate.py "$ARGUMENTS"`
- 用户给了参考图路径，或要求"改这张图/做成白底主图" → img2img：加 `--image <路径>`
- 跑完用 Read 读 `.claude/skills/gen-image/_last.json`，再 Read 图片路径展示给用户，并报 token 用量。

详细规则见 `.claude/skills/gen-image/SKILL.md`。
