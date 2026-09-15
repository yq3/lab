# L1.5 装饰器 vs 注解：@ 的两副面孔

## 1. 本课目标

读完框架源码里最常见的那个字符 `@`。完成后你能：

- 写出无参与带参两种装饰器（含 `functools.wraps`），并解释每层函数各收什么；
- 说清 Java 注解与 Python 装饰器的**本质差异**：标签 vs 函数变换；
- 看懂 langchain / crewAI 里 `@tool`、`@step` 风格代码背后发生了什么——为什么「函数定义完就自动进了注册表」。

**完成判据**：本目录下 `uv run pytest` 练习全绿（exercises/ 三个练习），且你能不看讲义复述 `@deco` 的等价展开。

## 2. 概念讲解

### 2.1 热身：函数是对象（60 秒）

装饰器只依赖一件事：**Python 的函数是对象**。函数可以存进变量、当参数传、当返回值返回——对应 Java 里 `Function<T, R>` / 函数式接口，但不需要任何接口声明：

```python
def preapprove(items: list[int]) -> str:
    return "PASS"


f = preapprove  # 不加括号：拿到函数对象本身（Java 里没有「方法引用之外」的对应写法）
print(f([1200]))  # 通过变量调用它
```

于是「一个收函数、返回函数的函数」（高阶函数）完全合法——这就是装饰器的全部原型。

### 2.2 最显眼的一句话：`@deco` 是语法糖

请把下面这条等价关系刻进肌肉记忆，本课一切推导都从它出发：

```python
@deco
def f(): ...


# 完全等价于（@ 语法糖的手工展开）：
def f(): ...


f = deco(f)  # 注意：是「用返回值替换原名」，deco 立即执行，此刻就发生
```

关键推论（与 Java 注解的分水岭）：

1. **`deco` 在 `def` 的瞬间就被调用**——不是编译期标记，不是运行时按需解析，就是一次普通的函数调用；
2. `f` 这个名字从那以后**绑定的是 `deco` 的返回值**，不一定是原来的函数；
3. 既然是普通调用，自然可以带参数（`@deco(x=1)`，见 2.5）、可以叠放（见 2.6）。

### 2.3 Java↔Python 对照表

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| `@Override` / `@SuppressWarnings` | （无参装饰器） | Java 注解是**贴在元素上的数据**；Python 装饰器是**立即执行的函数变换** |
| 注解处理器（APT / 编译期） | 不存在 | Python 装饰器不需要处理器兑现——`def` 时刻自己就兑现了 |
| 反射 + 动态代理（Spring AOP） | 装饰器本体 | Spring 要靠容器在运行时织入代理；Python 直接换个函数对象，零反射 |
| `@Transactional`（Spring） | `@retry` / `@timing`（本课 Step 1/3） | **Java 里最像 Python 装饰器的东西**：方法还是那个签名，行为被包了一层 |
| 多个注解：无顺序语义、可重复 | `@a @b` 有严格顺序：`a(b(f))` | Java 注解是平铺的标签集合；Python 是嵌套的函数调用 |
| 注解不改变被注解元素本身 | 装饰后原名绑定的是**新对象** | 这也是 §5「丢元数据坑」的根源 |

**用 `@Transactional` 当桥**：你写 `@Transactional def transfer()` 时，Spring 在运行时给 `transfer` 生成动态代理，调用前后织入 begin/commit/rollback——`transfer` 这个名字最终指向代理对象。
把「容器替你生成代理」换成「装饰器函数自己返回包装」，你就得到了 Python 装饰器：**同一件事，Python 把它做成了语言机制而不是框架魔法**。
本课 Step 3 的 `@retry` 与 L1.7 的 `with` 会把这个桥走完。

### 2.4 装饰器三形态

**形态一：无参装饰器（两层函数）**——外层收函数，内层做包装：

```python
from functools import wraps


def timing(func):  # 第 1 层：收被装饰函数
    @wraps(func)  # 见下文「为什么需要 wraps」
    def wrapper(*args, **kwargs):  # 第 2 层：真正的替身，将来以它的身份被调用
        start = perf_counter()
        result = func(*args, **kwargs)  # 调真身
        print(f"{func.__name__} 耗时 {perf_counter() - start:.4f}s")
        return result  # 返回值透传

    return wrapper  # 交出替身
```

**为什么需要 `functools.wraps`**：不写它，`f.__name__` 会变成 `'wrapper'`、`__doc__` 变 `None`——元数据被替身顶掉了。演示：

```python
def deco_naive(func):
    def wrapper(): ...

    return wrapper


@deco_naive
def preapprove():
    "预审"


print(preapprove.__name__)  # 'wrapper'  <- 不是 'preapprove'！
```

`@wraps(func)` 做的事就是把 `func` 的 `__name__` / `__doc__` / `__module__` 等复制到 wrapper 上。**纪律：写装饰器永远加 wraps**，理由见 §5 坑位。

**形态二：带参装饰器（三层函数）**——外收参数、中收函数、内做包装：

```python
def retry(max_attempts, retry_on=(Exception,)):  # 第 1 层：收参数
    def decorator(func):  # 第 2 层：收函数
        @wraps(func)  # wraps 永远贴在最内层
        def wrapper(*args, **kwargs):  # 第 3 层：做包装
            ...

        return wrapper

    return decorator  # 注意：交出的是「装饰器」


@retry(max_attempts=3)  # 展开两步：decorator = retry(3)；f = decorator(f)
def fetch(): ...
```

口诀：**带参装饰器比无参的多一层**，因为 `@` 后面跟的必须是个「能收函数的东西」，带参版得先吃参数、再交出一个装饰器。

**形态三：装饰类（一笔带过）**：`@dataclass` 就是装饰类的装饰器——收类、加工类、返回类。机制与装饰函数完全同构（类也是对象），本课不展开，L1.3 你已经用过它了。

### 2.5 装饰器能干的三件事（agent 框架全占）

| 用途 | 做什么 | 框架实例 |
|---|---|---|
| **注册** | 把函数登记进 dict，原样返回 | `@tool`：函数名进工具注册表，模型运行时按名调用 |
| **增强** | 包一层行为：重试 / 计时 / 缓存 | `@retry`、`@lru_cache`、LangGraph 的 retry policy |
| **校验** | 前置条件检查，不满足就抛 | `@tool` 检查 docstring 与类型标注（见 §6 源码） |

注册型与增强型的代码形状不同：**注册型原样返回 func，增强型返回 wrapper**——这是本课练习 3 与练习 1 的对照点。

### 2.6 叠放顺序：`@a @b` ≡ `a(b(f))`

```python
@a
@b
def f(): ...


# 等价于：f = a(b(f))——自下而上应用（离 def 近的先被包），调用时像洋葱由外向内
```

对照 Java：方法上叠三个注解只是三张互不相干的标签；Python 叠两个装饰器是**有顺序的两次函数变换**，先包谁后包谁，行为可能完全不同（Step 4 亲手验证）。

### 2.7 类型视角：Callable 进，Callable 出

装饰器保持签名：`Callable[P, R] -> Callable[P, R]`——进什么签名，出什么签名。`P` 描述「参数部分的形状」（ParamSpec），让 wrapper 的 `*args, **kwargs` 与原函数参数对上。本课与框架源码统一用老式写法，声明在函数外：

```python
from typing import ParamSpec, TypeVar

P = ParamSpec("P")  # 参数形状：抓「调用参数」整体
R = TypeVar("R")  # 返回值形状：单个类型占位符


def timing(func: Callable[P, R]) -> Callable[P, R]: ...
```

3.12 也支持把类型参数直接写在 def 上（`def timing[P, R](...)`，PEP 695，长得像 Java 的 `<T>`）——但它在 3.12 与 `collections.abc.Callable` 组合时有运行时 bug（3.13 才修），
而框架源码（如 §6 的 crewAI `@tool`）清一色老式写法，所以我们跟框架走。本课只要求**看懂**，不要求默写。

## 3. 动手代码

以下四个模块都在 `code/`，先 `uv sync`，再逐个跑。每个都可以 `uv run python code/<文件>` 直接看输出，配套测试在同名 `test_*.py`。

### Step 1 timing 装饰器（含 wraps）

```bash
cd units/unit1-core/L1.5-decorators
uv sync
uv run python code/timing.py
```

看两件事：①「路线一」不用 `@`，手工 `audited = timing(preapprove)`——这就是语法糖的展开形态；②把 `@wraps(func)` 注释掉再跑，`audited.__name__` 变成 `wrapper`。

### Step 2 registry：框架 `@tool` 的秘密

```bash
uv run python code/registry.py
```

`TOOLS` 字典 + `@tool` 装饰器 + 两个报销工具。输出里「已注册工具」那两行，**我们从头到尾没手动往 TOOLS 塞过东西**——登记发生在 `def` 被执行的瞬间（2.2 的推论 1）。
然后 `run_tool("check_item_limit", ...)` 用字符串按名调用：这就是 agent 框架「模型选了工具名 -> 注册表查表 -> 调用函数」的原型。§6 会带你去看 langchain / crewAI 里它的工业版。

### Step 3 带参 retry 装饰器

```bash
uv run python code/retry.py
```

三层结构 + 一个 mock：`fetch_exchange_rate` 前两次抛 `ConnectionError`、第三次成功。输出会打印两次重试日志和最终结果——「三次中两次失败仍成功」。注意 `@retry(max_attempts=3, retry_on=(ConnectionError,))` 的括号：带参形态必须带括号（展开是两步调用）。

### Step 4 叠放顺序实验

```bash
uv run python code/stacking.py
```

文件头部的「预期输出」注释写着 `[apply] b 在前、a 在后`（应用自下而上）、`[call] a 的前置 -> b 的前置`（调用由外向内）。跑完对照，再打开文件看 `manual = a(b(raw_audit))` 的直译与 `@a @b` 叠放是否等价。

```bash
uv run pytest code/        # 讲义示例测试应全绿（它不是你的练习）
uv run ruff check code/
```

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——每题只改标注的 TODO 区。卡住先想 5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 | 验收要点 |
|---|---|---|---|
| ex1 | `exercises/ex1_timing.py` | 无参装饰器（两层） | 返回值透传 + 每次调用耗时记进 `TIMINGS` + `__name__`/`__doc__` 保留 |
| ex2 | `exercises/ex2_retry.py` | 带参装饰器（三层） | 三次中两次失败仍成功 / 耗尽抛**最后一次**异常 / 成功后绝不重试 / 名单外异常不重试 |
| ex3 | `exercises/ex3_registry.py` | 注册型装饰器 + 按名调用 | import 后 TOOLS 内容断言 + 调用结果断言 + 未知名抛 `KeyError` |

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：丢元数据坑

这是装饰器课的必摔跤，命名化之后我们叫它「丢元数据坑」。

- **现象**：被装饰后 `f.__name__` 变成 `'wrapper'`、`f.__doc__` 变 `None`。平时无感，一旦有别的东西**按名字或文档找函数**，当场爆炸：pytest 的参数化 id、序列化工具按 `__name__` 导出、日志格式化 `%(__name__)s`、以及框架的 `@tool`——它靠 docstring 生成给模型看的工具描述。
- **最小复现**：

  ```python
  def deco_naive(func):
      def wrapper(*args, **kwargs):
          return func(*args, **kwargs)

      return wrapper  # 没有 @wraps


  @deco_naive
  def check_amount():
      """金额检查。"""


  print(check_amount.__name__)  # wrapper
  print(check_amount.__doc__)  # None
  ```

  再叠一层真实后果：把这个 `check_amount` 挂给 crewAI 的 `@tool`（见 §6 源码），它第一行检查就是 `if f.__doc__ is None: raise ValueError`——你的坏装饰器让框架直接拒收。
- **Java 直觉为何失效**：Java 注解是贴标签，**从不改变被注解元素本身**——`@Test` 过后方法还是那个方法，名字文档纹丝不动。Python 装饰器是替换，原名绑定的已经是 wrapper，元数据天然是 wrapper 的，除非你显式复制。
- **修复与纪律**：装饰器**永远** `@functools.wraps(func)`，贴在真正包住原函数的那层 def 上。wraps 还会顺手设 `__wrapped__` 指回原函数，调试时有用。已经丢了的现场可以用 `f.__wrapped__` 找回原身。

## 6. 延伸

- functools 官方文档（wraps / lru_cache / cache / cached_property）：https://docs.python.org/zh-cn/3.12/library/functools.html
- 《Fluent Python》第 2 版「装饰器与闭包」章（第 9 章）：三层结构与注册型装饰器的深水区；
- 框架真实 `@tool` 源码（两版对照，都是带参装饰器工业版）：
  - crewAI@894898f84#lib/crewai/src/crewai/tools/base_tool.py —— 搜 `def tool(`：三种用法（`@tool` / `@tool("名字")` / `@tool(result_as_answer=True)`）共用一个带参装饰器；
    开头就检查 `f.__doc__ is None` 抛 `ValueError`（§5 坑位的生产级受害者现场）；用 `signature` + 类型标注自动生成 Pydantic 参数 schema——那是 L1.3 的知识；
  - langchain@348c9dc572#libs/core/langchain_core/tools/convert.py —— 搜 `def tool(`：同一思路的另一实现，`@overload` 一列就是「无参/带参」双形态的类型签名。
- 用法层面的直观感受：GenAI_Agents@cd2ee86#all_agents_tutorials/memory-agent-tutorial.ipynb 里 `@tool` 定义工具的 notebook 用法。

## 离毕业又近的一块

今晚的 `@retry` 就是 Unit 5 毕业设计「执行门」里 **API 调用韧性层**的直接原型（跑长审批流时上游抖动，重试是刚需）；
`TOOLS` 注册表则是 L2.2「工具协议」的雏形——那时你会亲手把 `dict[str, Callable]` 升级成带 JSON Schema 的正式工具表。
装饰器这层皮，毕业后你每天都在框架里穿脱它。
