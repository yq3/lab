# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""tablegen 扩展：给决策表加一列「契约测试是否在位」。

背景（unit3 README 的对版约定）：code/test_contract.py 在 L3.1 / L3.2 / L3.4 / L3.5 /
L3.6 五课**字节相同**——「同题换框架，题面不变」靠它担保。决策表要能回答：
我这份 checkout 里，五课的契约是不是还齐着、有没有谁悄悄改版了？

你要实现的列值口径（与验收同一口径）：
  - 该课 code/test_contract.py 不存在        -> "missing"
  - 文件字节指纹 == 基准（众数指纹）          -> "in-place(<指纹8>)"
  - 指纹 != 基准                              -> "drift(<指纹8>)"
  - 基准 = 现存指纹的众数（出现次数最多）；并列时取字典序最小的指纹——
    同一组输入永远产出同一列（决策表的确定性纪律，对照 langgraph 归并顺序的确定性）。

完成判据（exercises/test_ex1.py，4 个测试）：五课同版本全部 in-place 且指纹正确；
一课漂移被点名 drift；缺文件的课标 missing；指纹并列时基准的选取是确定的。

提示：指纹半边已给定（_short_digest）；需要的顶部 import 在 TODO 注释里点名。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# 契约脚本在课时目录内的固定位置（unit3 README 的约定）
CONTRACT_REL = "code/test_contract.py"


def _short_digest(data: bytes) -> str:
    """字节内容的 md5 指纹前 8 位（given：对版校验的「指纹」半边）。

    对照 Java：BytesInputStream 手撸摘要的活儿，这里 hashlib 一行——
    注意吃的是 bytes（文件 read_bytes），不是 str（编码差异会改变指纹）。
    """
    return hashlib.md5(data).hexdigest()[:8]


def contract_column(lesson_dirs: dict[str, Path]) -> dict[str, str]:
    """TODO(ex1)：计算每课「契约测试是否在位」列的格子值。

    lesson_dirs：课时名 -> 课时目录（不保证存在、不保证里面有契约文件）。
    返回：课时名 -> 列值（missing / in-place(<指纹8>) / drift(<指纹8>)）。
    """
    # TODO(ex1): 需要的顶部 import：from collections import Counter
    # TODO(ex1): 先算「现存文件的指纹」dict（missing 的课先记下缺席）；
    #   再定基准指纹——现存指纹的众数，并列取字典序最小（确定性）；
    #   最后三分支组装返回 dict：missing / in-place(指纹) / drift(指纹)。
    raise NotImplementedError("TODO(ex1): 补全 contract_column")
