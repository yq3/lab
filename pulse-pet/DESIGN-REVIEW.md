# DESIGN.md 评审记录

> 评审日期：2026-08-09（首次评审）
> 补审日期：2026-08-09（整合第二轮评估，新增 B16-B17 / C18-C19）
> 评审对象：`DESIGN.md`（对照 `DECISIONS.md` 交叉检查）
> 结论：设计整体质量高，A 组三处矛盾需优先修正；B 组为时序/设计缺口，实现前需验证或补定义；C 组为小问题或建议。

---

## A. 文档内部矛盾（建议直接修）

1. **穿透默认值自相矛盾**：§2.3 表说 pet 窗口"默认 `ignoreCursorEvents:true`（点击穿透）"，但 §7.1 末尾说"pet 与 fireworks 默认 `ignoreCursorEvents=false`（关闭穿透）"。需明确 M1-M5 阶段（拖拽/穿透切换在 M6 才做）宠物默认是可交互还是纯展示。
2. **右键菜单与穿透冲突**：穿透开着时鼠标事件全部穿透，右键菜单（§2.2、§9 `PetMenu.tsx`）根本收不到右键事件。§2.3"交互时临时设 false"在穿透为默认值的阶段无法自洽。需要定义：穿透状态下如何唤出右键菜单（托盘/hotkey 兜底）。
3. **DB 命名不统一**：`pulsemet.db`（§5.1、M1）vs `pulsepet.db`（§6.3、§8.1）出现两个名字，且都不等于项目名 PulsePet / pulse-pet。

## B. 时序缺口（实现前需验证或补定义）

4. **状态机缺少"复位"事件**：`tool.execute.before`→editing、`chat.message`→thinking 之后，没有任何 `tool.execute.after` / 消息完成事件把状态拉回 working。若 opencode 的 `session.status` 不是每轮必发，宠物会在 editing/thinking 上卡住。建议 M2 补 `tool.execute.after`→working 或加状态超时兜底。
5. **30s 回收条件形同虚设**：§3.3 写"30s 无事件 + 无 `/health` ping"，但插件只 POST /state、没有周期 ping `/health` 的设计，"无 /health"分支永远不会触发。要么插件加心跳，要么删掉该条件。
6. **App 退出/未启动时插件行为未定义**：token 文件被清除后（App 退出）插件 POST 必失败，文档没写插件侧对连接失败/401 的处理策略（静默？退避重试？），建议明确为静默跳过 + 指数退避。
7. **当前会话 token 汇报的时序**：§4.3 的"idle 时气泡汇报 Xk input"依赖 opencode 在 session 结束时写入聚合列——若 opencode 是逐 message 更新（进行中 cost=0 或陈旧），需在 M3 验证写入时机，否则汇报数字滞后/为零。
8. **会话进行中的 session 表不可靠**：`token_stats_current_session` 对"正在跑"的 session 可能返回 0 行，前端要处理"无记录则不出气泡"（文档只说"有 ≥1 条记录时"），隐含已覆盖，但建议写明该验证项进 M3 done 标准。

## C. 小问题 / 建议

9. **`NO_MUTEX` 连接不可跨线程**：rusqlite 只读连接若被 Tauri command 在线程池共享会出问题；建议每次查询新建只读连接（开销极小）或 Mutex 包裹，文档提一句。
10. **tokio interval 睡眠恢复**：macOS 睡眠后醒来 `tokio::time::interval` 默认 `MissedTickBehavior::Burst` 会补发所有错过的 tick，可能瞬间连弹 N 次提醒。需显式设 `Skip`。
11. **pet 窗口 220×220 vs 素材尺寸**：atlas 单帧 192×208、占位 PNG 128×128，文档没定义 canvas 缩放策略（devicePixelRatio、窗口尺寸与帧尺寸的映射）。
12. **CI 共享文件冲突**：§13 说复用 todo-lite 的 `.github/workflows/build.yml`，但该 workflow 目前按 `todo-lite-v*` tag 触发，需改为同时匹配 `pulse-pet-v*` 并区分打包产物命名，文档应写明"需修改 build.yml"。
13. **Windows 上 mode 0600 无效**：§3.1 的 token 文件权限在 Windows 无 POSIX 语义，可提一句 Windows 仅靠目录 ACL/单用户假设。
14. **AgentAdapter 职责分裂**：事件归一化在 TS、token 读取在 Rust（rusqlite），v2 加 Claude Code 时要动两端，与"只改一个文件"的表述不完全一致——POC 可接受，但建议文档承认此边界。
15. **提醒跨午夜窗口**：`start_time > end_time`（如 22:00-06:00）的语义未定义。

---

## 第二轮评估补充（2026-08-09）

### B 组补充（设计缺口，实现前需补定义）

16. **Todo 与调度器的集成通道缺失**：§5.1 调度器只消费 `reminders` 表，但 §8.3"任务到点前 X 分钟气泡提醒"未定义如何注入该调度器——是动态往 `reminders` 表插行？还是调度器另查 `todos` 表？`todos` 表也缺少 `remind_before_minutes` 字段（§8.3 说默认 5 min 可配，但模型里无处存储）。M7 前需定案。
17. **atlas 状态映射表缺失**：§6.2 定义 9 个 atlas 行（idle/running-right/running-left/waving/jumping/failed/waiting/running/review），§3.1 归一化事件有 8 种（idle/working/thinking/editing/testing/waiting-permission/error）。§6.1 只给了占位阶段的映射（waiting-permission→thinking、testing→working），M5 换 atlas 后需要完整 8→9 映射表；其中 `working`（最常见状态）没有同名 atlas 行，需明确映射到 `running` 或 `running-right` 之一（目前只是隐含推断）。

### C 组补充（小问题 / 建议）

18. **托盘左键行为反直觉**：§7.2 左键单击切换控制面板可见性。托盘惯例是左键=显示主窗口/弹出菜单，控制面板是次级窗口，不应作为左键 primary action。建议左键显示/隐藏 pet 窗口或弹菜单，面板走右键菜单项。
19. **atlas 网格尺寸兼容**：§12 风险只提了 webp→png 回退，未提社区素材网格尺寸可能非标准（8×9 / 8×11）。加载器需校验网格尺寸并定义不匹配时的处理（报错提示 / 按单帧裁剪）。

---

## 后续动作建议

- 优先修 A 组三处矛盾（会直接误导实现）。
- B 组第 4 条（状态复位）是最可能造成"宠物状态错乱"的隐性缺陷，建议在 M2 里程碑加一行验证项。
- 补充的 B16（todo→调度器通道）与 B17（atlas 映射表）分别在 M7 / M5 前定案；C18（托盘左键）实现托盘时顺手调整。
- 修订完成后可在 `DESIGN.md` 顶部加一行指向本文档的链接。
