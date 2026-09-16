# 对照笔记：deepagents（L3.5）

> 抽象光谱第三格：harness——替你付掉的不再是循环，是「一整套工作环境」。
> 固定小节五个（`tests/test_notes_meta.py` 按结构把关）；问题是脚手架，
> 回答完删掉、留结论——`TODO(笔记)` 占位符必须全部替换。

## 它替 mini-agent 付掉了什么

对照 L3.5 结尾的对照段：mini-agent **完全没有的一整层**——虚拟文件系统
（`state["files"]`，审查底稿从「拼在消息里」变成可 `ls`/`read_file` 的文件）、
子代理（`task` 一个工具，对照 L3.1 的 handoff 是 harness 版转交）、记忆
（MemoryMiddleware：`before_agent` 下载、`wrap_model_call` 注入 `<agent_memory>`）。
注意：**agent 循环本体一点没换**——引擎就是 langgraph（L3.2+L3.4），
harness 是图引擎之上的一叠中间件。

- TODO(笔记)：三件环境件清单 + 一句「引擎没换」（这句决定它在光谱上的位置）。

## 它没替你付什么

L3.5 §5 的「缺省即全有」反直觉：你没配置文件系统，模型照样看见八个内置工具
（ls/read_file/write_file/edit_file/delete/glob/grep/task）+ 一个你没声明的
general-purpose 子代理；你没配预算，递归上限默认 **9999**。收窄（`tools=`
按 name 原位替换、`permissions`、`interrupt_on`）与覆盖预算
（`config={"recursion_limit": 25}`）都是你要亲手做的部署清单审计。

- TODO(笔记)：默认值清单 + 你要亲手做的收窄动作（对照 demo 的标准动作：
打印 `ep.requests[0]["tools"]`）。

## 最惊讶的一个机制

候选（挑一个，注明 L3.5 的位置）：「文件 = state 键」——StateBackend 的读写
全走 langgraph channel，虚拟文件系统没有任何磁盘（§延伸的 backends/state.py）；
或「默认给了你什么」的第一请求取证（Step 1）；或中间件栈的装配顺序
（Filesystem → SubAgent → Summarization → … → Memory，graph.py 的 200 行）。

- TODO(笔记)：一个机制 + 出处 + 一句「为什么惊讶」。

## 锁定性一句话

方向：harness 的锁定不在 API 而在**默认值与中间件栈**——工具越全的 harness
越要会收窄；且它站在 langgraph 之上（学过的语义全部继承，锁定是叠加的）。
你自己写一句。

- TODO(笔记)：一句话，别超一行。

## 什么时候选它

提示方向：任务真的需要「工作台」形态（多轮文件加工/底稿/子代理分工，
如毕业设计的审查底稿留痕）；已经在 langgraph 上、要快速长出环境件时。
反例：单轮工具调用的薄场景（白背 70 包依赖与默认工具面）。

- TODO(笔记)：两个选它的场景 + 一个不选它的场景，各一句理由。
