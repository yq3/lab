"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "三查各问一遍：第 4 查先「每条都读得懂吗」再「合计超不超」；第 5 查数的是谁的条数、"
        "本笔算不算进去；第 6 查拿注入的 now 与合同的哪个时刻比、到期那一刻算不算过期。",
        "形状级：遍历 paid 时对每条调 _parse_paid_amount，返回 None 时这一查的 kind/limit 与"
        "「合计超限」时相同还是不同？detail 里写什么才能让人一眼看出是 fail-closed？"
        "累计值和次数分别从哪个变量长出来（一个是求和、一个是计数）？"
        "第 6 查的比较符选 >= 还是 >——「恰好等于过期时刻」的那笔你敢放吗？"
        "expires_at 类型是 datetime | None，先断言非 None 再比。",
        "完整做法：paid_total 从 0 起累加 _parse_paid_amount 的返回值，遇 None 返回 "
        "Breach(quantitative, 'max_daily_total_cents', 0, \"today's paid list could not be read "
        '(fail-closed)")；随后 if paid_total + intent.amount_cents > caps.max_daily_total_cents '
        "返回 Breach(quantitative, 'max_daily_total_cents', paid_total + intent.amount_cents)；"
        "第 5 查 attempted_count = len(today.paid) + 1，超过 caps.max_payments_per_day 返回 "
        "Breach(quantitative, 'max_payments_per_day', intent.amount_cents, ...)；第 6 查先 "
        "assert mandate.consent.expires_at is not None，today.now >= expires_at 时返回 "
        "Breach(structural, 'mandate_expiry', intent.amount_cents, ...)。",
    ],
    "ex2": [
        "compute_record_hash 想清楚「这条记录要向谁负责」：自己的位置、前一条的哈希、自己的载荷——"
        "三样缺一个，篡改者就有空子。verify_chain 想清楚「每行要数哪三件事」。append 想清楚"
        "「写之前凭什么敢写」。",
        "形状级：compute_record_hash 把 {seq, prev_record_hash, payload} 装进一个 dict，交给谁"
        "序列化（给定的 canonical_json）、再对什么做 sha256（hashlib）、返回值的前缀跟谁对齐？"
        "verify_chain 从 expected_prev = GENESIS_PREV_HASH 起步，对每行：解析（失败算什么断点？）"
        "→ seq 等不等于第几条 → prev_record_hash 等不等于 expected_prev → record_hash 重算等不等；"
        "哪一步走通了 expected_prev 更新成什么？append 在写之前先调谁？下一条的 seq/prev 从哪来"
        "（空链时各是什么）？记录除了 payload 还带哪三个键？",
        "完整做法：compute_record_hash 返回 'sha256:' + hashlib.sha256(canonical_json({...})."
        "encode('utf-8')).hexdigest()；verify_chain 逐行走三查（seq 连续、prev 衔接、哈希重算——"
        "重算时的 payload 要把三个保留键从记录里剔掉），首处不一致包进 ChainBreak 返回 "
        "ChainVerificationResult(False, 数到的条数, 断点)，行行走完返回 ok=True；append 先 "
        "verify_chain，不 ok 就 raise LedgerCorruptionError，然后算 next_seq / next_prev（空链"
        "从 1 / GENESIS_PREV_HASH 起），组装三键记录，open('a') 写一行 JSON 返回记录。",
    ],
    "ex3": [
        "把「两条命」翻译成控制流：哪些情况是「礼貌返回 REFUSED」，哪种情况是「异常上抛、标记留盘」；"
        "reconcile 只做取证与决断，没有第三种动作。",
        "形状级：pay_with_safety 的顺序骨架是「查窗口 → 门裁决 → 生成 ref_id → 落盘标记 → "
        "（可选）抛 SimulatedCrash → broker.pay → 收尾」；每一步失败/不符时各自的出口是什么"
        "（REFUSED 带什么字段？OSError 时 broker 被碰了吗）？ref_id 的形状文件头部有约定。"
        "reconcile 的两分支拿 get_payment_by_ref 的返回值区分：非 None 时标记文件怎么处理、"
        "None 时怎么处理？两个方法里谁负责把窗口关上？",
        "完整做法：pay_with_safety——if self.has_pending(): return PayOutcome('REFUSED', "
        "'pending window open — reconcile first')；verdict = gate.decide(intent)，非 ALLOW "
        "返回 REFUSED 并附 verdict；ref_id = f'pay-{uuid.uuid4().hex}'；try: "
        "self._write_marker_atomic(...) except OSError: 返回 REFUSED（detail 写明 zero broker "
        "calls）；crash_after_marker 时 raise SimulatedCrash；receipt = broker.pay(intent, ref_id)"
        "（异常直接上抛、不清标记）；self._clear_marker() 后返回 PAID。reconcile_pending——"
        "无标记返回 NO_PENDING；_read_marker() 为 None 返回 NEEDS_MANUAL_REVIEW；evidence = "
        "broker.get_payment_by_ref(ref_id)，非 None 则 _clear_marker() 并返回 "
        "RESOLVED_BY_EVIDENCE（附 evidence），None 返回 NEEDS_MANUAL_REVIEW。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
