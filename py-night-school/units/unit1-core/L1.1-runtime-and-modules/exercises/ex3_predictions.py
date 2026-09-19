# 练习 3（单变量编辑约束：只改本文件的 "??" 占位，其余不要动）
"""__name__ 探究——先在纸上预测，再让 test_ex3.py 重放命令对答案。

三个命令（都在 exercises/ 目录下执行；验收测试会原样重跑）：
  A. uv run python probe_a.py
  B. uv run python -c "import probe_b"
  C. uv run python probe_c.py

把你预测的完整 stdout 逐行（含顺序、含空格）填进下表。提示：
import 会执行整个被导入文件（print 是真的会打出来），但 __main__ 分支
只在「被直接运行的那个文件」里进。
"""

PREDICTED_OUTPUTS: dict[str, list[str]] = {
    "A_run_probe_a_directly": ["??"],  # TODO(ex3)
    "B_import_probe_b": ["??"],  # TODO(ex3)
    "C_run_probe_c_directly": ["??"],  # TODO(ex3)
}
