"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "这一列的语义是「五课对版」（unit3 README 的字节相同约定）。先想清楚三件事：用什么比较"
        "「字节一致」（指纹还是直接 ==）；基准选谁（哪一版算「正版」）；缺文件的课怎么诚实降级。",
        "形状级三问：指纹函数已给定（_short_digest 吃 bytes——文件怎么读成 bytes）；基准怎么从"
        "「现存指纹的 Counter」里取（众数、并列怎么办——想想讲义说的确定性纪律）；返回 dict 的"
        "三种值分别在哪个分支产生？需要一个预收集 pass 再一个组装 pass 吗？",
        "完整做法：先一轮循环收集 digests（存在才收），全部缺失就直接全 missing；基准 = "
        "sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]（次数降序、指纹升序——并列"
        "取字典序最小）；再一轮按三分支组装：key 缺席 → 'missing'，指纹等于基准 → "
        'f"in-place({d})"，否则 f"drift({d})"。需要的顶部 import：from collections import Counter。',
    ],
    "ex2": [
        "六个场景各对应讲义 Step4 决策表的一行「何时选谁」。先盖住讲义自己填 CHOICES，再对照；"
        "每个场景里都有一个关键词压倒其他选项（断电恢复 / 即弃 / 工作台 / 调试器 / 画布 / 原语）。",
        "形状级六问：s1 的「杀进程后续跑」是哪一课的压轴实验？s2 的「零锁定」只有谁给得起？"
        "s3 的「派活+文件台+记忆」是哪个 harness 的三件套？s4 的两个「要」分别是哪一课的独有件？"
        "s5 的「不写代码」是哪种形态的题眼？s6 的「换人不换对话」是哪一课 Step3 的取证？",
        "答案映射：s1→langgraph（L3.3 分进程恢复）、s2→mini-agent（milestone 249 行零锁定）、"
        "s3→deepagents（L3.5 三件套）、s4→adk（L3.6 Step5 调试器+eval）、s5→dify（L3.7 画布表单）、"
        "s6→openai-agents（L3.1 handoff-as-tool）。理由每条 ≥15 字并把关键词与课次写进去。",
    ],
    "ex3": [
        "这是覆盖型练习：验收测试检查的是清单表本身（12 行 / 框架判据 / 六个名字 / 维度白名单）。"
        "先读 test_ex3.py 的四条断言——它们就是评分标准；再对照讲义的结业自查表补 7 行。",
        "形状级：每行 = 白名单维度 + 「能……」句式 + 课次证据。TODO 行至少要覆盖：deepagents 这个"
        "名字、Send 扇出或「为什么 5 轮」类机制条目、Checkpoint 私有格式、adk 的调试器/eval、"
        "五仓跳读的某仓入口、「框架判据」维度至少再一行。想想哪几条是你真有体感的。",
        "参考写法（七行示例方向）：deepagents 五轮的原因（task 子代理独立对话+Advice 收尾轮，"
        "L3.5 Step1）；装配 loc 口径能现场重数（def 行计入、docstring 剔除，L3.4 count_loc）；"
        "Checkpoint msgpack+serde 白名单（L3.3 Step4）；adk web 与 AgentEvaluator 入口（L3.6 Step5）；"
        "llama_index 的 AgentWorkflow 对照 handoff（L3.1 视角）；「何时自研」一行（mini-agent 的「—」格）；"
        "Send 扇出与线程池的差异（L3.4 §5）。每行挑一个维度词，别堆长句。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
