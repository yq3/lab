# 教程解剖综合报告：课程设计与教学方式（teaching-analysis）

> **输入**：[profiles/](./profiles/) 8 份逐仓解剖档案（2026-09-15 四路并行完成，代表性课时均全文精读，证据可溯源到本地克隆路径）。
> **视角**：为 py-night-school（Java 工程师 × Python Agent 夜校）提炼课程设计与教学方式的横向结论与设计更新。
> **与 [landscape.md](./landscape.md) 的分工**：landscape 回答「市场上有什么、我们补什么空档」（README/元数据级）；本报告回答「他们怎么教、我们怎么教得更好」（课时内容级）。

## 1. TL;DR：五条最大启发

1. **练习验收是全行业空白，但零件齐全**。8 仓中 7 仓无自动验收闭环（MS 系 quiz 答案分离但仅 1 课有 quiz；hello-agents 习题无答案、测试是 print 脚本；langchain-academy 三十本 notebook 零练习零验收；cookbook 根本不是课）；唯二例外是 HF（quiz + GAIA benchmark 全自动，但全外置在 HF Space）和 Anthropic prompt-eng 课（notebook 内嵌正则评分器）。我们的 TODO+pytest 差异化主张**成立且无先例可整体照抄**，但有四个可拼装件（见 §3.1）。
2. **对照组教学法被三处独立印证**：MS 04 课先手写裸 API tool-call 循环再上 `@tool` 装饰器；HF 用 40 行 `dummy-agent-library` 先让学习者体会幻觉 Observation 之苦再引出框架；OpenAI cookbook 的 `Orchestrating_agents.ipynb` 就是「无框架手写 mini-agent」的官方原典（run_full_turn 循环 + tools_map 分发 + handoff，最后才引出 Swarm）。我们的 Unit 2→Unit 3 主线有官方级同构先例，且后者可直接引用为对照原件。
3. **贯穿叙事线是高质量课程的共同骨架**：MS 的 STUDY_GUIDE 用一个 course helper agent 贯穿 18 课（每课问「demo agent 多了什么能力」）；HF 用 Alfred 管家串起一课所有代码；mcp-for-beginners 用同一个 calculator 三级演化（server → client → LLM client）；langchain-academy 的模块以毕业项目收束且被后续课复用。**我们的「报销单审查」应从 L0.1 就种下、毕业设计每课长一块**，而不是 Unit 3 才出现。
4. **工程纪律是竞品的系统性短板**：版本钉死与 notebook 内 `%pip install -U` 自相矛盾（MS）、依赖 pin 分裂 0.2.18 vs 0.2.76（GenAI_Agents）、同一课程三份手工拷贝漂移（Anthropic）、图片全外链 CDN（langchain-academy）、教学主体在仓外导致克隆后「无处可跑」（HF）。夜校的 uv.lock + 图片本地化 + 仓库自包含要作为**显性卖点**来做。
5. **OpenAI 已替我们写好了讲义写作宪法**：cookbook 的 `articles/what_makes_documentation_good.md` 主张标题写信息句、结论前置不做苏格拉底式铺垫，原文甚至举例「even an expert Java engineer might be a beginner at Python」——与我们的受众设定完全撞车，直接采纳为讲义规范。

## 2. 横向对比矩阵

评级：✅ 有且成体系 / 🔶 有但不成体系 / ❌ 无。证据见各档案 §4。

| 仓 | 练习形态 | 自动验收 | 答案披露设计 | 代码组织 | 版本纪律 | 贯穿叙事 | 结业机制 | 仓库自包含 |
|---|---|---|---|---|---|---|---|---|
| ai-agents-for-beginners | 🔶 1/18 课有 quiz | 🔶 部署后 smoke-test（非达标门槛） | 🔶 solution/ 分离 | 全仓共享单 requirements（钉版但自相矛盾） | 🔶 | ✅ demo agent + STUDY_GUIDE | ❌ | 🔶 绑 Azure（留 3 条解绑后门） |
| mcp-for-beginners | ✅ Exercise 步骤编号 + Assignment | ❌（唯一范本：协议级 test_calculator.py） | ✅ solution/<五语言>/ 分离 | 每课每语言独立工程（Java 侧完整 Spring Boot） | 🔶 | ✅ calculator 三级演化 | ✅ Module 11 capstone（讲义/代码分仓） | 🔶 单课膨胀至 1382 行 |
| hello-agents | 🔶 开放设计题、无答案 | ❌（test_*.py 为 print 脚本） | ❌ | code/ 与章节一一对应 + .env 三变量 | 🔶 | 🔶 | ✅ 毕业设计=开源 PR 共创（49 个学员项目） | ✅ |
| huggingface-agents-course | ✅ 两级 quiz（错项带解释 / 私有题库） | ✅ quiz + GAIA benchmark 全自动 | ✅ 开放/认证分级 | 执行全外置（Colab 链接） | ❌ | ✅ Alfred 管家 | ✅ 单元证书 + GAIA 总证（30% 线） | ❌ 本地克隆后无处可跑 |
| GenAI_Agents | ❌ | 🔶 仅作者自用（notebook 加载器） | — | notebook 自包含 + validate_notebook.py 机器校验 | ❌ pin 分裂 | 🔶 | ❌ | ✅ |
| langchain-academy | ❌ 零练习零 solution | ❌（课尾给期望输出字面量） | — | notebook + studio/*.py 双形态同构 | ❌ 宽松 pin | ✅ 毕业项目被复用 | ✅ 模块级 capstone | ❌ 导航靠仓外徽章 |
| anthropics-courses | ✅ 14/20 题有内嵌评分器 | 🔶 正则判分（notebook 内） | ✅ hints.py 渐进披露 | 单变量编辑约束 | ❌ 三份拷贝漂移 | ✅ FakeDatabase 假世界 | ❌ | ✅ |
| openai-cookbook | ❌（recipe 集非课程） | ❌ | — | recipe=notebook+包+prompts/*.md 外置+独立 requirements | 🔶 | 🔶（金融例有完整产物当样张） | — | 🔶 导航主入口在站外 |

## 3. 机制专题（证据 → 启发 → 落地）

### 3.1 练习与验收：全行业空白与四个可拼装件

**证据**：见矩阵「自动验收」列；细节在各档案 §4.1。四个可拼装件：

1. **Anthropic 的内嵌评分器**（prompt-eng 课）：练习 cell 内跑 `grade_exercise` 正则判分、即时出 `------ GRADING ------` 横幅；判分标准在 hints 里第一句复述——**题目 / 提示 / 答案三方对齐同一验收口径**。开放题诚实降级为素材行尾注释 golden answer，不硬造判分。
2. **GenAI_Agents 的 notebook 加载器**（`tests/test_hitl_approval_agent.py`）：把 notebook 的 code cells 逐个 exec 进 module 命名空间再行为断言——**学员在 notebook 里填 TODO、pytest 在仓里验收**的现成机制。
3. **HF 的题库/验收器分离**：quiz 题库 JSON 与评分 Space 分离；轻练习开放（答案明文在 MDX）、认证练习封闭（私有题库）——两级披露策略。
4. **mcp-for-beginners 的协议级集成测试**（`samples/python/test_calculator.py`）：subprocess 拉起真 MCP server、以 JSON-RPC 断言 `tools/list` 与协议协商——L2.5 MCP 课的验收可以直接仿写。

**落地**：练习机制升级为——`exercises/` 挖空 + `uv run pytest` 判定（主）；每题配 `hints.py` 渐进披露（需显式 import，防偷看）；题目注释、hints、pytest 三方对齐同一口径；开放设计题不硬造判分、给行尾 golden answer（诚实降级）；MCP 课做协议级集成测试。

### 3.2 对照组教学法：三处独立印证 + 一件对照原件

MS 04 课、HF dummy-agent-library、cookbook `Orchestrating_agents.ipynb` 三处先例（§1.2）。另 GenAI_Agents 的「同模式双框架实现」（LangChain 版 / `-pydanticai` 后缀版）证明**同一验收可以跑两份骨架**——Unit 3 四框架同题 demo 的验收脚本可以只写一份。

**落地**：L2.3 手写循环课直接引用 cookbook `Orchestrating_agents.ipynb` 为「对照原件」延伸读物；Unit 3 每框架课的「与 mini-agent 对照」固定加一问：*这一层抽象替我付掉的代码，在 cookbook 原典里是哪几行？*

### 3.3 贯穿叙事线：从「最后才有」到「每课长一块」

**证据**：STUDY_GUIDE 的 8 部件映射表 +「每课学完问 demo agent 多了什么能力」；langchain-academy 毕业项目 task_maistro 被部署课直接复用；cookbook 金融多 agent 例（multi-agent-portfolio-collaboration）内嵌完整真实产物（5 节投资备忘录）当「验收样张」。

**落地**：夜校设**双贯穿线**——明线「报销单审查」（Unit 0 即以它配环境变量与 mock 数据，Unit 3 换框架重做）；暗线「财务 agent 毕业设计」（每课结尾一行「离毕业又近了一块」：本课能力在毕业设计里对应哪个模块）。毕业设计参考实现里放一份完整「验收样张」产物（一张带审批链的报销建议单）。

### 3.4 坑位环节的结构化：失败模式命名学

**证据**：MS 12 课（上下文工程）把故障按四种失败模式命名——poisoning / distraction / confusion / clash，各按 What / Example / Solution 四段展开，零代码纯例子贯穿；GenAI_Agents 新代 notebook 的「叙事式对照实验」（同一句修复分别放 system prompt 与 loop 内，只有一处生效）。

**落地**：六段式模板的「Java 人坑位」升级为**命名化失败模式**：每个坑起一个可检索的名字（如「假 await 坑」「可变默认参数坑」），按 现象 / 最小复现 / Java 直觉为何失效 / 修复 四段写；能做成对照实验的（如 asyncio 阻塞）写成同一份代码两处改动看差异。

### 3.5 文档路标与仓库自包含

**证据**：langchain-academy 每个 API 术语超链官方文档精确锚点、教程本体刻意写薄（值得学）；但其导航靠仓外 Colab/Academy 徽章、HF 执行全外置 Colab——克隆后不自包含（反面）；mcp Module 11 讲义/代码分仓 + 外链（需钉 commit 防 drift）。

**落地**：每课「延伸」段的源码路标统一格式：`仓库名@commit#路径`（commit 锚点必写）；本仓讲义内所有必要内容自包含（克隆即学），外链只做加深不承载主线。

### 3.6 notebook 与 .py 的验收锚点

**证据**：langchain-academy 每课 graph 在 `studio/*.py` 逐行复刻并经 `langgraph.json` 注册（notebook 讲解、.py 承载可测实现）；GenAI_Agents 的 validate_notebook.py 对模板做机器校验（8 个必需章节、每 code cell 前必有标题、无输出残留）。

**落地**：夜校约定——**讲义用 md、动手用 code/（.py 为主，Jupyter 仅语言实验课用）、验收只测 .py**；写一个 `scripts/check_lesson.py` 机器校验六段式模板完整性（章节齐全、练习有 TODO、pytest 存在、源码路标带 commit），纳入我们的 CI 习惯。

### 3.7 数据与素材复用

**证据**：cookbook `examples/data/` 的代码/数据分离纪律（大数据不进仓、讲义写获取命令），且 `NotRealCorp_financial_data.json`（虚构财报）、`labelled_transactions.csv`（标注交易）、`10k/`（真实 Lyft/Uber 年报 PDF）可直接复用；hello-agents 的 `.env` 三变量约定贯穿全书。

**落地**：夜校建 `data/` 共享素材层（报销/预算/发票 mock 从 Unit 0 用到毕业设计），金融素材优先复用 cookbook 上述三件（注意引用其获取命令而非拷贝大文件）；.env 约定从 L0.1 固定（`OPENAI_BASE_URL` / `OPENAI_API_KEY` / `MODEL_NAME` 三变量，端点中立落地）。

### 3.8 结业与社区机制（远期参考）

hello-agents 的毕业设计 = 开源 PR 共创（命名规范 `{用户名}-{项目名}`、README 模板、PR 自检清单，沉淀 49 个学员项目）；HF 的「单元 checkpoint 徽章 + 毕业总验收」两级激励、学完与认证解耦。夜校近期只做**结业自查清单**（CURRICULUM §7 已有）；拆仓开源后再引入共创毕业设计（hello-agents 模式）与徽章体系（HF 模式）。

## 4. 对 py-night-school 的设计更新清单

以下决策已同步进 [CURRICULUM.md](../../py-night-school/CURRICULUM.md) §2/§3/§4/§6（标注「依据调研报告」）：

1. **课时模板**：练习段细化（单变量编辑约束——练习文件首行注释 `# 只改这个文件`；hints 渐进披露）；坑位段升级为命名化失败模式（现象/最小复现/Java 直觉失效点/修复四段）。
2. **练习机制**：补「答案与讲解分离（solution/ 不在学员主线视野）」「题目/hints/pytest 三方对齐验收口径」「开放题诚实降级为行尾 golden answer」。
3. **课表**：Unit 0 起即种下双贯穿线（报销 mock 数据 + 毕业设计进度提示），Unit 3 验收脚本同题复用（一份脚本跑四框架骨架）。
4. **工程纪律（并入 §6）**：每课独立 uv 项目 + uv.lock 钉版；源码路标一律 `仓库@commit#路径`；图片本地化不外链；外链延伸锚 commit；`scripts/check_lesson.py` 机器校验模板。
5. **延伸池更新**：cookbook `Orchestrating_agents.ipynb`（对照组原典）、`what_makes_documentation_good.md`（讲义写作宪法）、`examples/data/` 金融三素材；MS 12 课（失败模式命名学范例）；HF dummy-agent-library（对照组先例）。

## 5. 本报告的边界

- 8 仓的「单课解剖」各只深读 1-2 个代表性课时（档案 §3 已注明是哪些），横向结论建立在抽样上；引用某仓具体做法前请先查对应档案的证据路径。
- star 数与课程热度不反映教学质量——本报告只评内容与机制，不评传播。
- 框架版本快变是共同背景：所有「代码组织/版本纪律」结论锚定档案头部记录的 HEAD 基线（2026-09-04 ~ 09-12）。
