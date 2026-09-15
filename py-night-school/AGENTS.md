# AGENTS.md — py-night-school 工作规范

> 本文档是教程项目的「宪法」：中心思想、课程设计理念与硬性纪律。**写课 / 改课 / 审课前必读**。
> 课表与课时明细见 [CURRICULUM.md](./CURRICULUM.md)；对外叙事见 [README.md](./README.md)；设计理念的方法论证据链见 lab 仓 [research/agent-tutorials/](../research/agent-tutorials/)（landscape + report + profiles ×8）。

## 1. 中心思想

- **一句话**：写给 Java 工程师的 Python Agent 开发晚课——以 agent 开发为场景学 Python，以 Java 心智模型为桥。
- **双目的**：学员既获得 Python 工程能力，也获得可带回 Java 栈的迁移地图（毕业设计产出 JAVA-MAPPING.md）。
- **受众红线**：只服务「Java 熟、Python 略懂」人群。Python 已熟练者、零基础者、想学 LLM 原理者——在 README「招生对象」明确指路别处，不为他们加课。
- **空档定位**（不摇摆）：市场上无人占据的交集 = Java 桥 × 练习自动验收 × 源码深度 × 金融毕业设计 × 端点中立。证据：research/agent-tutorials/report.md（八仓解剖：练习验收是全行业空白）。

## 2. 课程设计理念（六特色，README 为准，此处为索引）

1. **Java 心智桥**——概念先给对照表；坑位按「现象 / 最小复现 / Java 直觉为何失效 / 修复」四段命名化拆解；
2. **练习即测试**——TODO + pytest 自动验收，全绿即过关；
3. **对照组教学法**——Unit 2 手写 mini-agent 是全程对照组，OpenAI cookbook `Orchestrating_agents.ipynb` 是对照原件；
4. **源码路标**——`仓库@commit#路径`，读生产框架不读玩具；
5. **双贯穿线 + 金融毕业设计**——明线「报销单审查」从 L0.1 种下；暗线每课结尾「离毕业又近了一块」；
6. **夜校工程纪律**——竞品的系统性短板在这里默认不发生（见 §5）。

## 3. 课时模板：六段式（唯一结构，机器校验）

```
## 1. 本课目标        （一句话、可验证）
## 2. 概念讲解        （含 Java↔Python 对照表）
## 3. 动手代码        （Step 化，code/ 目录支撑）
## 4. 练习            （单变量编辑约束 + hints 渐进披露 + pytest 验收）
## 5. Java 人坑位      （命名化失败模式，四段式）
## 6. 延伸            （官方文档 + 源码路标 仓库@commit#路径）
+ 结尾固定段「离毕业又近的一块」（暗线进度）
```

话术约定：单元 = 学段、课时 = 晚课讲次、Unit 5 = 结业考；README 三个区块名固定为「招生对象 / 课表 / 入学指南」。

## 4. 练习机制（验收即毕业）

- **单变量编辑约束**：练习文件首行注释声明只改 TODO 区；验收测试文件头部注明「不要改本文件」。
- **hints 三级渐进**：第 1 级只给方向、第 2 级给形状、第 3 级才是接近完整的做法——答案只在最后一级（先例教训：初版第 1 级泄底被 review 打回）。
- **三方对齐**：题目 docstring、hints、pytest 断言同一口径。
- **覆盖型练习配 meta-test**：题目要求是对用例表的覆盖时，验收测试直接检查用例表本身（结果种类 / 边界 / 数量）——先例：L0.1 ex2，它抓到的第一个 bug 就在参考答案里。
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
- 业务约定：金额一律整数「分」；返回码 `REJECT:<原因>` 枚举风格；明线素材唯一来源 `data/`。

**三态验证法**（涉及代码的改动必须实测）：

1. **发货态**「精确红」：只有设计内的失败（TODO 未填的 failed、meta 未过的 failed、ex3 类设计内 ruff 违规），讲义示例部分必须绿；
2. **毕业态**全绿：solution 覆盖进 /tmp 副本后，三命令 + `ruff format --check` 全部通过；
3. `scripts/check_lesson.py` PASS。

## 6. 写一课的标准流程

1. 在 CURRICULUM 找课时定位（不做大纲外加课）；
2. 以 L0.1 目录结构为骨架复制（课时目录即独立 uv 项目）；
3. 写六段讲义 + code/ + exercises/（含 hints.py、meta-test）+ solution/；
4. `uv lock` 后 `uv sync`；
5. 跑三态验证（§5）；
6. 更新 README 路线图 checklist；
7. 提交外部 review——L0.1 先例：一轮 review 抓出 1 个参考答案 bug、2 个机制矛盾、1 个大纲缺口，此环节不可省。

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

演进关键决策（变更前先读）：个人学习计划 → 教程化；命名 `java2agent` →（歧义）→ `py-night-school`（机构隐喻可开新课、品牌伞）；Unit 1 补异常处理课（review 缺口）；「单元 = 学期」改「学段」。拆仓原则：教程在 lab 仓内保持自包含，research 档案不随仓发布。
