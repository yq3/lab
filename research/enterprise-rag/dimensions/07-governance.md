# 维度 07：企业级治理（租户 / 权限 / 认证 / 审计 / 合规）

> 对象：`ragflow`（基线 deb1235be，2026-10 已是 Go 重写架构：服务端在 `internal/`，Flask `api/` 已不存在）、`dify`（79effdd498，v1.17.1）、`anything-llm`（2a10d052）、`quivr`（67a6c0e9f，Go 重写版）、`kotaemon`（9ad3e4e4）；多租户基建参照 milvus（partition key）与 qdrant（payload multitenancy）。
> 问题意识：「企业级」是开源 RAG 平台被宣传淹没最严重的词。本文逐平台对码回答：租户模型长什么样、文档级权限是不是真的在检索层过滤、SSO 是开源版有还是商业版才有、审计/配额有没有代码、私有化部署有没有数据出墙点、license 允许企业用到什么程度。**宣称与实现分开列**。

证据分级：【核心】= 数据表/模型/代码路径（最硬）；【示例】= 有实现但覆盖面有限；【文档】= README/官方文档宣称；❌ = 逐项查过、代码里没有；⚠️ = 有但弱或仅 UI 层。

## 1. 总表

| 治理能力 | ragflow (CE) | dify (OSS) | anything-llm | quivr (Go) | kotaemon |
|---|---|---|---|---|---|
| 租户层级 | 租户(tenant)+user_tenant 多对多，KB 属租户【核心】 | 租户(tenant)=workspace + 5 种成员角色 + dataset【核心】 | workspace + workspace_users，用户↔工作区多对多【核心】 | organization（API key 绑定，**无用户实体**）【核心】 | **无租户**：扁平 users 表（admin bool）【核心】 |
| KB 级权限 | ✅ private/tenant/shared + 按用户/租户共享，服务端策略引擎【核心】 | ✅ only_me/all_team/partial_members + dataset_permissions 表【核心】 | ⚠️ 工作区成员可见（admin 全可见），无 KB 内细分【核心】 | ⚠️ 仅 API key 级 scope（org+corpora+actions），无人维度 | ❌ 知识库全局共享，无权限模型 |
| **文档级权限（检索时过滤）** | ❌（权限粒度=dataset；policy 无 document 资源类型） | ❌（粒度=dataset；同一 dataset 内文档无 ACL） | ❌（粒度=workspace） | ❌（粒度=corpus） | ❌ |
| SSO/SAML/OIDC | ⚠️ conf 有 OAuth2/OIDC 模板但 handler 是 EE stub（"not implemented"）【核心】 | ❌ SAML/OIDC 枚举存在但实现全部外调闭源 dify-enterprise；OSS 仅 GitHub/Google OAuth 登录 | ❌ 无（"Simple SSO"=API 换临时 token，非协议级 SSO） | ❌ 无用户体系（静态 Bearer key） | ✅ OIDC（Google/Keycloak，gradiologin）【核心】 |
| LDAP | ❌ | ❌（EE 才有） | ❌ | ❌ | ❌ |
| 审计日志 | ❌ CE 无（仅 login audit 注释；EE stub） | ⚠️ dataset_queries 记检索、chat 记录；通用 audit_log 在 EE | ⚠️ event_logs 表（登录/上传/API 调用等轻量事件）【核心】 | ✅ audit_events 追加只读表+DB 触发器防篡改（但**不含查询**）【核心】 | ❌ |
| 配额 | ❌ CE 无（billing 全在 `*_ee.go` stub） | ⚠️ 限流（RateLimitLog）+ 系统模型 quota；租户/席位配额在 EE | ⚠️ 每用户 `dailyMessageLimit`【核心】 | ❌ | ❌ |
| License | Apache 2.0（CE）；EE 功能闭源替换 | 修改版 Apache：**多租户运营需商业授权** + 前端 LOGO 不可动 | MIT（另有 TERMS_SELF_HOSTED.md 数据主权声明） | MIT | Apache 2.0 |
| Telemetry 出墙点 | 未发现 phone-home（OTel 为自托管观测） | ⚠️ **默认开启**上报 otel.dify.ai（可 DISABLE_TELEMETRY）【核心】 | ⚠️ 默认开启 PostHog（DISABLE_TELEMETRY=true 关）【核心】 | 无出墙（OTel 自托管） | 无 |
| 离线部署 | ✅ compose 全本地镜像 | ✅（注意关 telemetry；插件市场默认离线不可用） | ✅ 明确支持 air-gap（本地模型+LanceDB）【文档】 | ✅ compose 全本地（TEI 嵌入本地化） | ✅ 单进程 Gradio |

## 2. 逐平台小节

### 2.1 ragflow：策略引擎是真做了，但「企业级」的一半锁在 EE stub 里

**租户模型**【核心】`internal/dao/tenant.go#TenantDAO.GetJoinedTenantsByUserID`：`tenant` + `user_tenant`（role: owner/admin/normal/invite，见 `internal/permission/policy_ce.go#membershipSatisfies`），用户可属多租户；KB（knowledgebase）挂在租户下。

**权限体系（社区版含金量最高的一块）**【核心】`internal/permission/policy_ce.go`（build tag `//go:build !enterprise`）实现了完整的资源级 ABAC-ish 策略：
- 资源类型 `dataset / canvas / agent_session`（`internal/permission/types.go:46-48`）——**注意没有 document 类型**，权限最小粒度是知识库；
- 资源可见性三档 `private / tenant / shared`，shared 支持 `SharedWithUserIDs`（按用户）和 `SharedWithTenantIDs`（按租户）；
- 操作集 `read/create/update/delete/share/run/use`，角色集 `owner/admin/normal/invite`；
- 列表场景不靠 UI 过滤：`Scope()` 返回 `ScopeIDs`（允许的资源 ID 集合）供查询下推，`FilterResources()` 做批量过滤；
- 检索入口真的查权限：`internal/handler/dify_retrieval_handler.go:219` 调 `kbSvc.CheckAccess(subject, datasetID, OperationUse)`；上传文档入口 `internal/handler/document.go:1007` 要求 `OperationUpdate`。这是「检索前置权限校验」（KB 级）的实锤。

**EE 拆分**【核心】全仓 8 个 `internal/dao/*_ee.go`（billing_product/billing_subscription/tenant/user_tenant/kb/search/task/user 等）在开源仓库里是 17-23 行的空壳（只有 license 头 + package 声明）；更实锤的是 `internal/handler/user_auth_ee.go:26-77`：`OAuthCallback / GitHubAuthCallback / LarkAuthCallback / ICBCAuthCallback / AzureAuthLogin / GetLoginChannels` 全部返回 `CodeNotImplemented "not implemented"`。**即社区版认证只有本地账号（邮箱/密码注册登录，`internal/handler/user.go#Register/Login`），conf/service_conf.yaml:195-210 里的 OAuth2/OIDC 配置模板在 CE 构建下不可用**。SAML/LDAP 全仓无匹配。

**审计/配额**：❌。CE 无审计表、无配额表（grep quota/audit 仅命中 login audit 注释与 wiki 编译预算等无关项）；billing 系列全在 EE stub。

**部署与出墙**【核心】`docker/docker-compose-base.yml`：es01/opensearch/infinity/serenedb/oceanbase/seekdb/vastbase（六选一的 doc store）+ mysql:8.0.40 + minio(兼容版 silo) + kvrocks + jaeger + nats + sandbox-executor-manager，全部本地镜像，无云依赖；Go 代码内未发现 phone-home（wikipedia.go 的 UA 字符串是唯一外部 URL 引用级别的东西）。OTel 配置（`internal/server/config/open_telemetry_config.go`）默认指向本地 jaeger。

**安全面**：上传有文件名长度（document.go:1017）与扩展名校验（`internal/service/document/` 管线中 "extension check (101)"）；模型 API key **明文存库**【核心】`internal/entity/tenant_llm.go:27`（`api_key;type:text`，无加密注解）；无 prompt injection 防护代码。

**License**：Apache 2.0 原版（LICENSE 文件无附加条款）；README:72 宣称 "adaptable to enterprises of any scale"，但如上，SSO/审计/配额全不在 CE。

### 2.2 dify：dataset 权限模型清晰，但「企业级」是一堵 HTTP 墙外面的闭源服务

**租户模型**【核心】`api/models/account.py`：`Tenant`（= workspace）+ `TenantAccountJoin`（角色枚举 `TenantAccountRole`：owner/admin/editor/normal/dataset_operator，account.py:21-27）；`Dataset` 属租户，`api/models/dataset.py:184` 的 `permission` 字段枚举 `only_me / all_team / partial_members`，partial_members 落 `dataset_permissions` 表（dataset.py:1344-1363，dataset_id/account_id/tenant_id + has_permission）。

**权限过滤实现位置**【核心】`api/services/dataset_service.py:262-332#get_datasets`：可见数据集查询在 **SQL where 条件里**按 `(permission==ALL_TEAM) or (created_by==me) or (id in permitted_dataset_ids)` 下推——不是 UI 层过滤；`check_dataset_permission`（dataset_service.py:1378）用于写操作与命中测试入口。**但粒度止步于 dataset**：同一 dataset 内所有文档、所有 chunk 对可见者一视同仁，无文档级 ACL（document 模型无 permission 字段）。应用侧检索走 `app_dataset_join`（应用绑定哪些库），权限模型是「应用级」而非「用户级」。

**RBAC 的真相**【核心】`api/commands/rbac.py` 把 legacy 角色迁移到 RBAC；但 `api/services/enterprise/rbac_service.py`（2335 行）本质是 **HTTP 客户端**，调用外部闭源服务 `dify-enterprise`（base.py:38-39 明写 header 与 `pkg/enterprise/service/rbac_inner_handlers.go` 对齐）。细粒度 RBAC、SSO（`feature_entities.py:103-105` 定义了 SAML/OIDC 协议枚举，但配置只能从 enterprise 侧下发）、workspace 成员配额（feature_service.py:122-127 从 EnterpriseService 拉取）全部如此。**纯 OSS 部署 = 传统 5 角色 + dataset 三档权限，无 SSO/SAML/LDAP**。

**审计与配额**：通用 audit log ❌（OSS 无 audit_logs 表）；检索有痕【示例】`dataset_queries` 表（dataset.py:1124，`core/rag/retrieval/dataset_retrieval.py:1125` 写入，含 created_by）可算「谁查了哪个库」的最小审计；RateLimitLog 做限流（rate limit per tenant，配置驱动），系统托管模型的 quota 字段在 `api/models/provider.py:64-68`（自托管自带 key 场景用不上）。

**部署与出墙**【核心】compose 服务全本地（api/worker/beat/web/sandbox/plugin-daemon/agent-backend/postgres/redis/squid，docker/docker-compose.yaml:229-728）。**最值得注意：社区版遥测默认开启**——`api/configs/feature/__init__.py:840` `DISABLE_TELEMETRY: bool = default(False)`，上报端点 `https://otel.dify.ai/v1/events`（:848），心跳任务 `api/tasks/community_telemetry_task.py` 每 30 分钟一次，payload 含 instance_id、OS、arch（telemetry_service.py:95）+ App 增删等事件（core/telemetry/events.py）。私有化部署清单第一件事应是 `DISABLE_TELEMETRY=true`。

**安全面**：上传三重限制（`configs/feature/__init__.py:449/459/545`：单文件大小、批次大小、扩展名黑名单）；无病毒扫描；无 prompt injection 检测（"injection" 命中的是 CSV 导出防公式注入 `core/helper/csv_sanitizer.py` 与 trace header 注入防护）；模型凭据加密存储【核心】`api/core/helper/encrypter.py`（租户 RSA 公钥加密，`models/account.py:261` Tenant.encrypt_public_key），是五家里唯一做凭据加密落库的。

**License**【核心】`LICENSE` 原文两条附加条件：(a) **用 dify 源码做多租户环境（多 workspace 对外服务）必须书面授权/商业许可**；(b) 前端（web/ 目录）LOGO 与版权信息不可移除修改（不用其前端则不受限）。另外贡献条款：LangGenius 可将贡献代码用于商业用途。→ 「企业内部单租户自用+修改」OK；「基于 dify 对外提供多租户 SaaS」越线。

### 2.3 anything-llm：治理最薄的 MIT 全家桶，但边界诚实

**租户模型**【核心】`server/prisma/schema.prisma`：`users`（role: "admin"/"default"，suspended，**dailyMessageLimit Int?**）+ `workspaces` + `workspace_users` 多对多。无组织层。

**权限实现**【核心】`server/models/workspace.js:294#getWithUser`：非 admin/manager 用户只能取到 `workspace_users` 里有自己的工作区（Prisma where 下推，服务端强制）；`server/utils/middleware/validWorkspace.js#validWorkspaceSlug` 在所有工作区路由前置执行。向量检索按工作区隔离（每 workspace 独立向量命名空间）。**粒度=工作区**：进了工作区的成员看得到该区全部文档，无 KB 内/文档级权限 ❌。

**认证**：本地账号（密码哈希）+ 可选 OAuth 登录（GitHub/Google 等，`server/utils/middleware/` 未见 SAML/OIDC/LDAP 任何协议实现）。所谓 "Simple SSO"（`simpleSSOEnabled.js`）= 管理员用 API key 换发临时登录 token 的桥接方案，供嵌入式场景，不是企业 IdP 对接。

**审计**【示例】`server/models/eventLogs.js`：event_logs 表（event/metadata/userId），记录 login_event、failed_login_invalid_password、api_sent_chat、api_document_uploaded、exported_chats 等——五家里唯一在开源版有「登录成败+查询+导出」事件流的，但没有检索内容级审计与不可篡改保证。

**配额**【核心】`server/endpoints/chat.js:61`：按用户 24 小时聊天条数上限（users.dailyMessageLimit）——简单的按用户配额有代码。

**部署与出墙**：MIT + `TERMS_SELF_HOSTED.md` 明确声明 local-first、可 air-gap（本地 LLM+LanceDB 下完全离线）、CDN 只用于兜底下载 ONNX 模型【文档】。Telemetry 默认开（PostHog，`server/models/telemetry.js:49-53`，DISABLE_TELEMETRY=true 关），声明不含 PII/文档内容/聊天记录。

**安全面**：上传有 mimetype 白名单（音频/图像端点，`server/utils/files/multer.js:182/207`）与大小限制；无病毒扫描；模型凭据（OpenAI key 等）存 system_settings 表 + `.env`（updateENV.js），**明文** ⚠️；无 prompt injection 防护。

### 2.4 quivr（Go 重写版）：把「引擎级治理」做成了样板，但放弃了人

**租户模型**【核心】`internal/corpus/corpus.go:29`：`Scope{Organization, Actions, Corpora}`——**没有用户表**。migrations 全部 SQL（001_corpora.sql：`corpora(organization, id, ...)` 主键含 organization），多租户单位 = organization，认证 = 部署时静态配置的 Bearer API key 映射到 Scope（`internal/transport/httpapi/api.go:169`：`a.Keys[token]` 查表，`internal/app/run.go:82`：Keys 来自配置文件）。key 可以限定 actions（读写）和 corpora 白名单——这是 **key 级 ACL**，不是人级。

**权限过滤位置**：检索/管理 API 的隔离边界是 organization + key scope，在路由中间件完成；无用户/角色/文档级概念 ❌（对纯引擎来说这是设计选择而非缺陷，但直接当「企业知识库」用则缺一整层）。

**审计（五家里最认真）**【核心】`migrations/20261006T0039Z_audit_events.sql`：audit_events 表含 actor/action/target_type/target_id/organization/outcome(accepted|refused)/request_id/detail(jsonb)；**DB 触发器禁止 UPDATE/DELETE/TRUNCATE（append-only），唯一删除路径是 SECURITY DEFINER 的 `prune_audit_events(retention_months, batch_size)`**，保留期 1-1200 月（`internal/app/audit_config.go`）。审计覆盖面见 `internal/transport/httpapi/audit.go:31-33` 注释：**只有写操作入审计，「reads, searches, push delivery and ingestion do not create audit events」**——「谁查了什么」不在其中；actor 是 API key 的 sha256 前 16 字节（无自然人身份）。

**配额**：❌。**SSO**：❌（无用户体系）。**License**：MIT（The Vibe Company）。

**部署与出墙**：compose 全本地（postgres + temporal + seaweedfs + weaviate + TEI + quivr 本体，deploy/compose/compose.yaml），嵌入走本地 TEI，无出墙点；telemetry = OTel 自托管（internal/telemetry）。

**安全面（引擎级亮点）**【核心】`internal/netguard/netguard.go`：net.Dialer Control 钩子在 DNS 解析后对**实际拨号地址**拒绝私网/环回/链路本地地址（防 SSRF/DNS rebinding，connector 抓取外链时启用）；connector 凭据**落库加密**（`internal/connectors/credentials.go`：Sealed + Sealer，密钥按部署派生并绑定 Organization）；uploads 服务有 checksum+size 校验（internal/uploads/uploads.go:164）。

### 2.5 kotaemon：单页 Gradio 应用，治理零配置

**租户**：❌。`libs/ktem/ktem/db/base_models.py:47-64#BaseUser`：username/password(哈希)/admin bool，无组织/角色。**认证**：`flowsettings.py:74-82`：`KH_FEATURE_USER_MANAGEMENT` 默认开，**默认管理员 admin/admin**（改密码靠自觉）；SSO 是亮点——`sso_app.py` 用 gradiologin 走 **OIDC（Google 或 Keycloak）**【核心】，但要换成 sso_app 启动入口，属「有但没有和本地账号体系融合成企业级 IdP 管理」。

**权限**：❌。知识库（index）全局共享，所有登录用户可检索全部知识库；admin 只控制「管理页签是否可见」（`libs/ktem/ktem/main.py:156-163` `gr.update(visible=is_admin)`——**UI 层开关**）；唯一的访问控制是 conversation 的 is_public（聊天记录公开/私有，`db/base_models.py:34`）。检索链路无任何 per-user 过滤。

**审计/配额/出墙**：❌ / ❌ / 无（SQLite + 本地向量库起步，Apache 2.0）。定位就是个人/小团队 UI，不该用企业标准苛求，但在「选型企业级 RAG」语境下必须标 ❌。

### 2.6 参照：向量库层的多租户姿势（治理的「地基」能力面）

- **milvus**【核心】：schema 字段可标 `is_partition_key`，引擎在 search/query/delete 时从布尔表达式提取 partition key 并哈希路由到 partition（`internal/proxy/dql/task_search.go:1429-1430` `AssignPartitionKeys`、`task_query.go:940`）——即「tenant_id 字段 + 查询必带 tenant_id 过滤」可下推为物理隔离；另有 collection 属性 PartitionKeyIsolation（`internal/querycoordv2/task/utils.go:366`）强化单租户分区排他。
- **qdrant**【文档】（官方 multiple-partitions 指南，qdrant.tech）：默认单 collection + payload 租户字段过滤（v1.11+ 可对该字段设 `is_tenant=true` 聚簇存储）；大租户用 custom sharding（shard_key）；v1.16+ 分层多租户（小租户共享 fallback shard，约 >2 万点/租户时提升为专属 shard）；多租户下建议 `m=0 + payload_m` 每租户独立 HNSW；BM25 需注意跨租户 IDF 混淆（v1.19+ `idf` 参数限定语料）。
- **对上层的意义**：五家平台全部把「租户隔离」做在**应用层的库表**上（dataset/workspace/corpus 归属），检索时由应用拼租户过滤条件或按租户分 collection/namespace——向量库能力是够用的，缺的从来不是地基，是上面的 ACL 与审计。

## 3. 宣称 vs 实现落差清单

1. **ragflow「enterprise-ready」vs CE 认证**：conf 里摆着 OAuth2/OIDC 配置模板，README 宣称服务任意规模企业；但 CE 构建里 OAuth 全部 handler 返回 "not implemented"（`internal/handler/user_auth_ee.go`），SSO/审计/配额（billing）全在闭源 EE。开源仓库展示的是接口形状，不是能力。
2. **dify「SSO/RBAC/审计」**：官网功能矩阵把这些列在企业版；源码层面 OSS 仓库里它们只是「调用闭源 dify-enterprise 的 HTTP 客户端 + 协议枚举」，纯 OSS 部署实测拿不到。另外**社区版遥测默认开**且不在安装文档首屏强调——「开源自托管=数据不出门」的直觉在 dify 上不成立。
3. **anything-llm「Multi-User」**：多用户=工作区成员表，角色只有 admin/default 两档（middleware 里另有 manager）；知识库级/文档级权限没有；"Simple SSO" 名字有 SSO，实为 token 桥接，别按企业 IdP 预期。
4. **quivr「企业级审计」**：append-only + 防篡改触发器是真材实料，但审计范围明确排除读/查/检索——「谁查了什么」这个企业刚需它没有；且无用户体系，actor 是 key 哈希。
5. **「文档级权限」全行业缺口**：五家全部 ❌（ragflow/dify 到 dataset 级、anything-llm 到 workspace 级、quivr 到 corpus 级、kotaemon 无）。任何宣称「细粒度权限」的开源 RAG（含部分国产闭源产品）都值得按本文方法查一遍 policy 资源枚举里有没有 document/chunk 类型。
6. **kotaemon「multi-user & personalization」**：multi-user 是登录墙，personalization 指聊天记录与偏好，不涉及知识权限；admin 控制还是 Gradio UI 层 visible 开关。

## 4. 自建系统的治理最小集（必须自研/补齐清单）

以「企业内部使用 + 对员工提供服务」为基准，直接用上述开源件会缺：

1. **文档级 ACL + 检索期过滤**（最大缺口，五家全无）：可行路线 = 平台侧 ACL 表（doc→用户/组）+ 检索后置过滤（chunk 带 doc_id 映射，rerank 前过滤），或前置过滤（把允许 doc_id 集合转成向量库 metadata/payload filter——qdrant payload filter、milvus partition key/标量过滤都支持）。注意 chunk 命中→文档鉴权要在**返回给 LLM 组 prompt 之前**做，否则权限内容已进上下文。
2. **协议级 SSO（OIDC/SAML）+ LDAP**：只有 kotaemon 给了 OIDC 样板（gradiologin）；其余要自研或选 ragflow/dify 商业版。自建标准做法：平台前面加 OAuth2 proxy / Keycloak，平台内保留本地账号做 fallback。
3. **查询级审计**（谁、何时、查了什么、返回了哪些来源）：dify 的 dataset_queries 和 anything-llm 的 event_logs 可抄表结构，quivr 的 append-only 触发器设计（DB 层防篡改 + 定长保留）值得整体搬。
4. **租户/部门配额与成本分摊**：只有 anything-llm 有每用户日限；要做按部门的 token/存储/请求配额，需要自建计量（可参照 08 维度的观测数据源）+ 配额表 + 中间件拦截。
5. **凭据与密钥治理**：dify 的 RSA+AES 加密落库是唯一样板；ragflow/anything-llm 明文存模型 key，自建应统一走 KMS/secret manager。
6. **合规边界**：dify 多租户对外服务需商业授权（内部单 workspace 自用不受限）；ragflow Apache 2.0 无附加条款但 EE 功能别想；anything-llm/quivr MIT、kotaemon/ragflow Apache 2.0 可放心改与内用。基于 dify 做对外运营前先过 LICENSE 附加条款 (a)(b)。
7. **数据出墙体检**：dify（telemetry 默认开）、anything-llm（PostHog 默认开）上线即关；ragflow/quivr/kotaemon 干净。

## 5. 证据与存疑清单

**关键证据（路径#符号）**：
- ragflow：`internal/permission/policy_ce.go#communityPolicy/resolveResource`（Visibility/SharedWith*）；`internal/permission/types.go:46-48`（资源枚举无 document）；`internal/handler/user_auth_ee.go:26-77`（OAuth stub）；`internal/dao/*_ee.go`（17-23 行空壳）；`internal/entity/tenant_llm.go:27`（api_key 明文）；`docker/docker-compose-base.yml`（服务清单）；LICENSE（Apache 2.0 无附加）。
- dify：`api/models/dataset.py:184/1344`（permission 枚举+dataset_permissions 表）；`api/services/dataset_service.py:262-332`（SQL 下推过滤）；`api/services/enterprise/base.py:38-39`、`rbac_service.py`（闭源 enterprise 客户端）；`api/configs/feature/__init__.py:840-860`（telemetry 默认开+endpoint）；`api/core/helper/encrypter.py`（凭据加密）；`LICENSE`（多租户+LOGO 条款）；`api/tasks/community_telemetry_task.py`。
- anything-llm：`server/prisma/schema.prisma`（users.role/dailyMessageLimit、workspace_users）；`server/models/workspace.js:294#getWithUser`（成员过滤）；`server/utils/middleware/validWorkspace.js`；`server/models/eventLogs.js`（审计）；`server/endpoints/chat.js:61`（日配额）；`server/models/telemetry.js:49-53`（PostHog）；`TERMS_SELF_HOSTED.md`；LICENSE（MIT）。
- quivr：`internal/corpus/corpus.go:29#Scope`；`internal/transport/httpapi/api.go:167-174`（key→scope）；`migrations/20261006T0039Z_audit_events.sql`（append-only 审计）；`internal/transport/httpapi/audit.go:31-33`（审计范围注释）；`internal/netguard/netguard.go`（SSRF 防护）；`internal/connectors/credentials.go`（凭据密封）；LICENSE（MIT）。
- kotaemon：`libs/ktem/ktem/db/base_models.py:47-64`（BaseUser）；`flowsettings.py:74-82`（默认 admin/admin）；`libs/ktem/ktem/main.py:156-163`（admin=UI visible）；`sso_app.py`（OIDC）；LICENSE.txt（Apache 2.0）。
- milvus：`internal/proxy/dql/task_search.go:1429-1430`（partition key 路由）；`internal/querycoordv2/task/utils.go:366`（PartitionKeyIsolation）。qdrant：官方 multitenancy 文档【文档】（仓库内 docs/ 不含该页）。

**存疑（未最终证实，标以待查）**：
- ragflow EE 的真实能力面（OAuth/审计/配额在闭源构建中的实现）只能从 stub 文件名与 CE 策略代码反推，未见过 EE 二进制源码。
- ragflow CE 是否存在按 KB 的存储/文档数上限（老 Python 版有 512MB 文档数限制类配置），Go 版未找到对应配置项——不能断言完全没有。
- dify OSS 部署下 EnterpriseService 调用失败的降级行为（如 RBAC 查询异常是否回落到 legacy 5 角色）只看了 rbac 迁移命令的兼容层，未逐条追运行时降级路径。
- anything-llm telemetry 的 PostHog host 未显式写在 models/telemetry.js（用默认 host + 内置 pubkey），「默认上报到 us.i.posthog.com」按 posthog-node 默认行为推断，未抓包验证。
- quivr 组织级隔离是否防跨 org 枚举（corpus_id 全局唯一性 vs (org,id) 复合键下的越权访问）未做逐 handler 核查；其 contracts/conformance 测试目录可能覆盖，未细读。
- milvus 官方多租户最佳实践文档（milvus.io）因网络重定向未取到原文，引擎代码证据充分但「官方建议阈值」（如 partition 数上限 1024）未在本仓库内核实。
