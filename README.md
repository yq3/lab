# lab

Personal laboratory for experimental code and PoCs. No guarantees, all ideas welcome.

个人实验室：多个实验性 App / POC 的汇聚仓库。每个项目在根目录下独立成目录，自包含、可独立运行。

## Projects

### [todo-lite](./todo-lite)

轻量级桌面端 To Do List 管理 App（Tauri 2 + React + SQLite），纯本地存储无云同步。
详情见 [todo-lite/README.md](./todo-lite/README.md)。

### [pulse-pet](./pulse-pet)

桌面宠物 App，监听 coding agent（opencode / Claude Code）工作状态并以像素小猫动画呈现，
附带 token 消耗统计、喝水/休息提醒、轻量 todo 插件。使用手册与 v1/v2 演进详见
[pulse-pet/README.md](./pulse-pet/README.md)。

### [research](./research)

调研专区：agent 相关开源项目的调研过程与结论，每轮任务一个子目录。
工作规范与历史调研索引见 [research/AGENTS.md](./research/AGENTS.md)。

### [py-night-school](./py-night-school)

Python 夜校教程：写给 Java 工程师的 Python Agent 开发晚课。以 agent 开发为场景学 Python、
以 Java 心智模型为桥，30 课时全部练习 pytest 自动验收，克隆即学、模型端点中立。

> **已拆仓独立演进**（2026-09-19）：新仓地址 [yq3/py-night-school](https://github.com/yq3/py-night-school)
> （public、MIT、完整提交历史随迁）。本目录为拆仓时的过渡副本，定格于 lab 提交 `0a228cd`；
> 后续维护一律在新仓进行。

### [knowledge-lattice](./knowledge-lattice)

企业知识层服务（POC，需求/设计 v0.8，冻结纪律延续）：**文档知识**（维度 ACL 权限内的混合检索）
与**业务语义**（术语识别 + 业务对象类型化关系图）同服务归一，单进程 + 存储后端双实现（SQLite 默认
零中间件 / PostgreSQL+pgvector 可选——D24）、嵌入与重排经 OpenAI 兼容 API（D12 修订），经单一
MCP server 给 agent 供数，含 v0.5 交互原型与验收用例集（TEST-CASES v1.4，172 条）。
详见 [knowledge-lattice/README.md](./knowledge-lattice/README.md)。
