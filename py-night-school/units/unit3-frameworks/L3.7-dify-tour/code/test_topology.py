"""讲义区验收：topology.py 对 compose 摘录的解析（不要改本文件——判卷口径）。"""

import topology


def test_excerpt_has_twelve_services() -> None:
    services = topology.load_compose()["services"]
    assert len(services) == 12
    assert set(services) == {
        "init_permissions",
        "api",
        "worker",
        "worker_beat",
        "web",
        "db_postgres",
        "redis",
        "sandbox",
        "plugin_daemon",
        "agent_backend",
        "nginx",
        "weaviate",
    }


def test_api_depends_on_db_and_redis() -> None:
    """关键事实（以摘录为准）：api 依赖 db_postgres / redis / agent_backend，且 init 容器先行。"""
    edges = topology.service_edges(topology.load_compose())
    assert edges["api"] == ["init_permissions", "db_postgres", "redis", "agent_backend"]
    assert edges["worker"][:3] == ["init_permissions", "db_postgres", "redis"]


def test_depends_on_accepts_both_yaml_forms() -> None:
    """映射式（api，带 condition）与列表式（nginx）两种 depends_on 都解析成邻接表。"""
    compose = topology.load_compose()
    assert isinstance(compose["services"]["api"]["depends_on"], dict)
    assert isinstance(compose["services"]["nginx"]["depends_on"], list)
    assert topology.service_edges(compose)["nginx"] == ["api", "web"]


def test_image_short_strips_registry_and_tag() -> None:
    assert topology.image_short("langgenius/dify-api:1.17.1") == "dify-api"
    assert topology.image_short("cr.weaviate.io/semitechnologies/weaviate:1.39.2") == "weaviate"
    assert topology.image_short("postgres:15-alpine") == "postgres"
