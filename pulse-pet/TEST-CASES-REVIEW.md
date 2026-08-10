# TEST-CASES.md 评审报告

> 评审日期：2026-08-10
> 评审对象：`TEST-CASES.md`（对照 `DESIGN.md` / `DECISIONS.md` / `DESIGN-REVIEW.md` / `desktop-pet-research.md` 交叉检查）
> 结论：用例覆盖度高（约 95 个用例）、编号体系规范、评审项→用例对照表与 DESIGN-REVIEW.md 的 A/B/C 组问题映射基本完整，可作为各里程碑的验收依据。但存在 **4 类设计缺口未被用例暴露**、**6 处测试覆盖缺口**、**5 处用例自身严谨性问题**，以及若干编号/对照表遗留。

---

## 一、设计缺口（用例应反向指出，但当前缺失）

### 1.1【高】节流分类与归一化事件的映射未定义（TC-EV-18）

- TC-EV-18 步骤写"语音类 5 次、权限类 5 次、反应类 5 次"，但 DESIGN §3.1 只列出"speech 20s / permission 3s / reaction 10s"三类冷却，**未定义哪些归一化 kind 属于哪一类**。
- 归一化 kind 有 8 种（idle / working / thinking / editing / testing / waiting-permission / error / success），无法直接映射到三类冷却。
- 建议：在 DESIGN 补一张 `kind → throttle-category` 映射表，并在 TC-EV-18 的预期里引用该表。

### 1.2【高】"今日"语义未定义（TC-TD-05）

- TC-TD-05 预期"今日完成 N 项"，但"今日"是按自然日 0 点？用户本地时区？24h 滚动？DESIGN §8.3 也未明确。
- 这关系到 `completed_at` 的时区处理与 SQL 聚合的 strftime 参数。
- 建议：明确"按用户本地时区自然日 00:00 起"，并在 TC-TD-05 引用该语义。

### 1.3【高】`remind_before_minutes=0` 语义模糊（TC-TD-08）

- TC-TD-08 预期写"到点本身是否提醒不引入（0 = 不提前提醒语义成立）"——这句话本身语义不清：是"0 = 完全不提醒"还是"0 = 到点提醒，只是不提前"？
- DESIGN §8.2 字段注释同样只写"0 = 不提前提醒"。
- 建议：明确为 `0 = 不生成派生 reminder`（即完全无提醒）；`>0 = 到点前 N 分钟提前 1 次`。并用 TC-TD-08 显式核对 0 值不派生 reminder 行（写入 `reminders` 表那一行根本不出现）。

### 1.4【中】`reminders.last_triggered_at` 与 `todos.remind_last_triggered_at` 双字段语义重叠（TC-TD-06）

- TC-TD-06 预期同时引用两个字段做防重，但两表都存"上次触发时间"，存在冗余/同步风险。
- 建议：在 DESIGN 里定论"todo 派生提醒只用 `reminders.last_triggered_at`，`todos.remind_last_triggered_at` 保留但 v1 不写"，或反之；TC-TD-06 应只验证单一来源。

---

## 二、测试用例与设计描述不一致

### 2.1【中】占位阶段"60fps 切帧"表述歧义（TC-SP-01）

- TC-SP-01 直接照搬 DESIGN §6.1"60fps 切帧"，但占位精灵是 **1 张 128×128 PNG 单图**，无法"切帧"。
- 实际语义应是"canvas 按 60fps 重绘，状态切换时切换帧图"。
- 建议：TC-SP-01 预期改为"占位阶段每状态渲染单帧，状态切换时画面立即更换；rAF 循环 60fps 维持动画时序"。

### 2.2【低】白名单语音池"五类"相对 openpets 是扩展（TC-EV-20）

- TC-EV-20 / §3.1 写"thinking / success / error / permission / waiting 五类"，而调研报告 3.1.3 与 DECISIONS §4 引用 openpets 时是"四类"（无 waiting）。
- 这是 PulsePet 主动新增 waiting 模板，但 TC 没标注是扩展，读者易误以为是照搬。
- 建议：在 TC-EV-20 预期里加一句"waiting 类为 PulsePet 在 openpets 四类基础上的扩展，模板独立定义"。

---

## 三、覆盖缺口（设计有，用例未覆盖）

### 3.1【高】默认 `ignoreCursorEvents=false` 未被显式验证

- TC-APP-01 仅核 `transparent / decorations / alwaysOnTop / skipTaskbar / resizable / shadow`，未核 `ignoreCursorEvents:false` 默认值。
- TC-WIN-06 同样遗漏。
- 这恰恰是 DESIGN-REVIEW A1 矛盾点修正后的关键结论（M1-M5 默认非穿透），必须有显式断言。
- 建议：在 TC-APP-01 预期 1 里补一条"启动后 `pet.setIgnoreCursorEvents()` 初始返回 false"；或新增 TC-APP-01b 专测穿透默认值。

### 3.2【高】`/state` body 字段校验未测（TC-EV-12）

- TC-EV-12 只测路由返回码，未测 DESIGN §3.2 约定的 body 契约 `{sessionId, kind, agent, project?, detail?}`。
- 必填字段缺失（如缺 sessionId / kind）应返回 400。
- 建议：在 TC-EV-12 后补一步：缺 sessionId、缺 kind、kind 非白名单值各发一请求，预期均 400。

### 3.3【中】Windows 端 endpoint/token 文件路径未测

- TC-EV-08 仅核 POSIX 路径 `~/.pulsepet/runtime/update-token`。
- Windows 应位于 `%LOCALAPPDATA%\pulsepet\runtime\`（DESIGN 未明确，但 TC-SEC-05 隐含用 `%LOCALAPPDATA% / ~/.pulsepet`）。需要补 Windows 版本的 TC-EV-08 / TC-EV-09。
- 建议：新增 TC-EV-08b（Windows token/endpoint 路径）。

### 3.4【中】"选择宠物"下拉 UI 未测（TC-SP）

- DESIGN M5 明确列出"控制面板'选择宠物'下拉"，但 TC-SP 没有任何用例核对下拉 UI、切换后宠物加载、无可用 atlas 时下拉的回退显示。
- 建议：新增 TC-SP-11 选择宠物下拉（列出 `~/.codex/pets` + `~/.petdex/pets` 扫描结果 + 内置占位为可选项；切换后立即重新加载并热替换 webview 帧）。

### 3.5【低】todo_tags 标签 CRUD 与 sort_order 排序行为未显式测（TC-TD-02）

- TC-TD-02 预期仅列出字段名，未显式验证 tag 增删、级联、与 sort_order 排序的实际行为。
- 建议：在 TC-TD-02 步骤后补"建立带 tag 的 todo → 删除 tag → 调整 sort_order → 核查列表顺序"。

### 3.6【低】opencode.json 是否 JSONC 感知未测（TC-EV-01）

- TC-EV-01 只测"用户原有 plugin 项保留不误删"，未测用户在 opencode.json 里有注释 / 尾逗号时是否仍能被合并。
- 调研报告（openpets `opencode-config.ts`）特别强调 JSONC 感知。
- 建议：在 TC-EV-01 步骤里加"在用户 opencode.json 的 plugin 段前后加注释行 → 跑 install.sh → 核对注释仍在"。

---

## 四、用例自身严谨性问题

### 4.1【中】TC-APP-05 "暂停所有提醒"等待时长未明确

- 步骤"等到原本会触发的时刻"过于宽泛，难以稳定复现。
- 建议：改为"先配置一条 1 分钟间隔的提醒 → 开启暂停 → 等待 90 秒，确认无气泡"，提高可重复性。

### 4.2【中】TC-EV-07 指数退避序列无观察方式

- 预期"1s→2s→5s→30s 封顶"如何观察？插件静默跳过、无日志输出（这是 TC-EV-07 自己的要求），无法直接观测重试间隔。
- 建议：要么在测试期开启插件 `PULSEPET_DEBUG=1` 输出退避时间戳；要么改为"用单元测试 / 集成测试在插件模块层 mock 时间，断言退避序列"。

### 4.3【中】TC-RM-09 烟花发射点与帧率无观察方式

- "粒子数 ~300-500、60fps、从宠物位置发射"，但纯渲染效果无自动化断言手段。
- 建议：拆分为两部分——可断言部分（窗口 `show` / `hide` 时序、3-5s 内必 hide、二次 show 不残留）留作 TC-RM-09；视觉部分（粒子轨迹、发射点、60fps）单独标为"目视验收项"，不进自动回归。

### 4.4【中】TC-EV-18 "反应类"事件如何触发未说明

- 与 1.1 节流分类缺失相关——"反应类 5 次"无明确事件源。
- 建议：先在 DESIGN 补 kind → category 表，再用具体 kind（如 `event` 透传分类）触发。

### 4.5【低】TC-SP-01 占位阶段"未覆盖状态映射"仅一笔带过

- TC-SP-01 预期最后说"waiting-permission → thinking、testing → working 等未覆盖状态映射到最近同类"，但仅在 5 状态切换一笔带过，未单独验证。
- 建议：单独列 TC-SP-01b，对占位阶段逐个驱动 8 种状态，断言 5 状态外状态的降级渲染。

---

## 五、编号与对照表问题

### 5.1【低】评审项对照表缺 B14 / C14 映射

- DESIGN-REVIEW B14（AgentAdapter 职责分裂）在评审记录里有，DESIGN §3.4 已承认此边界，TC-EV-23 实际覆盖了"接口存在 + 新增 adapter 不改主链路"。
- 但对照表未列 B14 → TC-EV-23。建议补上。

### 5.2【低】TC-APP-11 / TC-APP-12 跨里程碑内容

- TC-APP-11"跨显示器拖拽"内容属 M6（TC-WIN 章节），放在 TC-APP 易造成"在 M1 就应回归"的误解。
- TC-APP-12"宠物选择"是 M5 后才有，M1 阶段应只核穿透 / 烟花 / 提醒。
- 建议：TC-APP-11 移入 TC-WIN 章节或加里程碑标注"M6+"；TC-APP-12 拆为"M1 持久化基线（穿透 / 烟花 / 提醒）"与"M5 后补充（宠物选择）"两步。

### 5.3【低】TC-DONE-01~09 与 DESIGN §11 一一对应

- 9 条对应 9 条，无遗漏。✓

---

## 六、修订优先级

| 优先级 | 项 | 行动 |
|---|---|---|
| P0（阻塞测试执行） | 1.1 节流分类映射 | 先在 DESIGN 补 kind → category 表，TC-EV-18 引用 |
| P0 | 1.3 `remind_before_minutes=0` 语义 | DESIGN 与 TC 同步明确为"0 = 不派生 reminder" |
| P0 | 3.1 默认非穿透断言 | TC-APP-01 / TC-WIN-06 补 `ignoreCursorEvents:false` |
| P0 | 3.2 `/state` body 校验 | TC-EV-12 补必填字段缺失 → 400 |
| P1 | 1.2 "今日"语义 | DESIGN 与 TC-TD-05 同步明确本地时区自然日 |
| P1 | 1.4 防重字段单一来源 | DESIGN 定论，TC-TD-06 单源验证 |
| P1 | 3.3 Windows 文件路径 | 新增 TC-EV-08b |
| P1 | 3.4 选择宠物下拉 | 新增 TC-SP-11 |
| P2 | 2.1 / 4.1-4.5 表述与可执行性 | 逐条细化步骤与观察方式 |
| P2 | 3.5 / 3.6 / 5.x | 补充次要覆盖与对照表 |

---

## 七、未发现的正面问题（确认 OK）

- 评审项对照表对 A1 / A2 / A3 / B4-B8 / B16-B17 / C9-C13 / C15 / C18-C19 的映射均正确 ✓
- TC-DONE 9 条与 DESIGN §11 9 条 v1 Done 标准一一对应 ✓
- 优先级合并顺序 (TC-EV-16) `error > waiting-permission > testing > editing > thinking > working > idle` 与 DESIGN §3.3 完全一致 ✓
- 8 状态 → 9 行 atlas 映射表 (TC-SP-07) 与 DESIGN §6.2 表完全一致 ✓
- 多 session 回收条件 (TC-EV-17) 正确排除了 `/health` 分支，呼应 B5 ✓

---

## 八、后续动作建议

- 优先解决 P0 四项（节流分类、`remind_before_minutes=0` 语义、默认非穿透断言、`/state` body 校验）——这四项不解决会直接阻塞对应里程碑的测试执行。
- P1 四项可在对应里程碑（M3 / M5 / M7 / M8）开始前补齐，不影响早期里程碑。
- P2 项作为打磨项，可在 M8 收尾阶段统一处理。
- 修订完成后可在 `TEST-CASES.md` 顶部加一行指向本文档的链接，并在 `DESIGN.md` 顶部补一行指向 `TEST-CASES-REVIEW.md` 中"设计缺口"小节的反向链接。