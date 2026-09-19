"""参考答案（ex3）——三个场景的真实 stdout 逐行誊写。"""

PREDICTED_OUTPUTS: dict[str, list[str]] = {
    "A_run_probe_a_directly": [
        "probe-a: __name__ = __main__",
        "probe-a: main branch",
    ],
    "B_import_probe_b": [
        "probe-a: __name__ = probe_a",
        "probe-b: __name__ = probe_b",
        "probe-b: sees probe_a.__name__ = probe_a",
    ],
    "C_run_probe_c_directly": [
        "probe-a: __name__ = probe_a",
        "probe-b: __name__ = probe_b",
        "probe-b: sees probe_a.__name__ = probe_a",
        "probe-c: __name__ = __main__，我 import 了 probe_b",
        "probe-c: main branch",
    ],
}
