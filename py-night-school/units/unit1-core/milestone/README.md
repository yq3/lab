# Unit 1 里程碑：async 并发 fetcher（学段结业项目）

> 任务书 + 验收。没有六段式讲义——到这里，讲义是多余的：**零件前面九课全铸好了，拼装是你的事**。
> 对应 CURRICULUM 结业自查第一条：「不查资料手写 async 并发 fetcher + retry 装饰器」。

## 场景（明线：报销域）

财务中台要出一份**全区域报销汇总**：5 个区域台账端点各有延迟，其中：

- **east 不稳定**：前 2 次调用抛 `TimeoutError`（模拟抖动），第 3 次成功——需要**重试**；
- **north 永远慢**：0.3s 才响应——需要**超时降级**（拿空台账、标记 DEGRADED，别拖垮整个汇总）；
- 端点有礼数：**同时最多 2 路请求**——需要**限流**。

这些设定全部内建在 `fetcher.py` 的 mock 层（`asyncio.sleep` + 内存数据，无网络依赖，不要改）。

## 任务（三个 TODO，全在 `fetcher.py`）

### T1 带参 retry 装饰器（综合考点：L1.5 装饰器 × L1.9 asyncio）

```python
@retry(max_retries=2, exceptions=(TimeoutError,))
async def fetch_region_with_retry(region: str) -> list[int]: ...
```

比 L1.5 的同步版多两层，骨架已给好，你只填最里层 `wrapper` 的重试循环：

```python
def retry(max_retries, exceptions):  # 第 1 层：收参数（带参装饰器工厂）
    def decorator(func):  # 第 2 层：收函数
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):  # 第 3 层：必须是 async def——里面要 await func
            ...  # <- 你的重试循环

        return wrapper

    return decorator
```

语义：最多调用 `1 + max_retries` 次；命中 `exceptions` 则重试，耗尽抛最后一个异常；成功返回结果。
**设计考点**：`wait_for` 的取消是 `CancelledError`（`BaseException` 子类，L1.9 讲过）——你的 `except`
只点名 `exceptions`，取消就会原样放行，T2 的超时机制才不会被重试逻辑误吞。

### T2 超时降级

`fetch_region_guarded(region)`：用 `asyncio.wait_for` 给重试链套 `FETCH_TIMEOUT` 预算；
超时捕获 `TimeoutError`，返回 `([], True)`（空台账 + 降级标记）；正常返回 `(结果, False)`。

### T3 限流并发 + 汇总报告

`collect_all()`：`asyncio.Semaphore(MAX_CONCURRENCY)` 限流下并发拉取全部区域，产出
`Summary`（按 `REGIONS` 保序）。状态三态：降级 → `"DEGRADED"`；发生过重试（`call_count(region) > 1`）→
`"RETRY_OK"`；否则 `"PASS"`。

## 实现提示

- 卡住先想 10 分钟，再看三级渐进提示（每次只看一级）：

  ```bash
  cd units/unit1-core/milestone
  uv run python -c "from hints import hint; print(hint('t1', 1))"
  ```

- 手动看效果：`uv run python fetcher.py`（演示入口已给，跑一次打印结构化报告）；
- 零额外依赖：mock 端点是 `asyncio.sleep` + 内存数据；测试不用 pytest-asyncio——
  验收测试本身就是「同步 test 函数 + `asyncio.run` 包异步断言」的模板示范（L1.8 §4）。

## 验收（全部绿 = Unit 1 结业）

`tests/test_fetcher.py`（不要改）从 mock 观测仪表取证，六条断言：

| 测试 | 断什么 |
|---|---|
| `test_result_completeness` | 5 区域齐全保序；各区域单据数 / 金额合计（整数分）/ 总计正确 |
| `test_retry_happened_on_flaky_only` | east 被调用 3 次（抖 2 次成 1 次）；稳定端点只调 1 次 |
| `test_degraded_marked_for_slow_region` | north 状态 `DEGRADED`、空结果、0 金额 |
| `test_status_kinds` | east `RETRY_OK`、其余 `PASS`——三态各就各位 |
| `test_peak_concurrency_capped` | 峰值并发 ≤ 2 且 ≥ 2（限流真生效、并发真发生） |
| `test_total_elapsed_within_budget` | 总时长 < 0.40s（全串行约 0.60s——north 0.30 + east 重试共 0.07（0.01×2 抖动 + 0.05 成功）+ 其余端点 0.23，不并发过不了关） |

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

三条同时全绿，回到 [unit1-core/README.md](../README.md) 把里程碑打卡，然后进 Unit 2。

## 目录

```
milestone/
├── README.md            # 本任务书
├── fetcher.py           # 你的实现（三个 TODO；mock 层与仪表给定，不要改）
├── hints.py             # 三级渐进提示（t1/t2/t3）
├── tests/test_fetcher.py # 验收（不要改本文件）
└── solution/fetcher.py  # 参考答案（完成前别看）
```

## 离毕业又近的一块

这个 fetcher 就是毕业设计执行层「**并发取数 + 重试 + 超时降级 + 限流**」的完整雏形：
L5.1 的执行器把它从 mock 端点换成真实的 LLM API 与工具调用，四件韧性机制原样保留——
到那时你会发现毕设的执行层没有新零件，全是今天这套的参数化重演。
