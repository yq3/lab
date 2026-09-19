# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""ex1 工具注册改造：给审查 agent 加第三个工具 lookup_policy——查报销政策文案。

考察点（Step 2 的逆命题）：Step 2 我们看到 declaration 从函数身上长出来；
这次反过来——你写函数，让框架长出「好 schema」。三个信息源都要你亲手提供：
  名字 ← 函数名（已给定：lookup_policy）；
  描述 ← 你写的 docstring（模型靠它决定何时调用——它就是工具的广告词）；
  参数 ← 你写的签名（类型注解 → schema 类型；无默认值 → required）。

完成判据：uv run pytest exercises/test_ex1.py 全绿——共 3 个测试：
  ① 行为·命中：lookup_policy("item_limit") 返回 POLICIES 里的对应文案；
  ② 行为·查无：不存在的键返回含 "policy_not_found: <键>" 的提示串（不 raise——
    错误是给模型的修复指令，L2.2 纪律）；
  ③ schema·meta：FunctionTool 自动生成的 declaration——description 恰是
    lookup_policy.__doc__ 且提到「政策」；policy_key 的类型是 string 且在 required 里。

提示：模仿 code/mock_tools.py 的工具写法（docstring 一句话用途 + Args 段）。
"""

from __future__ import annotations

POLICIES: dict[str, str] = {
    "item_limit": "单笔报销上限 5000 分，超限直接拒绝（REJECT:ITEM_OVER_LIMIT）。",
    "invoice_rule": "发票须抬头、税号与报销人一致，连号重开视为作废。",
    "budget_rule": "报销总额不得超过部门剩余预算，超出拒绝（REJECT:BUDGET_EXCEEDED）。",
}


# TODO(ex1): 给下面的函数写 docstring（一句话用途 + Args 段说明 policy_key）与实现。
# docstring 会被 FunctionTool 原样用作 declaration 的 description——meta 测试会校验它。
def lookup_policy(policy_key: str) -> str:
    """查报销政策：按政策键返回一段政策文案。

    Args:
        policy_key: 政策键，如 item_limit / invoice_rule / budget_rule
    """
    return POLICIES.get(policy_key) or f"policy_not_found: {policy_key}"
