"""检查员队伍——观点的生成器（对版 hedge_fund/signals/）。

对版关系（机制抽取，不是抄域）：

    AlphaModel（ABC，signals/base.py）   -> Reviewer（ABC）
    LLMAgent（signals/llm_agent.py）      -> LLMCheckerBase
    buffett.py 等 5 个人格                -> ComplianceReviewer / BudgetReviewer / InvoiceReviewer
    PEADModel（signals/pead.py，纯数学）  -> RuleChecker（纯 Python 规则表，零 LLM）

产品的关键设计在夜校原样成立：LLM 人格与量化模型实现**同一个 ABC**，
对引擎（blend）完全可互换——「人格 = 一个 name + 一段 system prompt」，
其余机制（缓存→调用→解析→弃权）全部在基类。

失败契约（对版 llm_agent.py 的 locked decisions）：
- 数据层错误向上传播（fail loud——坏快照绝不能静默变成中性票）；
- LLM 调用/解析失败 → 弃权（score=0.0，metadata.abstained=True），
  且未解析的原始响应留盘（cache 的 parse_error 职责）；
- LLM 影响力终止于 Vote：检查员不接触金额处置（limits）与最终建议（pipeline 的纯函数）。
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

import httpx

from cache import DecisionCache, decision_key
from review import Vote
from snapshot import ITEM_LIMIT_CENTS, ClaimSnapshot

# 模型必须返回的立场；折进 Vote.score 的符号（对版 _SIGNAL_TO_SIGN）
_STANCE_TO_SIGN = {"support": 1.0, "oppose": -1.0, "abstain": 0.0}


def extract_json(text: str) -> dict:
    """从模型回复里抠出第一个 JSON 对象（对版 llm/client.py#extract_json，三级尝试）。

    ```json fence -> 整串 -> 首个配平的 {...}；全部失败抛 ValueError。
    产品刻意不用框架的 structured-output：自己要 JSON、自己解析、失败自己弃权。
    """
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError(f"no parseable JSON in response: {text[:80]!r}")


class HttpClient:
    """轻量模型客户端（对版产品的 LLMClient 协议 + ChatLLM 实现）。

    产品的协议面只有一个方法 complete(system, user) -> str——传输层是谁、
    哪家厂商，检查员一概不知。本课离线指向 MockLLMEndpoint（L2.3 服役至今的替身），
    真实端点时换 base_url 即可，检查员代码零改动。
    """

    def __init__(self, base_url: str, api_key: str = "test-key", model: str = "mock-model") -> None:
        self.model = model
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        response = httpx.post(self._url, json=payload, headers=self._headers, timeout=10)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class Reviewer(ABC):
    """检查员抽象基类（对版 AlphaModel）：只形成观点，返回一票。

    注意产品这里用 ABC 而不是 Protocol（§2 的对照点）：模型注册表在运行时
    枚举全部实现、基类还携带共享机制（LLMCheckerBase 的缓存与解析），
    名义子类型是自然选择；传输层的 LLMClient 反而是 Protocol——
    「IS-A 层级用 ABC，只关心能不能调用用 Protocol」，Java 的 abstract class vs interface 同款直觉。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """检查员标识（如 'compliance' / 'rules'）——合成权重表的 key。"""
        ...

    @abstractmethod
    def review(self, snapshot: ClaimSnapshot) -> Vote:
        """对一张报销单的时点快照投票。"""
        ...


class LLMCheckerBase(Reviewer):
    """LLM 人格检查员的基类（对版 LLMAgent）：机制全在这里，人格只是 prompt。

    流程（与产品 predict 逐段对版）：查缓存 -> miss 才调模型 -> extract_json 解析
    -> 校验 stance/confidence -> Vote；任何一步失败即弃权。
    """

    def __init__(self, client: HttpClient, cache: DecisionCache) -> None:
        self._client = client
        self._cache = cache

    # ---- Reviewer 接口 ----

    def review(self, snapshot: ClaimSnapshot) -> Vote:
        system = self.get_system_prompt()
        user = snapshot.render()
        key = decision_key(self.name, self._client.model, system, user)

        cached = self._cache.get(key)
        if cached is not None and "parsed" in cached:
            return self._to_vote(snapshot, cached["parsed"], key, cached=True)

        try:
            response = self._client.complete(system, user)
        except Exception as exc:  # 传输失败 -> 弃权（对版：abstain，不是 raise）
            return self._abstain(snapshot, f"LLM call failed: {exc}")

        record = {
            "checker": self.name,
            "model": self._client.model,
            "claim_id": snapshot.claim_id,
            "claim_hash": snapshot.content_hash,
            "system": system,
            "user": user,
            "response": response,
        }

        try:
            parsed = self._parse(response)
        except Exception as exc:
            # 解析失败也留盘——调试踪迹（对版 debug trail）
            self._cache.put(key, {**record, "parse_error": str(exc)})
            return self._abstain(snapshot, f"parse failed: {exc}")

        self._cache.put(key, {**record, "parsed": parsed})
        return self._to_vote(snapshot, parsed, key, cached=False)

    # ---- 子类表面：人格 = name + system prompt ----

    def get_system_prompt(self) -> str:
        """人格本体——每个子类必须定义自己的声音（对版 get_system_prompt）。"""
        raise NotImplementedError(f"{type(self).__name__} must define get_system_prompt()")

    # ---- 私有机械 ----

    def _parse(self, response: str) -> dict:
        """抽取并校验 {stance, confidence, reasoning}（对版 _parse）。"""
        data = extract_json(response)
        stance = str(data.get("stance", "")).lower()
        if stance not in _STANCE_TO_SIGN:
            raise ValueError(f"invalid stance {data.get('stance')!r}")
        confidence = float(data.get("confidence", 0))
        if not 0 <= confidence <= 100:
            raise ValueError(f"confidence out of range: {confidence}")
        return {"stance": stance, "confidence": confidence, "reasoning": str(data.get("reasoning", ""))}

    def _to_vote(self, snapshot: ClaimSnapshot, parsed: dict, key: str, cached: bool) -> Vote:
        score = _STANCE_TO_SIGN[parsed["stance"]] * parsed["confidence"] / 100.0
        return Vote(
            checker=self.name,
            claim_id=snapshot.claim_id,
            score=score,
            reasoning=parsed["reasoning"],
            metadata={
                "stance": parsed["stance"],
                "confidence": parsed["confidence"],
                "model": self._client.model,
                "prompt_key": key,
                "claim_hash": snapshot.content_hash,
                "cached": cached,
                "abstained": False,
            },
        )

    def _abstain(self, snapshot: ClaimSnapshot, reason: str) -> Vote:
        return Vote(
            checker=self.name,
            claim_id=snapshot.claim_id,
            score=0.0,
            reasoning=f"abstained: {reason}",
            metadata={"abstained": True, "abstain_reason": reason, "cached": False},
        )


class ComplianceReviewer(LLMCheckerBase):
    """合规检查员——审「这笔钱该不该花」（对版 buffett.py：人格即 system prompt）。"""

    @property
    def name(self) -> str:
        return "compliance"

    def get_system_prompt(self) -> str:
        return """你是财务合规检查员，评估一张报销单是否违反报销政策。

按你的检查清单走：
1. 事由与明细是否相符——客户拜访配工作餐合理，展会采购配物料合理；
2. 明细金额是否超过单笔上限 5000 分（50 元），超出即违反餐标/采购标；
3. 明细是否含非正数金额——负数或零是录入错误或冲账痕迹，数据可疑；
4. 报销人、部门与事由是否存在明显矛盾。

立场规则：
- support：各项检查都过得去。
- oppose：任一硬性政策被违反（单笔超标、明细异常）。
- abstain：信息不足以判断。

置信度（0-100）：90-100 证据确凿；70-89 明确；40-69 存疑；10-39 纯猜测。

硬规则：
- 只根据给出的数据推理，不要发明数字。
- 数据不足以判断时，明说并弃权。

只输出 JSON，严格按此 schema：
{"stance": "support" | "oppose" | "abstain", "confidence": <0-100>,
 "reasoning": "<2-3 句中文说明>"}"""


class BudgetReviewer(LLMCheckerBase):
    """预算检查员——审「这笔钱花不花得起」。"""

    @property
    def name(self) -> str:
        return "budget"

    def get_system_prompt(self) -> str:
        return """你是部门预算检查员，评估一张报销单对部门预算的压力。

按你的检查清单走：
1. 单据总额与部门剩余预算的差距——贴线（超过剩余的 80%）就要警惕；
2. 总额是否已经超过剩余预算——那是硬性超支；
3. 若明细含负数（冲账/录入错误），预算视角无法给出可靠意见。

立场规则：
- support：总额远低于剩余预算，无超支风险。
- oppose：总额超过剩余预算，或贴线且事由非必要。
- abstain：数据异常（如负数总额）无法评估。

置信度（0-100）：90-100 证据确凿；70-89 明确；40-69 存疑；10-39 纯猜测。

硬规则：
- 只根据给出的数据推理，不要发明数字。
- 数据不足以判断时，明说并弃权。

只输出 JSON，严格按此 schema：
{"stance": "support" | "oppose" | "abstain", "confidence": <0-100>,
 "reasoning": "<2-3 句中文说明>"}"""


class InvoiceReviewer(LLMCheckerBase):
    """发票检查员——审「凭据是否站得住」。"""

    @property
    def name(self) -> str:
        return "invoice"

    def get_system_prompt(self) -> str:
        return """你是发票检查员，评估报销单关联发票的凭证效力。

按你的检查清单走：
1. 发票校验结果——已作废、连号重开、抬头不符都是硬伤；
2. 发票校验未通过时，无论金额多合理都不能作为报销凭据；
3. 校验通过时，关注发票与事由的匹配度（工作餐配餐饮发票）。

立场规则：
- support：发票有效且与事由匹配。
- oppose：发票校验未通过，或与事由明显不符。
- abstain：发票信息缺失无法核验。

置信度（0-100）：90-100 证据确凿；70-89 明确；40-69 存疑；10-39 纯猜测。

硬规则：
- 只根据给出的数据推理，不要发明数字。
- 数据不足以判断时，明说并弃权。

只输出 JSON，严格按此 schema：
{"stance": "support" | "oppose" | "abstain", "confidence": <0-100>,
 "reasoning": "<2-3 句中文说明>"}"""


# 规则码 -> 人类可读说明（回执与 advice.reason 的口径）
RULE_TEXT = {
    "INVALID_AMOUNT": "明细含非正数金额，数据可疑",
    "ITEM_OVER_LIMIT": f"存在超过单笔上限 {ITEM_LIMIT_CENTS} 分的明细",
    "INVOICE_INVALID": "关联发票校验未通过",
    "BUDGET_EXCEEDED": "总额超过部门剩余预算",
    "PASS": "五条硬规则全部未命中",
}


class RuleChecker(Reviewer):
    """量化检查员——纯 Python 规则表，零 LLM（对版 PEADModel）。

    与 LLM 人格同一个 ABC、对 blend 完全可互换：产品的「量化模型与投资人格
    混编成一个 strategy」在这里是「规则表与 LLM 人格混编成一队检查员」。
    规则表先命中先停（Unit 3 review_rules 同源）。
    """

    @property
    def name(self) -> str:
        return "rules"

    def rule_code(self, snapshot: ClaimSnapshot) -> str:
        """规则表判定（纯函数）——pipeline 的决策门也用同一份口径。"""
        if any(cents <= 0 for cents in snapshot.items.values()):
            return "INVALID_AMOUNT"
        if any(cents > ITEM_LIMIT_CENTS for cents in snapshot.items.values()):
            return "ITEM_OVER_LIMIT"
        if not snapshot.invoice_valid:
            return "INVOICE_INVALID"
        if snapshot.total_cents > snapshot.remaining_cents:
            return "BUDGET_EXCEEDED"
        return "PASS"

    def review(self, snapshot: ClaimSnapshot) -> Vote:
        code = self.rule_code(snapshot)
        if code == "PASS":
            score, reasoning = 0.85, RULE_TEXT[code]
        else:
            score, reasoning = -0.95, RULE_TEXT[code]
        return Vote(
            checker=self.name,
            claim_id=snapshot.claim_id,
            score=score,
            reasoning=reasoning,
            metadata={"rule_code": code, "abstained": False, "cached": False},
        )
