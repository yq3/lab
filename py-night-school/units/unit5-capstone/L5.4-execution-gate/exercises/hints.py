"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "链体就是「查一步、拦一步」。先问 _parse_intent 的返回值：None 意味着什么？"
        "（fail-closed 的答案在讲义 gate.py 的第一查）。然后依序跑 given 的 ①②（两个 "
        "_xxx_issue 返回 None 表示放行到下一查）。定量三查共用一个套路：先判超限，再问 "
        "policy.clamp_overruns——False 立刻 PAUSE 返回；True 就把「当前生效金额」换成"
        "裁剪值**接着查**，并记住这个裁剪值（最后进 verdict 的哪个字段？）。④ 里两件事："
        "账本逐条解析发生在累计比较**之前**（任一条 None 即 DENY）；剩余额度 ≤ 0 时裁不动。"
        "⑤ 想一笔就是一笔。收口看裁剪值有没有被赋过。",
        "形状级：parsed = _parse_intent(intent)；if parsed is ???：DENY（unparseable_???）。"
        "issue = _approval_issue(policy, parsed, approval)；if issue is not ???：return issue"
        "；_blocklist_issue 同理。然后两个跟踪变量：effective = parsed 的金额分量；clamp = "
        "???。③ if effective > policy.???：not clamp_overruns → PAUSE(single_over_limit)；"
        "否则 clamp = policy.???，effective = clamp。④ 先 if ledger is ???：DENY("
        "ledger_unreadable)；for entry in ledger.payments：paid = _parse_paid(entry)，None "
        "→ DENY(???)；累计后 if paid_total + effective > policy.???：同样二分（True 时 "
        "remaining = ???，≤ 0 仍 PAUSE）。⑤ if len(ledger.payments) + 1 > policy.???："
        "PAUSE(frequency_over_limit)——clamp 变量在这里动不动？收口：if clamp is not ???："
        'ALLOW("clamped", clamp_cents=clamp) else ALLOW("allow")。',
        "完整做法：开头 parsed = _parse_intent(intent)；if parsed is None: return "
        'GateVerdict("DENY", "unparseable_intent", "payment intent unparseable")。'
        "issue = _approval_issue(policy, parsed, approval)；if issue is not None: return "
        "issue；issue = _blocklist_issue(policy, parsed)；if issue is not None: return "
        "issue。effective = parsed[3]；clamp = None。③ if effective > policy."
        "max_single_cents: if not policy.clamp_overruns: return GateVerdict("
        '"PAUSE_FOR_REAUTH", "single_over_limit", …)；clamp = policy.'
        "max_single_cents；effective = clamp。④ if ledger is None: return GateVerdict("
        '"DENY", "ledger_unreadable", …)；paid_total = 0；for entry in ledger.'
        'payments: paid = _parse_paid(entry)；if paid is None: return GateVerdict("DENY", '
        '"ledger_unreadable", …)；paid_total += paid。if paid_total + effective > '
        "policy.max_daily_total_cents: if not policy.clamp_overruns: return PAUSE("
        "daily_over_limit)；remaining = policy.max_daily_total_cents - paid_total；if "
        "remaining <= 0: return PAUSE(daily_over_limit)；clamp = remaining；effective = "
        "remaining。⑤ if len(ledger.payments) + 1 > policy.max_payments_per_day: return "
        "PAUSE(frequency_over_limit)。收口：if clamp is not None: return GateVerdict("
        '"ALLOW", "clamped", …, clamp) return GateVerdict("ALLOW", "allow", …)。',
    ],
    "ex2": [
        "execute 对着 verdict.action 写三个分支。ALLOW 分支四件事：算实付（有 clamp 用 "
        "clamp、没有用 amount_cents）→ ledger.record(一笔 dict) → 返回 paid_cents + 两条"
        "事件（gate.allowed / payment.executed）。DENY/PAUSE 共用一个形状：返回 "
        "gate_reject（action + reason_code——given 的 escalate 节点等着读它分码）+ 一条"
        "前缀是 gate.denied: 或 gate.paused: 的事件（哪个前缀配哪态？看讲义图的事件流）。"
        "route_after_execute 只判一个键在不在：付过款的那个键。",
        '形状级：if verdict.action == "???": paid = verdict.??? if verdict.??? is not '
        "None else amount_cents；ledger.???(一笔 dict——vendor/dept/amount_cents/paid_"
        'cents)；return {"paid_cents": paid, "events": ["gate.???", "payment.???"]}。'
        'else：gate_reject = {"action": verdict.???, "reason_code": verdict.???}；'
        'prefix = "gate.denied" if verdict.action == "???" else "gate.paused"；'
        'return {"gate_reject": gate_reject, "events": [f"{prefix}:{verdict.???}"]}。'
        'route_after_execute：if state.get("???") is not None: return END；return '
        '"escalate"。',
        '完整做法：execute 的 TODO 处——if verdict.action == "ALLOW": paid = verdict.'
        "clamp_cents if verdict.clamp_cents is not None else amount_cents；ledger.record("
        '{"claim_id": "CLM-MINI-0001", "vendor": VENDOR, "dept": DEPT, '
        '"amount_cents": amount_cents, "paid_cents": paid})；return {"paid_cents": '
        'paid, "events": ["gate.allowed", "payment.executed"]}。否则 gate_reject = '
        '{"action": verdict.action, "reason_code": verdict.reason_code}；stream = '
        '"gate.denied" if verdict.action == "DENY" else "gate.paused"；return '
        '{"gate_reject": gate_reject, "events": [f"{stream}:{verdict.reason_code}'
        '"]}。route_after_execute 体——if state.get("paid_cents") is not None: return '
        'END；return "escalate"。',
    ],
    "ex3": [
        "validate 是一个双循环加三个判断：外层遍历 tables.items()（拿表名与行列表），内层 "
        "enumerate(rows, start=1)（行号 1 起数）。三个判断依次是：len(row) 不等于四列长"
        "度报「缺列」；row[2] 空串报「为空」；TODO_MARK 出现在 row[2] 报「未填」。「需自"
        "建」是普通非空文本，不用特判。想想三个判断该是 if/elif 链还是三个独立 if——列都"
        "不齐的行，读 row[2] 安全吗？count_rows 是一行求和表达式。",
        "形状级：problems: list[str] = []；for section, rows in tables.???(): for lineno, "
        "row in enumerate(rows, start=???): if len(row) != len(ex3.???) 或 len(COLUMNS)："
        'problems.append(f"{section} 第 {lineno} 行缺列…")；elif not row[???]：…「Java '
        "对应物为空」；elif ex3.??? in row[2]：…「未填」。return problems。count_rows："
        "return sum(len(rows) for rows in tables.???())。",
        "完整做法：validate 体——problems: list[str] = []；for section, rows in tables."
        "items(): for lineno, row in enumerate(rows, start=1): if len(row) != "
        'len(COLUMNS): problems.append(f"{section} 第 {lineno} 行缺列：{len(row)}/'
        '{len(COLUMNS)}")；elif not row[2]: problems.append(f"{section} 第 {lineno} 行 '
        'Java 对应物为空")；elif TODO_MARK in row[2]: problems.append(f"{section} 第 '
        '{lineno} 行未填（TODO 未补全）")。return problems。count_rows 体——return sum('
        "len(rows) for rows in tables.values())。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
