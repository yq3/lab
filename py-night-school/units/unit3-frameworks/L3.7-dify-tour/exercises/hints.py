"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "计数是遍历 nodes 取 data.type——想想讲义 dsl_reader.node_types 是怎么数的。"
        "孤立检测的关键：孤立不是「没有入边」（start 也没有入边）——图论里孤立节点的定义是什么？"
        "你需要先把 6 条边折叠成一个「被边碰过」的节点集合。",
        "形状级三问：计数结果用什么容器累计（手写 dict 还是 collections.Counter——注意后者要转成"
        "普通 dict 才好做 == 断言）？「被碰过」集合怎么从 edges 一次算出（每条边贡献几个元素、"
        "分别取哪个键）？orphan 的推导是节点集合减碰过集合——为什么返回前要 sorted？",
        '计数：counter = Counter(n["data"]["type"] for n in graph["nodes"])，return dict(counter)；'
        '孤立：touched = {e["source"] for e in graph["edges"]} | {e["target"] for e in '
        'graph["edges"]}，return sorted(n["id"] for n in graph["nodes"] if n["id"] not in touched)'
        "——顶部需要 from collections import Counter。",
    ],
    "ex2": [
        "这题没有逻辑要写——考判断。四列各有落点：dify_entry 写到模块/服务级（讲义 §6 的源码路标"
        "就是证据口径）；library_counterpart 点名课号；lock_in_cost 回答「迁出平台时要重做什么」。"
        "先读讲义 Step 4 再动笔，别凭印象。",
        "形状级自查：知识库的平台侧入口是哪个服务文件（dataset_ 开头、四千多行那个）？模型接入"
        "靠哪个后台服务装插件（compose 里谁守护插件）？观测运营的库形态对应物是每课的什么文件？"
        "部署形态一行：平台侧数一数 compose 里的服务数，库侧回忆验收是哪三条命令？"
        "你自己的第七行挑哪个维度、四列各放什么？",
        "对照 code/capabilities.py 的六行——那是讲义版口径，四列写法照它的颗粒度来（入口带"
        "源码路径、对应物带课号、代价写具体的迁出成本）。第七行没有标准答案：扩展生态与插件/"
        "多租户与权限/版本与发布管理任选，同样四列、同样具体——meta-test 只查结构与标记，"
        "内容质量由你自己把关。",
    ],
    "ex3": [
        "先看 data/compose_excerpt.yaml：api 的 depends_on 是映射（键是依赖名），nginx 的是列表。"
        "pyyaml 读出来一个 dict 一个 list——你的函数要 isinstance 分流。dependents_of 是把正向"
        "邻接表反过来用：遍历谁的什么、收集什么？",
        "形状级三问：isinstance 判 dict 时取什么、判 list 时取什么（还是其实能统一）？无 depends_on "
        "的服务（如 web）get 出来是什么、怎么落到空列表？dependents_of 里遍历邻接表的 items，"
        "条件写什么、命中收集谁、为什么最后 sorted？",
        '与讲义 topology.service_edges 同构：deps = svc.get("depends_on") or []；adj[name] = '
        "list(deps)（dict 和 list 都能被 list() 收敛成依赖名序列）。反转：return sorted(svc for svc, "
        "deps in service_edges(compose).items() if service in deps)。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
