# 事故回溯报告：Tester 误改 opencode.db 导致全量会话崩溃

- **事故编号**：INC-20260827-1033
- **关联任务**：task-pulsepet-v2-m5（R2 测试轮）
- **发生时间**：2026-08-27 10:33:17（本地）
- **报告时间**：2026-08-27 11:13（v1）；11:19（v2，补处置结果）
- **定级**：P1——全部活跃会话崩溃 + 约 72 秒会话数据永久丢失；无代码损失；用户 14 分钟内完成恢复
- **状态**：已恢复；整改措施 2/4 已落地（见第七节）

---

## 一、事故摘要

2026-08-27 10:33:17，Tester 子会话（`ses_fbf1306f9ffeZJy2FGRa7o3zXw`）在执行验收用例 **TC-M5-09（双源容错 degraded）步骤 1** 时，按用例字面指令执行 `mv ~/.local/share/opencode/opencode.db opencode.db.m5test.bak`。该文件不仅是 PulsePet 的"opencode 数据源"，**同时也是正在运行的全部 opencode 会话（含 Tester 自己、supervised-coding、Vision 子会话）的实时状态库**。改名 20ms 后数据库层雪崩，所有会话崩溃；用例设计的"测完恢复"永远无法执行——执行者已随库同灭。

## 二、时间线（本地时间；证据：~/.local/share/opencode/log/opencode.log L133936–L136333 + after-crash 库恢复会话记录）

| 时刻 | 事件 |
|---|---|
| 09:54:27 | Tester 会话启动（parent=supervised-coding 会话 `ses_fbf3fbd19ffeWrO12Sym66YPuw`） |
| 09:54–10:32 | 正常验收：cargo test、npm test、构建、mock-tauri.js DOM 测试、pp-m5-dom 截图 + Vision 核对（进行至 TC-M5-03 会话列表 cc 徽标行） |
| **10:33:09.9** | Tester 解析 mv 命令路径；权限门 `external_directory: ~/.local/share/opencode/*` 触发**询问**（per_041106a42001sMTQw9Cp6ZpW4m） |
| 10:33:17.0 | 询问放行（7 秒后）；bash 权限通配 allow 对 `mv` 无拦截 → **mv 执行** |
| 10:33:17.1 | **+20ms 首错**：Tester 自身会话 part 查询失败；随后 supervised-coding 会话同样失败 |
| 10:33:17–53 | 级联报错：EffectDrizzleQueryError（part / session 表查询连续失败） |
| 10:35:27 | `SQLiteError: disk I/O error`——旧连接 WAL/shm 与改名后路径彻底失配，run 20f2d109 死寂 |
| 10:36:35 | 用户重启 opencode（run=2c445630）；路径上无库 → **自动生成 1MB 空新库**，历史会话"消失" |
| 10:36:40–10:46 | 用户开恢复调查会话（after-crash 库中「从 opencode.db 恢复中断的会话内容」）：immutable 只读取证 m5test.bak、定位 mv 来源会话、PRAGMA quick_check 校验完整性 ok |
| 10:46:51–10:47 | 生成 `~/.local/share/opencode/restore-old-db.sh`（三重安全检查：opencode 未退出拒执行 / 防重复执行 / 文件存在性校验） |
| 10:47 | 用户完全退出 opencode → 执行脚本：空新库另存为 `opencode.db.after-crash.db` 三件套 → 1.6GB 原库归位 → 重启，**全部历史会话恢复** |

## 三、崩溃机制

opencode 使用 SQLite WAL 模式，会话的每一步（消息、工具调用 part）实时落库。主库文件被 mv 后：

1. **新连接路径**：按路径打开 `opencode.db` → 文件不存在 → SQLite 新建空库 → 表不存在 → 查询失败；
2. **旧连接路径**：连接仍持有旧文件描述符，但 WAL/checkpoint 与改名后的文件失配 → `disk I/O error`。

两条路同时断：会话进程未死，但每一步落库都报错，等于全瘫。SQLite 的"文件即数据库"特性使得文件级操作（mv/rm）等价于对运行中服务的釜底抽薪。

## 四、损失评估

| 项 | 结论 |
|---|---|
| 代码 / 仓库 | **无损**。HEAD=ca2b600 未变，工作区与 09:37 一致 |
| 检查点 | 无损（Tester 只读；事故后 supervised-coding 已补记） |
| 会话数据 | 恢复会话确认：内容完整至 **10:32:05**；**10:32:05–10:33:17 约 72 秒的消息随旧 WAL 被新库重置而永久丢失** |
| Tester 验收成果 | 39 分钟工作，验收报告未出（进行至 TC-M5-03 中段）；会话内容在恢复后的主库中完整可查（至 10:32:05） |
| 恢复成本 | 用户手工约 14 分钟（10:33–10:47）；处置正确高效：先只读取证、完整性校验、退出后脚本归位、防二次事故 |

## 五、根因分析（按层级）

1. **用例设计自指危险（根因）**：TC-M5-09 写于设计期，把 `opencode.db` 当成"PulsePet 的被动数据文件"设计了"临时改名→观察→恢复"步骤。但它同时是**执行测试的 agent 运行时自身的活库**——自指场景下"测完恢复"是伪命题：改名瞬间执行者就死了（本次 +20ms）。
2. **派工词背书了危险流程（supervised-coding 责任）**：派工词仅要求"临时改名操作测完必须恢复原状"，未识别风险、未提供替代方案、未划禁区——等于确认该流程合法。**这一层失职在 supervised-coding。**
3. **权限门双失效（系统层）**：① `external_directory` 门只问"能否访问该目录"，不呈现"要改名"的动作语义，7 秒即放行；② subagent bash 为通配 allow，`mv` 直接过。两道门没有一道能拦住破坏性动作。
4. **无沙箱隔离（系统层）**：Tester 以真实 HOME 运行，"PulsePet 的数据源"与"opencode 自身状态库"在文件系统层面是同一文件，无隔离带。

## 六、环境残留与处置（2026-08-27 11:19 用户裁定后执行）

| # | 残留 | 处置 | 结果 |
|---|---|---|---|
| 1 | nohup vite dev server（pid 41765，Tester 09:27 启动，占端口 1430） | kill | ✅ 已终止（11:19） |
| 2 | `~/.claude/projects/-private-var-folders-...-pp-v2-test-cc-sandbox/`（3 个假 jsonl + memory/，Tester 造的测试 fixture，污染真实 Token 视图） | 删除 | ✅ 已删除（11:19，projects 下仅剩两个真实项目目录） |
| 3 | `opencode.db.after-crash.db` 三件套（1MB 新库 + wal + shm，恢复调查会话留档） | **留档一周**（至 2026-09-03，审计后删） | 保留在位 |

## 七、整改措施

| # | 措施 | 层级 | 状态 |
|---|---|---|---|
| 1 | 事故记入检查点 task-pulsepet-v2-m5（轮次记录 + 遗留事项） | 流程 | ✅ 已做（11:13） |
| 2 | **TC-M5-08/09 用例安全修订**：live rename 类步骤改"用户人工执行"；agent 禁触 `~/.local/share/opencode` 与 `~/.claude`；修订注记引用本报告 | 用例文档 | ✅ 已落笔（11:19，V2-TEST-CASES.md 五、两处修订注记） |
| 3 | **Tester/Coder 派工词模板加禁区清单**（项目目录与临时沙箱外禁 mv/rm/写；`~/.local/share/opencode` 与 `~/.claude` 永禁变更） | 流程 | ⏳ 随下轮测试派工启用（supervised-coding 执行） |
| 4 | **权限加固**：opencode 配置对 mv/rm 类命令加 ask/deny 规则 | 系统配置 | ❌ **用户裁定暂不做**（2026-08-27 11:19） |

## 八、对关联任务的影响与后续

- R2 代码产物完好（ca2b600），**测试轮作废需重跑**（testerTaskId=null，round 保持 2）；
- 重跑 Tester 时启用整改 #3 禁区清单；TC-M5-08/09 实机改名步骤按修订后口径**由用户人工执行**，agent 仅观察断言；
- 本报告存档：`.opencode/incidents/INC-20260827-1033-opencode-db-rename-crash.md`；after-crash 库留档至 2026-09-03。

## 附：证据索引

- 主日志：`~/.local/share/opencode/log/opencode.log`（L133936 Tester 创建、L136108 权限询问、L136109–136113 mv 执行与首错、L136176+ 恢复会话取证）
- 恢复调查会话：`opencode.db.after-crash.db` session `ses_fbeec60acffeabCVdBP46J5H43`（「从 opencode.db 恢复中断的会话内容」）
- 恢复脚本：`~/.local/share/opencode/restore-old-db.sh`（留档）
- 检查点事故记录：`.opencode/workflows/task-pulsepet-v2-m5.md` 轮次记录「R2 测试轮事故」条目
