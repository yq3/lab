# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体/区域与所需的顶部 import，其余不要动）
"""平台能力清单：把讲义 Step 4 的表变成你自己的判断（覆盖型练习，配 meta-test）。

考察点：这不是逻辑题，是判断题——本课固定收尾产出一份「平台能力清单」，
每行四列：dimension（维度）/ dify_entry（dify 有没有、入口在哪）/
library_counterpart（库形态对应物——L3.1–L3.6 或 mini-agent 的什么）/ lock_in_cost（锁定代价）。
骨架给了前两行（画布编排 / HITL 表单）作口径示范；你要：
  ① 补全 TODO 标注的四行（知识库 / 模型接入 / 观测与运营 / 部署形态）；
  ② 再自己加至少一行清单外维度（候选：扩展生态与插件、多租户与权限、
     版本与发布管理、环境隔离……挑你有感觉的写）。

验收（meta-test，L0.1 ex2 先例）：test_ex2.py 直接检查清单本身——六个必须维度齐全、
每行四列字段完整非空、每行的库形态对应物必须点名真实课程或诚实写「无」、
总行数不少于 7 且维度不重复。删行偷懒、留 TODO 占位都过不了。

证据口径：dify 入口写到模块/服务级（源码里核实过路径存在的写法见讲义 §6 源码路标）。
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
    # TODO(ex2-①): 补全下面四行（每个字段的空串换成你的判断；四列都要具体）
    {
        "dimension": "知识库",
        "dify_entry": "",
        "library_counterpart": "",
        "lock_in_cost": "",
    },
    {
        "dimension": "模型接入",
        "dify_entry": "",
        "library_counterpart": "",
        "lock_in_cost": "",
    },
    {
        "dimension": "观测与运营",
        "dify_entry": "",
        "library_counterpart": "",
        "lock_in_cost": "",
    },
    {
        "dimension": "部署形态",
        "dify_entry": "",
        "library_counterpart": "",
        "lock_in_cost": "",
    },
    # TODO(ex2-②): 再加至少一行你自己的维度（同样的四列结构，照上面的行抄形状）
]
