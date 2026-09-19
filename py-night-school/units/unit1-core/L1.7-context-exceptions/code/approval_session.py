"""with 协议最小实现——「审批会话」：__enter__ 开事务，__exit__ 决定 commit/rollback。

运行本文件：
    uv run python code/approval_session.py
"""

from types import TracebackType


class ApprovalSession:
    """用类实现上下文管理器：实现 __enter__ / __exit__ 两个方法即可被 with。"""

    def __init__(self, claim_id: str, log: list[str] | None = None) -> None:
        self.claim_id = claim_id
        self.log = log if log is not None else []

    def __enter__(self) -> "ApprovalSession":
        self.log.append(f"BEGIN {self.claim_id}")  # 对应 try-with-resources 里资源获取成功
        return self  # as 后面拿到的就是它

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if exc_type is None:
            self.log.append(f"COMMIT {self.claim_id}")  # with 体正常结束：提交
        else:
            self.log.append(f"ROLLBACK {self.claim_id}")  # with 体抛了异常：回滚
        return False  # False：不吞异常，让它继续向上传播（返回 True 才吞，见 SwallowingSession）


class SwallowingSession(ApprovalSession):
    """冷知识演示：__exit__ 返回 True 会吞掉 with 体内的一切异常。"""

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        super().__exit__(exc_type, exc_value, traceback)
        return True  # 「无论出什么事都当没发生」——生产代码几乎不该这么写，但要知道机制


if __name__ == "__main__":
    log: list[str] = []

    # 正常路径：BEGIN -> COMMIT
    with ApprovalSession("CLM-2026-0001", log) as session:
        print(f"会话中处理: {session.claim_id}")
    print(log)

    # 异常路径：BEGIN -> ROLLBACK，且异常继续向外传播（被我们在外面接住）
    try:
        with ApprovalSession("CLM-2026-0002", log):
            raise ValueError("金额为负")  # 模拟体内出事
    except ValueError as exc:
        print(f"异常逃出了 with 块（这是对的）: {exc}")
    print(log)

    # 吞异常路径：ROLLBACK 之后异常被吞，外面毫无知觉
    with SwallowingSession("CLM-2026-0003", log):
        raise ValueError("你将看不到我")
    print(log)  # ROLLBACK CLM-2026-0003——异常消失了
