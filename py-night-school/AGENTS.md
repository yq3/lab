# AGENTS.md — py-night-school 工作规范

> 本文档是教程项目的「宪法」：中心思想、课程设计理念与硬性纪律。**写课 / 改课 / 审课前必读**。
> 课表与课时明细见 [CURRICULUM.md](./CURRICULUM.md)；对外叙事见 [README.md](./README.md)；设计理念的方法论证据链见 lab 仓 [research/agent-tutorials/](../research/agent-tutorials/)（landscape + report + profiles ×8）。

## 1. 中心思想

- **一句话**：写给 Java 工程师的 Python Agent 开发晚课——以 agent 开发为场景学 Python，以 Java 心智模型为桥。
- **双目的**：学员既获得 Python 工程能力，也获得可带回 Java 栈的迁移地图（毕业设计产出 JAVA-MAPPING.md）。
- **受众红线**：只服务「Java 熟、Python 略懂」人群。Python 已熟练者、零基础者、想学 LLM 原理者——在 README「招生对象」明确指路别处，不为他们加课。
- **空档定位**（不摇摆）：市场上无人占据的交集 = Java 桥 × 练习自动验收 × 源码深度 × 金融毕业设计 × 端点中立。证据：research/agent-tutorials/report.md（八仓解剖：练习验收是全行业空白）。

## 2. 课程设计理念（六特色，README 为准，此处为索引）

1. **Java 心智桥**——概念先给对照表；陷阱按「现象 / 最小复现 / Java 直觉为何失效 / 修复」四段命名化拆解；
2. **练习即测试**——TODO + pytest 自动验收，全绿即过关；
3. **对照组教学法**——Unit 2 手写 mini-agent 是全程对照组，OpenAI cookbook `Orchestrating_agents.ipynb` 是对照原件；
4. **源码路标**——`仓库@commit#路径`，读生产框架不读玩具；
5. **双贯穿线 + 金融毕业设计**——明线「报销单审查」从 L0.1 种下；暗线每课结尾「离毕业又近的一块」；
6. **夜校工程纪律**——竞品的系统性短板在这里默认不发生（见 §5）。

## 3. 课时模板：六段式（唯一结构，机器校验）

```
> 承接段（2–3 句 blockquote：昨晚产出 → 今晚新问题 → 为何排在今晚；单元首课回收上一学段）
## 1. 本课目标        （一句话、可验证；完成判据三命令块全课只贴这一次）
## 2. 概念讲解        （开头先给全课 Java↔Python 对照表，再逐小节展开）
## 3. 动手代码        （Step 化，code/ 目录支撑；小节统一「Step N」，可选标「（可选）」）
## 4. 练习            （单变量编辑约束 + hints 渐进披露 + pytest 验收；验收处一句话引用 §1 判据，不复贴）
## 5. Java 直觉陷阱   （命名化失败模式，四段式）
## 6. 延伸            （官方文档 + 源码路标 仓库@commit#路径；「与 mini-agent 对照」排在 §6 开头）
+ 结尾固定段「离毕业又近的一块」（暗线进度，散文体，下集预告写在这里）
```

写作契约（与 CURRICULUM §2 一致，check_lesson 机器校验）：术语首现即定义或标注「先混个眼熟，Lx.y 主讲」；练习表头统一「| 题 | 文件 | 考察 |」；完成判据口径统一「三命令全绿」。

话术约定：单元 = 学段、课时 = 晚课讲次、Unit 5 = 结业考；README 三个区块名固定为「招生对象 / 课表 / 入学指南」。

## 4. 练习机制（验收即毕业）

- **单变量编辑约束**：练习文件首行注释声明只改 TODO 区；验收测试文件头部注明「不要改本文件」。
- **hints 三级渐进**：第 1 级只给方向、第 2 级给形状、第 3 级才是接近完整的做法——答案只在最后一级（先例教训：初版第 1 级泄底被 review 打回）。「形状」= 伪代码/签名/提问式，**不含成行可抄的答案代码**（先例：Unit 2 复盘，讲义 Step 已展示同构实现，hints 不自觉复述成代码，五课系统性泄底）。自查法：把第 2 级抄进练习文件，能直接过验收即为泄底。**TODO 注释同理**——骨架 TODO 只写「问什么/形状」，不写「返回什么」：先例 Unit 3 复盘，L3.4 ex1 的 TODO 原样给出 `return [Send(...)...]` 列表推导、L3.3 ex2 给出 `Command(resume=decision)`，抄注释即过验收——泄底自查范围从 hints 扩大到骨架注释（hints 三级自查法对 TODO 注释同样适用）。
- **三方对齐**：题目 docstring、hints、pytest 断言同一口径——**数量词也要兑现**：写「四态 / N 个测试」前先数实际断言；删测试时同步删 docstring 承诺（先例：Unit 2 两处「预审四态」实为三态/两态）。
- **import 约束口径**：练习首行统一「只改 TODO 区**与所需的顶部 import**，其余不要动」。骨架只预置 given 部分用到的 import——学生填完才用到的 import 预置了也会被 lint 判未使用删掉（Unit 2「import 六连发」根因）；所需的 import 在 docstring 或 TODO 注释里点名。
- **覆盖型练习配 meta-test**：题目要求是对用例表的覆盖时，验收测试直接检查用例表本身（结果种类 / 边界 / 数量）——先例：L0.1 ex2，它抓到的第一个 bug 就在参考答案里；覆盖维度要逐维断言，不留单维缺口——先例：Unit 3 复盘，contract 只断言了 decision/部门维度，把某用例的 reason 改成与另一用例相同照样全绿（修法：reason 种类集单独一行 assert，五课同灌）。
- **开放设计题**不硬造判分，给行尾 golden answer 诚实降级。
- **验收三命令**：`uv run pytest`、`uv run ruff check .`、`uv run pyright` 同时全绿 = 课时毕业。

## 5. 硬性纪律（check_lesson.py + 评审双保障）

工程纪律（全部源自竞品实测短板，出处 report.md §3.5/§3.6）：

- 每课是独立 uv 项目，**uv.lock 必须提交**；ruff `line-length = 120`（中文按双列宽计，100 太苛刻——实测结论）。
- **平台中立**：学员命令一律 `uv run ...`；多步命令分行走（**不用 `&&` 串联**，PowerShell 5.1 不支持；机器校验只查 bash 块内的 `&&`）；平台差异（安装脚本 / 环境变量 / cp-copy）以对照块标注；不默认 macOS。
- 源码路标与外链延伸一律**锚定 commit**；讲义图片本地化，不外链 CDN；仓库**克隆即学**，教学主体不外置。
- **模型端点中立**：`.env` 三变量（`OPENAI_BASE_URL` / `OPENAI_API_KEY` / `MODEL_NAME`），每课目录带 `.env.example`；不绑任何云厂。
- 依赖陷阱先例：pyright 的 Node 走 `nodejs-wheel-binaries`（随 PyPI 镜像），不依赖 nodejs.org 直连。
- 出题陷阱先例：E501 要用**单字符串字面量**出题——`ruff format` 出于语义安全永不改写字符串内容（表达式拼接会被 format 自动拆掉，白教）。
- 出题陷阱先例：JSON 测试夹具用 `json.dumps` 构造，不手写字符串——`'{"items": [4000] * 126}'` 是 Python 语法不是合法 JSON（Unit 2：夹具自己先红）。
- **`ruff check --fix` 禁止作用于练习骨架**：会把「学生填完才用」的 import 当 F401 删掉；练习区只跑 `ruff format` 与不带 `--fix` 的 `ruff check`（Unit 2 先例）。
- **讲义量化结论必须可复现**：行数等统计写明工具与口径（如 ast 计数：定位各级 docstring 行区间后数非空非注释行），禁止依赖 shell grep 管道的隐式口径——先例：「292 行」因 BSD grep 不认 `\s` 而不可复现，四处复述全部返工为 249（ast 口径）。
- **源码路标锚点要验证存在**：`commits?path=X&per_page=1` 取到的「最后触达」可能是删除/搬迁该文件的提交（先例：langgraph prebuilt 死链）；锚定后用 contents API 带 ref 复核文件真实存在，且格式带 org 前缀（`openai/openai-python@…`）。
- **共享模块对版纪律**：同一模块的多课副本修 bug 必须同灌全部副本（先例：model.py 空 tools 修补未回灌 L2.3）；复制到不同目录层级时核对 `parents[N]` 深度与 docstring 内路径（先例：milestone env 路径 bug、mcp_server 文档路径残留）；合理差异就地注释声明。
- **外部依赖离线化**：凡调用外部服务（模型端点/MCP/子进程），配协议级测试替身——mock 端点（≈ WireMock）与剧本模型，使验收离线确定、无需 key；真实端点做 `--real` 可选加餐（先例：Unit 2 全单元零 key 三态可验收）。
- 业务约定：金额一律整数「分」；返回码 `REJECT:<原因>` 枚举风格；明线素材唯一来源 `data/`。

**三态验证法**（涉及代码的改动必须实测）：

1. **发货态**「精确红」：只有设计内的失败（TODO 未填的 failed、meta 未过的 failed、ex3 类设计内 ruff 违规），讲义示例部分必须绿；
2. **毕业态**全绿：solution 覆盖进 /tmp 副本后，三命令 + `ruff format --check` 全部通过；
3. `scripts/check_lesson.py` PASS。

三态可用一条命令跑：`python3 scripts/three_state_check.py units/<unit>/<lesson>`（自动镜像
data/ 共享素材、覆盖 solution、跑全部命令；先例：L2.x 全课用它验收）。

## 6. 写一课的标准流程

1. 在 CURRICULUM 找课时定位（不做大纲外加课）；
2. 以 L0.1 目录结构为骨架复制（课时目录即独立 uv 项目）；
3. 写六段讲义 + code/ + exercises/（含 hints.py、meta-test）+ solution/；
4. `uv lock` 后 `uv sync`；
5. 跑三态验证（§5）；
6. 更新 README 路线图 checklist；
7. 提交外部 review——L0.1 先例：一轮 review 抓出 1 个参考答案 bug、2 个机制矛盾、1 个大纲缺口，此环节不可省；Unit 2 先例：一轮抓出 4 类系统性 P1。
8. 复盘修复轮的纪律（Unit 2 先例）：任何改动落地后**全量重跑三态**——改了验收相关文件而未重跑 = 证据链失效；**修 hints 前先读该题三方**（docstring/测试/solution）——修复本身也会引入语义回归（L2.2 的「错误回喂」口径被错搬进 L2.1 的「跳过」口径，P0）。三态已自动化为 `scripts/three_state_check.py`（支持课时与里程碑两种布局）。

## 7. 明确不做（防失焦）

- 不自研教学框架（hello-agents 第七章路线，直接指路）；
- 不写大部头理论（LLM/智能体史 → hello-agents 第一部分；MCP 深入 → mcp-for-beginners）；
- 远期才做：视频课 / 多语言 / 证书与榜单 / 在线阅读站 / 社区共创；
- 语言与领域红线：pandas 深入、Django、前端、可视化、ML 训练侧一概不进课表。

## 8. 文档地图与演进锚点

| 文档 | 角色 |
|---|---|
| [README.md](./README.md) | 对外入口：为什么 / 特色 / 课表 / 入学指南 / 路线图 |
| [CURRICULUM.md](./CURRICULUM.md) | 30 课时大纲 + 课时模板 + 练习机制 + 布局与纪律 |
| [research/agent-tutorials/](../research/agent-tutorials/) | 设计依据（创作输入，非发布物；landscape 元数据级 + report 教学机制级 + profiles ×8） |
| `units/unit0-toolchain/L0.1-uv-toolchain/` | 六段式打样板（结构基准，以它为准复制） |

演进关键决策（变更前先读）：个人学习计划 → 教程化；命名 `java2agent` →（歧义）→ `py-night-school`（机构隐喻可开新课、品牌伞）；Unit 1 补异常处理课（review 缺口）；「单元 = 学期」改「学段」；Unit 2 全单元交付 + 两轮复盘（对照组教学法落地：离线 mock 端点 + 剧本模型使零 key 可验收；锚定 mcp SDK 2.x——FastMCP 已改名 MCPServer，网上教程多为 1.x；2026 版 ruff 会 format Markdown 代码块，每课 pyproject `extend-exclude = ["*.md"]`）；**在线阅读站提前落地**（§7 远期项 → handbook/ 原型：units/ 的 MD 仍是唯一事实源与机器校验对象、站点是纯构建产物不手写、转换只作用于 .stage 副本且 fence 外、落地页渐进披露/对照表着色/灯卡先在站内演示、课程 MD 逐课采用前先在 §3/§4 补组件语法约定；过程志与踩坑实录沉淀 handbook/README.md）。拆仓原则：教程在 lab 仓内保持自包含，research 档案不随仓发布。

Unit 3 关键决策（先例与锚点）：①四框架同题 demo 的**共享件多课对版**（advice/mock_tools/review_rules/mock_endpoint 六课字节相同，test_contract 五课——L3.4 prebuilt 也带契约，展示「同题换装配」；改一处同步全部副本）；②新共享素材 `data/expense/review_mock.json`（expect_* 判分字段 + 覆盖型 meta），budget_mock.json 不动（Unit 2 兼容）；③框架依赖 == 钉到本地克隆 HEAD 对应版本，源码路标锚同一 commit（openai/openai-agents-python@fbd2dbca、langchain-ai/langgraph@e539ac122、langchain-ai/deepagents@9e7d62ff6、google/adk-python@7b246e01、langgenius/dify@79effdd498）；④L2.3 的 MockLLMEndpoint 全单元服役（框架模型客户端一律指向它，零 key 离线；adk 经 litellm 注意 `openai/` 前缀会被剥掉、传参用 api_base/api_key）；⑤openai-agents 第一件事 `set_tracing_disabled(True)`（trace 外发端点硬编码 api.openai.com，端点中立 ≠ trace 中立）；⑥L3.4 实测：Send 分支真并发（执行次序不保证）→ 批量剧本用「每单专属 mock 端点」；create_react_agent 在 prebuilt 1.1.0 已挂迁名 DeprecationWarning；⑦行数量化双口径并存：L3.8 决策表拆「装配 loc / 自写节点 loc」两列，milestone 工作台数「手写总行数」——列名不得再撞（先例：初版都叫「装配行数」学员无法自查）；⑧里程碑跨课重验（bench.py 子进程跑五课 contract）不得进 pytest——三态毕业态镜像不含兄弟课时，测试只用合成夹具，真跑是学员动作；⑨一轮外部 review 复盘（3 P1 + 择要 P2）：量化结论换 ast 实测口径（L3.4「约 40 loc」→20）、contract meta 补 reason 维度、adk web 目录约定以 cli 源码为准（每子目录一 agent.py）、骨架 TODO 注释泄底入 §4 新先例、计数与对版集合数逐处对齐（「共享件六课、契约五课」）。

Unit 4/5 关键决策（先例与锚点）：①**外部产品课型定式「机制抽取件 + 加餐」**（L3.7 先例推广入 CURRICULUM）：主线＝把产品核心机制对版搬到报销域（锚产品 commit、零 key 三态可验收），真跑产品与本地分支改造是可选加餐——产品仓不进课时依赖、不内置上万行代码；②Unit 4 三课沿**风控嵌入位置光谱**递进（dimensions/A §3：L4.1 处置层③ / L4.2 决策层② / L4.3 授权+执行层④⑤），「宣称 vs 实现对码」进课当教学点（TradingAgents README「PM 审批」无代码）；③产品锚定 HEAD：virattt/ai-hedge-fund@fc1bf25（**v2 全量重写版，v1 的 src/agents/ 结构已不存在——网上旧教程全部失效，讲义明示**）、TauricResearch/TradingAgents@be952b8、HKUDS/Vibe-Trading@f84b2977；④L4.3 零运行时依赖（纯标准库贴合产品 frozen dataclass 哲学）；flock/msvcrt 平台差异不进学员代码、就地注释声明合理差异；⑤Unit 5 四课**对版生长**：L5.2/L5.3 是 L5.1 的并行分支、L5.4 汇合（非线性叠加）——共享件字节相同为默认、演进差异 docstring 就地声明；EVENT_TYPES 封闭词汇表跨课登记制（9→12：gate.checked/payment.executed/gate.denied，新事件类型登记并全副本同灌）；⑥**JAVA-MAPPING 诚实纪律**：Java API 名必须到本地克隆核实（langgraph4j@c2cf2e33、alibaba/spring-ai-alibaba@f82da0b50——**org 前缀是 alibaba，曾误写 spring-ai-alibaba/ 造成 12 处死链，2026-09-18 锚点复核修复**）、不存在老实写「需自建」——先例：外审抓出 getDiagram/ChatLanguageModel 两个编造名改真（getGraph(GraphRepresentation.Type) / ChatModel）；⑦L5.2 实测坑：httpx ASGITransport 读不了常开 SSE 流——`?mode=replay` 重放面是产品正当形态，live 顺序断言走生成器直测，坑如实写进讲义；⑧Unit 5 milestone 布局方案 A（unit2 先例）：编码 TODO 放根模块（solution/*.py 覆盖得到——**覆盖不递归进 tests/**），文档件（JAVA-MAPPING）用两态 meta（有占位 ⇒ 必须有 solution 对照版，零占位 ⇒ 直接过）；⑨外审升级为**全实证**（宪法 §4 自查法真执行：hints 抄进练习文件跑验收、锚点到克隆验文件存在、数量词 collect-only 实数）——四轮 P0×1（L5.1 ex3 hints L2 泄底，实锤「抄过即全绿」）+P1×9+P2×13 全修并重跑三态。

通读评审修复轮（2026-09-18，先例与锚点，评审档案见 [reviews/](./reviews/2026-09-18-readthrough-review.md)）：**课间叙事层入模板**——每课 h1 后固定承接段（昨晚产出→今晚新问题→排位理由，blockquote），单元页承担结构地图（unit1 前置列 / unit3 光谱图 / unit4 双线倒挂 / unit5 树形），check_lesson 校验承接段与结尾段存在；**写作契约机器化**——§2 开头全课对照表、三命令块单贴、练习表头「| 题 | 文件 | 考察 |」、Step 命名统一、发货态说明独立行、「Step N（可选）」加餐定式；**知识点登记制**（CURRICULUM §2.1）：唯一主讲课 + 复现课指路，先例：推导式曾 L1.1/L1.4 双主讲修为互指；**内部坐标纪律**：作者元引用（宪法 §x / 调研 dimensions / 第 N 次登场）不进讲义，A 编号配 unit5 速查表，外部产品首现须一句话身份；**锚点复核命令化**：120 条锚点 gh api 全验，4 类死链（org 前缀 / FastMCP 改名 mcpserver / 目录更名）修复并同灌 JAVA-MAPPING 三副本。教训：单课视角的质量流水线（check_lesson + 单课外审）抓不住跨课叙事问题，全单元交付后应加一轮通读评审。
