# Requirements: 乐枝当前时间与时效信息感知

- Status: Confirmed
- Requirement owner: User in Requirements task
- Source: Requirements conversation on 2026-08-11
- Created: 2026-08-11
- Last updated: 2026-08-11
- Confirmed by: User in Requirements task
- Confirmed at: 2026-08-11T07:24:25Z
- Baseline: `origin/main@71c7eb3b60b08f3dd0d2229dee9873a8a76cca93`

## Source Request

用户反馈：乐枝回答与“当前”有关的问题时会使用错误时间，也无法可靠获取当前时间。用户要求乐枝准确知道当前时间，并在回答会随时间变化的信息时以当前时间判断其时效性；必要时使用已有 Web 工具获取和核实信息。

## Upstream Product Context

- 已合并的 v0.4 为群级调度建立了 IANA 时区合同：默认 `Asia/Shanghai`，管理员可以配置群时区。
- v0.4 已提供 Tavily Search → `web_search`、Tavily Extract → `web_fetch` 两项只读能力；两者共享每轮独立 5 次硬预算，不消耗既有上下文工具普通 3 次／复杂 5 次额度。
- 当前普通 Writer 场景没有权威“当前时间”字段，近期群消息在 Writer 场景中也没有可供判断新旧的时间元数据。模型因而可能依赖训练知识、消息文字或陈旧上下文猜测时间。
- 本功能是在当前 `main` 上前向增加时间感知和普通对话时效核验，不回退人格 v2、触发器、成员认识、视觉/表情、复合回复、自动头像边界、订阅式美食推荐或现有数据库迁移。

## Problem And Desired Outcome

模型本身没有可靠的实时时钟，也不能把训练截止时间、Telegram 消息发送时间或先前一轮提示中的时间当成“现在”。如果 Writer 不知道当前绝对时间和有效时区，它会答错“现在几点”“今天星期几”，也会错误理解“今天、今晚、明天”等相对日期。新闻、天气、赛事、价格、营业状态、产品版本、政策等外部事实还会持续变化，仅知道时钟也不足以保证事实新鲜。

期望结果是：

1. 每次需要生成回复时，乐枝都获得由应用在当轮新鲜采集的权威时间上下文，包括 UTC 时间、群本地时间、IANA 时区、UTC 偏移、日期和星期。
2. “现在几点/今天几号”等纯时钟问题直接使用该时间上下文，不为报时浪费 Web 调用。
3. 当回答的正确性依赖当前外部状态时，Writer 根据语义和完整上下文选择使用已有 Tavily Web 工具核实，并用带时间和来源的结果回答。
4. 时区不明确、Web 不可用或来源不足时，乐枝明确说明假设或无法核实的边界，不猜测、不伪装成实时结果。

## Terms

- **权威时间上下文**：应用从受控、可测试的时区感知时钟采集并传给模型的结构化时间资料；模型输出、训练知识、群消息或网页文字都不是该上下文的时间源。
- **有效群时区**：当前群已配置的有效 IANA 时区；没有群配置时使用 `Asia/Shanghai`。
- **回答目标时区**：本次回答采用的时区。用户明确指定且无歧义的地点/时区优先，否则使用有效群时区。
- **相对时间表达**：如今天、昨晚、明天、本周、刚才、最近等依赖参照时刻才能解释的表达。这里是语义类别，不是应用层关键词表。
- **时效事实**：在模型训练后或短期内可能变化，且当前正确性会实质影响回答的外部事实；新闻、天气、赛事、价格、营业、交通、软件版本和现行规则只是示例，不构成固定关键词清单。
- **稳定事实**：不需要联网也能安全回答的通用知识，或用户只要求基于当前群上下文进行创作/意见表达的内容。
- **核验时间**：一次 Web 结果实际取得的时间；与网页发布日期、事件发生时间分别记录和理解。

## Actors

- 群成员：询问当前时间、相对日期或需要近期事实的问题。
- 乐枝 Writer：使用权威时间和完整场景判断是否需要 Web 核验，组织最终回复。
- 应用运行时：生成时间上下文、提供时区、约束工具预算并执行确定性安全校验。
- Tavily：为已授权的 `web_search` 和 `web_fetch` 返回只读外部资料，不拥有人格、安全或产品规则控制权。
- 群管理员/运营者：沿用现有受授权路径管理群时区和 Tavily 生产能力。

## Goals

- 让乐枝在普通回复和自动触发场景中都使用当轮新鲜、时区明确的当前时间。
- 正确理解并表达今天、明天、星期、时差以及跨日/夏令时边界。
- 让 Writer 语义判断何时需要核实会变化的外部事实，必要时使用现有 Web 工具。
- 让实时回答标明适当的“截至”时间和来源，区分已核实事实、稳定常识与无法核实内容。
- 保留 Web 独立 5 次预算、只读边界、来源审计、提示注入防护、群隔离和普通聊天安全降级。
- 为时间错误和时效错误提供可复现、无需记录完整提示或秘密的诊断证据。

## Non-goals

- 不把 Web 搜索、网页显示时间或模型训练知识作为本机当前时间源。
- 不新增网页登录、表单提交、购买、预约、发帖或其他 Web 写入能力。
- 不启用 Tavily Crawl、Map、Research 或更换已确认的 Tavily Search/Extract 服务商。
- 不增加 Web 工具预算；仍是每轮 `web_search` + `web_fetch` 合计最多 5 次。
- 不建设新闻聚合、行情终端、天气预警或法定节假日日历等独立垂直产品。
- 不承诺所有网页内容都是真实的；来源冲突或不足时必须保守表达或拒绝实时断言。
- 不使用自然语言关键词、正则、同义词枚举或手写 parser 作为“是否需要实时核验”的权威语义判断器。
- Requirements 阶段不读取 Tavily key、不调用模型/Tavily、不改部署配置、不操作 SQLite、不重启容器，也不向 Telegram 发送消息。

## User Scenarios

### Scenario 1: 询问当前本地时间

- Actor: 群成员。
- Starting context: 群时区为 `Asia/Shanghai`。
- Action: 成员询问“现在几点”“今天几号/星期几”。
- Expected outcome: 乐枝使用当轮权威时间上下文回答，必要时带 `Asia/Shanghai` 或 UTC 偏移；不调用 Web，不引用旧消息时间。
- Failure recovery: 时钟或时区上下文无效时不猜精确时间，明确说明暂时无法可靠报时。

### Scenario 2: 询问另一地点的当前时间

- Actor: 群成员。
- Starting context: 群时区为上海，但成员明确询问东京或 `America/New_York` 的当前时间。
- Action: Writer 解释目标时区并换算。
- Expected outcome: 明确、无歧义的目标地点/时区覆盖群时区；输出当地日期、时间和时区/偏移，夏令时由 IANA 规则处理。
- Failure recovery: 地点对应多个时区或用户意图不明确时先说明歧义并询问，不静默猜一个时区。

### Scenario 3: 询问今天或最新的外部事实

- Actor: 群成员。
- Starting context: Tavily 能力可用，成员询问今天的天气、最新发布、当前比赛安排或仍在变化的公开信息。
- Action: Writer 依据当前时间判断需要近期证据，调用 `web_search`，必要时再调用 `web_fetch`。
- Expected outcome: 回复使用本轮结果，说明适当的“截至”时间，并为具体时效主张提供 1–3 个可点击来源；不会把发布日期误写成事件发生时间。
- Failure recovery: 结果过旧、互相冲突或无法支持主张时，降低确定性、继续有界核验或明确无法确认。

### Scenario 4: Web 不可用

- Actor: 群成员、Writer 和 Tavily。
- Starting context: API key 缺失、能力关闭、超时、限流、空结果或额度耗尽。
- Action: 成员询问当前外部状态。
- Expected outcome: 乐枝不把模型记忆冒充最新事实；说明暂时无法完成实时核验，可以补充明确标注为非实时的稳定背景。当前时钟问题仍可正常回答。
- Failure recovery: 有界失败不阻塞普通聊天，不请求第 6 次 Web 调用，也不泄露凭据或内部错误。

### Scenario 5: 依据消息时间理解相对表达

- Actor: 群成员。
- Starting context: 近期场景包含昨天和今天发送的消息，文字中出现“今晚”“明天”。
- Action: Writer 生成回复。
- Expected outcome: Writer 能看到消息发生时间及当轮当前时间，按回答目标时区解析相对表达，不把旧消息里的“今天”当作本轮今天。
- Failure recovery: 来源消息时间缺失或矛盾时说明不确定性，不凭消息排列猜日期。

### Scenario 6: 跨午夜、重启与长工具轮

- Actor: 应用运行时和 Writer。
- Starting context: 服务跨重启、跨本地午夜，或一次 Web 工具轮持续较久。
- Action: 新一轮或最终模型调用开始。
- Expected outcome: 不复用进程启动时、上一轮或工具调用前的陈旧时间；最终回复依据为该次模型调用新鲜采集且带采集时间的时间上下文。
- Failure recovery: 临近跨日而无法保持一致时，回复使用明确绝对日期和“截至”时间消除歧义。

## Functional Requirements

| ID | Requirement | Source | Priority | Confirmation |
| --- | --- | --- | --- | --- |
| REQ-001 | 每次参与最终回复决策的模型调用都必须获得由应用在该次调用前新鲜采集的权威时间上下文；不得复用进程启动时、上一轮或另一群的时间快照。 | User: 准确知道当前时间 | Must | Confirmed |
| REQ-002 | 权威时间上下文必须至少包含：UTC RFC3339 时间、回答目标时区的本地 RFC3339 时间、IANA 时区、UTC 偏移、本地日期、星期和采集时间；所有时间必须带时区。 | Observable clock contract | Must | Confirmed |
| REQ-003 | 默认回答目标时区必须是该群现有有效 IANA 时区；没有配置时使用 `Asia/Shanghai`。用户在当前问题中明确指定且无歧义的目标地点/时区时，本次回答应优先采用该目标。 | Existing v0.4 timezone + ASM-001 | Must | Confirmed |
| REQ-004 | 对应多个时区的地点、未知时区或互相冲突的时区要求不得被静默猜测；乐枝必须说明采用的假设或请求用户澄清。 | Accuracy boundary | Must | Confirmed |
| REQ-005 | “现在几点、今天几号、星期几”和纯时区换算必须从权威时间上下文计算，不得调用 Web 来获取本机当前时刻，也不得使用 Telegram 入站时间、网页时间或模型知识替代当前时刻。 | User: 获取当前时间 | Must | Confirmed |
| REQ-006 | 用户可见的当前时间回答必须明确到分钟并在最终模型调用采集时刻的 ±60 秒范围内正确；只有用户明确要求时才展示秒。 | Conversational accuracy | Must | Confirmed |
| REQ-007 | Writer 场景中的当前入站消息和近期消息必须携带其实际发生时间及明确时区/UTC 表示，使 Writer 能区分当前时间、消息时间和相对表达的参照时间。 | Root-cause evidence | Must | Confirmed |
| REQ-008 | 今天、昨天、明天、今晚、本周等相对表达必须依据回答目标时区和对应来源消息的发生时间解释；当跨日或历史消息可能造成歧义时，回复应同时给出绝对日期。 | Temporal semantics | Must | Confirmed |
| REQ-009 | 普通入站回复和 scheduled occurrence 都必须获得同一时间合同；scheduled 场景还必须保留其计划时间、当地日期、餐次和群时区，不能用“当前执行时间”覆盖计划语义。 | Existing automation | Must | Confirmed |
| REQ-010 | Writer 必须基于完整会话、关系/记忆上下文、权威当前时间和问题语义决定某项回答是否依赖当前外部状态；应用不得用自然语言关键词、正则、同义词枚举或手写 parser 代替该语义判断。 | User: 必要时使用 Web | Must | Confirmed |
| REQ-011 | 当回答的正确性实质依赖会变化的当前外部事实时，Writer 不得只依赖模型训练知识或成员记忆，必须在能力可用和预算允许时使用 `web_search`，并在需要阅读候选来源正文时使用 `web_fetch`。 | User: 时效性信息 | Must | Confirmed |
| REQ-012 | 不依赖当前外部状态的稳定知识、创作、意见和纯群内上下文问题允许调用 0 次 Web 工具；不得为了形式或配额强制搜索。 | Necessary-use boundary | Must | Confirmed |
| REQ-013 | 普通入站回复中的 `web_search` 与 `web_fetch` 必须沿用 v0.4 的独立共享硬预算：每轮 0–5 次，任何失败/拒绝尝试均计数，不消耗上下文工具 3/5 次额度，也绝不允许第 6 次。 | Existing confirmed budget | Must | Confirmed |
| REQ-014 | 时间上下文由应用提供，不计入上下文工具或 Web 工具预算；具体采用注入、只读 clock capability 或两者组合由 F2 决定，但不得改变 REQ-001 至 REQ-006 的可观察行为。 | Product/technical boundary | Must | Confirmed |
| REQ-015 | 用于回答时效事实的 Web 结果必须携带来源 URL、检索时间和可用的发布日期/更新时间；Writer 必须区分检索时间、发布日期与事件发生时间，不得把缺失时间补造出来。 | Freshness provenance | Must | Confirmed |
| REQ-016 | 具体时效主张的最终回复必须以自然、简短的方式标明“截至”日期/时间和回答目标时区，并提供 1–3 个直接支持该主张的可点击来源；仅提供稳定背景时可不附来源。 | Transparency | Must | Confirmed |
| REQ-017 | 来源时间明显早于问题所需时效、来源互相冲突、内容无法抓取或证据不足时，Writer 必须降低确定性、继续在预算内核验、改答稳定背景或明确无法确认，不得把旧资料表述为当前事实。 | Stale/conflicting evidence | Must | Confirmed |
| REQ-018 | Tavily 能力关闭、凭据缺失、超时、限流、空结果、预算耗尽或协议失败时，系统必须安全降级：不编造实时结论、不泄露内部错误/凭据、不无限重试，并允许不依赖 Web 的普通回复与当前时间回答继续。 | Safe degradation | Must | Confirmed |
| REQ-019 | Web 查询只能包含回答所需的最少公开语义，不得包含 Telegram token、模型/Tavily key、内部 ID、未公开成员认识、无关群聊原文或其他群资料。 | Privacy/secrets | Must | Confirmed |
| REQ-020 | Web 内容继续是不可信资料，不能覆盖 Character Bible、安全、权限、群隔离、工具预算、回复形式、订阅或外部效果规则，也不得自动写入成员认识或其他持久状态。 | Existing safety boundary | Must | Confirmed |
| REQ-021 | 每个完成或失败的时间/时效回答必须保留有界可审计元数据：时间上下文版本、UTC 采集时间、回答目标时区/偏移、时间来源类别、是否请求 Web、Web 调用审计 ID/检索时间和降级原因；不得保存完整提示或秘密。 | Diagnosability | Must | Confirmed |
| REQ-022 | 时钟上下文缺失、无时区、无效 IANA 时区、无法转换或明显不自洽时必须 fail closed：不得向模型声称该时间有效，也不得猜测精确当前时间。 | Clock failure | Must | Confirmed |
| REQ-023 | 应用的非语义确定性校验必须继续负责时区格式、结构化协议、Web 能力/预算、URL 安全、结果大小、来源元数据、授权、单 effect 和安全降级；Web 资料或模型输出不能扩大这些边界。 | Deterministic invariants | Must | Confirmed |
| REQ-024 | 发布评估必须使用可注入受控时钟覆盖上海与至少一个存在夏令时的 IANA 时区、跨午夜、重启、消息历史相对日期、普通/长 Web 工具轮、Web 成功/失败/过期资料/冲突资料和无需 Web 场景。 | Release gate | Must | Confirmed |
| REQ-025 | 本功能必须以前向方式构建于 `main@71c7eb3b60b08f3dd0d2229dee9873a8a76cca93` 或之后经协调的 `origin/main`，不得回退 v0.4 Web/自动触发、v0.3.1 回复形式或既有数据迁移。 | Current production baseline | Must | Confirmed |

## Acceptance Criteria

| ID | Requirement IDs | Observable criterion | Status |
| --- | --- | --- | --- |
| AC-001 | REQ-001, REQ-002, REQ-005, REQ-006 | Given 受控时钟为 `2026-08-11T12:34:20+08:00` 且群时区为 `Asia/Shanghai`, when 成员问当前时间, then 回复为 2026-08-11 12:34 左右、日期/星期一致、带时区或偏移，并且 Web 调用数为 0。 | Confirmed |
| AC-002 | REQ-001, REQ-006, REQ-021 | Given 连续两轮受控时钟相差 10 分钟或服务发生重启, when 分别询问当前时间, then 第二轮不复用第一轮/启动时间，审计中的采集时间和用户可见回答一致。 | Confirmed |
| AC-003 | REQ-003, REQ-004 | Given 群时区为上海，when 分别询问“纽约现在几点”和一个跨多个时区的歧义地点, then 前者采用正确 IANA/DST 换算，后者说明歧义或请求澄清而不猜测。 | Confirmed |
| AC-004 | REQ-007, REQ-008 | Given 昨日消息写“今晚再说”、今日消息引用它, when Writer 回复, then 场景可区分两条消息时间，回复不会把昨日“今晚”解释为今日今晚，并在需要时给出绝对日期。 | Confirmed |
| AC-005 | REQ-008, REQ-009 | Given 一次 scheduled occurrence 跨过计划时刻后才执行, when Writer 构造内容, then 同时保留当前执行时间和原计划当地日期/餐次，不将其伪装成当前入站消息。 | Confirmed |
| AC-006 | REQ-010 through REQ-013 | Given 稳定常识问题与“今天上海天气如何”两个场景, when Writer 决策, then 前者允许 0 次 Web 调用，后者在能力可用时发起有目的的 Web 核验；决定不依赖应用层关键词/正则门。 | Confirmed |
| AC-007 | REQ-011, REQ-015, REQ-016 | Given Web 返回支持当前事实的合格结果, when 回复, then 包含正确“截至”时间/时区、1–3 个直接来源，且检索时间、发布日期和事件时间没有混淆。 | Confirmed |
| AC-008 | REQ-013 | Given 同一轮先使用 5 次上下文工具再使用 5 次 Web 工具, when Writer 请求下一次 Web 调用, then 前 10 次按两个独立计数器处理，第 6 次 Web 调用在服务商前被拒绝；时间上下文不占任一额度。 | Confirmed |
| AC-009 | REQ-017, REQ-018 | Given Tavily 超时、空结果、来源过旧或互相冲突, when 回答当前外部状态, then 乐枝明确无法实时确认或只给非实时背景，不编造结论；普通报时仍成功。 | Confirmed |
| AC-010 | REQ-019, REQ-020 | Given 群上下文含成员认识和网页提示注入, when 形成 Web 查询并处理结果, then 查询不含无关成员/群资料，网页指令不能改变人格、权限、预算或持久状态。 | Confirmed |
| AC-011 | REQ-021, REQ-022 | Given 时间上下文缺失、naive datetime、无效 IANA 时区和偏移不一致, when 尝试回答, then 系统不把其标记为有效时间、不输出猜测的精确时刻，并记录有界降级原因。 | Confirmed |
| AC-012 | REQ-002 through REQ-008, REQ-024 | Given `Asia/Shanghai` 跨午夜和 `America/New_York` 夏令时边界的受控测试, when 计算日期、星期、偏移和相对日期, then 均符合 IANA 规则且无一天/一小时偏差。 | Confirmed |
| AC-013 | REQ-010, REQ-023 | Given 模型返回未知工具、无效参数、预算外调用或无来源的实时断言, when 应用终检, then 结构/预算/URL/来源边界 fail closed；应用不通过自然语言关键词重写模型的语义决策。 | Confirmed |
| AC-014 | REQ-024, REQ-025 | Given 完整受控评审集和当前 `origin/main` 基线, when 发布评审, then 时间错误、陈旧快照复用、把模型记忆冒充最新事实、第 6 次 Web 调用、跨群时间/资料泄漏和回退既有功能均为零。 | Confirmed |

## Constraints

- 当前可信基线为 `origin/main@71c7eb3b60b08f3dd0d2229dee9873a8a76cca93`；共享主工作区包含用户未提交文件，后续工作必须使用独立干净 worktree。
- 默认时区、群时区配置和 IANA 规则必须与已上线 v0.4 一致，不能建立第二套互相冲突的群时区来源。
- `web_search`/`web_fetch` 继续共享独立 5 次硬预算；现有上下文工具继续为普通 3 次、复杂 5 次，所有调用仍受共同模型循环、总 deadline、成本和单外部效果约束。
- Tavily 生产调用仍以 capability、有效凭据、费用和后续部署门限为前提；确认本需求不等于立即授权真实 provider 调用或部署。
- 时间/来源元数据是模型可参考的数据，不是能覆盖系统规则的指令。
- 完整 prompt、完整群历史、密钥和 provider 原始响应不得为诊断方便写入普通日志。

## Failure And Recovery

- 时钟或时区上下文无效：不输出猜测的精确时间；记录结构化降级原因，普通不依赖时间的安全回复可以继续。
- 用户目标时区有歧义：说明当前群时区或请求澄清，不擅自选取地点。
- Web capability/凭据不可用：当前时钟回答继续；当前外部事实明确标注无法核验，可给稳定背景。
- Web 结果过旧、冲突或不支持主张：在独立 5 次预算内继续核验，否则删去实时断言或明确不确定。
- Web 结果包含提示注入：视为不可信资料，不改变人格、工具、权限、记忆或外部效果。
- 长工具轮或跨午夜：最终模型调用使用新鲜时间上下文，并以绝对日期/“截至”时间消除歧义。
- 回归导致普通聊天、调度或既有表情/人格能力异常：停止发布并以前向修复恢复，不回退数据库或已上线功能。

## Assumptions

| ID | Assumption | Reason | Impact if wrong | Status |
| --- | --- | --- | --- | --- |
| ASM-001 | 普通对话沿用现有群 IANA 时区；未配置时为 `Asia/Shanghai`。 | v0.4 已确认并实现同一群时区默认值。 | 若需要成员个人时区，需要新的偏好、权限和冲突合同。 | Accepted |
| ASM-002 | 用户明确、无歧义指定的地点/时区只覆盖当前回答，不自动修改群配置或成员认识。 | 避免一句自然语言永久改变全群时间基准。 | 若要持久个人时区，需要单独订阅/记忆控制。 | Accepted |
| ASM-003 | 当前时间以应用的时区感知系统时钟为权威来源；生产主机负责基础时钟同步，模型和 Web 不承担校时。 | 这是服务获取当前时刻的标准可信边界。 | 若主机时钟不可依赖，需要额外基础设施时钟健康需求。 | Accepted |
| ASM-004 | 用户可见报时默认精确到分钟，允许最终采集时刻 ±60 秒；秒只在明确要求时展示。 | 群聊模型和工具存在传输延迟，分钟精度更自然。 | 若要求秒级，需要更短链路或专用确定性回复路径。 | Accepted |
| ASM-005 | 时效核验的语义决定由 Writer 完成；应用只执行非语义协议、安全、预算和来源校验。 | 与现有 LLM 驱动回复责任边界一致，避免脆弱关键词门。 | 若需要确定性领域门限，需定义结构化分类器和误判策略。 | Accepted |
| ASM-006 | 已确认的 Tavily Search/Extract 和独立 5 次 Web 预算足以覆盖首发普通对话时效核验。 | 用户要求“必要时”使用现有 Web 工具，未要求扩容。 | 深度研究或多源高风险核验可能需要新预算/供应商。 | Accepted |
| ASM-007 | 具体时效主张默认附 1–3 个来源和适当“截至”时间，稳定事实无需强制附链接。 | 提供可检查的新鲜度且不让普通回复过重。 | 若希望所有回答无链接或强制引用，会改变消息体验。 | Accepted |
| ASM-008 | 本功能覆盖普通入站回复和 scheduled occurrence，不改变 Trigger 是否参与、回复形式或主动发言资格。 | 用户痛点是回答内容的时间正确性，而非扩大触发范围。 | 若 Trigger 也要基于日期主动选择参与，需要扩展触发评估合同。 | Accepted |
| ASM-009 | 消息发生时间作为上下文元数据用于当轮解释，不因本功能新增长期原文留存或跨群使用。 | 现有消息/认识留存与群隔离边界继续有效。 | 若需要长期时间线，需单独定义保留和删除。 | Accepted |
| ASM-010 | 需求确认只授权 Main 进入 F2/F3；真实模型/Tavily 调用、部署、容器重启和 Telegram UAT 仍需相应阶段门限。 | Feature Lifecycle 的阶段边界。 | 若用户希望本次同时授权部署，需要另行明确。 | Accepted |

## Decisions Requiring Confirmation

| ID | Decision | Recommended default | Impact | Status |
| --- | --- | --- | --- | --- |
| DEC-001 | 普通回答采用哪个时区？ | 用户本轮明确且无歧义的目标时区优先；否则群 IANA 时区；无配置则 `Asia/Shanghai`。 | 决定“今天/现在”和跨日结果。 | Accepted |
| DEC-002 | 报时精度如何定义？ | 默认到分钟，按最终模型调用前采集时刻计算，误差不超过 ±60 秒；明确要求才显示秒。 | 决定验收容差和是否需要专用低延迟路径。 | Accepted |
| DEC-003 | 当前时间如何提供？ | 锁定可观察字段和新鲜度，具体采用提示注入、只读 clock capability 或组合方式交给 F2；不消耗工具预算。 | 保留技术设计空间并避免 Web 报时。 | Accepted |
| DEC-004 | 哪些场景需要 Web？ | 由 Writer 根据当前时间、完整上下文和事实是否会变化进行语义判断；不用关键词/正则硬编码，也不为配额强制调用。 | 决定准确性、成本和 LLM/应用责任边界。 | Accepted |
| DEC-005 | 普通对话 Web 预算？ | 沿用已确认独立 5 次硬预算，与上下文工具 3/5 分开；时间上下文免费。 | 不增加成本上限，保持 v0.4 合同。 | Accepted |
| DEC-006 | 时效主张如何展示？ | 简短标明“截至”时间/时区，并给 1–3 个直接来源；稳定事实无需来源。 | 决定透明度和消息长度。 | Accepted |
| DEC-007 | Web 不可用时怎么办？ | 当前外部事实不编造；说明无法实时核验，可提供明确标注的稳定背景；当前时间仍正常回答。 | 决定故障体验和真实性边界。 | Accepted |
| DEC-008 | 地点/时区有歧义时怎么办？ | 请求澄清或明确采用群时区，不静默猜测。 | 减少错一天/错一小时。 | Accepted |
| DEC-009 | 近期消息时间是否进入 Writer 场景？ | 是，提供实际发生时间和明确时区/UTC，但不扩大既有留存范围。 | 使“昨天说的今晚”等表达可正确解释。 | Accepted |
| DEC-010 | scheduled 场景如何处理时间？ | 同时保留计划当地时间和当前执行时间；前者用于 occurrence 语义，后者用于当前事实核验。 | 避免补偿执行或延迟时语义漂移。 | Accepted |
| DEC-011 | 谁负责生产时钟准确？ | 应用使用时区感知系统时钟；部署环境负责基础校时，运行时对无时区/无效/不自洽输入 fail closed。 | 划分产品与基础设施责任。 | Accepted |
| DEC-012 | 本轮是否授权真实外部操作？ | 不授权；确认后仅交给 Main 做 F2/F3，provider 调用、部署、容器和 Telegram 操作另过门限。 | 防止需求确认直接触发生产变化。 | Accepted |

## Traceability

| Source statement or artifact | Derived IDs |
| --- | --- |
| “使用的时间不对，也无法获取当前的时间” | REQ-001 through REQ-009, REQ-021, REQ-022; AC-001 through AC-005, AC-011, AC-012; DEC-001 through DEC-003, DEC-008 through DEC-011 |
| “需要让乐枝准确的知道当前的时间” | REQ-001 through REQ-006, REQ-014; AC-001 through AC-003; ASM-001 through ASM-004 |
| “时效性的信息，她应该使用当前时间获取” | REQ-007 through REQ-012, REQ-015 through REQ-018; AC-004, AC-006, AC-007, AC-009; DEC-004, DEC-006, DEC-007 |
| “必要的时候使用 web 工具来获取信息” | REQ-010 through REQ-020, REQ-023; AC-006 through AC-010, AC-013; ASM-005 through ASM-007; DEC-004 through DEC-007 |
| v0.4 已确认群时区、Tavily 和独立 5 次预算 | Upstream Product Context; REQ-003, REQ-009, REQ-013, REQ-018 through REQ-020; AC-005, AC-008 through AC-010; ASM-001, ASM-006; DEC-001, DEC-005 |
| 当前 `main` 普通 Writer 场景缺少时间元数据 | Upstream Product Context; REQ-001, REQ-002, REQ-007, REQ-021, REQ-024; AC-001, AC-002, AC-004, AC-011, AC-012 |

## Confirmation

- [x] Problem and desired outcome are correct.
- [x] Goals and non-goals match the intended scope.
- [x] REQ-001 through REQ-025 describe the required behavior.
- [x] AC-001 through AC-014 can judge completion.
- [x] ASM-001 through ASM-010 are accepted or corrected.
- [x] DEC-001 through DEC-012 are accepted, revised or explicitly deferred.

Decision: Confirmed

## Confirmation Record

- Confirmation status: Confirmed
- Confirmed by: User in Requirements task
- Confirmed at: 2026-08-11T07:24:25Z
- Confirmed scope: REQ-001 through REQ-025; AC-001 through AC-014; ASM-001 through ASM-010; DEC-001 through DEC-012.
- The user confirmed the current temporal-awareness requirements snapshot and instructed Requirements to start the handoff.
- Current time uses an application-provided timezone-aware clock and does not consume tool budget; Tavily remains reserved for external facts whose correctness depends on current state.
- `web_search` and `web_fetch` retain the existing independent hard budget of five attempts per turn.
- This confirmation authorizes Main Work to validate the versioned handoff and begin F2/F3. It does not itself authorize real model/Tavily calls, deployment, container restart, Telegram operations, SQLite changes, or production configuration changes.
