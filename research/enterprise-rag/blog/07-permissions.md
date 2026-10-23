# 开源 RAG 平台都不敢做的事：文档级权限与检索期过滤

> 本文事实基于 2026-10 冻结的开源源码基线与当日可访问的官方文档，源码基线 commit 见文末参考节。

把知识库接进 Agent 之前，安全团队通常会问一个让选型会冷场的问题：「这份文档只有财务组能看，Agent 检索的时候保证它不会出现在别人的上下文里吗？」

这不是刁难。企业内部知识天然带权限：薪酬制度、未公开的并购材料、按部门隔离的合规文件。一个 RAG 系统如果只能做到「登录的人搜得到所有东西」，它在企业里能接的数据源就被砍掉一大半。而这一期我想说的是一个不太舒服的结论：**我逐源码核对过的五个主流开源 RAG 平台，权限粒度没有一家做到「文档」这一级**。这不是某家的偷懒，是行业性的实现缺口——而且恰好在托管服务那里成了核心卖点。

先把话说清楚：不是说这些平台不能用于生产。它们的权限模型（知识库级、工作区级）覆盖了很多场景。但如果你的需求是「谁能看到哪一份文档，并在检索结果里被强制过滤」，这件事在当前的开源生态里就是自研必答题。本文把五家的实锤、SSO 的三种假象、过滤的正确位置、托管服务的可抄模式和自研最小集一次讲完。

## 一、五家平台逐一验尸：权限粒度止步在哪一级

判断一个平台的权限粒度，不要看官网功能矩阵，看两样东西：权限模型的**资源枚举里有没有 document**，以及检索入口**有没有逐请求的权限校验**。以下每一条都对到了源码。

### ragflow：策略引擎是真做了，但资源枚举里没有 document

ragflow 社区版（CE）的权限体系是五家里含金量最高的一块。先看租户模型：`tenant` + `user_tenant` 多对多（角色 owner/admin/normal/invite，见 `internal/permission/policy_ce.go#membershipSatisfies`），用户可属多租户，知识库挂在租户下。策略层在 `infiniflow/ragflow@deb1235be internal/permission/policy_ce.go`（build tag `//go:build !enterprise`）实现了一套资源级的策略引擎——资源可见性三档 `private / tenant / shared`，shared 支持按用户（`SharedWithUserIDs`）和按租户（`SharedWithTenantIDs`）共享；列表场景不靠 UI 过滤，`Scope()` 返回允许的资源 ID 集合供查询下推。而且检索入口是真的查权限：`internal/handler/dify_retrieval_handler.go:219` 调 `CheckAccess(subject, datasetID, OperationUse)`，上传文档入口 `internal/handler/document.go:1007` 要求 `OperationUpdate`。

但看资源类型定义 `internal/permission/types.go:46-48`：只有 `dataset / canvas / agent_session` 三种——**没有 document**。权限最小粒度是知识库。同一个库里的《公司通讯录》和《高管薪酬方案》，在策略引擎眼里是同一个资源。

### dify：止步 dataset 三档，SQL 层下推是真的，文档级 ACL 没有

dify 的 dataset 权限模型很清晰：`langgenius/dify@79effdd498 api/models/dataset.py:184` 的 `permission` 字段枚举 `only_me / all_team / partial_members`，partial_members 落 `dataset_permissions` 表（dataset.py:1344-1363）。可见性过滤也做在了正确的地方——`api/services/dataset_service.py:262-332` 的 `get_datasets` 在 SQL where 条件里下推 `(permission==ALL_TEAM) or (created_by==me) or (id in permitted_dataset_ids)`，不是 UI 层过滤。

但粒度同样止步 dataset：document 模型没有 permission 字段，同一 dataset 内所有文档、所有 chunk 对可见者一视同仁。还有一个容易踩的点：应用侧检索走 `app_dataset_join`（应用绑定哪些库），权限模型是「应用级」而非「用户级」——多个用户共用一个应用时，检索权限跟人无关，跟应用绑定有关。

### anything-llm：止步 workspace，进了门就是一家人

`Mintplex-Labs/anything-llm@2a10d052 server/models/workspace.js:294` 的 `getWithUser`：非 admin/manager 用户只能取到 `workspace_users` 里有自己的工作区（Prisma where 下推，服务端强制），`server/utils/middleware/validWorkspace.js` 在所有工作区路由前置执行，向量检索按工作区隔离命名空间。工程上是干净的。但进了工作区的成员看得到该区**全部**文档——没有知识库内细分，更没有文档级 ACL。

### quivr：止步 corpus，而且根本没有「人」

quivr（2026-09 重写为 Go 的版本）的隔离边界是 `The-Vibe-Company/quivr@67a6c0e9f internal/corpus/corpus.go:29` 的 `Scope{Organization, Actions, Corpora}`——注意这个模型里**没有用户表**。认证是部署时静态配置的 Bearer API key 映射到 Scope（`internal/transport/httpapi/api.go:169` 查表）。key 可以限定读写动作和 corpus 白名单，这是 key 级 ACL，不是人级。对一个检索引擎来说这是设计选择而非缺陷，但直接当「企业知识库」用，就缺了整层人的维度。

### kotaemon：无权限模型

`Cinnamon/kotaemon@9ad3e4e4` 的用户表 `libs/ktem/ktem/db/base_models.py:47-64` 只有 username/password/admin bool。知识库全局共享，所有登录用户可检索全部知识库；admin 控制的是「管理页签是否可见」——`libs/ktem/ktem/main.py:156-163` 里是 Gradio 的 `gr.update(visible=is_admin)`，**UI 层开关**；唯一的访问控制是聊天记录的 is_public。它的定位是个人/小团队 UI，拿企业标准苛求不公平，但在「选型企业级 RAG」的语境下必须如实标注。

### 汇总

| 平台 | 权限粒度 | 检索期逐请求校验 | 文档级 ACL |
|---|---|---|---|
| ragflow CE | dataset（KB） | 有（KB 级） | ❌ 资源枚举无 document |
| dify OSS | dataset 三档 | 有（SQL 下推） | ❌ document 无 permission 字段 |
| anything-llm | workspace | 有（中间件） | ❌ |
| quivr | corpus（key 级） | 有（scope 中间件） | ❌ 且无用户实体 |
| kotaemon | 无 | ❌ | ❌ |

「细粒度权限」是开源 RAG 宣传里最容易被当真的词。验证方法本文已经示范：去 policy 资源枚举里找有没有 document/chunk 类型——没有，就是没有。

## 二、SSO 的三种假象

文档级权限之外，「对接企业 IdP」是第二个宣称与实现落差的重灾区，而且各有各的假法。

**假象一：配置文件里有，构建产物里没有。** ragflow CE 的 `conf/service_conf.yaml:195-210` 摆着 OAuth2/OIDC 配置模板，看起来开箱即用。但看 handler：`internal/handler/user_auth_ee.go:26-77` 里 `OAuthCallback / GitHubAuthCallback / LarkAuthCallback / ICBCAuthCallback / AzureAuthLogin / GetLoginChannels` **全部返回 `CodeNotImplemented "not implemented"`**。这些 handler 属于 EE 构建替换件，开源仓库里的 `internal/dao/*_ee.go`（billing/tenant/user 等八个文件）也是只有 license 头的空壳。CE 构建下认证只有本地账号（邮箱/密码注册登录）。需要说明：EE 版闭源，其真实能力面只能从 stub 和 CE 策略代码反推，本文不对其下结论——但「社区版自带 SSO」这个预期可以放下了。

**假象二：代码里有 RBAC 服务，实现是一堵 HTTP 墙外的闭源服务。** dify 的 `api/commands/rbac.py` 负责把 legacy 角色迁移到 RBAC，`api/services/enterprise/rbac_service.py` 有 2335 行——但它的本质是**调用外部闭源服务 dify-enterprise 的 HTTP 客户端**（`api/services/enterprise/base.py:38-39` 明写请求头与闭源侧 `rbac_inner_handlers.go` 对齐）。`feature_entities.py:103-105` 定义了 SAML/OIDC 协议枚举，但配置只能从 enterprise 侧下发。也就是说：纯 OSS 部署拿到的是传统 5 角色 + dataset 三档权限，无 SSO/SAML/LDAP。

**假象三：名字里有 SSO，实现是 token 桥接。** anything-llm 的 "Simple SSO"（`simpleSSOEnabled.js`）实际是管理员用 API key 换发临时登录 token 的桥接方案，面向嵌入式场景，不是企业 IdP 对接协议。

补一句 LDAP：五家开源版全部没有（ragflow 全仓无匹配、dify 官网列在企业版、其余三家连提都没提）。如果你的企业用户体系在 AD 里，别在这件事上指望开源版。

一个反向例证：五家里唯一给了协议级 SSO 样板的反而是最不像企业产品的 kotaemon——`sso_app.py` 用 gradiologin 走 OIDC（Google 或 Keycloak）。虽然它要换成独立启动入口、且默认管理员是 admin/admin（改密码靠自觉），但至少证明这件事在开源里不是做不了。

## 三、过滤的正确位置：在「返回给 LLM 组 prompt 之前」

假设你已经有了文档级 ACL 表，接下来的工程问题是：过滤发生在链路的哪一环？答案有一条红线——**必须在检索结果返回给 LLM 组装 prompt 之前**。在这之后过滤（比如生成完了再检查），越权内容已经进过上下文，日志、缓存、prompt 消费方都可能留下痕迹；在「rerank 之后、组 prompt 之前」过滤则已经太晚了一半——你会先付了 rerank 的算力还可能污染排序。落地上有两条路线：

**路线 A：前置过滤（推荐主路线）。** 把「当前用户允许的 doc_id 集合」转成检索引擎的标量过滤条件，让引擎在召回阶段就只碰有权的 chunk。引擎侧能力是现成的：

- milvus：schema 字段标 `is_partition_key`，引擎在 search 时从布尔表达式提取 partition key 并哈希路由（`milvus-io/milvus@55b4415230 internal/proxy/dql/task_search.go:1429-1430` 的 `AssignPartitionKeys`），tenant 隔离可下推为物理分区；另有 PartitionKeyIsolation 强化单租户分区排他（`internal/querycoordv2/task/utils.go:366`）。普通标量过滤同样可用。
- qdrant：单 collection + payload 租户字段过滤是官方推荐姿势，v1.11+ 可对该字段设 `is_tenant=true` 聚簇存储（官方多租户指南，非仓库内源码）；官方还建议多租户下用 `m=0 + payload_m` 让每租户有独立 HNSW 图，并提醒 BM25 的 IDF 会被跨租户语料混淆（v1.19+ 可用 `idf` 参数限定语料）。
- ES：bool filter 加 term/terms 子句是常规操作，ragflow 的中文混合检索本来就跑在 ES 上（引擎通用能力，未做源码级验证）。

前置过滤的代价是 ACL 查询本身要快（组展开、大 IN 列表），以及权限变更要能反映到检索侧——这是后面增量同步要解的事。

顺带纠正一个常见误会：有人把「做不了文档级权限」归咎于向量库地基不行，事实恰恰相反。五家平台全部把租户隔离做在**应用层的库表**上（dataset/workspace/corpus 归属），检索时由应用拼过滤条件或按租户分 collection/namespace；milvus/qdrant 甚至为此专门做了产品化特性（partition key 路由、is_tenant 聚簇）。**地基是够用的，缺的从来不是地基，是地基之上的文档 ACL 与查询级审计。**

**路线 B：后置过滤（兜底）。** chunk 元数据带 doc_id，检索结果在 rerank **之前**按 ACL 集合过滤。缺点是召回配额被浪费（top 100 里可能只剩 30 条有权的结果），大 ACL 集合下效果抖动；优点是实现侵入小，不改检索请求。合理的用法是作为纵深防御的第二层：主过滤用前置，后置作为兜底断言（「进 prompt 的每个 chunk 必须过一次 ACL 检查」），两层都过才算闭环。

无论哪条路线，都别做「应用层 post-trim」——先取回大结果集再在应用里裁剪，既慢又容易在裁剪前的日志里漏内容。这个坑 Azure 官方文档也点名过（见下节）。

## 四、托管服务怎么做的：一个可以照抄的闭环

文档级权限恰是托管服务对开源的降维打击点。Google 与 Microsoft 都把它做成了产品闭环，模式值得整体抄。以下为官方文档口径（2026-10-15 可访问），非源码级；云文档时效性强，采用前建议重核当前版。

**Google（Vertex AI Search，已更名 Agent Search）：文档级 ACL 原生内置（GA）。** 数据模型层面，Document 带 `acl_info.readers.principals`（user_id / group_id 列表），随文档一起摄入索引；官方示例就是「Space→Page 层级、不同 readers」的文档树。身份侧连接企业 IdP，GCS/BigQuery/SharePoint 连接器负责同步源系统 ACL。查询时带上用户身份做过滤，而且顺序是**先裁剪再增强**——LLM 摘要、语义重排发生在 ACL 过滤之后，保证增强环节接触到的只剩有权内容。数据刷新走 EntityRefresh 定时重爬。

**Microsoft（Azure AI Search）：四条路线并行，官方文档直接对比。**

1. **Security filters（GA）**：索引加 `Collection(Edm.String)` 安全字段（filterable=true、retrievable=false），查询用 `group_ids/any(g: search.in(g, 'id1,id2'))` 过滤。官方强调 `search.in` 比一串 `or eq` 快到**亚秒级**。但要清醒：本质是字符串匹配，官方原话「There's no authentication or authorization through the security principal」——身份来源、ACL 灌入、刷新全靠应用自己（官方 azd 模板配 `manageacl.py`，从 Entra ID token 的 `oids`/`groups` claims 取组）。
2. **POSIX-like ACL / RBAC scopes（preview）**：ADLS Gen2/Blob 的 ACL/RBAC 由 indexer 摄入索引；查询请求头 `x-ms-query-source-authorization` 带用户 Entra token，**引擎内**提取 claims 与索引内权限元数据比对裁剪。官方明说引擎内 enforcement 比应用侧 post-trim 快，并免掉嵌套组解析、ACL 遍历的自研代码。
3. **SharePoint ACLs（preview）**：indexer 抽取 SharePoint 权限元数据做查询时检查；2026-05-preview 起支持权限项级的增量同步。
4. **Purview 敏感度标签（preview）**：按标签+策略过滤。

把两家抽象一下，可抄的闭环就三句话：**ACL 随索引摄入（权限是索引字段，不是外挂表）＋查询时引擎内过滤（勿 post-trim）＋权限增量同步（源系统 ACL 变更要追平索引）**。自建的等价物：ACL 表为真相源、冗余进检索引擎的标量字段、查询注入用户组过滤、后台任务监听 IdP/源系统权限变更做增量刷索引。风险提示：Azure 原生 ACL 三条路线目前都是 preview（GA 的只有字符串 security filter），Google 侧是 GA——选型时按此计风险。

微软 Foundry 的 RAG 概念文档还给了两条配套口径，值得一并抄走：一是 "Apply access control at retrieval time"——权限控制的时机锚定在检索期，而不是文档浏览期（浏览界面看不到 ≠ 检索不到）；二是生产环境用 Entra ID 身份而非 API key，并且**把检索内容当不可信输入做防注入**。这最后一条值得展开一句：本轮源码核对里，五家开源平台无一有 prompt injection 防护代码——权限过滤把越权内容挡在上下文之外，注入防护则要防「有权但恶意」的内容攻击 Agent，两件事都得自研。

## 五、自研最小集清单

既然要补，就按「企业内部使用、对员工提供服务」的基准列一份最小集。每项我都标注了可以直接抄的样板。

**1. 文档级 ACL 表 + 检索期过滤。** 最大缺口，五家全无。表设计很朴素：`doc_acl(doc_id, principal_type[user/group], principal_id, permission[read]`，外加 chunk 元数据带 doc_id 映射；组展开用 IdP 的组关系，展开结果给检索层做前置过滤（路线 A）+ 进 prompt 前断言（路线 B 兜底）。别忘了定期校验「ACL 表 ↔ 索引内权限字段」的一致性——增量同步漏刷是这个模式最常见的事故源。

**2. 查询级审计（谁、何时、查了什么、返回了哪些来源）。** 这块开源给了三块好料可以拼：dify 的 `dataset_queries` 表（`api/models/dataset.py:1124`，检索时由 `api/core/rag/retrieval/dataset_retrieval.py:1125` 写入，含 created_by）解决「谁查了哪个库」；anything-llm 的 `event_logs`（`server/models/eventLogs.js`，event/metadata/userId，覆盖登录成败、API 调用、文档上传、导出）是五家里唯一在开源版有完整登录+查询+导出事件流的；quivr 的 `migrations/20261006T0039Z_audit_events.sql` 值得整体搬——audit_events 表含 actor/action/target/outcome/request_id/detail(jsonb)，DB 触发器禁止 UPDATE/DELETE/TRUNCATE（append-only），唯一删除路径是 SECURITY DEFINER 的 `prune_audit_events(retention_months, batch_size)`，保留期 1-1200 个月可配。注意 quivr 的审计范围明确**不含读和检索**（`internal/transport/httpapi/audit.go:31-33` 注释原话「reads, searches, push delivery and ingestion do not create audit events」），actor 是 key 哈希——把它的防篡改设计和 dify/anything-llm 的表结构拼起来，才是完整的「查询级审计」。

**3. 凭据治理。** 五家里只有 dify 做了凭据加密落库：`api/core/helper/encrypter.py` 用租户 RSA 公钥加密模型 API key（`api/models/account.py:261` Tenant.encrypt_public_key）——唯一的正面样板。反面教材是 ragflow：`internal/entity/tenant_llm.go:27` 的 `api_key;type:text` 明文存库；anything-llm 的 key 也是明文走 system_settings 表和 .env。自建请统一走 KMS / secret manager，别让「能查库就能拿走所有租户的模型 key」。

**4. 配额与成本分摊。** 五家里只有 anything-llm 有每用户配额：`server/endpoints/chat.js:61` 按用户 24 小时聊天条数上限（`users.dailyMessageLimit`）。按部门摊 token/存储成本需要自建计量+配额表+中间件拦截，开源没有现成的。

**5. 出墙体检。** 上线前必查数据外发。dify 社区版遥测**默认开启**：`api/configs/feature/__init__.py:840` `DISABLE_TELEMETRY: bool = default(False)`，上报 `https://otel.dify.ai/v1/events`，心跳任务每 30 分钟一次，payload 含 instance_id、OS、arch 及应用增删事件——私有化部署清单第一件事应是 `DISABLE_TELEMETRY=true`。anything-llm 的 PostHog 同样默认开（`server/models/telemetry.js:49-53`，`DISABLE_TELEMETRY=true` 关闭；官方声明不含 PII/文档内容/聊天记录，具体上报端点按 posthog-node 默认行为推断、未抓包验证）。ragflow/quivr/kotaemon 未发现出墙点。

**6. 协议级 SSO。** 前面已经拆完假象，补法是标准做法：平台前面加 OAuth2 proxy 或 Keycloak，平台内保留本地账号做 fallback；只有 kotaemon 的 gradiologin + OIDC 可作参考实现。

收个尾，给一份上线前治理体检清单（全部来自前文的源码证据，可直接当 checklist 用）：① `DISABLE_TELEMETRY=true`（dify、anything-llm，第一件事）；② 确认所用构建里 SSO handler 不是 stub（ragflow CE 的 user_auth_ee.go 就是反面教材）；③ 检索链路加「进 prompt 前必有 ACL 断言」；④ 审计表挂 append-only 触发器并覆盖读/检索（quivr 的触发器 + 补上它没做的查询审计）；⑤ 模型凭据出库走加密（以 dify encrypter 为样板）；⑥ license 附加条款过一遍法务（重点是 dify）；⑦ EE 能力宣称按 stub 反推、不轻信——闭源部分本文同样无法验证。

## 六、License 边界速查表

治理能力之外，「这个仓库企业能用到什么程度」是另一个被问烂的问题。逐仓核过 LICENSE 后的速查：

| 仓库 | License | 企业内用边界 |
|---|---|---|
| ragflow (CE) | Apache 2.0（无附加条款） | 内用/修改/二次发布都行；但 SSO/审计/配额在闭源 EE，别指望 |
| dify | 修改版 Apache | **多租户对外服务（多 workspace 对外运营）需商业授权**；前端 LOGO/版权信息不可移除；内部单 workspace 自用+修改 OK |
| anything-llm | MIT | 随意；另有 TERMS_SELF_HOSTED.md 数据主权声明，明确支持 air-gap |
| quivr | MIT | 随意 |
| kotaemon | Apache 2.0 | 随意 |

dify 那两条附加条款值得展开一句：LICENSE 原文 (a) 用 dify 源码做多租户环境对外服务必须书面授权；(b) 前端（web/ 目录）LOGO 与版权信息不可动——不用它的前端则不受限。另外贡献条款写明 LangGenius 可将贡献代码用于商业用途。ragflow 的 README 宣称 "adaptable to enterprises of any scale"，配合上一节的 EE stub 实锤食用，你该知道这句话的含金量了。

## 结语

这一篇的结论单刀直入：权限是开源 RAG 与「企业级」之间的那道墙。五家平台在租户、知识库、工作区这些层级做得认真甚至出色（ragflow 的策略引擎、dify 的 SQL 下推、quivr 的防篡改审计都是好料），但「谁能看哪份文档、检索时强制过滤」这件事全行业缺位，托管服务拿它当核心卖点收钱。好消息是自研面并不大：一张 ACL 表、一个过滤位置纪律（组 prompt 之前、引擎内、别 post-trim）、一条增量同步管道，加上审计/凭据/出墙三个体检项。这些都是有明确样板可抄的工程活，不是研究难题。

下一篇我们从「谁能看」转向「看得好不好」：五个平台自带的评测功能为什么只是调试器，ragas 的 faithfulness 到底怎么算，以及怎么给中文场景搭一套能进 CI 的评测防线。

## 参考与出处

源码基线（2026-10 冻结）：`infiniflow/ragflow@deb1235be`、`langgenius/dify@79effdd498`、`Mintplex-Labs/anything-llm@2a10d052`、`The-Vibe-Company/quivr@67a6c0e9f`、`Cinnamon/kotaemon@9ad3e4e4`、`milvus-io/milvus@55b4415230`。正文中的相对路径均相对上述基线。

**ragflow**
- https://github.com/infiniflow/ragflow/blob/deb1235be/internal/permission/types.go （资源枚举 dataset/canvas/agent_session，无 document）
- https://github.com/infiniflow/ragflow/blob/deb1235be/internal/permission/policy_ce.go （CE 策略引擎）
- https://github.com/infiniflow/ragflow/blob/deb1235be/internal/handler/user_auth_ee.go （OAuth handler 全部 not implemented）
- https://github.com/infiniflow/ragflow/blob/deb1235be/internal/handler/dify_retrieval_handler.go （检索入口 CheckAccess）
- https://github.com/infiniflow/ragflow/blob/deb1235be/internal/entity/tenant_llm.go （api_key 明文存库）

**dify**
- https://github.com/langgenius/dify/blob/79effdd498/api/models/dataset.py （permission 三档枚举与 dataset_permissions 表）
- https://github.com/langgenius/dify/blob/79effdd498/api/services/dataset_service.py （get_datasets SQL 下推过滤）
- https://github.com/langgenius/dify/blob/79effdd498/api/services/enterprise/rbac_service.py 与 https://github.com/langgenius/dify/blob/79effdd498/api/services/enterprise/base.py （闭源 enterprise HTTP 客户端）
- https://github.com/langgenius/dify/blob/79effdd498/api/configs/feature/__init__.py （telemetry 默认开启）
- https://github.com/langgenius/dify/blob/79effdd498/api/core/helper/encrypter.py （凭据加密）

**anything-llm**
- https://github.com/Mintplex-Labs/anything-llm/blob/2a10d052/server/models/workspace.js （getWithUser 成员过滤）
- https://github.com/Mintplex-Labs/anything-llm/blob/2a10d052/server/models/eventLogs.js （审计事件表）
- https://github.com/Mintplex-Labs/anything-llm/blob/2a10d052/server/endpoints/chat.js （每用户日配额）
- https://github.com/Mintplex-Labs/anything-llm/blob/2a10d052/server/models/telemetry.js （PostHog 默认开启）

**quivr**
- https://github.com/The-Vibe-Company/quivr/blob/67a6c0e9f/internal/corpus/corpus.go （Scope 模型）
- https://github.com/The-Vibe-Company/quivr/blob/67a6c0e9f/migrations/20261006T0039Z_audit_events.sql （append-only 审计与触发器）
- https://github.com/The-Vibe-Company/quivr/blob/67a6c0e9f/internal/transport/httpapi/audit.go （审计范围注释）

**kotaemon**
- https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/libs/ktem/ktem/db/base_models.py （BaseUser）
- https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/libs/ktem/ktem/main.py （admin 为 UI visible 开关）

**milvus**
- https://github.com/milvus-io/milvus/blob/55b4415230/internal/proxy/dql/task_search.go （partition key 路由）
- https://github.com/milvus-io/milvus/blob/55b4415230/internal/querycoordv2/task/utils.go （PartitionKeyIsolation）

**License 与宣称原文**
- https://github.com/langgenius/dify/blob/79effdd498/LICENSE （多租户与前端 LOGO 附加条款）
- https://github.com/infiniflow/ragflow/blob/deb1235be/LICENSE 与 https://github.com/infiniflow/ragflow/blob/deb1235be/README.md （Apache 2.0 无附加；"adaptable to enterprises of any scale"）
- https://github.com/Mintplex-Labs/anything-llm/blob/2a10d052/LICENSE 与 https://github.com/Mintplex-Labs/anything-llm/blob/2a10d052/TERMS_SELF_HOSTED.md （MIT + 数据主权声明）
- https://github.com/The-Vibe-Company/quivr/blob/67a6c0e9f/LICENSE 与 https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/LICENSE.txt （MIT / Apache 2.0）

**官方文档（2026-10-15 可访问，非源码级）**
- Google Document acl_info：https://docs.cloud.google.com/generative-ai-app-builder/docs/reference/rpc/google.cloud.discoveryengine.v1
- Azure 文档级权限四路线：https://learn.microsoft.com/azure/search/search-document-level-access-overview
- Azure security filter 与 search.in：https://learn.microsoft.com/azure/search/search-security-trimming-for-azure-search
- qdrant 多租户指南：https://qdrant.tech/documentation/guides/multiple-partitions/

## 系列目录

《给 Agent 造知识库：企业级 RAG 搭建手记》

1. 企业级 RAG 全景：一篇文档到一段回答之间发生了什么
2. RAG 的第一道生死线：中文文档解析怎么做
3. 分块与索引：结构感知切分、双路索引与 schema 设计
4. 检索引擎选型对比：ES、milvus、pgvector、qdrant 与嵌入式方案
5. 检索算法：混合检索、融合公式与重排的正确姿势
6. 让答案可信：引用溯源的三种实现机制
7. 开源 RAG 平台都不敢做的事：文档级权限与检索期过滤（本篇）
8. 上线前后的质量防线：RAG 评测体系从零搭建
9. GraphRAG 与 Agentic RAG：什么时候该上，什么时候是过度设计
10. 实战设计：Python 自建轻量知识库服务，给 deepagents 供数

下一篇（第 8 篇）拆评测：dify 的 hit testing 为什么只是召回调试器，ragas 的 faithfulness 如何用「陈述分解 + NLI 逐条验证」算出来，以及中文场景上线前必须做的 50 条人工校准。
