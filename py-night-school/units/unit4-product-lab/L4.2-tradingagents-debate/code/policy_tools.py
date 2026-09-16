"""L4.2 政策查询 mock 工具：报销争议上诉的「数据侧」（明线素材的政策条目版）。

对版 TradingAgents 的分析师工具（yfinance/Alpha Vantage 等只读数据 API，按角色白名单挂
prebuilt ToolNode）：本课政策分析师的工具面 = 一张政策条目表，lookup_policy(article_id)
按条目号查——**只读、无写入面**，与产品「工具全部只读」的取向一致。

政策条目表是本课争议单 CLM-2026-0004（发票无效，见 data/expense/review_mock.json：
INV-2026-0005 已作废「连号重开」）的申诉依据：
- POL-7.2 常态规则：无有效发票整单驳回（初审 REJECT:INVOICE_INVALID 的出处）；
- POL-9.1 例外条款：连号重开情形凭新票 + 情况说明按 80% 报销——上诉争议的正反双方
  就围绕这两条对抗（申辩人主张适用例外，合规官主张单据链不完整）。

CALL_LOG 取证（对版 mock_tools.CALL_LOG）：测试用它证明工具被图真实执行过。
金额口径：条目里的金额全部整数分（宪法业务约定）。
"""

from __future__ import annotations

import json

POLICY_ENTRIES: dict[str, dict[str, object]] = {
    "POL-7.2": {
        "article": "POL-7.2",
        "topic": "发票有效性",
        "rule": "报销必须附有效发票；发票作废或校验未过的，整单驳回（REJECT）。",
    },
    "POL-9.1": {
        "article": "POL-9.1",
        "topic": "补开发票例外",
        "rule": "因供应商连号重开导致原票作废的，凭重开发票号与情况说明，"
        "可按原始金额的 80% 报销（APPROVE_WITH_CAP），需留档备查。",
    },
    "POL-3.4": {
        "article": "POL-3.4",
        "topic": "单笔限额",
        "rule": "单件物料采购金额上限 5000 分；展会物料采购适用本条。",
    },
}

CALL_LOG: list[str] = []  # 工具真实执行的取证（测试断言用）


def lookup_policy(article_id: str) -> dict[str, object]:
    """按条目号查政策（政策分析师的唯一工具）。

    Args:
        article_id: 政策条目号，如 "POL-7.2"。

    Returns:
        条目 dict（article/topic/rule）；查无此条返回 found=False 的提示 dict。
    """
    CALL_LOG.append(article_id)
    entry = POLICY_ENTRIES.get(article_id)
    if entry is None:
        return {"article": article_id, "found": False, "rule": "查无此条目"}
    return {"found": True, **entry}


def policy_tools_node(tool_calls: list[dict]) -> list[dict]:
    """把一轮 tool_calls 分发到注册表并回喂 ToolMessage 消息 dict（图内由 graph.py 调用）。

    对照 L3.2 demo.tools_node：查不到的工具名回喂 error JSON 而不是 raise——
    错误是给模型的修复指令，这条纪律在图引擎里原样成立。
    """
    results: list[dict] = []
    for call in tool_calls:
        name = call["name"]
        if name != "lookup_policy":
            content: str = json.dumps({"error": f"unknown_tool: {name}"}, ensure_ascii=False)
        else:
            content = json.dumps(lookup_policy(**call["args"]), ensure_ascii=False)
        results.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    return results
