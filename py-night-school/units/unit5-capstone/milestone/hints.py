"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('g1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "g1": [
        "取证只差一行：eventstore.EventStore 有一个读事件流的方法（docstring 里写的两个入口之一），"
        "给它 run_key、不按 type 过滤，拿回整条流。然后两个断言各吃这个返回值的一个投影："
        "「顺序」用每行的 type 字段拼列表，取末尾与 expected_tail 对齐（注意 tuple 与 list 能直接 "
        "== 吗？先想想再试）；「seq 连续」用每行的 seq 字段拼列表，它应该恰好是从 0 数到条数减一"
        "——range 在这里就是答案的形状。",
        "形状级：rows = store.???(run_key)。types = [row['???'] for row in rows]；"
        "assert types[???:] == ???(expected_tail)。seqs = [row['???'] for row in rows]；"
        "assert seqs == ???(range(len(rows)))——末尾切片的起点用负数下标最好写"
        "（-len(expected_tail)）。",
        "完整做法：rows = store.events_for(run_key)；types = [row['type'] for row in rows]；"
        "assert types[-len(expected_tail):] == list(expected_tail), f'事件流收尾 {types[-len("
        "expected_tail):]} != {list(expected_tail)}'；seqs = [row['seq'] for row in rows]；"
        "assert seqs == list(range(len(rows))), 'seq 必须从 0 连续无空洞'。",
    ],
    "g2": [
        "两张审批单都是 dict，指纹在 content_hash 键。三件事：first 的指纹非空、second 的指纹非空、"
        "两个指纹不相等——前两件防「没锁版本的批了」，第三件是 A6 本体（同一单据重生成出不同"
        "建议单，graph.content_hash 的契约就是内容一变指纹变）。断言消息里把两个值都打出来，"
        "红的时候一眼看出是「没变」还是「空」。",
        "形状级：assert first['???']；assert second['???']；assert second['???'] != "
        "first['???'], f'……{first}……{second}'——三个断言各自独立，别合并成一个 and（红的时候"
        "分不清是哪件）。",
        "完整做法：assert first['content_hash'], 'first 缺指纹'；assert second['content_hash'], "
        "'second 缺指纹'；assert second['content_hash'] != first['content_hash'], f\"content_hash "
        "没有轮换: {first['content_hash']} == {second['content_hash']}（A6：批的还是旧版）\"。",
    ],
    "mapping": [
        "「核实过」的最低标准：那一行写下的每个类名/方法名，你都在本地克隆里亲眼见过它存在于"
        "对应文件里（grep 到、打开看了）。克隆在 ~/develop/opensource/ 下的 langgraph4j 与 "
        "spring-ai-alibaba，锚点 commit 在文档末尾「核实锚点」一节。四行的方向：Plan 判别联合"
        "是语言级机制 + JSON 绑定注解；fail-closed 门是纯手写类（没有框架对应）；缓存即审计是"
        "JPA Entity + 代理装饰；拒绝回环去核实 CompiledGraph 的改状态方法。克隆里没有的，"
        "老实写「需自建」+ 一句为什么——这是诚实纪律，不是丢分。对照 solution/JAVA-MAPPING.md "
        "前先自己写一版。",
        "形状级：把 TODO(毕业) 单元格替换成「API/机制名 + 出处文件 + 一句怎么用」三件套；"
        "翻译坑列照抄原提示展开成两三条。别把整行重写——模式列与 Python 列不动，只补 Java "
        "列。补完跑 uv run pytest tests/test_mapping_meta.py 看结构口径（主表行数、四列非空、"
        "需自建两行、占位清零互证）。",
        "完整做法（以 fail-closed 门那行为例的行文形状）：Java 列写「**无框架对应，纯手写类**："
        "enum 三态 + record 裁决值 + 一个静态纯方法按常量顺序调七个 private 检查、首个命中即返回"
        "（L4.3 读过的 Vibe-Trading enforcement 的 Java 同族就是原型）」——即：先答「有没有框架"
        "对应」（没有就写需自建），再答「那它是什么形状」，每个名词都能指到克隆里的真实文件。"
        "四行都按这个形状写，写完自查：文里出现的每个 Java 类名，你都能说出它在哪个文件见过。",
    ],
}


def hint(topic: str, level: int = 1) -> str:
    """返回某题第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[topic]
    return levels[min(level, len(levels)) - 1]
