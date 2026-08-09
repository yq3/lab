# PulsePet v1 范围决策记录

> 记录日期：2026-08-09
> 来源：基于 `desktop-pet-research.md` 调研结论的对话讨论
> 性质：v1（POC 阶段）的边界与关键技术选型，作为后续方案设计（DESIGN.md）的输入

---

## 1. 命名

**项目名：PulsePet**（目录 `pulse-pet/`）

- 含义：`pulse`（脉冲/心跳）+ `pet`（宠物），即"盯 agent 状态脉冲的桌面宠物"，对应核心功能"监听 agent 工作状态并呈现"。
- 中文别名（非正式）：脉宠
- 选名理由：GitHub 上无同名开源项目；带 `pet` 词根符合产品品类直觉；与现有 7 个调研项目（openpets / petdex / clawd-on-desk / agentpet / oc-claw / PawPause / cc-haha）均不重名。
- 候选淘汰：Sparkpet / Lumipet / Crumbpet（备选）、Codama / Tokibi（含日文元素，已弃）。

---

## 2. v1 范围总览

| 维度 | v1 决定 | v2+ 规划 |
|---|---|---|
| Agent 支持 | 仅 opencode，但留 `AgentAdapter` 抽象 | 接入 Claude Code / Codex / 自研 agent |
| 事件链路 | opencode 插件 + 本地 HTTP（127.0.0.1 + token） | 维持 HTTP，扩展双向 |
| Token 统计 | 本地 by 会话/天/周/任意跨度聚合 | 加入后端服务与用户排行榜 |
| Todo 管理 | 自建轻量插件机制 + 独立存储 | 扩展更多内置/外置插件 |
| 权限气泡 | 单向：宠物只展示"权限待审"状态；用户在 agent 终端审批 | 双向：宠物气泡内 Allow/Deny/Always |
| 提醒形式 | 气泡文字（默认） + 可选"烟花模式"开关 | — |
| 素材 | 内置占位精灵打通链路，1 周内补 codex atlas 加载器 | 完整支持社区 178+ 素材 |
| 多 session | 单只宠物多会话切换（优先级合并式） | — |
| 对话入口 | 不做 | v2+ 评估接入 opencode run |
| 跨平台 | macOS + Windows（Linux 非目标，运行不起也不修） | — |
| 代码归属 | lab 下独立目录 pulse-pet/，develop 分支，不主动 push | 通过后单独建仓 |
| 提交策略 | 不主动 commit/push；push 时用 SSH | — |

---

## 3. 关键决策与依据

### 3.1 Agent 范围：opencode 优先 + 留扩展通道

**决定**：v1 仅支持 opencode，但架构上通过 `AgentAdapter` 抽象保留后续接入 Claude Code / Codex / 自研 agent 的便捷通道。

**依据**：
- opencode 是作者主力 agent，且其原生 SQLite（`~/.local/share/opencode/opencode.db` / Windows `%LOCALAPPDATA%\opencode\opencode.db`）已含精确 `tokens_input/output/reasoning/cache_read/cache_write` + `cost`，三端同路径同 schema、零侵入精确——这是 token 统计最大的"白嫖"。
- 跨 agent 通用化会立刻引入 transcript 增量解析（Claude Code）、JSONL 轮询（Codex/OpenClaw）、telemetry 读（Gemini）等多种异构链路，复杂度上一个台阶，不适合 v1 POC。
- `AgentAdapter` 抽象仅约束接口（事件输入契约 + token 数据源），不实现多份适配器，零成本。

### 3.2 事件链路：HTTP + token（petdex / openpets 风格）

**决定**：opencode 插件把归一化事件 POST 到本地 HTTP server（127.0.0.1 + token 文件 0600 + 每会话轮换），Tauri 侧起一个 tiny HTTP server。

**否决方案**：JSONL 文件总线（PawPause 方案，~30 行插件 + fs.watch）。

**比较**：

| 维度 | JSONL 文件总线 | 本地 HTTP + token ✓ |
|---|---|---|
| 客户端实现 | `fs.appendFile` 一行 JSON | `fetch POST 127.0.0.1` |
| 服务端 | `fs.watch` | tiny HTTP server / Unix socket |
| 延迟 | 100ms~1s（watch + 去抖动） | <10ms |
| 双向控制 | 不行（单向写文件） | 可以（HTTP 返回值回传审批结果） |
| app 关闭时事件 | 不丢，可回放 | 会丢（除非加队列缓存） |
| 隐私 | 事件明文落盘（含命令原文、文件路径） | 仅内存传递，不落盘 |
| 多 agent 同时上报 | 各写各文件天然分流；append 需去重 | 共享 HTTP server，天然并发 |
| 跨平台 | Tauri `fs.watch` 在 Windows/macOS 行为不一致，需兜底轮询 | 三个平台一致 |
| 实现代码量 | 最少（~30 行插件 + watch） | 中等（~100 行插件 + HTTP server） |

**取舍**：JSONL 唯一甜头是"实现最简单"，但插件省下的几十行会被三端 `fs.watch` 调适成本还回来。HTTP 方案同时为后续"权限气泡双向回传""烟花精确触发时机""明文不落盘的隐私诉求"预留空间，避免返工。

**参考实现**：
- petdex `hook_server.zig`（进程内 HTTP，30/s 限流，一次性连接，无分配热路径）
- openpets `@open-pets/client` + `local-ipc.ts`（Unix socket / 命名管道 / 私有 TCP，discovery 文件 + 每请求 token，消息 ≤16KB，超时上限）

### 3.3 Token 统计：本地完整聚合，不做排行榜

**决定**：v1 实现 by 会话/天/周/任意时间跨度的本地 token 统计与展示；**不做用户排行榜**。

**依据**：
- 排行榜作为副几期工作，引入 4 个新东西：① 后端服务（中心化比对）② 用户登录/身份 ③ 隐私边界（用户是否愿意上报 token）④ 数据上传协议。这 4 件事 openpets / petdex / PawPause 都没全解决，agentpet 也只做了"前端展示 + GitHub 登录 + 同步"半个参考。
- v1 直接做排行榜会拖慢核心链路验证。
- v1 接口层预留"聚合结果可序列化"输出，便于 v2 直接对接后端。

**数据源**：
- **opencode 用户**：直接读 opencode SQLite 的 `session` / `message` 表（已有 `cost, tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write` 聚合列），用只读连接（WAL 模式与运行时无冲突），按 `time_created/time_updated` + `project_id` 聚合。
- **早期版本兜底**：库不存在时读旧格式 `storage/session/*.json` / `storage/message/*.json`；按 opencode 版本检测做双路径兼容。
- **Claude Code 用户**（v2+）：走 transcript 增量解析（agentpet `TranscriptReader` 已验证可行）。
- **额度环展示**（可选，参考 clawd）：读 Claude Code status-line 的 `rate_limits.five_hour/seven_day.used_percentage` + `resets_at`。

**估算兜底**（仅当真实数字缺失，参考 agentpet `ModelPricing`）：per-million USD 单价表 + cache write 1.25× 、cache read 0.1×。

### 3.4 Todo 管理：自建轻量插件机制 + 独立存储

**决定**：不耦合 todo-lite；不读 opencode 原生 todo 表；自建一个轻量插件机制，v1 仅挂 todo 一个插件，独立存储。

**依据**：
- todo-lite 是独立应用，耦合其 SQLite 会带来多窗口并发锁、schema 演进耦合、拆仓困难。
- opencode 的原生 `todo` 表语义是"一个会话内子任务分步骤执行的记录"——不是用户自己的日常待办，用途错位。
- 自建插件机制的成本与风险都低于"复用任一外部 todo 存储"。
- v1 只挂 todo 一个插件，但机制留扩展槽位，喝水/休息/番茄钟等可作未来插件增量。

### 3.5 权限气泡：单向展示

**决定**：v1 宠物只展示"权限待审"状态；用户在 agent 终端审批之后，宠物通过监听 `session.status` 变化自动跟随更新。HTTP 协议预留双向 return channel（可返回值），但前端不画 Allow/Deny/Always 按钮。

**功能说明（什么是权限气泡）**：
opencode / Claude Code 在执行敏感操作（写文件、跑命令、调网络）前会发起 `permission.asked` 事件——CLI 终端里会卡住等用户按 y/n/Always allow/Deny。"权限气泡"是把这个终端提示搬到桌面悬浮卡片上：
- 宠物头上弹气泡"opencode 想执行 `rm -rf node_modules`，是否允许？[Allow] [Always] [Deny]"
- 用户点按钮 → 宠物通过 HTTP 把决定回传 opencode 插件 → 插件喂给 opencode 终端 → 终端收到答案继续跑

**v1 为什么单向**：
- 单向只需监听 `session.status`，无交互 UI、无多请求堆叠处理、无"终端先答了气泡要自动消失"的同步逻辑，复杂度显著降低。
- v1 宠物已经在监听 session 状态（成功/失败/思考中），权限待审只是多一个状态分支，零额外链路成本。
- HTTP 协议预返回值通道（即使 v1 不用），v2 加 UI 是增量不重构。

**参考**：clawd-on-desk 的权限审批气泡（独有杀器，支持 Allow/Deny/Always 规则 + 全局热键 Ctrl+Shift+Y/N + 多请求堆叠 + 终端先答自动消失 + per-agent 开关）。

### 3.6 提醒效果：气泡 + 可选烟花

**决定**：两种独立提醒形式，由用户设置切换。默认仅气泡；用户在设置里改"烟花模式"才有烟花效果。

**形态**：
- **气泡文字**：宠物上方弹气泡显示该喝水了之类，不干扰屏幕内容。
- **烟火模式**：宠物向整个屏幕放一束烟花，达到醒目效果。要求：轻量、效果好、清晰度高、类似日本动漫里的效果（避免廉价粒子）。

**实现倾向（待方案设计阶段定案）**：HTML canvas 全屏覆盖层 + 粒子动画。成本最低、跨 macOS/Windows 一致、不引入额外渲染器（对比 Tauri 多窗口分层 / 平台原生各自实现）。

### 3.7 素材：占位精灵起步 + 1 周内补 atlas

**决定**：v1 用内置 1 张 PNG 简单动画打通链路（~50 行 canvas 代码，立即可跑）；atlas 加载器在第一周内补入（petdex `sprite.zig` 帧表照抄 TS）。

**两种起步方式比较**：

| | 内置占位 | 直接接 codex atlas |
|---|---|---|
| 实现成本 | 一张 PNG 几帧切换，~50 行 canvas 代码 | atlas 切帧 + 帧时长表，半天到一天 |
| 视觉 | 单调（一两动画） | 9 个状态对应 9 行动画，社区 178+ 素材即装即用 |
| 第一版验证 | 只验证链路通不通 | 直接验证"agent 工作中→宠物开始跑"完整体验 |
| 起步时间 | 立刻 | 先写 atlas 加载器 |

**取舍**：不是二选一，是先后——先用占位加速打通链路，atlas 加载器一周内补，因为社区素材直接拿来用价值太高。

**后续素材标准**（atlas 加载器完成后）：
- 直接复用 codex atlas 格式（`pet.json` + `spritesheet.webp`，v1 8×9 = 1536×1872 / v2 8×11 = 1536×2288，单帧 192×208）。
- 扫描 `~/.codex/pets/` + `~/.petdex/pets/`，`npx petdex install xxx` 装的直接可见。
- Tauri canvas 按帧时长表播放行序列，petdex 的 `sprite.zig` 帧表直接照抄 TS 版本。
- 9 个状态：`idle / running-right / running-left / waving / jumping / failed / waiting / running / review`。

**素材许可注意**：
- awesome-codex-pet 素材 **CC BY-NC 4.0**（非商用），自用无碍，发布需逐一核对。
- petdex 素材归各提交者所有、许可自选。
- 自用 POC 阶段无碍；后续若拆仓开源/商用需逐一确认。

### 3.8 多 session：单只宠物多会话切换

**决定**：用户同时开多个 opencode session（多项目/多分支）时，**单只宠物**根据最活跃 session 显示状态（clawd 优先级合并式）；token 统计 per-session 但 UI 上合并展示。

**否决方案**：
- 每 session 一只宠物（openpets lease 模型）——需要位置管理与多窗口，UI 复杂。
- 主宠物 + 托盘看其他——v1 UI 简化优先。

**实现要点**：状态优先级合并参考 clawd 的 `state.js` 多会话状态优先级合并逻辑（哪个 agent / session 最"活跃"显示哪个动画）。

### 3.9 跨平台：macOS + Windows

**决定**：v1 仅保证 macOS 与 Windows 可用。Linux 非目标，能跑则跑不能跑不修。

**已知三端行为差异**：
- `fs.watch`（不选文件总线，规避此问题）。
- Accessibility 权限（macOS focus 模式检测活动窗口需要）——v1 不做 focus 模式时无此问题。
- 透明窗口、点击穿透（Tauri `transparent` + `setIgnoreCursorEvents`）在 Windows 上边缘行为需测试。

**opencode SQLite 跨平台路径**：

| 平台 | 路径 |
|---|---|
| macOS / Linux | `~/.local/share/opencode/opencode.db`（实测 v1.18.11，**不是** `~/Library`！） |
| **Windows** | `%LOCALAPPDATA%\opencode\opencode.db`（xdg-basedir 在 win32 映射到 LOCALAPPDATA） |
| 非稳定 channel | 同名但带渠道后缀：`opencode-{channel}.db`（如 canary） |

### 3.10 代码归属：lab 下独立目录

**决定**：作为 lab 仓库下的独立目录 `pulse-pet/`（按 AGENTS.md 约定"每个 App 一个独立目录"）；开发在 `develop` 分支；POC 阶段不主动 commit / push。

**依据**：与 todo-lite 一致的处理方式；POC 验证通过、效果稳定后再考虑拆仓单独建仓继续演进。

---

## 4. 已确认需要研究内容里照搬的部分

来自 `desktop-pet-research.md` 调研结论、且在本次对话中确认照搬：

- **opencode 集成**：注册到 `~/.config/opencode/opencode.json` 的 `plugin` 数组；hooks：`event`（`permission.asked`→waiting、`session.error`→error、`session.status` idle→success）+ `chat.message`→thinking + `tool.execute.before`→editing/testing（命令含 test/vitest/jest/pytest/npm test 等）。
- **节流**：speech 20s / permission 3s / reaction 10s 冷却（原子写 JSON 状态文件）。
- **自忽略**：正则跳过 `pulsepet_status/say/react` 工具，防止回环（openpets 已踩过的坑，照搬）。
- **消息净化**：气泡只显示状态 + 权限待审 + 提醒文字，**不显示代码 / 路径 / 命令原文 / URL / secret 样式 token**（参考 openpets 安全语音池思路，从源头规避敏感信息泄露）。
- **MCP 兜底**（v2+ 评估）：`opencode.json` 的 `mcp` 段注册自建 server（react/say/status 三工具），让 Claude Code 等其它 MCP agent 顺带可用。
- **指令文件引导**：在 `AGENTS.md` / 项目指令中声明"有新进展时用 react/say 汇报"，让 agent 主动驱动宠物。
- **窗口配置**：透明、无边框、置顶、点击穿透（Tauri `transparent` + `setIgnoreCursorEvents`）。
- **窗口渲染**：canvas 按帧时长表播放行序列（petdex `sprite.zig` 照抄 TS）。

---

## 5. 留待方案设计阶段定的小问题

下列在本次对话明确不阻塞方案设计，留到该阶段定案：

1. **烟花渲染选型**：HTML canvas 全屏覆盖层 vs Tauri 多窗口分层 vs 平台原生。倾向 canvas 全屏覆盖层（成本最低、跨端一致、粒子动画好做），需在方案设计阶段做最小验证。
2. **宠物窗口交互**：拖拽、多显示器定位、点击穿透、托盘菜单 —— v1 建议够用最小集，需枚举哪些"必须"哪些"延后"。
3. **HTTP server 端口策略**：固定端口 + token 文件 mode 0600（petdex 模式）vs 随机端口写 discovery 文件（openpets 模式）。倾向固定端口 + token，简单；多 app 实例冲突方案设计阶段评估。
4. **AgentAdapter 抽象位置**：Rust 侧（Tauri command）还是 TS 侧（webview）。倾向 TS 侧——因 opencode 插件是 JS 写的、跨 agent 协议归一化在 JS 更顺；token SQLite 读取也可走 Tauri fs + sql.js 在 webview 侧解析（只读连接、WAL 兼容性需验证）；或 Rust 侧用 rusqlite / sqlx 开只读连接再传 JSON 给前端。
5. **todo 插件机制形态**：先实现机制但只挂 todo 一个插件？还是先实现 todo 内置、机制延后？倾向先实现机制但只挂 todo 一个插件（参考 openpets 插件 SDK 缩水版：manifest + 权限面 + 配置 schema）。
6. **数据库读 SQLite 的 Rust 侧选型**：rusqlite vs sqlx vs Tauri plugin-sql；只读连接 + WAL 模式 + opencode 运行时同时写的兼容性测试。

---

## 6. 下一步

进入方案设计阶段，产出 `DESIGN.md`：
- 整体架构图（opencode 插件 ↔ HTTP ↔ Tauri 进程 ↔ Webview 渲染）
- 模块划分与代码组织（pulse-pet/ 目录结构）
- 关键技术点踩坑预案（上节 6 个小问题先行验证）
- v1 实现里程碑（链路打通 / atlas 加载器 / token 聚合 UI / 提醒 + 烟花 / todo 插件）
- v1 done 标准