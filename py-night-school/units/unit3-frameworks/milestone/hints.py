"""里程碑三级渐进提示：先自己想 10 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/提问式，无成行可抄的答案代码），
接近完整的做法在最后一级。用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('aggregate', 1))"
    uv run python -c "from hints import hint; print(hint('notes', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "aggregate": [
        "三路证据的共同主键是框架 key（bench.LessonResult.framework / tablegen.MetricRow.framework "
        "/ notes 字典的键），FRAMEWORKS 的键序就是行序。三个格子各自独立判定：bench 是「组内全绿才绿」的"
        "合并布尔值；定量是「同组多条怎么并列展示」的排版问题；lock_line 是「小节正文为空或含占位符就降级」"
        "的解析问题——给定件 section_body / first_meaningful_line 已经把最难的解析做完了。",
        "形状级：对 FRAMEWORKS 逐键循环。每键三个问题——bench 组里有没有记录？没有给什么值；"
        "定量组里 deps 取哪一条（同框架共用一个 lock，任一条非 None 即可，其余等值）；手写总行数"
        "怎么把组内多行的行数连成 '63 / 28'（None 的行跳过还是算进去？全空给什么？）。lock_line："
        "对哪个标题取小节？返回的正文什么时候算「没写完」——空、缺页、占位符三种情况各落到哪个值？"
        "注意占位符的判断要落在小节正文上，不是整页全文上（想想为什么：别的没写完的小节不该连累锁定性这一格）。",
        "每键的核心五句（对照题目口径补全变量名即可）:"
        " bench_hits = [r for r in bench_rows if r.framework == key];"
        " bench_cell = '—' if not bench_hits else ('PASS' if all(r.status == 'PASS' for r in bench_hits) else 'FAIL');"
        " deps 取组内第一条非 None 的 m.deps（同框架共用一个 lock），是 None 就给 '缺'（条件表达式最直白，"
        "别用 or 兜底——数字上 or 会误伤）；"
        " handwritten_cell = ' / '.join(str(m.handwritten_loc) for m in metric_hits if m.handwritten_loc is not None)"
        " or '缺';"
        " lock_line = line if line and PLACEHOLDER not in body else MISSING_NOTE。"
        "最后 append DecisionRow(FRAMEWORKS[key], ...)。",
    ],
    "notes": [
        "每页的素材都在对应课讲义结尾的「与 mini-agent 对照」小节里——先读那张表再动笔。"
        "五节的分工要吃透：付掉了什么=替你省的行（引用具体机制名）；没付什么=留给你的纪律与决策；"
        "最惊讶=一个机制+课次+为什么；锁定性=一句压秤的话（会进决策表）；什么时候选=两个正例一个反例。",
        "形状级：每节先抄下问题，用自己的话回答后删掉问题。「付掉了什么」按 mini-agent 的文件对行"
        "（agent.py 的循环 / tools.py 的注册表 / structured.py 的回喂）；「锁定性一句话」必须是单行陈述句，"
        "句式参考「多给你 X，代价是 Y」；写不出「最惊讶」就回讲义翻你当时画过线的段落——"
        "候选机制模板里已经列了三个。",
        "以 deepagents 页的「最惊讶」为例的成稿样式（其余页同构，换成你自己的机制）："
        "「文件 = state 键（L3.5 backends/state.py）：虚拟文件系统没有任何磁盘，读写全走 langgraph "
        "channel——我以为的文件系统其实是一个字典，而这让它免费获得 checkpoint 的暂停恢复语义。」"
        "一句机制 + 出处 + 为什么惊讶，两三行以内。锁定性一句话同款克制：一行，别写成段落。",
    ],
}


def hint(task: str, level: int = 1) -> str:
    """返回某任务第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[task]
    return levels[min(level, len(levels)) - 1]
