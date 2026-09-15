"""探究文件 C：导入 B（B 又导入 A，形成两层导入链），自己作为入口被直接运行。"""

import probe_b

print(f"probe-c: __name__ = {__name__}，我 import 了 {probe_b.__name__}")

if __name__ == "__main__":
    print("probe-c: main branch")
