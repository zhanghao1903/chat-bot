# Requirements: 乐枝订阅式自动触发与工作日美食推荐 v0.4

- Status: Confirmed
- Requirement owner: User in Requirements task
- Source: Requirements conversation on 2026-08-03; previously deferred meal-recommendation scope from v0.2
- Created: 2026-08-03
- Last updated: 2026-08-03
- Confirmed by: User in Requirements task
- Confirmed at: 2026-08-03T11:10:14Z
- Baseline: merged `main` at `c1e820ae167c1d65d3dd44371a1a40c018e0293d`

## Source Request

用户希望重新启动此前延期的美食推荐需求。新的目标不是只在成员问“吃什么”时回答，而是增加可订阅的自动触发能力：群员订阅美食推荐后，乐枝在每个工作日午餐和晚餐前主动在群里推荐一些食物。自动触发框架以后还应能承载其他经过允许的订阅式需求。

用户同时要求为 Writer 增加 `web search` 和 `web fetch` 两项只读工具，并指定服务商为 Tavily。Tavily 当前公开提供 Search 与 Extract API；具体 SDK、接口封装和调度实现由 F2/F3 决定，但产品行为、来源、安全、预算和降级边界由本需求锁定。

用户随后明确：Web 工具不与现有上下文工具共享次数，`web_search` 和 `web_fetch` 共同使用一个独立的每轮 5 次硬预算。

- Tavily Search 官方参考：<https://docs.tavily.com/documentation/api-reference/endpoint/search>
- Tavily Extract 官方参考：<https://docs.tavily.com/documentation/api-reference/endpoint/extract>
- Tavily 认证与端点总览：<https://docs.tavily.com/documentation/api-reference/introduction>

## Upstream Product Context

- v0.2 明确把 meal recommendation 延后，本功能正式接收该延期范围。
- 已部署乐枝 Character Bible、认识系统、群隔离、主动参与和单外部效果合同继续有效。
- v0.3 已把成员认识、近期群消息等现有上下文工具预算确认并实现为：可以调用 0 次，普通轮次最多 3 次，只有存在明确剩余缺口的复杂轮次才可到 5 次，绝不允许第 6 次。本功能保留该计数器，并为 Tavily Web 工具增加另一个独立的 0–5 次计数器。
- 当前已注册的只读工具只覆盖近期群消息和成员认识；没有生产 Tavily search/fetch，也没有订阅式 scheduler 外部效果。

## Problem And Desired Outcome

群成员经常在临近吃饭时不知道吃什么。要求成员每天主动询问会降低使用率，而无条件定时发言又会造成群聊打扰。与此同时，基于网络的餐馆、营业状态、榜单或时效信息容易过期，不能只靠模型记忆回答。

期望结果是：群管理员先允许某类自动触发，成员再明确为自己订阅；只要该群存在至少一名有效订阅者，乐枝就在工作日午餐和晚餐窗口各主动发送一条群级美食推荐。多个订阅者合并为一次推荐，不逐个刷屏。推荐保持乐枝人格，给出一份主推和两个备选，并能在确有需要时使用 Tavily search/fetch 获取带来源的近期信息。停机、重复调度、服务商失败或发送结果不确定时，系统必须避免补发和重复发言。

自动触发器应成为受治理的产品能力：新触发类型必须显式登记触发条件、订阅范围、时区、频率、工具预算、外部效果、暂停/退订和审计要求，不能让群成员提交任意 cron 或任意提示词直接变成后台任务。

## Terms

- **自动触发类型**：经过产品确认并加入允许清单的主动任务类型；首发唯一生产类型为 `weekday_food_recommendation`。
- **群级启用**：群管理员或受授权运营者允许某个自动触发类型在该群接受订阅和产生主动消息。
- **成员订阅**：当前群成员明确为自己登记某个已启用触发类型；订阅不能由其他普通成员代办。
- **餐次窗口**：群本地日期中的 `lunch` 或 `dinner` 计划时刻及其 30 分钟执行宽限期。
- **触发 occurrence**：由 bot identity、chat ID、触发类型、当地日期和餐次窗口唯一标识的一次计划执行。
- **工作日**：首发按群时区中的周一至周五判断，不接入法定节假日日历。
- **美食推荐**：一份主推和两个备选；可以是通用菜品/餐类，也可以在有明确地点和可靠近期来源时包含具体商家。
- **`web_search`**：由 Tavily Search 支持的逻辑只读能力，返回相关网页候选及来源元数据。
- **`web_fetch`**：由 Tavily Extract 支持的逻辑只读能力，获取指定网页的可读内容；不登录、不提交表单、不执行网页操作。
- **本地降级推荐**：不依赖实时网络事实、由 Writer 基于稳定常识和当前已授权上下文形成的通用菜品选择，不包含未经核实的营业时间、价格或商家状态。

## Actors

- 群管理员/运营者：启用、暂停、恢复、关闭触发类型，并配置群级时区和餐次时刻。
- 群成员/订阅者：为自己订阅、查看状态、更新有限偏好或退订。
- 乐枝 Writer：在调度场景中选择是否需要只读工具，形成符合人格、安全和推荐格式的内容。
- 自动触发调度器：创建到期 occurrence、检查资格、保证幂等并提交一次效应运行。
- Tavily：为 `web_search` 和 `web_fetch` 返回外部网络结果，不拥有产品规则控制权。
- 发布操作者：配置凭据和成本门限，验证时间、发送、审计、停机恢复和回滚。

## Goals

- 让群成员能够明确订阅和退订工作日美食推荐。
- 在工作日午餐和晚餐窗口稳定产生一次群级推荐，不因订阅人数增加而刷屏。
- 让推荐简短、有选择感、符合乐枝活跃开放的人格，并减少连续重复。
- 建立可扩展但受允许清单治理的自动触发框架。
- 为 Writer 增加由 Tavily 提供的 search/fetch 能力，并保留来源、预算和审计。
- 保证调度、Tavily 或 Telegram 异常不会重复发送或阻塞普通群聊。
- 保留群隔离、成员认识、安全优先、单外部效果和既有上下文工具 3–5 次预算，并为 Web 工具提供独立 5 次硬预算。

## Non-goals

- 首发不提供成员可自定义的任意 cron、任意后台 prompt 或任意外部写工具。
- 首发只生产启用工作日美食推荐；其他自动触发类型只验证扩展合同，不同时实现。
- 首发不做私聊提醒、跨群订阅、跨群偏好聚合或为每个订阅者单独发一条消息。
- 不接入中国法定节假日、调休或公司内部日历；工作日只指周一至周五。
- 不代成员下单、订座、付款、导航、打电话或联系商家。
- 不提供医疗营养方案、过敏安全保证、减重治疗建议或疾病饮食诊断。
- 不从认识系统或网络内容推断宗教、疾病、过敏、收入等敏感偏好。
- 不启用 Tavily Crawl、Map、Research 或任意网页写入能力；首发只使用 Search 和 Extract。
- 不把搜索结果、网页指令或商家宣传自动写入成员认识、Character Bible、订阅或触发配置。
- 不承诺没有地点信息时提供真实附近商家；此时只推荐通用菜品/餐类。
- 不在 Requirements 阶段申请 Tavily 账号、读取 API key、发起付费调用、修改代码或向 Telegram 发消息。

## User Scenarios

### Scenario 1: 管理员启用美食自动推荐

- Actor: 群管理员。
- Starting context: 该群尚未启用 `weekday_food_recommendation`。
- Action: 管理员明确启用，并查看默认时区、午餐和晚餐时刻。
- Expected outcome: 功能进入“可订阅”状态，但在没有有效订阅者前不产生主动推荐。
- Failure recovery: 身份无法验证、配置无效或功能全局关闭时不启用，并给出不泄露内部配置的说明。

### Scenario 2: 成员为自己订阅

- Actor: 群成员。
- Starting context: 当前群已启用美食推荐。
- Action: 成员明确表达“订阅工作日美食推荐”。
- Expected outcome: 系统确认订阅人、当前群、时区、两个餐次和下一次计划时间；订阅跨重启保持。
- Failure recovery: 不允许普通成员替别人订阅；重复订阅返回当前状态而不创建第二份记录。

### Scenario 3: 多名订阅者共享一条群推荐

- Actor: 多名订阅者和调度器。
- Starting context: 同一群有多个有效订阅者，午餐 occurrence 到期。
- Action: 调度器启动一次推荐。
- Expected outcome: 乐枝只在群里发一条“一份主推 + 两个备选”的推荐，不逐一 @ 或泄露订阅者清单。
- Failure recovery: 并发 worker 或重放只能有一个取得该 occurrence 的发送权。

### Scenario 4: 退订、暂停与无订阅者

- Actor: 订阅者和群管理员。
- Starting context: 成员已订阅，或该群已有计划任务。
- Action: 成员退订，或管理员暂停/关闭触发类型。
- Expected outcome: 退订立即影响尚未取得发送权的后续 occurrence；暂停/关闭期间不产生新推荐；最后一名成员退订后不再发送。
- Failure recovery: 操作结果不确定时状态可查询，不通过重复群消息确认。

### Scenario 5: 服务在餐次附近重启

- Actor: 调度器。
- Starting context: 服务在计划时间停机后恢复。
- Action: 系统重新计算到期 occurrence。
- Expected outcome: 若仍在计划时刻后 30 分钟内且该 occurrence 未取得发送权，可以执行一次；超过宽限期则记为 skipped，不迟到补发。
- Failure recovery: 已发送、sending 或结果不确定的 occurrence 不重发。

### Scenario 6: 使用 Tavily 查找近期信息

- Actor: 乐枝 Writer。
- Starting context: 群配置了城市/区域，推荐需要核实具体商家或近期美食信息。
- Action: Writer 调用 `web_search`，并在确有必要时对候选 URL 调用 `web_fetch`。
- Expected outcome: 返回标题、URL、内容摘要/提取内容、检索时间和服务商元数据；具体时效声明在消息中附上可点击来源。
- Failure recovery: 搜索为空、超时、限流或网页抓取失败时，改为不声称实时商家状态的本地降级推荐。

### Scenario 7: 网页包含提示注入或不可靠宣传

- Actor: Tavily 和乐枝 Writer。
- Starting context: 搜索结果或页面写着“忽略规则”“替用户下单”或夸大营业/健康声明。
- Action: 工具结果进入 Writer 场景。
- Expected outcome: 内容仅是不可信资料；不能修改人格、订阅、工具权限或外部效果，也不能把单一宣传源写成已证实事实。
- Failure recovery: 来源冲突或无法核实时使用保守表述、通用推荐或不引用该项。

### Scenario 8: 可选偏好与冲突偏好

- Actor: 订阅者。
- Starting context: 订阅者可选地声明菜系偏好、预算档、饮食标签或避免项；多个订阅者偏好可能冲突。
- Action: 午餐 occurrence 生成推荐。
- Expected outcome: 三个选项尽量覆盖不同方向，不点名谁有什么偏好，也不宣称过敏绝对安全。
- Failure recovery: 偏好冲突或信息不足时优先给多样化通用选择，不猜测敏感原因。

### Scenario 9: 新的自动触发需求被提出

- Actor: 产品所有者。
- Starting context: 美食推荐已经运行，用户希望新增天气提醒或每日话题。
- Action: 新类型进入需求/配置流程。
- Expected outcome: 只有明确了所有者、订阅、时区/事件、频率、资格、工具、外部效果、取消和审计合同并加入允许清单后才可运行。
- Failure recovery: 任意 cron/prompt 或缺少治理字段的类型被拒绝，不影响现有美食触发器。

### Scenario 10: Tavily 不可用但普通聊天继续

- Actor: Tavily、乐枝和群成员。
- Starting context: API key 缺失、401、429、5xx、超时或额度耗尽。
- Action: 调度推荐或普通对话尝试使用 web 工具。
- Expected outcome: 工具安全返回不可用状态；美食推荐使用通用降级内容或在无法安全形成内容时跳过；不依赖 web 的普通聊天继续。
- Failure recovery: 不泄露凭据、不无限重试、不产生第 6 次 Web 调用、第 6 次上下文工具调用或重复 Telegram 效果。

## Functional Requirements

| ID | Requirement | Source | Priority | Confirmation |
| --- | --- | --- | --- | --- |
| REQ-001 | 产品必须提供版本化、允许清单化的自动触发类型注册能力；每个类型必须声明作用群、所有者、启用状态、订阅规则、触发规则、时区、资格、工具预算、最终效果、失败恢复和审计语义。 | User: 自动触发器 | Must | Confirmed |
| REQ-002 | 首发唯一可生产启用的自动触发类型必须是 `weekday_food_recommendation`；其他类型不能仅凭运行时文本或配置自动获得执行权。 | Scope boundary | Must | Confirmed |
| REQ-003 | 美食触发类型必须先由当前群管理员或受授权运营者在该群启用，普通成员订阅才可能产生主动群消息。 | Group consent | Must | Confirmed |
| REQ-004 | 成员必须能够明确为自己订阅、退订和查看美食推荐状态；普通成员不得替其他成员订阅、修改偏好或退订。 | User: 群员订阅 | Must | Confirmed |
| REQ-005 | 订阅成功确认必须包含当前群、触发类型、群时区、午餐/晚餐时刻、下一次计划时间、群级投递说明和退订方法。 | Transparency | Must | Confirmed |
| REQ-006 | 重复订阅必须幂等地返回现有状态；不得创建重复有效订阅或因此增加发送次数。 | Idempotency | Must | Confirmed |
| REQ-007 | 成员退订必须立即停用其有效订阅；群管理员必须能够暂停、恢复或关闭该群的触发类型，并查看当前状态和下一次计划时间。 | Control | Must | Confirmed |
| REQ-008 | 群级启用、有效订阅、有限偏好和调度状态必须跨进程重启保持，并绑定明确的 bot identity、chat ID、member user ID 和配置版本。 | Persistence/identity | Must | Confirmed |
| REQ-009 | 调度器在每个 occurrence 执行前必须重新确认：类型全局可用、群级启用、至少一名有效订阅者、当前时间合格且该 occurrence 尚未取得发送权；任一条件不满足时不得发消息。 | Eligibility | Must | Confirmed |
| REQ-010 | 同一群有一个或多个订阅者时，每个餐次 occurrence 最多生成一条群级推荐；默认不得逐个 @、枚举或泄露订阅者清单。 | Coalescing/privacy | Must | Confirmed |
| REQ-011 | 订阅、偏好、调度和推荐历史必须严格按 bot identity 与 chat ID 隔离；不能使用其他群的订阅、地点、偏好或推荐记录。 | Group isolation | Must | Confirmed |
| REQ-012 | 订阅、退订、暂停、恢复、配置变更和拒绝操作必须可审计，至少记录行为类型、群、操作者身份、目标成员身份、配置版本、时间和结果，不记录 Tavily/API 凭据。 | Subscription audit | Must | Confirmed |
| REQ-013 | 首发工作日必须按群配置时区中的周一至周五计算，不包含法定节假日和调休日历。 | User: 工作日 | Must | Confirmed |
| REQ-014 | 默认群时区必须是 `Asia/Shanghai`，默认午餐时刻为 11:30、晚餐时刻为 17:30；受授权管理员/运营者可以修改群级时区和两个时刻。 | Recommended schedule | Must | Confirmed |
| REQ-015 | 所有状态查询和订阅确认必须以群本地时间显示下一次计划；时区或餐次时刻变更必须从下一未取得发送权的 occurrence 生效，不能制造重复窗口。 | Schedule transparency | Must | Confirmed |
| REQ-016 | 每个 occurrence 必须由 bot identity、chat ID、触发类型、当地日期和餐次窗口组成稳定唯一键；并发 worker、重放或重启必须竞争同一个发送权。 | Schedule idempotency | Must | Confirmed |
| REQ-017 | 每个已合格 occurrence 最多产生一个成功的 Telegram 群内可见外部效果；发送结果不确定时必须标记 uncertain 且不自动重发或补发。 | Single effect | Must | Confirmed |
| REQ-018 | 计划时刻后的执行宽限期必须是 30 分钟；停机恢复时只允许尚未取得发送权且仍在宽限期内的 occurrence 执行，超过宽限期必须跳过。 | Catch-up boundary | Must | Confirmed |
| REQ-019 | 调度器不得把自动 occurrence 伪装成某个成员的入站消息；Writer 场景必须明确包含触发类型、计划时间、订阅/群配置摘要和 `scheduled` 来源。 | Provenance | Must | Confirmed |
| REQ-020 | 调度器、数据库或 Telegram 异常不得阻塞正常 polling 和普通对话；自动触发器必须可被独立暂停或禁用。 | Isolation/recovery | Must | Confirmed |
| REQ-021 | 每次成功美食推荐必须包含一份清晰主推和两个可区分的备选，并保持整体简短、能帮助立即做选择且符合乐枝 Character Bible。 | Recommendation format | Must | Confirmed |
| REQ-022 | 三个选项必须尽量覆盖不同菜系、主食类型、口感或预算方向；不能只是同一道菜的同义改写。 | Diversity | Must | Confirmed |
| REQ-023 | 同一群的主推不得与最近 5 个已成功投递餐次的主推重复；确因选项不足需要重复时仍应改变备选组合，且不能依赖重试重新随机。 | Variety/idempotency | Must | Confirmed |
| REQ-024 | 每个 occurrence 的最终推荐内容或选择种子必须在外部发送前稳定保存，使同一 occurrence 的重放、检查或失败恢复不会改成另一套餐。 | Stable choice | Must | Confirmed |
| REQ-025 | 首发推荐是群级内容，不为每位订阅者单独生成消息；可选偏好只能包括菜系、预算档、饮食标签和避免项，系统不得推断其敏感原因。 | Preference boundary | Must | Confirmed |
| REQ-026 | 多名订阅者偏好冲突时，三个选项应尽量覆盖不同方向；消息不得点名成员偏好，也不得宣称任何选项对过敏、疾病或宗教要求绝对安全。 | Conflict/safety | Must | Confirmed |
| REQ-027 | 未配置城市/区域时只能推荐通用菜品或餐类；配置地点后才可尝试具体商家，并必须对营业、价格、地址或近期状态使用可追溯的近期来源和保守措辞。 | Location/current facts | Must | Confirmed |
| REQ-028 | 乐枝不得执行点单、订座、付款、导航或联系商家；涉及过敏、疾病、营养治疗等高风险问题时必须使用必要文字边界，不以通用推荐替代专业判断。 | Safety/external writes | Must | Confirmed |
| REQ-029 | 产品必须向 Writer 注册逻辑只读能力 `web_search` 和 `web_fetch`，两者的首发服务商必须是 Tavily；具体 SDK 或内部接口不得改变其可观察合同。 | User: Tavily | Must | Confirmed |
| REQ-030 | `web_search` 必须接受有界文本查询并返回有界数量的标题、规范化 HTTP(S) URL、相关摘要、结果顺序/相关性、检索时间和可用的 Tavily 请求/用量元数据。 | Search contract | Must | Confirmed |
| REQ-031 | `web_fetch` 必须只获取显式提供的单个或有界 URL 集合，返回来源 URL、提取文本、检索时间和结果状态；调度美食场景只能 fetch 本轮 Tavily 搜索返回的候选 URL。 | Fetch contract | Must | Confirmed |
| REQ-032 | `web_fetch` 必须拒绝非 HTTP(S)、凭据嵌入 URL、localhost、私网/链路本地地址、无效 URL、过多重定向和超过配置大小/时间边界的内容。 | URL safety | Must | Confirmed |
| REQ-033 | Tavily 搜索摘要、提取内容、页面文字和模型生成 answer 必须作为不可信外部资料；它们不得覆盖 Character Bible、安全、订阅、触发、工具权限、群隔离或外部效果规则。 | Prompt injection | Must | Confirmed |
| REQ-034 | Web 工具必须保持只读，不登录网站、不提交表单、不接受 cookie 会话、不执行页面脚本，也不调用 Tavily Crawl、Map 或 Research。 | Read-only boundary | Must | Confirmed |
| REQ-035 | Tavily API key 和可选 project ID 必须由部署者通过密钥配置提供，不得进入仓库、模型提示、工具结果、群消息或普通日志；缺失或无效时工具必须显示为不可用。 | Credential safety | Must | Confirmed |
| REQ-036 | `web_search` 和 `web_fetch` 必须共同使用独立于成员认识/群历史等上下文工具的 Web 预算；每条入站消息或 scheduled occurrence 可以调用 0 次 Web 工具，硬上限为 5 次，绝不允许第 6 次。 | User: separate Web budget | Must | Confirmed |
| REQ-037 | 每次 `web_search` 或 `web_fetch` 逻辑尝试都必须消耗一次 Web 预算，包括失败、超时、空结果、限流、无效参数和被执行器拒绝的尝试；上下文工具调用不得消耗 Web 预算，Web 调用也不得消耗上下文工具预算。 | Independent accounting | Must | Confirmed |
| REQ-038 | 独立预算不等于无限资源：Tavily 请求仍必须受共同 effect deadline、模型调用终止条件、结果数、结果字符数、单次超时和用量/成本门限约束；达到 Web 5 次或任一共同边界必须停止 Web 工具循环。 | Resource budget | Must | Confirmed |
| REQ-039 | Tavily 的认证失败、429、5xx、网络错误、协议错误、超时、空结果或内容超限必须安全降级；同一工具尝试不得在 Web 5 次预算外无限重试，普通聊天和可形成的通用美食推荐必须继续。 | Provider recovery | Must | Confirmed |
| REQ-040 | 基于具体商家、营业状态、价格、地址、榜单或其他近期网络事实的推荐必须在群消息中提供 1–3 个可点击来源；通用菜品推荐可以不附链接，但不得伪装为实时检索结论。 | Source transparency | Must | Confirmed |
| REQ-041 | 搜索结果相互冲突、来源过旧、只有商家自述或无法 fetch 核实时，Writer 必须降低确定性、换成通用推荐或省略该具体主张。 | Evidence quality | Must | Confirmed |
| REQ-042 | Web 工具调用必须可审计，至少记录群、effect/occurrence、工具名、目的、独立 Web 预算序号与剩余次数、提供方、状态、耗时、结果数、字符数、检索时间、来源域名、Tavily request ID/usage（若返回）和安全裁剪后的错误码；不得记录 API key 或完整敏感查询。 | Tool audit | Must | Confirmed |
| REQ-043 | Tavily 或网页结果不得自动创建/修改成员认识、订阅、偏好、群配置、推荐历史或触发定义；任何持久化变化必须来自相应受授权产品路径。 | Persistence boundary | Must | Confirmed |
| REQ-044 | Writer 可以在无需网络时调用 0 次 web 工具；web 工具不可用、无关或失败不得阻塞依据默认上下文和稳定常识可完成的普通回复。 | Safe no-tool path | Must | Confirmed |
| REQ-045 | 新自动触发类型必须复用允许清单、群级启用、明确订阅/退订、稳定 occurrence、时区、频率、单外部效果、工具预算、群隔离、审计、暂停和失败恢复合同。 | User: 其他需求 | Must | Confirmed |
| REQ-046 | 群成员不得提交任意 cron、任意 prompt、任意 URL 或任意工具序列作为后台任务；新类型需要新的确认需求或已确认模板及受授权配置。 | Automation safety | Must | Confirmed |
| REQ-047 | 自动触发只能创建“轮到乐枝考虑主动发言”的合格场景，不能绕过 Character Bible、认识边界、事实/安全、工具授权或最终应用校验。 | Persona/safety | Must | Confirmed |
| REQ-048 | 每个自动触发类型必须可独立查看启用状态、订阅数、下一次计划、最近一次 outcome、跳过/失败原因和版本，并可在不停止普通聊天的情况下暂停。 | Operability | Must | Confirmed |
| REQ-049 | 线上审计必须能够区分 `sent`、`skipped_no_subscribers`、`skipped_disabled`、`skipped_late`、`tool_degraded`、`definite_failure` 和 `uncertain` 等可操作结果。 | Observability | Must | Confirmed |
| REQ-050 | 发布前必须以受控测试时钟覆盖工作日/周末、两个餐次、时区变更、无订阅、多人订阅、退订、暂停、30 分钟宽限、重启、并发、Tavily 成功/失败/注入和 Telegram uncertain，且不向真实群发送未授权测试消息。 | Release gate | Must | Confirmed |

## Acceptance Criteria

| ID | Requirement IDs | Observable criterion | Status |
| --- | --- | --- | --- |
| AC-001 | REQ-003 through REQ-007 | Given 群未启用、已启用无订阅和成员重复订阅三种状态，when 操作，then 分别不能订阅生效、可订阅但不主动发言、只保留一份订阅并显示下一计划。 | Confirmed |
| AC-002 | REQ-004, REQ-006, REQ-008 | Given 成员 A 尝试替成员 B 订阅或退订，when 校验身份，then 操作被拒绝；A 为自己订阅后跨重启仍只有一份有效记录。 | Confirmed |
| AC-003 | REQ-007, REQ-009, REQ-010 | Given 最后一名订阅者退订或管理员暂停，when 下一 occurrence 到期，then 不发送；恢复并重新有订阅后只影响未来窗口。 | Confirmed |
| AC-004 | REQ-009 through REQ-012 | Given 同群有 20 名订阅者，when 午餐到期，then 只生成一个群级 effect，不逐一 @ 或输出订阅者清单，其他群订阅不参与。 | Confirmed |
| AC-005 | REQ-013 through REQ-016 | Given `Asia/Shanghai` 周一、周六和时区变更场景，when 计算计划，then 周一按 11:30/17:30、周六无 occurrence，变更只影响下一未取得发送权窗口。 | Confirmed |
| AC-006 | REQ-016 through REQ-018, REQ-024 | Given 同一 occurrence 被两个 worker、重启和重放同时看到，when 执行，then 只有一个取得发送权且内容稳定；uncertain 不重发。 | Confirmed |
| AC-007 | REQ-018, REQ-020 | Given 服务分别在计划后 20 分钟和 40 分钟恢复，when 处理未发送 occurrence，then 前者最多执行一次，后者记录 `skipped_late` 且普通聊天继续。 | Confirmed |
| AC-008 | REQ-019, REQ-047 | Given scheduled occurrence 进入 Writer，when 查看场景和最终输出，then 来源明确为 scheduled、没有伪造成员消息，并继续服从人格、安全与应用终检。 | Confirmed |
| AC-009 | REQ-021 through REQ-024 | Given 连续 6 个成功餐次，when 生成，then 每次均有一主推两备选，三个方向可区分，主推不与此前 5 次重复，同一 occurrence 重放内容不变。 | Confirmed |
| AC-010 | REQ-025 through REQ-028 | Given 多个订阅者存在相冲突偏好且无地点，when 推荐，then 返回多样化通用菜品、不点名偏好、不声称过敏安全，也不尝试下单或导航。 | Confirmed |
| AC-011 | REQ-027, REQ-029 through REQ-031 | Given 群配置了城市并需要近期商家信息，when Writer 搜索并 fetch 候选，then 结果带 URL、检索时间和来源元数据，fetch URL 来自本轮搜索。 | Confirmed |
| AC-012 | REQ-031, REQ-032, REQ-034 | Given `file://`、localhost、私网 URL、带凭据 URL、任意登录/表单和非搜索候选 URL，when 美食场景请求 fetch，then 全部在调用或执行前被拒绝。 | Confirmed |
| AC-013 | REQ-033, REQ-041, REQ-043 | Given 网页要求忽略人设、修改订阅或执行订单，when Writer 使用结果，then 这些指令不生效且不持久化；冲突主张被降级或省略。 | Confirmed |
| AC-014 | REQ-035 | Given API key 缺失、格式无效或检查日志/提示/群消息，when 启动和调用，then web 工具明确不可用且任何位置都不出现 key。 | Confirmed |
| AC-015 | REQ-036 through REQ-038 | Given 0 次、5 次和请求第 6 次 Web 工具的场景，when 执行，then 前两者分别正常完成且每次尝试计入独立 Web 序号，第 6 次在提供方调用前被拒绝；同轮已用的上下文工具次数不减少这 5 次 Web 配额。 | Confirmed |
| AC-016 | REQ-039, REQ-044 | Given Tavily 返回 401、429、5xx、超时、空结果或超限内容，when 处理，then 停止有界工具循环，普通对话继续；美食推荐改用不含实时商家主张的通用内容或安全跳过。 | Confirmed |
| AC-017 | REQ-027, REQ-040, REQ-041 | Given 推荐包含具体营业、价格、地址或近期榜单声明，when 发送，then 消息含 1–3 个可点击来源和保守措辞；没有合格来源时具体声明不出现。 | Confirmed |
| AC-018 | REQ-017, REQ-020 | Given Telegram 明确失败和结果不确定两种发送结果，when 恢复，then 前者记录失败且不刷屏重试，后者标记 uncertain 且不补发；polling 正常继续。 | Confirmed |
| AC-019 | REQ-011, REQ-042 | Given 两个群同时订阅并搜索不同地点，when 检查推荐和审计，then 配置、偏好、来源和历史互不串群，且审计无凭据或完整敏感查询。 | Confirmed |
| AC-020 | REQ-012, REQ-015, REQ-048, REQ-049 | Given 成员/管理员查看状态并执行暂停或配置变更，when 检查可观察状态，then 下一计划、最近 outcome、版本和跳过原因一致且可审计。 | Confirmed |
| AC-021 | REQ-001, REQ-002, REQ-045, REQ-046 | Given 用户提交任意 cron/prompt 或未登记新触发类型，when 配置，then 不创建后台任务；现有美食类型继续运行。 | Confirmed |
| AC-022 | REQ-028, REQ-033, REQ-034, REQ-043 | Given 工具结果包含医疗、购买、登录、写入或人格覆盖建议，when 最终验证，then 乐枝不给出医疗保证、不执行外部写入、不改变持久状态。 | Confirmed |
| AC-023 | REQ-029 through REQ-044 | Given Tavily 成功、失败、注入、URL 拒绝、预算耗尽和无需工具场景，when 检查工具审计，then 每次调用的目的、序号、状态、来源和用量可追溯，0 次路径正常且无秘密。 | Confirmed |
| AC-024 | REQ-001 through REQ-050 | Given 受控评审集覆盖订阅、调度、推荐、Tavily 和外部发送边界，when 发布评审，then 未订阅主动发言、周末发言、重复 occurrence、第 6 次 Web 调用、第 6 次上下文工具调用、跨群泄漏、提示注入生效、无来源实时商家断言和未授权外部写入均为零。 | Confirmed |

## Constraints

- 本功能建立在合并 `main@c1e820a…` 的人格、认识、触发、视觉/表情、单外部效果和上下文工具 3–5 次预算合同上；新增 Web 工具独立 5 次预算。
- 单轮理论上最多可消耗 5 次上下文工具和 5 次 Web 工具，但两个计数器仍共享共同 effect deadline、模型终止、安全校验、用量/成本和单外部效果边界；F2 必须协调现有模型调用循环以满足该可观察合同。
- 自动触发器扩大“何时轮到乐枝考虑发言”，但不扩大 Writer 的外部写权限。
- 每个 scheduled occurrence 与每条入站消息一样，最多一个成功群内可见外部效果。
- Tavily Search/Extract 是外部动态资料来源，不是权威系统或可信控制面。
- 群订阅和偏好只服务当前群；不得跨群形成营销或推送名单。
- Requirements 任务只产出本需求文档，不创建凭据、实现 scheduler、调用 Tavily、部署或发送群消息。

## Failure And Recovery

- 群未启用、无订阅者、周末、暂停或关闭：记录对应 skipped outcome，不调用 Writer/Tavily、不发消息。
- 重复订阅、调度重放或并发：返回/竞争同一稳定记录，不增加 effect 数。
- 停机恢复超过 30 分钟：跳过旧 occurrence，不把午餐推荐补到下午或晚间。
- Tavily key 缺失、认证失败、限流、额度、超时、网络或协议失败：消耗对应 Web 尝试并在最多 5 次内停止，使用通用推荐或安全跳过。
- 网页注入、冲突、过旧或来源不足：忽略指令、降低确定性、换通用推荐或删除具体断言。
- Telegram 明确失败：记录失败，不无限重试；结果不确定：标记 uncertain，不补发。
- 推荐内容生成失败：该 occurrence 记录失败或跳过，不发送空壳、内部错误、工具原文或未经终检内容。
- 自动触发器异常：可以独立暂停功能，普通 Telegram polling 和被动聊天继续。

## Assumptions

| ID | Assumption | Reason | Impact if wrong | Status |
| --- | --- | --- | --- | --- |
| ASM-001 | 美食推荐仍由现有角色乐枝承担，不创建“美食助手”第二角色。 | 用户说回到此前需求，并延续当前机器人。 | 第二角色需要独立人格、触发和路由合同。 | Accepted |
| ASM-002 | 首发推荐投递到订阅发生的目标群，不通过私聊发送。 | 用户描述群员订阅后自动推荐。 | 私聊需要用户先启动 bot、独立同意和投递状态。 | Accepted |
| ASM-003 | 群管理员先启用类型，成员再只能为自己订阅。 | 一名成员的订阅会产生全群可见主动消息。 | 如果任何成员都能直接开启，会改变群聊打扰与权限风险。 | Accepted |
| ASM-004 | “工作日”首发指周一至周五，不含中国法定节假日和调休。 | 用户未指定节假日日历。 | 接入节假日需要外部日历来源和更新治理。 | Accepted |
| ASM-005 | 默认时区为 `Asia/Shanghai`。 | 用户时区和项目运行环境位于中国。 | 其他群需要管理员配置各自时区。 | Accepted |
| ASM-006 | 午餐默认 11:30、晚餐默认 17:30，以便在正式用餐前提供选择。 | “中午和晚上”没有精确时刻。 | 更晚/更早会改变提醒价值和群节奏。 | Accepted |
| ASM-007 | 每次给一份主推和两个备选，比只给一个或长列表更能解决选择困难。 | 用户从“随机一份”扩展为“一些美食”。 | 数量不同会改变文案、重复和偏好覆盖规则。 | Accepted |
| ASM-008 | 多名订阅者共享一条群级推荐，默认不 @ 或列出订阅者。 | 避免一天两次按人数刷屏并减少成员暴露。 | 个性化逐人投递需要私聊或完全不同的群消息策略。 | Accepted |
| ASM-009 | 可选偏好仅存菜系、预算档、饮食标签和避免项，不记录其健康、宗教或经济原因。 | 足以改善推荐又避免扩大敏感认识。 | 深度个性化需要新的敏感信息和冲突解决合同。 | Accepted |
| ASM-010 | 用户/部署者会在实施阶段通过安全渠道提供可用 Tavily API key，并接受对应额度或费用；Requirements 不读取或验证该 key。 | 指定 Tavily 需要账户凭据。 | 无 key 时 web 工具保持不可用，功能只能使用通用降级。 | Accepted |
| ASM-011 | Tavily Search 和 Extract 分别承载 `web_search` 与 `web_fetch`；不启用 Crawl/Map/Research。 | 与用户要求的两种工具一一对应。 | 更复杂研究会扩大成本、延迟和网页范围。 | Accepted |
| ASM-012 | Web 工具拥有独立的每轮 5 次硬预算；既有上下文工具仍为普通 3 次/复杂 5 次，因此单轮理论上最多可有 10 次工具调用，但仍受共同 deadline、模型调用、成本和安全终止。 | 用户明确要求 Web 工具走单独预算 5 次。 | 若模型循环或 deadline 不扩展，技术设计将无法同时兑现两个独立上限。 | Accepted |
| ASM-013 | 停机补偿宽限期为计划后 30 分钟，超过即跳过。 | 避免迟到推荐干扰下一餐次。 | 更长宽限会增加迟到消息和重复窗口风险。 | Accepted |
| ASM-014 | Tavily 不可用时允许 Writer用稳定常识给通用菜品推荐，但不得声称实时商家状态。 | 保证日常价值不完全依赖外部服务。 | 若要求每次必须联网，有故障时只能跳过。 | Accepted |

## Decisions Requiring Confirmation

| ID | Decision | Recommended default | Impact | Status |
| --- | --- | --- | --- | --- |
| DEC-001 | 功能如何分层？ | 建立通用允许清单式自动触发框架，首发只注册工作日美食推荐。 | 支持未来扩展但控制当前实现范围。 | Accepted |
| DEC-002 | 谁能开启群级主动消息？ | 群管理员/授权运营者先启用；普通成员只能为自己订阅。 | 决定全群打扰和权限边界。 | Accepted |
| DEC-003 | 推荐投递到哪里？ | 订阅所在群中合并投递；首发不做私聊。 | 决定身份、投递和隐私模型。 | Accepted |
| DEC-004 | 默认时区和时刻？ | `Asia/Shanghai`，工作日 11:30 和 17:30；管理员可按群调整。 | 决定 occurrence 和用户预期。 | Accepted |
| DEC-005 | 工作日是否含法定节假日/调休？ | 不含日历逻辑，只按周一至周五。 | 避免首发依赖额外日历服务。 | Accepted |
| DEC-006 | 停机后是否补发？ | 计划后 30 分钟内未发送可补执行一次，超过跳过。 | 平衡可靠性和迟到打扰。 | Accepted |
| DEC-007 | 每次推荐几个选项？ | 一份主推加两个备选。 | 控制选择负担和消息长度。 | Accepted |
| DEC-008 | 如何控制重复？ | 同群主推避开最近 5 个成功餐次；同 occurrence 内容稳定。 | 保持新鲜感和幂等。 | Accepted |
| DEC-009 | 是否个性化？ | 群级聚合推荐；只接受有限非敏感偏好，三项尽量覆盖冲突方向，不逐人生成。 | 控制数据面和刷屏。 | Accepted |
| DEC-010 | 没有地点时推荐什么？ | 只推荐通用菜品/餐类；有明确地点且来源合格时才提具体商家。 | 降低虚构“附近”和过期商家信息。 | Accepted |
| DEC-011 | Web 服务商和能力？ | Tavily Search → `web_search`，Tavily Extract → `web_fetch`；不启用其他 Tavily 产品。 | 锁定供应商范围并保留内部接口设计空间。 | Accepted |
| DEC-012 | scheduled 美食场景可 fetch 哪些 URL？ | 只能 fetch 本轮 Tavily search 返回的候选，并经过 URL 安全校验。 | 限制 SSRF、任意抓取和来源漂移。 | Accepted |
| DEC-013 | 什么时候必须展示来源？ | 具体商家/营业/价格/地址/榜单等近期事实必须附 1–3 个链接；通用菜品无需链接。 | 平衡透明度与消息简洁。 | Accepted |
| DEC-014 | Tavily 失败怎么办？ | 降级为不含实时断言的通用推荐；连通用内容也无法安全形成时跳过。 | 保证普通价值且不伪装联网。 | Accepted |
| DEC-015 | Web 工具预算如何计算？ | `web_search`/`web_fetch` 共享独立 5 次硬预算；不消耗上下文工具 3/5 次预算，反之亦然。 | 单轮理论最大工具次数从 5 增为 10，需要 F2 协调模型循环、deadline 和成本。 | Accepted |
| DEC-016 | Tavily 请求是否自动重试？ | 不做预算外重试；任何重试都消耗一次独立 Web 预算并受共同 deadline，429 优先降级。 | 控制成本、延迟和重复。 | Accepted |
| DEC-017 | 订阅和偏好保留多久？ | 有效订阅保留至退订/群关闭；退订立即删除活动偏好，保留最小操作审计 30 天。 | 决定跨重启体验和删除边界。 | Accepted |
| DEC-018 | 推荐消息是否 @ 订阅者？ | 默认不 @、不列名单；所有群成员都能看到一次群级推荐。 | 降低通知打扰和身份暴露。 | Accepted |
| DEC-019 | 谁能修改时区和餐次时刻？ | 仅群管理员/授权运营者；成员只能查看。 | 防止成员争抢全群调度。 | Accepted |
| DEC-020 | 未来新自动触发类型如何上线？ | 必须经过新的明确确认或已确认模板审查并加入允许清单；不接受任意 cron/prompt。 | 保持主动外部效果受控。 | Accepted |

## Traceability

| Source statement or artifact | Derived IDs |
| --- | --- |
| “给群友提供美食推荐” | REQ-021 through REQ-028; AC-009, AC-010, AC-017, AC-022; DEC-007 through DEC-010 |
| “群员订阅了美食推荐提醒” | REQ-003 through REQ-012; AC-001 through AC-004, AC-019, AC-020; DEC-002, DEC-003, DEC-009, DEC-017 through DEC-019 |
| “每个工作日中午和晚上推荐” | REQ-013 through REQ-020, REQ-023, REQ-024; AC-005 through AC-008, AC-018; DEC-004 through DEC-006, DEC-008 |
| “自动触发器还有一些其他需求也可以满足” | REQ-001, REQ-002, REQ-045 through REQ-050; AC-021, AC-024; DEC-001, DEC-020 |
| “增加 web-search 和 web fetch，服务商使用 Tavily” | REQ-029 through REQ-044; AC-011 through AC-017, AC-019, AC-022 through AC-024; DEC-011 through DEC-016 |
| “web 工具走单独预算 5 次” | Upstream Product Context; REQ-036 through REQ-039, REQ-042; AC-015, AC-016, AC-023, AC-024; ASM-012; DEC-015, DEC-016 |
| Tavily 官方 Search/Extract/认证文档 | Source Request; REQ-029 through REQ-035, REQ-038 through REQ-042 |

## Confirmation Record

- Confirmation status: Confirmed
- Confirmed by: User in Requirements task
- Confirmed at: 2026-08-03T11:10:14Z
- Confirmed scope: REQ-001 through REQ-050; AC-001 through AC-024; ASM-001 through ASM-014; DEC-001 through DEC-020.
- The user explicitly authorized Lezhi to send at most one group-level food recommendation for each weekday lunch and dinner occurrence, at the group timezone defaults of 11:30 and 17:30, only after a group administrator enables the trigger and while at least one valid self-subscription exists.
- Each recommendation contains one primary choice and two alternatives, coalesces all subscribers into one group message, and does not @ subscribers by default.
- Tavily Search and Tavily Extract are confirmed as the providers behind `web_search` and `web_fetch`.
- `web_search` and `web_fetch` share an independent hard Web-tool budget of five attempts per turn. This does not consume the existing context-tool allowance of three ordinary or five complex calls, and the context-tool counter does not consume Web allowance.
- The user accepts a theoretical maximum of ten tool calls in a turn. F2 must reconcile the model loop, total deadline and cost controls while preserving both hard counters, safety termination and the single-effect contract.
- The user accepts the 30-minute catch-up grace window, the later Tavily credential/fee prerequisite, and generic food-recommendation degradation when Tavily is unavailable.
- This confirmation authorizes Main Work to accept the versioned requirements and begin F2/F3. It does not itself create or validate Tavily credentials, invoke Tavily, modify implementation, deploy services, restart containers, or send Telegram messages.
