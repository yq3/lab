# PulsePet v2 范围决策记录

> 记录日期：2026-08-20
> 来源：基于 v1 收官（M8 + v0.1.0/v0.1.2 发版）后的实际使用反馈与本轮范围讨论
> 性质：v2 的范围边界与分阶段计划，作为后续 v2 方案设计与实施的输入
> 关联：[DECISIONS.md](../v1/DECISIONS.md)（v1 范围）、[V1-OPEN-ITEMS.md](../v1/V1-OPEN-ITEMS.md)（v1 遗留清单）

---

## 1. 定位

- **个人工具深耕**：v2 服务于作者自己的日常使用（opencode + Claude Code 双 agent、多 session 多开），不做开源产品化运营（排行榜 / 插件市场 / 自动更新等均不在内）。
- **暂不拆仓**：继续在 lab/pulse-pet 下演进，拆仓时机后续再议。
- **前置**：先发 **v0.1.3 维护版**清偿 v1 遗留，再进入 v2 主体（§3）。分两段的原因：遗留 7 条均为日常使用正在忍受的痛点，早发早受益；其中 3 条改插件（`pulse-pet-hook.js`），插件与 App 需配套发布（改完需重跑 `install.sh`）。

---

## 2. v0.1.3 维护版（先行，~1 周）

> **（2026-08-22 移出）** 本节范围与计划已移至 [V1-OPEN-ITEMS.md §八](../v1/V1-OPEN-ITEMS.md)——v0.1.3 属 **0.1.x 发版线维护收尾**（清偿 v1 遗留），与 v2 开发并行，归入 v1 文档目录更合身份；本文件自 §3 起为 v2 主体，章节编号保持不变。

---

## 3. v2 主体（~6-8 周，六个里程碑）

### 3.1 M1：Claude Code 事件接入（~1.5 周）

- **接入方式：hooks 安装式**（与 opencode 插件同模式）：hook 脚本 POST 同一本地 HTTP server（读同一套 endpoint/token 文件）；安装器写 `~/.claude/settings.json`，幂等 + managed 标记 + 卸载不误删用户原有 hooks（照抄 opencode-plugin install 脚本模式）。
- **事件归一化**（与 opencode 插件同粒度）：`UserPromptSubmit`→thinking、`PreToolUse(Edit/Write)`→editing、`PreToolUse(bash+test)`→testing、**`PermissionRequest`→waiting-permission（单向展示，保留）**、`Stop`/`StopFailure`→idle/error。
- **AgentAdapter 第二实现**（`ClaudeCodeAdapter`）；session key 从 `sessionId` 升级为 `(agent, sessionId)` 复合键（现 `/state` 协议已要求 `agent` 字段、Rust 侧按 sessionId 维护状态机，此为 v1 预留的兑现）。
- **单向 waiting-permission 语义**：宠物切 review 姿态提醒用户去看终端；用户在终端审批后经状态事件自动跟随更新。不做气泡内代答（见 §4）。
- **接入管理**（源自 petdex v1.0.0，2026-08-21 裁定）：设置页加「接入管理」区——opencode 插件 / Claude Code hooks 各显示 已安装/未安装/版本 状态，一键安装/卸载 + doctor 健康检查；替代用户手跑终端脚本。安装逻辑复用既有脚本模式，JSONC 感知合并的 Rust 侧实现路径设计阶段定（M1 随 CC 安装器一并落地）。

### 3.2 M2：前端 UI 基础（~1-1.5 周）

- **背景**：v1 前端 UI（控制面板、宠物气泡等）朴素难看（用户 2026-08-20 评定；宠物精灵素材本身不在范围）。借助 opencode skill **frontend-design** / **impeccable** 辅助设计与实施。
- **范围**（本里程碑只做"壳"——设计系统与基础设施，功能增强拆入 M3，2026-08-21 用户裁定拆分）：
  - 控制面板整体：窗口视觉、导航、四个 tab（Token / 提醒 / Todo / 设置）统一设计语言；
  - 宠物气泡组件重构（提醒 / 会话汇报 / todo 派生文案各类形态）与宠物右键菜单；
  - **气泡并发/排队模型**（源自 petdex 邮箱模型，2026-08-21 裁定）：v1 气波单槽位；M3/M4 起气泡来源增多（工具播报/提醒/会话汇报/今日累计），须定优先级 + dwell 合并 + 并发上限——作为气泡组件重构的设计需求一并设计；
  - **tab 注册表 + feature flag**：核心 tab + 模块注册表驱动渲染（替代 Panel.tsx 硬编码 TABS 数组）；设置页加「功能管理」开关，消费 plugins 表**已有的** `enabled` 列——v1 插件外壳（manifest/panelTab）从装饰品变成真注册表，「不想要 todo 的用户可以关掉」从口号变成事实。禁用语义（隐藏 tab + 停派生提醒 + 数据保留）设计阶段定；
  - 导航按「最坏 6 个 tab」设计（分组 / 次级菜单 / 侧栏），为功能增长预留信息架构空间；
  - **不含**：宠物素材与动画、烟花粒子引擎（已按"动漫流光"验收，调整留彩蛋池）、托盘菜单（原生，样式受限）。
- **流程**：开工前先由 skill 辅助产出设计方向稿（设计语言 / 色板 / 字体 / 组件规范，与像素宠物的风格协调），用户拍板后实施。
- **约束**：zh/en 双语与字典键完备性测试保持；现有纯函数测试（bubble 文案 / token-chart 等）不破坏；提醒 tab 在 M2 只做轻量翻新（落新设计系统），完整表单重做并入 M4 的「定时任务」合并 tab，避免双重返工。
- **排序理由**：置于功能扩展类里程碑之前——面板与气泡在 M3~M6 均有改动，先立设计系统可让新功能直接落在新设计上，避免旧样式上开发再重绘的返工。

### 3.3 M3：Token 看板增强 + 工具级气泡（~1-1.5 周）

落 M2 新设计系统上的功能增强（2026-08-21 需求与裁定）：

- **A. 数据层**：`TokenRow` 扩展——`model_id`（`json_extract(model,'$.id')`；**仅按模型 id 归并**，variant/provider 折叠，如 glm-5.3 的 max/default 并为一项，对齐 GLM 平台心智；实测 session.model 为 JSON `{id, providerID, variant}`，近 30 天 15 种组合）、`project_name`（JOIN `project` 表哈希→路径取 basename 如 `lab`；`global`/无映射回退标签——修复现状展示哈希不可读的问题）、`title`（会话标题，opencode 自动摘要生成、质量良好，偶回退 `New session - 时间戳`）；`SESSION_REQUIRED_COLUMNS` 白名单同步补充；新命令 `token_stats_today` → `{input, output, cache_read, cost} | 错误码`（包 range 聚合求和，复用 no-database 等全套错误处理）。
- **B. 今日 preset**：`RangePreset` 加 `"today"`（from = 本地今天 0 点）；**面板默认选中今日**（原默认 7d）。
- **C. 三层快捷查看今日 token**（共享 `token_stats_today`）：① 被动层——会话结束气泡「本期用了 Xk…」末尾追加「今日累计 T」（零操作触达）；② 主动层——悬停宠物 ~500ms → 气泡显示今日汇总（总量 + in/out/cacheRead 三行），移开即消；③ 入口层——右键菜单「今日 token：X」信息项（数据未到 `…`、无库 `—`），点击 → 打开面板 Token tab（默认即今日，无缝衔接详情）。已知限制：穿透模式下悬停/右键不可达（仅被动层 + 面板可用）；左键单击行为不改（用户保留）；托盘 tooltip 不做。
- **D. 堆叠柱状图**：柱内三段自底向上 **output → input → cache read**（DeepSeek/GLM 平台式）；自定义 HTML tooltip（悬浮显示日期 + 三项数值 + 占比 + 总量）+ 图例；`computeStackedBars` 纯函数 + 单测；KPI 加首卡「总量」= in + out + cacheRead；**reasoning 不计入任何汇总口径**（用户裁定，与 GLM 官方展示同口径；注：数据层 tokens_reasoning 独立存在且 82% 会话非零，v1 会话详情已露出，v2 不改）。
- **E. 模型筛选**：柱状图上方罗列模型 ID 复选框列表（默认全勾），取消勾选即从柱图剔除（GLM 平台式）；**筛选作用域仅柱状图**——KPI 卡 / 会话列表不受勾选影响，口径各自独立。
- **F. 砍项目饼图**（用户裁定）：删 `ProjectPie` 组件 + `token-columns` 双栏布局（依据：实际分布高度集中——近 30 天 lab 项目占 ~97%，饼图信息量趋零；cost 大多为 0），空间让给模型筛选区与更宽的柱图/会话列表；项目维度本身保留（经 A 的映射修复后在会话列表体现）。
- **G. 会话列表改造**（用户裁定）：首列由截断 session id 换成**会话标题**（过长省略，完整标题 + session id 悬停 tooltip）；项目列显示可读项目名（basename）替代哈希；展开详情追加「模型」行；回退：无标题按原样显示、未知项目显示回退标签。
- **H. 工具级气泡文案**（源自 petdex，2026-08-21 裁定做 + 用户开关，**默认开**）：插件在投递 editing/testing/working 等事件时经 `/state` 既有 `detail` 字段（v1 未用）携带白名单模板文案——「正在编辑 V2-SCOPE.md」「正在跑 npm test」「访问 maven.aliyun.com」等；只允许模板 + 文件 basename / 命令首词，不带路径与参数原文（TC-SEC 净化口径）；speech 桶 20s 节流防刷屏；宠物从"状态灯"升级为"播报员"。设置页开关 + `app_state` 持久化；开关实现层倾向 App 侧过滤（插件照发，App 按开关忽略，不动插件）——设计阶段定。Token 页重构时**预留 agent 筛选位**（数据维度 M5 接入，避免二次返工）。

### 3.4 M4：定时任务（动作泛化，~1-1.5 周）

- **需求**：宠物定时周期性替用户做事（如每天早上 9 点评审仓库 open PR——提前写好命令，由宠物调用 opencode 执行）。底层能力抽象为**到点 → 执行动作 → 收集结果 → 汇报**，命令执行是 v2 落地的第一种动作类型。
- **三功能定位**（提醒 / 定时任务 / Todo，谁发起 × 谁做事 × 完成语义）：

| 功能 | 一句话定位 | 调度 | 动作 | 完成语义 |
|---|---|---|---|---|
| 提醒 | 宠物定期**提醒你**做事（喝水/休息） | 周期 interval | 气泡/烟花 | 无（触发即记账） |
| 定时任务 | 宠物定期**替你**做事（9 点评审 PR） | 定点（每天/每周 HH:mm）+ 仅一次 | spawn 命令执行 + 汇报 | 有（成功/失败/跳过记录） |
| Todo | 你**手动**管理的一次性任务清单 | 无（仅派生一次性提醒） | 气泡/烟花 | 有（勾选完成/庆祝） |

三者共享调度器、气泡/烟花、暂停开关、历史日志基础设施。与「对话入口不做」（§4）的区别：定时任务是后台 spawn 无对话 UI，非裁定反复。
- **数据模型**：扩展 `reminders` 表（迁移 003）——`action_type`（'notify' 默认 / 'exec'，未来类型只加枚举值不动表结构）+ `action_params`（JSON 载荷，exec = `{command, cwd?, timeout?}`）+ `schedule_kind`（'interval' / 'daily-at' / 'weekly-at' / 'once'）。不设 `command` 专列。**once + 定点语义顺手补齐**"明晚 9 点提醒我开会"类一次性定时需求（v1 只能 hack 成 todo）。保住「调度器单一数据源」定案（DESIGN §8.3）。
- **动作泛化**：Rust 侧 ActionExecutor 分派——`validate(params)`（表单保存时校验）+ `run(params) -> ActionOutcome{status: ok|failed|skipped, summary, output_tail?}`，统一喂养结果气泡 / 执行历史 / 宠物通用层状态。
- **exec 语义**：spawn 终端命令（cwd 可配、默认超时、stdout/stderr 尾部截取进历史）；**到点直接执行 + 事后结果气泡**，无前置确认（个人工具、命令自写明文可见），表单留「跳过本次」手动通道；opencode 作为**一等模板**（表单辅助拼命令），执行层不感知 opencode。
- **补跑语义**：系统睡眠唤醒后宽限窗口（15 分钟）内补跑一次，超窗跳过并记 skipped；托盘「暂停所有提醒」期间不跑不补、记 skipped。（与 v1 提醒"不补弹"的差异及理由：提醒错过无害、任务错过有信息损失，故小窗口内补。）
- **执行历史**：action logs 持久化（每次运行的时间 / 动作类型 / 退出状态 / 输出尾部截断），面板可查"今早跑了没 / 结果如何"。
- **宠物状态两层**：
  - 通用层（任何动作）：App 内部事件直接置态——执行中→working、退出码 0→success、非 0→error；
  - agent 层（exec 跑 opencode/claude 时）：**现有插件/hooks 事件链路免费工作，零新开发**（spawn 的 `opencode run` 加载 pulse-pet-hook.js，thinking/editing/testing 细粒度状态经 HTTP 正常上报；例程会话同时进入 token 统计，口径自洽）；
  - 两层合并规则（agent 层优先、通用层兜底收尾）设计阶段定；与 M6 抢镜规则天然配套（例程会话与手头会话并行时靠最近活跃优先裁决）。
- **UI**：与提醒合并为「定时任务」tab（用户 2026-08-20 裁定两并一留：提醒+定时任务合并、Todo 独立）——一张列表加动作类型徽标（💧提醒 / ⚡执行），表单按 `action_type` 条件显隐字段；落 M2 新设计系统。i18n 命名设计阶段配套。
- **提醒 snooze**（源自 openpets，2026-08-21 裁定）：提醒气泡加「稍后 10 分钟」按钮（与既有"确认"并列）；调度语义（`last_triggered_at` 顺延、与暂停/3 分钟去重的交互）设计阶段定。

### 3.5 M5：Token by agent（~1-1.5 周）

- **数据源**：Claude Code transcript JSONL 增量解析（`~/.claude/projects/*.jsonl`，agentpet `TranscriptReader` 已验证可行）；usage token 数为 API 实报、可信。
- **cost 口径（设计阶段定案）**：作者 CC 用**第三方模型 API key**，CC 自算 cost 按 Anthropic 官方定价计、**不可信**——CC 侧以 token 数为主，cost 省略或走自配单价表估算（DESIGN 阶段二选一）；opencode 侧 cost 逻辑不变。
- **Token 页统一视图**：by agent 统计与展示（用户已裁定：token 可以 by agent 进行统计和展示）——统一页 + agent 筛选维度，跨 agent 汇总；UI 落在 M2 新设计系统上；M3 的 `token_stats_today` / 今日 preset / 模型筛选 / 项目名映射届时扩展 by agent 维度（CC transcript 的 message 含 model 字段，顺接）；例程会话（M4 spawn 的 opencode run）是否加来源标注，随本里程碑设计定。
- **会话汇报气泡**覆盖 Claude Code 会话（落 M2 重构后的新气泡组件）。

### 3.6 M6：多 agent × 多 session 抢镜（~0.5-1 周）

- 背景：作者真实多开（多 opencode session + Claude Code 并行），v1 纯优先级合并可能让「不关心的 session 报错长时间抢镜」。
- **规则：最近活跃优先**（如「最近 5s 有事件的 session 优先」，DESIGN §12 既有设想），叠加原优先级合并。
- **气泡带 agent 标识**：多 agent 后状态来源需可辨识（气泡/悬浮信息标注 opencode / claude-code；落 M2 重构后的新气泡组件）；与 M4 例程会话的抢镜协同（例程跑时恰逢手头会话活跃）随本里程碑设计定。

### 3.7 彩蛋池（视余力，不承诺）

- atlas v2（8×11）注视方向行驱动（眼神跟光标类；网格加载 v1 已支持 9/11 行，缺驱动语义）。
- 子代理感知（源自 clawd，2026-08-21 评审）：agent 派 subagent 干活时驱动 atlas 预留的 jumping 行（v1 至今无状态映射，插件侧识别 task/agent 工具即可，几乎免费）。
- 轻量成就（源自 agentpet 简化版，2026-08-21 评审）：连续陪伴 N 天 / 累计 100M token 等里程碑放一次烟花（reminder_logs + opencode.db 数据已有，成本低；完整养成系统不做）。
- 双击戳一下 / Mini mode 贴边隐藏（源自 clawd 交互系列，2026-08-21 评审）：与挂起的「左键单击行为」决策同批再议。

---

## 4. 明确不做（及理由）

| 项 | 理由 |
|---|---|
| **双向权限审批**（气泡内 Allow/Deny/Always） | 用户裁定价值不大：权限请求均需仔细查看，代答反而增加误批风险。HTTP return channel 保持休眠（v1 总返回 `{action:null}`，协议预留不删不启用）。单向展示保留（§3.1） |
| **心跳机制 + `/health` 限流豁免**（V1-OPEN-ITEMS 五-1/五-3） | 原捆绑场景是双向审批；v0.1.3 流式心跳（四-4）落地后 App 侧活性感知已够，心跳只剩「探测插件进程存活」边缘用途，成本大于收益 |
| MCP 兜底（react/say/status 三工具） | Claude Code 直接接入后无服务对象 |
| 额度环（statusline `rate_limits`） | 作者用第三方模型 API key，无 Claude 订阅额度可读 |
| 排行榜（后端/登录/上传） | 引入 4 个新面（后端/身份/隐私/协议），与本地工具定位最远；推迟至 v3+ |
| 对话入口（opencode run 交互式） | 偏离桌宠定位（cc-haha 教训：桌宠沦为工作台一角）。**澄清**：M4 定时任务是后台 spawn + 事后汇报，无对话 UI，与本条裁定不冲突 |
| **waiting-permission 系统通知/托盘角标**（agentpet 式） | 用户裁定太侵入（2026-08-21）；气泡 + review 姿态已够，不引入系统通知通道 |
| **宠物自主漫游**（重力+弹跳走动，openpets 式） | 与穿透/位置记忆/"不挡操作"哲学冲突；原地跑动动画已有生命感（2026-08-21 评审裁定不做） |
| focus 模式 / 多 pet 同屏 / 自动更新 | 维持 v1 DECISIONS 既有裁定；个人工具定位下无收益 |
| **插件 SDK / 插件市场** | 用户 2026-08-20 裁定维持不做。理由（三视角共识）：v1 插件外壳已证明无第二消费者前建机制必是死代码（manifest 四件套无一被真实消费）；「不想要的用户可以不装」的真实诉求是「别让我看见」，由 M2 的模块注册表 + feature flag（消费 plugins 表 enabled 列）以 ~5% 成本覆盖 80%。**触发条件**（满足才重评）：拆仓 + 真实外部用户增长 + 出现第一个想自己写功能的人（v3+） |
| 未来动作类型（opencode-task via API / webhook / builtin / 平台自动化） | v2 只做 notify / exec 两种；泛化模型（type+params JSON）已容纳扩展，届时只加枚举值。注意 webhook 引入网络出口，违背 v1「不请求网络权限」原则，届时需单独安全裁定 |
| 宠物素材重绘 / 烟花粒子引擎重做 | 不在 UI 优化范围（M2 §3.2）；烟花调整留彩蛋池 |
| 旧版 opencode 纯文件存储完整解析 | 保留现有「提示升级 opencode」即可 |

---

## 5. 设计输入与风险（v2 方案设计阶段处理）

1. **CC transcript 字段实测**：`~/.claude/projects/*.jsonl` 的 usage/模型字段结构需先 spike（M5 前置）；`message.updated` / `message.part.updated` 字段实测（v0.1.3 前置）。
2. **cost 口径**：CC 侧 cost 省略 vs 自配单价表估算（M5 设计定案，见 §3.5）。
3. **hooks 安装器幂等性**：`~/.claude/settings.json` 的 hooks 段结构比 opencode.json 的 plugin 数组复杂（按事件分组的命令数组），合并/卸载的 managed 标记方案需专门设计（M1 前置）；接入管理区的 JSONC 感知合并 Rust 侧实现路径同段设计。
4. **AgentAdapter 职责收口**（DESIGN §3.4 遗留）：v1 事件归一化在 TS 插件、token 读取在 Rust，跨两层；v2 接入第二 agent 时评估是否把 `tokenSource` 实现收口进 `AgentAdapter`（每个 adapter 自带 token 读取实现，Rust 侧只暴露通用 fs/JSONL 能力）。M5 设计时一并定。
5. **session key 迁移**：`sessionId` → `(agent, sessionId)` 影响 Rust `session_state`、http_server 校验与前端 store，需迁移方案（纯内存态，无持久化迁移问题，预期小）。
6. **多屏实机 / Windows 剩余核对**（V1-OPEN-ITEMS 一）：不进 v2 里程碑，维持观察项（等硬件顺带）。
7. **前端 UI 基础（M2）设计输入**：设计语言与像素宠物的协调方案由 skill 辅助产出方向稿后用户拍板；样式技术取舍（维持手写 CSS vs 引入 Tailwind / 组件库——现零 UI 依赖、包体积敏感，v1 ~4MB 安装包是亮点）设计阶段定；frontend-design / impeccable skill 的安装在开工前确认（本机 github.com 网络不稳，可能需手动拷贝）；气泡排队模型参数（来源优先级表 / 并发上限 / dwell 时长 / 谁挤掉谁）。
8. **定时任务（M4）设计输入**：`reminders` 表迁移设计（action_type/action_params/schedule_kind 加列 + once 语义 + 与 todo 派生行共存）；exec 细节——超时默认值、Windows shell 差异（cmd/PowerShell）、`opencode run` 非交互模式下的权限行为（遇审批是卡死还是跳过，需 spike）、输出捕获上限；feature flag 禁用语义（隐藏 tab + 停派生提醒 + 数据保留的精确行为）；宠物状态两层合并规则（agent 层优先、通用层兜底收尾）；定点调度（daily-at/weekly-at/once）的到点判定与补跑宽限窗实现（MissedTickBehavior Skip 之上的精确判定）；snooze 与暂停/3 分钟去重的交互语义。
9. **tab 注册表形态（M2）**：核心 tab 与模块注册的边界（哪些属于核心不可关：Token/设置；哪些可关：Todo/定时任务）、注册表数据结构（前端静态注册 vs 消费 plugins 表）、与「最坏 6 个 tab」导航设计的配合。
10. **Token 看板增强（M3）实现细节**：悬停宠物 500ms 的防抖/关闭时机（mouseleave）与气泡既有 8s 自动消失逻辑的优先级（受 M2 排队模型约束）；会话结束气泡追加「今日累计」——Rust idle hook 顺带查当日聚合、新鲜度护栏沿用 60s 口径；模型数据边界——session.model 可为 NULL（回退「未知模型」合并）、历史存在 `deepseek-v4-flash@max` 类带后缀 id（按原样归并）、probe-model 等 mock 模型是否过滤；会话标题兜底与列宽策略；JOIN project 表的性能影响（现有查询即开即关，预期可忽略）。
11. **工具级气泡（M3）设计输入**：开关实现层（倾向 App 侧过滤，不动插件）确认；白名单模板集清单（读/编辑/跑命令/搜索/访问 URL 等中英文案）；basename / 命令首词的提取与净化规则（TC-SEC 口径，不带路径与参数原文）；与 M2 排队模型 / speech 桶 20s 节流的配合。

---

## 6. 实施顺序

```
v0.1.3 维护版（含 TC-DONE 综合验收 + 发版）
  └→ v2 M1 Claude Code 事件接入 + 接入管理（几乎无 UI 改动）
       └→ v2 M2 前端 UI 基础（设计系统 + 面板 + 气泡组件/排队模型 + tab 注册表/feature flag，skill 辅助）
            └→ v2 M3 Token 看板增强 + 工具级气泡（今日 preset/三层通道/堆叠柱图/模型筛选/会话列表/工具播报+开关，落新设计系统）
                 └→ v2 M4 定时任务（动作泛化 notify/exec + 「定时任务」合并 tab + snooze + 执行历史）
                      └→ v2 M5 Token by agent（CC transcript + agent 筛选维度）
                           └→ v2 M6 抢镜规则（依赖 M1 多 agent 场景 + M4 例程会话；气泡 agent 标识落新气泡）
```

依赖关系：M2 依赖 M1（CC 接入先稳定事件面再重构 UI）；M3 依赖 M2（功能落新设计系统与气泡排队模型）；M4 依赖 M2（合并 tab 落新设计系统）；M5 依赖 M1（CC 数据源）与 M2（设计系统），M3 的看板各项届时扩展 by agent；M6 依赖 M1（多 agent 场景）与 M4（例程会话参与抢镜），且受益于真实使用反馈。M4 与 M3/M5 之间无强依赖，如需可互换。
