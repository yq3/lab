# L1.7 上下文管理器与异常处理：没有 checked exception 的世界

> 昨晚你用 `yield` 串起了「解析 → 过滤 → 汇总」的惰性管线：只有被拉取才工作、短路即省功，还解释了
> 「生成器第二次 for 是空的」——「流」的心智模型装好了。今晚处理流的另一半现实：出错怎么办。Python
> 没有 checked exception，`except Exception` 也有拦不住的对象；你要画出异常家族树、用 `raise ... from`
> 保留因果链，并以 `with` 和 `@contextmanager` 接管资源清理。

## 1. 本课目标

Python 的错误处理与资源清理，是 Java 心智被冲击最狠的一站。完成后你能：

- 画出异常体系全景（`BaseException -> Exception` 的分叉），解释 `except Exception` 为什么拦不住 Ctrl+C；
- 用 EAFP 风格写代码，并用「异常链 + 自定义异常分层」把底层错误翻译成领域语言；
- 用类协议和 `@contextmanager` 两种方式实现 `with`，说清它对照 try-with-resources 的同与不同。

这课是 **L2.4「校验错误回喂重试」的直接前置**：把校验失败变成可分类的异常对象，才能决定「回喂模型 / 上抛人工 / 直接 DENY」。

**完成判据**：本目录下 `uv run pytest` / `uv run ruff check .` / `uv run pyright` 三条同时全绿；附加自查：说出裸 `except:` 与 `except Exception:` 的差别。

## 2. 概念讲解

先给全课对照表，再逐小节展开：

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| checked exception（编译器强制处理/声明） | 不存在——全是运行时异常 | 「要么 catch 要么 throws」的编译期契约没了，纪律自己扛（§2.3） |
| `catch (IOException e)` | `except IOException as e` | 形态几乎同构；except 还支持元组一次多捕（§2.5） |
| `e.getCause()` / 手动 `initCause` | `raise ... from e` | 异常链是显式语法，不是事后补链（§2.6） |
| try-with-resources | `with` 语句 + 上下文管理器 | 同为清理必达；Python 把协议做进语言（§2.7） |
| `finally`（无论成败都执行） | `finally` + `else` | Python 多一个 else：没有异常才执行（§2.5） |
| 自定义异常 `extends Exception` | `class ExpenseError(Exception)` | 同款领域分层，但没有 checked/unchecked 之分（§2.9） |
| 匿名类 / lambda 装一段清理逻辑 | `@contextmanager` + `yield` | 清理写成生成器：yield 前后即 enter/exit（§2.8） |

### 2.1 异常体系全景：一棵两层的树

```text
BaseException                 <- 万物之根
├── SystemExit                <- sys.exit() 抛的（退出信号）
├── KeyboardInterrupt         <- Ctrl+C（中断信号）
└── Exception                 <- 「业务错误」全部在这棵子树下
    ├── ValueError            <- 值不对（NumberFormatException 的近亲）
    ├── TypeError / KeyError / IndexError / AttributeError ...
    ├── RuntimeError          <- 运行时状态不对
    └── 你的领域异常（ExpenseError -> LimitExceededError ...）
```

**为什么 `except Exception` 拦不住 Ctrl+C**：`KeyboardInterrupt` 是 `BaseException` 的**直接子类**，绕过了 `Exception` 子树——语言故意留的逃生门，否则一个手滑的 try 就能让你的进程杀不死（§5 坑位整段讲这个）。

**所有异常都是对象，可携带属性**：`e.claim_id`、`e.__cause__` 都只是普通属性访问——这给了「异常即领域事件」的玩法（本课动手 ③）。

### 2.2 内置异常对照表（Java 直译手册）

| 你熟悉的 Java 异常 | Python 对应 | 一句话 |
|---|---|---|
| `NullPointerException` | `AttributeError: 'NoneType' object has no attribute ...` | None 上取属性炸的是**属性错**，不是专门的空指针 |
| `NumberFormatException` | `ValueError: invalid literal for int() ...` | 解析失败归入「值错误」 |
| `ArrayIndexOutOfBoundsException` | `IndexError` | 序列下标越界 |
| `ClassCastException` | （无对应） | 动态类型没有运行时 cast 这一说 |
| `IllegalStateException` | `RuntimeError` | 「现在不该调这个」的兜底状态错 |
| `ArithmeticException: / by zero` | `ZeroDivisionError` | 连除零都单独一类——异常树更细 |
| `IOException` 等 checked 家族 | （无 checked） | 见下节 |

### 2.3 没有 checked exception：两种哲学

Java 里 `throws IOException` 把「可能失败」写进签名，调用方被编译器**强迫**处理；Python 没有这回事——**全部异常都是 unchecked**，函数签名不声明它可能抛什么。

那「文档化异常」靠什么？docstring 加类型标注：

```python
def parse_amount(raw: str) -> int:
    """解析金额文本。

    Raises:
        ValueError: raw 不是合法整数。
    """
```

两种哲学各说两句（诚实版）：

- **Java checked 的好**：签名即契约，漏接异常编译不过；**坏**：吞异常式样板（`catch (Exception e) {}`）泛滥，大量 API 干脆全包 `RuntimeException` 绕过检查——checked 在实践中已被 Java 社区自己半抛弃；
- **Python unchecked 的好**：代码不被强迫处理它处理不了的异常，「谁有上下文谁接」；**坏**：契约藏在文档里，漏接的异常在很远的地方炸，traceback 爬半天栈。

Python 的补课方案就是本课三件套：**分层异常类型**（接一层就接住一类）+ **异常属性携带上下文** + **pytest.raises 把异常契约写进测试**（练习 2 实操）。

### 2.4 EAFP vs LBYL：先斩后奏是主流

```python
# LBYL（Look Before You Leap）——Java 人的本能：
if claim_id in claims:
    amount = claims[claim_id]

# EAFP（Easier to Ask Forgiveness than Permission）——Python 主流：
try:
    amount = claims[claim_id]
except KeyError:
    ...
```

为什么 EAFP 在 Python 是主流：

1. **与鸭子类型更配**：LBYL 要检查就得问「你是什么」（isinstance），EAFP 只管「试了再说」——对象有没有那个行为，用了才知道；
2. **与并发更配**：`if key in d` 与 `d[key]` 之间状态会变（另一个执行流删了 key），检查是白检查；`try` 把「使用」本身变成事实标准。L1.9 讲 asyncio 时会回扣这一点（动手 ① 有个确定性的竞争模拟）；
3. **快乐路径零噪音**：正常逻辑裸奔，异常路径集中一处。

Java 也有 EAFP（`Optional.orElseThrow`、并发里的「先 CAS 再说」），但 Python 把它做成了文化。L1.6 的 `StopIteration` 你已经见过一个：「异常当控制流」在 Python 不是坏事，是设计。

### 2.5 捕获语法全家：except / 元组 / as / else / finally

```python
try:
    risky()
except (ConnectionError, TimeoutError) as e:  # 多类型一个元组；as 取对象
    retry()
except ValueError:  # 从具体到宽泛排
    log()
else:  # 只在「没出事」时执行（try 成功的延伸段）
    commit()
finally:  # 无论如何都执行（return/异常都拦不住）
    cleanup()
```

`else` 是 Java 没有的子句：它把「可能出事的代码」（try）和「依赖成功结果的代码」（else）分开——出了事 else 根本不执行，而写在 try 尾部的代码会被本段的 except 捕到（练习 1 专门考这个区别）。

**裸 `except:` 与 `except BaseException:` 为什么 Worst**：它们连 `KeyboardInterrupt` / `SystemExit` 一起吞——Ctrl+C 杀不死程序、`sys.exit()` 退不出去。要么 `except Exception`，要么更具体的类型（§5 全段剖析）。

### 2.6 raise 与异常链：cause 的显式与隐式

```python
try:
    amount = int(raw)
except ValueError as exc:
    raise AmountParseError(f"金额字段不是整数: {raw!r}") from exc  # 显式因果链
```

| 姿势 | 语义 | 对照 Java |
|---|---|---|
| `raise X from e` | `X.__cause__ = e`，traceback 打印 "direct cause" | `new X(msg, e)` 传 cause |
| `raise X`（except 块内） | `X.__context__ = e`（隐式上下文，打印 "during handling"） | 没有对应——Java 会丢上一层 |
| `raise`（裸，except 块内） | 原对象原样重抛，traceback 完整保留 | `throw e;`（但不会刷新栈） |
| `raise X from None` | 切断因果链（底层异常是噪音时） | 无对应 |

纪律：**包装异常时永远 `from exc`**——保留因果链，排查时一段 traceback 看到底（动手 ② 打印给你看）。

### 2.7 with 协议：清理必达的语言化

Java 7 的 try-with-resources 解决「close 必达」；Python 的 `with` 解决同一件事，但做成了**可组合的协议**而不仅是语句：

```python
# Java: try (var session = open()) { ... }   // session 必须 implements AutoCloseable
# Python:
with ApprovalSession("CLM-1") as session:  # 任意实现 __enter__/__exit__ 的类
    session.review()  # 出了事也保证 __exit__ 被调用
```

协议两个方法：

```python
class ApprovalSession:
    def __enter__(self) -> "ApprovalSession": ...  # 进 with 前夕执行：开事务 / 拿锁 / 打开资源；返回值给 as
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        ...  # with 体结束时执行（正常与异常都来）：commit/rollback、close
        return False  # False=不吞异常（继续传播）；True=吞掉（冷知识，别滥用）
```

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| `AutoCloseable` 接口 | `__enter__` + `__exit__` 协议 | Python 无接口声明，凑齐两个方法就算 |
| try-with-resources（语句级） | `with`（表达式级） | with 的对象可传递、可组合（ExitStack 动态管理一串） |
| `close()` 单钩子 | `__exit__` 看得到异常三件套 | 知道「为什么退出」，才能决定 commit 还是 rollback |
| 多资源 `try (a; b)` | 多个 with / 嵌套 with | 语义相同：获取顺序的逆序释放 |

### 2.8 @contextmanager：上一课 yield 的直接复用

类协议要写两个方法；`@contextmanager` 让你**用生成器函数写上下文管理器**——课程设计线在这里收拢：L1.6 的「函数可以暂停」直接变成 with 的两个阶段：

```python
@contextmanager
def timed_block(label, log):
    start = perf_counter()
    try:
        yield  # <- with 体在这里执行（__enter__ 与 __exit__ 的分界线）
    finally:
        log.append((label, perf_counter() - start))  # 清理必达
```

`yield` 之前 = `__enter__`，之后 = `__exit__`，`finally` = 异常也执行。库代码与框架里大量上下文管理器都是这么写的（比类协议轻得多）。多资源动态管理有一个 `ExitStack`（进阶，一句带过：把一串上下文管理器叠着进、逆序出）。

### 2.9 自定义异常：领域分层

```python
class ExpenseError(Exception):  # 领域基类：调用方 except 这一个就接住全家
    def __init__(self, claim_id, message):
        super().__init__(message)
        self.claim_id = claim_id  # 证据随异常走


class InvalidAmountError(ExpenseError): ...


class LimitExceededError(ExpenseError): ...
```

三条纪律：**领域异常只从一个基类往下长**（顶层 except 一网打尽）；**属性带证据不带秘密**（别把密钥塞进异常消息）；
**REJECT 语义优先用返回值、异常留给「中断性失败」**——这条是毕设 fail-closed 执行门的地基（该 DENY 是正常业务分支，不该用异常表达；管线解析失败才是异常）。

## 3. 动手代码

五个模块都在 `code/`，先 `uv sync`；`uv run pytest code/` 应全绿（它们不是你的练习）。

### Step 1 EAFP 版安全取数（含竞争模拟）

```bash
cd units/unit1-core/L1.7-context-exceptions
uv sync
uv run python code/eafp_demo.py
```

三种取数（LBYL / EAFP / `dict.get`）结果一致；`RacyClaims` 用一个「检查时就丢数据」的 dict 子类**确定性地**模拟并发竞争——LBYL 当场 KeyError，EAFP 安然无恙。这是 L1.9 的前菜：检查与使用之间，执行权可能已经让出去了。

### Step 2 异常链实验（traceback 看链）

```bash
uv run python code/chains.py
```

`parse_amount` 把底层 `ValueError` 包成 `DomainError`，`raise ... from exc` 之后 traceback 会打出两段栈和一行 `The above exception was the direct cause of ...`——对照 2.6 的表格看输出。
文件里还有裸 `raise`（原样上抛）与 `from None`（切断链）两个对照组。

### Step 3 报销异常分层 + with 审批会话

```bash
uv run pytest code/test_expense_errors.py code/test_approval_session.py
uv run python code/approval_session.py
```

`expense_errors.py` 是 2.9 那棵异常树的全款实现（`claim_id` / `limit_cents` 随行）；`approval_session.py` 用类协议实现「开事务 -> 无异常 COMMIT / 有异常 ROLLBACK」，还演示了 `__exit__` 返回 True 吞异常的冷知识——看完你就懂为什么生产代码不该这么写。

### Step 4 @contextmanager 版计时器 / 临时目录

```bash
uv run python code/ctx_tools.py
```

`timed_block`（L1.5 timing 装饰器的 with 版表亲）与 `scratch_dir`（临时目录，异常退出也整目录删除）。注意两件事：`yield` 前后正好是 `__enter__`/`__exit__` 的分界；`finally` 让清理必达。

### Step 5 裸 except 反面演示（文档描述，别真卡 30 秒）

下面这段程序**不要真的运行后等它**（Ctrl+C 杀不死，最后得 kill 进程）——读一遍就懂：

```python
import time

while True:
    try:
        time.sleep(1)
        print("工作中")
    except BaseException:  # 把 Ctrl+C（KeyboardInterrupt）也吞了
        print("什么也杀不死我")  # 按 Ctrl+C 只会看到这行，循环继续
```

把 `except BaseException:` 换成 `except Exception:`，Ctrl+C 立刻生效——两词之差，一个进程的生死。§5 从「纪律」角度再钉一遍。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——每题只改标注的 TODO 区。卡住先想 5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_flow.py` | try/except/else/finally 完整结构；验收：两条路径的 trace 顺序断言 |
| ex2 | `exercises/ex2_custom_error.py` | 异常分层 + `raise from` + `pytest.raises`；验收：类型（含 isinstance 分层）/ 消息 match / `__cause__` 三重断言 |
| ex3 | `exercises/ex3_context.py` | `@contextmanager`；验收：正常路径限额改了又恢复、**异常路径**限额照样恢复且异常正常传播 |

ex2 顺带把 `pytest.raises` 的标准姿势教给你（`as exc_info` 取对象、`match=` 查消息）——L2 起天天用。

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：裸 except 吞天坑

- **现象**：一个顺手写的 `except:` 把 `KeyboardInterrupt` / `SystemExit` 一起吞了。症状：Ctrl+C 杀不死程序（终端只重复打印或干脆无反应）、`sys.exit()` 退不出去、调试器断点失灵、CI 里挂死的 job。**没有任何报错**——一切「正常」运行，只是失控。
- **最小复现**（§3 Step 5 的短版，读代码即可）：

  ```python
  import time

  try:
      time.sleep(60)
  except:  # 裸 except == except BaseException
      pass  # Ctrl+C 进来也被 pass 掉——你的 60 秒变成了永远
  ```

  按下 Ctrl+C，解释器抛 `KeyboardInterrupt`，被裸 except 吞掉，程序继续睡。
- **Java 直觉为何失效**：`catch (Exception e)` 在 Java 里**不会**拦 `Error` 和中断信号，所以「catch 宽一点没关系」的直觉带不过来；
  最接近的 `catch (Throwable t)` 至少**看起来刺眼**、IDE 会劝退你，而 Python 裸 `except:` 只有五个字符，顺手就写，没有任何警告——太顺了，没人警觉。
- **修复与纪律**：`except Exception` 起步，能写具体类型就写具体类型；裸 `except:` 只允许出现在**最外层的日志收尾处**，且必须 re-raise（`except: log(...); raise`——裸 raise 把 KeyboardInterrupt 也原样放行）。团队里见到裸 except，直接打回。

## 6. 延伸

- 官方错误与异常教程：https://docs.python.org/zh-cn/3.12/tutorial/errors.html
- contextlib 文档（contextmanager / closing / ExitStack / suppress）：https://docs.python.org/zh-cn/3.12/library/contextlib.html
- 《Fluent Python》第 2 版「装饰器与闭包」章对 `@contextmanager` 实现的源码级剖析（它就是靠 L1.6 的生成器协议驱动的），以及异常相关的「Iterators, Generators」章尾；
- 框架真实异常体系源码（两版对照，都是「领域异常基类 + 属性携带上下文」的实践）：
  - agentscope@b82253ba#src/agentscope/exception/_base.py —— 27 行的教科书样本：`AgentOrientedException`（错误回喂给 agent 处理）与 `DeveloperOrientedException`（错误上抛给开发者）两个基类——
    **「这个错该由谁处理」直接做进异常类型**，这正是 L2.4 校验错误回喂重试的语义雏形；具体子类看同目录 `_tool.py`（`ToolNotFoundError` 等四个）；
  - openai-agents-python@fbd2dbca#src/agents/exceptions.py —— 搜 `class AgentsException`：SDK 全部异常的基类，`run_data` 属性携带整次运行上下文（比 claim_id 激进得多），子类 `MaxTurnsExceeded` / `ModelBehaviorError` 各带专属属性——异常即事件的对象化样本。

## 离毕业又近的一块

L2.4 的「校验错误回喂重试」今晚配齐了全部零件：结构化输出解析失败时，用 `raise ParseError(...) from exc` 包住底层 JSON 错误（保留因果链），异常对象携带校验错误详情（属性带证据），回喂给模型重试——
agentscope 那两个基类的「谁处理这个错」的分法，就是那条流水线的岔路口。
毕业设计 fail-closed 的「不可解析即 DENY」，也是今晚「REJECT 用返回值、异常留给中断性失败」这条纪律的放大版。
