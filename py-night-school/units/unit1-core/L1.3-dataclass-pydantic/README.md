# L1.3 数据建模：dataclass 与 Pydantic v2

> 昨晚你写出了 `Rule` Protocol 和它的零继承实现（长得像就行，无需 implements），还练了 `str | None`
> 先收窄再运算的纪律——标注这层骨架有了，但数据本身还是散装的。今晚解决「数据长什么样」：先用手写
> 类的 38 行痛苦换 `@dataclass` 的 11 行声明，再用 Pydantic `BaseModel` 做到「构造即验证」——agent
> 框架里消息与工具 schema 的底座全是它。

## 1. 本课目标

写出「Java record 的对应物」，并理解 agent 世界的血管为什么全是 Pydantic。完成后你能：

- 手写一个朴素 Python 类，说清 `__init__` 与 `self` 到底在干什么（以及它为什么这么设计）；
- 用 `@dataclass` 把 38 行手写痛苦版换成 11 行声明版，并解释它**不验证任何东西**；
- 用 Pydantic `BaseModel` 定义「构造即验证」的数据模型（约束、嵌套、替代构造、序列化三件套），
  并说清**校验发生在哪一刻**——类被调用的那一刻，不是之后；
- 读懂 `ValidationError` 的完整报错（位置 / 类型 / 原因 / 原始输入）。

**完成判据**：本目录下三条命令同时全绿——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

本课是夜校第一个带**运行时依赖**的课时：`pydantic>=2` 写在 `pyproject.toml` 的 `dependencies`
（≈ Maven compile scope），而 pytest / ruff / pyright 在 dev 依赖组（≈ test scope）——
运行时依赖进产品，验收依赖只进课堂，从这课起要分得清。

## 2. 概念讲解

先给全课对照表，再逐个展开：

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| 类声明 + 字段声明区 | `class` 语句 + `__init__` 里挂属性 | Python 没有「字段声明区」这回事，属性是运行时挂上去的 |
| 构造器 | `__init__`（初始化方法，非构造器） | `new` 不存在：调用类本身 `Cls(...)` 就是创建实例 |
| 隐式 `this` | 显式 `self`（方法的第一个参数） | 方法就是函数，实例是第一个参数——「显式优于隐式」 |
| IDE 生成的 toString / equals | `__repr__` / `__eq__` | 不写 repr 打内存地址；写 `__eq__` 则失去 `__hash__` |
| record（不可变值对象） | `@dataclass(frozen=True)` | record 天生不可变；dataclass 默认可变，frozen 是开关 |
| `private List<X> items = new ArrayList<>();` | `field(default_factory=...)` | Java 每次构造执行；Python 只算一次 |
| bean + Bean Validation + Jackson | Pydantic `BaseModel` | 三件套合体：解析、校验、序列化发生在同一次构造里 |
| 静态工厂 `valueOf` / `List.of` | `@classmethod` 替代构造 | 首参数是类本身（`cls`），子类继承时自动正确 |

### 2.1 先补地基：第一次正式写 Python 类

夜校到这里才第一次完整展示类定义语法——不跳步，一块块搭。

**class 语句**：冒号 + 缩进代替花括号（缩进即语法，L0.1 陷阱讲过）；类名没有 `public/private`
前缀——可见性约定靠下划线前缀（`_x` 表示「内部用」，纯约定），本课全用公有。

**`__init__` 与 self**——并排看：

```python
class ExpenseClaimManual:
    def __init__(self, claim_id: str, submitter: str, items_cents: list[int] | None = None) -> None:
        self.claim_id = claim_id  # 给「这个实例」挂一个属性
        self.submitter = submitter
        self.items_cents = items_cents if items_cents is not None else []
```

```java
public class ExpenseClaimManual {
    private final String claimId;      // 字段在类体声明，构造器只是赋值
    private final String submitter;
    private final List<Integer> itemsCents;

    public ExpenseClaimManual(String claimId, String submitter, List<Integer> itemsCents) {
        this.claimId = claimId;        // this 是隐式传入的
        this.submitter = submitter;
        this.itemsCents = itemsCents == null ? new ArrayList<>() : itemsCents;
    }
}
```

五个必须说清的点：

1. `__init__` **不是构造器**，是初始化方法：你写 `ExpenseClaimManual("CLM-2026-0001", "王工")` 时，
   解释器先创建空实例，再把 `(实例本身, "CLM-2026-0001", "王工")` 传给 `__init__`。
   双下划线前后缀（dunder）的名字是 Python 协议方法的保留字——对照 `toString`/`equals` 的地位。
2. `self` 就是那个「实例本身」。它必须显式写在参数表第一位，这是**设计而非省事**：
   Python 里方法本质是普通函数，`obj.method(x)` 只是 `Class.method(obj, x)` 的语法糖——
   你甚至可以用后者形式调用，等价。Java 把这层映射藏在 JVM 里，Python 把它亮给你看。
3. **实例属性没有声明区**：`self.claim_id = ...` 这行执行之前，实例上没有 `claim_id`。
   对照 Java「字段在类体、构造器只赋值」的心智——Python 的属性是逐个「挂」上去的。
4. `list[int] | None` 读作「int 列表或 None」——`None` 是 Python 的空值（≈ `null`，但它是
   一个真实存在的对象），`X | None` 等价 Java 的 `Optional<X>` 直觉，且是运行时真实类型。
   None 哨兵 + 体内替换是可变默认值的纪律写法（§5 陷阱的主角）。
5. 不写 `__repr__` / `__eq__` 的代价：`print(claim)` 打出 `<...object at 0x1024...>`，
   两个内容相同的实例 `==` 判不相等（默认按身份比较，≈ 没重写 equals 的 Java 对象）。
   手写它们有多痛，§3 Step 1 亲测。

还有一个 Java 没有的连带效应：**一旦定义了 `__eq__`，Python 自动把 `__hash__` 置为 None**，
实例从此不可哈希（进 set / 当 dict key 直接 TypeError）。这是「重写 equals 必须同时重写
hashCode」契约的 Python 镜像——Java 靠纪律，Python 直接强制翻车给你看。

### 2.2 dataclass：把样板交给装饰器

`@dataclass` 先当语法用（L1.5 拆它的原理，今晚只需要知道：装饰器是「接收类、返回增强版类」
的函数应用语法）。它读类体里的类型标注，自动生成 `__init__` / `__repr__` / `__eq__`：

```python
from dataclasses import dataclass, field


@dataclass
class ExpenseClaimData:
    claim_id: str  # 「字段名: 类型」既是标注也是字段声明
    submitter: str
    items_cents: list[int] = field(default_factory=list)  # 可变默认值的唯一正确姿势
    note: str = ""  # 不可变类型的默认值可以直接写
```

```java
// Java 14+：record 是「纯数据载体」的语法答案
public record ExpenseClaimData(String claimId, String submitter,
                               List<Integer> itemsCents, String note) {}
```

逐点对照：

| 维度 | Java record | Python `@dataclass` |
|---|---|---|
| 生成物 | 构造器 + `equals` + `hashCode` + `toString` | `__init__` + `__eq__` + `__repr__`（`__hash__` 默认没有） |
| 可变性 | 字段 final，天生不可变 | 默认可变；`frozen=True` 才不可变 |
| 可哈希 | 自动（全字段 `hashCode`） | 默认不可哈希；`frozen=True` 时自动生成 `__hash__` |
| 默认值 | 不支持（工厂方法补） | 原生支持，可变值必须走 `default_factory` |
| 解构 | record 模式匹配 | 无内置（本课不展开） |

`field(default_factory=list)` 为什么必须：默认值只在**类定义时求值一次**，裸 `= []`
会让所有实例共享同一个列表对象；dataclass 干脆在定义时直接抛 `ValueError` 拒绝你
（最小复现见 §5）。对照 Java：字段初始化器 `= new ArrayList<>()` 是**每次构造都执行**的
语句——Java 直觉在这里失效，因为 Python 的默认值不是「语句」而是「定义时算好的对象」。

最后一条边界最重要：**dataclass 不验证任何东西**。`claim_id: str` 的类型标注对解释器
只是文档——传个 `"garbage"` 单号、负数金额照样构造成功。类型标注在 dataclass 里
服务的是 IDE 和 pyright（还记得吗，类型是给人看的，不是给解释器看的）。
要「脏数据进不来」，需要下一站。

### 2.3 Pydantic BaseModel：bean + Bean Validation + Jackson 三件套合体

同一个报销单模型，Java 世界的完整装备 vs Pydantic：

```python
from datetime import datetime
from typing import Annotated
from pydantic import BaseModel, Field


class ExpenseClaim(BaseModel):
    claim_id: str = Field(pattern=r"^CLM-\d{4}-\d{4}$")
    items_cents: list[Annotated[int, Field(gt=0)]]  # 列表元素级约束写进泛型参数
    submitter: str = Field(min_length=1)
    submitted_at: datetime | None = None  # 可选字段
```

```java
// ① bean + Bean Validation 注解（校验还要自己接 ValidatorFactory 才生效）
public class ExpenseClaim {
    @Pattern(regexp = "^CLM-\\d{4}-\\d{4}$")
    private String claimId;
    private List<@Min(1) Integer> itemsCents;
    @NotBlank
    private String submitter;
    private LocalDateTime submittedAt;   // 可选
}
// ② 反序列化（Jackson）：new ObjectMapper().readValue(json, ExpenseClaim.class)
// ③ 序列化：mapper.writeValueAsString(claim)
// 而且 ① 的校验和 ② 的解析是两套机制、两个时刻——顺序错了脏数据就溜进来了
```

Pydantic 把三件事压成**同一时刻**：

| Java 动作 | Pydantic 动作 | 校验时机 |
|---|---|---|
| `readValue` + 手动触发 validate | `ExpenseClaim(**dict)` 或 `model_validate(dict)` | **构造那一刻**，两者合一 |
| `readValue(json, ...)` | `model_validate_json(json_str)` | 同上（还多挡一层 JSON 语法错） |
| `writeValueAsString` | `model_dump()`（dict）/ `model_dump_json()`（str） | 序列化不校验，只是出口 |

「校验发生在哪一刻」的完整答案：**类被调用的那一刻**。`ExpenseClaim(claim_id="bad", ...)`
这行代码本身就会抛 `pydantic.ValidationError`（不是事后调 validator）——所以非法对象
在 Python 世界里**根本无法被造出来**，比「造出来再拒收」早一整拍。附带福利是类型收敛：
喂 ISO 字符串的 `submitted_at`，拿到手已是 `datetime` 对象（Jackson 反序列化的直觉，零配置）。

为什么 agent 框架全选它当血管：LLM 的输出是不可信的 JSON 字符串——消息（messages）、
工具参数（function calling 的 arguments）、配置对象，全靠 `model_validate` 一步
「解析 + 校验 + 类型收敛」，不合法立刻拒。L2.4 结构化输出的全部地基就是本课这几十行。

### 2.4 classmethod：替代构造

Java 的静态工厂（`Integer.valueOf`、`List.of`）在 Python 的对应物是 `@classmethod`：

```python
class ExpenseClaim(BaseModel):
    ...

    @classmethod
    def from_cents_string(cls, claim_id: str, submitter: str, cents_string: str) -> "ExpenseClaim":
        items: list[int] = []
        for part in cents_string.split(","):
            items.append(int(part.strip()))
        return cls(claim_id=claim_id, submitter=submitter, items_cents=items)
```

三个展开点：

- `@classmethod` 把方法的第一个参数从实例换成**类本身**（惯用名 `cls`）——不用先有实例就能调：
  `ExpenseClaim.from_cents_string("CLM-2026-0001", "王工", "1200,3500")`；
- `cls(...)` 而不是写死 `ExpenseClaim(...)`：子类调用时拿到的 `cls` 是子类，工厂自动正确
  ——对照 Java 静态工厂写死类名、子类继承会踩坑的老问题；
- 返回类型注解写成**字符串** `"ExpenseClaim"`：类体执行到这行时类还没定义完，字符串
  （前向引用）让注解延迟生效——pyright 认得它，这是标准写法不是偷懒。

## 3. 动手代码

### Step 1 手写朴素类，痛一次（15 分钟）

打开 `code/naive_claim.py`：一个只有四个字段 + 三个方法的值类，手写版 38 行——
`__init__` 挂属性、`__repr__` 手拼字符串、`__eq__` 逐字段比较（还要记得 `NotImplemented`
协议）。每个方法对照 Java 心里的 `toString` / `equals` 读一遍，然后：

```bash
uv run pytest code/test_naive_claim.py
```

重点看两个测试：默认列表各拿各的（None 哨兵纪律）、定义了 `__eq__` 后 `hash()` 直接
TypeError——都是 Java 没有的体感。

### Step 2 dataclass 改写（10 分钟）

打开 `code/dataclass_claim.py`：`ExpenseClaimData` 与手写版**行为等价**，声明只要 11 行
（真正的字段声明 5 行）。多出来的 `Policy` 是 `frozen=True` 演示——不可变、可哈希，
最接近 record 的形态：

```bash
uv run pytest code/test_dataclass_claim.py
```

看三个测试：`test_dataclass_validates_nothing`（垃圾数据照样构造——不验证的铁证）、
`test_bare_mutable_default_is_blocked_at_class_definition`（dataclass 把裸 `= []`
挡在类定义时）、`test_frozen_policy_is_immutable_and_hashable`。

### Step 3 Pydantic 版报销单（15 分钟）

打开 `code/claims.py`：`ExpenseClaim`（四字段带约束 + `from_cents_string` 替代构造）
与 `ClaimBatch`（嵌套：`claims: list[ExpenseClaim]`）。

```bash
uv run pytest code/test_claims.py
```

重点看：ISO 字符串进、`datetime` 出；非法数据在**构造那一行**抛 `ValidationError`；
嵌套元素的校验错误带着完整路径（下一 Step 眼见为实）。

### Step 4 读懂 ValidationError 的完整报错（10 分钟）

```bash
uv run python code/validation_demo.py
```

真实输出（三处伤一起报，不是只报第一个）：

```text
3 validation errors for ClaimBatch
claims.1.claim_id
  String should match pattern '^CLM-\d{4}-\d{4}$' [type=string_pattern_mismatch, input_value='bad-id', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/string_pattern_mismatch
claims.1.items_cents.1
  Input should be greater than 0 [type=greater_than, input_value=-1, input_type=int]
    For further information visit https://errors.pydantic.dev/2.13/v/greater_than
claims.1.submitter
  String should have at least 1 character [type=string_too_short, input_value='', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/string_too_short
共 3 处错误（上面每一行小标题都是一处）
```

怎么读：每处错误四要素——**位置**（`claims.1.claim_id`：第二张单（下标 1）的单号字段，
嵌套路径直达案发现场）、**类型**（`string_pattern_mismatch`：机器可判的错误码，
程序里按它分流重试或拒收）、**人话原因**（String should match pattern...）、**原始输入**
（`input_value='bad-id'`：留证据，别打印整个对象）。`exc.errors()` 拿到的就是这四要素的
dict 列表——L2.4「校验错误回喂重试」喂给模型的正是它。

### Step 5 序列化三件套观察（10 分钟）

`test_claims.py::test_dump_and_roundtrip` 一步看全：`model_dump()` 出 dict（`datetime`
保持对象）、`model_dump_json()` 出 JSON 字符串（`datetime` 自动 ISO 化）、
`model_validate` / `model_validate_json` 吃回 dict / JSON 字符串，往返相等。
这一来一回，就是「模型是数据的中枢格式」的含义。

### Step 6 对照源码（5 分钟）

§6 的两条源码路标现在可以读了：langchain 的 `BaseMessage` 是个生产级 Pydantic 模型
（agent 世界的「消息」本体），openai-agents 的 `items.py` 同一文件里 dataclass 与
Pydantic 各司其职。带着今晚的眼睛去看：`Field(default_factory=...)` 满屏都是。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——每题只改标注的 TODO 区，其余文件与代码区不要动。卡住先想
5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_dataclass.py` | 手写类改写成 dataclass：行为等价验收（构造 / 相等 / repr / 默认值隔离） |
| ex2 | `exercises/ex2_schema.py` | 补 Pydantic 字段约束 + 补非法样本表（meta-test 判定覆盖） |
| ex3 | `exercises/ex3_batch.py` | 嵌套模型 + `from_lines` 替代构造（model_dump 结构断言） |

三题的验收口径：

- ex1 行为等价之外，`is_dataclass(ExpenseLineData)` 必须为 True——把上面的手写类换个名字
  抄下来糊弄过不了；
- ex2 双向判据：合法样本全过、非法样本全部被 `ValidationError` 拒收；样本表本身要覆盖
  三个字段各自的违规、至少 4 组、不重复（文件内 meta-test 机器判定）；
- ex3 最终判据是 `model_dump()` 输出结构逐键断言；非法数据（坏单号 / 负金额 / 空类目）
  必须在构造那一刻被拒。

发货态的诚实说明（「发货态」= 仓库克隆下来、练习未做的初始状态；三命令全绿即「毕业态」）：现在跑 `uv run pytest`，练习区是设计内的红（TODO 未填）；跑 `uv run pyright`
会顺带报 ex1 测试里「参数数量不匹配」——那是空壳 dataclass 还没字段的回声，补完字段自动消失。

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 直觉陷阱：dataclass 可变默认

这是本课的命名化失败模式，以后说「可变默认」我们秒懂。

- **现象**：`ValueError: mutable default <class 'list'> for field items is not allowed:
  use default_factory`——注意，是**类定义时**抛，不是运行时踩雷。
- **最小复现**：

  ```python
  from dataclasses import dataclass


  @dataclass
  class Bad:
      items: list[int] = []  # ValueError 当场炸——dataclass 帮你挡了
  ```

- **Java 直觉为何失效**：Java 的字段初始化器 `private List<Integer> items = new ArrayList<>();`
  是**每次构造都执行的语句**，天然每实例一份。Python 的默认值不是语句，是**类定义时求值一次
  的对象**——之后所有实例共享同一个 list。Java 里「默认值 = 每次现做」，Python 里
  「默认值 = 定义时做好的那一个」，心智模型差在这一句。
- **修复与纪律**：可变默认值一律 `field(default_factory=list)`——「工厂」= 每个实例构造时
  调一次 `list()` 现做。手写类没有护栏，纪律是 None 哨兵（`code/naive_claim.py` 的写法）。
  顺带两个边界：Pydantic v2 对裸可变默认值做了每实例拷贝保护（我们实测过 `is not` 成立），
  但别依赖——统一 default_factory 肌肉记忆最稳；而**普通函数的默认参数没有任何护栏**，
  同一颗雷换个地方埋，L1.4 §5 是它的主场。

## 6. 延伸

- dataclasses 官方文档（field 全部选项、`__post_init__`）：https://docs.python.org/3/library/dataclasses.html
- Pydantic v2 官方文档 Concepts 三连（对照今晚的模型/字段/错误）：https://docs.pydantic.dev/latest/concepts/models/
- langchain@348c9dc572#libs/core/langchain_core/messages/base.py —— agent 世界的「消息」本体
  `BaseMessage`：生产级 Pydantic 模型长什么样（`Field(default_factory=dict)` 满屏、可选字段、
  `model_config`），今晚每个语法点都能在里面找到回声；
- openai-agents-python@fbd2dbca#src/agents/items.py —— 同一个文件里两种建模各司其职：
  `RunItemBase` 是 `@dataclass`（运行轨迹条目，无需校验），它持有的 `raw_item` 是
  Pydantic `BaseModel`（来自模型 API，必须校验）——「什么时候用哪个」的生产答案；
- 《Fluent Python》第 2 版第 5 章「数据类构建器」（frozen 与不可变性可续读第 6 章）。

## 离毕业又近的一块

毕业设计的 Plan JSON（L5.1「Pydantic 强约束 + 工具白名单」）的 schema 写法，今晚全部练完；
L2.2 工具协议里「Pydantic 模型 → JSON Schema → 工具注册表」的第一环、L2.4 结构化输出
「模型吐 JSON → 校验 → 拒了回喂重试」的地基，也都是今晚这个 `ExpenseClaim`。你刚写下的
每一个 `Field(pattern=...)`，毕业设计里都会以十倍的规模再出现。
