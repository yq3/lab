# 用 opencode 搭一套多 Agent 开发工作流：设计与搭建

> 这是系列第一篇，讲这套工作流的**设计与搭建**——架构、机制、决策依据和九轮修订的踩坑史。第二篇《用 opencode 跑完一个完整项目：多 Agent 开发工作流实践与效果》讲它跑起来的真实表现，两个典型案例的完整复盘都在那边。
>
> **相关地址**：实验仓库 [yq3/lab](https://github.com/yq3/lab) ｜ 本套工作流全部配置（agent 定义 + 检查点模板 + 855 行设计文档）：[.opencode/ 目录](https://github.com/yq3/lab/tree/main/.opencode) ｜ 设计文档全文：[.opencode/README.md](https://github.com/yq3/lab/blob/main/.opencode/README.md)

## 0. 我要的是什么

一句话：**我下达需求，流程自己转**。

```
实现 → 测试 → 审查 →（修复）→ 循环 → 交付
```

具体的期望有四条：

1. 全自动流转：四个 Agent 分工协作，我不写代码、不跑测试、不做审查；
2. 全程可观察、可打断：每一步在终端里看得见，随时能介入纠偏；
3. 质量有门禁：没有测试证据不许声称完成，没有审查通过不许交付；
4. 中断可恢复：进程崩了、网络断了，重开后能从断点继续，不依赖模型的记忆。

这套东西最终落在仓库的 `.opencode/` 目录里：4 个 agent 定义文件 + 1 份检查点模板 + 1 份 855 行的设计文档（含 37 条决策记录）。它不是纸上谈兵——用它跑完了一个桌面应用 pulse-pet 的 V1（8 个里程碑、8 个 PR 全部合入），实践中的翻车和返工又反过来改了九轮设计。这篇先讲设计。

## 1. 选型：为什么是 opencode

市面上的"多 Agent 开发"方案不少，我最后选 [opencode](https://opencode.ai) 作为底座，看中的是四个原生能力：

| 能力 | 在工作流里的用途 |
|---|---|
| `mode: primary / subagent` | 一个编排者 + 三个执行者的角色结构，Tab 键切换主 agent |
| Task 工具的 `task_id` 续接 | 同一角色跨轮次复用同一个会话，上下文不丢 |
| 细粒度 permission（bash/edit/task） | 把"谁能干什么"硬约束在配置层，不靠 prompt 自觉 |
| TUI 实时观察 | 每个子会话的推理过程都能进去看，随时 Ctrl+C 打断 |

还有一个隐性优点：opencode 的配置就是放在仓库里的几个 markdown 文件，随仓库迁徙、随 git 版本化，这让它本身可以被"工程化地"迭代——后面九轮修订就是证据。

### 参照系：从 clowder 借了什么

设计前我研究过 [clowder（Cat Cafe）](https://github.com/zts212653/clowder-ai) 的 multi-agent 体系，它的一批机制被直接搬了过来：

| clowder 机制 | 本方案落点 |
|---|---|
| QC Loop 分层（机械验证 → 只给 finding 的审查者 → final approver） | 质量门禁三层 |
| evidence manifest + stale invalidation | 检查点双 SHA 字段 + 终态校验 |
| 乒乓检测 | maxRounds + 同问题往返上报 |
| restart recovery | 检查点文件 + 恢复语义表 |
| receive-review 逐条响应协议 | 意见传递协议 |
| 金规："触发可以自动，授权不能自动" | 权限闸门 |

也有反过来不学的——比如 clowder 没有独立 tester 角色，我保留了（理由见 D4，后文）；比如它要求 reviewer 用 fresh context 防锚定偏差，我刻意续接会话（D26）。照抄和反着来，都得有论证。

## 2. 架构：四个角色

```
用户指令
   │
   ▼
supervised-coding（编排者，便宜模型）
   │  ⓪ 扫历史检查点的遗留事项（未了结的默认并入本任务）
   │  ⓪.5 需求复述 + 验收标准 + 遗留清单 → 用户确认
   │  ⓪.8 调用预告（每次调 subagent 前先请示用户）
   │  ① Task 调用（会话内直连，task_id 续接）
   ├─▶ coder（实现者）：TDD 实现 + 自测，只碰业务/测试代码
   ├─▶ tester（验证执行者）：用例文档 → 可执行测试 + 逐条勾验
   └─▶ committer（审查+把关）：语义审查 + CASE_BUG 裁定 + 终态 PR 评审，全只读
   │
   ├─ 每轮关键节点 ──写──▶ .opencode/workflows/<task>.md（检查点）
   ▼
双 verdict + 双 SHA = HEAD → 用户确认 → 交付（推分支、开 PR、留痕）
```

### 角色职责矩阵

| 角色 | 职责 | 明确不做 |
|---|---|---|
| supervised-coding | 遗留检查、需求确认、调用预告、调度、写检查点、传意见、收敛保护 | 写代码、测试、审查 |
| coder | 实现需求、TDD 自测、按意见修复 | 改验收用例/设计文档、未经确认 push、merge |
| tester | 用例文档→可执行测试、跑验证、里程碑勾验 | 改业务代码、改用例文档 |
| committer | 语义审查、CASE_BUG 裁定、终态 PR 评审 | 改任何代码 |

### 模型分配

| 角色 | 模型 | 理由 |
|---|---|---|
| supervised-coding | deepseek-v4-flash | 只做调度与状态机，便宜快 |
| coder | glm-5.3 | 主力实现，能力强（订阅套餐） |
| tester | deepseek-v4-flash | 跑命令 + 写测试为主 |
| committer | deepseek-v4-pro | **独立模型族**，审慎推理 |

committer 刻意与 coder 不同族，依据是"盲点正交性"：不同模型族有不同的系统性盲点，跨族 review 比同族 fresh-context 能多抓住问题。全部角色 `reasoningEffort: max`（这个字段的踩坑见 §7）。

### 七条核心原则

| # | 原则 |
|---|---|
| P1 | 触发可以自动，授权不能自动（push/merge 必经用户确认） |
| P2 | 没有失败的测试，就没有实现代码（TDD 铁律） |
| P3 | 声称完成必须附命令输出证据 |
| P4 | 禁止表演性同意（对意见逐条响应：已修/拒绝+论证） |
| P5 | 测试全绿是 review 的前置条件（机械验证在前，语义审查在后） |
| P6 | 机械层确定性，判断层留模型（调度/状态机是确定性逻辑，语义判断交给 LLM） |
| P7 | 通信走会话内直连，检查点文件只存档、只在恢复时读 |

P6 是整套设计的美学核心：**能用确定性机制解决的事，绝不交给模型自觉**。状态机、SHA 校验、权限规则都是确定性的；"这段代码对不对"、"这条意见是不是同一个问题"才交给模型。

## 3. 核心机制

### 3.1 主流程状态机

```
spec_confirm ──用户确认──▶ implementing
implementing ──coder 返回──▶ testing
testing ──tester FAIL──▶ fixing（round+1）──回 coder──▶ implementing
testing ──tester PASS──▶ reviewing
reviewing ──NEEDS_CHANGES──▶ fixing（round+1）──回 coder──▶ implementing
reviewing ──NEEDS_CHANGES（需求边界问题）──▶ spec_confirm（回用户，不经 coder）
reviewing ──APPROVED 且双 SHA=HEAD──▶ approved ──用户确认──▶ 交付 ──▶ done
任何状态 ──超轮/乒乓──▶ blocked（上报用户接管）
任何状态 ──用户放弃──▶ cancelled
```

两个容易忽略的细节：

- **fixing 是暂存态**：tester FAIL 或 committer NEEDS_CHANGES 后先置 `fixing` + `round+1` + `reviewedSha` 置空，调用 coder 前再回到 `implementing`。这样检查点在任何时刻落盘，恢复逻辑都无歧义。
- **需求边界问题单独通路**（D27）：committer 发现"验收标准与实现行为矛盾、需求歧义"时，这类问题不是代码 bug，不能发给 coder 硬修——回 `spec_confirm` 复述给用户确认/更新任务原文。实践中这条通路被频繁触发（M2 回 spec 5 处、M4 6 处），是验收口径持续纠偏的关键。

### 3.2 检查点文件：唯一权威状态

每个任务一个 markdown 检查点，放在 `.opencode/workflows/<task-id>.md`，frontmatter 是机器可读的状态：

```yaml
---
taskId: task-pulsepet-m1
target: pulse-pet/
coderTaskId: ses_fff32f83...      # Task 会话 ID（续接用）
testerTaskId: ses_ffd44c59...
committerTaskId: ses_ffd324ab...
status: reviewing                  # spec_confirm→implementing→testing→
                                   # reviewing→fixing→approved→blocked→cancelled→done
round: 2
maxRounds: 3
testVerdict: PASS
reviewVerdict: NEEDS_CHANGES
testedSha: a1b2c3d                 # tester 验证时的 HEAD
reviewedSha: null                  # 修复轮置空，待重审
filesChanged: [...]
endReason: null
createdAt: 2026-08-11T09:00:00+08:00
updatedAt: 2026-08-11T10:30:00+08:00
---

# task-001: 任务标题
## 任务原文        （需求 + 验收标准，写全——恢复时唯一上下文来源）
## 需求确认        （用户确认标记 + 历史遗留事项清单）
## 遗留事项        （跨任务移交，处理完毕回写）
## 轮次记录        （每轮 coder/tester/committer 结果摘要）
## 最新验证意见原文 （tester/committer 报告逐字保留——给 coder 的修复依据）
```

为什么需要它，而不是依赖 opencode 自带的 session 持久化（D3）？session 恢复能拿回对话历史，但 subagent 子会话的中间状态会丢、上下文可能被 compaction 洗掉细节。**"状态存档"和"通信"是两回事**：通信走消息层（会话内直连，零损耗），检查点只是每轮节点落盘的快照，正常流程只写不读，开销约等于零，崩溃恢复时才读。

恢复语义按中断时的 status 分派：`implementing` 中断则 coder 重做该轮（SHA 校验会回滚改了一半的文件）；`fixing` 中断则校验 testedSha vs HEAD，一致就直接从 committer 继续。

**三条铁律**（都是实跑翻车后加的，见 §7）：

1. **字段完整性**：每次写入必须包含模板全部字段，未产生的写 `null`/`[]`，禁止省略——漏写 task_id 意味着子会话无法续接；
2. **事件即写，禁止攒批**：Task 调用返回立即写 xxxTaskId，coder 返回立即写 SHA；
3. **写后必读校验**：写完立即重读逐字段核对，未经校验的写入视为未完成。

外加一条 `updatedAt` 铁律：任何写入（哪怕只改一个 status）都必须先跑 `date` 命令取真实时间更新，禁止凭记忆填。

### 3.3 会话管理：task_id 续接

一项任务内，coder / tester / committer **各自只维持一个 Task 会话**：

- 首次调用后把返回的 task_id 写入检查点；
- 二次调用必须携带 task_id 续接——coder 记得自己的实现思路，tester 记得自己写过的测试，committer 记得自己提过的意见；
- 续接失败（进程重启/compaction）才新开，并告知该角色"从检查点文件恢复上下文"。

注意两层 ID 不要混淆：业务 ID（taskId，1 任务 = 1 检查点文件）和会话 ID（coderTaskId 等，1 角色 = 1 会话）。主会话的恢复走 opencode 自身的 session 管理，不入检查点——这是 D34 删掉一个永远填不上的死字段后才干净下来的。

### 3.4 迭代顺序：tester 为什么在 committer 前（D5）

如果先 review 再测试：tester 发现测试挂 → coder 修 → **committer 的审查作废**（HEAD 变了，stale invalidation），浪费一轮贵的模型推理。

正确顺序：**机械验证（便宜、快、确定性）先挡低级错误，语义审查（贵）只审"能跑的代码"**。修复轮同样：tester 先回归，committer 再复看。

### 3.5 意见传递：逐字原文（D7）

supervised-coding 把 tester/committer 的报告**逐字原文**传给 coder，不做语义汇总、不删减；coder 对每条意见逐条响应：**已修（附证据）/ 拒绝（附技术论证）**。

编排者做语义汇总是新的损耗和分歧源。supervised-coding 只做机械传递 + 状态机，判断留给角色——P6 原则的又一次应用。

### 3.6 失败分类协议

tester 遇到测试失败必须归类：

| 分类 | 含义 | 处理 |
|---|---|---|
| IMPL_BUG | 实现与用例预期不符 | 报给 coder 修 |
| TEST_BUG | 测试自身错误 | tester 自己修测试重跑 |
| CASE_BUG | 用例预期与实际行为矛盾 | 报告编排者，**用例=需求，改动必须经 committer 裁定** |

CASE_BUG 这条很重要：验收用例文档等同需求，tester 和 coder 都不许改——"发现预期不对就顺手改预期"是验收失效的开端。

### 3.7 收敛保护

更多验证者 = 更容易卡死。两条硬限制：

- **maxRounds=3**：超轮 → `blocked`（endReason=max_rounds），上报用户决定继续/放弃/人工接管；
- **乒乓检测**：同一问题往返 ≥2 次 → blocked。这条是启发式（靠编排者对意见主题做语义比对），设计文档里明确标注了可能误判/漏判，POC 阶段观察误判率——实践里它触发过一次，判得没毛病（第二篇的 M1 案例）。

### 3.8 新任务开工：遗留事项清偿（D29）

各检查点彼此独立的话，"P2 清单移交下个里程碑"这类事项只活在旧文件里、靠人记。修订为开工强制清偿检查：

新任务创建检查点前，编排者必须扫描全部历史检查点：status ∉ {done, cancelled} 或"遗留事项"小节有未勾选项的，**默认并入本任务范围处理**（含相应测试用例更新），连同需求一起复述给用户确认。用户明示豁免的记录去向；处理完毕回写原检查点。

这把"技术债"从笔记变成了状态机的一部分。第二篇会展示它跨 8 个里程碑的真实流转链。

## 4. 权限设计

权限是这套工作流里确定性最强的部分。贴实际配置（有删节）：

### supervised-coding（编排者）

```yaml
permission:
  task:
    "*": deny
    "Coder": allow
    "Tester": allow
    "Committer": allow
  bash:
    "*": ask                      # 其余一律请示
    "git status*": allow          # 只放行检查点协议所需的只读命令
    "git log*": allow
    "git diff*": allow
    "git rev-parse*": allow
    "ls*": allow
    "cat*": allow
    "date*": allow                # 时间铁律依赖的取时命令
```

### coder（实现者）

```yaml
permission:
  edit: allow
  bash:
    "*": allow
    "git push*": ask              # 任何推送都弹用户确认
    "git pull*": ask
    "git cherry-pick*": ask
    "git revert*": ask
    "git merge*": deny            # 例外：同步 develop 专用动作精确放行
    "git merge origin/develop*": allow
    "git merge --no-edit origin/develop*": allow
    "git rebase origin/develop*": allow
    "git remote*": deny
    "git reset --hard*": deny
    "git clean*": deny
    "rm -rf*": deny
```

### tester（验证执行者）

```yaml
permission:
  edit:                           # 只能写测试文件
    "*": deny
    "**/tests/**": allow
    "**/test/**": allow
    "**/*.test.*": allow
    "**/*.spec.*": allow
  bash:
    "*": allow                    # 默认放行（D37，见下）
    "git *": deny                 # 任何 git 写操作破坏 SHA 校验协议
    "git status*": allow          # 只读例外
    "git diff*": allow
    "git log*": allow
    "git show*": allow
    "git rev-parse*": allow
    "git fetch*": allow
    "sudo*": deny
    "gh *": deny                  # 交付面工具归 committer/coder
    "rm -rf*": deny               # 仓库/home 内禁递归强删
    "rm -rf /var/folders/*": allow  # 系统临时目录精确放行（测试残留清理）
    "rm -rf /tmp/*": allow
  external_directory:
    "/var/folders/*": allow       # 截图/临时产物
    "/tmp/*": allow
    "~/Library/Application Support/*": allow   # 被测 GUI App 的数据目录
```

### committer（审查者）

```yaml
permission:
  edit: deny                      # 全只读
  bash:
    "*": deny
    "git diff*": allow
    "git status*": allow
    "git log*": allow
    "git show*": allow
    "git rev-parse*": allow
    "gh pr diff*": allow
    "gh pr view*": allow
    "gh pr review*": allow
    "gh pr comment*": allow
```

### 设计哲学的两次转向

这套权限不是一次设计出来的：

**第一次（D15）：从"匹配分支名"到"匹配动作"。** 初版用 `git push origin develop*` 这类前缀匹配拦推送，很快发现字符串前缀可被绕过——`git push`（无参数）、`git push -u origin develop`、`git push origin HEAD:main` 全都不匹配。教训：**授权的语义在动作，不在分支名**，改成 `git push*` → ask。

**第二次（D37）：从"白名单"到"默认放行 + 定向拦截"。** tester 的 bash 初版是白名单（`cargo *`、`npm *` 等命令族），两轮扩容后依然频繁触发授权确认——因为白名单假设"tester = 跑单测"，而 GUI 应用的验收是开放式 E2E 负载：截屏、OCR、CGEvent 驱动、swift 编译临时工具、sqlite 直查、进程管理……静态枚举必然打地鼠。更本质的觉悟是：**`node *` 早已放行 = 任意代码执行，bash 白名单根本不是安全边界，只剩摩擦**。威胁模型是"防误操作、非防对抗"，该模型下的正确形态就是反转：默认放行 + 只拦截不可逆动作（git 写、sudo、仓库内 rm -rf）。

另一个细节：opencode 的权限匹配对象是 shell 命令 AST 节点的完整文本，含 `FOO=bar` 环境变量前缀——`PULSEPET_TICK_MS=2000 npm test` 不匹配 `npm *` 锚定。默认放行后这类摩擦自然消失。

### git 策略（D20 / D30）

- **每轮 coder 完成后本地 commit**（`[<taskId>] R<n>`）：不是仪式感，是让 HEAD 前进、双 SHA 校验真正生效——没有 commit 就没有 stale 检测，恢复时的 SHA 回滚也无从谈起。本地 commit 不发布，不违反 P1；
- **固定开发分支 `develop_opencode`，PR 目标固定 `develop`**：每次 commit 前先 `git fetch` + merge `origin/develop` 同步，保证分支不落后；合并后远端分支保留复用；
- **push 只发生在交付阶段**，且权限是 ask——被指示推送时也弹用户确认。

## 5. 交付链路

用户确认交付后三步走：

1. **coder**：同步 origin/develop → 推 develop_opencode → 开 PR（base=develop）→ 把 evidence manifest JSON 写进 PR description；
2. **committer**：`gh pr review` 把审查结论落在 PR 上留痕；
3. **汇报合入请求，等用户合入**——不自动合入。

evidence manifest 是机器可读的交付凭证：

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

实际写进 PR 的版本更丰富（提交链、TC 逐条结论、knownIssues、specUpdates、reviewers 的 Review ID 等），但核心不变：**双 SHA + 双 verdict + 命令证据**。审查者的终态把关就是核对"manifest 完整且双 SHA 与 HEAD 一致"，不满足不放行。

## 6. 设计决策精选

完整决策记录有 37 条（D1-D37），挑几条有普遍价值的。

**D1：为什么不用 GitHub Issue/PR 当 agent 间通信媒介。** 被否决。异步强解耦方案的固有缺陷：单轮延迟高几十倍；只能传格式化文本，开发思路/调试过程全丢；要维护 agent 状态机与 GitHub 状态的对齐，必然出现"coder 已改但编排者未感知"；高频 API 调用触发限流。结论：GitHub 只做最终交付与归档，不做通信。

**D2：为什么是"编排者 + 3 subagent"而不是别的形态。** build 自驱动（写代码的同时记得调 reviewer）易跑偏；SDK 脚本硬编排可靠性最强但不可观察、开发成本高。编排抽成独立角色是中间态：职责清晰、各角色模型独立指定。SDK 固化是跑通之后的演进方向，不是起点。

**D4：为什么保留 tester（clowder 的反例）。** clowder 认为测试有效性依赖对实现意图的理解，分离角色引入上下文损耗——在它的场景成立。但我的前提不同：**验收用例文档已经存在且结构化**（编号到步骤+预期），测试意图固化在文档里，tester 不需要猜 coder 的意图；双技术栈要建两套测试设施是真实工程量；里程碑验收制需要持续的"验收执行者"；独立验证视角避免"验证自己写的东西"。防走样的约束：coder 仍保留 TDD 铁律（自测核心逻辑），tester 管验收级验证。

**D11：committer 为什么用独立模型族。** 盲点正交性。同族模型有同样的系统性盲点，"自己人查自己人"的增量有限。

**D13：需求确认节点。** 原设计把用户输入直接当需求交给 coder，需求歧义时所有轮次可能耗在错误方向。加一个 `spec_confirm`：编排者先复述"需求 + 验收标准 + 遗留清单"请求确认。代价是每任务多一次交互，换取方向正确性。

**D26：committer 续接会话 vs fresh-context review。** clowder 要求 reviewer 用 fresh context 防锚定偏差（同一会话里 reviewer 会渐进接受反复出现的东西）。我反着来：续接能追踪上轮意见的处置（防漏改）、保持审查标准一致。防锚定的补偿是硬规则：每轮以"HEAD vs 上一轮 reviewedSha"的 diff 为审查对象，先逐条核对上轮意见处置，禁止因"上轮已看过"跳过任何区域。

**D28：调用预告。** 编排自动化跑通后，用户（我）要求收紧观察粒度：每次 Task 调用前先发"调用预告"（角色 + 目的 + 传入要点），同意后才执行。代价是每轮 2-3 次额外交互；收益是每个角色介入前可纠偏，也为人工观察模型行为留出决策点。这是自动化程度和可控性之间的显式权衡——先跑通自动化，再往回收半步。

## 7. 九轮修订：设计是如何被打脸的

设计文档现在是 v10，九轮修订。v1 到 v10 的 diff 本身就是最有价值的部分，挑三段完整的翻车现场。

### 翻车一：`model@max` 的两天三版（D31 → D36）

第一版 agent 配置只写 `model: provider/model`。项目跑完复盘发现：不带 variant 后缀时用的是模型默认推理档，**设计意图是全员满血推理，实际一直在默认档跑**——配置没报错、流程没异常、效果打了折，是最阴的那种偏差。

第一版修复：`model: deepseek/deepseek-v4-flash@max`。切到任一 agent 直接报错 `configured model ... is not valid`。根因：v1.18.18 的 agent model 解析只按 `/` 切分，`@max` 留在模型 id 里，目录查无此模型。

第二版修复：改用独立 `variant: max` 字段 + 项目级配置注册自定义 variants。能跑，但 glm-5.3 被插件排除规则拦截需要额外注册，绕远。

终版：[官方文档 /docs/agents](https://opencode.ai/docs/agents) "Additional" 一节——agent frontmatter 里未列出的字段会作为模型选项直通 provider。直接写 `reasoningEffort: max`（请求体转 `reasoning_effort`），零额外配置，随仓库搬迁即用。用本地 mock 的 OpenAI-compatible 服务抓请求体验证了生效链路。

教训两条：① 控制推理强度首选官方 agent 选项 `reasoningEffort`；② **验证配置是否真的生效，要抓请求体，不要只看配置校验通过**。

### 翻车二：tester 权限的两轮扩容 + 一次反转（D14 → D32 → D37）

初版白名单 → 首跑实测"一轮测试触发十数次权限确认"→ 扩容只读探查命令和 node → M4 实跑依然频繁弹确认，落 ask 的命令全在白名单外（env 前缀命令、E2E 工具链、临时目录写文件）→ 最终承认白名单思路本身错误，反转为默认放行 + 定向拦截（§4 已详述）。

三版演化的共同触发器都是同一个：**实跑反馈**。每一版在纸面上都"够用了"。

### 翻车三：检查点漏写（D33 / D34）

实跑发现编排者漏写 frontmatter 字段（task_id、filesChanged）。后果具体：task_id 丢了 → 子会话无法续接，只能新开重建上下文。于是有了 §3.2 的三条铁律（完整性 / 事件即写 / 写后必读校验），外加放行 `date` 命令消除取时摩擦。同期删掉了 `supervisorSessionId` 死字段——编排者在会话内拿不到自己的会话 ID，三个任务实跑全部为 null，从未起过作用。**死字段不只是冗余，它持续消耗"完整性铁律"的执行预算。**

实践中还追加过一条更细的"追加写入铁律"：edit 工具是替换语义不是插入语义，用既有文本作锚点追加内容时，newString 必须以锚点完整原文开头——否则锚点旧文本被删等于悄悄丢了既有记录。这条是某次检查点内容被覆盖后加的。

### 修订全景

| 轮次 | 主题 | 代表条目 |
|---|---|---|
| 初版 | 架构定形 | D1-D12 |
| 一轮审阅 | 补需求确认、权限、终止流程 | D13-D20 |
| 二轮 | 命名体系（mode 族、name 解耦）、skill 调研 | D21-D25 |
| 三轮 | 护栏加固、回 spec 路径 | D26-D27 |
| 四轮 | 首跑反馈：调用预告、遗留清偿、分支策略 | D28-D30 |
| 五轮/八轮 | 模型推理强度（@max 翻车全程） | D31→D36 |
| 六轮 | 首跑实测：tester 扩容、检查点铁律、删死字段 | D32-D34 |
| 七轮 | 用户直连通道方案 | D35 |
| 九轮 | tester 权限反转 | D37 |

规律很明显：**D28 之后的每一条修订都来自实跑证据**。设计阶段的推演能解决结构问题，摩擦和边角只有跑起来才暴露。

## 8. 已知限制与演进方向

诚实的限制清单：

- **循环可靠性是软约束**：协议靠模型遵循 prompt，检查点写坏的最坏情况是重跑一轮（可接受，但别假装它是硬的）；
- **乒乓检测是启发式**：语义比对可能误判/漏判；
- **Rust 单测边界**：`#[cfg(test)]` 内联在 src/ 里，tester 的 edit 权限写不到，由 coder TDD 自测覆盖；
- **交互成本**：调用预告 + 各处确认，任务耗时随人工响应增加——这是 D28 主动选的，不是意外；
- **用户问询要中继**：过程中用户只能跟编排者对话，问 coder"你为什么这样写"要编排者传话（D35 的直连通道方案已定稿，靠 `opencode run -s <taskId>` 可以手动直连，完整协议待实施）。

演进方向按优先级：

1. **skill 化拆分**：把四个 agent prompt 里的 know-how（TDD 纪律、审查清单、检查点协议）拆成按需加载的 skill，prompt 瘦身为身份 + 路由；
2. **SDK 固化**：跑通的流程用 `@opencode-ai/sdk` 固化为脚本（硬循环 + structured output），支持 CI / 无人值守——D2 里说的"演进方向"，条件正在成熟；
3. 效果验证后整体迁移全局配置，其他仓库复用。

---

这套设计最终长什么样，一句话概括：**一个确定性的骨架（状态机 + 检查点 + 权限矩阵 + SHA 校验）上挂了四个各司其职的模型**。骨架保证流程不会乱，模型只在自己擅长的判断层发力。

至于它跑起来的真实表现——四轮才收口的透明窗口 bug、六轮美术迭代、committer 挖出的同族缺陷、以及全部质量数据——见第二篇。
