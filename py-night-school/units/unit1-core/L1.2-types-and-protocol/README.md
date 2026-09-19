# L1.2 类型系统与 Protocol：标注是承诺，Protocol 是形状

> 昨晚你把单文件 `preapprove()` 升级成了 `expense` 包：规则拆进模块、入口用 `python -m expense.cli`
> 启动、`__name__` guard 让规则模块既能被 pytest import 又能单独拉起排障。代码能跑了，但类型标注你
> 一直只是照模板抄——今晚把它变成自己的语言：写出精确签名（含 `str | None` 与泛型），理解「标注不
> 影响运行时」而 pyright 就是夜校的 javac，并用 `Rule` Protocol 表达「有这个方法就行」。

## 1. 本课目标

读懂并写出现代类型标注（含泛型与 `str | None` 联合），理解「标注不影响运行时」与 pyright 在工作流里的角色，并用 **Protocol** 表达「有这个方法就行」。完成后你能：

- 给任何函数写出精确签名，并知道 `list[int]` / `str | None` / `dict[str, int]` 各自读作什么；
- 解释为什么 `x: int = "abc"` 照样运行、而夜校仍然要求全程标注（pyright 就是你的 javac）；
- 写一个 Protocol 和两个「零继承」的实现，并说清它与 Java interface 的本质差异（结构化 vs 名义类型）；
- 在联合类型入口先收窄，避开 `None` 直接参与运算的运行时爆炸。

**完成判据**：本目录下三条命令同时全绿——

```bash
uv run pytest          # code/ 全绿；exercises/ 在完成练习前呈「精确红」
uv run ruff check .    # 无 lint 违规
uv run pyright         # 无类型错误（练习 2 完成前它会对 exercises/ 标红——见 §4 的说明）
```

## 2. 概念讲解

### 2.1 渐进类型：标注是「文档 + IDE + 静态检查」，运行时不强制

| 你熟悉的 Java 物 | Python 对应物 | 一句话差异 |
|---|---|---|
| javac 编译期硬拒收 | pyright（或 mypy）静态检查 | 类型错误不挡运行，只挡「编译」这一步 |
| 类型是语言强制约束 | 类型是**可选标注**（渐进类型，PEP 484 起） | 老代码零标注也能跑 |
| IDE 红线即编译错误 | IDE 红线：VS Code 的 Pylance（pyright 同引擎）、PyCharm 自带检查（要同引擎可装 Pyright 插件） | 你的 IDEA 直觉可以整体平移 |
| `@Nullable` 注解 + 人肉判空 | `str | None`（类型系统一等公民） | 联合类型会被静态检查器追踪 |

眼见为实——标注真的不影响运行时：

```bash
uv run python -c "x: int = 'abc'; print('照样运行, x =', x)"
```

声明 `int` 赋值 `str`，解释器毫无怨言。**但这不是标注没用的证据，而是分工不同的证据**：运行时不看标注，静态检查器看。夜校的纪律：全程标注 + `uv run pyright` 当编译器——L0.1 起每课验收都有它，理由和 Java 团队不开 `-Xlint:none` 一样。

顺带一个运行时差异：标注是**真实存储在函数对象上的数据**（练习 1 的验收会把它取出来逐个比对）——它不是注释，只是不被解释器强制。

### 2.2 基础标注语法与现代写法

```python
DAILY_MEAL_LIMIT_CENTS = 5000  # 模块级常量可省标注（值即类型）


def parse_amounts(raw: str) -> list[int]:  # 参数:类型，-> 返回类型
    return [int(part) for part in raw.split(",")]


def reject_tally(results: list[tuple[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}  # 局部变量也可标注：键是 str，值是 int
    for _, verdict in results:
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts
```

三条「现代写法」纪律（ruff 的 UP 规则会机器强制前两条）：

1. **内置泛型直接下标**：`list[int]`、`dict[str, int]`、`tuple[str, str]`（3.9+ 起合法）。不要写 `typing.List[int]`——那是 3.8 及以前的旧形态，UP006/UP035 会报。
2. **联合用竖线**：`str | None`（3.10+ 起）。它**等价于** `Optional[str]` / `Union[str, None]`——`Optional` 这个名字误导人（它不表示「可省参数」，只表示「可以为 None」），新代码一律用竖线。
3. 读法：`list[tuple[str, str]]` 读作「字符串二元组的列表」；`-> str | None` 读作「返回字符串或 None」。`None` 是 Python 的 null 对应物，但它是**一个真对象**（单例），不是关键字。

### 2.3 Any vs object：逃生舱 vs 万物基类

```python
from typing import Any


def shout_any(msg: Any) -> Any:
    return msg.upper()  # pyright 零抱怨——Any 把检查整个关掉


def shout_object(obj: object) -> object:
    return obj.upper()  # pyright 报错：object 只保证 object 的方法（没有 upper）
```

对照 Java：`Any` ≈ raw type（`List` 不带尖括号）——编译器放行一切，静默埋雷；`object` ≈ `Object`——什么都能装，但**只能调 Object 的方法**，想用具体的就得先收窄（见 §2.7）。纪律：`Any` 只用在「真的没法说清类型」的边界（动态 JSON、C 扩展接口），用一次给一次理由；练习 3 会让你把滥用点全部收紧。

### 2.4 泛型：3.12 的方括号语法

```java
// Firsts.java —— Java：泛型参数写在方法签名前
import java.util.List;

public class Firsts {
    public static <T> T first(List<T> items) {
        if (items.isEmpty()) {
            throw new IllegalArgumentException("first() 不接受空列表");
        }
        return items.get(0);
    }
}
// 调用：Firsts.first(List.of(3, 1, 2)) —— T 推断为 Integer
```

```python
# generics.py —— Python 3.12（PEP 695）：方括号紧跟函数名
def first[T](items: list[T]) -> T:
    if not items:
        raise ValueError("first() 不接受空列表")
    return items[0]


# 调用：first([3, 1, 2]) —— T 自动绑定 int；first(["a"]) —— T 绑定 str
```

两个类型参数的例子（`code/generics.py` 里的 `pluck`）：

```python
def pluck[K, V](rows: list[dict[K, V]], key: K) -> list[V]:
    return [row[key] for row in rows]
```

对照 Java 的 `<K, V> List<V> pluck(List<Map<K, V>> rows, K key)`。旧教程里的 `TypeVar("T")` + `Callable[..., T]` 形态你在框架源码里还会大量见到（`Callable`＝函数签名的类型，≈ Java 的函数式接口类型——与 `java.util.concurrent.Callable` 无关）（它们是同一件事的历史版本），3.12 新代码用方括号。

### 2.5 Protocol：结构化类型（本课高潮）

Java 的 interface 是**名义类型**（nominal）：兼容性看「名字与血缘」——不写 `implements`，长得再像也没关系。Python 的 Protocol 是**结构化类型**（structural）：兼容性看「形状」——方法齐了就算数，谁也不用声明。

```java
// 文件 1：PreapproveRule.java —— Java：必须 implements 才是「一家人」
import java.util.List;

public interface PreapproveRule {
    String apply(List<Integer> itemsCents);
}
```

```java
// 文件 2：ItemLimitRule.java —— 少写 implements，直接编译错误
import java.util.List;

public class ItemLimitRule {          // 想用？必须改成 ... implements PreapproveRule
    private final int limitCents;

    public ItemLimitRule(int limitCents) {
        this.limitCents = limitCents;
    }

    public String apply(List<Integer> itemsCents) {
        for (int c : itemsCents) {
            if (c > limitCents) {
                return "REJECT:ITEM_OVER_LIMIT";
            }
        }
        return "PASS";
    }
}
```

```python
# code/protocols.py —— Python：什么都不用声明，长得像就行
#（class 语法 L1.3 才主讲，此处只需看懂形状：一个只有方法签名、无实现的类）
# 两个提前量：self ≈ this 但必须显式写成第一个参数、调用时不传；__init__ ≈ 构造器——
# 练习里要手写，漏了 self 会得到 TypeError: ... takes 2 positional arguments but 3 were given
from typing import Protocol, runtime_checkable


@runtime_checkable
class Rule(Protocol):
    def apply(self, items: list[int]) -> str: ...  # ... = 只声明形状，不提供实现


class ItemLimitRule:  # 注意：没有 (Rule)！
    def __init__(self, limit_cents: int) -> None:
        self.limit_cents = limit_cents

    def apply(self, items: list[int]) -> str:
        if any(c > self.limit_cents for c in items):
            return "REJECT:ITEM_OVER_LIMIT"
        return "PASS"


class DirtyDataRule:  # 同样没有继承
    def apply(self, items: list[int]) -> str:
        if any(c <= 0 for c in items):
            return "REJECT:INVALID_AMOUNT"
        return "PASS"


def run_rules(rules: list[Rule], items: list[int]) -> str:  # 参数类型是协议
    for rule in rules:
        verdict = rule.apply(items)
        if verdict != "PASS":
            return verdict
    return "PASS"
```

四个要点：

- 协议方法体写 `...`（Ellipsis）：对照 Java interface 方法没有方法体。
- `run_rules` 的参数类型 `list[Rule]` 传 `ItemLimitRule` 实例完全合法——**pyright 在编译期做结构化检查**（静态版的鸭子类型）。这正是个成语的工程化：「走起来像鸭子、叫起来像鸭子，它就是鸭子」——只看行为不看出身；现在鸭子有了图纸（名义化的 interface 只认出身）。
- `@runtime_checkable` 解锁 `isinstance(rule, Rule)`（运行时只查「方法名在不在」，**不查签名与类型**——比静态检查粗得多）。没有这个装饰器，isinstance 一个 Protocol 直接 TypeError（`@` 装饰器语法 L1.5 才主讲，此处照抄——先别把它当 Java 注解，两者只是长得像）。
- 名义与结构不是宗教战争：框架两者都用（见 §6 路标——langchain 的 `Runnable` 是 ABC 名义基类，openai-agents 的 `Session` 是 runtime_checkable Protocol）。Python 给你选择权。

### 2.5.1 岔路口：「协议」这个词的四个意思

Python 世界说「协议」时，可能指四种东西，都**不是** Java 的 interface（除了今晚这个
最像）：① **typing.Protocol**（今晚）——结构化类型的声明工具；② **魔法方法协议**
（L1.3 起）——`__init__`/`__len__` 这类 dunder 约定，长出这些方法就算实现了「协议」；
③ **迭代器协议**（L1.6）——`iter()`/`next()` 那套；
④ **with 协议**（L1.7）——`__enter__`/`__exit__`。共性是「按形状认、不看出身」；看到「协议」先问自己指哪一种。

### 2.6 TypedDict：JSON 形状的轻量标注（一笔带过）

```python
from typing import TypedDict


class Claim(TypedDict):
    id: str
    items_cents: list[int]


claim: Claim = {"id": "CLM-2026-0001", "items_cents": [1200, 3500]}  # 键值形状受查
```

值类型不一的「异构」dict 用 `dict[str, int]` 表达不了，TypedDict 就是它的答案——L1.3 的 Pydantic 会把它升级成带校验的完整方案，这里混个脸熟即可。

### 2.7 类型收窄，与 is vs ==（附下划线惯例）

联合类型（`str | None`）的值，pyright 只允许你用「两边共有的操作」；想用 `str` 独有的，得先**收窄**（narrowing）：

```python
def late_fee_cents(days_late: int | None) -> int:
    if days_late is None:  # 收窄①：if 检查——之后 pyright 知道是 int
        raise ValueError("日期缺失应走人工通道")
    return days_late * 100  # 这里 days_late 已经是 int


def upper_first(verdicts: list[object]) -> None:
    for v in verdicts:
        if isinstance(v, str):  # 收窄②：isinstance——分支内 v 是 str
            print(v.upper())
        assert v is not None, "业务上不许 None"  # 收窄③：assert——之后的代码排除 None
```

对照 Java：`if (x instanceof String s)` 的 pattern matching for instanceof（Java 16+）与收窄①②同构——条件成立后的作用域里类型变具体。Python 没有这个语法糖，但 pyright 对 `isinstance` / `is None` / `assert` 的流分析效果一样。

**is vs ==**：`==` 问「值相等」（走 `__eq__`，可自定义）；`is` 问「是同一个对象」（身份，不可重载）。实测有保证的对照：

（`>>>` 是 Python REPL 提示符，≈ jshell 的 `jshell>`——终端 `uv run python` 或 IDE 的 Python Console 可跟做；照抄进 .py 文件会 SyntaxError）

```text
>>> a = [1200, 3500]; b = [1200, 3500]
>>> a == b          # 值相等 → True
>>> a is b          # 两个不同对象 → False
>>> a is a          # 同一对象 → True
```

对照 Java：`==` 比引用、`equals` 比值——你被 String 的 `==` 坑过的记忆直接平移过来，只是角色对调（Python 的 `==` 是 equals，`is` 才是引用比较）。CPython 对小整数（-5..256）和部分字符串有驻留缓存，`is` 有时「碰巧」为 True——**那是解释器实现细节，永远不要依赖**（正如你不依赖 JVM 的 String 池）。唯一例外是单例：**判 None 永远 `is None`**——`==` 可能被自定义 `__eq__` 劫持，`is` 不会。

**下划线命名惯例**（本课代码里已出现，正式交代）：`_x` 单下划线前缀 = 「内部用/可忽略」（循环里不要的变量惯用裸 `_`：`for _, verdict in results`，对照 Java 里 `var ignored = ...`）；`__x` 双下划线前缀 = 类内的名字改写（私有化，L1.3 讲）；`__x__` 双下划线包围 = dunder，解释器保留（`__init__`、`__name__`——L1.1 已见）。自己起名只用第一种。

## 3. 动手代码

以下命令都在本课目录 `units/unit1-core/L1.2-types-and-protocol/` 下执行（`uv run` 跨平台，Windows 无差异）。

### Step 1 同步与基线（2 分钟）

```bash
cd units/unit1-core/L1.2-types-and-protocol
uv sync
uv run pytest code/
```

### Step 2 读类型化全景（10 分钟）

打开 `code/typed_rules.py`：`parse_amounts` / `preapprove` / `first_rejected` / `reject_tally` / `late_fee_cents`——L0.1 的预算函数族扩编成类型标注教科书。重点读两处：

- `first_rejected` 的 `-> str | None` 与函数体里那条 `return None` 的路——签名如实说出所有出口；
- `late_fee_cents` 的收窄姿势：`if days_late is None: raise ...` 之后才敢 `days_late * 100`。

### Step 3 验证「运行时不强制」（3 分钟）

```bash
uv run python -c "x: int = 'abc'; print('照样运行, x =', x)"
```

亲手跑一次，破除「标注会不会拖慢/拦截」的疑虑；然后立刻跑 `uv run pyright` 看健康基线（0 errors）。

### Step 4 pyright 实验场：故意写错，看它怎么骂你（10 分钟）

往 `code/typed_rules.py` 的**任意位置**临时插一行：

```python
bad: int = "abc"
```

```bash
uv run pyright
```

你会看到类似 `code/typed_rules.py:行:列 - error: Type "Literal['abc']" is not assignable to declared type "int"` 的报错（pyright 报错格式：`文件:行:列 - error: 说明`）。再看一眼 IDE 里的同一行——VS Code 的 Pylance 红波浪线、PyCharm 自带检查的标红（要同引擎可装 Pyright 插件），都是同一条诊断。

> **IDE 侧（PyCharm）**：亲手试一次——临时写 `bad: int = "abc"`，看自带检查的标红与悬停说明（要与命令行 100% 同引擎可装 Marketplace 的 Pyright 插件）；删掉错行后 Problems 面板归零。

体验完**删掉这行**，`uv run pyright` 回到 0 errors 再继续。这个「写错 → 看报错 → 修复」的循环，就是你 Java 日常里 javac/IDEA 循环的 Python 版。

### Step 5 Protocol 与零继承实现（15 分钟）

打开 `code/protocols.py`（§2.5 的完整版）与 `code/test_protocols.py`：

```bash
uv run pytest code/test_protocols.py
```

`test_structural_isinstance`（isinstance 过审）与 `test_no_inheritance`（`__bases__ == (object,)`）同时绿——「没有继承却类型兼容」的机器证据。注意 `test_run_rules_priority` 里的 `rules: list[Rule] = [...]`：局部变量显式标注，让 pyright 按协议类型理解元素。

### Step 6 泛型（5 分钟）

```bash
uv run pytest code/test_generics.py
```

`first([3, 1, 2])` 与 `first(["REJECT", "PASS"])` 同一实现两种类型——T 在调用处自动绑定；`first([])` 抛 ValueError（`pytest.raises` ≈ JUnit 的 assertThrows）。

### Step 7 Any vs object 亲手对照（5 分钟）

```bash
uv run python -c "
from typing import Any


def shout_any(msg: Any) -> Any:
    return msg.upper()


print(shout_any('rejet'))
"
```

再把 `Any` 换成 `object` 存成临时文件跑 `uv run pyright`：`Any` 版零抱怨（检查被关掉），`object` 版报 `upper` 未知（只能调 object 的方法）——§2.3 的结论自己复现一遍。

### Step 8 收尾基线（3 分钟）

```bash
uv run pytest code/
uv run ruff check .
uv run pyright
```

`code/` 全绿；`exercises/` 是设计内的红，见下节。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——每题只改标注的 TODO 区，函数体与其余文件不要动。卡住先想 5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_annotate.py` | 给四个函数补类型标注（函数体已写好）：验收双通道 = 行为测试照过 + `get_type_hints()` 取出标注逐个比对 |
| ex2 | `exercises/ex2_protocol.py` | 写两个「零继承」的 Protocol 兼容类：验收 = `isinstance(sink, AuditSink)` 过 + `__bases__ == (object,)` + 精确格式行为测试 |
| ex3 | `exercises/ex3_tighten.py` | 把三个签名里的 `Any` 收紧成精确类型：验收 = 行为不变 + meta-test 递归扫描标注里不许藏任何 Any（`dict[str, Any]` 这种套壳也算） |

一个**设计内**的现象提前说明：练习 2 没完成时，`uv run pyright` 会对 exercises/ 报 `Cannot access attribute "record"`——这不是本课模板坏了，而是类型检查器抢在 pytest 之前告诉你「形状不完整」。把它当编译器，正是本课的主题。

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 直觉陷阱：Optional 不设防

- **现象**：`TypeError: unsupported operand type(s) for *: 'NoneType' and 'int'`——签名明明写了 `int | None`，运行时传 `None` 照样炸，标注一个字都没拦。
- **最小复现**：

  ```python
  def late_fee_cents_bad(days_late: int | None) -> int:
      return days_late * 100  # 标注说了「可能 None」，但运行时它不拦


  late_fee_cents_bad(3)  # 300，正常
  late_fee_cents_bad(None)  # TypeError: unsupported operand type(s) for *: 'NoneType' and 'int'
  ```

  同一段代码交给 pyright，静态就抓到了：`error: Operator "*" not supported for "None" (reportOptionalOperand)`——**同一个错误，pyright 在你运行之前就报**。

- **Java 直觉为何失效**：Java 里你会写 `@Nullable Integer` + `Objects.requireNonNull`，或者 `Optional<Integer>`——IDE 和编译器持续盯着可空性；Python 的标注则只是「贴在函数上的数据」，解释器运行时根本不读它。防护为零，只有静态检查这一道防线——这道防线不跑就等于没有。
- **修复与纪律**：**联合类型入口先收窄**——`if x is None: raise ...`（或返回默认值），收窄之后才当 `int` 用（对照 `code/typed_rules.py` 的 `late_fee_cents`）；把 `uv run pyright` 当 `javac` 纳入每次验收（夜校的三命令从 L0.1 起就这么干了）。反过来的对称坑也记一笔：返回类型写了 `str | None`，调用方就必须处理 None 分支——pyright 同样会盯。

## 6. 延伸

- typing 官方文档（ Protocol / TypedDict / 泛型 的权威定义）：https://docs.python.org/3/library/typing.html
- PEP 484（类型提示总纲）/ PEP 695（3.12 泛型新语法）：https://peps.python.org/pep-0484/ 、https://peps.python.org/pep-0695/
- pyright 官方文档（配置与诊断规则对照 mypy 的差异说明）：https://microsoft.github.io/pyright/
- openai/openai-agents-python@fbd2dbca#src/agents/memory/session.py —— 生产框架里的真 Protocol：`@runtime_checkable class Session(Protocol)`，注意它的方法体全是 `...`（纯形状声明）、以及它同时定义了默认值字段——你今晚写的东西和一线框架是同一种材料。
- langchain-ai/langchain@348c9dc572#libs/core/langchain_core/runnables/base.py —— 对照组：langchain 的 `Runnable` 是 **ABC（名义基类）** 而非 Protocol——同一个生态里两种类型风格并存，读完你能说清为什么（Runnable 有共享实现，纯形状才用 Protocol）。
- 《Fluent Python》第 2 版「Type Hints in Depth」与「Interfaces, Protocols, and ABCs」两章：本课的展开版，Protocol 一章尤其值得。

## 离毕业又近的一块

今晚的 `Rule` Protocol 就是毕业设计 fail-closed 执行门的**检查链接口**：限额 clamp、黑名单、频次检查各写成一个「长得像 Rule」的纯函数对象，链起来就是 L5.4 的三态裁决；`str | None` 与收窄纪律则是 Plan JSON 解析（L5.1）每天要打的仗——每个可空字段都是一扇要先锁上的门。类型这一课，是 PoC 敢叫「可维护」的底座。
