# 多 Agent 开发流程方案（Multi-Agent Development Workflow）

> 本文档是 `lab/.opencode/` 配置的权威设计文档：实现细节 + 设计依据（决策记录）。
> 内容已去掉具体项目属性，适用于任何目标项目；迁移到其他仓库/全局配置时随本目录整体搬迁。

---

## 1. 概述

### 1.1 目标

搭建一套自动化的多 Agent 开发流程：**实现 → 测试 → 审查 →（修复）→ 循环 → 交付**。
用户只下达需求，流程内部分工由 4 个 Agent 协作完成，全程可在 opencode TUI 中观察和打断。

### 1.2 核心原则

| # | 原则 | 来源 |
|---|---|---|
| P1 | 触发可以自动，授权不能自动（push/merge 必经用户确认） | clowder F253 金规 |
| P2 | 没有失败的测试，就没有实现代码（TDD 铁律） | clowder tdd skill |
| P3 | NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE（声称完成必须附命令输出） | clowder quality-gate skill |
| P4 | 禁止表演性同意（对意见逐条响应：已修 / 拒绝+论证） | clowder receive-review skill |
| P5 | 测试全绿是 review 的前置条件（机械验证在前，语义审查在后） | clowder request-review skill |
| P6 | 机械层确定性，判断层留模型（路由/调度是代码逻辑，语义判断交给 LLM） | clowder @提及路由系统 |
| P7 | 通信走会话内直连，检查点文件只存档、只在恢复时读 | 本文档 D3 |

---

## 2. 架构

### 2.1 角色总览

```
用户指令
   │
   ▼
supervisor（编排者，便宜模型）
   │  Task 调用（会话内直连，复用 task_id 保持子会话上下文）
   ├─▶ coder（实现者）：实现 + TDD 自测，只碰业务/测试代码
   ├─▶ tester（验证执行者）：用例文档 → 可执行测试 + 验收勾验
   └─▶ reviewer（审查者）：语义审查，全只读
   │
   ├─ 每轮关键节点 ──写──▶ .opencode/workflows/<task>.md（检查点）
   │
   ▼ 全部通过（双 verdict + 双 SHA = 当前 HEAD）→ 用户确认
   │
   ▼ 交付阶段：coder 推 PR 分支 → reviewer gh pr review → evidence manifest 写 PR description
```

### 2.2 角色职责矩阵

| 角色 | mode | 职责 | 不做 |
|---|---|---|---|
| supervisor | primary | 调度、写检查点、传意见、收敛保护 | 写代码、测试、审查 |
| coder | subagent | 实现需求、TDD 自测、按意见修复 | 改验收用例/设计文档（需 reviewer 审） |
| tester | subagent | 用例文档→可执行测试、跑验证、里程碑勾验 | 改业务代码、改用例文档 |
| reviewer | subagent | 语义审查（逻辑/边界/测试质量/安全）、PR 正式评审 | 改任何代码 |

### 2.3 职责边界的核心设计

借鉴 clowder F253 的三层分离：**tester/reviewer 只产出验证结论，不修改业务代码**。

- tester 拥有 `edit` 权限但限定**测试文件路径**（`**/*.test.*`、`**/*.spec.*`、`test/`、`tests/`）
- reviewer `edit: deny`，只能读 + 只读 git 命令 + `gh pr diff`
- 测试用例文档（如 `TEST-CASES.md`）是**验收依据，等同需求**：tester 发现"用例预期与实际矛盾"时不能自己改，必须报告 supervisor，由 reviewer 裁定是否改用例

---

## 3. 配置布局

### 3.1 文件结构

```
.opencode/
├── README.md               # 本文档
├── agent/
│   ├── supervisor.md       # 编排者（primary）
│   ├── coder.md            # 实现者（subagent）
│   ├── tester.md           # 验证执行者（subagent）
│   └── reviewer.md         # 审查者（subagent）
├── workflows/              # 检查点存档（运行时数据，需 git 忽略策略可选）
│   └── _template.md        # 检查点模板
└── command/
    └── new-task.md         # 任务入口（agent: supervisor）
```

### 3.2 放置位置与加载规则

**opencode 的配置加载规则**：从启动时的 cwd 向上到 git worktree root，只加载该范围内的 `opencode.json` / `.opencode/`。

- 本配置放在 **仓库根**（worktree root），从仓库根启动 opencode 即生效
- ⚠️ 若放在子项目目录（如 `pulse-pet/.opencode/`），从仓库根启动时**不会被扫描到**，必须 `cd` 进子目录启动才生效
- 检查点文件是运行时数据（supervisor 用 bash/edit 读写普通文件），不受加载规则限制，但统一放 `workflows/` 管理

### 3.3 模型分配（可替换，改 agent 文件 frontmatter 的 `model:` 即可）

| 角色 | 模型 | 定位理由 |
|---|---|---|
| supervisor | `deepseek/deepseek-v4-flash` | 只做调度与状态机，便宜快 |
| coder | `opencode/deepseek-v4-pro` | 主力实现，能力强 |
| tester | `deepseek/deepseek-v4-flash` | 跑命令+写测试为主，便宜；质量不足可升级 |
| reviewer | `opencode-go/glm-5.2` | 独立模型族，审慎推理（跨族盲点正交，见 D11） |

> ⚠️ subagent 不显式写 `model` 会**继承调用者的模型**，三个 subagent 必须各自写死。

---

## 4. 工作流详细设计

### 4.1 主流程状态机

```
created ──调 coder──▶ implementing ──coder 返回──▶ testing
testing ──tester FAIL──▶（回 coder）fixing 计数轮次
testing ──tester PASS──▶ reviewing
reviewing ──NEEDS_CHANGES──▶（回 coder）fixing
reviewing ──APPROVED 且双 SHA=HEAD──▶ approved ──用户确认──▶ 交付阶段 ──▶ done
```

### 4.2 每轮迭代顺序（为什么 tester 在 reviewer 前：D5）

```
coder 修复/实现（TDD + 命令证据）
  → tester 验证（机械、便宜、确定性）→ FAIL 直接回 coder（不浪费 reviewer）
  → PASS → reviewer 语义审查（贵、模型推理）
  → NEEDS_CHANGES → 回 coder
  → 修复后 tester 先回归（防 stale）→ reviewer 复看
```

### 4.3 检查点文件（防中断恢复）

**位置**：`.opencode/workflows/<task-id>.md`

```markdown
---
taskId: task-001
target: <目标项目目录>      # 如 pulse-pet/，多项目时区分
status: reviewing           # created→implementing→testing→reviewing→fixing→approved→done
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: NEEDS_CHANGES
testedSha: a1b2c3d
reviewedSha: a1b2c3d        # 修复后置空，待重审
filesChanged: ["src/lib/events.rs", "src/store/usePetStore.ts"]
updatedAt: 2026-08-11T10:30:00+08:00
---

# task-001: 任务标题

## 任务原文
（需求 + 验收标准，写全——这是恢复时唯一的上下文来源）

## 轮次记录
- R1: coder 完成（改动…，自测：cargo test 12/12 通过）
- R1: tester PASS（TC-EV-01~05 通过）
- R1: reviewer NEEDS_CHANGES（P1×1: src/lib/events.rs:42 …）

## 最新验证意见原文
（tester/reviewer 报告逐字保留——恢复时给 coder 的修复依据）
```

**写入时机**（supervisor 每轮节点落盘；tester/reviewer 无写权限，天然由 supervisor 代写）：

| 节点 | status | 写入内容 |
|---|---|---|
| 调 coder 前 | implementing | 任务原文 |
| coder 返回 | testing | 文件清单、自测证据 |
| tester 返回 | reviewing / fixing | testVerdict + testedSha + 报告原文 |
| reviewer 返回 | fixing / approved | reviewVerdict + reviewedSha + 意见原文 |
| 新一轮修复开始 | testing | round+1，reviewedSha 置空 |

**恢复语义**（借鉴 clowder F048：cancel old + replay new）：

| 中断时 status | 恢复动作 |
|---|---|
| implementing | coder 重做该轮（SHA 校验：改了一半的文件回滚） |
| testing | 从 tester 继续 |
| reviewing | 校验 reviewedSha vs HEAD：一致→reviewer 继续；不一致→回 implementing 重做修复轮 |
| fixing | 校验 testedSha vs HEAD：一致→直接从 reviewer 继续；不一致→coder 重做修复 |

**协议铁律**（写入 supervisor prompt）：开工先读、收工必写、状态只能前进、文件是唯一权威。

### 4.4 意见传递协议（D7）

- supervisor 将 tester/reviewer 报告**逐字原文**传给 coder，不做语义汇总、不删减
- coder 对每条意见逐条响应：**已修（附证据）/ 拒绝（附技术论证）**，禁止表演性同意

---

## 5. 质量门禁体系

借鉴 clowder F253 QC Loop 的分层：

```
① coder TDD 自测（L1 机械）→ 附命令输出
② tester 验收执行（L2 机械+模型）→ testVerdict + 失败分类（IMPL_BUG / TEST_BUG / CASE_BUG）
③ reviewer 语义审查（L3 模型）→ 只给 finding 不改码，reviewVerdict
④ evidence manifest（交付阶段）→ 写 PR description（机器可读 JSON）
⑤ stale 保护 → 双 SHA ≠ 当前 HEAD 时 verdict 自动回退，强制重验
⑥ 收敛保护 → 同类问题 ≥3 轮，supervisor 停循环上报用户
```

### 5.1 tester 失败分类协议

| 分类 | 含义 | 处理 |
|---|---|---|
| IMPL_BUG | 实现与用例预期不符 | 报给 coder 修 |
| TEST_BUG | 测试自身错误（mock/断言） | tester 自己修测试重跑 |
| CASE_BUG | 用例预期与实际行为矛盾 | 报告 supervisor，**用例=需求，改动必须经 reviewer 裁定** |

### 5.2 evidence manifest（交付时写入 PR description）

```json
{
  "head": "abc1234",
  "testedSha": "abc1234",
  "reviewedSha": "abc1234",
  "testVerdict": "PASS",
  "reviewVerdict": "APPROVED",
  "gate_commands": ["cargo test", "npx vitest run", "npm run build"],
  "stale": false
}
```

---

## 6. 护栏与收敛保护

| 护栏 | 实现 |
|---|---|
| 最大轮次 | maxRounds=3，超轮强制汇报用户接管 |
| 乒乓检测 | 同一问题往返 ≥2 次 → 停止循环上报用户（clowder F167 简化版） |
| 授权闸门 | supervisor `bash: ask`，push/merge/合入必经用户确认 |
| 权限隔离 | tester 只能写测试路径；reviewer 全只读 |
| gh 环境 | agent prompt 注明 gh 不在默认 PATH，需先 `export PATH=...` |

---

## 7. 使用指南

1. 在仓库根启动 opencode（配置加载前提）
2. Tab 切换到 supervisor，或直接输入 `/new-task 需求描述`
3. 观察 supervisor 的调度与检查点文件实时更新
4. 循环自动进行；push/merge 时 opencode 会弹出确认
5. **中断恢复**：重启 opencode → 重新进入 supervisor → 输入"继续任务 <task-id>" → supervisor 读检查点从断点继续

---

## 8. 设计依据（决策记录）

> 本文档由 2026-08 的多轮讨论沉淀。以下每条对应一个关键决策点及其理由。

### D1. 为什么不用 GitHub Issue/PR 作为 agent 间通信媒介

**结论：被否决。** GitHub Issue/PR 属于"异步强解耦"方案，固有缺陷：

- **协作效率低、延迟高**：每轮交互经过 Git 提交/推送/API 读写/Webhook 回调，单轮延迟比会话内直连高几十倍
- **信息损耗严重、上下文割裂**：Issue/PR 只能传格式化文本，无法携带开发思路/调试过程/中间决策；Reviewer 只看最终 Diff，容易脱离实际约束提意见；评论链过长导致上下文过载
- **状态同步复杂**：需额外维护状态机与 GitHub 状态、Agent 会话状态对齐，易出现"coder 已改但 supervisor 未感知""reviewer 重复审旧版本"等不一致
- **易陷入无效循环**：需求边界不清时 agent 缺乏人类共识能力，在非核心细节上无限迭代
- **成本与限流**：独立会话 token 消耗高，高频 GitHub API 调用触发限流

**替代结论**：GitHub 只做**最终交付与归档**（PR + evidence manifest + gh pr review 留痕），不做通信。

### D2. 为什么选 supervisor 编排 + subagent 分工，而非其他形态

候选方案对比：

| 方案 | 结论 |
|---|---|
| build 自驱动（command + reviewer subagent） | 循环逻辑混在 build 代理里，写代码的同时还要记得调 reviewer，易跑偏 |
| **supervisor 编排 + 3 个 subagent（选定）** | 编排抽成独立角色，职责清晰，各角色模型独立指定，符合 clowder 推荐的多 agent 协作模式 |
| SDK 脚本硬编排 | 可靠性最强但开发成本高、不可观察；适合未来把跑通的流程固化成 CI 脚本，作为演进方向 |

### D3. 为什么通信走会话内直连 + 检查点文件

- **会话内直连**：review 意见零损耗传递，多轮迭代上下文完整，延迟最低
- **检查点文件**：解决"网络不稳定/进程中断"的恢复问题（用户核心担忧）。每轮只写不读，仅在崩溃恢复时读，开销≈0
- 借鉴 clowder F048（restart recovery）：状态必须持久化，通信仍走消息层。**"状态存档"与"通信"是两回事**
- 相比 opencode 自带 session 持久化：session 恢复能拿回对话历史，但 subagent 子会话中间状态会丢、上下文可能被 compaction 洗掉细节；检查点文件是显式的权威状态，恢复不依赖模型记忆

### D4. 为什么设置 tester 角色（对比 clowder 无独立 tester 的设计）

clowder 没有独立 tester：测试是 coder 自己的 TDD 铁律。其反对独立 tester 的核心论据是"测试有效性依赖对实现意图的理解，分离角色引入上下文损耗"。

**本方案保留 tester，理由是**（目标项目特性改变了论据前提）：

- **验收用例文档已存在且结构化**（编号到具体步骤+预期、对应里程碑）——测试意图已固化在文档里，tester 不需要猜 coder 意图，clowder 反对论据被削弱
- **双技术栈**（如 Rust + React/TS）：测试设施要建两套（cargo test + vitest），工程量真实存在，值得独立角色专职承担
- **里程碑验收制**：需要持续的"验收执行者"逐条勾验并输出报告，tester 是天然人选
- **独立验证视角**：避免"验证自己写的东西"的动机偏差；跨模型盲点正交（clowder F253 reviewer delta 理论）

**防走样的约束**（避免 tester 变成 clowder 反对的样子）：
- coder 仍保留 TDD 铁律（自测核心逻辑），tester 管**验收级验证**（跨模块/状态机链路/平台行为）
- tester 不写业务代码、不修改用例文档（用例=需求）

### D5. 为什么 tester 在 reviewer 之前（顺序问题）

如果先 review 再测试：tester 发现测试挂 → coder 修 → **reviewer 的审查作废**（HEAD 变了，F253 叫 stale invalidation），浪费一轮模型推理。

正确顺序：**机械验证（便宜、快、确定性）先挡低级错误，语义审查（贵）只审"能跑的代码"**。修复后同样：tester 先回归，reviewer 再复看。clowder 的 request-review skill 实证："测试全绿是发 review 的前置条件（BLOCKED — 修到绿灯再发）"。

### D6. 为什么分层（三层分离）

借鉴 clowder F253 的 3-Layer Reviewer Split：**L1 确定性工具/机械验证 → L2 审查者只产出 finding → L3 final approver 确认 final HEAD 覆盖全部 finding**。消除"审查者顺手改代码导致审查记录断裂"的问题。

本方案映射：tester（L1 机械验证）→ reviewer（L2 只给 finding）→ 终态双 SHA 校验（L3 等价）。

### D7. 为什么意见逐字传递，不做 supervisor 语义汇总

clowder receive-review 协议：author 对意见逐条响应（已修/拒绝+论证，禁止表演性同意）。语义汇总引入 supervisor 的中间判断层，是新的损耗和分歧源。**supervisor 只做机械传递 + 状态机，判断留给角色**（P6）。

### D8. 为什么授权不能自动

clowder F253 金规："QC 触发可以自动，授权不能自动"。不自动 push、不自动 merge、不自动 bypass 审查。push/merge 是仓库历史不可逆操作，必须经过用户确认（supervisor `bash: ask`）。

### D9. 为什么需要收敛保护

更多验证者 = 更容易卡死。借鉴 clowder：F167 乒乓检测（同一对 agent 反复弹跳注入警告）、F253 触发策略（同类 finding 连续 ≥3 轮退回 plan/spec 层）。本方案：maxRounds=3 + 同问题往返 ≥2 次上报用户。

### D10. 为什么配置先放项目级而非全局

POC 阶段先在单仓库验证效果（模型配合、prompt 质量、检查点协议），效果好再迁移全局 `~/.config/opencode/`。项目级配置与仓库自包含原则一致（每个 App 独立可运行）。

### D11. 为什么 reviewer 选独立模型族

clowder F253 的"盲点正交性"：不同模型族有不同系统性盲点，跨族 review 比同族 fresh-context 多捕获的 finding（reviewer delta metric）更高。故 reviewer 用与 coder 不同族、审慎型的模型（如 glm-5.2），而非同族强模型。

### D12. 从 clowder 借鉴的设计清单

| clowder 机制 | 本方案落点 |
|---|---|
| @提及路由（行首 @handle = 路由指令） | supervisor 用 Task 工具显式调度，subagent 名称即路由目标 |
| 上下文组装（身份 + 队友花名册 + directMessageFrom） | supervisor 每次调用注入：检查点路径 + 需求文档路径 + 上下文包 |
| 乒乓检测 | maxRounds + 同问题 2 次上报 |
| F253 QC Loop 分层 | §5 质量门禁体系 |
| evidence manifest + stale invalidation | 检查点双 SHA 字段 + 终态校验 |
| F048 restart recovery | 检查点文件 + 恢复语义表 |
| receive-review 逐条响应协议 | §4.4 意见传递协议 |
| request-review 五件套（gate 报告/测试输出/需求引用/架构归属/实测证据） | 检查点中的"任务原文 + 自测证据 + 意见原文"，构成 review 的完整上下文包 |
| TDD 铁律 / quality-gate 证据原则 | coder/tester prompt 铁律（P2/P3） |
| 金规：触发可自动、授权不能自动 | supervisor `bash: ask` |

---

## 9. 已知限制与后续演进

### 限制

- **循环可靠性是软约束**：协议依赖模型遵循 prompt（检查点写坏最坏重跑一轮，可接受）
- **模型质量依赖**：tester 用便宜模型写测试，质量不足时需升级模型或由 reviewer 兜底审查测试质量
- **平台验证受限**：本地只能验证当前平台行为（如 macOS），跨平台行为靠 CI/手动
- **检查点文件漂移风险**：文件与代码短暂不一致，靠双 SHA 校验兜底

### 演进方向

1. 效果验证通过后，整体迁移全局配置 `~/.config/opencode/`
2. 用 `@opencode-ai/sdk` 将流程固化为脚本（硬循环 + structured output），支持 CI/无人值守
3. 每轮写检查点时生成 evidence manifest，交付阶段自动组装进 PR description（可脚本化）
