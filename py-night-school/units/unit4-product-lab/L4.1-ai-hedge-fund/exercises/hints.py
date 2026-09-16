"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/提问式，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "三个语义点分开想：谁进分子分母（怎么认出弃权票）？分母累加的是什么——score 还是权重？"
        "分母是零的时候（全弃权或权重全零），返回什么才能让下游「显式转人审」而不是拿到一个假 0.0？",
        "形状级：一个累加循环 + 两个累加器（分子、分母各一个）；循环体先做什么判断再决定累加还是"
        "记进 abstained 列表？最后 conviction 的条件表达式长什么样——除法什么时候才安全？",
        "完整做法：for vote in votes: 若 metadata.get('abstained') is True 则 abstained.append"
        "(vote.checker) 并 continue；否则 w = weights[vote.checker]，分子 += w * vote.score，"
        "分母 += w，voters.append(vote.checker)。conviction = 分子 / 分母 if 分母 > 0 else None，"
        "返回 BlendOutcome(conviction=conviction, voters=voters, abstained=abstained)。",
    ],
    "ex2": [
        "对版产品 llm/cache.py 想三件事：key 是「四字段拼一个字符串再哈希截断」；get 的两种 miss"
        "（文件不在/文件坏了）都要安静返回 None；put 是「建目录、补 created_at、写文件」三步。",
        "形状级：key 用 f-string 拼四段（中间放一个分隔符）再交给标准库哪个哈希模块、取结果的"
        "前多少位？get 拿 path 读文本 json.loads，except 里返回什么？put 里建目录要给哪两个参数"
        "才能「已存在也不炸」？created_at 那一步用什么调用取「现在的 UTC 时刻」、再以什么字符串"
        "格式进 JSON？",
        "完整做法：payload = f'{checker}|{model}|{system}|{user}'，return hashlib.sha256"
        "(payload.encode()).hexdigest()[:24]。get：path 不存在 return None；try json.loads"
        "(path.read_text(encoding='utf-8'))，except (json.JSONDecodeError, OSError) return None。"
        "put：self._dir.mkdir(parents=True, exist_ok=True)；record = {**record, 'created_at': "
        "datetime.now(UTC).isoformat()}；(self._dir / f'{key}.json').write_text(json.dumps"
        "(record, indent=2, ensure_ascii=False), encoding='utf-8')。顶部 import：hashlib、json、"
        "from datetime import UTC, datetime。",
    ],
    "ex3": [
        "两段式：第一段逐明细比单笔上限（遍历顺序想想怎么才确定——事件顺序要可重放）；第二段对"
        "封顶后的总和比总额上限。等比缩的「只缩不放」在整数世界里靠什么取整保证总和不超上限？",
        "形状级：第一段遍历明细（顺序选什么才可重放——依赖字典插入序稳不稳？），超过上限的记一条"
        " ClampEvent 并放入封顶值；第二段 total 求和后超上限时 scale 是什么比值？每个新值套 int()"
        "——对正数它是什么取整方向？批次级事件的一条 before/after 各记什么（验收要拿它对账）？",
        "完整做法：第一段 for item in sorted(claims_amounts): amount = claims_amounts[item]；若"
        "amount > max_single_cents：clamps.append(ClampEvent(limit='max_single_cents', item=item, "
        "before=amount, after=max_single_cents))，clamped[item] = max_single_cents；否则原值放入。"
        "第二段 total = sum(clamped.values())；若 total > max_dept_total_cents：scale = "
        "max_dept_total_cents / total，clamped = {i: int(a * scale) for i, a in clamped.items()}，"
        "clamps.append(ClampEvent(limit='max_dept_total_cents', item=None, before=total, "
        "after=sum(clamped.values())))。返回 LimitsResult(amounts=clamped, clamps=clamps)。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
