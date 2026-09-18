# L3.7 dify 半日游：平台形态——画布、HITL 表单与能力清单

> 昨晚 adk 交卷：`LlmAgent + Runner` 装出全家桶版审查 agent，`session.state` 让同一
> agent 换会话换策略，`before_model_callback` 把不合规单号拦在模型请求之前——四个
> **库**框架至此全部跑完。今晚加演抽象光谱的终点形态：L3.1–L3.6 全是 pip 装进你
> 进程的库，dify 却是自己跑着十余个服务的**平台**，你的 agent 只是画布上的一张图。
> 本课的全部意义就是摸到「平台 vs 库」这条分界线——主线照旧离线可验收（compose
> 拓扑 + DSL + 能力清单），真跑平台（Docker Desktop）是可选加餐。

## 1. 本课目标

不写新 agent——换一双眼睛看同一个问题。完成后你能：

- 说清「平台 vs 库」的分界线：库是**你 pip 安装的依赖**（进你的进程、归 pytest 管），
  平台是**你部署的系统**（你的逻辑是它画布上的数据）；这条线决定了可测试性、
  可 git 性与迁移成本三件事的全部走向；
- 用 pyyaml 离线解析平台的两类「静态物」：docker compose 服务拓扑（谁依赖谁）
  与 App DSL（平台的图序列化格式——节点计数、边邻接、找会停下来等人的节点）；
- 产出本课固定收尾**平台能力清单**：六个维度（画布编排 / HITL 表单 / 知识库 / 模型接入 /
  观测与运营 / 部署形态）逐行回答「dify 有没有、入口在哪、库形态对应物是什么、锁定代价」；
- （可选，需 Docker Desktop）本地 compose 把 dify 真跑起来，在画布上搭一个最小的
  报销审查流，亲眼看它跑到 human-input 节点时**暂停等人填表单**——跑不了不影响毕业。

一个先说破的教学点：**平台课没有「离线模型替身」这回事**。前六课的 mock 端点能让框架
课零 key 三态全绿，是因为框架在你的进程里，替身可以插进调用链；平台跑在自己的容器里，
离线验收只能测「静态物」（DSL / 拓扑 / 配置），**动态行为要么起平台、要么免谈**——
这本身就是平台与库的重要差异，今晚你会反复撞到它。

**完成判据**：本目录下三条命令同时全绿（发货态：`code/` 讲义区绿，`exercises/` 是设计内的红）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 2. 概念讲解

先给全课对照表，再逐个展开：

| 你熟悉的 Java 物 | 今天的 dify 物 | 一句话差异 |
|---|---|---|
| Flowable / Camunda 这类 BPM 平台 vs 自研状态机库 | dify 平台 vs langgraph / mini-agent 库 | 库进你的进程，平台让你进它的运行时；Java 人把业务写进 BPMN XML 还是写 Java 代码的老争论，原样搬到了画布 DSL vs Python 代码上 |
| BPMN 2.0 XML（流程定义文件） | App DSL（YAML，`version` + `kind: app` + `graph.nodes/edges`） | 都是「图即数据」的带版本序列化格式；标准看着开放，版本语义是平台私有的（§5 坑位） |
| Jenkins（平台）vs 一条自己写的 CI 脚本（库） | dify vs agent 库 | 平台把 UI / 权限 / 审计 / 生态都配好，代价是你的一切长在它的约定与数据库里 |
| war 包丢进 Tomcat / Spring Boot 单进程 | docker compose 十几个服务的 N-tier 部署 | 部署形态从「一个进程」变回「一张部署视图」——api/worker 分离 ≈ Java 的 web/worker 拆分 |
| `application.yml`（Spring 配置） | compose YAML 与 DSL YAML | Java 人其实早就熟 YAML：缩进即层级；区别是这两份 YAML 不是配置，是**部署定义与程序本体** |
| Flowable 的 UserTask（人工节点） | `human-input` 节点（表单 + 动作按钮） | HITL 的平台形态：暂停→表单→按钮即出边；L3.3 的库形态是 `interrupt` + checkpoint |

### 2.1 光谱的第五格：平台

把 Unit 3 的抽象光谱补全：**拒抽象的 SDK（L3.1）→ 图引擎（L3.2–L3.4）→ harness（L3.5）→
全家桶（L3.6）→ 平台（本课）**。库形态的每往右一步都是「框架替你多管一层」，平台是终点——
连「你的代码」都省了：业务逻辑变成画布上的节点与连线，存进平台的数据库，导出成 DSL 文件。

分界线一句话：**库是你 `pip install` 的依赖，平台是你部署的系统**。由此推出三条可操作的判据：

1. **可测试性**：库代码进你的进程，pytest + mock 替身够得到每一行（前六课的零 key 三态）；
   平台的行为在它的容器里，你的测试只能要么起平台（重）、要么测静态物（本课主线）；
2. **可 git 性**：库项目的每个行为变更都是可 review 的 diff；平台画布的变更是数据库行，
   导出的 DSL 虽是文本，但「节点语义」的解释权在平台版本（§5）；
3. **迁移成本**：换库≈改 import 与装配层（L3.1→L3.6 我们干了六次）；换平台≈把画布上
   每个节点翻译回代码重写一遍。

顺带看清一个多语言现实：dify 的 `api/` 是 Python（Flask + Celery），`web/` 是
TypeScript（Next.js），v2 新组件 `dify-agent-runtime/` 干脆是 Go——平台产品天然多语言，
你按「Python 库」建立的单一语言预期在这里不成立（这也是它与前六课气质不同的地方）。

### 2.2 compose 服务拓扑：平台的部署视图

dify 自部署用 docker compose 起**一组**互相依赖的服务。先补两个新知识点的最小份量：

- **docker compose 是什么**：一个 YAML 文件声明「起哪些容器、每个用什么镜像、谁等谁就绪、
  暴露哪些端口」，`docker compose up -d` 一条命令把整套系统拉起来。Java 人可以理解成
  「把 application.yml 的思路用到部署上」——描述式地写**部署拓扑**，而不是写八篇运维文档。
- **YAML 语法三件事**（你是 Spring 老手，缩进语法早就在 application.yml 里写熟了，这里只列三个易错点）：① 缩进表达层级（**空格缩进，不用 tab**，缩进错了
  整棵树就错了）；② `key: value` 是映射（相当于 JSON 对象），`- item` 是列表（相当于数组）；
  ③ 同名键下两种形态都是合法 YAML——比如 `depends_on` 既可写映射（带条件）也可写列表，
  今晚的解析代码要两种都认（ex3）。对照 `application.yml`：Spring 程序员对这套缩进语法
  其实是熟的，陌生的是它在这里定义的不是配置而是**系统本身**。

dify 的模板（`docker/docker-compose-template.yaml`，1322 行）声明了 **39 个服务**（pyyaml
口径：顶层 services 键计数；模板按 compose profiles 分档，档位引擎是
`COMPOSE_PROFILES=${VECTOR_STORE:-weaviate},${DB_TYPE:-postgresql},collaboration`）：
**21 个服务挂在向量库档位后面**（17 个向量库本体 + 4 个配套件：milvus 的 etcd/minio、
opensearch 的 dashboards、elasticsearch 的 kibana），13 个常驻骨架件，5 个其他档位件
（db_postgres / api_websocket 默认开；db_mysql / certbot / unstructured 可选）。本课
`data/compose_excerpt.yaml` 裁的是默认上岗骨架 12 个：常驻 13 件里留 10（略去
ssrf_proxy / agent_ssrf_proxy / local_sandbox 三个代理沙箱件），加上默认档的
db_postgres 与 weaviate：

```text
nginx :80（唯一入口，depends_on: [api, web]）
├─ web            前端控制台（TypeScript / Next.js）
└─ api            后端 API（Python / Flask）
   worker         Celery 异步任务（与 api 同镜像！仅 MODE=worker 不同）
   worker_beat    Celery 定时调度（同镜像，MODE=beat）
   db_postgres    业务库：app / 会话 / 工作流定义（DSL 存在这）
   redis          缓存 + Celery broker + 暂停中的人机表单
   weaviate       向量库（知识库的一格，17 个本体选 1 的默认档）
   sandbox        代码节点执行沙箱
   plugin_daemon  插件运行时（工具/模型供应商以插件包安装）
   agent_backend  v2 新组件：dify-agent 的 FastAPI 服务
```

读图三问（Java 部署直觉直接平移）：api 与 worker **同镜像不同 MODE**——正是 Java 里
「一个 jar、web 与 worker 两种启动姿势」的容器版；db / redis / 向量库各司其职——
状态全部外置，任何应用容器都可以随意扩缩（无状态设计的经典分发）；nginx 是唯一入口——
端口收敛、TLS 终结都在这一格。**注意「平台自己也在演进」**：`agent_backend` 是 v2 架构
新加的（仓库根的 `dify-agent/` 与 `dify-agent-runtime/` 目录），它把 agent 运行时拆成了
独立服务——`dify-agent/` 的定位是「用自研的 Agenton 包（`agenton`，组装 Pydantic AI
运行；与 §2.3 的外部包 `graphon` 是两回事）藏在 FastAPI 后面」
（其 pyproject 依赖 `pydantic-ai-slim`），Go 写的 runtime 负责 shell 沙箱。读旧博客的
架构图时以源码为准，别把 2024 年的图当现状。

### 2.3 DSL：平台的序列化格式

画布上的图存在数据库里，也能导出成文件——**App DSL**（YAML）。顶层四件（讲义样例
`data/review_workflow.dsl.yaml` 的真实形状，依据 `export_dsl()` 源码）：

```yaml
app:            # 应用元信息：name / mode(workflow|advanced-chat|chat|agent…) / icon…
kind: app       # 固定值（导入时缺失会被强制补上）
version: 0.7.0  # DSL 格式版本（CURRENT_APP_DSL_VERSION，管兼容策略——§5 坑位主角）
workflow:       # workflow / advanced-chat 模式的正文
  graph:
    nodes: [...]   # 节点：id / position / data.type（start/llm/if-else/tool/…）
    edges: [...]   # 边：source / target / sourceHandle（分支边靠它区分去向）
```

节点类型是平台的一等词汇（源码 planner 提示词里的完整类型表见 §6 路标）：`start` /
`end` / `answer` / `llm` / `knowledge-retrieval` / `code` / `template-transform` /
`http-request` / `tool` / `if-else` / `iteration` / `loop` / `question-classifier` /
`parameter-extractor` / `document-extractor` / `variable-aggregator` / `list-operator` /
`assigner` / `human-input`。更狠的一手是：本版把 start/llm 这些**经典节点类型的定义
本身**搬去了外部 pip 包 `graphon`（`langgenius/dify@79effdd498#api/pyproject.toml`
钉 `graphon==0.7.0`）——在 dify 仓内 grep NodeType 枚举会落空。平台代码也在拆包演进，
这是「读平台源码必须锚 commit」的又一实证。

对照 L3.2 记住这个反转：langgraph 的 StateGraph 是**代码构图**（Python 函数、条件边
lambda），平台的图是**数据**（YAML 里的 nodes/edges）。图是数据，所以能离线静态审查——
本课 Step 2 与 ex1 的全部动作（数节点、找孤立节点、找会停的节点）都建立在这一点上；
也是同一点让画布逻辑**不可单测**（没有函数可调用，只有平台运行时能解释它）。
Java 对照：BPMN XML 之于 Flowable，正是 DSL 之于 dify。

### 2.4 HITL 两种形态：平台表单 vs 库的 interrupt

同一个需求（跑到一半停下来等人），两种形态长这样：

| | 库形态（L3.3 langgraph） | 平台形态（dify human-input 节点） |
|---|---|---|
| 停下来的机制 | `interrupt()` 在代码里抛信号，图执行挂起 | 运行到 `human-input` 节点，工作流状态挂起 |
| 等人的界面 | 你自己写（CLI / API / 飞书卡片任你） | 平台生成表单：paragraph / select / file 输入 + 动作按钮 |
| 恢复的机制 | `Command(resume=...)` 从 checkpoint 继续 | 收表单，沿**所选按钮对应的出边**继续 |
| 超时兜底 | 你自己写 | 节点自带 `timeout: 36` / `timeout_unit: hour` |

一个源码细节值得记住（`api/core/workflow/nodes/human_input/entities.py`）：
`user_actions` 里每个动作的 `id`（如 `approve` / `reject`）**同时是节点的输出把手**——
出边的 `sourceHandle` 就是按钮 id。「按钮即出边」是平台把控制流数据化的漂亮样本，
Step 2 的测试会机器验证这一点。而它的代价在表里看不到：暂停/恢复/超时语义全部
活在平台运行时里，你的 pytest 够不着。

### 2.5 知识库：RAG 的平台化封装（指路不深入）

dify 的知识库（dataset）= 文档上传 → 切块 → 嵌入 → 存向量库 → 画布 `knowledge-retrieval`
节点检索 → LLM 节点引用。能力存在、入口清楚（`api/services/dataset_service.py`，
4484 行——wc -l 口径；画布节点选 dataset_ids），深入不做：RAG 的原理与 MCP 检索工具
属于 mcp-for-beginners 与毕业设计的领地（§6 指路）。对能力清单你只需要判断：
**库形态没有这一层**——前六课谁也没替你做检索，毕设的 SQLite + 检索要自己写；
平台替你做了，代价是切块/嵌入/检索策略都长在它的配置里。

## 3. 动手代码

先 `uv sync`（本课运行依赖只有 pyyaml——平台本体不需要 pip 安装，它跑在 compose 上，
这句话本身就是本课的题眼）。`data/` 下两份教学素材：`compose_excerpt.yaml`（从
langgenius/dify@79effdd498 的 compose 模板裁剪的 12 服务骨架）与
`review_workflow.dsl.yaml`（按 dify DSL 格式**手工构造**的教学样例，非平台导出——
两份文件的头注释都写明了来源与裁剪口径）。

### Step 1：解析 compose 拓扑（15 分钟）

```bash
uv run python code/topology.py
```

```text
== compose 服务拓扑（12 个服务，摘录自 dify 自部署模板） ==
init_permissions（busybox） ->（无依赖）
api（dify-api） -> ['init_permissions', 'db_postgres', 'redis', 'agent_backend']
worker（dify-api） -> ['init_permissions', 'db_postgres', 'redis', 'agent_backend']
worker_beat（dify-api） -> ['init_permissions', 'db_postgres', 'redis']
web（dify-web） ->（无依赖）
db_postgres（postgres） ->（无依赖）
redis（redis） ->（无依赖）
sandbox（dify-sandbox） ->（无依赖）
plugin_daemon（dify-plugin-daemon） -> ['db_postgres']
agent_backend（dify-agent-backend） -> ['redis', 'plugin_daemon']
nginx（nginx） -> ['api', 'web']
weaviate（weaviate） ->（无依赖）
```

对着输出把 §2.2 的读图三问走一遍。技术点只有两个：`yaml.safe_load` 把 YAML 读成
普通的 dict/list（纯数据、不执行任何东西）；`depends_on` 的两种合法写法（映射带
condition / 列表）读出来一个是 dict 一个是 list，解析要分流（ex3 会再练一遍）。

### Step 2：解析教学版 DSL——静态审查（15 分钟）

```bash
uv run python code/dsl_reader.py
```

```text
== DSL 静态审查：报销单审查（教学样例） ==
kind=app version=0.7.0 mode=workflow
节点类型计数: {'start': 1, 'knowledge-retrieval': 1, 'llm': 1, 'human-input': 1, 'end': 2, 'code': 1}
  start -> ['policy_kb']
  policy_kb -> ['precheck']
  precheck -> ['review']
  review -> ['end_ok', 'end_reject']
会停下来的节点（['human-input']）: ['review']
```

这份样例是一条最小报销审查流：开始（claim_id 输入）→ 查政策知识库 → LLM 预审 →
**人工复核（human-input：一个 paragraph 输入 + 同意/驳回两个按钮，出边 sourceHandle
就是按钮 id）→ 按钮分流到两个 end**。另有第 7 个节点 `code`（生成归档备注）是刻意保留的
**孤立节点**——画布上拉出来没接线，运行时永远走不到，但静态审查一眼看见（ex1 练这个）。

诚实边界再敲一次：静态审查能回答「图长什么样、哪里会停」，回答不了「跑起来对不对」——
那需要平台运行时。库课里这一格由 pytest 填，平台课里它只能空着或起平台。

### Step 3（可选，需 Docker Desktop）：真起一个 dify

前置：安装 Docker Desktop（或等价的 docker + compose v2.24+），分给它至少 2 CPU / 8GB
内存。以下步骤按官方 `docker/README.md`（langgenius/dify@79effdd498#docker/README.md）
与 compose 模板撰写——**本课作者没有实测运行时行为**（离线主线完整），跑不顺不影响毕业。

```bash
docker --version
docker compose version
```

在 dify 仓库克隆的 docker 目录里（平台差异：Windows 用 `copy` 替代 `cp`）：

```bash
cd docker
cp .env.example .env
docker compose up -d
```

起来后浏览器开 `http://localhost/`（`EXPOSE_NGINX_PORT` 默认 80），首次进入会让你建
管理员账号。自查清单（文字版「截图说明」，代替截图自查）：`docker compose ps` 里
api / worker / web / db_postgres / redis / nginx 应为 running 或 healthy；控制台能建应用。

然后做今晚的正事——**在画布上搭最小审查流**（步骤文字化）：

1. 控制台「创建空白应用 → 工作流」，命名「报销审查半日游」；
2. 拖一个开始节点，加输入变量 `claim_id`（文本，必填）；
3. 拖一个 LLM 节点：系统提示写「你是财务预审助手，对 {{#start.claim_id#}} 给出预审意见」
   （模型供应商要先在「设置 → 模型供应商」里配好，OpenAI 兼容端点即可）；
4. 拖一个「人工反馈/表单」类节点（本版本类型名 human-input）：加一个多行输入
   `comment`，两个按钮动作 `approve`（同意）与 `reject`（驳回）；
5. 从按钮各连一条边到两个结束节点，输出 `decision`（取所选动作）与 `reviewer_comment`；
6. 发布并试运行：观察运行到表单节点**工作流暂停**，填表单点按钮后沿对应边恢复——
   §2.4 的表格从「读过」变「摸过」。

另一个可选动作：控制台支持「导入 DSL 文件」（Apps → Import DSL file）。注意本课的
`data/review_workflow.dsl.yaml` 是教学构造样例——保证「读得懂」，**不保证「导入得进」**
（prompt 全文、插件依赖等字段有裁剪）；要导入请用你自己平台的导出文件。

### Step 4：平台能力清单（本课固定收尾）

```bash
uv run python code/capabilities.py
```

```text
== 平台能力清单（6 个维度）==
[画布编排]
  dify 入口     : web 画布拖拽编排 workflow，图即数据（DSL YAML，api/services/app_dsl_service.py 的 export_dsl）
  库形态对应物  : langgraph StateGraph 代码构图（L3.2–L3.4）；mini-agent 的 while 循环（Unit 2）
  锁定代价      : 图逻辑不可 git diff 审查、不可单测；迁出平台=按 DSL 重写一遍图
[HITL 表单]
  dify 入口     : human-input 节点：暂停→表单→按动作边恢复（api/core/workflow/nodes/human_input/）
  库形态对应物  : langgraph interrupt + checkpoint（L3.3）；openai-agents 的 RunState（L3.1）
  锁定代价      : 表单 schema、暂停/超时/恢复语义是平台私有格式与运行时行为
[知识库]
  dify 入口     : dataset 服务（api/services/dataset_service.py，4484 行（wc -l））+ knowledge-retrieval 节点
  库形态对应物  : 无内建——库形态要自己组 RAG（毕设的 SQLite + 检索，深入指路 mcp-for-beginners）
  锁定代价      : 切块/嵌入/检索策略绑平台配置；文档数据进平台库，导出走 API
[模型接入]
  dify 入口     : 模型供应商体系 + 插件市场（plugin_daemon 服务，docker/docker-compose-template.yaml）
  库形态对应物  : 每课 .env 三变量直连端点；adk 的 litellm 中转层（L3.6）
  锁定代价      : 供应商配置是平台数据库里的数据不是代码；换平台要重配全部模型路由
[观测与运营]
  dify 入口     : web 控制台：运行日志、标注、应用统计（api/services/workflow_app_log_query_service.py）
  库形态对应物  : 无内建——框架课 test_contract.py 的 pytest 契约 + mini-agent 的 print 取证
  锁定代价      : 运营数据在平台库里；对运行行为的断言只能进控制台人工看，进不了 CI
[部署形态]
  dify 入口     : compose 十余服务：api/worker 分离 + db/redis/向量库/nginx（docker-compose-template.yaml）
  库形态对应物  : 库形态（L3.1–L3.6、mini-agent）是 uv 单进程——pytest 即验收；毕设 FastAPI + SQLite
  锁定代价      : N-tier 运维成本：升级、备份、扩容、安全加固都是平台工程，不是 pip install
```

这张表是本课的交付物：每个维度一行，回答「dify 有没有、入口在哪（模块/服务级路径，
§6 路标是证据口径）/ 库形态对应物是什么（L3.1–L3.6 或 mini-agent 的哪一块）/
锁定代价（迁出平台时要重做什么）」。ex2 会让你把它变成**你自己写的**清单——
照抄讲义只能过字段检查，最后一行你自己的维度没人能替你写。

讲义区验收（12 个测试：compose 拓扑 4 + DSL 静态审查 5 + 能力清单 meta 检查 3）：

```bash
uv run pytest code/
```

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改标注的 TODO 区（与所需的顶部 import）；卡住先想 5 分钟，
再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_dsl_stats.py` | DSL 节点统计器：类型计数 + 孤立节点检测（图论邻接落地，内联图谱自包含） |
| ex2 | `exercises/ex2_capabilities.py` | 平台能力清单（覆盖型 + meta-test）：补全四行、自加一行，meta 检查维度齐全/字段完整/对应物点名真实课程 |
| ex3 | `exercises/ex3_compose_edges.py` | compose 拓扑提取：depends_on 两种 YAML 形态统一 + 反向邻接（谁依赖 redis？） |

ex2 是 L0.1 ex2 的 meta-test 先例在框架课的复用：被测数据是清单表本身，验收测试
（4 个）直接检查「六个必须维度、每行四列非空无 TODO 占位、对应物列必须点名真实课程
（或诚实写无）、至少 7 行且维度不重复」——删行偷懒与留空过关都过不了。ex1 / ex3 各
3 / 4 个测试。

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：DSL 版本漂移坑（导入「成功」，行为已变）

- **现象**：团队把半年前导出的审查流 DSL 导进升级后的 dify。导入界面绿色通过，工作流
  照常能跑——但某类节点的行为悄悄变了（比如表单默认值的新来源、某分支节点的比较语义）。
  没有任何测试红：因为**对平台行为的断言从来就不在你的 CI 里**（§1 说过：动态行为要么
  起平台要么免谈）。三周后有人工复核漏单才被发现。
- **最小复现**（源码级，不用起平台）：DSL 的版本语义写死在两个小文件里。
  `api/constants/dsl_version.py`：`CURRENT_APP_DSL_VERSION = "0.7.0"`；
  `api/services/dsl_version.py` 的 `check_version_compatibility`：

  ```python
  if imported_ver > current_ver:               # DSL 比平台新 → PENDING（等平台升级）
      return ImportStatus.PENDING
  if imported_ver.major < current_ver.major:   # 大版本落后 → PENDING（人工确认）
      return ImportStatus.PENDING
  if imported_ver.minor < current_ver.minor:   # 小版本落后 → 照常导入，仅带警告
      return ImportStatus.COMPLETED_WITH_WARNINGS
  return ImportStatus.COMPLETED
  ```

  拿 0.6.x 的 DSL 导入 0.7.0 平台：第三条命中——`COMPLETED_WITH_WARNINGS`，导入成功、
  警告只在导入响应里闪一次。节点怎么解释、哪些字段换了语义，全由**平台当前版本**决定。
- **Java 直觉为何失效**：两重错觉。①「YAML 是配置，配置向后兼容」——`application.yml`
  的经验是加字段旧程序无视、删字段新程序给默认值；但 DSL 不是配置，是**带版本号的
  程序本体**，minor 差一位就语义可能漂移。②「有版本号就有兼容承诺」——BPMN 2.0 XML
  看着是标准，但 Flowable 用户都知道：同名元素在不同引擎版本的解释能差出一个 bug 单。
  私有序列化格式的 `version` 字段管的是**导入策略**，不是**行为兼容**。
- **修复与纪律**：把 DSL 当「有版本的外部代码依赖」对待——① DSL 文件入库时同时记录
  导出方的 `version`（文件里就有）与平台版本，升级平台先在预发环境**全量重导入重试跑**；
  ② 导入带警告（`completed-with-warnings`）时按「可能行为漂移」处理：挑关键路径
  （本课样例里就是 human-input 那一站）人工过一遍，别让警告只活在导入响应里；
  ③ 长期纪律与 §2.1 第 2 条同源：能在代码里的逻辑别让它只活在画布里——DSL 是传输格式，
  不是 source of truth 的保险箱。

（第二候选坑「低代码锁定」——画布不可 git diff、不可单测、迁移成本随画布复杂度增长——
不再单独立节：它就是能力清单「锁定代价」一列的通项，ex2 写完你比读一节文字更清楚。）

## 6. 延伸

- langgenius/dify@79effdd498#docker/docker-compose-template.yaml —— compose 模板本体
  （1322 行、39 服务，本课摘录的母本）；同目录 `generate_docker_compose` 脚本演示
  `docker-compose.yaml` 如何从「模板 + .env.example」自动生成——部署产物也是生成物。
- langgenius/dify@79effdd498#api/services/app_dsl_service.py —— DSL 导入/导出服务
  （`import_app` / `export_dsl`）：顶层四件怎么写、workflow 模式怎么落库、
  版本缺失时强制补 `0.1.0` 与 `kind: app` 的宽容逻辑，都在这里。
- langgenius/dify@79effdd498#api/constants/dsl_version.py 与
  langgenius/dify@79effdd498#api/services/dsl_version.py —— §5 坑位的全部源码证据
  （`CURRENT_APP_DSL_VERSION = "0.7.0"` 与四级兼容判定），两个文件加起来不到 40 行。
- langgenius/dify@79effdd498#api/core/workflow/nodes/human_input/entities.py ——
  HITL 表单的真实 schema：`HumanInputNodeData` 的 inputs（paragraph/select/file/file-list）、
  user_actions（id 即输出把手）、timeout 默认 36 小时；§2.4 表格每一行都能在这里找到字段。
- langgenius/dify@79effdd498#api/core/workflow/generator/prompts/planner_prompts.py ——
  平台自己的「节点类型总表」（19 种，给自然语言建流用的 planner 提示词）——比任何
  博客都权威的类型枚举出处。
- langgenius/dify@79effdd498#api/services/dataset_service.py —— 知识库服务主体
  （4484 行）：能力存在、入口在此，深入按宪法不做（指路 mcp-for-beginners 的
  retrieval/RAG 章节，L2.5 的 MCP 检索工具是它的库形态近亲）。
- langgenius/dify@79effdd498#dify-agent/README.md 与
  langgenius/dify@79effdd498#dify-agent-runtime/README.md —— v2 架构的两个新组件：
  前者是「Agenton 组装 Pydantic AI、藏在 FastAPI 后面」的 Python 服务（依赖
  `pydantic-ai-slim`——**平台的新 agent 运行时自己也站在库上**），后者是 Go 写的
  shellctl 沙箱运行时（Landlock 路径隔离）。读旧架构博客前先读这两个 README。
- 官方文档：自部署 compose 指南 https://docs.dify.ai/en/self-host/deploy/quick-start/docker-compose ；
  应用的 DSL 导入/导出说明 https://docs.dify.ai/en/cloud/use-dify/workspace/app-management
  （文档随版本走，源码锚定以本文路标为准）。

下一课 L3.8 是 Unit 3 收口：mini-agent vs 四框架 vs 今晚的平台放进同一张
「能力-成本-锁定性」决策表——今晚的能力清单就是「平台」一行的数据来源；
毕设选「库」不选「平台」的理由，明晚在决策表上正式落锤。

## 离毕业又近的一块

毕业设计选 langgraph（库）不选平台，今晚有了实感：可测试性（毕设三条主链路要进
pytest 集成测试——平台行为够不着 CI）、可 git（L5.3 事件溯源与图版本绑定依赖代码
可审查——画布 DSL 只是长得像文本）、可迁移（JAVA-MAPPING.md 要把每个模式翻译回
Java——`interrupt` 的语义能用 langgraph4j 讲清楚，human-input 表单只能用 dify 讲）。
L3.8 的决策表明晚把这些直觉收成一张表，毕业设计的技术评审（L5.0）直接引用它。
