"""探究文件 B：导入 A（会触发 A 的顶层代码执行），再打印自己与 A 的模块名。"""

import probe_a

print(f"probe-b: __name__ = {__name__}")
print(f"probe-b: sees probe_a.__name__ = {probe_a.__name__}")

if __name__ == "__main__":
    print("probe-b: main branch")
