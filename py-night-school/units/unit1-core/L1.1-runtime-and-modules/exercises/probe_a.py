"""探究文件 A：打印自己被加载时的 __name__，并演示 __main__ 分支的进出。"""

print(f"probe-a: __name__ = {__name__}")

if __name__ == "__main__":
    print("probe-a: main branch")
