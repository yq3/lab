"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

import ex3_coroutine_fates as ex3


def test_ex3_three_fates() -> None:
    observed = ex3.demo_fates("CLM-001")
    # 归宿 0（对照）：只调用不执行——拿到的是协程对象
    assert observed["type"] == "coroutine"
    # 归宿一：被 await（经 asyncio.run 驱动的帮手协程）
    assert observed["await"] == "PASS:CLM-001"
    # 归宿二：被 asyncio.run 直接驱动
    assert observed["run"] == "PASS:CLM-001"
