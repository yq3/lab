"""解析 docker compose 的服务拓扑：服务 -> 依赖邻接表 + 镜像简名（讲义 Step 1）。

输入是 data/compose_excerpt.yaml（从 dify 自部署 compose 模板裁剪的教学摘录，
来源与裁剪口径见该文件头注释）。平台课离线主线第一站：不起 docker，
先读懂「平台」的部署视图——它是一组互相依赖的服务，不是一个 pip 依赖。

depends_on 在 compose 里有两种真实写法（摘录里都保留了）：
  映射式（带启动条件）：depends_on: {db_postgres: {condition: service_healthy, ...}}
  列表式（只管顺序）：  depends_on: [api, web]
pyyaml 把前者读成 dict、后者读成 list——解析两种形态正是本题的教学点。
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

LESSON_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = LESSON_ROOT / "data" / "compose_excerpt.yaml"


def load_compose(path: Path = COMPOSE_FILE) -> dict:
    """读 compose YAML 文件，返回解析后的字典（yaml.safe_load：纯数据，不执行任何标签）。"""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def service_edges(compose: dict) -> dict[str, list[str]]:
    """提取「服务 -> 它 depends_on 的服务列表」邻接表（保留 YAML 里的声明顺序）。

    映射式 depends_on 读出来是 dict（键即依赖名，值是条件对象）；
    列表式读出来就是 list。两种都要认。
    """
    adjacency: dict[str, list[str]] = {}
    for name, svc in compose.get("services", {}).items():
        deps = svc.get("depends_on") or []
        adjacency[name] = list(deps) if isinstance(deps, dict) else list(deps)
    return adjacency


def image_short(image: str) -> str:
    """镜像全名 -> 简名：去掉仓库前缀与 tag。

    langgenius/dify-api:1.17.1 -> dify-api；
    cr.weaviate.io/semitechnologies/weaviate:1.39.2 -> weaviate；
    postgres:15-alpine -> postgres。用于打印「这个格子是谁」而不是「从哪拉」。
    """
    no_tag = image.rsplit(":", 1)[0] if ":" in image else image
    return no_tag.rsplit("/", 1)[-1]


def print_topology(compose: dict) -> None:
    """打印服务拓扑：每行「服务（镜像简名） -> 依赖…」。"""
    edges = service_edges(compose)
    images = {name: image_short(svc.get("image", "")) for name, svc in compose.get("services", {}).items()}
    print(f"== compose 服务拓扑（{len(edges)} 个服务，摘录自 dify 自部署模板） ==")
    for name, deps in edges.items():
        arrow = f" -> {deps}" if deps else " ->（无依赖）"
        print(f"{name}（{images[name]}）{arrow}")


if __name__ == "__main__":
    print_topology(load_compose())
    sys.exit(0)
