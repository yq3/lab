"""主 agent 的 state_schema 与 context_schema 扩展。

- TaxMainState：在 deepagents 内置状态上追加业务缓存字段（state_schema 参数）
- TaxContext：企业会话上下文（context_schema 参数）——操作员身份由平台注入，
  工具经 runtime.context 读取，模型无法伪造身份
"""

from __future__ import annotations

from typing import TypedDict

from deepagents.graph import DeepAgentState


class TaxMainState(DeepAgentState, total=False):
    """主 agent 状态 = deepagents 内置（messages/files/todos…）+ 业务扩展。"""

    last_tax_result: str
    """最近一次计税结论的 JSON 文本（save_calc_result 工具写入，申报委派时引用）。"""


class TaxContext(TypedDict):
    """企业会话上下文：CLI 启动时注入（invoke(context=...)）。"""

    operator: str
    """操作员工号（企业税务专员）。"""
    taxpayer_id: str
    """在办纳税人编号。"""
