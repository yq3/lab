# Unit 5 毕业设计：财务 agent

> 把研究报告的推荐架构做成 Python PoC——用最低成本验证模式，再翻译回 Java。技术栈：langgraph + FastAPI + SQLite + 任一 OpenAI 兼容模型。
> 蓝本：lab 仓 [research/agent-oss/report.md](../../../research/agent-oss/report.md) §4（18 仓解剖出的推荐架构；讲义里以模式编号指代其中的模式，速查表见下节——不必去读研究报告）。

## A 模式速查表（讲义里的编号都在这）

四课讲义用编号指代推荐架构里的模式。**每个编号只需记住一句话**，讲义首次用到时会再提醒：

| 编号 | 一句话 | 主战场 |
|---|---|---|
| A23 | 固定图 + 计划驱动路由：拓扑静态可审计，LLM 只产 Plan JSON（schema 强约束 + 工具白名单） | L5.1 |
| A25 | 条件边循环 + 计数终止：回环可预算，不靠模型自觉 | L5.1 |
| A29 | 失败原因显式状态键：拒绝原因进 state 驱动定向重生成，不是笼统重试 | L5.1 |
| A15 | 审计绑定版本：图形状签名进 checkpoint key，改图自动作废旧执行态 | L5.1/L5.3 |
| A1 | 审批外化 API 组：REST 建单 / 待审总表 / once-always-reject 回复 + SSE 推送，执行挂起等待 | L5.2 |
| A2 | 审批是可重放事件：断线重订阅即重放，无人在线不丢单 | L5.2 |
| A24 | 图上 human 节点回环：interrupt 暂停 + checkpoint 断点续跑（HITL） | L5.2 |
| A6 | 审批与被审内容版本绑定：内容一改即撤销审批（批的是这一版，不是单据号） | L5.2/L5.4 |
| A11 | 事件溯源存储：append-only 事件表，审批/成本/压缩皆一等事件 | L5.3 |
| A13 | 缓存即审计：每个 LLM 决策的输入输出快照按内容寻址落盘 | L5.3 |
| A7 | 执行侧二次校验：执行器收口处独立复核审批状态，与决策层纵深防御 | L5.4 |
| A8 | fail-closed 决策门 + 三态裁决：任何输入不可解析即 DENY | L5.4 |
| A9 | 授权不可达：限额/白名单不是工具、不进注册表，被劫持的 agent 无从发现 | L5.4 |

## 学法说明（先读这段）

- **四课是一棵树的四次生长，不是一个课的四章**：

  ```
              L5.1 静态图 + 计划驱动（地基）
                    │
        ┌───────────┴───────────┐
   L5.2 审批外化 API          L5.3 事件溯源与审计
   （REST+SSE+interrupt，      （SQLite append-only、
     一条并行生长线）            缓存即审计，另一条并行线）
        └───────────┬───────────┘
                    │
              L5.4 执行门 + 结业（汇合：以 L5.3 为底、并入 L5.2 的审批面）
  ```

  L5.2 与 L5.3 **相互独立、都只依赖 L5.1**（先做哪个都行），L5.4 汇合两条线加执行门
  （fail-closed 检查链）收口结业。**每课目录都含截至当课的完整 PoC**（对版纪律：共享件
  从基准课整目录复制再扩展，字节相同的文件保持字节相同；每处差异在 docstring 就地声明）
  ——任何一课毕业，你手里都有一个能跑的完整系统。
- **毕业设计的形状**（注意：这是 L5.4 长完的**终态**，L5.1 开局只有七节点核心图，审批面
  和执行门是四次生长逐步长出来的）：固定拓扑「intake → planner（LLM 产 Plan JSON）→
  plan_gate（校验+白名单）→ executor（确定性步进）→ drafter（LLM 叙述建议单）→
  submit（送审，interrupt 暂停）→ 审批 API（once/always/reject）→ 执行门（fail-closed）→
  终态」。LLM 的动态性只出现在两个节点（规划与叙述），数字全部代码算，审批与执行全部代码门。
- **零 key 底线不变**：mock 端点继续服役。本学段新增 Web 层：FastAPI（Python 的异步 Web 框架，≈ Spring Boot + WebMVC）的验收走 httpx（Unit 2 用过的 HTTP 客户端）进程内直连——不经网络、不起端口，SSE 逐事件断言照做。真实端点（L5.1 的 `--real`）与起真服务（L5.2 Step 5 的 uvicorn）是各自独立的两项可选加餐。
- **Java 桥在这里换挡**：前四个学段用 Java 概念解释 Python，本学段开始反向——每课的
  Java↔Python 对照表把模式的 Java 对应物给全（spring-ai-alibaba graph / langgraph4j 的
  真实 API 名），这些对照在 L5.4 汇总成你亲手填写的 **JAVA-MAPPING.md**：毕业后把 PoC
  翻译回 Java 栈的开发任务拆解输入。这是本教程双目的的兑现点。
- **三条主链路是毕业判据**（里程碑集成测试）：①审批暂停→恢复（interrupt → 工作台批准 → 断点续跑）；②审批拒绝→回环（reject+反馈 → 重新规划/重生成）；③fail-closed 拒绝（超限 proposal → DENY → 审计链留痕）。三条全绿 + JAVA-MAPPING.md = 毕业。

## 课表

| 课 | 主题 | 一句话 |
|---|---|---|
| [L5.1](./L5.1-plan-graph/README.md) | 静态图 + 计划驱动 | 固定拓扑可审计；Plan JSON（Pydantic 强约束 + 工具白名单）驱动确定性执行；失败原因回喂重规划（封顶 2 次） |
| [L5.2](./L5.2-approval-api/README.md) | 审批外化 API 组 | REST 建单 + SSE 推送 + once/always/reject 三元回复；interrupt 挂起 + checkpoint 恢复；断线重放不丢单 |
| [L5.3](./L5.3-event-sourcing/README.md) | 事件溯源与审计 | SQLite append-only 事件表（会话/消息/审批/成本一等事件）；缓存即审计；图版本绑定 |
| [L5.4](./L5.4-execution-gate/README.md) | fail-closed 执行门 + 结业 | 纯函数检查链（审批单二次校验/限额/黑名单/频次），不可解析即 DENY；JAVA-MAPPING.md 收口 |

## 节奏建议（三周，W14–16）

- 第 1 周：L5.1（地基：图、计划、执行器——先把「确定性骨架」立起来）；
- 第 2 周：L5.2 + L5.3（服务化与可观测：审批面 + 事件面，两者正交可并进）；
- 第 3 周：L5.4 + 里程碑（执行门 + 三链路集成 + JAVA-MAPPING.md 定稿）。

每课完成判据与全学段一致：`uv run pytest` / `uv run ruff check .` / `uv run pyright` 三条同时全绿。

## 里程碑（毕业判据）

独立完成 [milestone/](./milestone/README.md)：**可运行 PoC + 三条主链路 pytest 集成测试全绿 + JAVA-MAPPING.md**。里程碑目录是四课共享件的最终汇合点——装配清单由你按毕业自查表勾选，集成测试是你写过的最长的测试（但每一段都该眼熟：它们是四课验收测试的串联）。

## 与前学段的接口

- L3.3 的 checkpoint/interrupt 是 L5.2 审批暂停的直接机制（当时说过「毕业设计审批外化的原型」，本周兑现）；
- L3.8 决策表选定 langgraph（spoiler 早已披露），L5.1 是它的最终用途；
- Unit 4 三块蓝本就位：L4.1 加权合成与 clamp → L5.1/L5.4；L4.2 条件边循环与 REVIEW 哨兵 → L5.1 重规划回环；L4.3 检查链与哈希链 → L5.4/L5.3。

## 离毕业又近的一块

本学段结束，「又近的一块」这句话退役——毕业设计本体就是那最后一块。三十课的明线（一张报销单从 L0.1 的 mock 数据走到 L5.4 的带门付款）与暗线（每课攒下的模式）在这里合流：PoC 三链路全绿的那天，你带走的不是一份课程作业，而是一张经过 18 个开源产品验证、可以按 JAVA-MAPPING.md 直接拆任务的架构蓝图。
