# 维度 6：Skill 机制（Agent Skills / 渐进式披露）

> 本维度回答：框架是否原生支持 Anthropic Agent Skills 范式（SKILL.md + frontmatter + progressive disclosure 渐进式披露：name/description 常驻提示 → 正文按需载入），封装格式、触发机制、来源与版本管理、以及 skill 与工具系统的关系。这是 2025 下半年才兴起的 capability，却是 17 家里扩散最快的：**12 家已有正式抽象**（11 ✅ + claude-sdk 的开关式形态），4 家 ❌（langchain、langgraph、llama_index、spring-ai 由生态或后继框架承载），1 家 🔶（openai-agents 仅参数透传）。Java 生态罕见地与 Python 同步甚至超前（langgraph4j/spring-ai-alibaba/agentscope-java 全有，而 Python 侧 langgraph/spring-ai 没有）。

## 6.1 总览矩阵

| 框架 | 评级 | 一句话实现 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|
| agent-framework | ✅ | core 内最完整抽象（ADR-0037）：Skill/SkillFrontmatter（含 license/compatibility/allowed_tools）+ File/Inline/MCP 三源 + 可组合 Source + {skills} 指令模板 + 三工具（load_skill/read_skill_resource/run_skill_script） | python/packages/core/agent_framework/_skills.py#Skill(:619)/#SkillFrontmatter(:683)/#MCPSkill(:4339)；docs/decisions/0037-agent-skills-design.md |
| deepagents | ✅ | Anthropic 规范完整实现：SKILLS_SYSTEM_PROMPT 四步渐进披露（read_file limit=1000 读全文）+ base→user→project→team 多源分层 last-wins + 10MB 防护 | libs/deepagents/deepagents/middleware/skills.py#SKILLS_SYSTEM_PROMPT(:735)/#MAX_SKILL_FILE_SIZE(:141)；middleware/skills.py:54-73（分层） |
| adk-python | ✅ | SkillRegistry + SkillToolset 渐进披露五工具（List/Search/Load/LoadResource/**RunSkillScript 沙箱执行**），README 明示 experimental | src/google/adk/tools/skill_toolset.py#SkillToolset(:1319)/#RunSkillScriptTool(:960)；skills/README.md（WARNING: experimental）；skills/skill_registry.py#SkillRegistry(:26) |
| adk-java | ✅ | SkillSource（classpath/local/memory）+ Frontmatter 解析 + SkillToolset 三工具渐进披露；默认指令提到 run_skill_script 但工具未实现（见 6.2-C） | core/.../skills/{SkillSource,Frontmatter}.java；tools/skills/SkillToolset.java#getTools（仅 List/Load/LoadResource 三工具） |
| langchain4j | ✅ | 官方 langchain4j-skills 模块（@Experimental）：name/description 常显 + activate_skill 工具载入正文（ACTIVATED_SKILL_ATTRIBUTE）+ read_skill_resource + FileSystem/ClassPath 双 Loader，javadoc 引 agentskills.io 规范 | langchain4j-skills/src/main/java/dev/langchain4j/skills/Skill.java；ActivateSkillToolExecutor.java(:15/:42)；experimental/langchain4j-experimental-skills-shell/ |
| langgraph4j | ✅ | Java 图框架罕见内置：core SkillParser 解析 front-matter + 集成层 SkillInjector **工具调用触发**（工具成功→激活技能 id 入 State.ACTIVE_SKILLS→下轮 call model 注入 body，可 UnloadTarget 卸载） | langgraph4j-core/.../agent/skill/SkillParser.java#getFrontMatter；langchain4j/langchain4j-agent/.../SkillInjector.java(:32-100)；spring-ai-agent 侧 SkilledReactSubAgent/SkillResource |
| agentscope | ✅ | Claude 式两级渐进披露：技能清单（名/描述/目录）注入系统提示（get_skill_instructions）+ SkillViewer 只读工具按需读全文；技能 hub（ClawHub）+ workspace seed | src/agentscope/tool/_toolkit.py#get_skill_instructions(:431)；tool/_builtin/_skill.py#SkillViewer(:18, is_read_only=True)；app/hub/_skill/、skill/（LocalSkillLoader） |
| agentscope-java | ✅ | SkillBox 渐进披露（load_skill_through_path：资源缺失时自动回列可用资源）+ curator/usage 中间件 + FileSystem/Classpath 核心 + git/mysql/pg 仓库扩展；仓库根本身是一份 SKILL.md | agentscope-core/.../skill/SkillBox.java#registerSkillLoadTool(:629)；harness/.../skill/curator/；agentscope-extensions-skills/（3 仓库）；SKILL.md（根，frontmatter 含 license/compatibility） |
| crewai | ✅ | skills/ 全套（registry/loader/parser/validation/cache/events）+ **三级 DisclosureLevel**（METADATA/INSTRUCTIONS/RESOURCES）+ frontmatter metadata.version 版本 pin + SkillTool 工具化 + CLI 子命令 + Plus 平台分发 | lib/crewai/src/crewai/skills/models.py#DisclosureLevel(:25-40)；registry.py#_load_matching_skill(:183)；tool.py#activate_skill；lib/cli/src/crewai_cli/skills/ |
| dify | ✅ | 采纳 Anthropic 约定的 Skill 包管理：.zip/.skill 校验（SKILL.md 必含、zip-slip/200MB/1MB/5000 条目上限）+ 草稿/发布 SkillVersion（hash 审计）+ Agent 绑定；执行侧 dify-agent 运行时按提及拉取（见 6.2-E，档案 ⚠️ 已核验解决） | api/services/agent/skill_package_service.py；api/models/skill.py#SkillVersion；dify-agent/src/dify_agent/layers/config/layer.py#DifyConfigLayer |
| spring-ai-alibaba | ✅ | graph-core skills：SkillMetadata（注释明言 "Claude-style"，含 allowedTools）+ SkillRegistry（classpath/filesystem，reload/search/disable）+ SpringAiSkillAdvisor 渐进披露（元数据进 system prompt + read_skill 工具） | spring-ai-alibaba-graph-core/.../graph/skills/SkillMetadata.java(:24/:41/:94-118)；SpringAiSkillAdvisor.java(:47-49/:250)；AbstractSkillRegistry.java(:80-105) |
| claude-agent-sdk-python | ✅ | options.skills 单一开关（"all"/名单）：SDK 注入 `Skill`/`Skill(name)` 进 allowedTools 并默认 setting_sources=["user","project"]；SKILL.md 发现与渐进披露在 CLI 侧【文档】 | src/claude_agent_sdk/_internal/transport/subprocess_cli.py#_apply_skills_defaults(:519)/#_validate_skill_name；types.py#ClaudeAgentOptions.skills |
| openai-agents-python | 🔶 | 无 SDK 级 Agent Skills 抽象；仅 ShellTool 参数接受 skills 元数据（ShellToolSkillReference/ShellToolInlineSkill）透传给托管 shell 容器 | src/agents/tool.py#ShellToolLocalSkill(:1271)/#ShellToolSkillReference(:1279)/#ShellToolInlineSkill(:1295) |
| langchain | ❌ | langchain 1.x 全文无 skill/渐进披露抽象；官方实现在 deepagents 仓库（SkillsMiddleware 基于 LangGraph） | libs/langchain_v1 全文 rg 'skill' 零命中（二次核验确认）；替代 = deepagents 生态组合 |
| langgraph | ❌ | 核心与 prebuilt 零命中；Anthropic Skills 范式由 deepagents 在其上实现 | libs/langgraph + libs/prebuilt rg 'skill' 零命中（二次核验确认） |
| llama_index | ❌ | 全仓无 SKILL.md/渐进加载概念（flare 提示词里的 "Skill 1." 只是文案） | llama-index-core rg 'skill' 仅 query_engine/flare/base.py:47 提示词字符串（二次核验确认）；替代 = ObjectRetriever 工具检索 |
| spring-ai | ❌ | 无 skill/渐进披露抽象；最接近的 ToolSearchTool 是工具 schema 级发现，非指令文件包 | spring-ai-tool-search-tool/.../ToolSearchTool.java；spring-ai-model/core rg 'skill' 零命中（二次核验确认） |

## 6.2 实现方式深析

### A. 封装格式：frontmatter 规范的谱系

所有实现都对齐 Anthropic 基线（SKILL.md 必含、YAML frontmatter、name/description），字段扩展程度分层：

- **基线 + 校验**：deepagents 显式实现 agentskills.io 约束——name≤64、description≤1024、目录名与 name 一致（middleware/skills.py:146-149/:147-148）；dify 校验 name 模式 `^[a-z0-9]+(?:-[a-z0-9]+)*$`（skill_package_service.py:35）。
- **扩展元数据**：agent-framework `SkillFrontmatter` 最宽——name/description/license/**compatibility（≤500 字符）**/**allowed_tools（空格分隔的预批准工具）**/metadata dict（_skills.py:683-729）；agentscope-java 仓库根 SKILL.md 实地示范了这套（license: Apache-2.0、compatibility: "Designed for Claude Code and Cursor"、metadata.framework）——**用自身规范自举**，是 17 家里唯一「仓库自己就是一个 skill」的。
- **工具授权字段**：spring-ai-alibaba `SkillMetadata.allowedTools`（List\<String\>，SkillMetadata.java:41）——skill 可以携带自己的工具白名单，与 agent-framework 的 allowed_tools 同思路（skill → 工具权限的映射）。
- **版本字段**：crewai 约定 `metadata.version`（registry.py:183-209：声明版本不满足 pin 则拒载）；dify 用数据库版本表而非 frontmatter。

### B. 渐进式披露（progressive disclosure）的五种触发机制

这是各框架差异最大的设计点——「从 name/description 到正文」这一步由谁驱动：

1. **专用工具触发（主流，8 家）**：agent-framework（ADR-0037 明确三工具 `load_skill(skillName)` 返回全文、`read_skill_resource` 读附属资源、`run_skill_script` 执行脚本——且脚本工具只在有技能含脚本时才广告给模型）；adk-python（五工具：ListSkills/SearchSkills/LoadSkill/LoadSkillResource/RunSkillScript，:209/:240/:304/:398/:960）；adk-java（三工具，默认指令强制「MUST use load_skill 先读再执行」）；langchain4j（`activate_skill` 返回 skill.content() 并置 ACTIVATED_SKILL_ATTRIBUTE 属性、`read_skill_resource` 读资源）；agentscope-java（`load_skill_through_path`，资源找不到时自动返回可用资源清单+SKILL.md 优先）；crewai（SkillTool，activate 参数控制披露级别）；claude CLI（`Skill` 工具）。
2. **通用文件读取触发（无专用工具）**：deepagents 不加新工具——技能清单进 system prompt 后，模型用现有 `read_file(path, limit=1000)` 读 SKILL.md 全文（SKILLS_SYSTEM_PROMPT:745-763 四步教学）。这与 Claude Code 同构，且「技能正文住在虚拟文件系统里」使 skill 与普通文件共享同一后端协议；agentscope 的 SkillViewer 本质同路（只读工具读 markdown 全文 :127 返回 TextBlock）。
3. **图状态触发（langgraph4j 独有）**：`SkillInjector` 把披露做进图语义——工具成功结果 → resolver 解析激活技能 id → `Command#update()` 写入 `State.ACTIVE_SKILLS` channel → 下一轮 call model 节点把 body 经 `ConversationContextPolicy` 注入（类注释强调 "never written into Graph State"，正文永不落状态、只在发模型瞬间物化）→ 可配 `UnloadTarget` 在 call model 后自动卸载。技能激活成为**可 checkpoint、可回放的状态迁移**，这是图框架才能给出的形态。
4. **提及触发（dify-agent，档案 ⚠️ 二次核验解决）**：`DifyConfigLayer`（dify-agent/src/dify_agent/layers/config/layer.py）在 config 上下文常驻 prompt-safe 技能摘要（DifyConfigSkillConfig：name/description/size/mime）；当 `mentioned_skill_names` 出现（技能被提及），运行 `dify-agent config skills pull <name>` shell 命令把归档物化到 /workspace/.dify_conf/skills/<name>，再把拉取输出渲染成 "Loaded mentioned skills:" 段落进提示上下文（:117-127/:232-234）。拉取即披露，无工具往返。
5. **声明式开关（claude-sdk）**：`options.skills="all"` → 注入裸 `Skill` 到 allowedTools；名单 → 注入 `Skill(name)` 规则；同时默认 `setting_sources=["user","project"]` 让 CLI 能发现已安装技能（_apply_skills_defaults，二次核验 :519-560 全文）。名字经 `_validate_skill_name` 严校验（括号/通配/控制字符/BOM 全拒）因为它要进 CLI 的规则文法。注意 skills 是**上下文过滤器而非沙箱**：未列出的技能对模型隐藏且被 Skill 工具拒绝，但文件仍可被 Read/Bash 读到（types.py:2230-2250 docstring 自述）。

披露层数：多数两家为两级（元数据→正文）；crewai 三级（METADATA=1 / INSTRUCTIONS=2 / **RESOURCES=3**——第三级连资源目录都编目披露，models.py:25-40）；agent-framework 隐式三层（name/desc → body → resource/script 各自再按需）。

### C. 来源（source）与分发：从本地目录到 MCP

- **本地文件系统/类路径是基线**：deepagents 四层分层 `/skills/{base,user,project,team}/` 同名 last-wins（middleware/skills.py:54-73，路径全走 BackendProtocol 与存储后端正交）；langchain4j FileSystem/ClassPath 双 Loader；adk-java ClassPath/Local/InMemory 三源；spring-ai-alibaba classpath/filesystem 两实现。
- **agent-framework 的 Source 代数最完整**：FileSkillsSource/InlineSkill（代码内联技能）/**MCPSkill/MCPSkillsSource（技能经 MCP 协议分发——17 家唯一）**，再叠加 Aggregating/Caching/Deduplicating/Filtering 四个组合子（_skills.py:3812-4096）；.NET 侧对等实现于 Microsoft.Agents.AI.Mcp/Skills/。
- **数据库/远端仓库**：agentscope-java 独有 git/mysql/postgresql 三个 SkillRepository 扩展；adk-python 有 integrations/skill_registry（GCP 托管源）。
- **市场/平台**：crewai（Plus 平台缓存双源 + `download_skill` + CLI `crewai skills` 安装/列表）；agentscope（ClawHub 技能市场 + workspace seed_skills）；dify（工作区上传 .zip/.skill 包）。

### D. 版本管理与安全防护

- **版本管理只有两家成体系**：dify（`SkillVersion` 不可变发布快照，hash_code 含技能身份+版本号+内容摘要供下游审计，草稿可改/发布不可变/Agent 绑定读绑定表；二次核验 models/skill.py:54-65 UniqueConstraint(skill_id, version_number)）；crewai（frontmatter metadata.version + `versions_match` pin 语义）。其余（agent-framework 的 compatibility 字段、agentscope 的 updated_at）只算元数据不算版本治理。
- **防护共识**：体积上限（deepagents SKILL.md 10MB + 告警条数/长度封顶；dify 归档 200MB/单个 SKILL.md 1MB/5000 条目 + zip-slip 路径穿越防护）；名称注入防御（claude-sdk 名单严校验进规则文法）；执行隔离（adk-python `_SkillScriptCodeExecutor` 沙箱执行技能脚本 :628；agent-framework FileSkillScript 支持用户自定义 executor）。

### E. 与工具系统的关系：三种挂接方式

1. **skill 作为 toolset 暴露**：adk 双语 SkillToolset 实现 BaseToolset（自然进 ToolPredicate 过滤体系）；langchain4j activate_skill/read_skill_resource 是 ToolExecutor；agentscope-java SkillBox.registerSkillLoadTool 注册进 Toolkit 的 "skill-build-in-tools" 分组。
2. **skill 影响工具授权**：agent-framework frontmatter allowed_tools（技能激活即预批准工具）；spring-ai-alibaba SkillMetadata.allowedTools；claude-sdk `Skill(name)` 本身就是 allowedTools 规则文法的一等公民。
3. **skill 正文注入走上下文工程而非工具**：langgraph4j SkillInjector 经 ConversationContextPolicy（不占工具面）；agentscope get_skill_instructions 拼 system prompt；spring-ai-alibaba SpringAiSkillAdvisor（advisor 链上注入，:250 生成「MUST use read_skill tool」清单）；agent-framework SkillsProvider 是 ContextProvider，注入 `{skills}` 占位符（_skills.py:1872-1908）。

### F. 二次核验发现：adk-java 的「幽灵工具」

adk-java `SkillToolset` 默认系统指令第 4 条让模型「Use `run_skill_script` to run scripts」（SkillToolset.java:59），但 `getTools` 只注册三个工具（ListSkillsTool/LoadSkillTool/LoadSkillResourceTool，:77-79），全仓 grep 无 RunSkillScriptTool——**指令引用了不存在的工具**。adk-python 侧该工具真实存在且有沙箱执行器（:960/:628）。这是 Python→Java 移植时的半成品痕迹，模型遇到 scripts/ 目录技能时只能走 bash 绕行（指令自身也说 scripts "run via bash"）。

## 6.3 跨语言对齐

| 对 | Python 侧 | Java 侧 | 差异要点 |
|---|---|---|---|
| langgraph ↔ langgraph4j | ❌：核心与 prebuilt 零 skill 抽象；范式由另仓 deepagents（SkillsMiddleware 基于 LangGraph）实现 | ✅：core SkillParser + 集成层 SkillInjector（工具触发→ACTIVE_SKILLS channel→下轮注入，UnloadTarget 卸载）+ spring-ai-agent 侧 SkilledReactSubAgent | **Java 反超**（档案结论复核成立）：主仓 Python 把 skill 让给 deepagents 生态，Java 把渐进披露做进核心图语义；形态也相反——LangGraph 系的「文件读取式」vs Java 的「状态迁移式」 |
| adk-python(2.9) ↔ adk-java(1.9) | 五工具含 RunSkillScriptTool + `_SkillScriptCodeExecutor` 沙箱；README 明示 experimental；integrations/skill_registry GCP 托管源 | 三工具（无脚本执行工具，但默认指令仍提及 run_skill_script——幽灵工具）；ClassPath/Local/InMemory 三源 | 骨架对齐（SkillSource + SkillToolset + 强制 load_skill 先行）；Python 多脚本沙箱执行与托管源；两侧都无版本管理 |
| agentscope ↔ agentscope-java | 两级披露：清单进提示（get_skill_instructions 支持按激活工具组过滤）+ SkillViewer 只读工具；LocalSkillLoader + ClawHub 市场 + workspace seed | SkillBox（load_skill_through_path + 资源缺失自动回列）+ SkillCuratorMiddleware/SkillUsageMiddleware（策略化策展）+ git/mysql/pg 仓库扩展 + 根 SKILL.md 自举 | **已对齐/Java 仓库后端更多**：Python 强在市场（hub）与 workspace 集成；Java 强在仓库矩阵（git/mysql/pg）与 curator/usage 中间件（技能使用分析——Python 无对应物） |

## 6.4 取舍与趋势

1. **扩散速度史上最快、但成熟度标记诚实**：Agent Skills 规范落地仅一年，12/17 已有原生抽象；其中 langchain4j（@Experimental）、adk-python（README WARNING: experimental）、agent-framework（ADR-0037 status: proposed）都主动打实验标签——框架们在「抢占范式」与「承诺稳定性」之间普遍选择前者加标签。
2. **触发机制的设计空间已被探满**：专用工具（8 家）→ 通用 read_file（deepagents/agentscope，最少新增面）→ 图状态迁移（langgraph4j，可 checkpoint）→ 提及拉取（dify-agent，无工具往返）→ 规则文法开关（claude-sdk）。方向一致的内核是「正文永不默认进 prompt」——连注入点都开始分化（system prompt vs advisor 链 vs ConversationContextPolicy vs 状态物化）。
3. **skill 与工具权限的融合是最值得跟踪的方向**：agent-framework 的 allowed_tools frontmatter、spring-ai-alibaba 的 allowedTools、claude 的 `Skill(name)` 规则——三家独立演化出「技能携带工具授权」的语义，skill 正在从指令包变成**能力单元（instructions + resources + scripts + tool grants）**。
4. **分发渠道决定生态位**：本地目录（全员基线）→ 数据库/git 仓库（agentscope-java，企业自托管取向）→ MCP 分发（agent-framework 独家，技能成为 MCP 一等资源）→ 云托管 registry（adk-python GCP）→ 平台市场（crewai Plus/agentscope ClawHub）。dify 的「包管理 + 不可变版本」是唯一把 skill 当制品（artifact）治理的——版本管理（dify 的 hash 审计、crewai 的 version pin）整体仍是最薄弱环节。
5. **skill 是 Java 框架罕见的「不落后反超前」维度**：langgraph4j/spring-ai-alibaba/agentscope-java/adk-java 四个 Java 框架全部有 skill 抽象，而对应 Python 生态的 langgraph/spring-ai 没有——因为 skill 本质是「文件约定 + 提示工程」，不依赖快速迭代的运行时特性，Java 生态第一次能与 Anthropic 范式同周落地。
6. **无 skill 框架的替代物各不相同**：langchain→deepagents 组合（SkillsMiddleware 就是官方答案）；langgraph→同上；llama_index→ObjectRetriever 检索式工具选择（schema 级按需披露，缺指令文件语义）；spring-ai→ToolSearchTool（同为工具级发现）；openai-agents→托管容器技能参数（ShellTool skills 元数据，能力在 OpenAI 服务端）。共同点：都用「按需加载」思想补位，但都没有「SKILL.md 约定 + frontmatter 规范」的互操作格式。
