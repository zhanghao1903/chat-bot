# Requirements: 乐枝默认头像部署与复合表情回复 v0.3.1

- Status: Confirmed
- Requirement owner: User in Requirements task
- Source: Delegated production evidence plus user revision on 2026-08-04
- Created: 2026-08-04
- Last updated: 2026-08-04
- Confirmed by: User in Requirements task
- Confirmed at: 2026-08-04T04:55:30Z
- Production baseline: `c1e820ae167c1d65d3dd44371a1a40c018e0293d`
- Latest remote main observed at intake: `88c775c8ef0be7d1c63fd71b5924334b12492d75`

## Source Request

用户要求简化默认头像部署：信任 Telegram 官方头像上传接口的成功响应；接口返回成功即认定操作成功，不再执行自动 readback、字节摘要比较或视觉内容检查。如果实际头像缺失、错误或显示异常，由用户人工检查并上报，再由操作者处理。

用户同时要求提高乐枝使用专属表情包的频率，并扩大一次效应器回复的可见形式。一次获得回复资格的效应器可以输出：一句文字、多句话文字、文字加一个表情包，或只回复一个表情包。用户写出的目标区间 `0. 4-07` 在本快照中暂解释为 `0.4–0.7`，即在合格回复中的表情包承载率约为 40%–70%，等待用户确认。

## Upstream And Locked State

| Artifact or state | Locked identity / current value |
| --- | --- |
| Production code baseline | `c1e820ae167c1d65d3dd44371a1a40c018e0293d` |
| Latest `origin/main` at intake | `88c775c8ef0be7d1c63fd71b5924334b12492d75`（含 PR #6） |
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

## Terms

- **API success**：Telegram 官方头像上传接口返回协议定义的明确成功响应；不包含超时、连接中断、无法解析或结果未知。
- **Manual avatar report**：用户或操作者在 Telegram 客户端观察到头像缺失、错误或异常后，通过既有运维沟通渠道提供的人工报告；首发不增加群内公共报障命令。
- **Logical effect bundle**：一次 effector 决策产生的一个逻辑回复，可包含零或一个文本组件、零或一个 sticker 组件。
- **Text component**：一条 Telegram 文本消息；可以含一句或多句话，但首发不拆成多条文本消息。
- **Sticker-bearing reply**：逻辑效应包中成功发送了一个已启用乐枝专属 sticker；包括 sticker-only 和 text+sticker。
- **Sticker-eligible reply turn**：已经获得回复资格、最终不会静默，并且人格/关系/内容安全规则允许使用 sticker 的轮次。
- **Sticker-bearing rate**：在统计窗口中，成功出现 sticker 的合格可见回复数 ÷ 产生至少一个成功可见组件的 sticker-eligible 回复数。

## Actors

- 用户/产品所有者：确认 API-success 头像策略、复合回复形式和表情包频率目标。
- 乐枝 Writer/Effector：选择文本内容、已启用 sticker 语义或组合，并遵守人格与安全门限。
- Telegram 官方 Bot API：接收默认头像、文本和 sticker 外部效果。
- 本机操作者：部署、执行一次默认头像 apply、查看审计并处理人工上报。
- 群成员：接收文字、表情或组合回复；不能直接获得头像写权限。
- 独立 Reviewer：复审精确技术计划和代码快照。

## Goals

- 移除真实 Telegram JPEG 重编码导致的头像误失败，按官方接口成功响应部署批准默认头像。
- 保留摘要绑定、操作者授权、审计、失败/不确定状态和人工上报恢复路径。
- 允许乐枝在一个回复轮次中输出一条单句或多句文本、一个 sticker，或文本加 sticker。
- 使专属表情成为常见表达，在合格回复中达到约 40%–70% 的成功 sticker 承载率。
- 保持事实、安全、人格、关系强度、重复节制和 Telegram 幂等边界。
- 保持 48 枚表情目录、VISION disabled 和自动头像轮换 disabled。

## Non-goals

- 不实现自动头像 readback、字节比较、视觉相似度、远端视觉模型或头像内容自动纠错。
- 不保证 Telegram API 成功后所有客户端立即刷新头像；显示异常依赖人工上报。
- 不修改、重裁或原地晋级仓库中的头像/表情 candidate 源。
- 不应用四个 mood 头像，不启用自动头像轮换。
- 不启用 VISION，不把项目图片发送到当前非官方兼容视觉端点。
- 不允许一次回复包含多个 sticker、多个文本消息、图片、任意文件或其他新增效果。
- 不因为频率目标而在严肃、高风险、需要清楚事实或关系不合适的场景强发表情。
- 不新增成员可调用的头像修改或公共报障工具。

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

### Scenario 6: 表情包频率达到目标

- Actor: 产品所有者与运营者。
- Starting context: 固定评审集和线上滚动窗口包含足够多 sticker-eligible 回复。
- Action: 统计成功 sticker-only 与 text+sticker。
- Expected outcome: sticker-bearing rate 处于 40%–70%；安全禁用、静默和关系不合适轮次不被强行填充。
- Failure recovery: 比例偏低时调整选择策略或评审集，但不得放宽安全；比例偏高时降低非必要 sticker 选择并保持人格自然。

### Scenario 7: 严肃或高风险回复

- Actor: 乐枝 Effector。
- Starting context: 事实说明、操作步骤、权限、安全事故、医疗、自伤、违法或严肃关系修复。
- Action: 形成回复。
- Expected outcome: 使用必要文本；不得为了达到 40%–70% 指标附加轻浮 sticker。
- Failure recovery: 安全校验拒绝 sticker 后仍可发送文本，拒绝不计为频率缺陷。

### Scenario 8: 部署后保持现有能力

- Actor: 部署操作者。
- Starting context: 48 枚专属表情已启用，VISION 与 rotation 关闭。
- Action: 部署头像/效应器修订并重启。
- Expected outcome: 默认头像 API 操作有审计；48 枚映射保持；复合回复可用；VISION 和 rotation 继续关闭。
- Failure recovery: 发生回退时恢复代码/数据库备份，不重新发布表情包或启用视觉能力。

## Functional Requirements

| ID | Requirement | Source | Priority | Confirmation |
| --- | --- | --- | --- | --- |
| REQ-001 | 本次唯一获准的头像写入必须是 bot 账号的 `lezhi-default`；四张 mood 头像和群头像不在范围。 | User goal | Must | Confirmed |
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
| REQ-016 | sticker-only 只允许一个 sticker 足以完整表达的轻量互动；需要事实、步骤、澄清、严肃道歉或高风险信息时必须包含必要文本。 | Existing safety | Must | Confirmed |
| REQ-017 | text+sticker 只能在 sticker 与文字语气一致、不会弱化必要信息且人格/关系强度允许时使用；医疗、自伤、安全事故、违法、权限错误或严肃关系修复默认禁止附加 sticker。 | Safety/persona | Must | Confirmed |
| REQ-018 | 亲昵、撒娇、偏心、故作不满等 sticker 仍须由成员认识和关系温度支持；频率目标不得覆盖关系边界。 | Recognition boundary | Must | Confirmed |
| REQ-019 | 乐枝不得在相邻 sticker-bearing 回复中连续使用同一 sticker；text+sticker 与 sticker-only 共享该重复节制。 | Variety | Must | Confirmed |
| REQ-020 | 每个 logical effect bundle 必须持久化其预期组件、发送顺序和每个组件的 claim/outcome，使重放或进程恢复不能重复已经成功或结果不确定的组件。 | Idempotency | Must | Confirmed |
| REQ-021 | text+sticker 中 text 明确失败时不得继续发送 sticker；text 成功而 sticker 明确失败时以 text-only degraded 结束；任一组件结果不确定时不得重发该组件或追加替代内容。 | Partial failure | Must | Confirmed |
| REQ-022 | 进程在 text 成功后、sticker 发送前中断时，恢复后不得迟到补发 sticker；该 bundle 以 text-only interrupted/degraded 终结。 | Restart safety | Must | Confirmed |
| REQ-023 | 每个 bundle 必须审计人格/目录版本、trigger、回复形式、text/sticker 选择、语义 ID、顺序、组件结果、降级原因和是否计入频率；不得记录完整消息正文或凭据。 | Effect audit | Must | Confirmed |
| REQ-024 | 表情包目标区间必须解释为 sticker-bearing rate `0.4–0.7`，包含 sticker-only 和成功的 text+sticker。 | User: `0. 4-07` | Must | Confirmed |
| REQ-025 | 频率分母必须是产生至少一个成功可见组件的 sticker-eligible 回复；silence、未获得回复资格、sticker 被安全/关系规则禁止、全部发送失败的轮次不进入分母。 | Rate denominator | Must | Confirmed |
| REQ-026 | 固定评审集必须达到 40%–70%；线上窗口取最近 7 天内最新最多 100 个合格回复，少于 30 个样本时只显示 insufficient-data，不强行纠偏。 | Measurement | Must | Confirmed |
| REQ-027 | 线上统计必须以成功送达组件计算 numerator，按 bot/persona/catalog 版本聚合，只保留计数和比例；不得保存消息正文、成员敏感信息或按个人制定 sticker 配额。 | Observability/privacy | Must | Confirmed |
| REQ-028 | 低于 40% 或高于 70% 时只能调整选择策略、目录覆盖或评审样本；不得放宽安全、关系、事实文本、重复、授权或幂等规则来追指标。 | Safe tuning | Must | Confirmed |
| REQ-029 | 原有“每轮最多一个可见外部效果”必须仅对本版本的回复 bundle 修订为“最多一个 text 加一个 sticker”；头像、自动触发器、工具和其他外部写入不因此获得第二效果权限。 | Scope reconciliation | Must | Confirmed |
| REQ-030 | 任何数据库变化必须向前兼容，保留现有消息、effect、avatar audit 和 expression mapping；部署前必须备份生产 SQLite 并证明 `quick_check=ok`。 | Production safety | Must | Confirmed |
| REQ-031 | 实现必须通过完整测试和独立复审后才能合并/部署，覆盖全部回复形式、频率口径、组件部分失败、uncertain、重放、重启、头像 success/failed/uncertain 和凭据保护。 | Release gate | Must | Confirmed |
| REQ-032 | 生产制品必须显式协调 `c1e820a` 生产基线与最新 main；不得未经授权把 PR #6 行为带入本次生产，同时同一修复必须前向集成到最新 main。 | Baseline divergence | Must | Confirmed |
| REQ-033 | 部署前后必须证明 48 枚 expression mapping 和 enable 状态不变，VISION disabled，automatic avatar rotation disabled，且四张 mood 头像没有被应用。 | Deployment invariants | Must | Confirmed |
| REQ-034 | 用户确认本快照后，在 REQ-030/REQ-031 门限通过的前提下，授权部署 effector 修订、执行一次 `lezhi-default` apply 和必要容器重启；不授权自动轮换或视觉外发。 | Explicit deployment scope | Must | Confirmed |

## Acceptance Criteria

| ID | Requirement IDs | Observable criterion | Status |
| --- | --- | --- | --- |
| AC-001 | REQ-001 through REQ-005 | Given 精确批准目录和默认头像，when Telegram 官方上传返回明确 success，then audit 记为 success，且没有 profile readback、Remote SHA、视觉比较或视觉端点调用。 | Confirmed |
| AC-002 | REQ-002, REQ-003 | Given 目录/图片/bot 任一摘要错误或仓库 candidate 被修改，when apply，then Telegram 写接口调用次数为零。 | Confirmed |
| AC-003 | REQ-006 through REQ-010 | Given API 明确失败、请求结果不确定和“API 成功但用户看到异常”三种情况，when 处理，then 分别记录 failed、uncertain、success+manual report；均不自动循环重试或授予成员写权限。 | Confirmed |
| AC-004 | REQ-008 | Given 检查 avatar audit、日志和错误，when 搜索敏感内容，then 能关联 operation/目录/头像/API outcome，且无 token、key、URL 凭据或图片二进制。 | Confirmed |
| AC-005 | REQ-011 through REQ-014 | Given 五种用户要求的可见回复形式，when effector 执行，then 单句/多句均为一条 text，sticker-only 为一个 sticker，组合为一条 text 后跟一个 sticker，组件总数不超过二。 | Confirmed |
| AC-006 | REQ-015, REQ-019 | Given 未知/停用 sticker、任意 `file_id` 和与上一 sticker 相同的候选，when 最终校验，then 均不发送该 sticker，可安全退化为 text 或 silence。 | Confirmed |
| AC-007 | REQ-016 through REQ-018 | Given 轻量互动、事实说明、医疗/安全场景和关系不足场景，when 选择回复，then 轻量场景可使用 sticker-only/组合，其他场景保留必要文本且禁止不合适 sticker。 | Confirmed |
| AC-008 | REQ-020, REQ-021 | Given text+sticker 的 text 明确失败，when 执行，then sticker 不发送；given text 成功、sticker 明确失败，then 只保留 text 且 bundle 为 degraded。 | Confirmed |
| AC-009 | REQ-020 through REQ-022 | Given text 或 sticker 结果不确定、或进程在两组件之间中断，when 重放/重启，then 已成功或 uncertain 组件不重复，未发送 sticker 不迟到补发。 | Confirmed |
| AC-010 | REQ-023 | Given text-only、sticker-only、text+sticker、partial failure 和 uncertain，when 查审计，then 每个 bundle/组件/顺序/outcome 可还原且没有完整正文。 | Confirmed |
| AC-011 | REQ-024 through REQ-026 | Given 固定评审集至少 30 个 sticker-eligible 回复，when 统计，then sticker-only 与成功 text+sticker 的合计比例在 0.4–0.7。 | Confirmed |
| AC-012 | REQ-025 through REQ-028 | Given silence、安全禁用 sticker、关系禁用 sticker 和发送失败轮次，when 统计，then 按定义排除；比例偏离不会使这些轮次被强发表情。 | Confirmed |
| AC-013 | REQ-026, REQ-027 | Given 最近 7 天不足 30 个、30–100 个和超过 100 个合格样本，when 查看指标，then 分别显示 insufficient-data、全部 7 天样本结果、最新 100 个样本结果，且无成员正文/敏感字段。 | Confirmed |
| AC-014 | REQ-029 | Given 同一触发的 text+sticker 以及任何头像/工具/自动触发操作，when 校验权限，then 只有该回复 bundle 可有两个可见组件，其他系统不能借此增加效果。 | Confirmed |
| AC-015 | REQ-030, REQ-031 | Given 生产数据库副本和精确代码提交，when 发布检查，then向前迁移、`quick_check`、完整测试和独立 Reviewer 均通过；否则不部署。 | Confirmed |
| AC-016 | REQ-032 | Given 生产基线 `c1e820a` 与最新 main 不同，when 核对制品，then 本次生产只含获准修订，同一修复已前向集成且 PR #6 未被隐式启用。 | Confirmed |
| AC-017 | REQ-033 | Given 部署和重启前后，when 比较生产状态，then 48/48 mapping 与 enable 不变，VISION/rotation disabled，mood avatar apply 为零。 | Confirmed |
| AC-018 | REQ-001 through REQ-034 | Given 最终发布记录，when 独立审计，then 能追溯确认需求、评审提交、测试、备份、复合回复、频率、一次 default apply 和不变量，且没有未授权视觉外发或重复组件。 | Confirmed |

## Constraints

- Requirements 任务只修改本需求文档，不修改实现、测试、数据库、部署文件或资产。
- 实现必须使用独立干净 worktree，不能 reset、覆盖、暂存或清理共享根工作区的用户文件。
- Telegram API 明确 success 是头像操作的系统成功事实；人工客户端观察是事后反馈，不是自动 verified 门限。
- 一条多句回复是一个 text component；复合回复最多两个 Telegram 可见组件。
- 表情频率是长期产品目标，不是每个成员、每段对话或每十条消息的硬配额。
- 安全、必要文字、关系边界、目录 allowlist、重复节制和幂等优先于频率。
- 自动轮换、VISION 和 mood 头像继续关闭；48 枚表情目录保持启用。

## Failure And Recovery

- 头像摘要/身份/授权错误：Telegram 调用前拒绝。
- 头像 API 明确失败：记录 failed，不自动重试。
- 头像 API 结果未知：记录 uncertain，等待人工检查，不伪造 success。
- API success 但客户端显示异常：保留原 success 审计并追加人工 incident，不改写历史；由操作者显式恢复或重试。
- text 明确失败：组合回复终止，不发 sticker。
- sticker 明确失败：若 text 已成功则保留 text-only degraded；否则无可见效果。
- 任一组件 uncertain：不重发、不追加替代组件。
- 两组件之间中断：已成功 text 保留，sticker 不跨重启补发。
- 频率偏离：调整选择策略但不突破安全或关系门限。
- 数据库迁移、测试、复审或不变量失败：不部署或恢复备份/旧容器。

## Assumptions

| ID | Assumption | Reason | Impact if wrong | Status |
| --- | --- | --- | --- | --- |
| ASM-001 | 用户写出的 `0. 4-07` 指 `0.4–0.7`，即 40%–70%。 | 结合“频率应该达到”语境。 | 若目标是其他范围，必须修改 REQ-024–028。 | Accepted |
| ASM-002 | “一句话或多句话”指一条 Telegram 文本消息中的一个或多个句子，不是连续多条文本消息。 | 用户按内容形式描述。 | 若要多条文本，bundle 上限、顺序和失败恢复都需扩大。 | Accepted |
| ASM-003 | text+sticker 中最多附加一个专属 sticker。 | 现有目录和避免刷屏的边界。 | 多 sticker 需要新的数量、顺序和频率合同。 | Accepted |
| ASM-004 | 既有 silence 仍然有效；用户列出的形式描述“回复时”的输出，而非要求每轮都回复。 | 保留触发/参与合同。 | 若禁止 silence，会改变主动参与和刷屏风险。 | Accepted |
| ASM-005 | 频率目标统计 sticker-only 与 text+sticker 的成功 sticker，不只统计 sticker-only。 | 用户说“有效应器有表情包回复”。 | 若只统计 sticker-only，组合回复不会提高指标。 | Accepted |
| ASM-006 | 频率只针对 sticker-eligible 可见回复，不包含安全/关系禁止 sticker 或静默轮次。 | 避免指标破坏安全。 | 若按全部轮次统计，可能无法安全达到下限。 | Accepted |
| ASM-007 | 头像异常上报使用既有人工运维沟通渠道，不新增群命令、工单系统或成员写权限。 | 用户只要求“用户检查上报”。 | 新上报产品入口需要独立范围。 | Accepted |
| ASM-008 | Telegram 官方上传接口的明确 success 足以作为系统成功，不需要任何 post-upload 自动 readback。 | 用户明确要求信任接口报文。 | 若仍需最小 readback，REQ-004/005 必须修订。 | Accepted |
| ASM-009 | 当前生产仍为 `c1e820a`、头像为空、48 枚表情启用、VISION/rotation disabled。 | 权威现场。 | 状态变化需在 F2 前重新协调。 | Accepted |
| ASM-010 | 用户对“修复并部署”的既有授权继续适用于简化头像方案和本次 effector 修订，但仍受测试、复审和备份门限。 | 本轮是同一功能修订并新增回复需求。 | 若只授权需求设计，部署前仍需再次授权。 | Accepted |

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
| DEC-010 | `0. 4-07` 如何解释？ | sticker-bearing rate 为 0.4–0.7。 | 锁定目标区间。 | Accepted |
| DEC-011 | 频率分母？ | sticker-eligible 且至少一个组件成功可见的回复；排除 silence、安全/关系禁用和全部失败。 | 防止指标逼迫不合适 sticker。 | Accepted |
| DEC-012 | 线上统计窗口？ | 最近 7 天内最新最多 100 个合格回复；少于 30 个只报数据不足。 | 减少短窗口抖动。 | Accepted |
| DEC-013 | 严肃场景能否用 text+sticker？ | 医疗、自伤、安全、违法、权限错误和严肃关系修复默认禁止；普通事实/步骤仅在不弱化信息时允许。 | 保持必要文字的严肃性。 | Accepted |
| DEC-014 | 生产基线协调？ | 从 `c1e820a` 构建受控生产修订并前向集成最新 main；本次不隐式部署 PR #6。 | 避免扩大生产范围。 | Accepted |
| DEC-015 | 生产不变量？ | 48 枚表情映射保持、VISION/rotation/mood avatars 关闭。 | 防止回退和权限扩大。 | Accepted |

## Traceability

| Source statement or artifact | Derived IDs |
| --- | --- |
| “信任 Telegram 的接口报文；上传成功则认定成功” | REQ-004 through REQ-008; AC-001, AC-003, AC-004; ASM-008; DEC-001 through DEC-003 |
| “不做视觉化检查；失败由用户检查上报” | Product Policy Revision; REQ-005, REQ-009, REQ-010; AC-001, AC-003; ASM-007; DEC-002, DEC-004 |
| “一句话或者多句话” | REQ-011, REQ-012; AC-005; ASM-002; DEC-005, DEC-006 |
| “一句话/多句话 + 表情包，或单纯表情包” | REQ-011 through REQ-023, REQ-029; AC-005 through AC-010, AC-014; ASM-003 through ASM-005; DEC-005 through DEC-009 |
| “表情包回复频率 0. 4-07 左右” | REQ-024 through REQ-028; AC-011 through AC-013; ASM-001, ASM-005, ASM-006; DEC-010 through DEC-013 |
| 既有批准头像、48 枚表情、VISION/rotation 状态 | Upstream And Locked State; REQ-001 through REQ-003, REQ-015, REQ-030 through REQ-034; AC-002, AC-015 through AC-018; ASM-009, ASM-010; DEC-014, DEC-015 |

## Confirmation Record

- Confirmation status: Confirmed
- Confirmed by: User in Requirements task
- Confirmed at: 2026-08-04T04:55:30Z
- Confirmed scope: REQ-001 through REQ-034; AC-001 through AC-018; ASM-001 through ASM-010; DEC-001 through DEC-015.
- The user confirms that Telegram's official avatar-upload API success response is the system success condition. The product will not perform automated post-upload profile readback, Remote SHA comparison or visual verification; visible anomalies are reported through the existing manual operations channel.
- The user confirms that one effector reply may be one text component containing one or multiple sentences, one sticker, or text first followed by one sticker. Silence remains available.
- The user confirms that sticker-only and successfully delivered text+sticker both count toward a sticker-bearing rate target of 0.4–0.7, using the confirmed eligibility, safety and rolling-window denominator.
- The user accepts the confirmed component ordering, partial-failure, uncertain-delivery, restart, repetition, relationship and serious-context boundaries.
- The user authorizes implementation and, only after the confirmed test, independent-review and database-backup gates pass, deployment of the effector revision, one `lezhi-default` apply and necessary container restart.
- Automatic avatar rotation, VISION and mood-avatar application remain disabled; all 48 approved expression mappings remain enabled.
- This confirmation authorizes Main Work to begin F2/F3 after accepting the versioned RequirementsHandoff. It does not itself modify implementation, call Telegram, send messages/stickers, read credentials, alter production data or deploy services.
