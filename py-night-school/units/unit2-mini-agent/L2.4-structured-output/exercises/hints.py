"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "顺序是关键：先看有没有围栏（正则），没有围栏再按首尾大括号截；大括号都没有才是「找不到 JSON」。",
        '围栏正则：re.search(r"```(?:json)?\\s*(.*?)\\s*```", stripped, re.DOTALL)——'
        "(?:json)? 表示可选的 json 标注；DOTALL 让 . 吃掉换行。"
        '截取：start, end = candidate.find("{"), candidate.rfind("}")；都存在且 end > start 才 loads。',
        "收尾：return json.loads(candidate[start : end + 1])，外面套 try/except json.JSONDecodeError "
        'as exc: raise ValueError(f"JSON 语法错误: {exc.msg}") from exc；找不到大括号时 '
        'raise ValueError(f"输出里找不到 JSON 对象: {text[:50]!r}")。',
    ],
    "ex2": [
        "循环体三步的顺序：① response 取 content；② messages.append(assistant)——先入史；"
        "③ extract + validate，失败才 append 修复指令。",
        "形状：for _ in range(attempts): text = await model.complete(messages)；"
        'messages.append({"role": "assistant", "content": text})；'
        "try: return Decision.model_validate(extract_json(text)), messages；"
        'except (ValueError, ValidationError) as exc: messages.append({"role": "user", '
        '"content": f"上一次输出不合法（{exc}），请只输出一个 JSON 对象。"})。',
        '循环外：raise DecisionError(f"{attempts} 次尝试仍未得到合法决策 JSON")。'
        "修复指令里点不点名字段都过验收，但点名（从 exc 提取字段）是更好的回喂——模型修得快。",
    ],
    "ex3": [
        'Literal 字段写法：verdict: Verdict = Field(description="PASS 或 REJECT:<原因>")——'
        "Verdict 别名已在文件顶部定义好；归一化先把 raw 处理成统一形状再查表。",
        '字段三行：claim_id: str = Field(pattern=r"^CLM-\\d{4}-\\d{4}$")；verdict: Verdict = '
        'Field(...)；reviewer: str = "night-school-agent"。归一化形状：cleaned = '
        'raw.strip().upper().replace(": ", ":")，合法集合 = {"PASS"} | '
        '{f"REJECT:{reason}" for reason in REJECT_REASONS}。',
        "归一化收尾：if cleaned in valid: return cleaned；raise ValueError("
        'f"未知 verdict: {raw!r}（合法值：{sorted(valid)}）")——fail-closed：宁可抛错也不猜。'
        '"REJECT: ITEM_OVER_LIMIT"（冒号后空格）用 .replace(": ", ":") 处理。',
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
