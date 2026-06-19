---
description: 把图片上传到阿里云 OSS 拿公网直链（复用 webui 已配的 OSS 凭证）。例：/oss-upload output/主图_0.png
---

调用 `oss-upload` skill。把 `$ARGUMENTS` 当作要上传的文件路径 / URL / 通配。

- 本地文件或 URL：`python .claude/skills/oss-upload/upload.py $ARGUMENTS`
- 传 gen-image 刚出的图：`python .claude/skills/oss-upload/upload.py --from-genimage`
- 跑完用 Read 读 `.claude/skills/oss-upload/_last.json`，把每个 `input → url` 公网直链报给用户。

详细规则见 `.claude/skills/oss-upload/SKILL.md`。
