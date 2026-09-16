"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

import ex3_compose_edges as ex3


def test_edges_from_mapping_form() -> None:
    """映射式 depends_on（api/worker，带 condition）：键即依赖名，忽略条件值。"""
    edges = ex3.service_edges(ex3.load_compose())
    assert edges["api"] == ["init_permissions", "db_postgres", "redis", "agent_backend"]
    assert edges["worker"][:3] == ["init_permissions", "db_postgres", "redis"]


def test_edges_from_list_form_and_no_deps() -> None:
    edges = ex3.service_edges(ex3.load_compose())
    assert edges["nginx"] == ["api", "web"]  # 列表式
    assert edges["web"] == []  # 无 depends_on -> 空列表，不是缺键


def test_dependents_of_redis() -> None:
    """反向邻接：依赖 redis 的恰好 4 个服务（api/worker/worker_beat/agent_backend）。"""
    assert ex3.dependents_of(ex3.load_compose(), "redis") == ["agent_backend", "api", "worker", "worker_beat"]


def test_dependents_of_api_is_nginx_only() -> None:
    assert ex3.dependents_of(ex3.load_compose(), "api") == ["nginx"]
