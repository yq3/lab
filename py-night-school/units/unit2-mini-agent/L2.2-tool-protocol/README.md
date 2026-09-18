# L2.2 工具协议：Pydantic 模型 → JSON Schema → 注册表

> 昨晚你的 `client.py` 裸调端点走通了工具调用两回合——`tools` 下行、`tool_calls` 上行、
> `role=tool` 回喂，也亲手拆封了一次「字符串套娃」（`arguments` 是一层 JSON 字符串）。
> 今晚让那份手抄的工具契约下岗：形状改由 Pydantic 参数模型声明、schema 一键生成、
> 函数定义即注册——五块肌肉的第二块（工具层）。

## 1. 本课目标

把昨晚手写的工具契约升级成「单一事实源」的工具注册表。完成后你能：

- 用 Pydantic 参数模型声明工具的形状，`model_json_schema()` 一键生成端点看得懂的契约——
  并说清约束怎么映射进 JSON Schema（`gt` → `exclusiveMinimum`、`min_length` → `minItems`）；
- 写 `@tool(ArgsModel)` 带参装饰器（L1.5 三层结构的真实落地），函数定义即注册；
- 写 `run_tool` 分发器：`model_validate_json` 一步完成「解析 + 校验 + 类型收敛」——
  昨晚的「字符串套娃坑」从手工拆封升级为工程级拆封；
- 说清「回喂不抛」的错误哲学：unknown / invalid / tool_error 三态都是**给模型的修复指令**，
  以及「schema 管形状、规则管业务值」的校验分层纪律。

**完成判据**：本目录下三条命令同时全绿——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

发货态诚实说明：`code/` 讲义区绿，`exercises/` 是设计内的红（TODO 未填）。
本课依赖：`pydantic>=2` + `httpx`（L2.1 的 `client.py` / `mock_endpoint.py` /
`env_loader.py` 原样搬来，`uv sync` 一次装齐）。

## 2. 概念讲解

先给全课对照表，再逐个展开：

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| springdoc 从 DTO 生成 OpenAPI schema | `model_json_schema()` | 契约从类型生成，不是手抄——同一思想 |
| `@Component` + classpath 扫描 + `Map<String, Method>` 白名单 | `@tool(ArgsModel)` + `TOOL_REGISTRY` | 一个 dict + 装饰器副作用，「工具发现 = 查表」 |
| Jackson `readValue` + Bean Validation 两道工序 | `model_validate_json()` | 解析、校验、类型收敛压成同一次调用（L1.3 三合一的兑现） |
| Javadoc（不进运行时） | docstring 第一行 | 「文档即数据」：描述直接进 schema 广告给模型 |
| 全局 `@ExceptionHandler` 往上抛 | error JSON 回喂 | 异常服务调用栈，回喂服务模型——错误是给模型的修复指令 |

### 2.1 昨晚的三个问题

L2.1 我们手写了工具契约（那个 dict）并手工回喂——三个问题在真实项目里都会长大：

1. **重复**：`PREAPPROVE_TOOL` 的 schema 手写一遍，函数签名又写一遍，同一形状写两次；
2. **漂移**：函数改了参数名，schema 忘了改——模型按旧契约调用，运行时 `TypeError`（§5 坑位）；
3. **裸奔**：`json.loads(arguments)` 拆封后没有任何校验，`{"items_cents": "八千八"}` 直达业务函数。

本课的答案是把「参数的形状」声明成 Pydantic 模型，**声明一次，两头使用**：

```text
            ┌────────────── 对外（给模型看）─────────────┐
PreapproveArgs ── model_json_schema() ──> tools 载荷的 parameters
      │
      └──── model_validate_json() ──> 对内（模型回的 arguments）
                 解析 + 校验 + 类型收敛一步完成，再 func(**args.model_dump()) 调用
```

对照 Java：这就是 springdoc/OpenAPI 从 DTO 生成 schema 的思路——**契约从类型生成，
而不是手抄**。差别在于 Pydantic 的模型同时是运行时的解析校验器（Jackson + Bean Validation
合体，L1.3 讲过的三合一在这里兑现）。

### 2.2 `model_json_schema()`：契约长什么样

```bash
uv run python code/demo_schema.py
```

```text
== GetClaimArgs 的 JSON Schema（关注 required 与 pattern） ==
{
  "description": "get_claim 的参数形状：单号格式用 pattern 在门口拦住幻觉单号。",
  "properties": {
    "claim_id": {
      "description": "报销单号，形如 CLM-2026-0001",
      "pattern": "^CLM-\\d{4}-\\d{4}$",
      "title": "Claim Id",
      "type": "string"
    }
  },
  "required": [
    "claim_id"
  ],
  "title": "GetClaimArgs",
  "type": "object"
}
```

读法：`properties` 是每个字段的形状与约束；`required` 是无默认值的字段名单。
约束的映射表（ex1 的考点）：

| Pydantic 约束 | JSON Schema 键 | 语义 |
|---|---|---|
| `Field(gt=0)` | `exclusiveMinimum: 0` | 开区间下界 |
| `Field(min_length=1)`（list） | `minItems: 1` | 至少 1 个元素 |
| `Field(pattern=r"^CLM-...")` | `pattern` | 正则（JSON 里 `\\d` 是转义的转义） |
| 无默认值 | 进 `required` | 模型必须给 |

两个值得知道的细节：给字段加默认值（`limit: int = 10`）它会**从 `required` 消失**——
契约从此告诉模型「可省略」；`description`（模型级与字段级）会原样进 schema，
**这是写给模型看的提示词**，值得认真写。

### 2.3 注册表：`@tool` 装饰器与查表分发

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    func: Callable[..., str | int]

TOOL_REGISTRY: dict[str, ToolSpec] = {}

@tool(PreapproveArgs)
def preapprove(items_cents: list[int]) -> str:
    """对报销单明细金额做规则预审，返回 PASS 或 REJECT:<原因>。"""
    ...
```

`@tool(ArgsModel)` 是 L1.5 的带参装饰器三层结构（工厂收参数 → 装饰器收函数 →
wrapper 转发调用），多做的只有一件事：造 `ToolSpec` 存进注册表。名字取 `__name__`，
描述取 **docstring 第一行**——「文档即数据」是 Python 生态的普遍约定（FastAPI 的接口
文档、pytest 的用例名全是这么来的）。对照 Java：Javadoc 不进运行时，注解才进；
Python 的 docstring 就是运行时可读的「注解」。

对照 Spring：`@Component` + classpath 扫描 + `Map<String, Method>` 白名单——
我们用一个 dict + 装饰器副作用做到了同一件事，**工具发现 = 查表**。

### 2.4 `run_tool`：分发与「回喂不抛」

```python
def run_tool(name: str, arguments_json: str, registry = TOOL_REGISTRY) -> str:
    spec = registry.get(name)
    if spec is None:
        return error_result(f"unknown_tool: {name}（可用工具：...）")
    try:
        args = spec.args_model.model_validate_json(arguments_json)
    except ValidationError as exc:
        return error_result(f"invalid_arguments: ...")
    try:
        return spec.func(**args.model_dump())
    except Exception as exc:
        return error_result(f"tool_error: {type(exc).__name__}: {exc}")
```

四步：查表 → 解析校验 → 解包调用 → 字符串化。`func(**args.model_dump())` 是
「单一事实源」的另一半：**调用处的形参名被 args 模型的字段名锁定**，schema 与签名
不可能漂移（§5 坑位从此绝迹）。

最重要的是错误哲学：**三种失败都不 raise，全部返回 error JSON**。对照 Java 直觉——
分层架构里异常往上抛给最外层兜底（全局 `@ExceptionHandler`），这是对的，因为
上层是「人」或「框架」；但 agent 循环里，异常抛出去模型**永远看不见**，下一轮
它只会重复同样的错误。回喂的 `{"error": "invalid_arguments: claim_id: ..."}` 模型
下一轮就能修（换单号格式 / 换工具 / 补参数）。一句话：**异常服务调用栈，回喂服务模型**。

### 2.5 校验分层：schema 管形状，规则管业务值

一个真实张力：`preapprove([-500])` 该在 schema 层被拦下吗？**不该**——
`REJECT:INVALID_AMOUNT` 是这个工具的合法输出（L0.1 预审的四态之一：PASS 与三个
`REJECT:原因`——L2.4 会把这组值写成 `Literal` 值域），负数必须能进来，
才能被业务规则判断并拒绝。所以：

- schema 层（PreapproveArgs）：`items_cents` 是「至少 1 个元素的整数列表」——形状；
- 规则层（preapprove 函数）：负数 / 超限 / 超总——业务值。

把业务规则写进 schema（比如 `Field(gt=0)`）会**改变工具语义**：负数单据从「被规则
拒绝的 REJECT」变成「进都进不来的 invalid_arguments」——上游永远看不到 INVALID_AMOUNT
这个合法结论。这条分层纪律在毕业设计（L5.4 的 fail-closed 检查链——fail-closed：
值域是闭合集合，宁可拒绝也不猜，L2.4 正式展开）会再次出现。

### 2.6 与 L2.1 的连接

`to_openai_tools()` 的产物直接喂给 `complete(messages, tools=...)`；模型回的
`tool_call["function"]["arguments"]` 直接喂给 `run_tool(name, arguments)`——
L2.1 的协议层与本课的注册表层严丝合缝。Step 2 的 demo 走的还是昨晚那条工具调用
时序，但每一行都是注册表驱动。

## 3. 动手代码

先 `uv sync`。L2.1 的三件套（`client.py` / `mock_endpoint.py` / `env_loader.py`）
已在 `code/`，未改一行——独立课时项目复制的正是这个用法。

### Step 1：schema 观察（10 分钟）

```bash
uv run python code/demo_schema.py
```

看三样东西：`PreapproveArgs` 的 `minItems`（`min_length=1` 的映射）、`GetClaimArgs`
的 `required` 与 `pattern`、最后一段「注册表 → OpenAI tools 载荷」的整体形状。
然后跑讲义区验收（发货态全绿）：

```bash
uv run pytest code/
```

六个测试覆盖：注册生效与 docstring 描述、payload 与模型 schema 的一致性（单一事实源）、
required/pattern 广告、四条分发路径、校验分层（负数进得来、空列表进不来）。

### Step 2：注册表驱动的三回合对话（15 分钟）

```bash
uv run python code/demo_registry.py
```

```text
== 随请求下发的工具契约: ['get_claim', 'preapprove'] ==
== 对话开始 ==
  -> get_claim({"claim_id": "CLM-2026-0002"})
     结果: {"id": "CLM-2026-0002", "submitter": "李工", "purpose": "项目验收宴请（单餐超标）", "items_cents": [8800]}
  -> preapprove({"items_cents": [8800]})
     结果: REJECT:ITEM_OVER_LIMIT
  [最终回答] 报销单 CLM-2026-0002（项目验收宴请）预审拒绝：单笔 8800 分超过 5000 分上限。
```

`get_claim` 读的是仓库共享素材 `data/expense/budget_mock.json`（明线纪律：素材唯一来源）。
注意这个 while 循环——它已经是 ReAct 循环的雏形，只是没有轮数预算；L2.3 把它抽成类、
配上 `ModelClient` 协议与预算。

### Step 3：（可选）真实端点

```bash
uv run python code/demo_registry.py --real
```

（首次配 `.env`：`cp .env.example .env`，Windows PowerShell：`copy .env.example .env`。）

模型自己决定调用顺序与参数（这是它与 mock 的区别）；循环带了 6 轮护栏——
真实世界没有护栏的循环会发生什么，是 L2.3 §5 的主题。

### Step 4：读一遍 `code/tools.py`（10 分钟）

150 行不到，每一节都对着今晚的概念：`ToolSpec`（§2.3）、`tool`（§2.3）、
`to_openai_tools`（§2.2）、`run_tool`（§2.4）。明天 L2.3 的 agent 会原封不动 import 它们。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改标注的 TODO 区；实现需要的顶部 import 可以补（骨架只预置了
given 部分用到的）。卡住先想 5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_tool_schema.py` | 参数模型声明（约束 + 描述）与三层 payload 组装；约束映射验收 |
| ex2 | `exercises/ex2_registry.py` | `@tool` 带参装饰器：注册、docstring 首行描述、wraps |
| ex3 | `exercises/ex3_dispatch.py` | `run_tool` 四步分发；三态错误回喂；校验分层 |

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：签名漂移坑（手写 schema 与函数签名脱钩）

这是本课的命名化失败模式——L2.1 手写契约时你已经埋下了它，今晚拆引信。

- **现象**：`TypeError: preapprove() got an unexpected keyword argument 'amount_cents'`——
  模型规规矩矩按你下发的 schema 传参，你的函数却收不到。
- **最小复现**：

  ```python
  PREAPPROVE_TOOL = {  # 手写契约：字段叫 amount_cents
      "type": "function",
      "function": {"name": "preapprove",
                   "parameters": {"type": "object",
                                  "properties": {"amount_cents": {"type": "integer"}},
                                  "required": ["amount_cents"]}},
  }

  def preapprove(items_cents: list[int]) -> str:  # 函数签名：参数叫 items_cents
      ...

  preapprove(**{"amount_cents": 8800})  # TypeError: unexpected keyword argument
  ```

- **Java 直觉为何失效**：Java 里 DTO 与方法签名被编译器拴在一起——重构改名是
  原子操作，改漏了过不了编译。Python 的 dict 字面量与函数签名之间**没有任何连接**：
  类型检查器看得见 `func(**kwargs)` 的错配吗？看不见——kwargs 是运行时才解包的 dict。
  两份「真相」各自演化，炸在深夜的第三次工具调用里。
- **修复与纪律**：单一事实源——参数模型声明一次，schema 从它生成（`model_json_schema()`），
  调用从它解包（`func(**args.model_dump())`）。字段名既锁契约也锁签名，物理上无法漂移。
  今晚的注册表就是这条纪律的机械化；你在 ex3 里会亲手拧紧最后一颗螺丝。

## 6. 延伸

- Pydantic JSON Schema 官方文档（约束映射全表、schema 生成定制）：
  https://docs.pydantic.dev/latest/concepts/json_schema/
- pydantic/pydantic@e2683e14d#pydantic/json_schema.py —— schema 生成器的实现本体
  （`GenerateJsonSchema`）：`gt` → `exclusiveMinimum` 的映射就发生在这里，读它等于
  看契约编译器。
- langchain-ai/langchain@a063ec26d#libs/core/langchain_core/tools/simple.py —— 生产框架的 `@tool`：
  与我们的注册表对照读——它同样从函数签名/Pydantic 模型生成 schema、用 docstring 当
  描述；多出来的是 `args_schema` 定制与异步变体，骨架与我们今晚的一致。
- openai/openai-cookbook@0aaed0f1d#examples/Orchestrating_agents.ipynb —— 对照原件的
  「Executing Routines」一节：官方手写版用 `inspect` 从函数签名生成 schema——
  同一个问题的另一种解法（反射签名 vs 声明模型），L2.3 读它的循环时留意这个差异。
- FastAPI 文档「Python 类型提示」一节（「文档即数据」生态的另一个大客户）：
  https://fastapi.tiangolo.com/python-types/

## 离毕业又近的一块

毕业设计 L5.1 的 Plan JSON 用「Pydantic 强约束 + 工具白名单」驱动确定性执行——
白名单就是今晚的注册表，强约束就是今晚的 `model_validate_json`；L5.4 fail-closed
检查链的「形状与值分层」也在这里预演。mini-agent 的第二块肌肉（工具层）今晚完工，
明晚把它装进循环。
