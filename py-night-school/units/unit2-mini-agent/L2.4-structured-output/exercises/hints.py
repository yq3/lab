"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "三层顺序不能颠倒：先问有没有围栏，没有围栏再按首尾大括号截取，大括号都没有才是「找不到」；"
        "语法错是另一类失败，要接住转译成 ValueError（信息带行列号）。",
        "形状级：怎么用一个正则同时匹配带/不带 json 标注两种围栏（可选组），又让点号吃得动换行"
        "（哪个 flag）？大括号截取用哪一对查找方法？JSONDecodeError 的哪个属性能拼出人话报错？",
        "收尾：return json.loads(candidate[start : end + 1])，外面套 try/except json.JSONDecodeError "
        'as exc: raise ValueError(f"JSON 语法错误: {exc.msg} (第 {exc.lineno} 行第 {exc.colno} 列)") '
        'from exc；找不到大括号时 raise ValueError(f"输出里找不到 JSON 对象: {text[:50]!r}")。',
    ],
    "ex2": [
        "循环体三步的顺序是考点：模型产出先入史（好坏都入）、再解析校验、失败才追加修复指令；"
        "重试耗尽的 raise 写在循环外。",
        "形状级：两种伤（ValueError / ValidationError）怎么用一个 except 接住（异常元组）？"
        "修复指令这条消息的 role 是什么、内容要点名什么？决策校验用模型的哪个类方法？",
        '循环外：raise DecisionError(f"{attempts} 次尝试仍未得到合法决策 JSON")。'
        "修复指令里点不点名字段都过验收，但点名（从 exc 提取字段）是更好的回喂——模型修得快。",
    ],
    "ex3": [
        "claim_id 与 reason 各缺一种约束——一个是格式（pattern）、一个是长度（min_length），"
        "回讲义 §2.2 的约束映射表选 Field 参数；归一化只做「收窄方向的容错」。",
        "形状级：归一化的三步处理是什么（去空白、大小写、冒号后空格）？合法值集合怎么用 REJECT_REASONS "
        "和 PASS 拼出来？查不到时抛什么（fail-closed：宁可抛错也不猜）？",
        '归一化收尾：cleaned = raw.strip().upper().replace(": ", ":")；valid = {"PASS"} | '
        '{f"REJECT:{reason}" for reason in REJECT_REASONS}；if cleaned in valid: return cleaned；'
        'raise ValueError(f"未知 verdict: {raw!r}（合法值：{sorted(valid)}）")。',
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
