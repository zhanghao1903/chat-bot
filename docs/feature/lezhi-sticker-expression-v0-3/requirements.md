# Requirements: 乐枝表情理解与专属表情包 v0.3

- Status: Confirmed
- Requirement owner: User in Requirements task
- Source: Requirements conversation on 2026-07-31
- Created: 2026-07-31
- Last updated: 2026-08-01
- Confirmed by: User in Requirements task
- Confirmed at: 2026-08-01T01:14:34Z
- Baseline: deployed `main` at `4f50c14e748afd00c097393c0fa481184c006e12`

## Source Request

乐枝应当能够看懂群成员发送的表情，也能使用她自己的表情包回复。乐枝的表情包将基于她的原创视觉形象单独制作；每个表情资产都有一份文字语义说明，使模型能以文字理解其意图并选择对应表情发送。

## Problem And Desired Outcome

当前已部署版本只处理 Telegram 群文本：非文本贴纸会被忽略，外部效果也只能发送文本。这使乐枝无法接住成员用表情表达的态度，也只能通过句子表现惊喜、得意、犹豫、尴尬、安慰或亲近。

期望结果是：

- 乐枝能把文本里的 Unicode emoji 与符合范围的 Telegram 表情视为对话语义的一部分；
- 乐枝能从已确认、已登记的专属表情目录中选择一个符合人格、关系和当前场景的表情；
- 模型只处理稳定语义标识和文字说明，由产品把选择映射为真实 Telegram 表情资产；
- 表情让她更像一个有情绪和关系温度的角色，而不是新的刷屏或安全绕过通道。

## Terms

- **Unicode emoji**：出现在文本消息中的标准 emoji，例如 `😂`、`😭`、`🤔`。
- **Telegram sticker**：通过 Telegram 贴纸消息发送的非文本表情资产。
- **乐枝专属表情包**：基于乐枝已确认原创视觉形象制作、并由产品维护语义目录的 Telegram sticker 集合。
- **表情目录**：每个可发送表情的稳定标识、文字说明、情绪/互动意图、适用与禁用场景、关系强度以及真实资产映射的版本化集合。

## Goals

- 让乐枝在当前群聊场景中理解 Unicode emoji 和已知表情的互动含义。
- 让乐枝能以表情作为一次完整、角色化的回复。
- 用已确认文字语义目录限制模型可选表情，禁止模型伪造资产 ID 或任意发送外部图像。
- 保持乐枝在陌生人、熟人和亲近成员之间的表达温度差，同时遵守 Character Bible 和安全规则。
- 使表情的理解、选择、映射、发送和降级可审计、可回滚。
- 为乐枝原创视觉形象和首套表情包建立独立产品任务，不由 Main Work 临时发明。

## Non-goals

- 首发不要求通过视觉模型理解任意第三方贴纸或网络梗图。
- 首发不下载、长期保存或训练于群成员发送的任意表情图像。
- 不支持语音、视频、GIF、照片或普通文件的多模态理解。
- 首发不要求 Telegram 消息 reaction、custom emoji、动画 sticker 或视频 sticker。
- 不允许模型上传、生成、编辑或注册新表情资产；资产制作与发布是独立、受确认的流程。
- 不因增加表情能力而修改乐枝的核心人格、成员认识、触发优先级或工具权限。
- 不要求每条回复都配表情，也不让表情替代必要的信息、事实、道歉或安全说明。

## Blocking Product Tasks

### TASK-VISUAL-001: 乐枝原创视觉形象

- Task status: Accepted as blocking product task
- Deliverable status: Pending separate user confirmation

在制作生产表情资产前，必须形成并由用户单独确认一份 Character Visual Bible，至少定义：

- 整体视觉年龄感、脸部/发型特征、主色、服饰、辨识元素和表情张力；
- 原创性和版权边界，不以改名或局部改色复刻已有角色；
- 适合小尺寸 sticker 识别的轮廓、色彩对比和视觉简化原则；
- 必须保持的特征与不得出现的偏移。

### TASK-STICKER-PACK-001: 乐枝首套专属表情包

- Task status: Accepted as blocking product task
- Deliverable status: Pending separate user confirmation

只有 `TASK-VISUAL-001` 确认后才可制作。必须单独交付并确认：

- 每个表情的视觉资产和稳定语义标识；
- 给模型使用的文字说明、互动意图、适用/禁用场景和关系强度；
- 所有会显示给群成员的图内文字（如有）；
- 小尺寸可读性、角色一致性、原创性和 Telegram 实际发送效果验收；
- 目录版本、资产映射与回滚路径。

Main Work 可以在两项任务完成前设计和实现通用的输入、目录、选择、发送和降级能力，但不得发明临时乐枝形象、临时生产表情或临时语义目录。

## User Scenarios

### Scenario 1: 理解文本中的 emoji

- Actor: Telegram 群成员
- Starting context: 成员的文本包含 emoji，且当前场景和关系可用。
- Action: 成员发送“我又忘记保存了 😭”或在不同场景使用同一 emoji。
- Expected outcome: 乐枝把 emoji 和句子、近期场景一起理解，用具体语境决定安慰、调侃、追问或静默，不把单个符号当成固定情绪证据。
- Failure recovery: 语义不清时按文本和当前关系保守理解，不把推测当事实或持久成员认识。

### Scenario 2: 成员用乐枝专属表情回应她

- Actor: Telegram 群成员
- Starting context: 成员使用已确认乐枝表情包，通过 Telegram 原生回复或有效对话连续性回应乐枝。
- Action: 成员发送一个已登记 sticker，没有附加文本。
- Expected outcome: 系统通过已确认目录获得准确文字语义；该表情可作为对话输入参与触发和回复决策。
- Failure recovery: 映射丢失、版本不匹配或资产未确认时，不伪造表情含义。

### Scenario 3: 收到未知第三方表情

- Actor: Telegram 群成员
- Starting context: 成员发送一个不在已确认目录中的 sticker。
- Action: Telegram 仅提供资产标识、表情包名或关联 emoji 等有限元数据，或完全没有可靠语义。
- Expected outcome: 系统只使用可靠元数据，并把缺少语义的贴纸标记为未知；乐枝不声称看见了元数据中没有的视觉内容。
- Failure recovery: 若消息又不是直接回复或连续性候选，默认忽略；必须回应时可依据其他可靠场景回复或静默。

### Scenario 4: 乐枝用专属表情完成回复

- Actor: 乐枝
- Starting context: 当前是欢迎、庆祝、认可、调皮、思考、尴尬、道歉、轻量安慰或关系化反应，且一个已确认表情能够完整承载当前意图。
- Action: 效应器根据文字语义目录选择一个表情。
- Expected outcome: 群里只看到一个已确认的乐枝表情；它符合当前人格、情绪余韵、关系温度和交流意图。
- Failure recovery: 没有足够匹配的表情时，选择文本或静默，不选“差不多”的错误表情。

### Scenario 5: 信息性或严肃场景不用表情替代内容

- Actor: Telegram 群成员
- Starting context: 成员询问事实、步骤或严肃安全问题。
- Action: 乐枝需要回答实质内容。
- Expected outcome: 乐枝使用必要文本；不以表情-only 回复替代事实、风险提示、边界说明或负责任的道歉。
- Failure recovery: 存在不确定或安全风险时优先文本与安全，不为体现人格强行发表情。

### Scenario 6: 表情目录或 Telegram 发送异常

- Actor: 乐枝
- Starting context: 模型选择的语义标识未登记、已停用、映射缺失，或 Telegram 无法发送对应 sticker。
- Action: 产品执行最终外部效果。
- Expected outcome: 未登记或版本不匹配的选择不会被发送；可在不制造重复效果的前提下降级为文本或静默。
- Failure recovery: Telegram 结果不确定时不再发第二个可见效果；只有确认表情未送达时才允许最多一次安全文本降级。

## Functional Requirements

| ID | Requirement | Source | Priority | Confirmation |
| --- | --- | --- | --- | --- |
| REQ-001 | 产品必须把文本中的 Unicode emoji 保留在对话场景中，使触发、认识和效应器能够结合文本、近期场景和关系理解其含义。 | User: “看懂表情” | Unprioritized | Confirmed |
| REQ-002 | Unicode emoji 不得被视为无上下文的固定情绪或成员属性证据；存在多义时必须保守理解。 | Scenario 1 | Unprioritized | Confirmed |
| REQ-003 | 产品必须能够接收目标群中的 Telegram sticker 消息，保留对话所必需的发送者、群、消息、回复关系、时间与表情资产身份信息。 | User / Telegram gap | Unprioritized | Confirmed |
| REQ-004 | 乐枝专属表情包中的已登记 sticker 必须通过已确认目录转换为文字语义；映射结果必须与目录版本和资产身份一致。 | User: 每个表情有文字说明 | Unprioritized | Confirmed |
| REQ-005 | 未登记第三方 sticker 只能使用 Telegram 已提供的可靠元数据；元数据不足时必须标记为未知，不得编造其视觉内容或情绪含义。 | Scenario 3 / DEC-001 | Unprioritized | Confirmed |
| REQ-006 | sticker-only 入站消息只有在原生回复乐枝、符合已确认对话连续性，或另有已确认直接触发证据时，才能获得响应资格；任意 sticker 不得自动触发乐枝。 | Trigger boundary | Unprioritized | Confirmed |
| REQ-007 | 已知表情的文字语义可用于当前场景和回复决策，但不得仅凭一个表情创建敏感成员属性、权威性人格结论或不可修订的长期印象。 | Existing recognition safety | Unprioritized | Confirmed |
| REQ-008 | 产品必须维护版本化乐枝表情目录，每个可发送条目至少包含稳定语义标识、给模型的文字说明、情绪/互动意图、适用场景、禁用场景、关系强度和真实 Telegram 资产映射。 | User proposal | Unprioritized | Confirmed |
| REQ-009 | 模型必须只能从当前已启用目录的文字语义选项中选择表情，不得直接提供 Telegram 资产 ID、表情包名、URL、文件或任意图像作为外部效果。 | User proposal / allowlist boundary | Unprioritized | Confirmed |
| REQ-010 | 应用必须在外部发送前校验模型选择的语义标识、目录版本、人格版本、资产映射和当前启用状态；任一不匹配时不得发送。 | Asset integrity | Unprioritized | Confirmed |
| REQ-011 | 效应器每次必须在“文本回复”、“一个专属 sticker”或“静默”中选择一种最终结果；首发不同时发送文本和 sticker。 | Single-effect contract / DEC-003 | Unprioritized | Confirmed |
| REQ-012 | sticker-only 回复只能用于一个表情足以完整表达的反应、欢迎、庆祝、认可、调皮、思考、尴尬、道歉、轻量安慰或关系化互动。 | User desired outcome / Persona | Unprioritized | Confirmed |
| REQ-013 | 需要事实、步骤、不确定性、权限边界、严肃道歉、医疗/自伤/违法等高风险信息时，必须使用必要文本，不得以 sticker-only 回复替代实质内容。 | Safety and factual integrity | Unprioritized | Confirmed |
| REQ-014 | 表情选择必须受当前 Character Bible、情绪余韵、成员认识置信度和关系温度约束；亲昵、撒娇、偏心或故作不满的表情只能在已有关系支持时使用。 | Character Bible | Unprioritized | Confirmed |
| REQ-015 | 表情不得成为固定口头禅的视觉等价物；乐枝不得连续重复同一 sticker，也不得在多条连续回复中用 sticker 替代有内容的互动。 | Character restraint | Unprioritized | Confirmed |
| REQ-016 | 每条入站消息仍然最多产生一个成功的群内可见外部效果，不得因文本和表情候选同时存在而重复发送。 | Existing single-effect contract | Unprioritized | Confirmed |
| REQ-017 | 未知语义标识、停用条目、版本不匹配、缺失资产或校验失败必须在发送前被拒绝，并安全降级为文本或静默。 | Failure recovery | Unprioritized | Confirmed |
| REQ-018 | Telegram 表情发送结果不确定时不得再发文本或第二表情；只有确认未送达时才允许最多一次文本降级。 | Idempotent recovery | Unprioritized | Confirmed |
| REQ-019 | 每次表情理解或选择必须可审计，至少能识别目标群、人格版本、目录版本、入站表情类别、选定语义标识、结果和降级理由；日志不得记录表情二进制内容、模型完整提示词或凭据。 | Audit | Unprioritized | Confirmed |
| REQ-020 | 入站表情语义、目录和发送必须严格按当前群和人格版本隔离；其他群、私聊或未启用表情包不得成为可用资产或上下文。 | Existing isolation | Unprioritized | Confirmed |
| REQ-021 | 群消息、第三方表情包名、表情元数据或模型输出不得修改启用目录、资产映射、角色视觉定义、Character Bible 或安全规则。 | Prompt and asset integrity | Unprioritized | Confirmed |
| REQ-022 | `TASK-VISUAL-001` 必须在任何生产乐枝表情资产制作前由用户单独确认；Main Work 不得根据文字人格自行决定乐枝的外观。 | Visual identity gap | Unprioritized | Confirmed |
| REQ-023 | `TASK-STICKER-PACK-001` 必须在任何生产表情目录启用前由用户单独确认，并且其视觉、图内文字和语义说明必须彼此一致。 | User: separate pack | Unprioritized | Confirmed |
| REQ-024 | 乐枝视觉形象和表情资产必须完全原创，不得复刻已知版权角色、真人或未授权 IP 的辨识性外观、服饰、道具、组合特征或图像风格。 | Existing originality boundary | Unprioritized | Confirmed |
| REQ-025 | 表情资产必须在 Telegram 实际显示尺寸下保持乐枝可识别性、表情意图和必要图内文字的可读性，且不得通过小字隐藏关键语义。 | Asset acceptance | Unprioritized | Confirmed |
| REQ-026 | 表情目录和真实资产映射必须可识别版本，能与人格版本、验收结果和已启用 Telegram 资产关联，并能回滚到上一个已通过版本。 | Operability | Unprioritized | Confirmed |
| REQ-027 | 首发不得为理解未知第三方 sticker 而下载或持久化图像二进制内容；未来若引入视觉理解，必须重新确认数据来源、保留、成本、超时和降级边界。 | DEC-001 / Data boundary | Unprioritized | Confirmed |

## Acceptance Criteria

| ID | Requirement IDs | Observable criterion | Status |
| --- | --- | --- | --- |
| AC-001 | REQ-001, REQ-002 | Given 同一 emoji 出现在真难过、自嘲和调侃场景，when 乐枝处理，then 候选理解随文本和场景变化，不把 emoji 固定解释或直接写入长期成员属性。 | Confirmed |
| AC-002 | REQ-003, REQ-004 | Given 成员使用已确认乐枝表情包的 sticker 回复乐枝，when 处理，then 系统识别该资产的稳定目录语义，并将其作为当前对话输入。 | Confirmed |
| AC-003 | REQ-005, REQ-027 | Given 成员发送未登记第三方 sticker，when 没有足够可靠元数据，then 系统标记语义未知，不下载图像、不声称看见图像内容。 | Confirmed |
| AC-004 | REQ-006 | Given 普通群成员单独发送一个无回复关系的 sticker，when 不满足对话连续性或其他直接触发，then 不因“这是表情”而自动触发乐枝。 | Confirmed |
| AC-005 | REQ-006, REQ-007 | Given 成员用已知 sticker 原生回复乐枝或在有效连续性窗口中回应，when 处理，then 它获得与对应文本意图一致的响应资格，但不因单次表情形成敏感或不可修订认识。 | Confirmed |
| AC-006 | REQ-008 through REQ-012 | Given 当前是足以由表情完整表达的庆祝或角色化反应，when 模型选择已启用语义标识，then 应用只发送映射的一个乐枝 sticker，群里不出现内部描述、标识或资产 ID。 | Confirmed |
| AC-007 | REQ-009, REQ-010, REQ-017 | Given 模型输出任意资产 ID、未知语义标识、停用条目或错误版本，when 执行前校验，then 该表情不被发送，结果为文本降级或静默。 | Confirmed |
| AC-008 | REQ-011, REQ-016 | Given 同一次触发同时有文本与表情候选，when 最终执行，then 只有文本、一个 sticker 或静默之一，不产生两个成功可见效果。 | Confirmed |
| AC-009 | REQ-013 | Given 成员询问具体事实、步骤或发出严肃求助，when 乐枝回复，then 使用必要文本且不以 sticker-only 替代实质信息。 | Confirmed |
| AC-010 | REQ-014 | Given 同一调皮或撒娇表情分别候选给陌生人和已确认亲近成员，when 选择，then 只在关系证据和目录关系强度都允许时向亲近成员发送。 | Confirmed |
| AC-011 | REQ-015 | Given 乐枝上一次已发送某 sticker，when 紧接着再次候选同一 sticker，then 不连续重复；多轮对话中表情也不取代有必要内容的文本。 | Confirmed |
| AC-012 | REQ-017, REQ-018 | Given 表情发送前校验失败、Telegram 确认未送达或 Telegram 结果不确定，when 降级，then 分别为文本/静默、最多一次文本、不再发送，且无重复可见效果。 | Confirmed |
| AC-013 | REQ-019 | Given 已知、未知、成功、拒绝和降级场景，when 检查审计，then 能识别群、人格/目录版本、语义标识、结果和理由，且无二进制图像、完整提示词或凭据。 | Confirmed |
| AC-014 | REQ-020, REQ-021 | Given 其他群的表情资产或群消息尝试改写目录/角色规则，when 处理，then 不跨群使用资产，也不改变目录、Character Bible 或安全边界。 | Confirmed |
| AC-015 | REQ-022, REQ-024, REQ-025 | Given `TASK-VISUAL-001` 未确认，when 检查 Main Work 或生产资产，then 不存在自行发明的乐枝外观；任务确认后，视觉形象为原创且适合小尺寸识别。 | Confirmed |
| AC-016 | REQ-023 through REQ-026 | Given `TASK-STICKER-PACK-001` 未确认，when 检查生产配置，then 没有启用临时表情或目录；任务确认后，每个资产的视觉、图内文字、文字语义和 Telegram 实际效果一致且可回滚。 | Confirmed |
| AC-017 | REQ-001 through REQ-027 | Given 固定表情评审集覆盖 emoji 多义、已知/未知 sticker、回复与非触发、陌生/亲近、文本必需、重复、映射注入、版本错配、发送失败和回滚，when 发布候选被评审，then 所有关键编造、越权、跨群、重复发送和严肃场景 sticker-only 案例为零且全部预期路径通过。 | Confirmed |

## Constraints

- 本版本建立在已部署的 `main` 和已确认 `lezhi-v1.0` Character Bible 上。
- 首发只支持目标 Telegram 公开群的文本、Unicode emoji 和静态 sticker。
- 角色视觉形象、表情资产和语义目录必须分别版本化并可与验收结果关联。
- 每条入站消息最多一个成功群内可见效果。
- 事实、安全、群隔离、成员认识、触发和审计边界继续沿用已确认前置需求。

## Failure And Recovery

- emoji 含义不清时保守理解，不形成高置信长期结论。
- 未知第三方 sticker 不伪造语义，不为首发视觉理解下载图像。
- 目录、版本、人格或资产映射不匹配时，发送前拒绝并降级为文本或静默。
- Telegram 确认未送达时可最多发送一次安全文本降级；结果不确定时不产生第二效果。
- 专属表情包不可用或模型不选表情时，普通文本对话和静默能力仍然可用。
- 新表情目录或资产版本失败时，可恢复上一个已通过版本，不需要回滚 Character Bible 或成员认识。

## Assumptions

| ID | Assumption | Reason | Impact if wrong | Status |
| --- | --- | --- | --- | --- |
| ASM-001 | 表情能力是已有乐枝的新表达媒介，不新建第二个角色。 | 用户明确说“乐枝”理解和发表情。 | 如果需要多角色运营，触发、人格和资产路由都需重新定义。 | Accepted |
| ASM-002 | “表情”首发指文本中的 Unicode emoji 和 Telegram 静态 sticker。 | 这两类覆盖用户描述的理解与专属表情包。 | 如果必须包含 reaction、custom emoji、动画或视频 sticker，需扩展事件、资产和测试范围。 | Accepted |
| ASM-003 | 模型使用的“文字说明”是内部语义目录，不表示每个 sticker 必须把说明全部印在图上。 | 用户的目标是让模型能以文字选表情。 | 如果每个表情必须含可见文案，资产设计和多语言需求会改变。 | Accepted |
| ASM-004 | 乐枝当前没有已确认视觉外观，需要先完成 Character Visual Bible。 | 现有 Character Bible 定义人格、关系与文字声音，未定义外观。 | 如果已有权威视觉资产，可以把它作为 `TASK-VISUAL-001` 的源材料。 | Accepted |
| ASM-005 | 首发不使用视觉模型理解任意第三方 sticker。 | 先用可控文字目录验证角色表达，避免突然扩大数据、成本和延迟边界。 | 若用户必须理解任意 sticker 图像，需将多模态输入纳入本版本。 | Accepted |
| ASM-006 | 一个 sticker 可以作为完整的乐枝回复，首发不需要同时发文本和 sticker。 | 保持每次一个外部效果，也更像真实群聊中的表情回应。 | 若必须组合回复，需定义多效果顺序、幂等和失败补偿。 | Accepted |
| ASM-007 | 专属表情仅在已确认目录中选择，模型不动态生成新图像。 | 用户提议单独制作一套可用文字选择的表情。 | 如果需要运行时生成，会引入全新的内容审核、延迟和成本边界。 | Accepted |

## Resolved Decisions

| ID | Decision | Options or recommended default | Impact | Status |
| --- | --- | --- | --- | --- |
| DEC-001 | 首发要看懂哪些表情？ | **已接受：** 完整支持 Unicode emoji 和乐枝已登记专属 sticker；第三方 sticker 只使用 Telegram 可靠元数据，未知时不解读；任意图像视觉理解延后。 | 决定多模态模型、媒体下载、成本和隐私范围。 | Accepted |
| DEC-002 | 首发支持哪些 Telegram 表情形态？ | **已接受：** 静态 sticker；reaction、custom emoji、动画 sticker 和视频 sticker 延后。 | 决定事件、文件格式、预览、性能和测试范围。 | Accepted |
| DEC-003 | 乐枝能否同时发文本和 sticker？ | **已接受：** 首发三选一：文本、一个 sticker 或静默；不改变已确认的单外部效果合同。 | 决定效果账本、顺序、幂等和群聊节奏。 | Accepted |
| DEC-004 | 文字说明是否必须显示在 sticker 图上？ | **已接受：** 内部文字语义说明必须有；图内可见短文案按每个表情设计，可选但一旦存在必须单独验收。 | 决定图像构图、小尺寸可读性和未来多语言范围。 | Accepted |
| DEC-005 | 首套表情包多大？ | **已接受：16 个。** 至少覆盖问候、开心、大笑、认可、庆祝、惊讶、疑惑、思考、尴尬、小得意、故作不满、调皮、拒绝/边界、道歉、安慰和晚安；具体视觉与文案在 `TASK-STICKER-PACK-001` 确认。 | 决定语义覆盖、资产成本和评审量。 | Accepted |
| DEC-006 | 视觉与表情包任务如何解锁？ | **已接受：** 先单独确认 `TASK-VISUAL-001`，再制作并确认 `TASK-STICKER-PACK-001`；两项都完成后才启用生产表情。 | 防止 Main Work 静默发明形象或目录。 | Accepted |
| DEC-007 | 表情使用节奏如何控制？ | **已接受：** 只在表情足以完整承载当前意图时 sticker-only；不连续重复同一 sticker，信息性和严肃场景优先文本。 | 决定活人感、刷屏风险和信息完整性。 | Accepted |
| DEC-008 | sticker-only 入站消息何时触发？ | **已接受：** 只有 Telegram 原生回复乐枝、命中已确认对话连续性，或另有直接触发证据时；其他单独 sticker 不自动抢话。 | 决定表情对话连续性和误触发率。 | Accepted |
| DEC-009 | 未知第三方 sticker 如何回应？ | **已接受：** 不固定追问“这是什么”；有其他可靠场景时基于场景回复，否则静默。 | 决定未知输入的自然度和干扰程度。 | Accepted |
| DEC-010 | 表情目录如何版本化？ | **已接受：** 每个人格版本同时最多启用一个已验收表情目录版本；变更视觉语义、图内文字或资产映射时产生新版本，可回滚上一版。 | 决定模型/资产一致性和运维恢复。 | Accepted |

## Traceability

| Source statement or artifact | Derived IDs |
| --- | --- |
| “让乐枝能够看懂表情” | REQ-001 through REQ-007; AC-001 through AC-005; DEC-001, DEC-002, DEC-008, DEC-009 |
| “也能发表情包” | REQ-008 through REQ-021; AC-006 through AC-014; DEC-003, DEC-007, DEC-010 |
| “单独为她做一套，以她的形象制作” | TASK-VISUAL-001; TASK-STICKER-PACK-001; REQ-022 through REQ-026; AC-015, AC-016; ASM-004; DEC-005, DEC-006 |
| “每个表情有文字说明，模型可以使用文字发布表情” | REQ-004, REQ-008 through REQ-010, REQ-023; AC-002, AC-006, AC-007, AC-016; ASM-003; DEC-004 |
| 已确认 Character Bible、触发、成员认识和单外部效果合同 | REQ-006, REQ-007, REQ-011 through REQ-021, REQ-026; AC-004 through AC-014, AC-017 |

## Confirmation

- [x] Problem and desired outcome are correct.
- [x] Goals and non-goals match the intended scope.
- [x] Requirements describe the required behavior.
- [x] Acceptance criteria can judge completion.
- [x] Assumptions are accepted or corrected.
- [x] Decisions are resolved or explicitly deferred.
- [x] `TASK-VISUAL-001` 和 `TASK-STICKER-PACK-001` 被接受为生产表情启用前的单独确认门。
- [x] 未知第三方表情、sticker-only 回复、关系强度和失败降级边界符合预期。

Decision: Confirmed by User in Requirements task on 2026-08-01T01:14:34Z
