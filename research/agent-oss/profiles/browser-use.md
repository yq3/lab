# browser-use 解剖档案

> 基线：~/develop/opensource/browser-use @ 50f205533 (2026-09-09)；canonical browser-use/browser-use；MIT（Cloud 服务闭源）。本档案属 D 组快扫：火力在维度 2（DOM 提取-行动循环）与维度 6（动作空间 + 敏感输入不经过 LLM 的机制），维度 5 看 watchdog 体系。当前版本重大演进：**已弃 Playwright，改走自研 CDP 客户端 `cdp_use`**（`browser/session.py` 顶部 import），网上旧架构资料（Playwright DOM snapshot、controller/service.py 分层）已过时。无 agent-framework 交叉引用（自研 loop）。

## 1. 产品定位与形态（简）

- LLM 浏览器自动化库（pip 安装、Python API `Agent(task, llm, browser_session).run()`）；Cloud 为闭源托管服务（api.browser-use.com，Session=15min 上限、Browser Profile 持久化登录态、按任务计费，【文档】`CLOUD.md`）。另提供 MCP server（`browser_use/mcp/`）与 SDK 同步事件流（`agent/cloud_events.py` 向 Cloud UI 推 session/task/step 事件）。OSS 库内**无 workflow 编排层**（旧 `browser_use.workflow` 已不存在，grep `class Workflow` 全仓无命中 ❌；编排型 Workflow 是 Cloud 侧产品概念）。

## 2. Agent 执行架构 ★重点

- **感知-行动循环**（`agent/service.py`，4100+ 行单类 `Agent`）：`run(max_steps)` 主循环 → `_execute_step` = `_prepare_context`（取浏览器状态摘要）→ `_maybe_compact_messages`（历史压缩）→ `_get_next_action`（LLM 结构化输出）→ `_execute_actions`（`multi_act` 执行动作队列）→ `_post_process`。熔断：`max_failures` 连续失败停机、`max_steps` 上限、步超时 `step_timeout`。
- **DOM 序列化管线**（`dom/service.py#DomService.get_serialized_dom_tree`）：CDP DOM snapshot + 完整无障碍树（`GetFullAXTree`）合并为 `EnhancedDOMTreeNode`（跨域 iframe 懒加载）→ `DOMTreeSerializer.serialize_accessible_elements`（`dom/serializer/serializer.py`）四步：简化树（可点性检测 `ClickableElementDetector`）→ **paint-order 过滤遮挡元素** → 剪掉无信息父节点 + bbox 过滤 → 给可交互元素分配 `[index]`。输出缩进文本树，交互元素行首 `[index]`、新元素加 `*` 前缀。
- **索引稳定性**：`selector_index` 从 CDP `backend_node_id` 派生（`serializer.py#_allocate_selector_index`，冲突时分配合成索引），且 `get_serialized_dom_tree(previous_cached_state)` 把上一状态传入 serializer 复用索引——LLM 引用的元素编号跨步骤尽量不漂移；`multi_act` 执行前快照 `selector_map`，动作后校验，失效即报错让 agent 重取状态（`tools/service.py` input 分支）。
- **多步动作队列 + 双层页面变更守卫**（`agent/service.py#multi_act`）：单步 LLM 可输出动作列表顺序执行；①静态声明——注册时标 `terminates_sequence=True` 的动作（navigate/search/switch_tab）后自动丢弃剩余队列；②运行时检测——每动作后比对 URL 与焦点 target，变化即截断。`done` 只允许单动作。防"对陈旧 DOM 执行计划"。
- **多 tab**：tab 即 CDP target；`browser/session.py#BrowserSession` + `session_manager.py#SessionManager` 管理多 target 多 CDPSession；LLM 视角：状态里 `Tab {target_id[-4:]}: url - title` 列表（`agent/prompts.py` L296），动作 `switch_tab`/`close_tab` 用 4 字符 tab_id（`tools/views.py#SwitchTabAction`）。
- 输出结构 `AgentOutput`（`agent/views.py`）：`evaluation_previous_goal`/`memory`/`next_goal`/`plan_update` + `action: list[ActionModel]`——自省式字段强制模型逐步评估（结构化输出约束 required 字段）。
- 会话恢复：`AgentHistoryList` JSON 持久化 + `rerun_history`/`load_and_rerun` 重放纠错（含索引重映射 `_update_action_indices`、菜单展开重放 `_reexecute_menu_opener`）。

## 3. 技术底座（简）

- Python；自研 CDP 客户端 `cdp_use`（弃 Playwright）；LLM 层 `browser_use/llm/` 按 provider 适配（openai/anthropic/google/azure/…/litellm 兜底），Pydantic 结构化输出。消息历史 `MessageManager`：超阈值触发 LLM 摘要压缩（`message_manager/service.py`，`compaction_count`/`last_compaction_step` 状态）。

## 4. 状态与持久化（简）

- 运行状态在 `AgentState`（n_steps/consecutive_failures/paused/stopped）；历史 = `AgentHistoryList`（每步 model_output/result/浏览器状态摘要/截图路径），`save_to_file` 落 JSON 且可选敏感值过滤；token 成本经 `token_cost_service` 汇总。无服务端会话存储（库形态）；Cloud 侧才有任务持久化【文档】。

## 5. HITL 与风控（简）

- **无内置审批门**：`run()` 只有 `on_step_start/on_step_end` 钩子 + `pause()/resume()/stop()`（含 SIGINT 一次暂停、两次强退的信号协议，`agent/service.py` SignalHandler）——审批要靠宿主在钩子里实现 ❌内置。
- 风控靠 **watchdog 总线**（`browser/watchdogs/`，14 个）：`security_watchdog.py` 在 navigate 前校验 `allowed_domains`/`block_ip_addresses`，拦截后跳 about:blank，重定向后二次校验；另有 captcha/popups/downloads/permissions/crash/dom 等 watchdog 挂在 session 事件总线上。域白名单与敏感数据联动校验（见维度 6）。
- `DoneAction.text` 的 prompt 约束反幻觉：只准报告本会话直接观察到的内容（`tools/views.py#DoneAction`）。

## 6. 工具与业务系统集成 ★重点

- **动作空间 = Pydantic schema 联合**：每个动作一个 `BaseModel`（`tools/views.py`：click[index|x,y]/input_text/navigate/scroll/send_keys/switch_tab/close_tab/upload_file/save_as_pdf/extract/search_page/find_elements/done…约 25 个），`registry.create_action_model` 生成 Union 动态类型，**按当前页 URL 过滤可用动作**（动作可注册 `domains=[...]`，`agent/service.py#_update_action_models_for_page` 每步重建输出模型）。
- **自定义工具**：`@tools.registry.action(description, param_model, domains, terminates_sequence)` 装饰器（`tools/registry/service.py#action`），函数签名注入 `browser_session`/`file_system`/`page_extraction_llm` 等特殊上下文；skills 亦按此注册为动作（`agent/service.py#_register_skills_as_actions`）。
- **敏感输入不经过 LLM（核心亮点）**：构造 `Agent(..., sensitive_data={domain_pattern: {key: value}})`。①LLM 只看到**键名占位符清单**（按当前页 URL 域匹配过滤，`message_manager/service.py#_get_sensitive_data_description`），指示用 `<secret>key</secret>` 标签引用；②执行时 `registry/service.py#_replace_sensitive_data` 递归替换 `<secret>` 标签为真值——**只有当前 URL 域匹配的 secret 才可替换**，支持 `bu_2fa_code` 后缀键现场生成 TOTP；③input 动作回给 LLM 的消息只写 `Typed <password>`（`tools/service.py` L816-822），真值不进入消息历史；④历史压缩、`save_to_file` 均再做一遍敏感值 redaction（`agent/views.py`、`utils.py#redact_sensitive_string`）；⑤配置了 sensitive_data 但未锁 `allowed_domains` 时启动即警告提示注入风险，且校验 domain pattern 被白名单覆盖（`agent/service.py` L533-580）。
- 凭据/登录态：本地 `BrowserProfile`（cookies/localStorage 落盘）或 Cloud Profile Sync（上传本地登录态）【文档】。

## 7. 部署与产品化（简）

- 库形态嵌宿主进程；`browser_session(cdp_url=...)` 可接本地或 Cloud 远程浏览器（`browser/cloud/`）；observability：Laminar span + telemetry（可关）；沙箱执行 `sandbox/`（容器内跑浏览器）。Cloud 边界清晰：OSS=库+CDP 控制协议，闭源=托管浏览器/计费/Profile/判官（judge）【文档】。多租户/配额全在 Cloud 侧，OSS ❌。

## 8. 对本项目的适用性

- **可借鉴**：①**`<secret>` 占位符机制是对财务场景最有价值的样板**——LLM 全程只见占位符，真值在工具执行层域限定替换、回注消息前脱敏，等价于"密码不出密管、审计只见掩码"，可直接移植为 Java 侧凭据引用协议（`tools/registry/service.py#_replace_sensitive_data` + `message_manager` 占位符注入）；②按页/按域动态裁剪动作空间（动作级 `domains` 白名单 + 每步重建输出 schema）——财务 agent 可按用户权限/场景裁剪工具面；③双层页面变更守卫（静态 `terminates_sequence` + 运行时 URL/焦点比对）是"计划失效即截断"的通用模式；④ watchdog 事件总线把安全策略（域/IP 拦截、重定向二次校验）从动作实现中解耦。
- **不可迁移**：浏览器领域特有（DOM 序列化/CDP/索引稳定性）；单机库无审批/租户/持久化服务端语义；Cloud 侧编排与判官闭源不可引证。
- **避坑**：审批合规不能指望其内置（只有钩子与暂停）；`sensitive_data` 旧格式 `{key: value}` 全域暴露，务必用域限定新格式并配 `allowed_domains`；结构化输出对 empty-object 敏感的模型需 `NoParamsAction` 这类兼容补丁（`tools/views.py`），Java 侧选型 JSON-schema 兼容模型时同理。
