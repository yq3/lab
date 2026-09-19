# 练习 2 参考答案（solution 覆盖版：TODO 行补全 + 自选第七行，given 部分与练习骨架逐字一致）
"""平台能力清单：把讲义 Step 4 的表变成你自己的判断（覆盖型练习，配 meta-test）。

每行四列：dimension / dify_entry / library_counterpart / lock_in_cost。
本答案是讲义版口径的一份完整实现，第七行选了「扩展生态」——你自己的答案
只要四列具体、维度不重复，判卷（meta-test）不比对内容本身。
"""

from __future__ import annotations

FIELDS = ("dimension", "dify_entry", "library_counterpart", "lock_in_cost")

CAPABILITIES: list[dict[str, str]] = [
    {
        "dimension": "画布编排",
        "dify_entry": "web 画布拖拽编排 workflow，图即数据（DSL YAML，api/services/app_dsl_service.py 的 export_dsl）",
        "library_counterpart": "langgraph StateGraph 代码构图（L3.2–L3.4）；mini-agent 的 while 循环（Unit 2）",
        "lock_in_cost": "图逻辑不可 git diff 审查、不可单测；迁出平台=按 DSL 重写一遍图",
    },
    {
        "dimension": "HITL 表单",
        "dify_entry": "human-input 节点：暂停→表单→按动作边恢复（api/core/workflow/nodes/human_input/）",
        "library_counterpart": "langgraph interrupt + checkpoint（L3.3）；openai-agents 的 RunState（L3.1）",
        "lock_in_cost": "表单 schema 与暂停/恢复语义是平台私有格式与运行时行为",
    },
    {
        "dimension": "知识库",
        "dify_entry": "dataset 服务（api/services/dataset_service.py，4484 行（wc -l））+ knowledge-retrieval 节点",
        "library_counterpart": "无内建——库形态要自己组 RAG（毕设的 SQLite + 检索，深入指路 mcp-for-beginners）",
        "lock_in_cost": "切块/嵌入/检索策略绑平台配置；文档数据进平台库，导出走 API",
    },
    {
        "dimension": "模型接入",
        "dify_entry": "模型供应商体系 + 插件市场（plugin_daemon 服务，docker/docker-compose-template.yaml）",
        "library_counterpart": "每课 .env 三变量直连端点；adk 的 litellm 中转层（L3.6）",
        "lock_in_cost": "供应商配置是平台数据库里的数据不是代码；换平台要重配全部模型路由",
    },
    {
        "dimension": "观测与运营",
        "dify_entry": "web 控制台：运行日志、标注、应用统计（api/services/workflow_app_log_query_service.py）",
        "library_counterpart": "无内建——框架课 test_contract.py 的 pytest 契约 + mini-agent 的 print 取证",
        "lock_in_cost": "运营数据在平台库里；对运行行为的断言只能进控制台人工看，进不了 CI",
    },
    {
        "dimension": "部署形态",
        "dify_entry": "compose 十余服务：api/worker 分离 + db/redis/向量库/nginx（docker-compose-template.yaml）",
        "library_counterpart": "库形态（L3.1–L3.6、mini-agent）是 uv 单进程——pytest 即验收；毕设 FastAPI + SQLite",
        "lock_in_cost": "N-tier 运维成本：升级、备份、扩容、安全加固都是平台工程，不是 pip install",
    },
    {
        "dimension": "扩展生态",
        "dify_entry": "插件市场 + plugin_daemon 运行时：工具/模型供应商以插件包安装（marketplace.dify.ai）",
        "library_counterpart": "MCP server 即插即用（L2.5 mini-agent 直接挂）；框架课的工具是函数+装饰器注册",
        "lock_in_cost": "插件是平台私有打包格式；自研工具想进画布要按它的插件规范重写并签名分发",
    },
]
