# langgraph checkpoint 体系深挖档案（迁移化石 / SQL 原文 / 写入时序 / conformance / 借鉴意义）

> agent-persistence 轮补充深挖（单对象）。基线：~/develop/opensource/langgraph @ e539ac122f（只读）。定位：`dimensions/02-执行状态与checkpoint.md` §1 已给三表 DDL/serde 分流/BaseStore DDL 的结论级摘要，本文下挖到 **SQL 原文 / 迁移化石 / 写入时序 / conformance 契约** 级，不重复 §1 的横向对比。证据格式：仓库相对路径`:行号`或`#符号`。

## 1. 迁移化石史：PG 9 条迁移逐条解剖

`libs/checkpoint-postgres/langgraph/checkpoint/postgres/base.py:43-91`，`MIGRATIONS` 列表位置即版本号（`:39-42` 注释明言 append-only），`setup()` 从 `checkpoint_migrations(v)` 表读最大 v 后顺序补跑（`postgres/__init__.py:85-110`）。

| v | 内容 | 加了什么 | 背后推断的兼容问题 |
|---|---|---|---|
| 0 | `checkpoint_migrations(v PK)` | 版本表本身 | 无迁移机制的裸表时代终结 |
| 1 | `checkpoints` 表 | thread_id/ns/id/parent/type/checkpoint JSONB/metadata JSONB | 初始形态即 JSONB 双列 + 三列复合 PK |
| 2 | `checkpoint_blobs` 表 | `(thread_id, ns, channel, version)` PK + type + blob BYTEA | 当前文本 `blob BYTEA` **无 NOT NULL**（`:63`）——注意这是后来改写的文本（见 v4） |
| 3 | `checkpoint_writes` 表 | 五列 PK `(thread_id, ns, checkpoint_id, task_id, idx)` | |
| 4 | `ALTER TABLE checkpoint_blobs ALTER COLUMN blob DROP not null` | 允许 blob 为 NULL | **化石点 1**：`_dump_blobs`（`base.py:566-568`）对「版本存在但值不在本 checkpoint」写 `("empty", None)` 墓碑行——NOT NULL 会让墓碑写不进去。旧库已执行过带 NOT NULL 的 v2（迁移不可重跑），只能追加 v4 抹掉；新装库跑的是改写后的 v2 文本，v4 对它是 no-op |
| 5 | `SELECT 1;` | 什么都不做 | **化石点 2**：`:78-79` 注释自认「曾加入一条空迁移导致版本号错位」，此条用于对齐版本表——一次发布事故的化石 |
| 6/7/8 | 三条 `CREATE INDEX CONCURRENTLY ... ON *(thread_id)` | checkpoints/blobs/writes 各一个 thread_id 单列索引 | **化石点 3**：`list()`/`delete_thread()` 都按 `WHERE thread_id = %s` 打三张表（`__init__.py:390-402`）；CONCURRENTLY 不锁表，说明是大存量线上库的在线加索引 |
| 9 | `checkpoint_writes ADD COLUMN task_path TEXT NOT NULL DEFAULT ''` | 写入行携带任务路径 | **化石点 4**：`SELECT_PENDING_SENDS_SQL` 靠 `ORDER BY task_path, task_id, idx`（`base.py:120-129`）恢复 Send 的确定序——task_id 是随机 UUID，并行任务间无拓扑序，task_path（父任务路径前缀）才是拓扑序。有默认值 = 无锁加列 + 旧行语义降级但不炸 |

**Store 侧迁移**（独立版本表 `store_migrations`，`store/postgres/base.py:63-90`）：v0 建表 → v1 `prefix text_pattern_ops` btree（前缀 LIKE 可走索引）→ v2 `ADD COLUMN expires_at + ttl_minutes`（**TTL 是后补功能**）→ v3 `expires_at` 部分索引（只为有 TTL 的少数行建索引）。**向量迁移**另一张版本表 `vector_migrations`（`:92-145`）：v0 `CREATE EXTENSION vector` → v1 `store_vectors(embedding %(vector_type)s(%(dims)s))`，vector_type 支持 `halfvec` 半精度 → v2 ANN 索引，kind/参数经 `_get_index_params` 白名单消毒防 DDL 注入（`:1237-1275`：kind∈{hnsw,ivfflat,flat}，参数强转 int、flat 则跳过建索引）。

## 2. 完整 SQL 读路径

### 2.1 主装配查询 SELECT_SQL（`base.py:93-118`，二进制游标）

```sql
select thread_id, checkpoint, checkpoint_ns, checkpoint_id, parent_checkpoint_id, metadata,
  ( select array_agg(array[bl.channel::bytea, bl.type::bytea, bl.blob])
    from jsonb_each_text(checkpoint -> 'channel_versions')
    inner join checkpoint_blobs bl
        on bl.thread_id = checkpoints.thread_id
        and bl.checkpoint_ns = checkpoints.checkpoint_ns
        and bl.channel = jsonb_each_text.key
        and bl.version = jsonb_each_text.value ) as channel_values,
  ( select array_agg(array[cw.task_id::text::bytea, cw.channel::bytea, cw.type::bytea, cw.blob]
                     order by cw.task_id, cw.idx)
    from checkpoint_writes cw
    where cw.thread_id = checkpoints.thread_id
        and cw.checkpoint_ns = checkpoints.checkpoint_ns
        and cw.checkpoint_id = checkpoints.checkpoint_id ) as pending_writes
from checkpoints
```

要点：**版本表驱动重装配**——`jsonb_each_text(checkpoint->'channel_versions')` 把版本图展开成 (channel, version) 行，与 blobs 表 PK 精确内连；未变通道自动命中旧版本 blob 行（跨 checkpoint 零拷贝复用的读侧根基）。`array[bytea,...]` 一次行传输（配合 `conn.cursor(binary=True)`，`__init__.py:419`）；`_load_blobs` 丢弃 `type='empty'` 墓碑（`base.py:375-384`）；pending_writes 旁路子查询按 `(task_id, idx)` 排序、最终 merge 成 `{**inline_values, **blobs}`（`__init__.py:579-584`）。

### 2.2 get_tuple / list 的外层谓词

- get_tuple（`__init__.py:230-235`）：有 checkpoint_id → `WHERE thread_id=%s AND checkpoint_ns=%s AND checkpoint_id=%s`；无 → `... ORDER BY checkpoint_id DESC LIMIT 1`（uuid6 单调可排序是隐含前提）。
- list（`:152-157`）：`_search_where`（`base.py:624-666`）拼 `metadata @> %s::jsonb`（JSONB 包含语义过滤）+ `checkpoint_id < %s`（before 游标）+ `ORDER BY checkpoint_id DESC [LIMIT n]`。

### 2.3 Send 通道旁路 SELECT_PENDING_SENDS_SQL（`base.py:120-129`）

```sql
select checkpoint_id, array_agg(array[type::bytea, blob] order by task_path, task_id, idx) as sends
from checkpoint_writes
where thread_id = %s and checkpoint_id = any(%s) and channel = '__pregel_tasks'
group by checkpoint_id
```

仅在读路径遇到 `checkpoint.v < 4` 的**旧格式 checkpoint** 时触发（`__init__.py:247-259`）：v4 之前 pending sends 存在父 checkpoint 的 `__pregel_tasks` 写入行里，读取时捞回、`_migrate_pending_sends`（`base.py:355-373`）重组进 channel_values 并补 max+1 版本号——**一次 schema 语义变更被做成了读时惰性迁移**，避免一次性刷库。

### 2.4 DeltaChannel 两阶段查询（PG override）

`get_delta_channel_history`（`__init__.py:444-557`）：

- **Stage 1**（`_build_delta_stage1_sql`，`base.py:201-290`）：分页（`_DELTA_PAGE_SIZE=1024`）扫 checkpoints，每通道三列动态拼接：`checkpoint->'channel_versions'->>%s` 版本列 + `EXISTS(checkpoint_blobs ... type<>'empty')` 探针 + 行内值列；Python 侧 `_try_advance_walks`（`:413-469`）走 parent 链，**blob 优先于 inline**——`_DeltaSnapshot` 弹出后行内只剩 `True` 标记（`:243-253` 注释详述：只测 channel_values 键会漏「存进 blob 的纯值」，只测 blobs 会漏行内标量，两探测缺一不可）。
- **Stage 2**（`_build_delta_stage2_sql`，`:293-335`）：按通道 UNION ALL——每链一条 `checkpoint_writes WHERE channel=%s AND checkpoint_id = ANY(%s)` 分支 + 每种子一条 `checkpoint_blobs WHERE channel=%s AND version=%s` 分支，单往返取齐。
- 文件内自带实测对比注释（`:175-199`）：动态列方案 vs 整块 ship channel_versions/values，端到端 **2.28ms vs 6.83ms（3 倍）、线上载荷 61% 更小**，胜因是避开 wire 上的 JSONB 序列化。

## 3. 写路径全序列

### 3.1 put 分流（`postgres/__init__.py:309-344`）

```
for k, v in checkpoint["channel_values"].items():
  isinstance(v, _DeltaSnapshot) → 弹出进 blob_values；行内 channel_values[k] = True（哨兵标记）
  v is None / str / int / float / bool → 留 JSONB 行内
  其他一切 → 弹出进 blob_values
```

随后 `blob_versions = {k: v for k,v in new_versions.items() if k in blob_values}`（`:322-324`）——**只有本超步版本变更的通道才写 blob 行**；未变通道不写，读侧靠版本表 join 到旧 blob。两条 SQL 在一个 pipeline 事务里执行：

```sql
-- blobs：幂等去重（base.py:131-135）
INSERT INTO checkpoint_blobs (thread_id, checkpoint_ns, channel, version, type, blob)
VALUES (...) ON CONFLICT (thread_id, checkpoint_ns, channel, version) DO NOTHING
-- checkpoints：重试覆盖（base.py:137-144）
INSERT INTO checkpoints (...) VALUES (...)
ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id)
DO UPDATE SET checkpoint = EXCLUDED.checkpoint, metadata = EXCLUDED.metadata;
```

语义分工：blob 按 `(channel, version)` 寻址，同版本重写（崩溃重放）静默跳过，天然防重复膨胀；checkpoint 行按 id 寻址、DO UPDATE 允许同一超步重试覆盖最新态。**没有 CAS/版本条件**——依赖单写者假设。

### 3.2 put_writes 去重（`__init__.py:347-379`）

```python
query = (UPSERT_CHECKPOINT_WRITES_SQL          # DO UPDATE
         if all(w[0] in WRITES_IDX_MAP for w in writes)
         else INSERT_CHECKPOINT_WRITES_SQL)    # DO NOTHING
```

`WRITES_IDX_MAP = {__error__:-1, __scheduled__:-2, __interrupt__:-3, __resume__:-4}`（`checkpoint/base/__init__.py:796`）——**特殊通道负 idx**，与常规写 0..n 永不撞键。选择规则：整批全是特殊通道 → `DO UPDATE`（**last-write-wins**，中断状态可覆盖）；含任何常规通道写 → `DO NOTHING`（**纯幂等去重**，任务重试不覆盖已落盘的业务写）。SQLite 版同构：`INSERT OR REPLACE` vs `INSERT OR IGNORE`（`sqlite/__init__.py:462-466`）。

### 3.3 task_path 的作用与上游内存侧

`_loop.py#put_writes`（:415-505）先在内存去重（特殊通道同通道 last-wins；NULL_TASK_ID 累积语义；删除本 task 旧写），`durability != "exit"` 时立刻 `submit(checkpointer.put_writes, config, writes, task_id, task_path)`；saver 是否接受 task_path 靠 `signature(put_writes).parameters.get("task_path")` 运行时探测（`:1520-1523`）——**契约向后兼容的接口探测模式**。task_path 唯一消费方就是 `SELECT_PENDING_SENDS_SQL` 的排序与 `_dump_writes` 落列（`base.py:590-611`）。

## 4. checkpoint 写入时机与 durability 三级

落盘点全在 `libs/langgraph/langgraph/pregel/_loop.py`：

| 触发 | source | 位置 |
|---|---|---|
| 线程首轮输入 / Command 输入 | `"input"` | `_first`→`_put_checkpoint({"source":"input"})`（`:1033`） |
| 时间旅行 fork | `"fork"` | `:968-971`（先清 stale INTERRUPT 写） |
| 每超步末（after_tick，apply_writes 之后） | `"loop"` | `:718` |
| loop 退出（`_suppress_interrupt`，ExitStack 栈顶） | 复用现有 metadata | `:1317-1334` |

`_put_checkpoint`（`:1081-1219`）内部分叉：

- `do_checkpoint = _checkpointer_put_after_previous is not None and (exiting or durability != "exit")`（`:1133-1135`）——**exit 模式中间步不落盘**，但每步仍照常 bump `counters_since_delta_snapshot` 并 `create_checkpoint`（channels=None 空转）。
- 退出调用以 `metadata is self.checkpoint_metadata` 对象身份判定，checkpoint id 未变则幂等跳过（恢复后无新步不重写）。
- 提交走 `self.submit(_checkpointer_put_after_previous, prev_fut, ...)` **future 链保序**（`:1202-1209`）——即使后台并发执行，checkpointer 看到的顺序也是超步序；put 前**先 drain `_delta_write_futs`**——可见性不变量：**祖先写入必须先于引用它们的 checkpoint 可见**。

durability 三级（`types.py:89`，默认 async）：

| 级别 | 中间 checkpoint | 中间 put_writes | 阻塞点 |
|---|---|---|---|
| sync | ✅ | ✅ | 每超步 `after_tick` 后 `result()` 阻塞（main.py:2987-2988） |
| async | ✅ | ✅ | 不等，future 链后台保序 |
| exit | ❌（仅计数器推进） | ❌（写入累积进 `_exit_delta_writes`） | loop 退出时三连落盘（`:1324-1334`） |

exit 模式特有机制：无持久父 checkpoint 时惰性造 **stub 空 checkpoint（step=-2）** 作锚点（`:1253-1281`）；累积的 delta 写按超步分组、用 `exit_delta_task_id(step, tid)`（`_checkpoint.py:39-47`，**把 step 编进 UUID 第一段**）合成 task_id，让 `ORDER BY task_id` 保持时间序且仍是合法 UUID。

## 5. serde：JsonPlusSerializer 细节

协议 = `dumps_typed(obj)->(type_tag, bytes)`（`serde/jsonplus.py:258-271`）：`None→("null",b"")`、bytes 直传、默认 `("msgpack", ormsgpack.packb(...))`，编码失败且 `pickle_fallback=True` 才 `("pickle", pickle.dumps)`；**读 pickle 同样要求 pickle_fallback=True**，旧 `"json"` tag 走 `json.loads(object_hook=self._reviver)`。

**ormsgpack ext code 分配表**（`:295-302`）：

| code | 用途 |
|---|---|
| 0 | EXT_CONSTRUCTOR_SINGLE_ARG（SecretStr/UUID/Decimal/set/Enum…） |
| 1 | EXT_CONSTRUCTOR_POS_ARGS（Path/re.Pattern/timedelta/Send…） |
| 2 | EXT_CONSTRUCTOR_KW_ARGS（namedtuple/dataclass/Item） |
| 3 | EXT_METHOD_SINGLE_ARG（仅 datetime.fromisoformat） |
| 4 / 5 | pydantic v1 / v2 |
| 6 | numpy array（零拷贝 memoryview） |
| **7** | **`_DeltaSnapshot`**——Delta 哨兵的持久层形态 |

**reviver（旧 json 格式兼容）**：`_reviver` 识别 `lc=2 + type=constructor` 信封；`method` 字段已被移除（GHSA-fjqc-hq36-qh5p 修复，`:186-191` 注释），BaseException 类拒活；`_check_allowed_json_modules`：SAFE_MSGPACK_TYPES 成员免检直过，其余必须显式 `allowed_json_modules`，**故意不支持前缀 allowlist**。

**安全边界三档**（`_msgpack.py`）：默认 permissive——未知类型 warn-once 后放行；`LANGGRAPH_STRICT_MSGPACK=true` 收紧为 ~40 个安全类型白名单；被拦类型**降级返回原始载荷 dict** 而非抛错。类文档明言：**攻击者能直写 checkpoint 库即可 RCE，serde 不是信任边界**（`:86-95`）。

## 6. DeltaChannel 持久层表示

- **非快照步**：`DeltaChannel.checkpoint()` 恒返回 `MISSING`（`channels/delta.py:193-202`）→ 不进 channel_values——**持久层表示就是「absence + 祖先 checkpoint_writes 行」**。
- **快照步**：`create_checkpoint` 对 `channels_to_snapshot` 中的通道写 `_DeltaSnapshot(ch.get())`（`_checkpoint.py:180-201`），PG put 弹入 blobs（msgpack ext 7）+ 行内 `True` 标记；exit 模式快照通道即使本步未写也**手动 bump 版本**，否则 blob 会被 `new_versions` 过滤掉静默丢失（`:186-200` 注释详述此 gap）。
- **双阈值**：`updates >= snapshot_frequency`（默认 1000，`delta.py:74`）**或** `supersteps >= DELTA_MAX_SUPERSTEPS_SINCE_SNAPSHOT`（默认 5000，env 可调）——后者兜底「不再被写的通道」的重放深度。**新线程首次 update_state 强制全量快照**（`_checkpoint.py:132-133`）。
- **读取路径**：发现通道缺失 → 批量 `saver.get_delta_channel_history` → `from_checkpoint(seed)` + `replay_writes`（**单次 reducer 调用喂全部回放写**——要求 reducer 批处理不变式；Overwrite 写是重置点）。reducer 需确定性 + 结合律（`delta.py:39-48` 文档契约）。

## 7. BaseStore 深挖（PostgresStore）

> 定位：BaseStore 是 langgraph 的**用户级记忆 / 跨线程长期状态存储底座**（namespace+key 文档模型 + 字段级向量检索）——「记忆用 PG」的直接先例。记忆视角的横向定位（介质谱系、与 markdown/LanceDB 流派对比、遗忘缺位）见 `dimensions/03-记忆存储.md` §4/§10；本文只挖实现层。

- **TTL 写**：put 时 `expires_at = NOW() + interval` + `ttl_minutes` 列（`store/postgres/base.py:360-375`）；upsert 冲突时一并 EXCLUDED 覆盖——**写操作即续期**。
- **TTL 读刷新（refresh_ttl）**：GET 的 CTE（`:278-307`）——unnest keys → `SET expires_at = NOW() + (ttl_minutes||' minutes')::interval WHERE do_refresh AND ttl_minutes IS NOT NULL`；SEARCH 把整个查询包进 `search_results` CTE 再 UPDATE（`:565-581`）。`TTLConfig`：refresh_on_read（默认 True）/ omit_expired（读时过滤）/ default_ttl / sweep_interval_minutes。
- **opportunistic sweep**：`DELETE FROM store WHERE expires_at IS NOT NULL AND expires_at < NOW()`（`:834-848`）；daemon 线程默认 5min 一轮，**必须显式启动**。设计 = 惰性过滤 + 低频后台清扫，不追求精确过期。
- **batch API**：按 op 类型分组依序单 pipeline 执行；PUT 先按 `(namespace, key)` 去重 last-wins、`value is None` 转 DELETE；向量文本先攒参数、embedding 算完后回填再 upsert（`:982-1065`）。
- **search 的 limit 放大公式**：`expanded_limit = (op.limit × __estimated_num_vectors × 2) + 1`（`:503-506`）；内层 `ORDER BY 距离算子 LIMIT expanded_limit` → `DISTINCT ON (prefix, key)` 每文档取最优向量 → 外层 `ORDER BY score DESC LIMIT/OFFSET`。距离算子：l2 `<->` / ip `<#>` / cosine `<=>`（score=1-dist）。**重要注释**（`:1416-1424`）：因 pgvector 限制（ORDER BY 必须裸算子、不能负号表达式），当前形态实际吃不到 ANN 索引（见 pgvector#216）——**照抄前先验证索引命中**。
- **EmbeddingsLambda**（`store/base/embed.py:109-230`）：任意 sync/async `Callable[[Sequence[str]], list[list[float]]]` 包成 Embeddings；另接受 Embeddings 实例或 `"openai:text-embedding-3-small"` 字符串。search 查询里向量用 PLACEHOLDER 占位、embedding 完成后回填。
- **index_config 字段路径**（`tokenize_path`，`embed.py:336-399`）：`a.b` 嵌套、`[0]/[*]/[-1]` 数组、`*` 通配、`{f1,f2}` 多选、`"$"`=整文档；一路径产出多 text 时 field_name 加 `.i` 后缀——store_vectors 一文档多行的来源。

## 8. conformance 套件（libs/checkpoint-conformance/）

- **能力模型**（`conformance/capabilities.py:15-50`）：BASE 5 项必须（put/put_writes/get_tuple/list/delete_thread）+ EXTENDED 4 项可选（delete_for_runs/copy_thread/prune/delta_channel_history）。检测 = 对应 **async 方法是否 override 基类**（`_is_overridden`）——零配置声明式能力发现。
- **机制**：`@checkpointer_test(name=...)` 注册工厂；`validate()`（`validate.py:45-90`）逐能力**新建干净 saver** → 未检出能力记 skipped → 检出则跑 `spec/` 下对应 runner。即「实现 BaseCheckpointSaver + 过套件 ⇒ 可插拔」。
- **测试面**：spec/ 9 文件共 **89 个 test**：put_writes 的幂等/跨 ns/特殊通道/下一 checkpoint 清空、put 的通道增删/版本保留/多线程隔离、list 的 metadata 多键过滤/before+limit 组合、**copy_thread 必须整条父链复制**、**prune keep_latest 保 writes**、delta history 的边界（最近快照为种子/目标自身 pending_writes 不计入等）。
- **BaseCheckpointSaver 全方法清单**（`checkpoint/base/__init__.py:177-723`）：get/get_tuple/list/put/put_writes/delete_thread + delete_for_runs/copy_thread/prune（默认 NotImplementedError，docstring 详述 DeltaChannel 下的安全约束：**naive keep_latest 会切断祖先链导致静默空重建**）+ get_delta_channel_history（默认实现性能弱但契约正确）+ get_next_version（PG/SQLite override 为 `f"{v:032}.{rand:016}"` 字符串版本）+ with_allowlist。⚠️ 本快照 PG/SQLite saver 均未实现 delete_for_runs/copy_thread/prune（仅 base 声明 + sdk client prune API）——扩展能力目前只有 conformance 契约与平台侧实现。

## 9. SQLite vs PG 实现差异对照

| 维度 | SqliteSaver | PostgresSaver |
|---|---|---|
| blob 表 | **无**——channel_values 内联 checkpoint blob（`_delta.py:6-12`） | 有，`(channel, version)` 寻址旁表 |
| setup | `PRAGMA WAL` + 两表 executescript，`is_setup` 进程内标记（`:139-166`） | 9 条版本化迁移，幂等可续跑 |
| put | 整个 checkpoint `dumps_typed` 后 `INSERT OR REPLACE`（`:420-436`）——**每步全量重写**，无增量 | 标量/blobs 分流 + 版本增量 |
| metadata 过滤 | `json_extract(CAST(metadata AS TEXT), '$.k') = ?`（key 正则白名单防注入，`utils.py:31-73`） | JSONB `@>` 包含语义 |
| 并发 | 单连接 + `threading.Lock` 全局串行，cursor 退出即 commit（`:168-189`） | pipeline / ConnectionPool；Async 版 AsyncPipeline |
| delta walk | 单流式合并走链：逐行反序列化、**峰值仅一个 checkpoint 在内存**（`_delta.py:1-20,68-120`） | K 通道独立游标 + JSONB 动态列探测 + EXISTS 探针 |
| 读装配 | 主查询后**每行再发一条 writes 子查询（N+1）**（`:353-356`） | 两个关联子查询一次行完成 |
| async | 同步类直接 raise，需 AsyncSqliteSaver | AsyncPostgresSaver 全方法真异步 |

## 10. 对企业级 agent（分布式 PG / Java-Spring JPA 建模）的借鉴意义

dimensions/02 §8 已给五条结论级判断，这里给 DDL/SQL 级的可抄物与坑。

**照搬清单**：
1. **版本寻址 blob 旁表 + DO NOTHING**：`(ns, channel, version)` PK 使未变状态零拷贝复用，天然幂等；JPA 建模 = 复合键 + native upsert，或 Hibernate `@SQLInsert(sql="... ON CONFLICT DO NOTHING")`。
2. **特殊写负 idx + 「全特殊才 REPLACE」**（`WRITES_IDX_MAP` + §3.2 查询选择）：错误/中断/恢复元数据与业务写共用一张表但语义隔离，值得逐字抄。
3. **put_writes 的 task_path 排序列**：恢复并行任务时的确定性顺序必须进 schema，uuid 主键不够。
4. **迁移即 append-only 列表 + 版本表**（含 no-op 对齐条目）：比 Liquibase 更轻的先例；「改旧迁移文本 + 追加补偿迁移」的 v2/v4 组合拳是标准做法。
5. **TTL 组合**：`expires_at`（写时定）+ `ttl_minutes`（读时算 interval 续期）双列 + 部分索引 + 惰性过滤谓词 + 低频 sweep——读路径 CTE（§7）可直接译成 PG SQL。
6. **future 链保序 + 写先于 checkpoint 可见**（§4）：Spring 侧等价物 = `CompletableFuture.thenCompose` 串联持久化任务，且 delta 写的 future 必须 join 在快照提交前。

**改造清单**：
1. **补 CAS**：checkpoints upsert 的 DO UPDATE 无版本条件，多副本并发同 thread 会互相覆盖——分布式部署前给 checkpoints 加 `WHERE checkpoints.checkpoint < EXCLUDED.checkpoint` 或独立 epoch 列（agentscope-java 式 `WHERE version=?`）。
2. **metadata 过滤要索引**：`@>` 无 GIN 索引时 list(filter) 全表扫；`CREATE INDEX ... USING gin (metadata jsonb_path_ops)` 应进迁移而非事后补。
3. **exit-durability 的合成 task_id**（step 编入 UUID 首段）：Java 侧可改为 `(step, task_id)` 双列排序键，比编码进 UUID 更直白。
4. **search limit 放大系数**：`limit × 每文档向量数 × 2 + 1` 是启发式；字段路径含通配时应按实际计数校准，否则 DISTINCT ON 后不够 limit。

**补缺清单**（langgraph 自身没做、企业场景必须补）：
1. **serde 信任边界**：permissive 默认 +「拦了就降级返原始 dict」意味着库被写入即近 RCE——企业侧必须 STRICT 白名单 + 库访问控制 + 载荷签名（对照 agent-framework 的 `register_checkpoint_type` 白名单）。
2. **prune/copy_thread 的 DeltaChannel 安全实现**：base docstring 自认 naive keep_latest 会静默空重建——凡采用「增量+快照」混合存储，清理策略必须先强制打快照或整链保留，**这是通用规律不是 langgraph 特例**。
3. **blobs/writes 无引用计数的清理**（GC 靠 delete_thread 整删）——需要按 version 引用图做异步回收。
4. **双阈值快照策略本身可抄**（updates≥N 或 supersteps≥M 强制快照，防「不活跃通道无限重放」），但 M 的 env 可调性说明这是运维旋钮——应做成配置表项而非常量。

## 11. 附录：全表字段明细（PG checkpoint 3 表 + Store 2 表 + SQLite 2 表 + 版本表 3 张）

### A. PG：checkpoints（快照主表；写入=put，UPSERT DO UPDATE 允许同超步重试覆盖）

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| thread_id | TEXT | NOT NULL, 复合 PK 第一列 | 线程/会话标识（隔离单元） |
| checkpoint_ns | TEXT | NOT NULL DEFAULT '' | 子图命名空间（默认根；子图独立寻址） |
| checkpoint_id | TEXT | NOT NULL, 复合 PK 第三列 | uuid6 单调可排序（`ORDER BY DESC LIMIT 1` 取最新的隐含前提） |
| parent_checkpoint_id | TEXT | 可空 | 父快照（time-travel 链） |
| type | TEXT | 可空 | serde 类型标签（msgpack/pickle/…） |
| checkpoint | JSONB | NOT NULL | 快照本体：channel_versions（版本图）/ channel_values（标量行内值）/ versions_seen（调度差分表）/ pending_sends 等 |
| metadata | JSONB | NOT NULL DEFAULT '{}' | source(input/loop/update/fork)/step/parents/run_id/counters_since_delta_snapshot |

索引：复合 PK + v6 迁移加的 `(thread_id)` 单列索引（list/delete_thread 谓词）。

### B. PG：checkpoint_blobs（按通道版本寻址的值旁表；写入=put，ON CONFLICT DO NOTHING 幂等）

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| thread_id / checkpoint_ns | TEXT | NOT NULL, 复合 PK 前两列 | |
| channel | TEXT | NOT NULL, 复合 PK 第三列 | 状态通道名（含特殊通道 `__pregel_tasks` 等） |
| version | TEXT | NOT NULL, 复合 PK 第四列 | 通道版本（`f"{v:032}.{rand:016}"` 字符串，单调可比较） |
| type | TEXT | 可空 | serde 标签；**`'empty'` = 墓碑**（版本存在但值不在本 checkpoint） |
| blob | BYTEA | **可空**（v4 迁移 DROP NOT NULL） | 值序列化字节（msgpack 为主，_DeltaSnapshot=ext 7） |

索引：复合 PK + v7 `(thread_id)`。**未变通道不写新行——读侧靠版本图 join 到旧版本行，跨 checkpoint 零拷贝复用的根基。**

### C. PG：checkpoint_writes（pending writes；写入=put_writes，特殊通道 DO UPDATE / 常规通道 DO NOTHING）

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| thread_id / checkpoint_ns / checkpoint_id | TEXT | NOT NULL, 复合 PK 前三列 | 归属快照 |
| task_id | TEXT | NOT NULL, 复合 PK 第四列 | 写入归属任务（随机 UUID；exit 模式合成 id 把 step 编进首段） |
| idx | INTEGER | NOT NULL, 复合 PK 第五列 | 写入序号；**特殊通道负 idx**：`__error__=-1/__scheduled__=-2/__interrupt__=-3/__resume__=-4` |
| task_path | TEXT | NOT NULL DEFAULT ''（v9 迁移加） | 任务拓扑路径——恢复 Send 的确定序（`ORDER BY task_path, task_id, idx`） |
| channel | TEXT | NOT NULL | 目标通道 |
| type | TEXT | 可空 | serde 标签 |
| blob | BYTEA | 可空 | 值序列化 |

索引：复合 PK + v8 `(thread_id)`。

### D. PG：store（跨线程长期状态真相表；upsert 冲突时 expires_at/ttl 一并 EXCLUDED 覆盖=写即续期）

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| prefix | TEXT | NOT NULL, 复合 PK 第一列 | namespace 元组的 '.' 连接（层级路径） |
| key | TEXT | NOT NULL, 复合 PK 第二列 | 命名空间内唯一键 |
| value | JSONB | NOT NULL | 文档本体（可对指定字段建向量索引） |
| created_at / updated_at | TIMESTAMPTZ | DEFAULT CURRENT_TIMESTAMP | |
| expires_at | TIMESTAMPTZ | 可空（v2 迁移加） | 过期时刻（写时 `NOW()+ttl`） |
| ttl_minutes | INT | 可空（v2 迁移加） | 读时续期参数（`NOW()+ttl_minutes::interval`） |

索引：复合 PK；`store_prefix_idx` btree(prefix text_pattern_ops)（前缀 LIKE）；`idx_store_expires_at` 部分索引（WHERE expires_at IS NOT NULL，只为有 TTL 的行）。

### E. PG：store_vectors（字段级向量派生表）

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| prefix / key | TEXT | 复合 PK 前两列, FK→store ON DELETE CASCADE | 文档引用（删文档级联清向量） |
| field_name | TEXT | 复合 PK 第三列 | 索引字段路径（`content`/`metadata.title`/`chapters[*].body`…；一路径多 text 加 `.i` 后缀——**一文档多行**） |
| embedding | vector(dims) 或 halfvec(dims) | NOT NULL | 向量（半精度可选；维度不一致拒写） |
| created_at / updated_at | TIMESTAMPTZ | DEFAULT CURRENT_TIMESTAMP | |

索引：复合 PK；ANN 索引 hnsw/ivfflat（kind/参数白名单消毒；⚠️ 当前 search 形态吃不到 ANN，见 §7）。

### F. SQLite 变体（SqliteSaver 两表，对照 §9）

`checkpoints`：thread_id / checkpoint_ns DEFAULT '' / checkpoint_id / parent_checkpoint_id / type / **checkpoint BLOB / metadata BLOB**（JSON 字节，过滤走 json_extract），PK(thread_id, checkpoint_ns, checkpoint_id)——**无 blob 旁表，channel_values 内联**。
`writes`：thread_id / checkpoint_ns / checkpoint_id / task_id / idx / channel / type / **value BLOB**，PK(thread_id, checkpoint_ns, checkpoint_id, task_id, idx)——无 task_path 列（旧契约）。

### G. 版本表（三张，各一行一版本号）

`checkpoint_migrations(v PK)` / `store_migrations(v PK)` / `vector_migrations(v PK)`——迁移 append-only 列表的位置索引（§1）。

---

*证据基线：langgraph@e539ac122f；行号以该快照为准。附录字段类型以 §1 迁移原文与 §2 SQL 为准。*
