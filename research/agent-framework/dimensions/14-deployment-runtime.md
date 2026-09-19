# 维度 14：部署运行时（Deployment Runtime）

> 本维度回答：代码写完之后**怎么跑起来**——框架提供什么 serving 形态（库、内嵌 server、独立服务、平台）、异步与定时任务（async jobs / cron）怎么承载、多副本高可用（HA）靠什么共享状态、仓库里有没有容器化产物（Docker/Helm）。17 框架呈四个梯队：**全家桶平台**（Dify 13 核心服务 docker-compose——全量 compose 文件定义 39 个 service，其余为可选向量库/中间件、agentscope-java 三进程 + Helm + aistio）自带完整生产拓扑；**CLI/dev-server + 云部署器**（adk-python、langgraph、agent-framework devui）给开发态满分、生产态半开半闭；**服务工厂**（agentscope Python、adk-java、spring-ai-alibaba）把企业能力做成可 mount 的 FastAPI/Spring 组件；**纯库**（langchain、langchain4j、spring-ai、openai-agents、claude-sdk、llama_index、crewai OSS）完全外置运行时。异步/定时是分化最大的子项：celery 分级队列（Dify）、quartz/xxl-job（agentscope-java）、cron SDK 指向闭源平台（langgraph）三 种形态并存。

## 14.1 总览矩阵

| 框架 | 评级 | 一句话实现 | 关键证据（仓库相对路径#符号）|
|---|---|---|---|
| langchain | ❌ | v1/core 无任何 server 代码（rg fastapi/uvicorn 零命中）；运行时整体外置 langgraph 生态与闭源平台 | libs/langchain_v1、libs/core 检索无命中（档案已验证，二次复核维持）|
| langgraph | 🟡 | 开源 = cli dev server + 双语 SDK + RemoteGraph；生产 API server 是闭源 `langchain/langgraph-api` 镜像（cli 直接编排它）| libs/cli/langgraph_cli/docker.py:262-278（langgraph-api service + REDIS_URI/POSTGRES_URI，二次核验）；libs/sdk-py/langgraph_sdk/_async/cron.py |
| langgraph4j | 🟡 | Studio 是嵌入式进程内调试服务器（jetty/springboot，SSE + 内嵌 webui）；无生产 server/cron/queue/docker | studio/base/.../LangGraphStudioServer.java；studio/{jetty,springboot}/ |
| langchain4j | ❌ | 纯库：无 server/cron/queue；Spring Boot/Quarkus starter 在独立官方仓库（本仓 pom 无 spring 依赖） | pom.xml（108 模块无 server 模块；全文无 spring/quarkus）|
| deepagents | 🟡 | 核心纯库（返回 CompiledStateGraph 挂 langgraph 生态）；外围包：ACP server（Zed）、dcode 终端 TUI + headless、talon 消息通道 + cron（实验 alpha）| libs/acp/deepagents_acp/server.py；libs/talon/deepagents_talon/cron/；libs/code/ |
| agent-framework (MS) | 🟡 | app-owned 哲学：hosting 系列只给执行态 helpers（alpha）+ devui 本地台（beta）+ Foundry Hosting/Local；**durable 扩展已外置独立仓**（ADR-0032 二次核验修正）| python/packages/hosting/pyproject.toml；packages/devui/agent_framework_devui/_cli.py:149#main；docs/decisions/0032-durable-azure-functions-extraction.md |
| adk-python | ✅ | CLI 全家桶 `adk create/run/web/api_server/eval/deploy/conformance/optimize/telemetry` + to_a2a Starlette + Cloud Run/Agent Engine deployer + Live 双向流 | src/google/adk/cli/cli_tools_click.py（deploy:445、conformance:569、create:811、run:1027、cli_web:2142、api_server 命令:2250 二次核验）；cli/fast_api.py:573/:616 |
| adk-java | 🟡 | dev 模块 = Spring Boot 服务器（REST×7 + Live WebSocket + Agent Engine 部署器），入口 `mvn google-adk:web`；无 CLI 全家桶 | dev/.../AdkWebServer.java#main；maven_plugin/.../WebMojo.java:90 @Mojo(name="web")（二次核验）；dev/deploy/AgentEngineDeployer.java |
| openai-agents-python | 🔶 | 无 server/队列/定时；仅 realtime FastAPI/WebSocket demo 与 Temporal 持久化示例；REPL 调试循环 | examples/realtime/app/server.py:12；examples/sandbox/extensions/temporal/；src/agents/repl.py#run_demo_loop |
| claude-agent-sdk-python | ❌ | 每次 query 一个 CLI 子进程（无池化；shielded 三段关闭 + atexit 收割孤儿）；部署完全留给宿主 | _internal/transport/subprocess_cli.py#close、#_kill_active_children、#_DEFAULT_MAX_BUFFER_SIZE |
| crewai | 🟡 | OSS 无服务端/镜像；`crewai deploy`（create/list/push/status/logs）与 triggers/cron 全是对付费 AMP 平台的 REST 客户端 | lib/cli/src/crewai_cli/cli.py:714#deploy（二次核验）；lib/crewai-core/src/crewai_core/plus_api.py:323/:328#deploy_by_name；cli/triggers/main.py:23 |
| dify | ✅ | docker-compose 13 核心服务全家桶（api/api_websocket/worker/worker_beat/web/db/redis/sandbox/plugin_daemon/agent_backend/ssrf_proxy/nginx/local_sandbox；另含 init_permissions 与约 20 个可选数据库/中间件 service，compose 全量共 39 个）+ Celery 三级队列 + CFS + webhook/定时触发节点；无 Helm（外部社区仓）| docker/docker-compose.yaml（服务名与镜像二次核验：dify-api:1.17.1×4、dify-sandbox:0.2.15:511、dify-agent-local-sandbox:1.17.1:549）；api/tasks/async_workflow_tasks.py:53-90 |
| llama_index | ❌ | 无 server/队列/调度；deployment 文档正文仅 "TODO"；LlamaDeploy 是外部独立仓库（零代码）| docs/.../deployment/deployment.md（TODO 占位）；llama-dev/ 为 monorepo 工程 CLI |
| agentscope | ✅ | `create_app` FastAPI 工厂（17 路由，可 standalone 可 mount 进现有服务）+ cron 调度器（apscheduler）+ 渠道 worker（钉钉/飞书/Discord）+ Redis MessageBus；仓库无 Docker/Helm | src/agentscope/app/_app.py:78#create_app；app/_router/_schedule.py；app/channel/ |
| agentscope-java | ✅ | 三进程 service（Gateway/DataPlane/Scheduler，二次核验 GatewayApp/DataApp/SchedulerApp 三 main 类）+ docker-compose + Helm + deploy/release runbook + Go 版 aistio 流量连接器 + 11 Spring starter + quartz/xxl-job + 5 IM 渠道 | agentscope-service/{service-gateway,service-dataplane,service-scheduler}/、helm/、docker-compose.yml、aistio/go.mod；agentscope-extensions-scheduler/（quartz/xxl-job 二次核验）|
| spring-ai-alibaba | 🟡 | Spring Boot 应用即部署单元；A2A JSON-RPC server + Nacos 注册发现 + 图定时调度（CompiledGraph#schedule）+ Docker 代码沙箱；无官方 HA/queue | spring-boot-starters/spring-ai-alibaba-starter-a2a-nacos/.../GraphAgentExecutor.java；graph-core/.../graph/scheduling/（ScheduledAgentTask）|
| spring-ai | 🟡 | 库形态：48 个 starter 即部署单元；唯一服务化出口是 MCP server starter（webmvc/webflux）；GraalVM AOT 成体系 | starters/（48 模块）；starters/spring-ai-starter-mcp-server-webmvc |

评级说明：与档案一致。修正一处事实陈述（不改评级）：MS agent-framework 的 Durable Task / Azure Functions 托管已按 ADR-0032 **抽到外部仓 microsoft/agent-framework-durable-extension**（python/packages/ 已无 durabletask 包、dotnet/src 无对应项目，二次核验）——「MS 的 durable execution」应表述为「外置生态承载」而非仓内能力。

## 14.2 实现方式深析

### 派系 A：serving 形态——从库到平台的五档

**第 1 档 · 纯库（进程即运行时）**：langchain、langchain4j、spring-ai、openai-agents、claude-sdk、llama_index。特征是仓库里连一个 uvicorn/FastAPI 依赖都没有（langchain v1 档案 rg 零命中；langchain4j/spring-ai pom 已验证），运行时 = 宿主应用进程。其中两个特例值得注意：spring-ai 虽是库，但 48 个 Spring Boot starter 让「部署单元 = 一个 starter 依赖」，且 MCP server starter 是唯一的反向服务化出口（把 Spring 应用整体暴露为 MCP 工具服务，webmvc/webflux 双传输 + stateless 模式）；claude-sdk 的「运行时」是每 query 一个 CLI 子进程，SDK 的工程精力全花在进程边界上（1MiB stdout 缓冲上限、shielded 三段关闭 5s→SIGTERM 5s→SIGKILL、atexit 孤儿收割）——部署拓扑留给宿主。

**第 2 档 · 嵌入式调试服务器**：langgraph4j Studio（LangGraphStudioServer 内嵌 webui，jetty/springboot 宿主，SSE 流式；quarkus 模块已停用）、spring-ai-alibaba studio（Spring MVC + 内嵌 agent-chat-ui 静态资源 + ConfigAgentWatcher 热加载）、adk-java dev 模块（Spring Boot + REST×7 + Live WebSocket，入口是 Maven goal 而非 CLI）。共同点：调试/开发态明确、生产态明确不管。

**第 3 档 · CLI 编排 + 半闭源生产边界**：这是 langgraph 与 adk-python 的对照热点。langgraph 的边界最清晰可指证：开源 cli 的 docker.py:262-278 直接生成引用 `langgraph-api` 镜像的 compose（配 REDIS_URI/POSTGRES_URI，distributed 模式设 N_JOBS_PER_WORKER=0）——即本地 dev server（langgraph dev）可用，生产 API server（队列/Postgres 编排/Studio）是 LangGraph Platform / LangSmith Deployments 商业镜像；开源侧留下的是双语 SDK（threads/runs/assistants/**crons**/store 客户端）与 RemoteGraph（把远端部署图当本地子图调）。cron 客户端在 SDK 里但引擎在闭源平台。adk-python 反其道：CLI 全家桶全开源（二次核验：create:811/run:1027/web:2142/api_server:2250/eval/deploy:445/conformance:569/optimize/telemetry:407），`adk api_server` 是 FastAPI/uvicorn（fast_api.py 非流式 + SSE 两端点，带 CORS 与 host 白名单中间件），`adk deploy` 交付 Cloud Run/Agent Engine deployer——开源侧即可走完开发→部署，托管增值在 Vertex 侧。

**第 4 档 · 服务工厂 / 多进程平台**：agentscope(Python) 的 `create_app` 是「库与平台一套代码两个形态」的样板——17 个 router（session/chat/agent/channel/credential/model/schedule/skill/kb/workspace…）+ scheduler + channel worker + index worker 注入一个 FastAPI 工厂，可 `uvicorn.run` 也可 `root.mount("/agentscope", app)` 嵌入现有服务；lifespan 统一管理后端生命周期。agentscope-java 则升级为三进程控制平面（Gateway 契约路由 / DataPlane 托管会话与工具确认 / Scheduler cron 部署与渠道运行时，README 宣称可治理 Claude/OpenClaw/QwenPaw 等异构框架 agent）+ Go 写的 aistio 流量连接器——是 17 家中唯一把「跨框架 agent 网关」做进仓库的。

**第 5 档 · 全平台 docker-compose**：Dify 一家。compose 拉起 12+ 服务（二次核验服务名：init_permissions/api/api_websocket/worker/worker_beat/web/db_postgres/redis/sandbox/plugin_daemon/agent_backend/ssrf_proxy/nginx/local_sandbox，镜像 langgenius/dify-api:1.17.1 出现 4 次——api、websocket、worker、beat 共享同一镜像不同入口）。API 层是 gunicorn + gevent + psycogreen（gunicorn.conf.py 头部大段 monkey-patching 时序注释）+ Socket.IO。唯一缺口：Helm chart 不在仓库（社区 dify-kubernetes 独立仓），自托管 K8s 用户需自行搬运。

### 派系 B：异步任务与定时

- **Dify：Celery 分级队列 + 引擎内 CFS 双层调度**——worker 落 `PROFESSIONAL/TEAM/SANDBOX` 三队列（按订阅层级分队列，async_workflow_tasks.py:53-90 二次核验，每个队列独立 AsyncWorkflowCFSPlanScheduler 实例），引擎侧 TimeSliceLayer 再做工作流粒度 CFS 时间片与资源超限暂停；worker_beat（ext_celery.py beat_schedule：conversation_cleanup_sweeper 等）+ trigger_schedule/trigger_webhook 节点 + trigger_processing_tasks 完成事件驱动闭环。这是 17 家中唯一的「资源公平调度」实现，平台属性使然。
- **agentscope-java：三路定时**——service-scheduler 的 CronDeploymentScheduler（进程级 cron 部署）、extensions-scheduler（quartz / xxl-job 两企业调度器，二次核验目录）、harness 的 PeriodicGate（Local/StoreBacked 周期唤醒门，cron 型常驻 agent 原语）。
- **langgraph：cron 是平台协议**——SDK 有完整 crons 客户端（create/list/delete），引擎本身无 scheduler；开源自托管没有官方定时方案（Redis 破损触发/外部 cron 调 API 是社区常态）。
- **MS：durable 已外置**（ADR-0032 二次核验）——Durable Task/Azure Functions 集成搬到 microsoft/agent-framework-durable-extension 独立仓；仓内留存的是自身 checkpoint 体系（每超步自动落盘）+ Foundry Hosting（长运行/弹性 agent，ADR-0035，beta）。
- **agentscope(Python)**：apscheduler 的 cron 表达式 + 时区校验（改 cron 即重排）。
- **crewai**：`crewai triggers` 是 AMP 平台客户端（list_triggers/execute_with_trigger），OSS 无定时。
- **其余**（adk 双语、openai-agents、claude-sdk、llama_index、spring-ai、langchain4j）：无内置定时，外部调度器直调。

### 派系 C：高可用与共享状态

多副本会话路由的共识是「无本地状态 + 外置真相源」，但外置对象不同：

- **langgraph 生态（langgraph/deepagents/langchain）**：checkpointer 是唯一真相源（Postgres saver 官方、Redis 社区仓 ⚠️未本地验证），多副本经 BaseCheckpointSaver 共享；durability 三级（sync/async/exit）把一致性-延迟权衡交给调用点；durable 不是靠队列而是靠超步边界写 checkpoint。
- **agentscope(Python)**：显式双通道设计——持久化走 Storage（SQLAlchemy 异步/Redis）+ 传输走 MessageBus（in-memory/Redis），create_app docstring 明示可组合「SQL 持久 + Redis 传输」。
- **agentscope-java**：AgentStateStore 三元组 + **CAS 乐观并发**（getVersioned/saveIfVersion，冲突抛 ConcurrentSessionModificationException + ConflictPolicy）——比分布式锁更保守的多节点写冲突方案；跨节点子代理经 RemoteSubagentStub + SubagentRegistry。
- **adk-python**：SessionService 4 核心实现 + 2 集成包（InMemory/SQLite/Database-SQLAlchemy/VertexAi + integrations Firestore/Redis），事件溯源使「多副本 = 共享 session 表」即可成立；JVM 对位缺失是 adk-java 的已知短板（无 JDBC 后端）。
- **Dify**：postgres（真相）+ redis（队列/缓存/暂停命令通道，execution_coordinator 经 Redis 下发 stop）+ gunicorn 多 worker——HA 就是 compose 服务各自多副本。
- **MS / spring-ai / langchain4j / openai-agents / claude-sdk / crewai OSS**：框架层无 HA 叙事（前者交 Azure、Spring 交 Boot 生态、后者交宿主）。

### 派系 D：容器化产物在不在仓库

| 框架 | Dockerfile | docker-compose | Helm |
|---|---|---|---|
| dify | docker/ 全套（含 ssrf_proxy/nginx/certbot 配置）| ✅（12+ 服务）| ❌（社区外部仓 ⚠️）|
| agentscope-java | ✅（service/docker/）| ✅（agentscope-service/docker-compose.yml）| ✅（helm/agentscope-service/）+ deploy/ + release/ runbook |
| adk-java | dev 模块内嵌部署逻辑；AgentEngine 部署器生成物在外 | ❌ | ❌ |
| langgraph | cli 生成 docker-compose（引用闭源镜像）| 生成物非仓库自带 | ❌ |
| 其余 13 家 | 仅测试用（如 claude-sdk Dockerfile.test）或无 | ❌ | ❌ |

agentscope-java 是唯一「Docker + compose + Helm + 发布 runbook + 流量网格连接器（aistio 含自己的 helm）」五件齐全的框架——云原生交付成熟度 Java 服务化框架 > 低代码平台（Dify）> 其余。

## 14.3 跨语言对齐

| 对 | Python 侧 | Java 侧 | 差异要点 |
|---|---|---|---|
| langgraph ↔ langgraph4j | 🟡 cli dev server（拉起闭源 langgraph-api 镜像的 compose 生成器）+ RemoteGraph 连平台 + 双语 SDK | 🟡 Studio 嵌入式进程内服务器（jetty/springboot），无独立 dev server | **RemoteGraph/Platform 概念 Java 全缺**（无远端图调用、无平台 SDK）；Python 的 dev server 会编排外部镜像，Java 的 Studio 是同进程 servlet——「部署」一词在两侧含义不同：Python 侧指向平台生态，Java 侧指向嵌入用户应用 |
| adk-python(2.9) ↔ adk-java(1.9) | ✅ CLI 全家桶（8+ 子命令）+ api_server FastAPI + to_a2a Starlette + Live 双向流 + Cloud Run/Agent Engine deployer | 🟡 dev 模块 Spring Boot（REST×7 + WS）+ `mvn google-adk:web` + AgentEngineDeployer | Python 面向「独立起服务/部署到云」全链路；Java 面向「嵌进 Spring 开发流」（Maven goal + YAML Config Agent 热重载是 Java 独有的「低代码调试」通道）。deploy 能力：Python 双 deployer（Cloud Run + Agent Engine）vs Java 单 deployer（Agent Engine）|
| agentscope(Python) ↔ agentscope-java | ✅ create_app 单体 FastAPI 工厂（可 mount）+ Redis MessageBus + apscheduler cron + 3 渠道 | ✅ 三进程 service（Gateway/DataPlane/Scheduler）+ React 前端 + Helm + aistio + 11 starter + quartz/xxl-job + 5 渠道 | **架构形态代差**：Python 是「单应用多路由」，Java 是「控制平面/数据平面分离」；调度：apscheduler vs quartz/xxl-job（后者是企业既有调度体系的接入件）；渠道：钉钉/飞书/Discord vs 钉钉/飞书/企微/GitHub/GitLab；Java 独有 Go 写的 aistio 流量连接器。Python 侧无 Docker/Helm，Java 五件齐全 |

## 14.4 取舍与趋势

1. **「部署」的边界正在从运行时移向编排面**：langgraph（生产 server 闭源）、crewai（deploy/triggers 是付费平台 REST 客户端）、openai-agents（tracing 默认外发 OpenAI 平台）三家把生产运行时放在商业侧、仓库里只留客户端协议；而 adk-python（CLI + deployer 全开源）与 agentscope-java（Helm + 三进程全开源）押注相反方向。同一「🟡/✅」评级背后的商业模式差异比能力差异大。
2. **异步执行的两种范式都没有收敛迹象**：外部队列派（Dify celery 分级队列 + CFS、agentscope-java xxl-job）复用运维熟悉的调度基础设施，换弹性与可观测；引擎内 durable 派（langgraph 超步 checkpoint、MS Runner 每 superstep 落盘、openai-agents RunState 快照）把可恢复性做进执行语义。MS 的 durable-Azure-Functions 外置（ADR-0032 二次核验）说明连「框架该不该自带 durable 托管」在微软内部也是否定答案——重型托管依赖独立生命周期。
3. **多副本 HA 的最小公分母是「外部状态存储 + 无本地真相」**：checkpointer（langgraph 系）/ SessionService（adk）/ AgentStateStore+CAS（agentscope-java）/ postgres+redis（Dify）殊途同归；agentscope-java 的 CAS 乐观并发（saveIfVersion + ConflictPolicy）是唯一把「多节点写冲突」提升为框架显式语义的，其余框架默认单写者或交给 DB 行锁。
4. **定时任务是企业落地的暗门槛，多数框架缺席**：只有 Dify（节点级触发器 + beat）、agentscope 双语（cron 路由 / CronDeploymentScheduler + quartz）、spring-ai-alibaba（CompiledGraph#schedule）、deepagents talon（实验）四家半有正式 cron 抽象；langgraph 的 cron 客户端指向闭源平台、crewai 指向付费 AMP——「常驻/周期性 agent」恰是 2026 年 agent 的主形态，这块留白是选型时最容易被低估的差异。
5. **容器化成熟度与「框架是不是平台」强相关且不成比例**：agentscope-java（五件套）> Dify（compose 无 Helm）> 其余为零——纯库框架一致的「零 Dockerfile」不是疏忽而是定位声明：部署单元是宿主应用。唯一越位的是 adk-python，作为「全代码框架」却给了 deploy CLI（生成 Cloud Run/Agent Engine 配置），把部署当 DX（开发者体验）而非平台功能。
