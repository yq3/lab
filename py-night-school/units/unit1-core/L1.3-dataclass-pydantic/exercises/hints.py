"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "改写类 = 把 __init__ 的 self.x = x 换成「字段名: 类型」的类体声明；"
        "__repr__ / __eq__ 一个都不用写——@dataclass 自动生成。",
        "形状：@dataclass 装饰 + 类体三行「description: str」「amount_cents: int」「tags: ...」；"
        "注意前两个无默认值、tags 有默认值时的声明顺序。",
        "tags 那行是唯一难点：裸 = [] 会被 dataclass 拒（ValueError），正确姿势是"
        "「tags: list[str] = field(default_factory=list)」，"
        "并在文件顶部 import 处补上 field（from dataclasses import dataclass, field）。",
    ],
    "ex2": [
        "三个约束对应三种 Field 参数：格式用 pattern（正则）、数值范围用 gt/le、字符串非空用 min_length；"
        "非法样本表挑「格式错 / 太小 / 太大 / 空串」各来一发。",
        '字段形状：receipt_no: str = Field(pattern=r"^RCP-\\d{4}-\\d{6}$")；'
        "amount_cents: int = Field(gt=0, le=5000)；payer: str = Field(min_length=1)。"
        "import 行记得补 Field。",
        '样本表示例：("receipt_no", {"receipt_no": "RCP-26-1", "amount_cents": 100, "payer": "美团"})、'
        '("amount_cents", {"receipt_no": "RCP-2026-000001", "amount_cents": 5001, "payer": "美团"})、'
        '("payer", {"receipt_no": "RCP-2026-000001", "amount_cents": 100, "payer": ""})——'
        "注意 kind 必须与真实违规字段一致，meta-test 会查三字段覆盖、≥4 组、不重复。",
    ],
    "ex3": [
        "ex3a 抄 ClaimBatch 的 batch_id 写法即可；"
        'ex3b 先建一个空列表，for 每行 split("|") 解包成两段，append 一个 ClaimItem，最后 return cls(...)。',
        'ex3b 骨架：items = []; for line in lines: category, amount = line.split("|");'
        " items.append(ClaimItem(category=category, amount_cents=int(amount)));"
        " return cls(report_id=report_id, submitted_by=submitted_by, items=items)。",
        "完整实现就是骨架四行；类目空串与负数金额不用任何 if——ClaimItem 的 min_length/gt=0 "
        "会在 cls(...) 构造那一刻替你拒（这正是「校验发生在哪一刻」的体感）；"
        '没有 | 的行由「category, amount = line.split("|")」解包失败自然抛 ValueError。',
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
