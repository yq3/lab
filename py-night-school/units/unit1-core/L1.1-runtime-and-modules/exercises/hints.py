"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在 exercises/ 目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "被 import 时 __name__ 是模块名，guard 条件为假，块内代码不执行——所以三个 TODO 里"
        "只有 ex1c 所在的块会因「直接运行」而触发；ex1a/ex1b 是普通的函数实现。",
        'ex1a 的形状：return f"{claim_id} -> {verdict}"（注意 -> 两侧各一个空格）；'
        'ex1b 的形状：print(format_daily_report("CLM-2026-0001", "PASS")) 然后 return 0。',
        'ex1c 两件事：文件顶部补 import sys；if __name__ == "__main__": 下一行缩进 4 格写 sys.exit(main())——'
        "对照 Java：public static void main 的方法体搬到了模块底部的这个块里。",
    ],
    "ex2": [
        "重放事故现场再想：-m 跑通了模块（没报错），却什么都没打印——模块里缺了什么？",
        "main() 已经写好但无人调用：缺的是「入口约定」那一块，讲义 §3 Step 6 / §5 的主角。",
        '在 runner.py 文件末尾补两行：if __name__ == "__main__": 换行缩进 4 格写 sys.exit(main())。'
        "补完后 python -m claimfix.runner 1200,3500 应打印判定并退出码 0。",
    ],
    "ex3": [
        "逐个文件问「它被加载时 __name__ 是什么」：直接运行的那个是 __main__，其余一律是自己的模块名（不带 .py）。",
        "import 会执行被导入文件的顶层 print——所以 B 场景的第一行输出来自 probe_a；"
        "而 main branch 行只属于被直接运行的文件，import 链上的文件一行都不会有。",
        "B 场景三行：probe-a 的模块名行、probe-b 的模块名行、probe-b 看到 probe_a.__name__ 的行；"
        "C 场景共五行：probe-a 与 probe-b 的四行照打（模块名身份），最后两行是 probe-c 的"
        " __main__ 身份行（它还 import 了 probe_b）与 main branch 行。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
