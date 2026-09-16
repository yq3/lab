# solution/ —— Unit 5 里程碑参考答案

覆盖用法（三态验证的毕业态自动做，手动看 diff 时）：

```bash
cp solution/graduation_checks.py graduation_checks.py
uv run pytest
```

- `graduation_checks.py`：三颗取证钉子的完整版——assert_stream_tail（type 末尾对齐
  expected_tail + seq 全程 0..N-1 连续）、assert_hash_rotated（两指纹非空且互异，A6）、
  assert_zero_payments（日历聚合上 payment.executed 过滤读出空列表）。覆盖后三/四张
  链路测试转绿，与毕业态镜像同构。
- `JAVA-MAPPING.md`：4 行 TODO(毕业) 占位的完整对照版（L5.4 对照答案原样迁入，Java API
  名沿用 L5.4 已核实版本——不新增未核实断言）。**不走覆盖**（三态的 solution 覆盖只
  glob `*.py` 到目录根）：tests/test_mapping_meta.py 对它做的是「占位行必须有完成版
  对照」的结构把关（先例 Unit 3 milestone 笔记）——你填完根文档的 4 行后，两版 diff
  才是你的认知增量清单。
