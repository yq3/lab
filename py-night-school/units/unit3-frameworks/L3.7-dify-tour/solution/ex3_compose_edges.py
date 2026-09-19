# 练习 3 参考答案（solution 覆盖版：函数体补全，given 部分与练习骨架逐字一致）
"""compose 拓扑提取：从 dify compose 教学摘录里提取服务依赖边与反向邻接。

考察点：depends_on 在 compose 里有两种 YAML 真实写法（映射带条件 / 列表），
提取函数两种都要认；dependents_of 练图的反转（谁依赖我）。
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

    dict 与 list 都能被 list() 收敛成依赖名序列——映射式的键、列表式的元素。
    """
    adjacency: dict[str, list[str]] = {}
    for name, svc in compose.get("services", {}).items():
        deps = svc.get("depends_on") or []
        adjacency[name] = list(deps)
    return adjacency


def dependents_of(compose: dict, service: str) -> list[str]:
    """反向邻接：依赖 service 的服务列表（按名字排序）。"""
    return sorted(name for name, deps in service_edges(compose).items() if service in deps)
