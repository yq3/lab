# L1.4 函数是一等公民

> 昨晚你造出了 `ExpenseClaim`：`@dataclass` 负责 11 行声明、Pydantic `BaseModel` 负责「构造即验证」，
> `Field(...)` 把脏数据挡在门外，`ValidationError` 报错你也读得懂了。数据有了，今晚把「行为」变成值：
> `def` 创建的是函数对象，它能排进 `RULES` 列表、能当参数传（`sorted(key=...)`）、能被闭包工厂造出来
> ——这是 L1.5 装饰器的全部地基。

## 1. 本课目标

把「函数是对象」变成直觉——这是装饰器（L1.5）的全部地基。完成后你能：

- 解释 `def` 到底做了什么（创建函数对象 + 绑定名字），把函数赋值、入列表、当参数、当返回值；
- 熟练读写的「函数当参数」代码：`sorted(key=...)`、规则序列、langgraph 的 `path=`；
- 掌握参数的完整规则：关键字调用、默认值、`*args` / `**kwargs` 的定义侧与调用侧、
  keyword-only（`*`）与 positional-only（`/`）；
- 说清 Python 为什么没有方法重载、替代方案是什么；
- 用 nonlocal 写出闭包工厂，并解释它与 Java lambda 捕获 effectively final 变量的异同；
- 用列表 / 字典 / 集合推导式替换 Java Stream 的 map / filter / collect。

**完成判据**：本目录下三条命令同时全绿——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 2. 概念讲解

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| 函数式接口 `Function<T,R>` / 自定义 `Rule` | 函数天生是值，注解 `Callable[[T], R]` | 不必先把「函数形状」声明成接口 |
| 方法引用 `this::check` | 函数名本身（`check` 不加括号） | 零仪式：名字就是引用，没有适配层 |
| 全位置参数 | 每个参数都有名字，可 `func(a=1)` 关键字调用 | Java 想传「第二个参数」必须占位第一个 |
| 方法重载 | **没有**：同名函数后定义覆盖前定义 | 替代：默认参数 + union 类型 + kwargs |
| lambda（函数式接口实例） | lambda（受限的单表达式） | Java lambda 是接口的匿名实现；Python 是函数对象 |
| lambda 捕获 effectively final | 闭包：读免费、写要 `nonlocal` | 两个语言各限制一头，对照着记 |
| `Comparator.comparing(...)` / Stream | `sorted(key=...)` / 推导式 | 推导式是日常主力，Stream 是「翻译过来的人写的」 |
| 手写 `x -> f(x, 2)` 预填参数 | `functools.partial(f, 2)` | partial 把「预填参数」做成了通用工具 |

### 2.1 函数是对象：def 做了什么

`def` 语句**执行时**创建一个函数对象，再把它绑定到名字上——和 `x = [1, 2]` 创建列表并绑定
没有本质区别。所以函数能干对象能干的一切事：

```python
def check_invalid(items: list[int]) -> str | None: ...


f = check_invalid  # 赋值：不加括号，传的是函数本身，不是调用结果
print(f.__name__)  # check_invalid —— 函数自带名字元数据
rules = [check_invalid, check_item_limit]  # 入列表：规则序列的原料
verdict = rules[0]([-1])  # 取出来调用："REJECT:INVALID_AMOUNT"
```

同样的事在 Java 里要先造一个「函数的形状」（函数式接口），再用方法引用把方法适配进去：

```java
interface Rule {                                   // 第一步：先声明函数的形状
    String apply(List<Integer> itemsCents);
}
Rule r = service::checkInvalid;                    // 第二步：方法引用适配
List<Rule> rules = List.of(r, service::checkItemLimit);
String verdict = rules.get(0).apply(List.of(-1));  // 第三步：调用要换回接口方法名
```

Python 的函数天生满足「可调用 + 自带名字」，这三步压成一步——这就是「一等公民」的含义。
类型注解侧的对应物是 `collections.abc` 的 `Callable[[list[int]], str | None]`
（参数类型列表 → 返回类型），对照 `java.util.function.Function<List<Integer>, String>`。

### 2.2 一切皆 key 参数：调用的完整规则

**最大的 Java 差异先立住**：Java 调用全靠位置（`f(a, b)` 里 a、b 的含义靠顺序传达）；
Python 每个参数都有名字，调用时可以用 `参数名=` 点名传递：

```python
def create_claim(claim_id: str, submitter: str, items_cents: list[int] = []): ...
# （这个 = [] 只为演示「默认值在 def 时求值」——可变默认的雷本课 §5 专讲，别学这个写法）


create_claim("CLM-2026-0001", "王工", [1200])  # 全位置：可以
create_claim(claim_id="CLM-2026-0001", submitter="王工")  # 全关键字：默认值生效
create_claim("CLM-2026-0001", items_cents=[1200], submitter="王工")  # 混用：位置在前
```

**定义侧**的完整形状（一条签名把所有区段摆在一起）：

```python
def func(a, b=1, /, c=2, *args, d, e=3, **kwargs): ...


#      └─┬─┘└─┬─┘ └┬┘ └─┬─┘ └─┬─┘└┬┘└─┬─┘
#      普通 默认  /   *args keyword-only(* 之后的 d、e，必须点名传) **kwargs
#              边界    收拢多余位置参数成 tuple              收拢多余关键字参数成 dict
```

`/` 与 `*` 是两个方向的栏：`/` 之前的参数**只能按位置传**（positional-only，内置函数与
不少框架 API 在用，见到要认识）；`*` 之后的参数**只能按名字传**（keyword-only，框架
保护「易混位置参数」的惯用法，本课 `render_verdict(reviewer=...)` 就是）。

**调用侧**的 `*` / `**` 是另一件事——解包摊开：

```python
args = [1200, 3500]
kwargs = {"submitter": "王工"}
create_claim(*args, **kwargs)  # 等价于 create_claim(1200, 3500, submitter="王工")
```

| 写法 | 语义 |
|---|---|
| `def f(*args)` | 定义侧收拢：多余位置参数打包成 `tuple` |
| `def f(**kwargs)` | 定义侧收拢：多余关键字参数打包成 `dict` |
| `f(*[1, 2])` | 调用侧摊开：等价 `f(1, 2)` |
| `f(**{"a": 1})` | 调用侧摊开：等价 `f(a=1)` |

一收一摊互逆。`f(**dict)` 就是「dict 到函数调用」的桥——agent 世界每天都走（§3 Step 4）。

### 2.3 没有重载：一个名字只有最后一个定义生效

Java 靠编译器按签名分派重载；Python 的类型标注不参与运行时分派，同名函数就是覆盖：

```python
def area(r: float) -> float:  # 圆面积——定义即被覆盖，静默消失
    return 3.14159 * r * r


def area(w: float, h: float) -> float:  # 矩形面积：这是「重新赋值」不是「重载」
    return w * h


area(3)  # TypeError: 缺少 1 个必需的位置参数 'h'——报错来自第二个 area！
```

没有报「函数已存在」、没有警告，第一个定义悄悄蒸发——这是从 Java 过来最意外的一课。
替代方案按场景选：

- **参数个数差异** → 默认参数：`def area(w, h=None)`，体内 `h` 缺省按圆算；
- **参数类型差异** → union 类型标注 + 体内 `isinstance` 分支（L1.2 的类型课详解过渐进类型）；
- **真想按类型分派** → 标准库 `functools.singledispatch`（按第一个参数的运行时类型注册实现，
  知道存在即可，agent 框架里不常用）。

### 2.4 lambda：受限的单表达式函数

```python
sorted(claims, key=lambda c: c.total_cents)  # 内联小回调的标准形态
```

对照 Java：`(c) -> c.getTotalCents()` 必须适配目标接口（`Comparator` / `Function`）；
Python lambda 就是一个**只能写单个表达式**的函数对象——不能有语句、不能赋值、
隐式返回表达式的值，连名字都没有（`__name__` 固定是 `"<lambda>"`）。

为什么有 `def` 还需要它：省掉「为用一次的小函数起名 + 占两行」的仪式。
社区惯例：lambda 的身体只能是一个表达式，写到条件表达式（`x if cond else y`）就是公认的复杂度上限，
再复杂就老老实实 `def`——有名字的函数才好测试、好在 traceback 里认人。
（PEP 8＝Python 官方编码风格规范，≈ Java 的 Code Conventions；它本身只禁止把 lambda 赋值给名字当变量用；这条上限是经验法则，不是规范条文。）

### 2.5 闭包：函数记住了出生环境

闭包三要素：内层函数 + 引用外层函数的变量 + 外层返回内层函数。

```python
def make_threshold(limit_cents: int) -> Callable[[int], bool]:
    def exceeds(amount_cents: int) -> bool:
        return amount_cents > limit_cents  # 读外层变量：免费，无需声明

    return exceeds  # 返回函数本身（不带括号！）


exceeds_5k = make_threshold(5000)
exceeds_5k(5001)  # True —— limit_cents 还活着
```

两条铁律：

1. **捕获的是引用不是值**（变量本身，不是当时的快照）——循环里建闭包会踩 late binding（§5）；
2. **读免费、写要 `nonlocal`**：内层给外层名字赋值前必须声明 `nonlocal state`，
   否则赋值语句会创建同名局部变量（遮蔽外层，通常直接 `UnboundLocalError`）。

与 Java 的对照非常妙——两个语言各限制一头：

| | Java lambda | Python 闭包 |
|---|---|---|
| 读外围变量 | 随便（捕获副本引用） | 随便（免费） |
| 写外围变量 | **禁止**（必须 effectively final） | 允许，但要 `nonlocal` 声明 |

闭包工厂（`make_threshold` / `make_multiplier`）+ 状态闭包（计数器）是两种标准用法，
§3 Step 2 各写一个。每次工厂调用都是一套**全新**环境——状态隔离是它的核心竞争力。

### 2.6 高阶三件与推导式：Stream 的翻译（推导式在 L1.1 §2.7 速览过，这里是正式主讲）

**`sorted(key=...)`** 是「函数当参数」的最高频现场（多级排序用元组 key，§3 Step 3）。

**`map` / `filter`** 存在，但 Python 日常主力是**推导式**——本课正式引入，必须讲透：

```python
# 列表推导式 = filter + map + collect 一行
big = [c for c in claims if c.total_cents > 5000]
# 字典推导式 = collect(toMap)
totals = {c.submitter: c.total_cents for c in claims}
# 集合推导式 = collect(toSet)
names = {c.submitter for c in claims}
```

```java
// Java Stream 的同款（每个动词都要显式说出来）
List<ClaimSummary> big = claims.stream()
        .filter(c -> c.totalCents() > 5000)
        .collect(Collectors.toList());
```

纪律两条：条件筛选写在尾部（`for ... if ...`），可叠加多个 if；**嵌套不超过两层**——
双层以上的推导式读不回来，退回普通循环（带累加的分组求和就属于「别硬凹」，§3 Step 3
的 `totals_by_submitter` 用循环写，它是正确的样子）。

**`functools.partial`**：预填参数返回新可调用，对照 Java 手写绑定 lambda：

```python
from functools import partial

int_bin = partial(int, base=2)  # 预填 base=2
int_bin("1010")  # 10
```

```java
Function<String, Integer> intBin = s -> Integer.parseInt(s, 2);   // Java 没有通用预填，手写
```

### 2.7 今晚的形状在框架里叫什么

- 规则函数序列 → langgraph 的条件边 `add_conditional_edges(path=一个函数)`、
  openai-agents 的 guardrail：判定逻辑以函数为单位注入框架；
- `**kwargs` 收拢 → 框架回调的通用签名 `def hook(context, **kwargs)`：框架新增参数不破坏你的旧回调；
- `__name__` → 追踪与日志：框架拿函数自报的名字展示节点（没有注解，没有 XML）。

## 3. 动手代码

### Step 1 规则链：preapprove 拆成数据（15 分钟）

打开 `code/preapprove_rules.py`：L0.1 的三连 `if` 拆成 `RULES` 列表里的三个函数，
`preapprove` 只负责「按序找第一个非 None」。注意两处细节：`Rule` 类型别名让列表签名
可读（`Rule = Callable[...]` 是赋值式类型别名——Java 没有对应物，只能重复写全名；Python 一行缩写）；`describe_rules()` 用 `__name__` 拿函数自己的名字。

```bash
uv run pytest code/test_preapprove_rules.py
```

重点看 `test_chain_is_data_not_control_flow`：往 `RULES` 头部**注入**一条黑名单规则，
行为立刻变化、还原后复原——规则是数据，不是写死的控制流。这就是中间件 / guardrail
能动态装配的全部原理。

### Step 2 闭包工厂：读捕获与写捕获（15 分钟）

打开 `code/closures.py`：`make_threshold`（读捕获，返回检查函数）与 `make_counter`
（写捕获，`nonlocal state` 推进计数）。对照 2.5 的两条铁律读一遍。

```bash
uv run pytest code/test_closures.py
```

重点看 `test_counters_do_not_share_state`：两个计数器各数各的——state 活在各自的
闭包环境里。如果把它写成模块级全局变量，这个测试当场穿帮。

### Step 3 多级排序与推导式（15 分钟）

打开 `code/reporting.py`：`rank_by_total` 用元组 key 实现金额降序 + 同额按提交人升序；
`big_claims` / `submitters` 是列表 / 集合推导式；`totals_by_submitter` 示范「带累加的
分组用循环」的正确姿势。

```bash
uv run pytest code/test_reporting.py
```

看 `test_rank_by_total_then_submitter` 的注释：字符串按 Unicode 码点排序，
中文的「字典序」并不保证——生产环境按 locale 或专门键排，这是个诚实的小提醒。

### Step 4 **kwargs 适配器：function calling 的桥（10 分钟）

打开 `code/tool_bridge.py`：`invoke_tool(func, params)` 一行 `func(**params)` 把 dict
摊开成函数调用；`render_verdict` 的 `reviewer` 是 keyword-only 参数（`*` 之后）。

```bash
uv run pytest code/test_tool_bridge.py
```

`test_unknown_key_blows_up_at_the_call` 值得盯三秒：多余的键在摊开那一行抛 TypeError——
**签名就是校验器**。L2.2 工具协议课会给这座桥套上 Pydantic，把 TypeError 升级成
带字段路径的 ValidationError（今晚先记住这座桥的样子）。

### Step 5 跑一遍两个坑（5 分钟）

```bash
uv run python code/pitfall_demos.py
```

输出（§5 逐行拆解）：

```text
── 可变默认参数 ──
两次调用各传一个元素，第二次结果：['打车', '工作餐']
第一次的结果也被改了：['打车', '工作餐']
两次拿到的是同一个 list 对象：True
── late binding 闭包 ──
循环里建的三个 lambda，调用结果：[2, 2, 2]
默认参数钉值修复后：[0, 1, 2]
```

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——每题只改标注的 TODO 区，其余文件与代码区不要动。卡住先想
5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_rule_chain.py` | 规则序列版 preapprove：与 L0.1 同一套用例验收 |
| ex2 | `exercises/ex2_closures.py` | `make_greeter` + `make_counter`（必须 `nonlocal`） |
| ex3 | `exercises/ex3_report.py` | keyword-only 报表函数 + `**kwargs` 透传 |

三题的验收标准：

- ex1 的用例表含冲突优先级（脏数据 > 单笔 > 合计）与边界（恰好等于上限应 PASS），覆盖
  由 meta 断言机器判定；另有一个**注入测试**——往 `RULES` 头部插一条规则、行为必须立刻变。
  它验证你真的在消费 `RULES` 列表：把逻辑硬编码成 if 链过不了；
- ex2 双保险：源码检查（`make_counter` 函数体里必须出现 `nonlocal`）+ 行为检查（两个
  计数器状态隔离，全局变量写法当场穿帮）；
- ex3 调用形态断言：`unit` / `bracket` 按位置传必须 TypeError（`*` 栏在调用时拦截），
  签名形态由 `inspect`（标准库的运行时反射模块，≈ Java reflection 读方法参数）判定；透传遇到不认识的键必须让 TypeError 自然炸出。

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 直觉陷阱（本课两个）

### 陷阱一：可变默认参数

- **现象**：`def add_item(item, items=[])` 多次调用，历史数据越积越多——上一次调用的
  追加还在列表里（Step 5 已眼见为实）。
- **最小复现**：

  ```python
  def add_item_buggy(item: str, items: list[str] = []):  # 默认值在 def 执行时创建一次
      items.append(item)
      return items


  add_item_buggy("打车")  # ['打车']
  add_item_buggy("工作餐")  # ['打车', '工作餐'] ！！
  # id(add_item_buggy("x")) 每次都同一个对象（Step 5 打印了 True）
  ```

- **Java 直觉为何失效**：Java 的默认参数（或字段初始化）语义是「每次调用/构造时求值」；
  Python 的默认值是 **def 语句执行那一刻求值一次的对象**，之后所有调用共享它。
  L1.3 的 dataclass 用 `ValueError` 把同样的坑挡在定义时，普通函数没有这层护栏——
  ruff 的 B006 规则就是为它存在的（`code/pitfall_demos.py` 里那行 noqa 标的就是它）。
- **修复与纪律**：默认 `None` + 体内现做——`items = items if items is not None else []`。
  一辈子照此办理，坑就与你无关。

> **IDE 侧**：Debug 跑两轮 `add_item_buggy` 调用，在 Watches 面板加表达式 `id(items)`——两次同一个 id，「默认值跨调用共享」当场可见，比读三遍文字直观。

### 陷阱二：late binding 闭包

- **现象**：循环里建的 lambda，调用时全部返回**循环结束时的**变量值——`[2, 2, 2]`
  （range(3) 最后一个 i 是 2），不是各自那轮的 0、1、2。
- **最小复现**：

  ```python
  funcs = [lambda: i for i in range(3)]  # 三个 lambda 捕获的都是变量 i 本身（引用）
  [f() for f in funcs]  # [2, 2, 2] —— 调用时才去读 i，i 已经走到头
  ```

- **Java 直觉为何失效**：Java 增强 for 里 `for (var i : list) lambdas.add(() -> i)`
  根本编译不过——i 不 effectively final；每轮循环是一个新变量，捕获即定值。
  Python 的 for 循环**不给每轮创建新作用域**，整个循环共享一个 `i`，闭包捕获引用、
  调用时才解引用（late binding 的字面意思）。
- **修复与纪律**：默认参数钉值——`[lambda i=i: i for i in range(3)]`，默认值在函数定义
  （每轮循环）时求值，把当时的 i 抄进函数对象；或用工厂函数（`def make(i): return lambda: i`）。
  在 asyncio 回调 / GUI 事件绑定里这坑会以「按钮全触发同一个值」的形态重逢。

## 6. 延伸

- functools 官方文档（partial / wraps / singledispatch）：https://docs.python.org/3/library/functools.html
- Python 语言参考「调用与可调用对象」：
  https://docs.python.org/3/reference/expressions.html#calls
- langgraph@e539ac122#libs/langgraph/langgraph/_internal/_runnable.py —— `RunnableCallable`：
  框架把「函数对象 + `__name__` + `**kwargs` 透传」打包成图节点的真实形状，今晚 Step 1
  和 Step 4 的合体；
- langgraph@e539ac122#libs/langgraph/langgraph/graph/state.py —— `add_conditional_edges(path=...)`：
  路由判定就是「函数当参数」传进框架（L3.2 条件边的地基）；
- GenAI_Agents@cd2ee86#all_agents_tutorials/EU_Green_Compliance_FAQ_Bot.ipynb —— 教学 notebook
  里 `key=lambda x: ...` 的高频用法，看真实教程代码怎么消费一等函数（对照：lambda 复杂度纪律）；
- 《Fluent Python》第 2 版第 7 章「一等函数」（第 8 章闭包与装饰器是 L1.5 的预习材料）。

## 离毕业又近的一块

今晚的 `RULES` 列表就是毕业设计 L5.4「fail-closed 执行门」的执行骨架（限额 clamp /
黑名单 / 频次三态裁决（毕业设计执行门的门语义，L5.4 见）按序装配）；`invoke_tool` 的 `func(**params)` 是 L2.2 工具协议
「模型选工具 → 摊开参数 → 调 Python 函数」的那一行；闭包与 nonlocal 则是 L1.5 重试装饰器
（装饰器 = 闭包的亲儿子）的一半地基。函数当值用，是从今晚开始到毕业一路的底层通货。
