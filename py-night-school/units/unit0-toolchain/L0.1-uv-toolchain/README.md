# L0.1 环境与工具链：从 Maven 到 uv

> 欢迎入学。这门课**克隆即学**：仓库拉下来就是全部教材，每课目录是一个独立的 uv 项目，进目录让
> `uv run pytest` / `uv run ruff check .` / `uv run pyright` 三条命令同时全绿，即本课毕业；卡住了
> 先翻该课的「Java 直觉陷阱」小节——你将踩的坑，前人都已命名归档。今晚第一课只干一件事：把
> uv / pytest / ruff / pyright 工具链一次配齐，之后 29 课都踩在这套地基上开工。

## 1. 本课目标

配齐夜校工具链，并种下「报销单审查」明线的第一颗种子。完成后你能：

- 用 uv 创建、同步、运行一个 Python 项目（对应你闭着眼能敲的 mvn 工作流）；
- 用 pytest 让测试当你的「验收老师」——这是之后 29 课的过关方式；
- 让 ruff 与 pyright 守住代码质量（Checkstyle + IDEA 检查的等价物）；
- 说清 `.env` 三变量约定：为什么夜校不绑定任何模型厂商。

**完成判据**：本目录下三条命令同时全绿——

```bash
uv run pytest          # 练习验收全绿
uv run ruff check .    # 无 lint 违规
uv run pyright         # 无类型错误
```

## 2. 概念讲解：工具链对照表

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| JDK（多版本用 SDKMAN/jenv 管） | Python 解释器（`uv python install 3.12`） | 解释器也归包管理器管，一个工具全覆盖 |
| Maven（pom.xml） | uv（pyproject.toml + uv.lock） | 依赖声明与锁定分离，uv.lock 类似你用 CI 强制生成的锁定版本 |
| `mvn dependency:resolve` / test scope | `uv sync` / dev 依赖组 | `uv add --dev` ≈ test scope，不进生产依赖 |
| `mvn exec:java` / jbang | `uv run` / `uvx` | uvx 临时拉起工具不污染当前项目 |
| JUnit 5 + AssertJ | pytest | 没有注解仪式：函数名 `test_` 开头即是测试，`assert` 是语言关键字 |
| Checkstyle + Spotless | ruff | lint + format 二合一，毫秒级 |
| IDEA 实时编译检查 | pyright | Python 类型标注是可选的——夜校要求全程标注，把它当回 javac |
| jshell | Jupyter / IPython | 可以存图、存代码块的超级 REPL |
| classpath 天然隔离 | venv（uv 每项目自动建 `.venv/`） | Java 没有的痛点，Python 用虚拟环境解决 |

**pyproject.toml vs pom.xml 段落对照**：

| pyproject.toml | pom.xml |
|---|---|
| `[project] name / version / requires-python` | `<groupId>/<artifactId>/<version>` + 编译目标 |
| `[project.dependencies]` | `<dependencies>`（compile scope） |
| `[dependency-groups] dev = [...]` | `<scope>test</scope>` 依赖 |
| `uv.lock`（自动生成，提交进仓） | （Maven 无直接对应；相当于 enforcer 插件钉死的版本树） |

语言运行模型差异（解释执行、GIL、动态类型）属于 Unit 1 的正餐，今晚不展开——你只需要知道：**工具链层面，Python 世界已经收敛到 uv 一把梭**，这是我们今晚配它的原因。

## 3. 动手代码

### Step 1 安装 uv（10 分钟）

```bash
# macOS / Linux（官方独立安装器，装到 ~/.local/bin，不碰系统目录）
curl -LsSf https://astral.sh/uv/install.sh | sh
# 按提示把 ~/.local/bin 加进 PATH，或：
source $HOME/.local/bin/env
uv --version
```

```powershell
# Windows（PowerShell）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv --version   # 新开一个终端后生效
```

### Step 2 网络受限配置（国内环境建议，5 分钟）

```bash
# macOS / Linux（PyPI 镜像，写入 ~/.zshrc 持久化）：
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
# （可选）uv 下载 Python 解释器走镜像：
export UV_PYTHON_INSTALL_MIRROR=https://gh-proxy.com/https://github.com/astral-sh/python-build-standalone/releases/download
```

```powershell
# Windows（PowerShell）
$env:UV_DEFAULT_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"      # 当前会话
setx UV_DEFAULT_INDEX "https://pypi.tuna.tsinghua.edu.cn/simple"        # 持久化（新终端生效）
```

Node 也提前说清：pyright 需要 Node 运行时，本项目已把 `nodejs-wheel-binaries` 钉进 dev 依赖——Node 随 PyPI 安装（走上面的镜像），不会去 nodejs.org 直连下载；你机器上若已有 Node，pyright 也会直接复用。

### Step 3 理解本课项目（5 分钟）

本课目录**已经是一个配好的 uv 项目**（克隆即学，不必自己 init）。先看结构再同步：

```
L0.1-uv-toolchain/
├── pyproject.toml     # 依赖与工具配置（对应 pom.xml）
├── uv.lock            # 锁定的依赖版本树（已提交，保证你和我跑的完全一致）
├── .env.example       # 模型端点三变量约定（L2 才真正用）
├── code/              # 讲义示例：报销预审纯函数 + 它的测试
├── exercises/         # 你的练习（本课过关的地方）
└── solution/          # 参考答案（完成练习前别看）
```

```bash
cd units/unit0-toolchain/L0.1-uv-toolchain
uv sync               # 创建 .venv 并按 uv.lock 安装（≈ mvn dependency:resolve + test scope）
```

想体验「从零建项目」的话，找个临时目录依次跑 `uv init demo`、`cd demo`、`uv add --dev pytest`——感受与 `mvn archetype:generate` 的对应关系。

### Step 4 跑通讲义示例（15 分钟）

打开 `code/budget.py`：**报销单预审**——这是明线「报销单审查」的核心规则，纯函数、金额用整数「分」（Java 里 `long` 存分的习惯，在 Python 同样成立，还天然避开浮点误差）。三条规则：

1. 任意金额 ≤ 0 → `REJECT:INVALID_AMOUNT`（脏数据最先挡）；
2. 任意单笔 > 5000 分（50 元）→ `REJECT:ITEM_OVER_LIMIT`；
3. 合计 > 500000 分（5000 元）→ `REJECT:TOTAL_OVER_LIMIT`。

```bash
uv run pytest code/        # 讲义测试应全绿（它不是你的练习，是示例）
uv run ruff check code/    # 示例代码无违规
uv run ruff format --check code/   # 格式符合规范
```

看一眼 `code/test_budget.py` 里的 `@pytest.mark.parametrize`——它对应 JUnit 5 的 `@ParameterizedTest`，但只需要一个装饰器 + 一个元组表。（`@` 是装饰器语法，L1.5 才主讲——今晚照抄这一行即可。）

### Step 5 体验 ruff 当老师（5 分钟）

```bash
uv run ruff format .       # 一键格式化（≈ Spotless apply）
uv run ruff check .        # 全仓检查——现在 exercises/ 里有练习 3 留的 3 处违规，这正是你要修的
```

### Step 6 pyright 类型检查（5 分钟）

```bash
uv run pyright
```

`code/budget.py` 的每个函数都有完整的类型标注（`list[int] -> str`）。Python 的类型是「可选的」——但夜校全程要求标注，理由和你在 Java 里的体感一致：**类型是给读代码的人和 IDE 看的，不是给解释器看的**。

（Node 从哪来：pyright 的解析顺序是 ① 依赖里的 `nodejs-wheel-binaries`——随 PyPI 走镜像；② 系统 Node——装过就直接复用；③ 在线下载——我们从不依赖这条慢路。）

### Step 7 断点调试与 IDE 接入（15 分钟，对照 IDEA）

先体验最原始的方式——命令行：

```bash
uv run python code/debug_demo.py
```

程序在 `breakpoint()` 处暂停，进入 pdb（Python 内置调试器，零安装；`breakpoint()` 等价于 IDEA 里的红点）。常用命令对照：

| pdb | IDEA / VS Code 对应 |
|---|---|
| `n`（next） | Step Over |
| `s`（step） | Step Into |
| `c`（continue） | Resume |
| `p 变量名` | Evaluate Expression |
| `q` | Stop |

试试在暂停时输入 `p items_cents`（不行的话就 `p [1200, 8800]`）、`n`、`c`。

然后选一把称手的 IDE（**二选一，今晚定下来，后面 29 课都靠它**）：

| 选择 | 适合谁 | 备注 |
|---|---|---|
| VS Code + Python 扩展（Pylance） | 想轻快、贴近 Python 社区主流 | **Pylance 就是 pyright 的微软发行版**——终端里跑的 pyright 检查和 IDE 里是同一套引擎，工具链故事闭环；再装 ruff 官方扩展，format/lint 直接进 IDE |
| PyCharm（Community 版够用） | 重度 IDEA 用户 | 键位与操作习惯零迁移，JetBrains 全家桶体验；装 ruff 插件补齐 lint/format |

共同动作：用 IDE 打开本课目录（`L0.1-uv-toolchain/`），`.venv` 解释器会被自动识别；右键 `code/test_budget.py` → Run / Debug（图形化跑 pytest）；给 `code/debug_demo.py` 打一个图形化断点跑一遍——刚才 pdb 的 `n`/`s`/`c`/`p` 在这里全是按钮。

### Step 8 模型端点约定（5 分钟）

```bash
cp .env.example .env   # Windows: copy .env.example .env；然后填入你的端点，L2 之前不用真的填
```

三变量的含义：`OPENAI_BASE_URL`（任一 OpenAI 兼容端点：GLM / DeepSeek / Qwen / vLLM 本地……）、`OPENAI_API_KEY`、`MODEL_NAME`。这是夜校「端点中立」的落地——微软课程绑 Azure Foundry，我们只绑「OpenAI 兼容协议」这一个约定。

### Step 9（可选）Jupyter 草稿纸（10 分钟）

```bash
uv run --with jupyter jupyter lab
```

以后调 prompt、试 API 返回结构，都在这里草稿——不用装进任何项目。

### Step 10 看一眼你的未来客户（3 分钟）

打开 `data/expense/budget_mock.json`：三张报销单（一张合法、一张单餐超标、一张录了负数）。**Unit 2 的 mini-agent 将对它们调用你今晚写的 `preapprove()`；Unit 5 的毕业设计会给它加上审批流**。今晚你手写了规则本体。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——每题只改标注的 TODO 区，其余文件与代码区不要动。卡住先想 5 分钟，再看渐进提示（`uv run` 命令跨平台，Windows 学员不用纠结 python3/py）：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_preapprove.py` | 补全 `preapprove()` 三条规则（基础语法：循环 / any / sum） |
| ex2 | `exercises/test_ex2_cases.py` | 补全参数化用例表：四种结果各≥1 组、含边界（恰好等于上限应 PASS）、共≥5 组——覆盖是否达标由文件内的 meta-test 机器验收，全 PASS 用例混不过去 |
| ex3 | `exercises/ex3_ruff_fix.py` | 修复 3 处 ruff 违规（F401 未用 import / F841 未用变量 / E501 超长行——单字符串字面量，`ruff format` 拆不了它） |

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 直觉陷阱：缩进即语法

这是你在 Python 的第一个「命名化失败模式」，以后说「缩进即语法」我们秒懂。

- **现象**：`IndentationError: expected an indented block`——编译期就炸；更危险的是不报错的静默变体：多缩进一层，代码跑进了一个它不该在的 `if` 分支里，逻辑悄悄变了。
- **最小复现**：

  ```python
  def check(amount: int) -> str:
  if amount > 5000:          # IndentationError：def 体必须缩进
      return "REJECT"

  def check2(amount: int) -> str:
      if amount > 5000:
          return "REJECT"
      return "REVIEW"        # 把这行改成与 return "REJECT" 同级缩进，语义就变了——但没有报错
  ```

  **验证一个惊喜**：把 `check2` 的 `return "REVIEW"` 缩进进 `if` 块里（上面的静默变体），pyright 会立刻标红——声明的返回类型是 `str`，而函数出现了一条「什么都不返回就结束」的路径。这个坑不是无解，工具链兜得住。

- **Java 直觉为何失效**：Java 里花括号是语法、缩进只是风格；Python 里**缩进就是语法**（等价于每个块都有隐式 `{ }`），Tab 和空格混用甚至直接 `TabError`。
- **修复与纪律**：统一 4 空格（别手输 Tab）；让编辑器把 Tab 转空格；提交前 `uv run ruff format .` 一键归一——格式问题尽量交给工具，但格式化器**永远不会改写字符串内容**（练习 3 的 E501 就是为这条能力边界设计的）。

## 6. 延伸

- uv 官方文档（概念与全部命令）：https://docs.astral.sh/uv/
- pytest 官方入门：https://docs.pytest.org/en/stable/getting-started.html
- ruff 官方文档（规则一览）：https://docs.astral.sh/ruff/rules/
- openai/openai-cookbook@9aad95f#articles/what_makes_documentation_good.md —— OpenAI 的「好文档写作宪法」，本教程讲义规范的同源出处；读它能让你具备鉴别好教程/坏教程的眼光。
- microsoft/mcp-for-beginners@2f43408b#03-GettingStarted —— 它的「练习三层结构」（Exercise 步骤引导 → Assignment 开放作业 → solution 分离）是本课练习机制的设计先例之一，Unit 2 讲 MCP 时还会回来。

## 离毕业又近的一块

`preapprove()` 就是毕业设计「fail-closed 执行门」里**限额检查**的雏形（纯函数、整数分、可参数化测试）。到 Unit 5 你会把它升级成检查链：授权有效 → kill switch → 对账 → 限额三态裁决——今晚你已经写下了最后一环的种子。
