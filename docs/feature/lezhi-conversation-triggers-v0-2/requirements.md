# Requirements: 乐枝对话连续性触发 v0.2

- Status: Confirmed
- Requirement owner: User in Requirements task
- Source: Requirements conversation on 2026-07-31
- Created: 2026-07-31
- Last updated: 2026-07-31
- Confirmed by: User in Requirements task
- Confirmed at: 2026-07-31T11:32:56Z
- Baseline: `codex/maomao-persona-chat` at `7c73ca0f809643a2e83362922212a05f843b694d`

## Source Request

下一版本扩充乐枝在 Telegram 群中的触发方式：

1. 群成员不用 `@`，直接用角色称呼呼叫，例如“乐枝，你看看……”。
2. 乐枝发言后，群成员即使没有使用 Telegram 回复、`@` 或角色称呼，只要当前消息从聊天内容上是在回应乐枝，机器人也能识别这段对话连续性。

## Problem And Desired Outcome

当前已评审版本只把 `@机器人`、Telegram 原生回复机器人以及机器人命令视为直接触发。其他消息即使自然语言上明显是在叫乐枝，或是在回答乐枝刚提出的问题，也会落入普通主动参与路径，受到至少 15 分钟和 5 条真人消息的保守门槛限制。这会让连续对话突然中断，使角色显得听不懂自己的名字，也不记得刚刚说过什么。

目标是在不要求成员学习 Telegram 操作的情况下，让乐枝能够识别：

- 群成员是否在自然语言中直接呼叫她；
- 群成员是否在延续她刚刚参与的对话；
- 当前消息只是谈论乐枝、引用她、结束话题，还是确实期待她继续回应。

新触发能力必须提高连续对话的自然度，同时避免把每次出现“乐枝”或每条紧随机器人之后的群消息都误判为对她说话。

## Actors

- Telegram 群成员：用自然语言呼叫乐枝，或延续乐枝刚参与的对话。
- 乐枝：识别自己是当前消息的交流对象，并按 Character Bible、关系认识和当前场景回复或克制地静默。
- 群内其他成员：即使正在谈论乐枝，也不应因为误触发而被机器人抢话。

## Goals

- 支持不带 `@` 的“乐枝”直接称呼触发。
- 支持依据当前公开群聊内容识别对乐枝最近发言的自然回应。
- 将对话连续性触发与普通主动参与区分，避免受到 15 分钟/5 条消息门槛的错误阻断。
- 保留乐枝选择静默的能力，特别是话题自然结束或交流对象不明确时。
- 为每次新触发记录可理解的触发类别和依据，便于发现误触发与漏触发。
- 保持现有 Character Bible、安全、群隔离、单次最多一个外部效果和失败降级边界。

## Non-goals

- 不要求本版本支持语音、图片、贴纸、私聊或 Telegram 之外的平台。
- 不把所有包含“乐枝”的消息都视为直接呼叫。
- 不把所有出现在乐枝消息之后的群消息都视为对乐枝的回答。
- 不保证识别到对话连续性后每次都发送消息；无新增价值的收尾回应可以静默。
- 不改变乐枝的人格、成员认识、关系偏好、工具权限或数据保留合同。
- 不放宽与乐枝无关的普通主动参与所使用的 15 分钟/5 条真人消息门槛。
- 不在需求阶段指定正则表达式、分类模型、提示词、数据库字段或组件边界。
- 不自动从群成员随口使用的称呼中学习永久昵称。

## User Scenarios

### Scenario 1: 使用角色称呼直接叫乐枝

- Actor: Telegram 群成员
- Starting context: 乐枝已在目标群启用；成员没有使用 `@` 或 Telegram 原生回复。
- Action: 成员发送“乐枝，你看看这个”“乐枝 你怎么看？”或“你觉得呢，乐枝？”等明确把乐枝作为交流对象的文本。
- Expected outcome: 消息被识别为直接称呼触发，不受普通主动参与的 15 分钟/5 条消息门槛限制；乐枝依据当前场景和人格发送最多一条回复。
- Failure recovery: 如果称呼边界无法可靠确认，则不得仅凭名字出现而强制回复；消息可以按普通主动参与规则继续评估。

### Scenario 2: 回答乐枝刚刚提出的问题

- Actor: Telegram 群成员
- Starting context: 乐枝最近在当前群提出问题或明确邀请成员继续说明；对话仍处于有效连续性范围。
- Action: 成员直接发送“我觉得第二个更好”“因为前一个太慢了”或其他语义上回答该问题的文本，但没有 `@`、Telegram 回复或角色称呼。
- Expected outcome: 消息被识别为对话连续性候选，不受普通主动参与门槛阻断；乐枝结合自己的最近发言和当前成员回复，自然地继续对话。
- Failure recovery: 无法确定回答对象、上下文已过期或中间话题已明显转移时，不得猜测成员在回答乐枝。

### Scenario 3: 对乐枝的陈述作出反应或追问

- Actor: Telegram 群成员
- Starting context: 乐枝最近给出建议、观察、玩笑或具体事实。
- Action: 成员发送“这个角度挺有意思”“那如果换成周末呢？”“你刚才第二点是什么意思？”等在内容上承接乐枝发言的消息。
- Expected outcome: 系统能把相关消息识别为对话连续性候选；若继续回应符合角色参与价值，乐枝发送最多一条关联回复。
- Failure recovery: 仅凭时间相邻但内容无关时保持普通消息处理，不制造虚假的一问一答关系。

### Scenario 4: 对话自然结束

- Actor: Telegram 群成员
- Starting context: 乐枝刚完成回答。
- Action: 成员发送“收到”“好哒”“哈哈行”等没有新问题、新信息或继续邀请的收尾回应。
- Expected outcome: 系统可以识别该消息与乐枝有关，但乐枝可以选择静默，让对话自然结束；静默不是错误或模型失败。
- Failure recovery: 若收尾消息同时包含明确的新问题或请求，应按新内容继续回应。

### Scenario 5: 群成员只是谈论或引用乐枝

- Actor: Telegram 群成员
- Starting context: 群内成员彼此交谈。
- Action: 成员发送“我觉得乐枝刚才说得对”“小王，你看乐枝发的第二点”或引用包含“乐枝”的旧文本，但没有把当前话语指向乐枝。
- Expected outcome: 不因名字出现而进入直接称呼触发；只有满足普通主动参与条件时才可作为普通候选参与。
- Failure recovery: 有歧义时宁可按普通消息处理或静默，不抢占成员之间的对话。

### Scenario 6: 多人插话导致回应对象不明确

- Actor: 多名 Telegram 群成员
- Starting context: 乐枝发言后，多名成员围绕相近话题交错发言。
- Action: 当前成员发送一句既可能回应乐枝，也可能回应另一位群成员的话。
- Expected outcome: 系统使用最近公开群聊场景判断交流对象；证据不足时不把消息提升为对话连续性触发。
- Failure recovery: 消息仍可按现有普通主动参与规则评估；不得编造被回复的对象或共同上下文。

## Functional Requirements

| ID | Requirement | Source | Priority | Confirmation |
| --- | --- | --- | --- | --- |
| REQ-001 | 产品必须在现有 `@机器人`、Telegram 原生回复和命令之外，支持通过已确认角色称呼直接触发乐枝。 | User item 1 | Unprioritized | Confirmed |
| REQ-002 | 本版本至少必须把当前 Character Bible 的正式角色名“乐枝”作为可用称呼；其他别名只有被产品明确配置后才可成为直接触发称呼。 | Character Bible / DEC-001 | Unprioritized | Confirmed |
| REQ-003 | 角色称呼只有在当前语句中承担呼语、直接交流对象或明确点名请求的作用时，才能成为直接触发；句首、句尾、全角或半角标点以及合理空格差异不得阻断明确呼叫。 | Scenario 1 | Unprioritized | Confirmed |
| REQ-004 | 仅在第三人称中谈论乐枝、向其他成员引用乐枝的话、讨论乐枝的历史发言或在不指向乐枝的列表中出现名字，不得仅凭名字命中直接触发。 | Scenario 5 | Unprioritized | Confirmed |
| REQ-005 | 已确认的角色称呼直接触发必须与 `@机器人` 和 Telegram 原生回复具有同级的响应资格，不受普通主动参与的 15 分钟/5 条真人消息门槛限制。 | User item 1 | Unprioritized | Confirmed |
| REQ-006 | 产品必须能够依据当前公开群聊场景，判断没有 `@`、原生回复或角色称呼的成员消息是否在回应乐枝最近发送的消息。 | User item 2 | Unprioritized | Confirmed |
| REQ-007 | 对话连续性判断至少必须能够识别：回答乐枝提出的问题、接受或拒绝她的建议、回应她的观察或玩笑、追问她刚说的内容，以及继续她明确邀请的话题。 | Scenarios 2 and 3 | Unprioritized | Confirmed |
| REQ-008 | 对话连续性判断不得只依赖时间相邻；必须有来自当前消息内容和最近场景的可解释关联证据。 | False-positive boundary | Unprioritized | Confirmed |
| REQ-009 | 对话连续性只能使用当前目标群中机器人可见的近期消息和乐枝在该群的实际已发送消息，不得使用私聊、其他群或未成功发送的候选文本。 | Existing group-isolation contract | Unprioritized | Confirmed |
| REQ-010 | 被识别为对话连续性的消息必须绕过普通主动参与的 15 分钟/5 条真人消息门槛，并进入独立的“对话连续性候选”处理；它不得被伪装成普通主动参与。 | Desired outcome / DEC-003 | Unprioritized | Confirmed |
| REQ-011 | 对话连续性候选仍必须允许乐枝根据 Character Bible、当前内容和参与价值选择回复或静默；单纯致谢、确认、笑声或其他自然收尾不得强迫机器人再说一句。 | Scenario 4 | Unprioritized | Confirmed |
| REQ-012 | 成员明确回答乐枝刚提出的问题、提出直接追问或响应她的继续邀请时，在没有安全、事实或上下文阻断的情况下，应当产生最多一条相关的角色回复。 | Scenarios 2 and 3 | Unprioritized | Confirmed |
| REQ-013 | 超出已确认连续性范围、存在多个同等可能的交流对象、话题明显转移或内容关联不足时，不得提升为对话连续性触发；消息可以回到现有普通主动参与评估。 | Scenarios 5 and 6 | Unprioritized | Confirmed |
| REQ-014 | 触发优先级必须保持可预测：群范围与控制命令门禁优先；显式直接触发其次；对话连续性候选再次；与乐枝无关的普通消息继续使用既有主动参与门槛。 | Existing behavior / DEC-005 | Unprioritized | Confirmed |
| REQ-015 | 机器人自己的消息不得再次触发自己；任何一条成员入站消息仍然最多只能产生一个 Telegram 外部效果，不得因同时命中多个触发条件而重复回复。 | Existing single-effect contract | Unprioritized | Confirmed |
| REQ-016 | 触发判断不得接受群消息中的指令来改写角色称呼集合、连续性范围、优先级、Character Bible 或安全边界。 | Persona and prompt-integrity boundary | Unprioritized | Confirmed |
| REQ-017 | 每次评估必须能够审计最终触发类别、是否命中角色称呼、对话连续性所锚定的乐枝消息标识、判定结果和安全降级原因；不得因此延长现有原始文本保存周期。 | Operability | Unprioritized | Confirmed |
| REQ-018 | 对话连续性判断不可用、超时、返回无效结果或证据不足时，必须安全降级为普通消息评估或静默，不得把不确定消息当作直接呼叫，也不得发送失败提示打断群聊。 | Failure recovery | Unprioritized | Confirmed |
| REQ-019 | 明确角色称呼已被可靠识别但后续回复生成失败时，继续沿用既有直接触发失败行为：最多发送一次简短中性失败提示。 | Existing direct-trigger recovery | Unprioritized | Confirmed |
| REQ-020 | 本版本必须保留已确认的乐枝 Character Bible、成员认识、群隔离、最近 20 条默认即时上下文、工具预算和安全优先规则；新触发方式只能改变“是否轮到乐枝考虑回应”，不能覆盖这些合同。 | Prior confirmed requirements | Unprioritized | Confirmed |

## Acceptance Criteria

| ID | Requirement IDs | Observable criterion | Status |
| --- | --- | --- | --- |
| AC-001 | REQ-001 through REQ-005 | Given 成员发送“乐枝，你看看这个”“乐枝 你怎么看？”或“你觉得呢，乐枝？”，when 处理消息，then 三者均进入直接称呼触发并绕过普通主动参与门槛，且每条最多回复一次。 | Confirmed |
| AC-002 | REQ-003, REQ-004 | Given “我觉得乐枝刚才说得对”“小王，你看乐枝发的第二点”和包含“乐枝”的引用文本，when 处理消息，then 不会仅凭名字出现而判为直接称呼。 | Confirmed |
| AC-003 | REQ-006 through REQ-010, REQ-012 | Given 乐枝刚问“你更喜欢哪个方案？”，when 成员在确认范围内直接发送“第二个，比较省事”，then 消息进入对话连续性候选并在无其他阻断时得到关联回复，不等待 15 分钟或 5 条消息。 | Confirmed |
| AC-004 | REQ-006 through REQ-010, REQ-012 | Given 乐枝刚给出一个观察或建议，when 成员发送语义明确的追问或反应但没有显式寻址，then 系统能锚定乐枝的实际已发送消息并继续相关对话。 | Confirmed |
| AC-005 | REQ-011 | Given 乐枝刚完成回答，when 成员只发送“收到”“好哒”或“哈哈行”，then 系统允许以自然收尾为理由静默，且审计中不把它记录为失败。 | Confirmed |
| AC-006 | REQ-008, REQ-013 | Given 乐枝消息之后出现与其内容无关的成员消息，when 仅有时间相邻而没有内容关联，then 不判为对话连续性触发。 | Confirmed |
| AC-007 | REQ-008, REQ-013 | Given 乐枝发言后多名成员交错讨论，when 当前消息可能同等合理地回应另一成员，then 不猜测它在回应乐枝，并按普通消息评估或静默。 | Confirmed |
| AC-008 | REQ-009 | Given 其他群或私聊中存在相似对话，when 目标群消息被评估，then 不使用其他群、私聊或未发送候选作为连续性锚点。 | Confirmed |
| AC-009 | REQ-014 | Given 同一消息同时包含控制命令、角色称呼或其他候选信号，when 处理消息，then 按已确认优先级只走一个处理路径；与乐枝无关的普通消息仍受原主动参与门槛约束。 | Confirmed |
| AC-010 | REQ-015 | Given 乐枝发送一条消息或同一成员消息同时命中多个触发信号，when 处理完成，then 不发生机器人自触发，且该入站消息最多产生一个外部效果。 | Confirmed |
| AC-011 | REQ-016 | Given 群成员要求把自己的名字加入乐枝称呼、扩大连续性窗口或忽略安全边界，when 处理消息，then 运行时触发合同不改变。 | Confirmed |
| AC-012 | REQ-017 | Given 分别发生角色称呼、对话连续性命中、歧义降级和普通主动参与，when 检查审计，then 能区分类别、结果和安全理由；连续性命中还能关联实际乐枝消息标识。 | Confirmed |
| AC-013 | REQ-018, REQ-019 | Given 对话连续性判断不可用，when 消息没有显式触发，then 安全降级且不发送失败提示；given 明确称呼触发后的回复生成失败，then 最多发送一次既有中性失败提示。 | Confirmed |
| AC-014 | REQ-020 | Given 新触发方式命中，when 生成或静默，then Character Bible、成员认识边界、群隔离、工具预算、事实与安全规则仍与上一确认版本一致。 | Confirmed |
| AC-015 | REQ-001 through REQ-020 | Given 固定触发评审集包含明确称呼、第三人称提及、回答问题、追问、反应、收尾、过期、多人歧义、跨群、注入、故障和重复信号场景，when 发布候选被评审，then 所有关键误触发/重复发送案例为零且全部预期路径通过。 | Confirmed |

## Constraints

- 本版本建立在已确认并评审的乐枝 `lezhi-v1.0` Character Bible 之上。
- 只处理目标 Telegram 公开群中的文本消息。
- 最近 20 条普通文本仍是默认即时上下文上限。
- 对话连续性触发不是扩大数据来源或保留周期的授权。
- 每条入站消息最多一个外部效果；安全与事实规则优先于回复欲望。
- 与乐枝无关的普通主动参与继续保留至少 15 分钟且间隔 5 条真人消息的现有门槛。

## Failure And Recovery

- 明确角色称呼不能可靠确定时，不把名字出现强制升级为直接触发。
- 对话连续性判断超时、不可用、结果无效或证据不足时，回到普通消息评估或静默。
- 锚定的乐枝消息不存在、未成功发送、已超出范围或属于其他群时，不使用该锚点。
- 多人交错导致交流对象不清楚时，不猜测成员在回答乐枝。
- 对话连续性候选的静默不生成面向群成员的错误提示。
- 明确直接称呼后的回复生成失败继续使用既有一次性中性失败提示。
- 重放同一入站消息不得产生第二个外部效果。

## Assumptions

| ID | Assumption | Reason | Impact if wrong | Status |
| --- | --- | --- | --- | --- |
| ASM-001 | 当前 `lezhi-v1.0` Character Bible 和上一版本已确认的安全、认识、工具及群隔离合同继续有效。 | 用户只要求新增触发方式。 | 如果同时修改人格或认识合同，需要扩大需求范围并重新评审 Character Bible。 | Accepted |
| ASM-002 | 本版本只验证目标公开 Telegram 群中的文本对话。 | 当前产品与用户示例都是群文本。 | 媒体、语音、贴纸或私聊需要独立触发语义。 | Accepted |
| ASM-003 | “昵称触发”指成员使用已确认的角色称呼直接与乐枝说话，而不是名字在任意语境中出现。 | 用户示例“乐枝，你看看……”体现呼语。 | 如果任意出现都应触发，将显著增加误触发和抢话。 | Accepted |
| ASM-004 | 对话连续性需要结合内容和近期场景判断，不能只看上一条消息的发送者。 | 用户明确要求“从聊天内容判断”。 | 如果只要求紧邻规则，需求和评测可更简单但误触发更高。 | Accepted |
| ASM-005 | 对话连续性消息属于响应式互动，因此可以绕过普通主动参与门槛，但仍可因自然收尾选择静默。 | 连续对话不应等待 15 分钟/5 条消息。 | 如果每次都必须回复，会形成“收到—好的—嗯嗯”的无意义尾巴。 | Accepted |
| ASM-006 | 现有最近 20 条默认即时上下文足以承载本版本的连续性判断，不需要扩大原始文本窗口。 | 上一版本已确认该上限。 | 若真实群中对话经常跨越更长上下文，需要另行调整数据与保留边界。 | Accepted |

## Resolved Decisions

| ID | Decision | Options or recommended default | Impact | Status |
| --- | --- | --- | --- | --- |
| DEC-001 | 首发角色称呼集合包含哪些文本？ | **已接受：** 首发只包含 Character Bible 正式名“乐枝”；后续别名必须显式配置并随人格版本管理，不从群聊自动学习。 | 决定误触发率、角色一致性和配置边界。 | Accepted |
| DEC-002 | 对话连续性允许锚定多早的乐枝消息？ | **已接受：** 只考虑当前群最近一次成功发送的乐枝消息，且该消息在 10 分钟内、之后不超过 5 条真人消息；仍必须通过内容关联判断。 | 决定漏触发、误触发和场景成本。 | Accepted |
| DEC-003 | 识别为对话连续性后是否强制回复？ | **已接受：** 不强制。绕过普通主动参与门槛，但由乐枝判断继续回复或自然收尾；明确回答、追问或继续邀请在无其他阻断时应回复。 | 决定自然度与“机器人总要最后说一句”的风险。 | Accepted |
| DEC-004 | 歧义或连续性判断失败后如何处理？ | **已接受：** 回到现有普通主动参与评估；若不满足 15 分钟/5 条消息门槛则静默，不发送失败提示。 | 决定安全降级与漏回复体验。 | Accepted |
| DEC-005 | 新旧触发路径的优先级是什么？ | **已接受：** 群范围/控制命令 → `@`、Telegram 回复、已确认角色称呼 → 对话连续性候选 → 普通主动参与。命中更高优先级后不再执行低优先级路径。 | 决定重复效果和可预测性。 | Accepted |
| DEC-006 | 触发审计保存什么？ | **已接受：** 保存触发类别、结果、理由码和连续性锚点消息标识；不因本功能额外长期保存消息全文。 | 决定可诊断性和数据边界。 | Accepted |

## Traceability

| Source statement or artifact | Derived IDs |
| --- | --- |
| “增加昵称触发，比如说，乐枝，你看看……” | Scenario 1; REQ-001 through REQ-005; AC-001, AC-002; ASM-003; DEC-001 |
| “从聊天内容判断，别人对乐枝的回答” | Scenarios 2 through 4; REQ-006 through REQ-013; AC-003 through AC-007; ASM-004 through ASM-006; DEC-002 through DEC-004 |
| 现有 `@`、Telegram 回复和普通主动参与门槛 | REQ-005, REQ-010, REQ-014, REQ-019; AC-009, AC-013; DEC-005 |
| 已确认的 Character Bible、群隔离和单外部效果合同 | REQ-009, REQ-015 through REQ-020; AC-008, AC-010 through AC-015; ASM-001 |

## Confirmation

- [x] Problem and desired outcome are correct.
- [x] Goals and non-goals match the intended scope.
- [x] Requirements describe the required behavior.
- [x] Acceptance criteria can judge completion.
- [x] Assumptions are accepted or corrected.
- [x] Decisions are resolved or explicitly deferred.
- [x] “直接称呼”与“仅谈论乐枝”的边界符合预期。
- [x] 对话连续性范围、静默规则和安全降级符合预期。

Decision: Confirmed by User in Requirements task on 2026-07-31T11:32:56Z
