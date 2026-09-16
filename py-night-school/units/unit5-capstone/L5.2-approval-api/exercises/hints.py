"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "reply 的骨架三步：取单（取不到抛什么——对照 UnknownTicket 的 docstring）→ 记 "
        "approval.replied 事件 → 恢复执行。三分支的差异集中在两处：事件的附加字段"
        "（once/always 带 rule_id、reject 带 message）与恢复载荷里放什么。恢复入口回 L3.3 "
        "翻——「新 invoke + 什么构造器」；载荷里放哪些键，看迷你图 submit 里 decision.get "
        "的两行。always 的规则命中查询在记事件之前做（match 命中拿现成 rule_id，未命中才 "
        "grant）。",
        "形状级：reject 分支——feedback 缺省从哪个常量来？事件的 data 是哪三个键？恢复指令"
        "「构造器(resume=什么形状的 dict)」——action 与 message 两个键的值各是什么？"
        "once/always 分支——approve 动作的载荷比 reject 少哪个键？always 先 self.rules.match"
        "(哪两个字段)、None 时 self.rules.grant(同两字段) 拿 rule_id；最后都把恢复指令交给 "
        "self._drive。返回回执三个键。",
        "完整做法：顶部补 from langgraph.types import Command。reply 体：ticket = "
        "self.pending.pop(ticket_id, None)；if ticket is None: raise UnknownTicket"
        "(ticket_id)。reject：feedback = message or DEFAULT_FEEDBACK（本文件常量）；"
        "self._emit('approval.replied', {'ticket_id': ticket_id, 'decision': 'reject', "
        "'message': feedback})；await self._drive(Command(resume={'action': 'reject', "
        "'message': feedback}))；return {..., 'rule_id': None}。once/always：rule_id = None；"
        "if decision == 'always': rule_id = self.rules.match(ticket['dept'], "
        "ticket['total_cents'])，为 None 则 rule_id = self.rules.grant(ticket['dept'], "
        "ticket['total_cents'])；self._emit('approval.replied', {'ticket_id': ticket_id, "
        "'decision': decision, 'rule_id': rule_id})；await self._drive(Command"
        "(resume={'action': 'approve'}))；return {'ticket_id': ticket_id, 'decision': "
        "decision, 'rule_id': rule_id}。",
    ],
    "ex2": [
        "两半各想一件事。广播半边：订阅者挂在各自的 asyncio.Queue 上等——append 时对每个"
        "队列做「非阻塞投递」（Queue 的哪个方法不 await？）。订阅半边：先 snapshot(last_id) "
        "拿到该重放的列表，把「自己的队列」登记进 _subscribers，然后 yield 重放、再 await "
        "队列拿新事件。关键在顺序：登记必须发生在第一次 await 之前——为什么？断开用 finally。",
        "形状级：append 的 TODO 一行——for queue in self._subscribers: queue.???(record)"
        "（哪个入队方法不阻塞？）。subscribe 的形状——replay = self.snapshot(?)；queue = "
        "asyncio.Queue()；self._subscribers.???(queue)；try: 先 for 循环 yield replay，再 "
        "while True: record = await queue.???(); yield record；finally: self._subscribers"
        ".???(queue)。last_id 参数传给 snapshot 的哪个形参？",
        "完整做法：append 的 TODO 处——for queue in self._subscribers: queue.put_nowait"
        "(record)。subscribe 整段——queue: asyncio.Queue[dict] = asyncio.Queue()；replay = "
        "self.snapshot(last_id)；self._subscribers.append(queue)；try: for record in "
        "replay: yield record；然后 while True: record = await queue.get()；yield record；"
        "finally: self._subscribers.remove(queue)。（replay 与 append 之间不能有 await："
        "事件表先记、队列后到——登记前发生的事件走重放，登记后走广播，两边不重不漏。）",
    ],
    "ex3": [
        "三个 TODO 各对一个验收维度。grant：编号（len+1 格式化成 rule-00N）、时间戳"
        "（datetime 的 now + isoformat——标准库哪个模块？）、四元组（形参全录）——ApprovalRule "
        "的六个字段每个都有来处。match：两维条件 dept 相符、total_cents 不超 cap，遍历 "
        "self._rules 第一个命中就返回它，走完没中返回 None。admit：拿 ticket 的两个匹配"
        "维度去 match，命中 emit + True，未命中 False。",
        "形状级：grant——ApprovalRule(rule_id=f'rule-{??? :03d}', dept=..., max_total_cents=…"
        "哪个形参？, approved_by=…, approved_at=<datetime 的 ISO 字符串>, content_hash=…)，"
        "然后 self._rules.???。match——for rule in self._rules: if rule.??? == dept and "
        "total_cents ??? rule.??? : return rule；循环后 return ???。admit——hit = rules."
        "match(ticket[哪个键], ticket[哪个键])；if hit is not None: emit(事件名, {ticket_id: "
        "ticket[...], rule_id: hit.???}) 且 return True；else return False。",
        "完整做法：grant 顶部补 from datetime import UTC, datetime。grant 体——rule = "
        "ApprovalRule(rule_id=f'rule-{len(self._rules) + 1:03d}', dept=dept, "
        "max_total_cents=cap_cents, approved_by=approved_by, approved_at=datetime.now(UTC)"
        ".isoformat(timespec='seconds'), content_hash=content_hash)；self._rules.append"
        "(rule)；return rule。match 体——for rule in self._rules: if rule.dept == dept and "
        "total_cents <= rule.max_total_cents: return rule；return None。admit 体——hit = "
        "rules.match(ticket['dept'], ticket['total_cents'])；if hit is None: return False；"
        "emit('approval.auto_applied', {'ticket_id': ticket['ticket_id'], 'rule_id': "
        "hit.rule_id})；return True。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
