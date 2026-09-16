"""里程碑三级渐进提示：先自己想 10 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（提问式/骨架式，无成段可抄的成稿），接近完整的
做法在最后一级。用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('notes', 1))"
    uv run python -c "from hints import hint; print(hint('repro', 1))"
    uv run python -c "from hints import hint; print(hint('evidence', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "notes": [
        "五节的分工先吃透再动笔：改什么=文件路径+改点+前后值（能定位到行）；为什么=一句动机"
        "+一句预期（预期错了也要写）；最小 diff=git diff 摘录（十行以内）；复现步骤=编号命令；"
        "证据=输出摘录+「变化在哪一行」。素材全在各课讲义 §3 的加餐段与 §6 源码路标——"
        "先照着任务卡把改造真做了，再回来写；没做过的改造写不出可信的「预期」。",
        "形状级：每节先抄下模板里的引导问题，用自己的话回答完删掉问题。「改什么」两句话封顶，"
        "别复述机制背景（那属于「为什么」）；「为什么」要挂到讲义主张（人格即 prompt / 权重即"
        "话语权 / 固定轮次可预算 / 顺序即语义），一句主张一句预期；「最小 diff」自查：把 diff "
        "贴回去能否还原你的改动——还原不了就是贴少了；「复现步骤」自查见 repro 提示；「证据」"
        "自查见 evidence 提示。每节写完删掉那节的 `- TODO(改造)` 行。",
        "以 L4.1 改造 B 为例的「改什么 + 为什么」成稿样式（其余节同构，换成你的内容）："
        "「改什么：hedge_fund/strategies/deep-value-lab.yaml 的 models 列表——graham 的 "
        "`weight: 2.0` 改 `4.0`，其余模型不动。」「为什么：验证权重即话语权（§2.2 弃权同剔"
        "的加权合成）；预期 graham 话语权翻倍后，同一组 signals 的合成 conviction 向 graham "
        "方向偏移，单 agent 输出不变。」——路径可定位、主张有出处、预期可证伪，三样齐了这节"
        "就算写对了。",
    ],
    "repro": [
        "「可复现」的判据：换一台干净机器、一个没读过你代码的人，照着步骤走，能到达同一个"
        "观察。四样缺一不可：从哪个 commit 起步、分支名、env 变量（名字与值域，不写密钥）、"
        "每步跑什么命令。产品克隆都锚定 commit（fc1bf25 / be952b8 / f84b2977）——写分支前的"
        "checkout 步骤。",
        "形状级：编号步骤，每步一条命令（bash 块分步走，不串联）；每步后面跟一个检查点"
        "（「这一步成了应该看到什么」——如 aihf 打出完整 CycleRecord、debug 输出里 Bull/Bear "
        "各发言 N 次、pytest 收集到 N 项）。改造前先跑一次基线、改造后跑对照——两态对比才是"
        "观察；只有一态的复现步骤是残的。",
        "以 L4.2 改造一为例的成稿样式（其余课同构）：步骤 1，git clone git@github.com:"
        "TauricResearch/TradingAgents.git，检查点：git log -1 显示 be952b8（不是就 checkout "
        "到它）；步骤 2，uv sync，检查点：import tradingagents 不报错；步骤 3，配 "
        "TRADINGAGENTS_* 四个 env；步骤 4，TRADINGAGENTS_MAX_DEBATE_ROUNDS=1 跑 main.py，"
        "检查点：debug 输出 Bull/Bear 各 1 次（辩论段共 2 次调用）；步骤 5，改成 =2 再跑，"
        "检查点：共 4 次。",
    ],
    "evidence": [
        "证据的要件是「可指认」：摘录必须是原始输出（日志/stdout/测试摘要），配一句「变化在"
        "哪一行」——没有指认的贴图只是装饰。对比类证据要两态并排（改前/改后各一段）；没有"
        "真跑产品时，先用机制件输出做替身（同一机制的离线版），并注明真产品证据需自己跑——"
        "这是诚实问题，不是格式问题。",
        "形状级：```text 块贴 3–5 行（别整屏粘贴），改动的那个数字/那一行用 <- 箭头或加粗"
        "点出；两态并排时对齐同位置方便对照；截图存 notes/assets/（自建目录），md 里引相对"
        "路径，并在「证据」节开头写一句存放位置。密钥与内部 URL 打码后再贴。",
        "以 L4.2 改造二为例的成稿样式（机制件替身版）：「cap=5 中途烧穿（step2_budget.py "
        "幕[3] 替身，真产品日志需自己跑）：BudgetExceeded: LLM 调用预算耗尽：limit=5, 已调用 "
        "5 次 / 烧穿点: 第 6 次调用（风险辩论第 1 方发言被拒）——预算检查在放行前，已花的恰好 "
        "= cap。指认：前一行证明超限即停，后一行证明检查在放行前（不超卖）。」——原始摘录 "
        "+ 指认 + 一句它证明了什么。",
    ],
}


def hint(task: str, level: int = 1) -> str:
    """返回某任务第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[task]
    return levels[min(level, len(levels)) - 1]
