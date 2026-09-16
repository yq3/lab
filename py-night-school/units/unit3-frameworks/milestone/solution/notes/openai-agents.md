# 对照笔记：openai-agents（L3.1）

## 它替 mini-agent 付掉了什么

- `Runner.run` ≈ `agent.py::run` 的十行循环：软终止（模型收敛）+ `max_turns`
  硬预算（`MaxTurnsExceeded` ≈ `AgentBudgetExceeded`），一行没多；
- `@function_tool` ≈ `tools.py` 的「Pydantic → JSON Schema → 注册表」三步：
  装饰时从签名 + docstring 生成 schema（docstring-as-schema），零适配代码直包
  mock_tools；
- `output_type=Advice` ≈ `structured.py::ask_structured`：response_format 每轮注入 +
  客户端 Pydantic 校验，且实测（0.22.2）**不多花一轮模型**。

## 它没替你付什么

模型端点还得自己注入（`OpenAIChatCompletionsModel` + `AsyncOpenAI(base_url=...)`，
传字符串会走默认 Responses API）；工具返回值边界仍是我的纪律——dict 被 `str()` 成
Python repr 而非 JSON（§2.3 实测，L2.2「边界收敛」纪律要自己守）；trace 目的地
要自己管（§2.7）；handoff 拼错工具名直接 `ModelBehaviorError`（打错名字的风险
外包给了模型）。装配 29 行、lock 51 包——四框架最薄，但薄的部分仍是我的责任。

## 最惊讶的一个机制

tracing 默认外发（L3.1 §2.7 / Step 2）：端点硬编码 api.openai.com/v1/traces/ingest，
只要环境里有 OPENAI_API_KEY，即使模型端点是 GLM/本地 vLLM，会话内容也发往
OpenAI；没配 key 时只告警——离线验收「看着没事」，生产静默外发。惊讶点：
一个「极简、无魔法」的框架把可观测默认值做成了外发。肌肉记忆：
`set_tracing_disabled(True)` 或 `set_trace_processors(...)`。

## 锁定性一句话

原语层几乎无锁定（薄包装 + 普通对象），但默认值有牙齿：trace 外发与 Responses
API 路径是它的私有默认，不管住它，「极简」就是错觉。

## 什么时候选它

选它：已用 OpenAI 兼容端点、只要「循环 + 工具 + 结构化输出」的最薄装配
（29 行/51 包）；要保住循环语义控制权的场景。不选它：需要显式图、
checkpoint/暂停恢复、动态扇出时——它没有这些机制（L3.2–L3.4 的领域）。
