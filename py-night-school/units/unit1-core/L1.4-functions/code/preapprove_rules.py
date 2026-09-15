"""L0.1 的 preapprove 拆成规则函数序列——框架「中间件 / 校验链 / guardrail」的雏形。

核心事实：def 语句执行时创建一个函数对象并把它绑定到名字上——
函数是值，可以放进 list、按序取出、当参数传递（这就是「一等公民」的全部含义）。

对照 Java：同样的结构要 interface Rule + List<Rule> + 策略模式注册；
Python 里函数天生满足「可调用 + 可比较身份 + 自带名字」，零仪式。
langgraph 的条件边（add_conditional_edges(path=...) 收一个函数）、
openai-agents 的 guardrail，走的都是这个形状。
"""

from collections.abc import Callable

# L0.1 的两个上限原样搬来（金额单位：整数分）
DAILY_MEAL_LIMIT_CENTS = 5000
TRIP_TOTAL_LIMIT_CENTS = 500000

# 规则的类型别名：吃明细金额列表，命中返回拒绝原因，未命中返回 None
# Callable[[参数类型], 返回类型] 对照 java.util.function.Function<List<Integer>, String>
Rule = Callable[[list[int]], str | None]


def check_invalid(items_cents: list[int]) -> str | None:
    """脏数据最先挡：任意金额 <= 0 -> "REJECT:INVALID_AMOUNT"。"""
    if any(c <= 0 for c in items_cents):
        return "REJECT:INVALID_AMOUNT"
    return None


def check_item_limit(items_cents: list[int]) -> str | None:
    """单笔超限：任意一笔 > DAILY_MEAL_LIMIT_CENTS -> "REJECT:ITEM_OVER_LIMIT"。"""
    if any(c > DAILY_MEAL_LIMIT_CENTS for c in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    return None


def check_total_limit(items_cents: list[int]) -> str | None:
    """合计超限：sum > TRIP_TOTAL_LIMIT_CENTS -> "REJECT:TOTAL_OVER_LIMIT"。"""
    if sum(items_cents) > TRIP_TOTAL_LIMIT_CENTS:
        return "REJECT:TOTAL_OVER_LIMIT"
    return None


# 规则序列 = 数据：列表顺序就是判定优先级（想插一条新规则？append 进来即可，主函数一行不改）
RULES: list[Rule] = [check_invalid, check_item_limit, check_total_limit]


def preapprove(items_cents: list[int]) -> str:
    """按序执行规则链，第一条命中（返回非 None）的 verdict 胜出；全未命中放行。"""
    for rule in RULES:
        verdict = rule(items_cents)
        if verdict is not None:
            return verdict
    return "PASS"


def describe_rules() -> list[str]:
    """函数对象自带元数据：__name__ 是函数自己的名字（框架日志/追踪全靠它，不用注解）。"""
    return [rule.__name__ for rule in RULES]
