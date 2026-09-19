# 专项评审：新手友好度 + PyCharm 触点 + 命令双端 + 生态概念与图形化对照（2026-09-19）

> **修复进度（2026-09-19 同日，R0–R3 全部落地，验证全绿）**：
> **R0** ✅ P1（L3.4 Step 3 补 clone+checkout，count_loc.py 加 `expanduser()`）；L3.2/L3.3 hints 补 `cd exercises`；L4.1 算式分母 5.5→5.0（讲义与 step1_blend.py 同步）；L4.3 七查表删重复行；L3.7 结尾改「先里程碑后 L3.8」；unit5 里程碑重验五连 `python3`→`uv run python`；handbook README 两处 `python3`+`&&` 双修。
> **R1** ✅ L0.1 扩容：虚拟环境 101（.venv / activate 为何从不需要 / uv run 机制）+ pip↔uv 身世段 + ruff/Astral 身份 + .python-version、[tool.*]、wheel、元组、@commit 记法 gloss + site-packages gloss（L1.1）；生态件身份 P2×10（token / JSON-RPC / ChatOpenAI / FastAPI / uvicorn / ASGI / unit5 README 拆句 / self 桥 / **dict / eval 表）+ 口径失真 5 条 + 内部语汇与超载句 + P3 五组约 120 处（5 分片 agent 并行 + 主代理补漏：L3.7 服务数口径自洽、六段式×5 里程碑、宪法×6、三态全绿×4、HITL gloss）；cp 行内 Windows 注 ×3、L4.1 export PowerShell 对照块、L1.1 转写块 uv 化、L4.x clone 补 checkout。
> **R2** ✅ IDE 侧栏 36 处（`> **IDE 侧…**` blockquote 定式，覆盖 §5.1 全部 18 个高优先级 + 中优先级主体）；L0.1 Step 7 重写为 PyCharm 四步 + VS Code 三步双 checklist + 终端↔IDE 全量对照表；L1.2 Pylance 独占假设改双 IDE（表行 + Step 4）。
> **R3** ✅ check_lesson 30 课全 PASS；改码三课（L3.4 / L4.1 / L4.3）three_state 全过（含 ruff format --check）；handbook 44 页重建通过；CURRICULUM §6「平台中立」增补（IDE 侧栏定式 / 仓库根脚本 uv 化 / `~` 双端交代）+ L0.1 明细行同步；AGENTS §8 演进锚点记档。
> **独立复审轮（同日，只读评审按宪法八维度复核全部改动）**：结构性合宪——受众红线 / 六段式写作契约 / 平台中立主线 / 端点中立 / 侧栏零入代码围栏 / 知识点登记制 全 PASS（正面清单：虚拟环境 101 单段四合一、「验收判据永远是终端三命令」原则句、L1.1 侧栏＝陷阱对齐标杆、L2.5 子进程断点防困惑点等，下轮勿改回）。抓出 **3 处 P1 已修**：① L3.7「默认全量约 21 个服务」错数——按本课 pyyaml 口径在锚定 commit 实测为 16（常驻 13 + db_postgres/api_websocket/weaviate），并删悬空的「逐档账目见…」指针；② L2.5「同目录仍留着的 fastmcp.py 活化石」为未验证断言——gh api 全树证实该 commit 无任何 fastmcp 路径，改写为真话「旧路径已无残留，网上 `from mcp.server.fastmcp` 老教程全部失效」；③ L0.1「Astral 官方 Ruff 插件」归属错误——Marketplace 的 Ruff 插件系 koxudaxi 社区维护（Astral 官方编辑器支持仅 VS Code 扩展），改「社区维护——ruff 官方文档指路的那款」并给 format 行补「插件设置启用」前提与双端快捷键。**P2 已修**：unit2 README「milestone 给了工具」假指针→改指 L3.4 的 count_loc.py；L3.4/L4.1/L4.2 三处 clone 块补 `mkdir -p` 与目标路径，与 unit3 README 克隆约定对齐。**P3 顺手修**：五处 mac-only 快捷键补 Windows 对照、L3.4 侧栏移出冒号断点、L5.2 双「先给」、unit4 milestone 毕业态镜像句白话化、L5.3 drizzle 破折号叠逗号。复验：check_lesson 30 课 PASS、handbook 重建通过。**教训入册：评审报告自身的建议也要过宪法验证（量化复现 / 锚点复核 / 事实核查）——②③ 两处 P1 正是照抄本报告建议、未做独立验证引入。**
> **遗留（下轮可选）**：L4.2 code/ 两个 docstring 的「dimensions 官方映射」旧词（涉共享件对版未单动）；unit5 三个 pyproject 注释里的「宪法『三态全绿』」（作者侧注释，不进学员主线）；共享件 docstring 里的「宪法」（test_contract/mock_tools 五课副本、tablegen——按对版纪律下轮同灌）；exercises 文件「验收口径」×4；L1.6:265 SSE / L2.1:16 ReAct 首现裸用（gloss 落在后一课）；L1.3/L1.8/L1.9 三处侧栏位于命令块与输出块之间（可平移到输出后）；L0.1 对照表可补一行「无 GUI 对应」诚实项；unit3 milestone「复制到本目录根」措辞；评审中判定低价值未动的少量 P3（L4.2:14 deep 括注、L3.7:331 课次考古、L3.8 CURRICULUM §7 内联、L5.1:52 孤儿词条、L5.2:110 单线程括注、L4.3:82 fail-closed 指路）。

> **背景**：用户四个审核点——① 叙述风格对 Python 新手（受众红线：Java 熟、Python 略懂）是否友好，是否还有「自顾自讲新手不懂的知识点」；② 日常开发在 IDE（PyCharm）里，而讲义全程 `uv run` 命令行，希望适时补充 PyCharm 操作；③（补充轮 1）讲义命令是否同时照顾 Windows 与 macOS；④（补充轮 2）Python 生态的基础概念（如 `.venv/` 是什么、ruff 是什么）是否给新手讲透，以及**各个命令行操作**是否有对应的 PyCharm 图形化操作。
>
> **方式**：①②由 8 个分片并行精读全部 34 份讲义（30 课时 + 6 单元页/里程碑，≈12,600 行），以「Java 资深、Python 略懂学员按课序通读」视角审计；③由主代理用 fence 解析脚本扫描全部代码块的 6 类平台敏感模式并逐处人工核对；④由主代理对七组生态关键词（activate / pip / .venv / site-packages / wheel / .python-version / Astral）做全书 grep 取证，并联网核实 PyCharm 的 uv 图形化能力现状。全部最重指控逐条回原文抽查实锤，PyCharm 与平台事实另做联网/本机核查。
>
> **与 [2026-09-18 通读评审](./2026-09-18-readthrough-review.md) 的关系**：那轮修的是课间叙事，其修复项经本轮 grep 复验**全部到位**；本轮换镜头专查四件上轮没覆盖的事。两轮问题集基本不重叠。

## 0. 结论先行

1. **新手友好度整体成立，无大面积「自顾自」**。Java 桥是体系化执行的（登记制、四段式、对照表纪律在 L2.2/L4.1/L5.3 等课执行极稳）。残留问题共 ≈130 条：**P1×1、P2×29、P3×100**，集中在四类：生态件/行话首现缺半句身份、作者侧语汇漏网、课间口径失真与未兑现承诺、密度超载句。多数是「半句话」级修复。
2. **PyCharm 触点近乎为零**：全书唯一 IDE 内容在 L0.1 Step 7（约 3 行 PyCharm 侧文字、零菜单路径，且「共同动作」段按 VS Code 心态写成）；此后 29 课 + 5 里程碑零回收。建议以「**IDE 侧栏**」定式补 ≈15–20 个高价值场景点（§5），不动「终端三命令」验收主线。
3. **命令双端覆盖执行率很高**（学员主线 `uv run` 化基本全绿），漏网集中在三处宪法盲区：仓库根作者脚本入口用裸 `python3`（unit5 里程碑「重验五连」，Windows 照抄必炸）、家目录路径 `~/develop/opensource` 簇（Windows 不展开 `~`）、L4.1 加餐 `export` 缺 PowerShell 对照块；另有作者侧 handbook/README 两行（用户例句的实锤出处）。正面样板：L0.1 安装/镜像双块、L5.2 的 `curl.exe` 警告（§3.3）。
4. **生态基础概念讲解深度不均**（用户点名的两个例子都成立）：`.venv/` 全书讲解总量仅 3 行；「**activate**」全书零出现——学员查任何外部资料必撞的第一个仪式，课程用了它的替代方案（uv run）却从未点破；「**pip**」一词在学员正文从未被解释（「收敛到 uv 一把梭」但没说收敛自什么、pip 与 uv 什么关系）；ruff 有 Checkstyle 桥但缺「是什么」的身份半句。命令的图形化对照方面，本轮补齐为**全书命令 ↔ PyCharm 图形操作全量对照表**（§4.2）——作为 L0.1 Step 7 扩容的一部分一次兑现「各个命令行操作都有图形化对应」。

## 1. 审核点①：新手友好度——残留问题分层

### 1.1 P1（唯一）：主线步骤硬依赖未教的本地克隆

| 位置 | 问题 | 实锤 |
|---|---|---|
| `L3.4:194-204` | Step 3（30 分钟核心步骤）五条命令全部以 `~/develop/opensource/langgraph/...` 绝对路径运行 `code/count_loc.py`，但**全程没有任何一课教过 clone 这个仓库**（grep 证实 clone 指引最早出现在 Unit 4；L3.1:399/L3.2:341/L3.3:413 的 §6 路标只写「本地克隆……」同样无命令）。照抄即 FileNotFoundError；学员自行 clone 默认 HEAD 也未必是 `e539ac122`，loc 结论会漂移 | ✅ 已验证 |

**修法**：L3.4 Step 3 前补一行 clone+checkout（HTTPS 形式，`git clone https://github.com/langchain-ai/langgraph.git ~/develop/opensource/langgraph` 分行 + `git checkout e539ac122`）；并在 unit3 README 学法说明统一交代「本学段源码路标统一克隆到 `~/develop/opensource/`」（L3.1 的 openai-agents-python 同享）。注意 L4.3 已有先例教训：SSH clone 对未配 key 的学员当场卡死，且 `~/develop/opensource` 父目录不存在时 git 不代建（L4.3:357 需 `mkdir -p`，见 P3 清单）。**该修法与 §3.2 的 `~` 路径双端问题是同一工作项，一次改齐**。

### 1.2 P2（29 条，按类型分组）

**A. 生态件/术语首现无身份（补半句即消，共 10 条）**——「自顾自讲新手不懂的知识点」的最典型残留：

| # | 位置 | 缺什么 |
|---|---|---|
| 1 | `L2.1:14/109`（L2.3 计费叙事延续） | **token** 全学段当货币单位用，从未一句白话（且 Java 人第一联想是鉴权 token）。修法：§2.3 usage 处「token：模型读写文本的计量单元（约 ¼ 个词）——计费、截断、上下文预算全按它算，与鉴权 token 无关」 |
| 2 | `L2.5:18/55` | **JSON-RPC** 是 §5「stdout 每个字节都是协议帧」的解释底座，零身份。修法：「用 JSON 表示请求/响应的轻量 RPC——HTTP+JSON 去掉 HTTP 的样子」 |
| 3 | `L3.2:171` | **ChatOpenAI** 零身份，且 langgraph / langchain / langchain-openai 三包关系全课无一字。修法：「langchain 对 chat-completions 客户端的封装（langchain-openai 包），≈ 你 L2.1 手写的 client + bind_tools 自动生成 schema」 |
| 4 | `L5.2:22` | **FastAPI** 无伞形总桥（对照表只有 Depends/StreamingResponse 零件桥）。修法：表前一行「FastAPI：Python 异步 Web 框架，角色 ≈ Spring Boot + WebMVC（Pydantic 校验内置）」 |
| 5 | `L5.2:281` | **uvicorn** 全仓首现即裸命令。修法：「≈ 内嵌 Tomcat 的角色：把 FastAPI 应用对象跑成真端口的 ASGI 服务器」 |
| 6 | `L5.2:273` | **ASGI** 无桥，「ASGITransport 会等 app 跑完」只能当现象背。修法：「ASGI ≈ Python 版 Servlet 接口（应用与容器间的契约）；ASGITransport＝进程内直连不走网络——所以能不起端口测 HTTP」 |
| 7 | `unit5/README.md:51` | 学员进 Unit 5 读到的第一批话连塞 httpx 内存直连 / ASGI transport / uvicorn / --real 五专名。修法：拆两句各给半句身份（同 #4/5/6 口径） |
| 8 | `L1.2:159/355` | 「class 语法 L1.3 才主讲，此处只需看懂形状」只兑现了**读**，但 ex2 要求**手写**协议类——`self ≈ this、必须显式写、调用时不传`半句桥缺失，漏写 self 的 `TypeError` 无自救材料；§2.5 的 `__init__` 同样裸用。修法：159 行括注补齐这半句 |
| 9 | `L1.3:176` | `ExpenseClaim(**dict)` 出现在本课核心论证表里，而 `**dict` 调用侧摊开是 L1.4 §2.2 主讲内容，L1.1 速览只讲过元组解包。修法：括注「`**dict` 把 dict 摊开成关键字参数，L1.4 §2.2 主讲」 |
| 10 | `L3.6:43` | 全课第一张表塞 actual/expected Invocation、轨迹比对、**LLM-as-judge**（全课程首现，:192 才有「裁判模型」）。修法：表内降为「评估是框架的一层（Step 5 详讲）」 |

**B. 课间口径失真 / 承接错位（5 条）**——学员「按图索骥会找错课、怀疑自己记错」：

| # | 位置 | 问题 |
|---|---|---|
| 11 | `L3.5:11` | 「L3.1 的 SDK 说『我只给你原语，循环自己搭』」与 L3.1:41「循环进了框架：软终止 + max_turns」直接矛盾（L3.8:56 与 L3.1 一致，失真方在 L3.5）。修法：改「原语给你，循环在 Runner 里但薄得能看穿」 |
| 12 | `L3.7:410-412` | 结尾直接导向 L3.8，而实际学序是 L3.7 → **里程碑** → L3.8（unit3 README 排期 + L3.8:5「昨晚里程碑」证实）；L3.7 全文零提里程碑（grep 证实）——学员会跳过产出选型数据的结业项目 |
| 13 | `L4.1:156` | 算式自相矛盾：`(0.8 + 3.0*(-0.6) + 0.9) / 5.5 = -0.0200`，左边实算 ≈ -0.0182；源头 `code/step1_blend.py:52`（公式串硬编码 5.5，数值另算）。本课主打「数学精确到分」，学员复算对不上会怀疑自己误解弃权剔除规则 |
| 14 | `L4.3:223/225` | 「产品八查 → 本课七查」裁剪表里**授权过期出现两次**（第 6 行与末行），本课列实数 8 项对不上「七查」；学员被明确指引拿表对 `code/enforcement.py` 数 |
| 15 | `L3.4:45/188` | `create_react_agent` 的 **v2**（version 参数取值）首现无定义，与 :115 的「V2.0」（库大版本）撞名不辨析；读到「v2 默认下每个 tool_call 是独立 Send」概念悬空 |

**C. 学员照抄即卡（2 条）**：

| # | 位置 | 问题 |
|---|---|---|
| 16 | `L3.2:279-282`、`L3.3:355-358` | hints 命令块缺 `cd exercises`（L0.1/L1.x/L2.x/L3.1 全带），括注「（在 exercises/ 目录下）」能救回但要卡一下；照抄即 `ModuleNotFoundError` |
| 17 | `unit5/README.md:51` | 「真实端点与 `uvicorn` 起服务都是 `--real` 可选加餐」与事实有出入：`--real` 只在 L5.1 demo_trace 存在，L5.2 的 uvicorn 加餐与它无关，学员照抄找不到开关 |

**D. 作者内部语汇 / 不可达引用漏网（7 条）**——上轮「元引用清洗」的漏网之鱼：

| # | 位置 | 问题 |
|---|---|---|
| 18 | `unit2/README.md:15`、`unit3/README.md:38-39` | 「`uv run pytest` 照样**三态**全绿」——「三态」学员侧未定义，且全课程至少四个三元组撞名（L1.2 限额三态、L2.2 错误三态、发货/毕业态、三条命令）。修法：改「三条验收命令全绿」 |
| 19 | `L3.8:82`、`unit4/milestone:108` | 「宪法先例：『292 行』因 BSD grep…」「宪法 §5」——宪法=AGENTS.md 学员不读；292→249 典故从未对学员讲过。修法：一句补全故事或删典故留纪律，「宪法」改「本教程纪律」 |
| 20 | `L3.8:108` | 「解析器**进了电池**」——batteries included 习语的残缺直译，重读无解。修法：「Python 自带电池（batteries included）：标准库连 TOML 解析器都内置」 |
| 21 | `unit3/milestone:21/42/200` | 把作者侧验证流水线内部状态机当学员已知：「三态验证的毕业态把本目录镜像到临时目录时只带…」。修法：改白话「我们的验收在一个只含 milestone/ 与 data/ 的干净副本里跑」 |
| 22 | `unit4/README.md:15` | 「对版机制件」的「对版」在 unit3 定义为「共享件字节相同」，本单元换了含义（与产品结构对应）未声明。修法：首现给半句（L4.1:132 已有正确表述，前移） |
| 23 | `unit4/README.md:28`、`L4.1:95/473`、`L4.2:118`、`L4.3:65` | 「A 组通病」「调研 dimensions/A-金融交易组.md §4」等调研内部坐标漏网（上轮政策：不进讲义、A 编号配 unit5 速查表）。修法：改「金融交易类产品通病」「课程调研结论一句话版」，或指向 unit5 速查表 |
| 24 | `L3.1:344` 等处 | 「对口径」「验收口径」的「口径」写作侧口语多处首现无定义（L1.3:312、L1.4:318 等同）。修法：统一改「验收标准 / 逐字段一致」，或首现半句定义 |

**E. 密度超载 / 概念先于结构（5 条）**：

| # | 位置 | 问题 |
|---|---|---|
| 25 | `L3.5:112-113` | backend / StateBackend / SandboxBackendProtocol / execute 四新名先于 Step 2 的 backend 概念，且不再展开。修法：bullet 前半句「backend＝虚拟文件系统的存储实现（Step 2 详讲）」 |
| 26 | `L3.5:116` | 「harness profile 关掉 `general_purpose_subagent.enabled`」——harness profile 全课唯一出现，无解释、无配置片段、无文档指路。修法：给 config 片段/官方指路，否则删 |
| 27 | `L3.7:83-84` | compose profiles + `${VAR:-默认}` shell 语法 + 21/13/5 服务账目一句压载，整段账目建立其上。修法：账目移 §6，正文留「profiles 开关按需启用可选服务」+ 一行语法注 |
| 28 | `L3.7:111-112` | 一句五专名（Agenton/graphon/Pydantic AI/pydantic-ai-slim/FastAPI），Pydantic AI 是完整未教框架。修法：收敛为「v2 新增的独立 agent 运行时服务（细节见 §6 路标）」 |
| 29 | `L1.8:33-34` | 全课锚点句「两者都让你**用同步的写法**拿到高并发」与本课自己的表（「写法外观……全链路 async/await 传染」）相抵触。修法：改「写**顺序命令式代码**拿到高并发（不写回调、不装配算子链）——但让出的位置不同」 |

### 1.3 P3（≈100 条，摘要归组）

上轮修复后的打磨级残留，按频次排序（修复时可按组批量处理）：

- **首现缺半句 gloss（最大簇，≈30 条）**：元组（L0.1:120，Java 无对应物）、`>>>` REPL 提示符（L1.2:247，jshell 对照 + 照抄进 .py 会 SyntaxError）、duck typing 成语只引半句（L1.2:196）、Callable 会误联想 `java.util.concurrent.Callable`（L1.2:120）、生成器表达式首行无桥（L1.1:227，≈ Stream.anyMatch）、`@runtime_checkable` 无「别当 Java 注解」警示（L1.2:197）、fail-closed 学员路径首现（unit0:40 + L0.1:244 等，主讲在 L2.4）、`仓库@commit#路径` 记法本身无解释（L0.1:239 首现）、`__x` 名字改写 L1.2:255 承诺 L1.3 讲但 L1.3 从未兑现、SSE 缩写全程无展开（L1.6:263 起，补「Server-Sent Events，Spring 的 SseEmitter」）、agentscope 无身份（L1.7:313）、`is_dataclass` 直进验收判据（L1.3:314）、Annotated 只有一行注（L1.3:152）、PEP 8 无身份（L1.4:154）、inspect（L1.4:330）、tracemalloc（L1.6:154）、ReAct 词形拆解迟到一课（L2.2:221）、openai-python 身份（L2.1:302）、PEAD/point-in-time/mandate（L4.1:58/64/52，mandate 白话在两课后）、pipx/poetry（L4.1:346）、pyyaml（L3.7:18）、StructuredTool（L3.4:110）、astream（L3.2:370）、通道 channel（L3.2:91）、wire 名词（L3.1:18）、`import agents` 三套名字并存（L3.1:285，artifactId≠包名 现成桥）、HITL 缩写（unit3:83）、os.replace 原子性（L4.3:136，≈ Files.move ATOMIC_MOVE）、model_construct 旁路身份（L5.1:86）、Effect/drizzle（L5.2:380/L5.3:65，opencode 的 TS 件）、qualname（unit3 milestone:37）。
- **作者语汇 / 内部计数漏网（≈20 条）**：「六段式」仍留在 4 个 milestone 开头（上轮已点名，未改）；「发货态」连用 7 处仅 L1.3 定义过一次（L2.1 首现补同位语即可）；「命名化失败模式」（L1.3:334/L1.5:244）；「延伸路标」（L2.3:255/L2.4:156）；「原典 vs 对照原件」不统一（L2.3:63 等 vs 全学段「对照原件」）；「三态裁决」提前入 L1.4 结尾预告；「行尾降级」（unit5 milestone:71）；「A 组」「第 N 次登场」类自计数；「课程设计线在这里收拢」（L1.7:174）。
- **数字 / 指代对不上（≈12 条）**：L2.1:304「第二条路标」实为第三条；L4.1:19「六个文件」实为八条路标；L5.2:102「四类事件五种名字」归类不释；L5.4:341「表 11 行」指代不明（ex1 骨架覆盖表）；L3.4:59「ast 口径」先用于定义后给（Step 3 才解释）；unit3 milestone:87 发货态输出里提前引用 L3.8 两列对账（顺序错位）；L2.4:69「漂移点」与 L2.2 签名漂移两码事；L4.2:240 相邻两节「9 份/9 次」同数异指；L3.3:231「再跑一遍」实为「重新 start 一单再 deny」（同一 thread 恢复一次即完结）。
- **克隆 / 锚定一致性（4 条）**：L4.1/L4.2 加餐 clone 不 checkout，§6 却假设 HEAD==锚定 commit；L4.3:357 SSH clone + 无 `mkdir -p`（并入 §3.2 平台簇一并修）。
- **事实 / 排版小疵（≈10 条）**：L3.7:188 树图 11 服务 vs「12 个上岗」数不上（init_permissions 未介绍）；L2.5:284「活化石」指错了文件（真活化石是同目录遗留的 `fastmcp.py`）；L3.8:46 SonarQubit→SonarQube；L3.8:95 tomllib「首现」与里程碑冲突；L3.8:118 Path 缓存归一动机论证反了；L1.7:139「不会刷新栈」落错列；L1.8:262/L284 括号全半角混用；L5.3:124 多余右括号 + 断行破词；L1.1:196 §2.7 标题括号歧义；L1.2:205 枚举分号体例不一。
- **示例细节（3 条）**：L1.4:77 演示默认值的示例用 `= []`（恰是本课 §5 要拆的雷）；L1.5:84-87/162-168 讲义片段缺 import 行（抄进 Console 会 NameError）；L1.5:246 一句四受害者的例子可砍半。

### 1.4 正面确认（防过度修正）

- 登记制执行到位的样板：L2.2（四态/fail-closed 首现全带标注）、L4.1/L5.3（对照表 + JDBC 五连）、L3.2 superstep / L3.3 pregel 内嵌定义完好——上轮 18 处首现修复无一回退。
- A 编号 13 个全部可从 unit5 速查表查到；`research/` 引用的章节实测存在（虽个别仍以内部路径形态出现，归入 P3）。
- 生态件身份交代的好样板（照此推广即可）：httpx（L2.1:36 OkHttp 对照）、SSE 协议（L2.1:126 全称+格式图）、docker compose（L3.7:71-80 专段+application.yml 类比）、DataAgent/opencode/DB-GPT 身份介绍。

## 2. 审核点②：PyCharm 触点现状审计

### 2.1 现状（量化）

- **全书唯一 IDE 内容 = L0.1 Step 7（139–166 行）**：pdb 五命令对照表（好）+ IDE 二选一表 + 「共同动作」段。PyCharm 侧专属内容 = 1 个表行 + 半段通用语，**约 3 行、零菜单路径**，覆盖约为 VS Code 侧的 1/3（VS Code 行有「Pylance=命令行 pyright 同引擎」的闭环故事 + 扩展动作；PyCharm 行只有三个卖点词）。
- 「共同动作」段的「右键 → Run / Debug」实际是 PyCharm 词汇却无菜单路径；对 VS Code 用户措辞反而不准。
- **此后 29 课 + 5 里程碑：IDE 内容为零**（8 个分片 grep 复核；L3.1/L4.2 出现的「断点」均指 checkpoint 恢复点或 `debug=True` 日志参数，与 IDE 无关——补充时值得顺带消歧）。学员操作 100% 终端 `uv run`。
- 连带失真：L1.2:33/296「IDE 红线 = Pylance = pyright 同引擎」对选了 PyCharm 的学员不成立（PyCharm 自带检查是另一套引擎，可装 Pyright 插件对齐）。

### 2.2 事实基础（2026-09 联网核实）

- **PyCharm 2025.1 起原生支持 uv**：环境类型列表直接选 uv，自动检测、按 pyproject/uv.lock 管理 `.venv` 与依赖同步（官方文档 [Configure a uv environment](https://www.jetbrains.com/help/pycharm/configure-a-uv-environment.html)）；**Python Packages 工具窗口装/卸包会写入 pyproject.toml（等价 `uv add`）**；2025.2 起支持 uv workspace（beta）。诚实边界：远程解释器/WSL 等 edge case 偶尔仍需内置终端手动 `uv sync`（JetBrains YouTrack 有在案 issue）。因此 L0.1「`.venv` 会被自动识别」现在可以写得更准：Add Interpreter → **uv 类型**（手动指到 `.venv/bin/python` 是旧办法，仍可用）。
- pytest 集成开箱即用（测试文件/类/用例行首 gutter 绿三角，≈ IDEA 的 JUnit 体验）；ruff 有 Astral 官方插件（Problems 面板出 lint 结果 + quick-fix，可接管 Reformat Code）；调试器面板 Variables/Watches/Evaluate 对应 pdb 的 `p`。
- **诚实边界**（补充时必须遵守，不硬造）：HTTP Client 与 Database 面板属 Professional 版能力（Community 学员用内置终端 `curl` / `sqlite3` CLI 等价完成，注明即可）；PyCharm 无 langgraph 图视图（库侧 `get_graph().draw_mermaid()` 是库 API 加餐，不是 IDE 能力）；IDEA Ultimate + Python 插件是等价路径——受众是 Java 人，很多人手头就有 IDEA，值得在 L0.1 表行点一句。

## 3. 审核点③（补充轮 1）：命令行的 Windows / macOS 双端覆盖

> 宪法基准（CURRICULUM §6 / AGENTS §5）：「平台中立：学员命令一律 `uv run ...`；多步命令不用 `&&`（PowerShell 5.1 不支持）；平台差异（安装脚本/环境变量/cp-copy）以**对照块**标注」。方法：fence 解析脚本扫描全部 34 份讲义 + 元文档的代码块，命中 6 类模式（裸 `python`/`python3`/`pip`、`cp`/`rm`/`ls` 等 POSIX 命令、`curl`、`~`/`$HOME`、`export`/`source`），逐处人工核对上下文有无 Windows 对照。

### 3.1 总体判断

**纪律执行率高**：学员主线 bash 块里裸 `python`/`pip` 全程零出现（验收/演示命令 100% `uv run` 化，这正是「命令一致跨三平台」设计的结果）；`&&` 机器校验兜底；L0.1 的安装与镜像配置是双块模范。漏网集中在三类**宪法没覆盖到的缝隙**：仓库根的作者脚本入口（不是课时内命令，绕过了「一律 uv run」的习惯）、家目录路径 `~`（shell 展开差异，命令本身仍是 uv run）、加餐段的 `export`（对照块纪律执行到 L0.1/L1.1 后未坚持）。

### 3.2 问题清单（P2×3 簇 + P3×2 + 作者侧×1）

| # | 严重度 | 位置 | 问题 | 修法 |
|---|---|---|---|---|
| 1 | **P2**（与用户例句同款） | `unit5/milestone/README.md:93-98` | 结业「重验五连」在**仓库根**用裸 `python3 scripts/three_state_check.py …`×5——Windows 无 `python3`（python.org 安装器只装 `python.exe`/`py.exe`，Store 别名只会弹商店），照抄必炸；macOS 能跑纯属惯例。这是全课程学员命令里唯一一处裸解释器调用（讽刺的是它跑的正是三态验证） | 五行统一改 `uv run python scripts/three_state_check.py …`（`uv run` 在无 pyproject 的仓库根照常工作，用 uv 托管的解释器，三端一致） |
| 2 | **P2**（簇） | `L3.4:200-204`、`L4.1:359`、`L4.3:357/361` + L3.1:399/L3.2:341/L3.3:413 路标 | `~/develop/opensource/...` 家目录路径簇：bash/zsh 会展开 `~`，但 **Windows PowerShell/cmd 不为原生命令的参数展开 `~`**——`uv run python code/count_loc.py def ~/develop/...` 收到字面 `~` 目录直接 FileNotFoundError；`git clone … ~/develop/...` 在 PS 里会建出名为 `~` 的目录，后续 `cd ~/...`（PS 对 cd 自身可展开）反而对不上 | ① unit3 README 学法说明一次性约定：「Windows 学员把源码统一放 `%USERPROFILE%\develop\opensource`（PowerShell 里 `$HOME` 变量可用 `$env:USERPROFILE`），讲义中 `~/develop/opensource` 均指该目录」；② L3.4 的 `code/count_loc.py` 参数解析加一行 `Path(arg).expanduser()`（课程自有工具，改脚本一次，五条命令全端通用）；③ L4.3/L4.1 的 clone 命令配 PowerShell 对照块——与 §1.1 的 P1 clone 指引是**同一工作项** |
| 3 | **P2** | `L4.1:355-358` | 加餐段 `export FINANCIAL_DATASETS_API_KEY=…` 等四连：只有半句「（PowerShell 用 `$env:` 语法）」提示，没有对照块——学员要自己现写四行 PS；且随后 `aihf ~/.hedge-fund/…` 又是 `~`（同 #2 簇）。对照 L0.1 Step 2 的双块先例，这是对照纪律没坚持到底 | 补 PowerShell 对照块（`$env:FINANCIAL_DATASETS_API_KEY = "…"` ×4）；`~` 路径按 #2 约定处理 |
| 4 | P3 | `L2.1:201`、`L3.1:315`、`L3.7:246` | 三处 `cp .env.example .env` 裸奔，无就地 Windows 注（对照信息只在 20 课前的 L0.1:171 行内注释与 L1.1:242 开头说明里） | 推广 L0.1:171 的行内注释样式：`cp .env.example .env   # Windows: copy .env.example .env`，三处就地补齐（`copy` 在 PS 里是 Copy-Item 别名，能用） |
| 5 | P3 | `L1.1:159/163` | 概念转写块 `$ python demo_name.py` / `$ python -c "import demo_name"`——展示 `__name__` 双身份的终端记录用了裸 `python`，与全书 `uv run python` 口径不一（本课 Step 3 实际命令是对的）；Windows 学员若照转写块敲，又会撞上 `python` 存在性/环境问题 | 转写块统一改 `$ uv run python …`，或块前注明「示意转写，实际命令见 Step 3」 |
| 6 | 作者侧 | `handbook/README.md:26、222` | **用户例句的实锤出处**：`uv run build.py && python3 -m http.server 8347 -d dist`——`python3` 双端问题 + `&&` 违反自家 PS 5.1 纪律（虽是作者侧文档，教程开源后读者会照抄） | 拆两行、全端化：`uv run build.py` ＋ `uv run python -m http.server 8347 -d dist`（handbook 本身是 uv 项目，`uv run python` 直接成立——正是用户给出的修法） |

### 3.3 已核实无需修的命中（避免误伤）

- `L0.1:54-66` 安装：bash/PowerShell 双块齐全（`curl|sh` vs `irm|iex`）——宪法对照块的**正面样板**。
- `L0.1:70-81` 镜像环境变量：双块齐全（`export` vs `$env:`/`setx`）。
- `L0.1:58` `source $HOME/.local/bin/env`：在 macOS/Linux 块内，Windows 有独立块，正确。
- `L1.1:286/292` `ls` / `rm -rf`：L1.1:242 开头有整行 Windows 映射说明（`cp`→`copy`、`rm -rf`→`Remove-Item -Recurse -Force`）；`ls` 在 PowerShell 是 Get-ChildItem 别名可直接用。
- `L1.1:328` `PYTHONPATH=code uv run …`（bash 前缀赋值语法 PS 不支持）：紧随其后有 PowerShell 对照块（`$env:PYTHONPATH = "code"`）——执行到位。
- `L5.2:288-305` curl 四连：**:296-297 已有完整 Windows 警告**（「PowerShell 5.1 注意：curl 是 Invoke-WebRequest 的别名，-N/-d 语法不通——用 `curl.exe -N ...` 强制走真 curl，或换 Invoke-RestMethod；以下 curl 命令同」）——对照纪律的模范，本轮初判误报、经上下文核对排除。
- `L3.7` docker compose 三连：Docker Desktop 跨端一致，`cd docker`/`copy` 在 PS 均可用（仅 `cp` 裸用见 P3#4）。

### 3.4 面上的规律（修复轮参考）

- **缝隙规律**：破口不在「课时内 uv 命令」（机器校验 + 写作习惯双保险），而在三处视野盲区——**仓库根的脚本**（three_state_check 是作者工具进入学员路径的唯一入口）、**`~` 展开**（命令仍是 uv run，但参数是 shell 语义）、**加餐段**（对照块纪律在「主线」执行、加餐松懈）。
- **修法优先级**：#1（结业重验五连，一行×5）与 #6（handbook 两行）分钟级；#2 与 §1.1 P1 合并成「克隆与源码目录约定」一个工作项；#3/#4/#5 顺手补。

## 4. 审核点④（补充轮 2）：生态基础概念的讲解深度 + 命令行的全量图形化对照

> 方法：对七组生态关键词（`activate` / `pip` / `.venv`·虚拟环境 / `site-packages` / `wheel` / `.python-version` / `Astral`）做全书 grep 取证并核对上下文；PyCharm 图形化能力逐项联网/文档核实（§2.2）。这两个子项正好互为表里：概念讲透了，图形化对照才有地基（学员要知道「PyCharm 右键 Run 用的就是 `.venv` 里的解释器」≈「`uv run` 的后半段」，前提是先知道 `uv run` 和 `.venv` 是什么关系）。

### 4.1 A：生态基础概念审计（用户点名 `.venv/` 与 ruff，均成立）

| # | 严重度 | 概念 | 现状（grep 实证） | 缺口与修法 |
|---|---|---|---|---|
| 1 | **P2** | **虚拟环境 / `.venv/`（用户点名）** | 全书讲解总量 **3 行**：L0.1:37 表行（「classpath 天然隔离 \| venv…Java 没有的痛点，Python 用虚拟环境解决」——为什么 Java 没有这个痛点没展开）、L0.1:101 行内注（uv sync 创建 .venv）、L0.1:166 IDE 顺带一句 | 缺四件：① 为什么 Java 不需要（每个应用自带 classpath/fat jar，Python 传统上**全局唯一**一份 site-packages → 多项目依赖地狱）；② `.venv/bin/python` 与「系统 python」是什么关系；③ **为什么夜校从不 activate**（见 #2）；④ `uv run` 的机制半句（见 #3）。修法：L0.1 Step 3 处扩一段 6–8 行「虚拟环境 101」，把 uv sync / uv run / .venv / （外部教程的）activate 四者的关系一次讲清。这段同时是 §5 全部 IDE 等价操作的理解地基 |
| 2 | **P2** | **activate（激活）** | **全书零出现**（grep 证实）——但它是学员离开讲义查任何外部资料（报错搜索、别人的教程）**必撞的第一个仪式**：`source .venv/bin/activate` / `.\.venv\Scripts\Activate.ps1`。课程用了它的替代方案（uv run 自动做了）却从未点破，学员会困惑「我少做了一步吗」 | 并入 #1 的「虚拟环境 101」：activate 是「把 .venv 的 python 提到 PATH 最前」的手动仪式；`uv run` 每次替你做了同样的事，所以夜校从不需要 activate——一句话点破，外部资料的「仪式」从此能对上号 |
| 3 | **P2** | **`uv run` 的机制** | 只有 L0.1:32 表行（`mvn exec:java` → `uv run`）——桥有了，机制没有：uv run = 「先确认 .venv 与 uv.lock 同步，再用 **.venv 里那个**解释器执行命令」 | 并入 #1。这半句还直接支撑 §4.2 表：「PyCharm 右键 Run」之所以等价，是因为它同样用 .venv 解释器（同步这件事 PyCharm 2025.1+ 也接管了） |
| 4 | **P2** | **pip** | **学员正文从未出现「pip」一词**（grep 证实）；L0.1:48 只有一句「Python 世界已经收敛到 uv 一把梭」——收敛**自**什么、pip 和 uv 什么关系、为什么不用 pip，零交代。学员第一次离开教程（搜报错、装课程外的东西）就是 pip 世界 | L0.1:48 旁补 2–3 行：pip 是 Python 官方老牌安装器（≈ 没有 lock 文件时代的 Maven）、装的位置相同（site-packages）；uv 是 Astral 公司用 Rust 写的兼容替代，多做了项目管理与锁定；夜校全程 uv，外部资料里的 `pip install` ≈ 我们的 `uv add`/`uv sync` |
| 5 | P3 | **ruff 的身份（用户点名）** | L0.1:34 表行有 Checkstyle+Spotless 桥（角色对上了）、:35「毫秒级」、Step 5 体验、:238 官方文档链接——但「它是个什么东西」没有：第三方工具（非标准库）、Astral 用 Rust 写、与 uv 同厂 | 表行或 Step 5 补一句身份：「ruff：Astral 公司（uv 的同一家）用 Rust 写的第三方 linter + formatter，Checkstyle + Spotless 合体且快两个数量级」。顺带把 L0.1 安装 URL 里的 astral.sh 与「Astral」挂钩（全书只出现域名从未说这是公司名） |
| 6 | P3 | **site-packages** | L1.1:179 表行「依赖只在 site-packages」+ :281 顺带（sys.path 尾部）——从未说它是什么 | 半句 gloss：「site-packages ＝ venv 里平铺第三方包的目录，≈ 把依赖 jar 解开平放进 classpath 的那层」（与 L1.1 的 sys.path 讲解天然同位） |
| 7 | P3 | **wheel** | L0.1:83/137 两次用到「nodejs-wheel-binaries」「随 PyPI 安装」，wheel 本身零解释 | 半句：「wheel（.whl）＝ Python 的 jar：预编译二进制包格式，PyPI 分发的就是它」 |
| 8 | P3 | **`.python-version`** | 每课目录都有（check_lesson 强制），但 L0.1:89-97 结构图没列它，全书零解释——学员 `ls -a` 会看到一个没讲过的隐藏文件 | 结构图补一行 + 半句作用：「`.python-version` ＝ 本项目用的解释器版本号（uv 据此自动装/选），≈ .sdkmanrc / .java-version 的角色」 |
| 9 | P3 | **pyproject 的 `[tool.*]` 段** | L0.1:39-46 段落对照表只覆盖 `[project]` / `[dependency-groups]` / uv.lock；学员打开 pyproject 还会看到 `[tool.ruff]`（line-length=120）等段落 | 对照表补一行：「`[tool.ruff]` 等工具段 ≈ pom 的 `<build><plugins>` 配置段——ruff/pyright/pytest 各自的开关都住这里」 |

**判断**：这不是「讲错了什么」而是「讲少了什么」——L0.1 用一张漂亮的 Maven→uv 对照表把工具链**角色**全对上了（角色映射执行得好，ruff/pytest/pyright 的桥都在），但角色背后的**生态背景**（venv 为什么存在、activate 仪式、pip→uv 的关系）被表格的密度吃掉了。四个 P2 全在 L0.1 一课内，一次扩写全消；且与审核点②互为地基。

### 4.2 B：全书命令 ↔ PyCharm 图形化操作全量对照表（对用户第 2 问的正面交付）

> 落点建议：这张表进 **L0.1 Step 7**（随 §5.1-#1 的双 checklist 一起扩容），此后全书图形化承诺即由此表一次兑现、各课侧栏只做场景化回收。原则不变：**验收判据永远是终端三命令**，这张表回答的是「日常在 IDE 里写代码时，每个动作都有按钮版」。Pro-only 能力明确标注——**Community 版全程可完成主线**。

| 终端命令（全书出现过的全部形态） | PyCharm 图形化对应 | 前提/边界 |
|---|---|---|
| `uv sync` | 打开课目录时自动识别 uv 项目并提示创建/同步环境（2025.1+ 读 pyproject/uv.lock）；Settings → Project → Python Interpreter 可见 uv 类型环境 | 远程解释器/WSL 等 edge case 偶需内置终端手动 sync（YouTrack 在案） |
| `uv add …` / `uv add --dev …` | Python Packages 工具窗口搜索安装/卸载——**写入 pyproject.toml，等价 uv add** | 低频动作，内置终端跑也一样 |
| `uv run python demo_x.py` | 编辑器/项目树右键该文件 → Run ▶（解释器＝.venv 里那个，等价 uv run 的后半） | L0.1 接入后全程成立 |
| 带参：`--real CLM-2026-0003`、`start <id>`、`8800` 等 | Run → Edit Configurations → **Parameters** 栏（IDEA 的 Program arguments 对应物） | §5.1-#13 的回收点 |
| `uv run python -m expense.cli` | Run Config → Launch option 选 **Module name** 填 `expense.cli`，Working directory 设包的父目录 | §5.1-#2：与 L1.1 核心陷阱对齐（点 gutter 直跑必炸的那个） |
| `uv run python -c "…"`（hints 三级提示） | 底部 **Python Console** 直接敲 `from hints import hint; print(hint('ex1', 1))`——≈ jshell 常驻版，比 -c 顺手 | — |
| `uv run pytest` | 测试文件/类/用例行首 **gutter 绿三角**；失败用例红条可单条重跑；断言 diff 直接展示实际值——≈ IDEA 的 JUnit 面板 | pytest 集成内置，零配置 |
| `uv run pytest -k 关键词` | 测试树面板筛选/只勾选目标再 Run | — |
| `uv run ruff check .` | 装 Astral 官方 **Ruff 插件** → Problems 面板即 lint 结果，编辑器行内黄标 + quick-fix | 与命令行同一套规则（读 pyproject `[tool.ruff]`） |
| `uv run ruff format .` | Ruff 插件接管 **Reformat Code**（⌥⌘L / Ctrl+Alt+L） | 插件设置里指定为默认 formatter |
| `uv run pyright` | PyCharm **自带**类型检查即标红（引擎与 pyright 不同）；要 100% 同引擎装 Marketplace 的 **Pyright 插件** | §2.2 / §5.1-#3：修 L1.2 的 Pylance 独占假设时一并交代 |
| `.env`（`cp` 一次即生效） | **无需任何配置**：课程 env_loader.py 按文件位置读 `.env`，与 IDE 无关 | 想用真实环境变量覆盖时才去 Run Config → Environment variables（§5.1-#18 场景） |
| `uv run --with jupyter jupyter lab` | Professional 内置 Jupyter 支持（.ipynb）；**Community 无此能力，保持命令行** | L0.1 Step 9 本就是可选项 |
| `uv run uvicorn api:app --app-dir code --port 8000` | Run Config：Module name `uvicorn` + Parameters（Pro 另有 FastAPI 专项模板）；Services 面板统一启停 | §5.1-#18（L5.2 多终端工位） |
| `curl -N` / `curl -s -X POST …` | Professional：内置 **HTTP Client**（.http 文件可复放）；Community：内置终端 `curl` | SSE 长流的实时帧保留终端观察（§5 诚实边界）；Windows 用 `curl.exe`（讲义已有警告） |
| `git clone` / `git checkout` / 分支改造 | Git 菜单 → Clone；分支 widget 新建/切换；Checkout Revision…；Commit 窗口 diff 预览 | §5.1-#16/#17（L3.4 读码、L4 真改造） |
| `docker compose up -d`（L3.7） | Professional：Docker/Services 面板；Community：内置终端 | 平台课主线在浏览器，本就不需要 |
| `uv tool install .`、`aihf ~/.hedge-fund/…`（L4 加餐） | **无 GUI 对应**——内置终端跑（内置终端本身就是图形化工作台的一部分） | 低频加餐 |
| 仓库根 `uv run python scripts/three_state_check.py …`（§3.2-#1 修复后形态） | Run Config 指向该脚本即可（纯标准库，解释器要求宽松） | 先落 §3.2-#1 的 uv 化修复 |

表后随行原则句（写入 L0.1）：**三命令验收永远在终端跑**（机器判据不动摇）；表内能力以 PyCharm 2025.1+ 为基线，Pro-only 项已标注，Community 可完成全部主线；VS Code 学员的对应操作以一小节平行给出（Pylance/Ruff 扩展、Testing 面板、launch.json 传参——L0.1 现有 VS Code 行扩写即可）。

## 5. 补充方案：IDE 侧栏定式（不破宪法）

**四条设计原则**：

1. **主线不动**：验收判据永远是终端三命令（平台中立、机器校验口径不变）。PyCharm 内容全部以**固定格式的「IDE 侧」侧栏**出现（建议 blockquote 定式，如 `> 💡 IDE 侧（PyCharm / IDEA+Python 插件）：…`），**不进 bash 代码块**——天然避开 check_lesson 的 `&&` 校验与「学员命令一律 `uv run`」契约（侧栏描述 IDE 内等价操作，不是新命令）。
2. **一次教学 + 回收式点名**：L0.1 Step 7 扩容为「接入双 checklist（VS Code / PyCharm）+ §4.2 全量对照表 + §4.1 的虚拟环境 101 作理解地基」。此后每课**至多 1 个**高价值侧栏，全书 ≈15–20 个，以「还是 L0.1 Step 7 那套」回收，不逐课刷存在感。
3. **插入点选「断点/IDE 独有收益」的场景**，四类优先：① 断点看**时间型机制**（print 讲不出的行为）；② 首次引入的**操作型工具**（Run Configuration 传参、起服务、子进程调试）；③ **读大仓导航**（Go to Definition / Find Usages，IDEA 肌肉零成本平移）；④ 高频**测试迭代循环**（里程碑验收）。
4. **诚实边界随行**：每条侧栏不承诺 IDE 没有的能力（见 §2.2 与下表注记）。

### 5.1 高优先级插入点（按课序，18 处）

| # | 位置 | 侧栏内容 | 类型 |
|---|---|---|---|
| 1 | L0.1 Step 7（166） | 重写「共同动作」为双 checklist + §4.2 全量对照表 + 「虚拟环境 101」衔接；PyCharm 表行补「pytest 集成开箱即用」「IDEA Ultimate + Python 插件等价」 | 接入 |
| 2 | L1.1 Step 6/§5 | **PyCharm 用户点 gutter 绿三角跑 `cli.py` = 直跑文件，第一次运行就复现本课核心 ImportError**；正解 Run → Edit Configurations → Python → Launch option 选 Module name `expense.cli`、Working directory `code/`——顺带引入 Run Configuration 概念（全书此后带参运行全靠它） | 陷阱对齐 |
| 3 | L1.2 Step 4（296） | 补 PyCharm 分支：自带检查同样对 `bad: int = "abc"` 标红（悬停看 Inspection）；要与命令行 100% 同引擎装 Pyright 插件；同步修 :33 表行的 Pylance 独占假设 | 接入 |
| 4 | L1.4 §5 陷阱一 | 断点 Debug `add_item_buggy` 两次，Watches 加 `id(items)`——两次同一 id，可变默认值共享立现（本课最反 Java 直觉处） | 断点看机制 |
| 5 | L1.5 Step 2 registry | 断点 `TOOLS[func.__name__] = func`，Debug 跑——任何函数被调用前就停两次，TOOLS 从空长到两条：「定义即执行」从断言变证物 | 断点看机制 |
| 6 | L1.6 Step 1（**四课中断点收益最高**） | 三个 `yield` 行断点 Debug：每 Step 一次，函数在 yield 行挂起、Frames 里挂起的帧与局部变量还活着——「冻结/唤醒」从比喻变成看得见的调用栈 | 断点看机制 |
| 7 | L1.7 §3 Step 2 | Python Exception Breakpoints（Run → View Breakpoints，勾 `AmountParseError`）＝IDEA「Java Exception Breakpoints」原位平移；触发时 Variables 直接看 `__cause__`/`__context__`——异常链从读日志变看对象 | 新调试能力 |
| 8 | L1.8 Step 5 | `await asyncio.sleep(0)` 行断点 Debug：Frames 里两个协程帧轮流成为当前帧；PyCharm 对 asyncio 默认 Async 调试模式（协程按色分组）——「让出点」从日志推断变单步亲见 | 断点看机制 |
| 9 | unit1 milestone 验收段 | 测试文件 gutter 绿三角跑/单条重跑（≈ IDEA JUnit 面板），失败断言 diff 直示 Summary 实际值——结业考高频迭代提速最明显 | 测试循环 |
| 10 | L2.1 Step 2 后（SSE） | 断点 `SSEDecoder.feed` 的 `find(b"\n\n")` 与切块两行，Debug `demo_stream.py`，Watch `_buffer` 从半截 JSON 逐块长出——字节流重组是「看不见的过程」，断点是唯一肉眼验证法 | 断点看机制 |
| 11 | L2.3 Step 3（读 agent.py） | 断点 `for turn` 与两处 `messages.append`，Debug `demo_agent.py`——§2.1 的十行伪代码变成可暂停的实物，Watch messages 列表 2→7 条逐轮生长 | 断点看机制 |
| 12 | L2.5 Step 1（MCP） | 两句实话：① 直接 Run `finance_server.py` 在 Run 窗口「卡住」是正常的（等 stdin），红色 Stop＝Ctrl+C；② **在 server 代码打断点、Debug client 是不命中的**——server 是 stdio_client 拉起的子进程；要单步 server 逻辑，对 in-process 的 `code/test_server.py` 打断点跑 pytest Debug。不讲这条「断点为什么不命中」是必然发生的困惑 | 子进程调试 |
| 13 | L3.1 Step 6（`--real`） | 第一个带参 Run Configuration（Parameters 填 `--real CLM-2026-0003`）；此后 L3.2 单号、L3.3 start/approve 子命令全是同一招 | 操作型工具 |
| 14 | L3.2 Step 2（读 demo.py） | 断点 `make_reviewer` / `tools_node` 内，Debug 跑 demo_trace：Variables 亲眼看「节点收整份 state、返回更新 dict」——全单元「调试器比终端强」的最佳代言 | 断点看机制 |
| 15 | L3.3 Step 2（杀进程实验） | 两个 Run Configuration（start / approve，thread_id 从 Run 窗口复制）；Stop 按钮＝强杀，验证 checkpoint 恢复照样成立；§2.5 警告的「进程挂住」Stop 就是那个 kill——多终端+长参数最易敲错处一次消掉 | 操作型工具 |
| 16 | L3.4 Step 3（源码导读） | 用 PyCharm 打开/Attach 克隆仓：Structure 定位 `create_react_agent`，⌘B / ⌥F7 在 `should_continue`、`Send`、`ToolNode` 间跳转（IDEA 同款键）——与 §1.1 的 clone 指引合并成同一段「准备动作」。**反提醒（诚实边界）**：别用断点看扇出并发——断点会把并行 Send 串行化，时序证据当场消失 | 大仓导航 |
| 17 | unit4：README 学法末尾 + L4.1 §6 / L4.2 真改造 / L4.3 Step 5 / milestone | 一个「IDE 准备」段 + 四处点名：克隆仓 Attach 同窗（课内机制件 ↔ 产品源码互跳）；§6 路标精读用 ⇧⇧/⌘B/⌥F7（路径+函数名形态的路标在 IDE 里是按钮）；L4.2/L4.3 真改造用 Git 分支 widget + Commit diff 预览（新手第一次动陌生仓，可视化可撤销比裸 git 安全）；milestone 的「最小 diff / 证据」两节天然由 Show Diff / Run 窗口产出 | 大仓导航+git |
| 18 | unit5：L5.2 Step 5 ×2、L5.3 Database、milestone | L5.2 多终端工位：Run Configuration 起 uvicorn + 非流式三连写进 `.http` 文件（HTTP Client，**Professional**；Community 用内置终端 curl）+ SSE 长流保留终端 `curl -N`；**点睛**：服务用 Debug 启动、断点打 `interrupt(payload)`——断点挂起时 SSE 终端停止蹦事件，「调试器冻住的就是事件循环」，把 §5「事件循环里睡死」从纸面反例变亲手实验。L5.3：Database 面板（**Professional**）打开事件库跑 `SELECT type, COUNT(*)…`，§2.2「可查询」承诺的最直接兑现（Community 用 sqlite3 CLI）。milestone：Debug + Evaluate 直接执行 `store.events_for(...)` 看事件元组形状再写断言（运行≠修改，不违「不要改」） | 操作型工具 |

### 5.2 中优先级（择要，≈10 处）

L1.2 §2.7 `>>>` 段顺带指路 Python Console（与 P3 修法合并）；L1.3 Step 4 `model_validate` 断点看 `exc.errors()` 四要素；L1.5 timing 双断点（装饰时刻 vs 调用时刻）+ ex2 异常断点；L1.9 gather 双任务帧 / 取消注入断点；L2.2 `model_validate_json` 断点看 arguments str→dict；L2.4 「编辑器当场红线」实操兑现（PyCharm 装或不装 Pyright 插件都行）；L3.5 首个动手课的 uv 环境一次性配置 + `result["files"]` 断点；L3.6 callback 断点证「零请求短路」+ 「adk web 与 IDE 断点互补」一句；L3.8 Step 3 跳读克隆仓用 ⌘O 直达类名；unit2/3 milestone：Run Config Parameters 传 `--mcp`／bench.py「子进程断点不命中是正常的」防困惑。L3.7 dify（浏览器+docker 课）与多数纯阅读 Step **明确不加**。

### 5.3 配套文档改动（实施轮一并做）

- **CURRICULUM §6 工程纪律「平台中立」条目**补两句：「IDE 侧栏（PyCharm/VS Code 等价操作提示）以 blockquote 定式存在，不入 bash 块、不作验收判据」；「仓库根脚本进入学员路径时同样 `uv run python` 化；`~` 家目录参数须双端交代（Windows 不展开）」。
- **CURRICULUM L0.1 课时明细**同步：Step 7 明确为「双 checklist + 终端↔IDE 全量对照表 + 虚拟环境 101（venv/activate/uv run 机制/pip 关系）」。
- **AGENTS.md §8 演进锚点**记一行本轮决策（IDE 侧栏定式 + L0.1 Step 7 扩容 + `~`/python3 双端缝隙先例 + 生态概念 101 段）。
- **check_lesson 暂不加新校验**（侧栏是散文、可选段，机器化收益低；「仓库根脚本 uv 化」仅一处，不值得规则）。侧栏会随 handbook 构建自然进站（units MD 是唯一事实源），无额外工作。
- 修复轮完成后照 AGENTS §6 写课流程全量重跑三态 + `check_lesson` 30 课 PASS + handbook 重建。

## 6. 修复路线建议

- **R0（小时级，先做）**：§1.1 P1（clone 指引，与 §3.2-#2 的 `~` 双端约定合并）；§1.2-C 照抄即卡 ×2；L4.1 算式、L4.3 表重复两个硬错误；L3.7:410 课序承接（防跳过里程碑）；§3.2-#1 重验五连 `python3`→`uv run python`；§3.2-#6 handbook 两行。
- **R1（半天～一天，批量「半句话」+ L0.1 扩写）**：§1.2-A 生态件身份 10 条按 §1.4 好样板逐条补 gloss；§1.2-B 口径失真 3 条；§1.2-D/E 内部语汇与超载句；§3.2-#3 L4.1 export 对照块、#4 cp 行内注 ×3、#5 转写块；**§4.1 虚拟环境/activate/pip/uv run 机制四合一扩写（P2×4，全在 L0.1）与 #5–#9 小 gloss**；P3 按 §1.3 五组扫荡。
- **R2（独立轮，建议单单元试点再全灌）**：IDE 侧栏 18 高 + 10 中 + **§4.2 全量对照表进 L0.1 Step 7**（它是全书回收的锚点，与 R1 的 L0.1 扩写同文件可并轮）；L1.2:33/296 Pylance 独占假设修正随行。
- **R3**：全量三态重跑 + check_lesson + handbook 重建；CURRICULUM/AGENTS 配套行同步。

## 7. 方法与证据说明

- 8 个分片均要求「原文摘录 + 实际行号」，主代理对最重指控（P1、全部硬错误、token/JSON-RPC/ChatOpenAI/uvicorn/ASGI 首现、「三态全绿」「进了电池」「同步的写法」矛盾、L3.5↔L3.1 口径、hints 命令缺 cd、多余括号）逐条回文件复核，**13/13 属实**。
- 平台专项：fence 解析脚本扫 34 讲义 + 元文档 + handbook 的全部代码块，命中 6 类模式共 29 行，逐行人工核对上下文——其中 3 处（L5.2 curl、L1.1 PYTHONPATH、L0.1 安装/镜像）经核对**已有对照、判定误报**并入 §3.3；其余 6 项问题全部带行号实锤（§3.2）。用户例句 `python3 -m http.server 8347 -d dist` 定位到 `handbook/README.md:26/222`（作者侧文档）。
- 生态概念专项：七组关键词（activate / pip / .venv·虚拟环境 / site-packages / wheel / .python-version / Astral）全书 grep 取证——「activate」与学员正文「pip」**零命中**、`.venv` 讲解总量 3 行（L0.1:37/101/166）、`.python-version` 不在 L0.1:89-97 结构图、Astral 仅以 astral.sh 域名出现从未点名（§4.1 各条均已带行号）。
- PyCharm 事实见 §2.2 来源（uv 环境配置官方文档、Packages 工具窗口写 pyproject、workspace beta、YouTrack edge case）；「PyCharm 免费用于非商业用途」的说法本轮未核实，实施时不引用。
- 修复轮已于 2026-09-19 同日按 §6 路线完成（R0–R3 全落地，见头部修复进度）；本文件头部即进度档案，沿用 2026-09-18 惯例。
