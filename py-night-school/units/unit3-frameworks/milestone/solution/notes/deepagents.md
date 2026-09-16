# 对照笔记：deepagents（L3.5）

## 它替 mini-agent 付掉了什么

mini-agent 完全没有的一整层**工作环境**：虚拟文件系统（`state["files"]`，
StateBackend 的读写全走 langgraph channel——审查底稿从「拼在消息里」变成可
`ls`/`read_file` 的文件，还天然是审计证据）；子代理（`task` 一个工具，
声明式 `SubAgent` spec，handoff 的 harness 版）；记忆（MemoryMiddleware：
`before_agent` 下载进 state、`wrap_model_call` 注入 `<agent_memory>`）。
注意 agent 循环本体一点没换：引擎就是 langgraph（L3.2+L3.4），harness 是图引擎
之上的一叠中间件——所以它在光谱上的位置是「环境件」，不是「新引擎」。

## 它没替你付什么

「缺省即全有」与 Spring 自动装配直觉相反（L3.5 §5）：没配置文件系统，模型照样
看见八个内置工具（ls/read_file/write_file/edit_file/delete/glob/grep/task）+
一个没声明的 general-purpose 子代理；没配预算，递归上限默认 **9999**。
收窄全是我的活：`tools=[...]` 按 name 原位替换（read_file 必须保留）、
`permissions` allow/deny/interrupt、`config={"recursion_limit": 25}` 覆盖默认；
标准动作是打印 `ep.requests[0]["tools"]` 做部署清单审计。五轮剧本（task →
子代理工具 → 报告 → write_file → Advice 收尾）的编排也比四框架厚（71 行装配）。

## 最惊讶的一个机制

「文件 = state 键」（L3.5 §延伸 backends/state.py）：虚拟文件系统没有任何磁盘，
`_read_files`/`_send_files_update` 全是 langgraph channel 读写——所以预置文件
能跟 checkpoint 一起被暂停/恢复，文件内容与图状态同生命周期。惊讶点：
我以为的「文件系统」其实是一个字典，而这让「工作台」免费获得了 L3.3 的
暂停恢复语义。

## 锁定性一句话

锁定不在 API 在默认值与中间件栈：工具越全的 harness 越要会收窄，且它站在
langgraph 之上——锁定是叠加的（先锁 langgraph 词汇，再锁 harness 默认件）。

## 什么时候选它

选它：任务真需要工作台形态——多轮文件加工、底稿留痕、子代理分工（毕业设计的
审查底稿与事件溯源雏形）；已在 langgraph 上、想快速长出环境件时（语义零新增）。
不选它：单轮工具调用的薄场景——白背 70 包依赖、默认工具面与 9999 预算的审计成本。
