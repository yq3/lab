"""断点调试初体验——夜校承诺的「断点调试一次」（对照 IDEA 的红点）。

运行：uv run python code/debug_demo.py
程序会在 breakpoint() 处暂停并进入 pdb（Python 内置调试器，零安装）。
pdb 常用命令：n=单步跳过(Step Over)  s=步入(Step Into)  c=继续(Resume)
            p 变量名=求值(Evaluate)  q=退出(Stop)
"""

from budget import preapprove

breakpoint()  # 断点：等价于 IDEA 里点的红点
result = preapprove([1200, 8800])
print(f"预审结果：{result}")
