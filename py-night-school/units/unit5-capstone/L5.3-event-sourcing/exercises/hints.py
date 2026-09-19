"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "append 里先想「门的顺序」：词汇表校验（ValueError，消息里记得带上 EVENT_TYPES 这个"
        "名字——验收断言会认它）应该发生在开门之前还是事务之内？"
        "进了 `with self._conn:` 之后按序做四件事——取时钟、payload 变 JSON 文本（哪一步天然会炸）、"
        "seq 分配（seq 是 None 才算：对该聚合取最大值加一，注意 WHERE 里要不要管别的聚合）、"
        "INSERT（什么情况下会撞 PRIMARY KEY，撞了抛的原始异常是谁，怎么把它翻译成语义化异常且保留因果链）。"
        "events_for 想清楚：两个过滤值都必须走 ? 占位——讲义 Step1 的注入对照就是给你的。",
        "形状级：seq 分配的 SELECT 想两层——「该聚合当前最大 seq」用哪个聚合函数取？"
        "空表（该聚合还没有事件）时最大值是什么、怎么落到 0（SQL 里有没有能把 NULL 换成"
        "默认值的辅助函数？或者 fetchone 回来的行怎么判）？INSERT 的占位符有几个、VALUES "
        "对应哪五个字段？except 住哪个 sqlite3 异常、raise … from … 的两个位置各放什么？"
        "events_for 的两个分支只是 WHERE 子句差一个条件，返回的列表推导里 payload 那一列"
        "需要哪个 json 函数还原？",
        "完整做法：顶部补 import json。append：校验后 `with self._conn:`，先 created_at = "
        "self._clock()、text = json.dumps(payload, ensure_ascii=False)；seq 为 None 时执行 "
        '"SELECT COALESCE(MAX(seq), -1) + 1 FROM events WHERE aggregate_id = ?" 取回 int；'
        "INSERT 五列五占位符；包住 execute 的 try 里 `except sqlite3.IntegrityError as exc: "
        "raise EventSeqConflict(aggregate_id, seq) from exc`。events_for：两分支 SQL（差别只在 "
        "AND type = ?），参数元组相应多一个值，ORDER BY seq；返回的列表里每行组装 "
        "seq/type/payload/created_at 四键，payload 那一列用 json.loads 还原成 dict。",
    ],
    "ex2": [
        "三块各自想一件事：canonical_prompt——每条消息取「归一后的角色 + 全文内容」拼一行，"
        "行间用确定的分隔符；角色归一查 given 的映射，查不到时用原词。prompt_hash——模型名与"
        "规范文本拼一个串再 sha256（编码成什么再哈希）。cached_complete——先算键再查表："
        "命中直接返回（response 从行的哪个键取？boolean 标记是什么？）；未命中先真调用，"
        "再把四个字段 put 回去（规范文本 vs response 文本别放反）。",
        "形状级：canonical 的一行长什么样「角色|内容」？多条消息怎么连成一个串？prompt_hash 的"
        "输入串把 model 放在最前还是最后都行，但拼接符要确定；hashlib 的函数名吃 bytes——"
        "字符串怎么 encode？cached_complete 的两个出口都是二元组 (str, bool)：命中出口不出现"
        "任何 await，未命中出口 await 哪个方法的哪个入参？put 的四个实参按序是什么？"
        "audit_query 拿 given 的点查方法，从行里搬三个键。",
        "完整做法：顶部补 import hashlib。canonical_prompt：对每条消息 role = "
        "_ROLE_ALIASES.get(_role_of(m), _role_of(m))，收集 f'{role}|{_content_of(m)}' 后 "
        '"\\n".join。prompt_hash：payload = f"{model}\\n{canonical_prompt(messages)}"，'
        "return hashlib.sha256(payload.encode('utf-8')).hexdigest()。cached_complete：digest = "
        "prompt_hash(model_name, messages)；hit = cache.get(digest)，非 None 时 return "
        "(hit['response'], True)；否则 response = await model.ainvoke(messages)，cache.put("
        "digest, model_name, canonical_prompt(messages), str(response.content))，return "
        "(str(response.content), False)。audit_query：row = cache.get(digest)，None 时返回 "
        "None，否则 {'model': row['model'], 'prompt': row['prompt'], 'response': row['response']}。",
    ],
    "ex3": [
        "run_key 只有一件事：把两个串拼成一个确定形态——分隔符自定，但同输入必须同输出；"
        "签名取前多长是可读性取舍（讲义取 12 位十六进制）。assert_compatible 是一个比较 + "
        "一个条件抛出：构造异常时把两个签名都存进去（stored/current 属性验收要读）。",
        "形状级：run_key 的返回串以什么开头、签名用哪个切片表达式（前 N 个字符）？"
        "assert_compatible 的 if 条件比较哪两个参数；不等时 raise 的异常类构造参数顺序——"
        "stored 在前还是 current 在前（对齐异常类的 __init__ 声明）；相等时这个函数的"
        "「放行」形态是什么（有 return 吗）？",
        "完整做法：run_key：return f'{aggregate_id}@{signature[:12]}'。assert_compatible："
        "if stored_sig != current_sig: raise GraphVersionMismatch(stored_sig, current_sig)"
        "——相等时什么都不做（静默放行，函数自然返回 None）。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
