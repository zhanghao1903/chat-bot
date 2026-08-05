# Requirements: 乐枝默认头像部署与复合表情回复 v0.3.1

- Status: Confirmed
- Requirement owner: User in Requirements task
- Source: Delegated production evidence plus user architecture revisions on 2026-08-04
- Created: 2026-08-04
- Last updated: 2026-08-04
- Confirmed by: User in Requirements task
- Confirmed at: 2026-08-04T15:17:31Z
- Forward remediation baseline: `origin/main@85998708aa9a1d85b33a4477a818339498846868`
- Previous production baseline: `c1e820ae167c1d65d3dd44371a1a40c018e0293d`（本次发布不再以此构建）
- Revision starting point: PR #8 branch `codex/lezhi-v031-provider-gate-fix@b749d380f5fdc8a04b64e51ce11bc8ed34a0342a`

## Source Request

用户要求简化默认头像部署：信任 Telegram 官方头像上传接口的成功响应；接口返回成功即认定操作成功，不再执行自动 readback、字节摘要比较或视觉内容检查。如果实际头像缺失、错误或显示异常，由用户人工检查并上报，再由操作者处理。

用户最初要求提高乐枝使用专属表情包的频率，并扩大一次效应器回复的可见形式。一次获得回复资格的效应器可以输出：一句文字、多句话文字、文字加一个表情包，或只回复一个表情包。原先确认的 `0.4–0.7` 硬目标及其统计/门限合同，现已被下文最新架构决定取代；该区间只保留为离线评估参考。

在原快照被 Main Work 接收后，用户进一步决定“使用安全前向发布，在 main 的分支上修复就行”。因此本修订只调整发布基线合同：以当前 `origin/main@88c775c8ef0be7d1c63fd71b5924334b12492d75` 为前向基线叠加 v0.3.1，并保留该基线中已经合入/上线的 v0.4 订阅与美食推荐能力。

在 PR #8 的关键词补丁进入多轮修复后，用户作出新的架构决定：删除应用层所有用于决定 `sticker`、`reply_with_sticker`、`reply` 或 `silence` 的自然语言关键词、正则、同义词枚举和手写句法/解析门；回复形式的语义判断由 LLM 基于完整会话、关系上下文和记忆完成。应用层只保留结构化协议和非语义确定性不变量。`0.4–0.7` 仅作为离线评估参考证据，不再是目标、发布门、运行时 guard 或应用指标。

## Upstream And Locked State

| Artifact or state | Locked identity / current value |
| --- | --- |
| Forward remediation baseline | `origin/main@85998708aa9a1d85b33a4477a818339498846868`（已包含 PR #7 / v0.3.1 和全部 v0.4 能力） |
| PR #8 revision starting point | `codex/lezhi-v031-provider-gate-fix@b749d380f5fdc8a04b64e51ce11bc8ed34a0342a`；旧关键词修复实现与验证仅作历史，不是新合同证据 |
| Previous production baseline | `c1e820ae167c1d65d3dd44371a1a40c018e0293d`（仅作历史证据；本次不得以此构建或覆盖 v0.4） |
| Repository expression candidate `catalog.json` | SHA-256 `bd85f2a6ead7943d2504d3e5203ddb54e35aa3e91446b8f5743c9ba28372f3cd` |
| Repository `avatar-candidates.json` | SHA-256 `abd8aa18ab295cb261d7610daabf6650e82de8c5640855c51755de0d5c25f4ea` |
| Deployment-side approved avatar catalog | SHA-256 `b871161e68c18115893d7aea932dabf1e9101d40278d6ce9168a6eb3735d405a` |
| Default avatar | `lezhi-default`; image SHA-256 `fd7ec0efafb9dc1e36856461228cecbf7467548c7628454fe2022f7ad607badf` |
| Current bot avatar | `none` |
| Existing avatar apply audit | `verification_mismatch`; rollback `succeeded`; must remain historical evidence |
| Expression runtime | 48 entries uploaded, mapped, smoke-tested, attached and enabled |
| Vision capability | disabled |
| Automatic avatar rotation | disabled |

## Product Policy Revision

本快照明确取代先前草案中的严格头像 readback 方案：

- 不要求头像上传后调用 `getUserProfilePhotos`/`getFile` 验证内容；
- 不比较 Source SHA 与 Remote SHA；
- 不执行本地或远端视觉相似度检查；
- Telegram 官方接口返回明确成功即写入 `platform_status=success` 或等价成功状态；
- 接口明确失败时记录 failed；请求结果不确定时记录 uncertain；
- 用户发现实际显示错误时，通过人工渠道上报，不能由系统伪装成已自动发现。

这个取舍接受一种已知风险：Telegram 可能返回成功但用户仍观察到头像缺失、缓存异常或错误显示，系统不会自动检测，依赖用户上报和操作者恢复。

## Reply-form Responsibility Revision

本修订明确替代 PR #8 当前的关键词补丁方向：

- LLM 是回复形式语义决策的唯一责任方，必须从完整会话场景、关系上下文和可用记忆中选择 `reply`、`reply_with_sticker`、`sticker` 或 `silence`；
- Prompt 应指导 LLM 在严肃、安全、医疗、权限、关系修复以及排他/偏爱请求中避免 sticker；在 sticker 能自然补充情绪或动作时优先考虑；不得为了命中比例强制使用；
- 应用层不得读取自然语言内容后用关键词、正则、同义词表、前后缀枚举、否定/主语识别或手写句法/解析器重新决定、允许、禁止或改写回复形式；
- 应用层可以且必须执行非语义确定性验证：精确封闭 schema、已启用目录/摘要与 sticker ID、关系/目录元数据兼容、相邻重复、逻辑效果与幂等、授权、交付分类和安全降级；
- 结构化 JSON/schema 的解析和验证不属于被删除的“自然语言 parser gate”；它不得扩展成对用户消息语义的二次解释；
- 旧关键词覆盖测试与旧 provider evidence 不能证明本修订完成；新证据必须来自确定性协议/边界测试，以及在另行授权后生成的 provider/evaluation 证据。

## Terms

- **API success**：Telegram 官方头像上传接口返回协议定义的明确成功响应；不包含超时、连接中断、无法解析或结果未知。
- **Manual avatar report**：用户或操作者在 Telegram 客户端观察到头像缺失、错误或异常后，通过既有运维沟通渠道提供的人工报告；首发不增加群内公共报障命令。
- **Logical effect bundle**：一次 effector 决策产生的一个逻辑回复，可包含零或一个文本组件、零或一个 sticker 组件。
- **Text component**：一条 Telegram 文本消息；可以含一句或多句话，但首发不拆成多条文本消息。
- **Sticker-bearing reply**：逻辑效应包中成功发送了一个已启用乐枝专属 sticker；包括 sticker-only 和 text+sticker。
- **Reply-form semantic decision**：基于完整自然语言会话、关系上下文和记忆，在 `reply`、`reply_with_sticker`、`sticker`、`silence` 之间作出的语义选择；只属于 LLM。
- **Non-semantic deterministic invariant**：无需解释自然语言含义即可验证的结构、身份、摘要、目录元数据、重复、授权、幂等和交付边界。
- **Sticker-bearing rate reference**：离线 provider/evaluation 报告中对 sticker-bearing 输出占比的观察值；`0.4–0.7` 只用于理解历史产品偏好，不产生 pass/fail、运行时纠偏或应用指标。

## Actors

- 用户/产品所有者：确认 API-success 头像策略、复合回复形式和 LLM/应用责任边界。
- 乐枝 Writer/Effector：基于完整上下文选择文本、已启用 sticker 语义、组合或静默，并遵守 Prompt 中的人格与安全指导。
- Telegram 官方 Bot API：接收默认头像、文本和 sticker 外部效果。
- 本机操作者：部署、执行一次默认头像 apply、查看审计并处理人工上报。
- 群成员：接收文字、表情或组合回复；不能直接获得头像写权限。
- 独立 Reviewer：复审精确技术计划和代码快照。

## Goals

- 移除真实 Telegram JPEG 重编码导致的头像误失败，按官方接口成功响应部署批准默认头像。
- 保留摘要绑定、操作者授权、审计、失败/不确定状态和人工上报恢复路径。
- 允许乐枝在一个回复轮次中输出一条单句或多句文本、一个 sticker，或文本加 sticker。
- 让 LLM 基于完整会话、关系上下文和记忆自然选择回复形式，而不是由应用层关键词系统代理语义判断。
- 保持 Prompt 中的严肃/安全/关系指导，以及应用层目录、元数据兼容、重复节制、授权、幂等和 Telegram 交付边界。
- 将 `0.4–0.7` 保留为离线评估参考，不把它实现成目标、配额、发布门、运行时 guard 或应用指标。
- 保持 48 枚表情目录、VISION disabled 和自动头像轮换 disabled。

## Non-goals

- 不实现自动头像 readback、字节比较、视觉相似度、远端视觉模型或头像内容自动纠错。
- 不保证 Telegram API 成功后所有客户端立即刷新头像；显示异常依赖人工上报。
- 不修改、重裁或原地晋级仓库中的头像/表情 candidate 源。
- 不应用四个 mood 头像，不启用自动头像轮换。
- 不启用 VISION，不把项目图片发送到当前非官方兼容视觉端点。
- 不允许一次回复包含多个 sticker、多个文本消息、图片、任意文件或其他新增效果。
- 不在应用层保留任何用于决定回复形式的自然语言关键词、正则、同义词枚举或手写句法/解析门。
- 不因为历史频率参考而在任何场景强发表情，也不以观察比例失败阻止发布或运行。
- 不新增成员可调用的头像修改或公共报障工具。
- 本次 Requirements 修订不授权 provider call、部署、容器、Telegram、SQLite、sticker 上传或头像操作。

## User Scenarios

### Scenario 1: 默认头像 API 返回成功

- Actor: 本机操作者。
- Starting context: 批准目录和 `lezhi-default` 摘要匹配，当前 bot 无头像。
- Action: 操作者执行一次默认头像 apply，Telegram 官方接口返回明确成功。
- Expected outcome: 系统记录 success，不进行 readback 或视觉检查；部署流程继续。
- Failure recovery: 用户随后发现显示异常时人工上报，操作者检查当前状态并决定重试、恢复或修复。

### Scenario 2: 头像 API 明确失败或结果不确定

- Actor: Telegram 与本机操作者。
- Starting context: apply 已发起。
- Action: API 返回明确失败，或连接/进程在结果确认前中断。
- Expected outcome: 明确失败记录 failed；无法判断则记录 uncertain；两者都不伪造 success，也不自动循环重试。
- Failure recovery: 操作者结合人工 Telegram 客户端检查和审计发起新的显式操作。

### Scenario 3: 一句或多句话文本回复

- Actor: 乐枝 Effector。
- Starting context: 本轮需要文字且不选择 sticker。
- Action: 生成一句或多句话。
- Expected outcome: 作为一条 Telegram 文本消息发送；不会因为句子数拆成多次发送。
- Failure recovery: 文本结果不确定时不重发，也不追加 sticker。

### Scenario 4: 只回复表情包

- Actor: 乐枝 Effector。
- Starting context: 一个已启用 sticker 足以完整表达轻量反应。
- Action: 选择一个允许的 sticker。
- Expected outcome: 只发送该 sticker，不发送空文本、解释或第二个 sticker。
- Failure recovery: 结果不确定时不追加文本或重发。

### Scenario 5: 文字加表情包

- Actor: 乐枝 Effector。
- Starting context: 文字提供内容，sticker 能自然加强语气且场景允许。
- Action: 选择一条单句/多句文本和一个 sticker。
- Expected outcome: 先发送一条文本，再发送一个 sticker；两者属于同一逻辑效应包并可分别审计。
- Failure recovery: 文本明确失败则不发 sticker；文本成功而 sticker 明确失败时保留 text-only，不再补发其他内容；任一结果不确定都不重试该组件。

### Scenario 6: LLM 选择与评估参考

- Actor: 产品所有者、Reviewer 与 LLM Writer。
- Starting context: 在另行授权后，以覆盖普通互动和严肃/安全/关系场景的固定评审集运行 provider evaluation。
- Action: 检查每个回复形式是否与完整上下文自然一致，并观察 sticker-bearing rate。
- Expected outcome: `0.4–0.7` 只作为参考值展示；比例在区间内或区间外都不单独决定 pass/fail，也不会触发应用层纠偏。
- Failure recovery: 若质量不自然，只调整 Prompt、上下文构造、目录描述或评审设计；不得增加关键词 gate 或强制配额。

### Scenario 7: 严肃或高风险回复

- Actor: 乐枝 Effector。
- Starting context: 事实说明、操作步骤、权限、安全事故、医疗、自伤、违法或严肃关系修复。
- Action: LLM 结合完整上下文并遵循 Prompt 指导形成回复形式。
- Expected outcome: provider/evaluation evidence 显示这些场景通常使用必要文本并避免不合适 sticker；应用层不通过关键词重新判断语义。
- Failure recovery: 若模型输出违反质量预期，通过 Prompt、上下文或模型评估修订；只有结构、目录、授权等非语义不变量失败时应用层才降级。

### Scenario 8: 部署后保持现有能力

- Actor: 部署操作者。
- Starting context: 48 枚专属表情已启用，VISION 与 rotation 关闭。
- Action: 在未来获得单独授权后部署头像/效应器修订并重启。
- Expected outcome: 默认头像 API 操作有审计；48 枚映射保持；复合回复可用；VISION 和 rotation 继续关闭。
- Failure recovery: 发生回退时恢复代码/数据库备份，不重新发布表情包或启用视觉能力；本次 Requirements 修订本身不执行该场景。

## Functional Requirements

| ID | Requirement | Source | Priority | Confirmation |
| --- | --- | --- | --- | --- |
| REQ-001 | 若未来另行授权头像写入，本功能唯一允许的目标必须是 bot 账号的 `lezhi-default`；四张 mood 头像和群头像不在范围。本次修订本身不授权该写入。 | User goal / latest authorization boundary | Must | Confirmed |
| REQ-002 | apply 前必须校验部署侧批准目录 SHA-256 `b871161e...405a`、`lezhi-default`、图片 SHA-256 `fd7ec0...badf`、目标 bot identity 和本机操作者授权；不匹配时不得调用 Telegram。 | Existing approval gate | Must | Confirmed |
| REQ-003 | 仓库 `catalog.json`、`avatar-candidates.json` 和头像图片必须保持现有 candidate 字节与摘要，不得为了平台成品或成功状态原地修改。 | Existing invariant | Must | Confirmed |
| REQ-004 | Telegram 官方头像上传接口返回明确成功时，系统必须把该 operation 记为 success；成功判定不得依赖 post-upload profile readback、Remote SHA 或视觉检查。 | User revision | Must | Confirmed |
| REQ-005 | 头像 apply 不得调用 `getUserProfilePhotos`/`getFile` 验证上传内容，也不得把头像发送给视觉模型或其他图片服务。 | User revision / privacy | Must | Confirmed |
| REQ-006 | Telegram 明确失败时必须记录 failed；超时、中断、无法解析或无法知道平台结果时必须记录 uncertain，均不得伪造成 success。 | Reliability | Must | Confirmed |
| REQ-007 | failed 或 uncertain operation 不得自动循环重试；新的 apply 必须由操作者在人工检查 Telegram 当前显示和审计后显式发起。 | Idempotency | Must | Confirmed |
| REQ-008 | 每次头像 operation 至少审计 operation ID、bot identity、目录版本/摘要、头像 ID、Source SHA、操作者、原因、API method、API success/failed/uncertain、错误类别和时间；不得记录 token、key、带凭据 URL 或图片二进制。 | Audit/secrets | Must | Confirmed |
| REQ-009 | 用户发现头像缺失、错误或显示异常时，首发通过既有人工运维沟通渠道上报；上报必须能关联最近 operation/audit，但不新增公共群命令或成员头像写权限。 | User: 人工检查上报 | Must | Confirmed |
| REQ-010 | 收到人工异常报告后，操作者必须先读取当前 Telegram 客户端状态和审计，再决定显式重试、恢复为空或发布修复；系统不得根据普通群消息自动修改头像。 | Recovery boundary | Must | Confirmed |
| REQ-011 | 一次已获回复资格的 effector 必须支持以下可见结果：一条单句文本、一条多句文本、一个 sticker、一条单句文本加一个 sticker、一条多句文本加一个 sticker；既有 silence 仍可用于不回复。 | User: reply forms | Must | Confirmed |
| REQ-012 | 单句和多句文字都必须装入一个 text component，即一条 Telegram 文本消息；首发不得因句子数拆成多条消息。 | Bounded delivery | Must | Confirmed |
| REQ-013 | 一个 logical effect bundle 最多包含一个 text component 和一个 sticker component；不得包含多个 sticker、多个文本消息或其他新增媒体。 | Effect bound | Must | Confirmed |
| REQ-014 | text+sticker 必须按 text first、sticker second 发送，并共享同一 trigger/effect bundle identity；sticker-only 只有一个组件。 | Information-first delivery | Must | Confirmed |
| REQ-015 | sticker 必须来自当前启用、摘要锁定且通过 Telegram mapping 的 48 枚乐枝目录；Writer 只能选择语义 ID，不能提供任意文件、URL、`file_id` 或包名。 | Existing allowlist | Must | Confirmed |
| REQ-016 | `reply`、`reply_with_sticker`、`sticker`、`silence` 的语义选择必须由 LLM 基于完整会话场景、关系上下文和可用记忆完成；应用层不得根据自然语言内容独立决定、否决、升级或降级回复形式。 | User architecture decision | Must | Confirmed |
| REQ-017 | Writer Prompt 必须指导 LLM：在严肃、安全、医疗、权限、关系修复以及排他/偏爱请求中避免 sticker；在 sticker 能自然补充情绪或动作时优先考虑；不得为了任何使用率强制 sticker。该指导不得复制为应用层语义 gate。 | User prompt guidance | Must | Confirmed |
| REQ-018 | 应用必须把可用关系上下文、记忆和目录描述提供给 LLM；模型选择 sticker 后，应用只可执行关系等级与目录条目声明等结构化元数据兼容校验，不得解析消息文本来推断排他、偏爱、亲昵、严肃或安全语义。 | Recognition/catalog boundary | Must | Confirmed |
| REQ-019 | 乐枝不得在相邻 sticker-bearing 回复中连续使用同一 sticker；text+sticker 与 sticker-only 共享该重复节制。 | Variety | Must | Confirmed |
| REQ-020 | 每个 logical effect bundle 必须持久化其预期组件、发送顺序和每个组件的 claim/outcome，使重放或进程恢复不能重复已经成功或结果不确定的组件。 | Idempotency | Must | Confirmed |
| REQ-021 | text+sticker 中 text 明确失败时不得继续发送 sticker；text 成功而 sticker 明确失败时以 text-only degraded 结束；任一组件结果不确定时不得重发该组件或追加替代内容。 | Partial failure | Must | Confirmed |
| REQ-022 | 进程在 text 成功后、sticker 发送前中断时，恢复后不得迟到补发 sticker；该 bundle 以 text-only interrupted/degraded 终结。 | Restart safety | Must | Confirmed |
| REQ-023 | 每个 bundle 必须审计人格/目录版本、trigger、模型选择的回复形式、语义 ID、顺序、组件结果和非语义降级原因；不得记录完整消息正文、凭据或为了运行时频率纠偏而增加成员级画像/配额。 | Effect audit | Must | Confirmed |
| REQ-024 | `0.4–0.7` 必须仅作为离线 provider/evaluation 报告中的 sticker-bearing 观察参考；它不得成为硬目标、case-set pass/fail 条件、发布门、运行时 guard、应用指标或纠偏输入。 | User architecture decision | Must | Confirmed |
| REQ-025 | 应用不得维护 sticker-eligible 语义分母、线上滚动频率窗口、最小样本门、成员/群配额或任何为命中 `0.4–0.7` 而改变 LLM 有效输出的逻辑；离线报告可以展示观察比例，但不得据此单独判定合格。 | No rate enforcement | Must | Confirmed |
| REQ-026 | 所有用于决定四种回复形式的自然语言关键词、正则、同义词/主语/前后缀/否定枚举以及手写句法或 parser gate 必须从运行时决策路径删除；应用不得用等价的规则表、分类器或启发式重新引入同一责任。 | User: delete semantic gates | Must | Confirmed |
| REQ-027 | 应用层允许保留的决定性检查仅限：精确封闭结构化 schema、已启用目录与摘要、sticker semantic ID、关系/目录结构化元数据兼容、相邻 sticker 不重复、一个 logical effect/bundle 上限与幂等、触发路径/操作者授权、交付 success/failed/uncertain 分类，以及无效/未知模型输出的安全降级。 | Deterministic responsibility | Must | Confirmed |
| REQ-028 | 关键词覆盖测试必须由确定性协议/边界测试替代，至少覆盖 schema/kind/字段组合、目录/摘要/ID、关系元数据、相邻重复、授权、幂等、部分失败/uncertain 和降级；语义质量必须由固定场景的 provider/evaluation 证据与独立复审证明，旧 PR #8 关键词修复测试和旧 evidence 不得作为新合同的充分证据。 | Test/evidence revision | Must | Confirmed |
| REQ-029 | 原有“每轮最多一个可见外部效果”必须仅对本版本的回复 bundle 修订为“最多一个 text 加一个 sticker”；头像、自动触发器、工具和其他外部写入不因此获得第二效果权限。 | Scope reconciliation | Must | Confirmed |
| REQ-030 | 任何数据库变化必须向前兼容，保留现有消息、effect、avatar audit 和 expression mapping；部署前必须备份生产 SQLite 并证明 `quick_check=ok`。 | Production safety | Must | Confirmed |
| REQ-031 | 实现必须通过完整确定性协议/边界测试和独立复审；在另行获得 provider-call 授权后，还必须生成与本修订匹配的新 provider/evaluation 证据。旧关键词覆盖或旧 provider evidence 不能满足该门限，且 `0.4–0.7` 观察值不能决定 pass/fail。 | Release evidence gate | Must | Confirmed |
| REQ-032 | PR #8 修订必须以 `origin/main@85998708aa9a1d85b33a4477a818339498846868` 为前向基线并保持其为祖先，保留已合入的 v0.3.1 与全部 v0.4 数据库迁移、订阅/美食命令、调度和运行时能力；不得回退到 `88c775c8` 或 `c1e820ae` 构建替代制品。 | Safe forward remediation | Must | Confirmed |
| REQ-033 | 任何未来另行授权的部署前后都必须证明 48 枚 expression mapping 和 enable 状态不变，VISION disabled，automatic avatar rotation disabled，且四张 mood 头像没有被应用。 | Deployment invariants | Must | Confirmed |
| REQ-034 | 确认本修订只授权 Requirements 交接以及 Main Work 后续设计、代码修订和本地确定性验证；不授权 provider call、部署、容器操作、Telegram 调用/发信、生产或本地 SQLite 变更、sticker 上传、头像 apply 或其他外部写入。上述动作必须获得新的明确授权。 | Explicit authorization boundary | Must | Confirmed |

## Acceptance Criteria

| ID | Requirement IDs | Observable criterion | Status |
| --- | --- | --- | --- |
| AC-001 | REQ-001 through REQ-005 | Given 未来获得单独头像操作授权且精确批准目录和默认头像匹配，when Telegram 官方上传返回明确 success，then audit 记为 success，且没有 profile readback、Remote SHA、视觉比较或视觉端点调用；本次修订期间 Telegram 调用为零。 | Confirmed |
| AC-002 | REQ-002, REQ-003 | Given 目录/图片/bot 任一摘要错误或仓库 candidate 被修改，when apply，then Telegram 写接口调用次数为零。 | Confirmed |
| AC-003 | REQ-006 through REQ-010 | Given API 明确失败、请求结果不确定和“API 成功但用户看到异常”三种情况，when 处理，then 分别记录 failed、uncertain、success+manual report；均不自动循环重试或授予成员写权限。 | Confirmed |
| AC-004 | REQ-008 | Given 检查 avatar audit、日志和错误，when 搜索敏感内容，then 能关联 operation/目录/头像/API outcome，且无 token、key、URL 凭据或图片二进制。 | Confirmed |
| AC-005 | REQ-011 through REQ-014 | Given 五种用户要求的可见回复形式，when effector 执行，then 单句/多句均为一条 text，sticker-only 为一个 sticker，组合为一条 text 后跟一个 sticker，组件总数不超过二。 | Confirmed |
| AC-006 | REQ-015, REQ-019 | Given 未知/停用 sticker、任意 `file_id` 和与上一 sticker 相同的候选，when 最终校验，then 均不发送该 sticker，可安全退化为 text 或 silence。 | Confirmed |
| AC-007 | REQ-016 through REQ-018 | Given LLM 收到完整会话、关系上下文、记忆、目录描述和指导 Prompt，when 返回 schema-valid 且满足非语义不变量的任一回复形式，then 应用按该形式执行，不因消息中的严肃/医疗/权限/关系/偏爱词语再次允许、禁止或改写；语义质量由 provider/evaluation 证据判断。 | Confirmed |
| AC-008 | REQ-020, REQ-021 | Given text+sticker 的 text 明确失败，when 执行，then sticker 不发送；given text 成功、sticker 明确失败，then 只保留 text 且 bundle 为 degraded。 | Confirmed |
| AC-009 | REQ-020 through REQ-022 | Given text 或 sticker 结果不确定、或进程在两组件之间中断，when 重放/重启，then 已成功或 uncertain 组件不重复，未发送 sticker 不迟到补发。 | Confirmed |
| AC-010 | REQ-023 | Given text-only、sticker-only、text+sticker、partial failure、non-semantic degradation 和 uncertain，when 查审计，then 每个 bundle/组件/顺序/outcome 可还原且没有完整正文、凭据、成员配额或运行时频率纠偏字段。 | Confirmed |
| AC-011 | REQ-024, REQ-025 | Given 新 provider/evaluation 报告观察到 sticker-bearing rate 低于、处于或高于 `0.4–0.7`，when 评审结果，then 三者都不会仅因比例而失败、阻止发布、改变有效模型输出或触发运行时纠偏；报告只展示参考值。 | Confirmed |
| AC-012 | REQ-026 through REQ-028 | Given 运行时回复形式决策路径和测试套件，when 独立检查，then 不存在用于选择/否决四种形式的自然语言关键词、正则、同义词/句法枚举或手写 parser gate，也不存在以同类短语覆盖率为目的的测试；封闭 schema 与非语义边界测试仍完整。 | Confirmed |
| AC-013 | REQ-016 through REQ-018, REQ-028 | Given 覆盖普通情绪互动、严肃、安全、医疗、权限、关系修复、排他/偏爱和新颖措辞的固定场景，when 在另行授权后运行 provider evaluation，then 报告可追溯 Prompt、上下文/记忆输入、模型/目录版本和逐案输出，由独立 Reviewer 判断上下文自然性，而不是由关键词命中或使用率单独判定。 | Confirmed |
| AC-014 | REQ-029 | Given 同一触发的 text+sticker 以及任何头像/工具/自动触发操作，when 校验权限，then 只有该回复 bundle 可有两个可见组件，其他系统不能借此增加效果。 | Confirmed |
| AC-015 | REQ-030, REQ-031, REQ-034 | Given 精确代码提交，when 当前授权范围内执行验证，then 确定性协议/边界测试和独立 Reviewer 通过；provider evaluation、SQLite、部署和外部操作保持未执行，直到分别获得明确授权。 | Confirmed |
| AC-016 | REQ-032 | Given PR #8 以 `origin/main@85998708aa9a1d85b33a4477a818339498846868` 为 base，when 核对修订提交，then 该精确 main 提交仍为祖先，已合入 v0.3.1 和全部 v0.4 数据库迁移、订阅/美食命令、调度与运行时能力没有回退。 | Confirmed |
| AC-017 | REQ-033, REQ-034 | Given 当前未获得部署授权，when 比较本次修订前后环境，then 容器、Telegram、SQLite、48/48 mapping、VISION/rotation 和 mood avatars 均未被操作；未来授权部署时仍须重新验证这些不变量。 | Confirmed |
| AC-018 | REQ-001 through REQ-034 | Given 本次 RequirementsHandoff 和后续精确代码修订，when 独立审计，then 能追溯 LLM/应用责任边界、删除的关键词 gate、协议测试、待授权 provider evidence 和所有非语义不变量，且 provider、部署、容器、Telegram、SQLite、上传与头像操作均无未授权调用。 | Confirmed |

## Constraints

- Requirements 任务只修改本需求文档，不修改实现、测试、数据库、部署文件或资产。
- 实现必须使用独立干净 worktree，不能 reset、覆盖、暂存或清理共享根工作区的用户文件。
- Telegram API 明确 success 是头像操作的系统成功事实；人工客户端观察是事后反馈，不是自动 verified 门限。
- 一条多句回复是一个 text component；复合回复最多两个 Telegram 可见组件。
- `0.4–0.7` 只允许出现在离线评估报告中作为观察参考，不是长期目标、配额、指标、运行时输入或发布条件。
- 严肃/安全/医疗/权限/关系指导属于 Prompt 与 provider evaluation；应用层不得用自然语言规则重建该语义边界。
- 精确 schema、目录/摘要/ID、关系/目录结构化元数据兼容、重复节制、授权、幂等和交付分类属于应用层确定性边界。
- 自动轮换、VISION 和 mood 头像继续关闭；48 枚表情目录保持启用。
- 当前未授权 provider call、部署、容器、Telegram、SQLite、sticker 上传或头像操作。

## Failure And Recovery

- 头像摘要/身份/授权错误：Telegram 调用前拒绝。
- 头像 API 明确失败：记录 failed，不自动重试。
- 头像 API 结果未知：记录 uncertain，等待人工检查，不伪造 success。
- API success 但客户端显示异常：保留原 success 审计并追加人工 incident，不改写历史；由操作者显式恢复或重试。
- text 明确失败：组合回复终止，不发 sticker。
- sticker 明确失败：若 text 已成功则保留 text-only degraded；否则无可见效果。
- 任一组件 uncertain：不重发、不追加替代组件。
- 两组件之间中断：已成功 text 保留，sticker 不跨重启补发。
- 完整模型输出 schema/kind 无效或未知：推荐安全降级为 silence，不以自然语言启发式猜测回复形式。
- `reply_with_sticker` 的 text 合法但 sticker 因目录/摘要/ID/元数据/相邻重复等非语义不变量无效：推荐降级为 text-only；sticker-only 的 sticker 无效时推荐 silence。
- 离线观察比例偏离 `0.4–0.7`：只记录为参考，不自动调参、阻止发布或改变运行时输出。
- provider evidence 尚未获得调用授权：保持门限未满足，不复用旧关键词修复 evidence，也不绕过授权。
- 数据库迁移、测试、复审或不变量失败：不部署或恢复备份/旧容器。

## Assumptions

| ID | Assumption | Reason | Impact if wrong | Status |
| --- | --- | --- | --- | --- |
| ASM-001 | 用户写出的 `0. 4-07` 仍指 `0.4–0.7`，但最新决定把它降级为离线观察参考，不再表达必须达到的目标。 | 用户明确修订。 | 若仍要硬目标，REQ-024–028、AC-011–013 必须重新修订。 | Accepted |
| ASM-002 | “一句话或多句话”指一条 Telegram 文本消息中的一个或多个句子，不是连续多条文本消息。 | 用户按内容形式描述。 | 若要多条文本，bundle 上限、顺序和失败恢复都需扩大。 | Accepted |
| ASM-003 | text+sticker 中最多附加一个专属 sticker。 | 现有目录和避免刷屏的边界。 | 多 sticker 需要新的数量、顺序和频率合同。 | Accepted |
| ASM-004 | 既有 silence 仍然有效；用户列出的形式描述“回复时”的输出，而非要求每轮都回复。 | 保留触发/参与合同。 | 若禁止 silence，会改变主动参与和刷屏风险。 | Accepted |
| ASM-005 | 若离线报告展示 sticker-bearing 观察值，sticker-only 与 reply_with_sticker 都算 sticker-bearing；该计算不进入应用运行时。 | 保留原区间含义供参考。 | 若只展示分类分布而不展示合计值，评估报告格式可在 F2/F3 调整。 | Accepted |
| ASM-006 | 不再存在应用层的 sticker-eligible 语义分母；固定评审集可以按场景标签解释结果，但不得把标签实现为运行时 gate。 | 用户删除应用语义门和指标。 | 若需要线上语义分母，会重新引入被禁止的责任。 | Accepted |
| ASM-007 | 头像异常上报使用既有人工运维沟通渠道，不新增群命令、工单系统或成员写权限。 | 用户只要求“用户检查上报”。 | 新上报产品入口需要独立范围。 | Accepted |
| ASM-008 | Telegram 官方上传接口的明确 success 足以作为系统成功，不需要任何 post-upload 自动 readback。 | 用户明确要求信任接口报文。 | 若仍需最小 readback，REQ-004/005 必须修订。 | Accepted |
| ASM-009 | PR #8 修订以 `origin/main@85998708aa9a1d85b33a4477a818339498846868` 为精确起始 base，该提交已包含合并后的 v0.3.1 和全部 v0.4 能力；48 枚表情启用、VISION/rotation disabled 的产品不变量继续有效。 | Main 提供的生命周期现场。 | 若远端 base 或运行状态变化，必须在 F2/F3 重新协调。 | Accepted |
| ASM-010 | 最新“无 provider call/部署/容器/Telegram/SQLite/上传/头像操作授权”覆盖旧快照中的部署授权；后续任何此类动作都需要新的明确授权。 | 用户最新授权边界。 | 若用户只限制 Requirements 任务而非 Main，也仍可通过单独授权解除，不应在本快照中推定。 | Accepted |
| ASM-011 | “删除 handcrafted parser gate”只指解析自然语言来决定回复形式的代码；封闭 JSON/schema parser、字段组合和标识符验证必须保留。 | 用户同时要求保留 exact structured schema。 | 若连结构化 parser 也删除，将无法安全验证模型输出和外部效果。 | Accepted |

## Decisions Requiring Confirmation

| ID | Decision | Recommended default | Impact | Status |
| --- | --- | --- | --- | --- |
| DEC-001 | 头像 success 如何认定？ | Telegram 官方上传接口明确 success 即系统 success。 | 删除当前必失败的 SHA/readback 门限。 | Accepted |
| DEC-002 | 是否保留任何自动 profile readback？ | 不保留；不调用 profile/getFile 做验证。 | 显示错误只能由人工发现。 | Accepted |
| DEC-003 | API 结果不确定怎么办？ | 记 uncertain、不自动重试，由操作者人工检查后新建 operation。 | 避免重复全局写入。 | Accepted |
| DEC-004 | 用户如何上报头像异常？ | 通过既有人工运维沟通渠道，关联最近 audit；不新增 bot 命令。 | 控制本次范围。 | Accepted |
| DEC-005 | 一次复合回复最多几个组件？ | 一个 text + 一个 sticker；silence 为零组件。 | 允许组合但避免刷屏。 | Accepted |
| DEC-006 | 多句话如何发送？ | 合并为一条 Telegram 文本消息。 | 保持组件上限和阅读连续性。 | Accepted |
| DEC-007 | text+sticker 顺序？ | text first、sticker second。 | 必要信息优先。 | Accepted |
| DEC-008 | 组合回复部分失败怎么办？ | text 失败则不发 sticker；sticker 失败则保留 text-only；uncertain 不重试。 | 明确可见结果和幂等。 | Accepted |
| DEC-009 | 中断后是否补发第二组件？ | 不补发，text 已成功则以 text-only degraded 终结。 | 防止迟到表情和重放重复。 | Accepted |
| DEC-010 | `0.4–0.7` 如何解释？ | 只作为离线 provider/evaluation 的观察参考；不产生任何 pass/fail 或运行时行为。 | 取消硬频率合同。 | Accepted |
| DEC-011 | 谁决定四种回复形式？ | LLM 基于完整会话、关系上下文和记忆作唯一语义决定；应用不二次解释自然语言。 | 锁定核心责任边界。 | Accepted |
| DEC-012 | 是否保留线上频率窗口/指标？ | 不保留；离线报告可展示观察值，但应用不计算或使用该指标。 | 删除运行时纠偏与配额。 | Accepted |
| DEC-013 | 严肃/安全/关系场景如何约束？ | 作为 Prompt 指导并由 provider evaluation/Reviewer 验证，不实现为应用层关键词 gate。 | 接受模型质量由 Prompt/评估治理。 | Accepted |
| DEC-014 | 修订基线协调？ | 以 `origin/main@85998708aa9a1d85b33a4477a818339498846868` 为 PR #8 前向 base，在现有分支上 fast-forward 修订，不改写历史。 | 保留已合入 v0.3.1/v0.4 能力。 | Accepted |
| DEC-015 | 生产不变量？ | 48 枚表情映射保持、VISION/rotation/mood avatars 关闭。 | 防止回退和权限扩大。 | Accepted |
| DEC-016 | 无效/未知模型输出如何安全降级？ | 整体 schema/kind 无效或未知时 silence；合法 composite 的 sticker 仅因非语义不变量无效时 text-only；sticker-only 无效时 silence。 | 不使用语义启发式也能 fail closed。 | Accepted |

## Traceability

| Source statement or artifact | Derived IDs |
| --- | --- |
| “信任 Telegram 的接口报文；上传成功则认定成功” | REQ-004 through REQ-008; AC-001, AC-003, AC-004; ASM-008; DEC-001 through DEC-003 |
| “不做视觉化检查；失败由用户检查上报” | Product Policy Revision; REQ-005, REQ-009, REQ-010; AC-001, AC-003; ASM-007; DEC-002, DEC-004 |
| “一句话或者多句话” | REQ-011, REQ-012; AC-005; ASM-002; DEC-005, DEC-006 |
| “一句话/多句话 + 表情包，或单纯表情包” | REQ-011 through REQ-023, REQ-029; AC-005 through AC-010, AC-014; ASM-003 through ASM-005; DEC-005 through DEC-009 |
| “表情包回复频率 0. 4-07 左右” | REQ-024 through REQ-028; AC-011 through AC-013; ASM-001, ASM-005, ASM-006; DEC-010 through DEC-013 |
| 既有批准头像、48 枚表情、VISION/rotation 状态 | Upstream And Locked State; REQ-001 through REQ-003, REQ-015, REQ-030 through REQ-034; AC-002, AC-015 through AC-018; ASM-009, ASM-010; DEC-014, DEC-015 |
| “使用安全前向发布，在 main 的分支上修复就行” | REQ-032; AC-016; ASM-009; DEC-014 |
| “删除所有自然语言关键词、正则、同义词枚举和手写 parser gate；由 LLM 决定回复形式” | Reply-form Responsibility Revision; REQ-016 through REQ-018, REQ-026 through REQ-028; AC-007, AC-012, AC-013; ASM-006, ASM-011; DEC-011, DEC-013, DEC-016 |
| “0.4–0.7 只作评估参考，不是目标、门限、guard 或应用指标” | REQ-023 through REQ-025, REQ-031; AC-010 through AC-013; ASM-001, ASM-005, ASM-006; DEC-010, DEC-012 |
| “保留非语义确定性不变量，替换测试与证据” | REQ-015, REQ-019 through REQ-023, REQ-027 through REQ-031; AC-006, AC-008 through AC-015; ASM-011; DEC-016 |
| “不授权 provider call、部署、容器、Telegram、SQLite、上传或头像操作” | Non-goals; REQ-001, REQ-031, REQ-034; AC-001, AC-015, AC-017, AC-018; ASM-010 |

## Confirmation Record

- Current confirmation status: Confirmed.
- Confirmed by: User in Requirements task.
- Confirmed at: 2026-08-04T15:17:31Z.
- Confirmation evidence: 用户明确确认由 LLM 基于完整会话、关系上下文和记忆决定四种回复形式；删除应用层自然语言关键词、正则、同义词枚举和手写句法/parser gate；只保留 REQ-027 的非语义不变量；`0.4–0.7` 只作离线评估参考；接受 DEC-016 的 fail-closed 降级方案。
- Confirmed revision scope: REQ-001, REQ-016 through REQ-018, REQ-023 through REQ-028, REQ-031 through REQ-034; AC-001, AC-007, AC-010 through AC-013, AC-015 through AC-018; ASM-001, ASM-005, ASM-006, ASM-009 through ASM-011; DEC-010 through DEC-014 and DEC-016, plus metadata, policy, scenarios, constraints, recovery and traceability. All other previously confirmed content remains unchanged.
- Authorization boundary: this confirmation does not authorize provider call, deployment, container, Telegram, SQLite, sticker upload, avatar apply or other external/persistent operation.
- Prior RequirementsHandoff `9d6321c7a5fc0012ea064eca3caa8056f7d2653e189d1593ac555edf32782ef9`, requirements commit `86ace06b0704da458646747e3ca0468456235851` and requirements SHA-256 `66b82b3db77ffba968d26b651a2cccfc7a85e500b36a79a8aa41722a6b67593d` remain immutable historical records.
- Obsolete PR #8 keyword-remediation review dispatch `abb58b0236e5c817110a7c68b1c44d769dfceb8f50fe48fcc48721a4712288e2` remains cancelled and cannot satisfy this contract.
- This confirmation authorizes preparation of a new versioned RequirementsHandoff to Main Work for design, code revision and local deterministic verification only.
