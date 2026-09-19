"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "分三步想：① json.loads 的产物怎么变成 Plan——Pydantic 的哪个入口能带着判别联合一起校验？"
        "② 失败时除了「抛」，还能从异常对象上拿到什么结构化信息（首错）？——映射函数 _reason_code_for "
        "已经给你，它吃的是什么形状？③ 校验都过了，为什么还要对每步的 tool 再查一遍 TOOL_ALLOWLIST"
        "（Literal tag 不是已经枚举了合法工具吗——这层查是给谁看的）？",
        "形状级：哪个类的哪个方法负责「对 Python 对象按模型校验」？except 住哪类异常后，"
        "e.errors()[0] 的哪些键分别给你原因码（喂 _reason_code_for）和出错位置（loc 拼进 detail）？"
        "合法路径的循环里，step 的哪个属性和 TOOL_ALLOWLIST 做成员判断？不满足时 PlanRejection 的"
        "两个字段分别填什么？",
        "完整做法：from pydantic import TypeAdapter, ValidationError（顶部补 import）；"
        "plan = TypeAdapter(Plan).validate_python(obj) 放进 try；except ValidationError as e: 取 "
        "error = e.errors()[0]，loc = '.'.join(str(p) for p in error['loc']) or '<root>'，返回 "
        "PlanRejection(reason_code=_reason_code_for(error), detail=f'{loc}: {error[\"msg\"]}')。"
        "合法后 for index, step in enumerate(plan.steps)：step.tool 不在 TOOL_ALLOWLIST 时返回 "
        "PlanRejection(reason_code='unknown_tool', detail=f'steps[{index}].tool: {step.tool!r} 不在白名单')；"
        "全部通过才 return plan。",
    ],
    "ex2": [
        "每步三件事的顺序：先白名单（不在——怎么让失败「可见不静默」，PlanExecutionError 的构造参数"
        "看类定义）、再 produces 占用检查（results 这个 dict 里已经有哪些键）、最后才是真正的工具调用。"
        "工具入参别硬编码 step.dept——想想哪些字段是「步的元数据」，剩下的才是参数。",
        "形状级：step.model_dump() 给你完整字段的 dict，减掉 _COMMON_FIELDS 之后剩下的就是工具入参"
        "（调用时怎么把 dict 展开成关键字参数）？两个 raise 的触发条件分别是「tool 不在白名单」和"
        "「produces 已在 results」；成功路径把工具返回值写进 results 的哪个键？",
        "完整做法：顶部补 from plan import TOOL_ALLOWLIST；循环体内：if step.tool not in "
        "TOOL_ALLOWLIST: raise PlanExecutionError(step.step_id, step.tool, 'unknown_tool')；"
        "if step.produces in results: raise PlanExecutionError(step.step_id, step.tool, "
        "f'duplicate_produces: {step.produces}')；payload = {k: v for k, v in step.model_dump().items() "
        "if k not in _COMMON_FIELDS}；results[step.produces] = TOOL_FUNCS[step.tool](**payload)。",
    ],
    "ex3": [
        "拒绝分支想两件事：PlanRejection 实例放进哪个状态键——看它的 Annotated，reducer 每次收到的"
        "是什么形态（一个元素？一个列表？）；events 里把「拒了+为什么」登记成一条，讲义约定是 "
        "'plan.rejected:' 拼什么。三分支路由：合法与否看哪个键（NotRequired 键缺席时 state.get "
        "给什么）；「未超限」拿 plan_rejections 长度与 MAX_REPLANS 比——第 3 次拒绝发生时，"
        "已经用掉几次重规划？",
        "形状级：拒绝分支 return 的 dict 有哪两个键？plan_rejections 的值为什么必须「装一个元素的"
        "列表」？事件名字符串用 + 拼接哪两段？路由函数的三个返回值分别对应图里哪三个节点名——"
        "合法与否怎么读那个 NotRequired 键（键缺席时 state.get 不带第二参返回什么）？「未超限」"
        "的判断拿哪个键里列表的长度、跟哪个常量比，不等号朝哪边（自己代入「第 3 次拒绝还回不回"
        "planner」验证一次）？",
        "完整做法：拒绝分支 return {'plan_rejections': [outcome], 'events': "
        "[f'plan.rejected:{outcome.reason_code}']}；路由：def route_after_gate 里先 "
        "if state.get('plan') is not None: return 'executor'，再 "
        "if len(state.get('plan_rejections') or []) <= MAX_REPLANS: return 'planner'，"
        "最后 return 'escalate'。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
