# L1.1 运行模型与模块系统：一个 .py 怎么变成运行中的程序

## 1. 本课目标

说清两件 Java 里「基础设施替你干了」的事：**一个 `.py` 文件怎么变成运行中的程序**，以及 **`import` 那一行到底发生了什么**。完成后你能：

- 解释 CPython 的执行方式，以及 `__pycache__/` 里那堆 `.pyc` 是什么（「Python 没有编译」是以讹传讹）；
- 把手写脚本组织成包（目录 + `__init__.py`），并说清模块名、包名与文件名的关系；
- 逐行解释 `if __name__ == "__main__"`——Python 版的入口方法约定；
- 用 `python -m 包.模块` 正确启动包内入口，并知道为什么直接跑文件会炸。

**完成判据**：本目录下三条命令同时全绿——

```bash
uv run pytest          # code/ 全绿；exercises/ 在完成练习前呈「精确红」
uv run ruff check .    # 无 lint 违规
uv run pyright         # 无类型错误
```

## 2. 概念讲解

### 2.1 运行模型：不是「没有编译」，是「没有独立编译步骤」

| 你熟悉的 Java 物 | Python 对应物 | 一句话差异 |
|---|---|---|
| `javac Hello.java` → `Hello.class` | （无显式步骤） | 编译发生了，只是自动且透明 |
| JVM 加载 `.class` 执行字节码 | CPython 编译 `.py` 为字节码并直接执行 | 「解释执行」的准确含义：编译是运行的前置子步骤 |
| `.class` 是部署物，必须随包发布 | `.pyc` 是**缓存**，删了也能跑（下次重新编译） | 产物角色完全不同 |
| `mvn clean` 清 `target/` | `__pycache__/` 目录 | 同为构建残留，后者 Python 运行时自建自管 |

先看并排版（完整、可各自跑通）：

```java
// Hello.java —— Java：两个显式步骤
public class Hello {
    public static void main(String[] args) {
        System.out.println("hello from " + Hello.class.getName());
    }
}
// 终端：javac Hello.java   生成 Hello.class
// 终端：java Hello         JVM 加载字节码执行
```

```python
# hello.py —— Python：一个步骤
print(f"hello from {__name__}")

# 终端：python hello.py     CPython 先把源码编译成字节码，再立即执行
# （import 一个模块时，字节码会缓存进 __pycache__/，直接运行的脚本不缓存）
```

所以对「Python 是解释型语言」的准确说法是：**没有独立于运行的编译步骤**。第一次 `import expense.rules` 后你会看到 `__pycache__/rules.cpython-312.pyc`——那就是编译产物缓存，换个 Python 版本会自动失效重建（文件名里的 `cpython-312` 就是版本指纹）。

### 2.2 模块与包：文件即模块，目录即包

| 你熟悉的 Java 物 | Python 对应物 | 一句话差异 |
|---|---|---|
| 类必须进包；公共类名必须与文件名一致 | **文件名就是模块名**，想放几个函数就放几个 | Python 没有「一个文件一个公共类」约束 |
| `package com.acme.finance;` 声明 | 目录 + `__init__.py` 文件 | 包身份来自目录结构，不来自声明语句 |
| `com.acme.finance.Rules`（全限定名） | `expense.rules`（包.模块） | 命名空间分隔符从 `.` 变 `.`，但单位是模块不是类 |
| jar 打包 | （目录本身就是可分发的形态） | 无需打包即可 import |

本课 `code/` 里的包结构：

```
code/
├── expense/            # 包 = 目录
│   ├── __init__.py     # 包身份标记（几乎总是空的，见其内注释）
│   ├── rules.py        # 模块 expense.rules：预审规则
│   └── cli.py          # 模块 expense.cli：命令行入口
├── demo_name.py        # 顶层模块 demo_name：__name__ 演示
└── test_expense.py     # 顶层模块：讲义测试
```

`__init__.py` 这个名字是**固定约定**。两侧各两个下划线的名字（dunder，double-underscore）是 Python 保留给解释器的「魔法名字」体系：`__name__`、`__init__.py`、`__pycache__/` 都是这一家子——你自己起名永远不要用这种形状（单下划线 `_x`、双下划线 `__x` 前缀另有惯例，L1.2 讲）。

### 2.3 import 到底发生了什么：**执行整个模块文件**

这是本课最大的认知差。Java 的 `import` 只引入名字，类的初始化发生在**首次真正使用时**（class loading 是惰性的）；Python 的 `import` 是一条可执行语句：**把目标模块从顶到底跑一遍**，然后把产出的名字（函数、类、常量）绑定进当前命名空间。

```java
// App.java —— Java：import 只是「引入名字」，不执行任何东西
import com.acme.finance.Rules;

public class App {
    public static void main(String[] args) {
        // 到这一行才触发 Rules 类的加载与初始化
        System.out.println(Rules.preapprove(new int[]{1200, 8800}));
    }
}
```

```python
# app.py —— Python：import 语句当场「执行」整个 rules.py
from expense import rules

# 上面的 import 已经把 rules.py 从头到尾跑了一遍：
#   常量 DAILY_MEAL_LIMIT_CENTS 被赋值、函数 def preapprove 被执行（生成函数对象）
# 如果 rules.py 顶层有 print，此刻就会打印——不管你后面用不用它
print(rules.preapprove([1200, 8800]))
```

正因如此，**模块顶层的代码要克制**：放常量、函数定义、类定义；放重型副作用（连数据库、起服务）就是给所有 import 你的人埋雷。同一个模块无论被 import 多少次，**只有第一次真正执行**（之后命中 `sys.modules` 缓存）——这对应 Java 里「每个类加载器只初始化类一次」。

三种写法对照 Java 的 `import` / `import static` / 别名：

```python
import expense.rules  # 全名访问：expense.rules.preapprove(...)
import expense.rules as er  # 别名：er.preapprove(...)（≈ 单类型 import + 简名）
from expense.rules import preapprove  # 直取名字：preapprove(...)（≈ import static）
```

### 2.4 `__name__` 与入口约定：Python 版的 main 方法

每个模块都有一个自动变量 `__name__`，只有两种取值：

- **被直接运行**的文件：`__name__ == "__main__"`；
- **被 import** 的模块：`__name__` 是它的模块名（如 `"expense.rules"`、`"demo_name"`）。

于是 Python 的入口约定长这样（`code/expense/cli.py` 的真实底部）：

```python
import sys

from .rules import preapprove


def main(argv: list[str]) -> int:
    """主流程：返回进程退出码——对照 System.exit。"""
    items = parse_amounts(argv[0]) if argv else [1200, 3500, 2400]
    verdict = preapprove(items)
    print(f"预审结果：{verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":  # 被导入时这段不会执行
    sys.exit(main(sys.argv[1:]))
```

```java
// Java：入口是「签名约定」，JVM 找的就是这个方法
public class Cli {
    public static void main(String[] args) {   // args 不含程序名
        System.exit(run(args));
    }
}
```

`sys.argv` 对照：Python 的 `argv[0]` 是脚本名（或 `-m` 时的模块全名），**业务参数从 `argv[1]` 开始**——所以上面的 `sys.argv[1:]` 用切片丢掉第 0 个。`if x: A else: B` 的表达式版 `A if x else B`（见 `return` 行）同理是 Java 没有的三元形态。

跑一遍 `code/demo_name.py` 就能肉眼看到双身份（Step 3 你会亲手跑）：

```text
$ python demo_name.py            ← 直接运行
demo_name 模块正在被加载，此刻 __name__ == '__main__'
→ 我是入口（直接运行），走进了 __main__ 分支

$ python -c "import demo_name"   ← 被导入
demo_name 模块正在被加载，此刻 __name__ == 'demo_name'
→ 我是被导入的，__main__ 分支不会执行
```

两个结论都藏在输出里：**import 确实执行了模块顶层**（第一行两次都打印），而 **guard 块只认直接运行**。这个机制让同一个文件既能当库被 import、又能当程序被运行——Java 里这是两个角色两个文件，Python 一个文件身兼二职。

### 2.5 sys.path vs classpath

import 找模块的搜索路径是 `sys.path` 列表，对照：

| Java | Python | 差异 |
|---|---|---|
| classpath（启动时定死，`-cp` / 环境变量） | `sys.path`（**运行中的普通列表**，可改） | Python 的搜索路径是可编程对象 |
| 当前目录默认在 classpath 里（`java Hello`） | 脚本所在目录自动**插队到 `sys.path[0]`** | 这是很多「为什么这里能 import」的答案 |
| `CLASSPATH` 环境变量 | `PYTHONPATH` 环境变量（插在标准库之后） | 同为「追加搜索路径」的逃生门 |
| 依赖 jar 全部平铺在 classpath | 每个项目一个 `.venv/`，依赖只在 `site-packages` | uv 在 L0.1 已替你管好 |

注意 `sys.path[0]` 随**启动方式**变：直接跑脚本时是**脚本所在目录**；`python -m 包.模块` 时是**当前目录**；`python -c` 时也是当前目录。这个细节是 §5 坑位的直接成因。

### 2.6 PyPI 包名 vs Maven 坐标

| Maven | PyPI + uv | 差异 |
|---|---|---|
| GAV 三元组 `group:artifact:version` | 单一名 + 版本：`pytest>=8.3` | **没有 group 概念**，名字全网唯一（先到先得） |
| `<dependency>` + scope | `[project.dependencies]` / dev 依赖组 | 已在 L0.1 对照过 |
| 版本范围 `[1.0,2.0)` | `>=8.3,<9` 等说明符 | 语义相近，语法不同 |
| 无锁文件（靠 enforcer 钉） | `uv.lock` 锁全依赖树 | L0.1 已见 |

没有 group 的直接后果：PyPI 上的名字是稀缺资源（`pytest` 被官方占了，你就只能叫 `pytest-anyio` 这类带前缀的名字）。

### 2.7 顺手正式讲：f-string、字符串不可变、print 的 SEP/END（附推导式与切片）

前面代码反复用了几个「Java 没有对应物」的形态，这里一次讲透。

**f-string（格式化字符串字面量）**——前缀 `f` 的字符串里，`{}` 内是**任意表达式**：

```python
claim_id, verdict = "CLM-2026-0001", "PASS"
f"{claim_id} -> {verdict}"  # 表达式：变量
f"合计 {sum([1200, 3500])} 分"  # 表达式：函数调用
f"{verdict.lower():>10}"  # 冒号后是格式说明：右对齐占 10 列 → "      pass"
f"{claim_id=}"  # 调试语法：连变量名一起打印 → claim_id='CLM-2026-0001'
f"{verdict!r}"  # !r 用 repr() 显示 → "'PASS'"（带引号）
```

对照 Java：`String.format("%s -> %s", ...)` 或 `+"..." +` 拼接；f-string 是编译进字节码的高效版本，且 `{}` 内是活表达式不是占位符。**字符串不可变**：所有「修改」都返回新对象（`verdict.lower()` 不改原串），对应 Java 字符串不可变 + `String.concat` 返回新串——这个直觉你可以直接平移。

**print 的 sep / end**：`print` 是函数（不是 `System.out.println` 的方法调用），分次 print 默认换行是因为 `end="\n"`：

```python
print("A", "B", sep=" | ")  # A | B          （多参数默认用空格分隔，sep 可改）
print("loading", end="...")  # 不换行，末尾改成 "..."
print("done")  # loading...done（接在上行后面）
```

**推导式（comprehension）**——从现有序列构造新序列的一行式，Java Stream 的 `map/filter` 心智可以直接平移：

```python
[int(part) for part in "1200,3500".split(",")]  # [1200, 3500]  ≈ map(Integer::parseInt)
[c for c in items if c > 5000]  # 过滤          ≈ filter
any(c <= 0 for c in items)  # 生成器表达式：惰性逐个取，any 短路
```

**切片与解包**——`序列[起:止]` 取一段（**含头不含尾**，`argv[1:]` 是「从下标 1 到末尾」）；`a, b = 对子` 把元组拆给多个变量：

```python
sys.argv[1:]                 # 丢掉脚本名
claim_id, verdict = pair     # pair 是 ("CLM-2026-0001", "PASS") 这样的二元组
for cid, v in results:       # 循环里也能直接解包（测试文件里到处是）
```

缩进块与冒号的语法地位 L0.1 坑位已讲（缩进即语法）；`None`（Java 的 null 对应物，但它是一个真对象）在 L1.2 类型课正式登场。

## 3. 动手代码

以下命令都在本课目录 `units/unit1-core/L1.1-runtime-and-modules/` 下执行（Windows 学员把 `cp` 换成 `copy`、`rm -rf` 换成 `Remove-Item -Recurse -Force`，其余 `uv run` 完全一致）。

### Step 1 同步项目（2 分钟）

```bash
cd units/unit1-core/L1.1-runtime-and-modules
uv sync
```

### Step 2 认识本课的包（10 分钟）

打开 `code/expense/` 三件套：空的 `__init__.py`（只带注释）、`rules.py`（L0.1 的 `preapprove` 原样迁入，现在全名 `expense.rules`）、`cli.py`（命令行入口）。先跑讲义测试确认基线：

```bash
uv run pytest code/
```

`code/test_expense.py` 里的 `test_package_identity` 断言了 `rules.__name__ == "expense.rules"`——被导入时模块名带包前缀，这是 §2.4 的机器验证版。

### Step 3 肉眼看 `__name__` 双身份（5 分钟）

```bash
cd code
uv run python demo_name.py
uv run python -c "import demo_name"
cd ..
```

对照 §2.4 的输出逐行核对你的预测。

### Step 4 观察 import 的「执行」语义与模块名（5 分钟）

```bash
cd code
uv run python -c "import expense.rules; print(expense.rules.__name__)"
uv run python -c "import sys; print(sys.path)"
cd ..
```

第一条应输出 `expense.rules`（注意 `python -c` 里用 `;` 串联两条语句——这是解释器内的语法，不是 shell 的 `&&`）。第二条的 `sys.path` 第一个元素是 `''`（当前目录，因为 `-c` 模式把 cwd 插队到 `sys.path[0]`），最后一个元素是本项目的 `.venv/.../site-packages`——你项目里所有 import 的搜索边界就在这一屏里。

### Step 5 观察 `__pycache__`（5 分钟）

```bash
ls code/expense/__pycache__/
```

应看到 `rules.cpython-312.pyc` 之类（Step 4 的 import 生成）。体验「缓存」属性：

```bash
rm -rf code/expense/__pycache__
uv run python -c "import sys; sys.path.insert(0, 'code'); import expense.rules"
ls code/expense/__pycache__/
```

删了照样能跑，`.pyc` 原地重建——对照 Java：`.class` 删了程序就起不来，`.pyc` 只是缓存。`.gitignore` 里忽略它即可。

### Step 6 两种启动方式：一个能跑，一个炸（10 分钟，本课核心实验）

```bash
cd code
uv run python -m expense.cli
uv run python -m expense.cli 8800
uv run python expense/cli.py
cd ..
```

前两条：`-m` 把 `expense.cli` 当**包成员**启动，正常打印判定（第二条退出码 1——REJECT 单据）。第三条：同一个文件**直接当脚本跑**，`sys.path[0]` 变成了 `code/expense/`，文件失去包身份，顶部的 `from .rules import ...` 当场炸出：

```text
ImportError: attempted relative import with no known parent package
```

别急着修——这个坑 §5 四段拆解，练习 2 还要你亲手修一次。先记住现象。

### Step 7 PYTHONPATH 小实验（5 分钟）

从**课目录根**（不是 code/）启动 `-m`，模拟「忘了 cd」：

```bash
uv run python -m expense.cli
```

报 `ModuleNotFoundError: No module named 'expense'`——因为 `-m` 模式只把**当前目录**插进 `sys.path[0]`，而 `expense` 在 `code/` 里。用 PYTHONPATH 把它加进搜索路径：

```bash
PYTHONPATH=code uv run python -m expense.cli
```

```powershell
# Windows（PowerShell）：环境变量语法不同，分两行
$env:PYTHONPATH = "code"
uv run python -m expense.cli
```

跑通了。PYTHONPATH 是临时的搜索路径补充（对照 `CLASSPATH`）；工程上更常见的正解是「进入正确的目录」或把包做成可安装依赖（L1.3 之后的事）。

### Step 8 收尾基线（3 分钟）

```bash
uv run pytest code/
uv run ruff check .
uv run pyright
```

`code/` 应全绿（讲义部分）；`exercises/` 此刻是设计内的红——那是你的功课，见下节。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——每题只改标注的 TODO 区，其余文件与代码区不要动。卡住先想 5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_guard.py` | 补全 `__main__` guard 双模式：被 import 时提供函数、被直接运行时执行主流程。验收**双通道**：进程内 import 调函数 + subprocess 真跑一次（验证输出与退出码） |
| ex2 | `exercises/claimfix/runner.py` | 修一个真实的包导入错误：直接跑 `claimfix/runner.py` 炸出 `attempted relative import`；不许改相对导入，把入口修到「`-m` 方式可跑」。验收还会钉死「直接跑仍应炸」——防止绕过考点 |
| ex3 | `exercises/ex3_predictions.py` | `__name__` 探究：三个 probe 文件（A 直跑 / B 被 import / C 直跑但 import 了 B），预测三个场景的完整 stdout 逐行填表；测试重放命令逐行比对 |

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：直跑包内脚本坑

- **现象**：`ImportError: attempted relative import with no known parent package`——在包目录里直接 `python xxx.py`，或从项目根 `python code/expense/cli.py`，第一行相对导入就炸。
- **最小复现**（Step 6 已跑过一次）：

  ```bash
  cd code
  uv run python expense/cli.py
  ```

  ```text
  ImportError: attempted relative import with no known parent package
  ```

- **Java 直觉为何失效**：Java 的类路径与包结构天然统一——`java -cp . com.acme.Cli` 从哪个目录敲都行，「文件在哪」与「类是谁」无关。Python 里**文件的身份随启动方式变**：`-m` 启动时 `cli.py` 是包成员 `expense.cli`（`__name__` 带包前缀，`__package__` 有值，相对导入 `.rules` 有处安放）；直接跑时它是顶层脚本 `__main__`（无包上下文，`.rules` 无从解析）。同一个文件，两种身份——Java 里没有这种事。
- **修复与纪律**：**包内入口永远 `python -m 包.模块`**，并且站在能让包被找到的目录上（包的父目录，或用 PYTHONPATH 补位）。反过来，如果你拿到一个「单文件工具」想直接跑，就不要在它里面用相对导入——顶层脚本的 import 一律写绝对形式。看到这条 ImportError，第一反应不该是「改 import」，而是「改启动方式」。

## 6. 延伸

- 官方语言教程 Modules 章（模块/包/`__name__`/搜索路径的权威叙述）：https://docs.python.org/3/tutorial/modules.html
- 官方 Import System 参考（`sys.modules` 缓存、查找器/加载器机制，进阶）：https://docs.python.org/3/reference/import.html
- langchain-ai/langchain@348c9dc572#libs/core/langchain_core/__init__.py —— 一个真实库的 `__init__.py`：注意它顶层就执行了函数调用（`surface_langchain_deprecation_warnings()`）——「import 即执行」在生产库里的样子；同时它刻意保持极轻，正是 §2.3「模块顶层要克制」的示范。
- google/adk-python@7b246e01#src/google/adk/__init__.py —— 另一种生产做法：`__getattr__` + 懒加载表，把 `__init__.py` 做成「按需 import」的门面（读懂它需要 L1.4 的函数为一等公民，先混个眼熟）。
- 《Fluent Python》第 2 版第 1 章（数据模型）：dunder 名字体系的出处，`__name__` 是你遇到的第一个，后面还有一整个家族。

## 离毕业又近了一块

今晚你把 L0.1 的单文件规则升级成了**包**——毕业设计的 fail-closed 执行门就是这种形态：检查链按「一个规则一个模块」拆进包里，入口统一 `python -m` 启动，`__name__` guard 保证检查模块既能被 pytest import 又能被单独拉起排障。模块化，是 PoC 长成系统的第一块骨头。
