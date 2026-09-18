# Unit 1 Python 语言核心·Java 对照

> 夜校的语言主课：九个晚课讲完「写 agent 代码真正会用到的那部分 Python」。不追求大而全——GUI、科学计算、Web 全栈不碰；每一课都对着框架源码里真实出现的形态讲。

## 学法说明（先读这段）

- 你已有 Java 肌肉记忆，本学段的教学法就是**借力**：每个概念先给对照表与 Java 代码并排版，再动手。
- 讲义里任何「看起来理所当然」的 Python 语法都会展开讲——这门课不假设你自学过 Python 细节。
- 三个梯队，难度递进：**框架血管**（L1.1–L1.3：不掌握它们连框架代码都读不懂）→ **行为与错误处理**（L1.4–L1.7：Python 的行为魔法与异常哲学）→ **重中之重**（L1.8–L1.9：asyncio 独占一周，agent 框架全是 async）。

## 课表（含前置依赖——为什么是这个顺序）

| 课 | 主题 | 一句话 | 前置 |
|---|---|---|---|
| [L1.1](./L1.1-runtime-and-modules/README.md) | 运行模型与模块系统 | Python 怎么跑起来、import 到底发生了什么——classpath 与 Maven 坐标的 Python 对应物 | —（起点） |
| [L1.2](./L1.2-types-and-protocol/README.md) | 类型系统与 Protocol | 类型标注是「给人看的」；Protocol 教你什么叫结构化类型 | L1.1（包与模块就位） |
| [L1.3](./L1.3-dataclass-pydantic/README.md) | 数据建模：dataclass 与 Pydantic | record 的对应物，以及 agent 世界的「bean + validation + 序列化」三合一 | L1.2（类型标注与 Protocol） |
| [L1.4](./L1.4-functions/README.md) | 函数是一等公民 | 函数是对象、闭包、`*args/**kwargs`——装饰器的全部地基 | L1.3（数据形态已齐） |
| [L1.5](./L1.5-decorators/README.md) | 装饰器 vs 注解 | 像 @Override 却不是注解；框架里 `@tool` 的秘密 | **L1.4（闭包）** |
| [L1.6](./L1.6-iterators-generators/README.md) | 迭代器与生成器 | `yield` 惰性管线——流式输出的心智底座 | L1.4（函数与惰性求值） |
| [L1.7](./L1.7-context-exceptions/README.md) | 上下文管理器与异常处理 | 没有 checked exception 的世界：EAFP、异常链、`with` | **L1.6（生成器暂停 → with 两阶段）** |
| [L1.8](./L1.8-asyncio-1/README.md) | asyncio ①：事件循环与协程 | 与虚拟线程最像也最不像的东西；「不让出就阻塞全场」事故剖析 | L1.6 + L1.7（协程=可暂停函数；异常家族） |
| [L1.9](./L1.9-asyncio-2/README.md) | asyncio ②：并发原语与异步生成器 | gather / 超时取消 / 限流 / `async for`——并综合演练里程碑 | L1.8 |

## 里程碑（本学段结业判据）

独立完成 [milestone/](./milestone/README.md)：**async 并发 fetcher**——并发拉取多张报销单数据、带超时与重试装饰器、限流、汇总输出，`uv run pytest` 全绿。综合考点：**L1.5 装饰器 × L1.8/L1.9 asyncio**。对应结业自查：*不查资料手写 async 并发 fetcher + retry 装饰器*。

## 节奏建议（三周）

- 第 1 周：L1.1–L1.3（第一梯队，概念密度高但每个都小）；
- 第 2 周：L1.4–L1.6（行为魔法三连，装饰器是难点）；
- 第 3 周：L1.7–L1.9 + 里程碑（asyncio 是本学段最重的一块，值得占一周的大半时间）。
  L1.7 逻辑上属第二梯队（行为与错误处理），但紧贴 asyncio 排进第 3 周开路——
  异常家族树与生成器暂停都是协程的直接前置。

配套阅读：《Fluent Python》第 2 版对应章节挑读（每课延伸段给出具体章节）；夜校讲义自成体系，不依赖该书。

## 离毕业又近的一块

本学段结束你将拥有：Pydantic 建模（毕设 Plan JSON 的 schema 基础）、重试装饰器（执行层 API 调用的韧性组件）、异步生成器（流式输出的机制底座）、异常分层（fail-closed 的 REJECT 语义基础）——毕业设计的一半零件在这个学段铸出。
