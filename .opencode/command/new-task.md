---
description: 发起一个多 Agent 开发任务（实现→测试→审查→修复循环）
agent: supervisor
model: deepseek/deepseek-v4-flash
---

发起多 Agent 开发任务。目标项目与需求：$ARGUMENTS

按 supervisor 工作流协议执行：创建检查点 → 调 coder 实现 → 调 tester 验证 → 调 reviewer 审查 → 循环直到双通过 → 汇报并询问是否交付。
