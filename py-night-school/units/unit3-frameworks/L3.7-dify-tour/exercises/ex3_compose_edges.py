# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体/区域与所需的顶部 import，其余不要动）
"""compose 拓扑提取：从 dify compose 教学摘录里提取服务依赖边与反向邻接。

考察点：depends_on 在 compose 里有两种 YAML 真实写法（本课 data/compose_excerpt.yaml
两种都有）：映射式（api：带 condition/required 的对象）与列表式（nginx：只给名字）。
pyyaml 把前者读成 dict、后者读成 list——提取函数两种都要认。
再练一次图的反转：邻接表给「我依赖谁」，dependents_of 要回答「谁依赖我」。

完成判据：uv run pytest exercises/test_ex3.py 全绿——
  api/worker 的依赖序（映射式）；nginx 的依赖（列表式）；
  依赖 redis 的恰好 4 个服务；只有 nginx 依赖 api。
"""

from __future__ import annotations

from pathlib import Path

import yaml

COMPOSE_FILE = Path(__file__).resolve().parents[1] / "data" / "compose_excerpt.yaml"


def load_compose() -> dict:
    """读 compose 教学摘录（given：不要动）。"""
    with open(COMPOSE_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def service_edges(compose: dict) -> dict[str, list[str]]:
    """提取「服务 -> 它 depends_on 的服务列表」（保留 YAML 声明顺序）。

    映射式 depends_on 读出来是 dict（键是依赖名，值是条件对象，忽略值）；
    列表式读出来是 list（元素就是依赖名）。无 depends_on 的服务映射到空列表。
    """
    # TODO(ex3): 遍历 services，按 depends_on 的实际类型（dict/list）统一成 list[str]
    raise NotImplementedError("TODO(ex3): 补全 service_edges")


def dependents_of(compose: dict, service: str) -> list[str]:
    """反向邻接：依赖 service 的服务列表（按名字排序，断言要确定性）。

    提示：先把正向邻接表算出来，再遍历它反着收集。
    """
    # TODO(ex3): 基于 service_edges 的结果反转，收集依赖者并排序
    raise NotImplementedError("TODO(ex3): 补全 dependents_of")
