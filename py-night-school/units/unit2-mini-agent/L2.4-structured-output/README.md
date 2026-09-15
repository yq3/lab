# L2.4 结构化输出：解析、校验与回喂重试

## 1. 本课目标

agent 的产出要给**下游程序**消费（存库、触发审批流、进对账），不能是一段散文。
今晚把 L2.3 的「最终回答」升级成**带 schema 的决策对象**。完成后你能：

- 写 `extract_json` 三层剥壳（```json 围栏 → 无语言围栏 → 首尾大括号）——模型的
  「花式包裹」从此不是事故；
- 用 `typing.Literal`（新朋友，五分钟上手）把 verdict 值域写进类型，看 Pydantic 把它
  广告成 schema 的 `enum`——值域约束对模型可见；
- 写**校验错误回喂重试**循环：解析/校验失败 → 坏产出入史 + 修复指令回喂 → 再问；
  重试预算耗尽 fail-loud（半成品不许当结论）；
- 说清「客户端方案」与「端点侧 `response_format` 约束」的取舍，以及为什么夜校主线
  用前者（端点中立纪律）。

**完成判据**：本目录下三条命令同时全绿——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

发货态诚实说明：`code/` 讲义区绿，`exercises/` 是设计内的红（TODO 未填）。

## 2. 概念讲解

### 2.1 问题：LLM 是聊天界面，不是序列化层

后端互调（Java ↔ Java）的 JSON 没人会包 Markdown——但模型是个「爱聊天」的输出器：
它会贴心地加上 ```json 围栏、在 JSON 前后写「好的，这是我的决策：」、或者干脆
跟你聊两句就是不吐 JSON。而你的下游需要的是一个**确定性形状**的对象。

结构化输出的完整问题域 = 三种失败 × 一套修复：

| 失败 | 层次 | 拦截者 | 修法 |
|---|---|---|---|
| 围栏 / 散文夹带 | 文本层 | `extract_json` 剥壳 | 多数当场解决 |
| 键值不合法（值域外 / 缺字段 / 格式坏） | 校验层 | Pydantic `ValidationError`（L1.3） | 回喂重试 |
| 重试耗尽 | 预算层 | `StructuredOutputError` | fail-loud，人工介入 |

### 2.2 `Literal`：把枚举写进类型

```python
from typing import Literal

Verdict = Literal["PASS", "REJECT:INVALID_AMOUNT", "REJECT:ITEM_OVER_LIMIT", "REJECT:TOTAL_OVER_LIMIT"]

class PreapprovalDecision(BaseModel):
    claim_id: str = Field(pattern=r"^CLM-\d{4}-\d{4}$")
    verdict: Verdict
    reason: str = Field(min_length=1)
    reviewer: str = "night-school-agent"  # 有默认值 → 不进 required（L2.2 的漂移点）
```

`Literal[...]` 是类型层的**值域枚举**：pyright 拿它做静态收窄（你传 `"REJECT:NEW_RULE"`
给构造器，编辑器当场红线——不用等运行时）；Pydantic 拿它做运行时校验，还把它广告进
JSON Schema：`"verdict": {"enum": ["PASS", "REJECT:INVALID_AMOUNT", ...], ...}`——
**值域对模型可见**，幻觉率显著下降。

对照 Java：`enum Verdict { PASS, ... }` 是「真枚举类」（有 name/ordinal/可挂方法）；
`Literal` 只是「类型注解里的一组字符串」，更轻但也更浅——没有 `values()`、没有
switch 穷尽检查。夜校的约定（返回码 `REJECT:<原因>` 枚举风格）用 `Literal` 表达
刚好：**值域是文档、校验、schema 三处共享的一张表**。这也是 `REJECT:NEW_RULE`
必须抛错的原因（ex3 的 fail-closed）：值域是闭合集合，宁可失败也不猜。

一个意外之喜（今晚验收里就会遇到）：pyright 对 Literal 的静态收窄太尽职，
测试里**故意**传非法值的用例得走 `model_validate(dict)` 的 dict 路径——
字面量直传会被静态检查先拦下。静态层替你证明了值域约束的存在本身。

### 2.3 `extract_json`：三层剥壳

```python
fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
candidate = fenced.group(1) if fenced else stripped
start, end = candidate.find("{"), candidate.rfind("}")
if start == -1 or end <= start:
    raise ValueError(f"输出里找不到 JSON 对象: {text[:50]!r}")
return json.loads(candidate[start : end + 1])
```

三个正则/字符串细节值得说清（Java 里你早写过同款）：

- `(?:json)?`：非捕获组 + 可选——```json 与 ``` 两种围栏一个模式吃下；
- `re.DOTALL`：让 `.` 匹配换行——围栏里的 JSON 是多行的（没有它第一行就断）；
- `find("{")` / `rfind("}")`：首尾大括号兜底——散文夹带（「决策如下：{...} 请查收」）
  也认。这是「宽进」的边界：**只认第一个 `{` 到最后一个 `}`**，JSON 里嵌套大括号
  不会截断（截错的概率只在「散文里还有别的大括号」时出现——遇到就把 prompt 写严一点）。

两种失败要分开报（都是 `ValueError` 但文案不同）：「找不到 JSON 对象」（文本层）
与「JSON 语法错误: ... (第 N 行第 M 列)」（`json.JSONDecodeError` 转译）——
回喂时模型才知道该补对象还是改语法。

### 2.4 回喂重试循环：错误是给模型的修复指令

```python
for _attempt in range(1, attempts + 1):
    response = await client.complete(messages, tools=[])
    text = response["choices"][0]["message"]["content"] or ""
    messages.append({"role": "assistant", "content": text})   # ① 模型产出永远先入史
    try:
        return PreapprovalDecision.model_validate(extract_json(text)), messages
    except (ValueError, ValidationError) as exc:
        messages.append(feedback_message(exc))                # ② 修复指令回喂
raise StructuredOutputError(f"{attempts} 次尝试仍未得到合法决策 JSON ...")  # ③ fail-loud
```

三个纪律，每个都有出处：

1. **先入史再校验**（L2.3 的纪律平移）：成功路径的 assistant 消息也要进历史——
   审计轨迹不能缺最后一环；坏产出更是要「留案底」；
2. **一个 except 接两种伤**：`ValueError`（文本层）与 `ValidationError`（校验层）
   都走同一条回喂路——对模型来说都是「你上次交的不行，原因是 X」；
   `feedback_message` 把 `exc.errors()` 的四要素（L1.3 讲的位置/类型/原因/输入）
   翻译成点名字段的修复指令：`verdict: Input should be 'PASS', 'REJECT:...'`；
3. **重试也有预算**：`attempts` 就是这一层的 `max_turns`——恰好 N 次后抛有名异常。
   无限重试与无限循环是同一颗雷（L2.3 §5），只是换了个楼层。

对照 Java：这套「校验失败 → 错误信息展示 → 重新提交」的形状，最接近的是表单回填
（Bean Validation 的 errors 回传给用户改了再交）——只是「用户」换成了模型，
而且它真的会照着错误信息改。

### 2.5 端点侧约束 vs 客户端方案

很多端点支持 `response_format: {"type": "json_schema", ...}`——把 schema 交给端点，
由端点约束解码器，理论上从根上消灭格式错误（OpenAI 文档称之为 Structured Outputs）。
取舍表：

| | 端点侧 `response_format` | 客户端方案（本课） |
|---|---|---|
| 格式保证 | 端点保证（强） | 自己剥壳（宽进） |
| 支持范围 | 各家不一（字段/版本差异大） | 任何能输出文本的端点 |
| 值域校验 | schema 子集 | Pydantic 全量约束 |
| 修复回路 | 无（错了就是错了） | 回喂重试 |

夜校主线用客户端方案——**端点中立纪律**（GLM/DeepSeek/Qwen/本地 vLLM 都能跑同
一份代码）；工程实践是两层叠加：端点支持就带上 `response_format`，客户端的解析
校验回喂照留（兜底 + 审计）。openai-agents 的 `output_type` 就是这两层的框架化
（延伸路标）。

## 3. 动手代码

先 `uv sync`。L2.1 三件套与 L2.3 的 `model.py`（ScriptedModel / HttpModelClient）
原样在 `code/`——离线剧本继续当测试替身。

### Step 1：`extract_json` 五连测（10 分钟）

```bash
uv run python code/demo_extract.py
```

```text
[干净的 JSON] -> claim_id=CLM-2026-0001  verdict=PASS
[```json 围栏] -> claim_id=CLM-2026-0002  verdict=REJECT:ITEM_OVER_LIMIT
[无语言围栏] -> claim_id=CLM-2026-0003  verdict=REJECT:INVALID_AMOUNT
[散文夹带] -> claim_id=CLM-2026-0001  verdict=PASS
[根本没有 JSON] -> ValueError: 输出里找不到 JSON 对象: '我认为这张单据符合规定，可以直接通过。'
```

五种形态一张表看全。把 `demo_extract.py` 里的样本改坏几个再跑——观察报错文案怎么
区分「找不到」与「语法错」。

### Step 2：回喂重试全程（15 分钟）

```bash
uv run python code/demo_repair.py
```

```text
== 第 1 次输出：围栏 + 值域越界 + 缺 reason ==
== 第 2 次输出：散文夹带但字段齐全 ==

拿到决策对象: {"claim_id":"CLM-2026-0002","verdict":"REJECT:ITEM_OVER_LIMIT","reason":"单笔 8800 分超过 5000 分上限","reviewer":"night-school-agent"}
== 修复后的消息轨迹（5 条） ==
     system: 你是财务预审决策器。只输出一个 JSON 对象，不要围栏、不要解释：\n{"claim_id": "CLM-YYYY-NNNN",…
       user: 报销单 CLM-2026-0002（明细单笔 8800 分）的预审决策是什么？
  assistant: ```json\n{"claim_id": "CLM-2026-0002", "verdict": "REJECT:OVER_LI…
       user: 上一次输出不是合法的决策 JSON（verdict: Input should be 'PASS', 'REJECT:INVAL…
  assistant: 抱歉，修正后的决策如下：{"claim_id": "CLM-2026-0002", "verdict": "REJECT:ITE…
```

看第 4 条消息：修复指令把 ValidationError 的值域原文（`Input should be 'PASS',
'REJECT:INVALID_AMOUNT', ...`）带回给了模型——第 2 次输出不仅改对了 verdict，
还学会了散文夹带照样被第 3 层剥壳救回。一次演示，三种机制全部到场。

### Step 3：讲义区验收（10 分钟）

```bash
uv run pytest code/
```

六个测试覆盖：三层剥壳全过 + 两种失败各自报错、Literal 值域（enum 广告 / required
漂移 / 越界拒收）、修复指令的翻译质量、修复循环的历史形状、预算耗尽的确定性。

### Step 4：（可选）真实端点

```bash
uv run python code/demo_repair.py --real
```

错误形态由模型自由发挥——可能一次就过，也可能给你表演新的花式包裹；
`attempts=3` 的预算兜底。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改标注的 TODO 区。卡住先想 5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_extract.py` | 三层剥壳 + 两种失败的报错文案 |
| ex2 | `exercises/ex2_repair.py` | 修复循环：先入史再校验、回喂、预算耗尽 |
| ex3 | `exercises/ex3_verdict_model.py` | Literal 值域 + Field 约束 + 归一化 fail-closed |

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：Markdown 围栏坑（LLM 不是序列化层）

这是本课的命名化失败模式——「模型输出可以直接 `json.loads`」这个假设，第一次连
真实端点就碎。

- **现象**：`json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)`——
  你 `json.loads(text)`，而 `text` 的第一个字符是反引号。
- **最小复现**：

  ```python
  text = '```json\n{"claim_id": "CLM-2026-0002", "verdict": "REJECT:ITEM_OVER_LIMIT"}\n```'
  json.loads(text)  # JSONDecodeError: Expecting value: line 1 column 1 (char 0)
  ```

- **Java 直觉为何失效**：二十年的后端经验告诉你「接口返回 JSON 就是 JSON」——
  因为对端是序列化层，`writeValueAsString` 不会在前后加聊天文案。LLM 端点的输出
  本质是**聊天消息**：模型「好心」用 Markdown 代码块把 JSON 装起来，因为它被训练
  成对人类友好，不是对你的解析器友好。「输出即契约」的直觉在这里要改成
  **「输出是聊天，契约靠你自己剥 + 校验」**。
- **修复与纪律**：三层剥壳（`extract_json`）+ prompt 明令「只输出 JSON，不要围栏」+
  （端点支持时）`response_format` 三层设防。只做 prompt 不做剥壳是脆弱的——prompt
  是概率约束，剥壳是确定约束；本课的验收逼你把确定层写对。

## 6. 延伸

- OpenAI Structured Outputs 指南（端点侧约束的权威说明与支持范围）：
  https://platform.openai.com/docs/guides/structured-outputs
- Pydantic JSON Schema 文档（Literal → enum 映射、Field 约束 → schema 键全表）：
  https://docs.pydantic.dev/latest/concepts/json_schema/
- openai-python@f348ec87b#src/openai/types/shared/response_format_json_schema.py ——
  端点侧约束在官方 SDK 里的类型定义：`json_schema` / `strict` 字段的静态化，
  与我们客户端方案并排读，取舍表（§2.5）的实物版。
- openai/openai-agents-python@fb8fa1ba5#src/agents/agent.py —— 生产框架的 `output_type`：
  Agent 构造参数里的输出类型声明，框架替你做了本课全部三件事（schema 下发 / 解析 /
  校验重试）——读它之前先手写过一遍，才知道它替你付掉了什么（Unit 3 对照问题之一）。
- typing.Literal 官方文档与 PEP 586：
  https://docs.python.org/3/library/typing.html#typing.Literal

## 离毕业又近的一块

毕业设计的 Plan JSON（L5.1「Pydantic 强约束 + 工具白名单」）就是今晚这套
「Literal 值域 + Field 约束 + 解析校验」的放大版；L5.4 的 fail-closed 执行门把
`normalize_verdict` 的「收窄容错、未知即拒」做成整条检查链的哲学。mini-agent 的
第四块肌肉（输出质量闸）今晚完工——只剩最后一课：让工具走出进程（MCP）。
