"""__name__ 双身份演示——同一个文件，两种启动方式，两种身份。

直接运行：uv run python demo_name.py        （在 code/ 目录下）
被导入运行：uv run python -c "import demo_name"

注意顶层的 print：import 会「执行」整个模块文件（顶到底跑一遍），
所以两种方式都会打印第一行；但 __main__ 分支只有直接运行才会进。
"""

print(f"demo_name 模块正在被加载，此刻 __name__ == {__name__!r}")


def identity() -> str:
    """把自己被加载时的模块名交出去，方便别人检查。"""
    return __name__


if __name__ == "__main__":
    print("→ 我是入口（直接运行），走进了 __main__ 分支")
else:
    print("→ 我是被导入的，__main__ 分支不会执行")
