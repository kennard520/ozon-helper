# 项目约定

## 语言
- **始终用中文回复**（所有解释、总结、状态汇报、提问都用中文）。
- 代码、命令、变量名、提交信息按惯例可保留英文/原文；面向用户的说明文字用中文。

## 执行方式
- 实现计划（superpowers writing-plans 产出的 plan）**一律 subagent 驱动执行**（superpowers:subagent-driven-development）：每个任务派 fresh subagent 实现，任务之间由 controller 独立复核（自己重跑回归/构建/失败数基线，必要时起本地后端做浏览器视觉验收），连续跑完不中途打断。
- writing-plans 完成后**不要再问**“Subagent-Driven 还是 Inline”——直接建任务、派第一个、连续推进。
