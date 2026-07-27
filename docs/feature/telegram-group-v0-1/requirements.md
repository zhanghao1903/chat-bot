# Requirements: Telegram 群聊基础骨架 0.1

- Status: Confirmed
- Requirement owner: User in Requirements task
- Source: User request in Requirements task, 2026-07-27
- Created: 2026-07-27
- Last updated: 2026-07-27
- Confirmed by: User in Requirements task
- Confirmed at: 2026-07-27T01:48:31Z

## Source Request

为 chat-bot 搭建 0.1 版本骨架，使其能够连接 Telegram 群、读取群消息，并能回复简单的固定消息（示例为 `1`）。由于该版本涉及部署和线上服务，仓库还需要一个专用文件夹，集中管理部署配置、服务配置、脚本及相关说明文件。

## Problem And Desired Outcome

chat-bot 需要先证明 Telegram 群聊的最小端到端链路可用。目前缺少一个经过明确验收的 0.1 产品合同，无法一致判断“已连接”“已读取消息”和“已完成固定回复”分别意味着什么。

本版本完成后，群管理员能够把 bot 接入一个目标 Telegram 群；群成员发送普通文本消息时，bot 能接收到消息；当消息命中约定的最小固定规则时，bot 能给出确定且不会循环的回复。负责部署和运维的人员还能从仓库内一个明确的专用目录找到 0.1 所需的部署与服务资产，而不必从源代码或零散目录中寻找。

## Goals

- 建立 bot 到一个目标 Telegram 群的可运行连接。
- 接收并处理群成员发送的普通文本消息。
- 用最小固定规则验证从收消息到回消息的完整链路。
- 在连接失败或配置错误时提供可观察的失败结果和恢复路径。
- 将 0.1 的部署配置、服务配置、脚本和使用说明集中到一个专用目录中。

## Non-goals

- 0.1 不要求 LLM、智能问答、上下文记忆或工具调用。
- 0.1 不要求广告识别、成员管理、删消息、禁言或封禁。
- 0.1 不要求处理图片、文件、语音、视频、贴纸等非文本消息。
- 0.1 不要求私聊支持、多个群的管理界面或 SaaS 多租户能力。
- 根据已确认的 `DEC-002`，0.1 不把群消息长期持久化作为验收条件。
- 0.1 不要求 Webhook；连接方式属于后续技术设计，只要满足本需求的可观察行为即可。
- 0.1 不要求自动化 CI/CD、零停机发布、集群编排或多环境发布平台。
- 0.1 不要求把生产密钥、运行日志、数据库文件或其他运行时数据存入部署专用目录。

## User Scenarios

### Scenario 1: 管理员接入目标群

- Actor: Telegram 群管理员
- Starting context: 管理员已有可用的 bot 身份，并能把 bot 加入目标群。
- Action: 管理员完成必要配置并启动 chat-bot。
- Expected outcome: chat-bot 进入可接收该群消息的运行状态，且不会把失败状态误报为已连接。
- Failure recovery: 如果身份凭据、群权限或网络配置错误，管理员能看到可定位的失败信息；修正配置并重新启动后可以恢复。

### Scenario 2: 群成员发送固定触发消息

- Actor: Telegram 群成员
- Starting context: chat-bot 已连接目标群并具备读取普通文本消息的权限。
- Action: 群成员发送文本 `1`。
- Expected outcome: bot 对该条消息只回复一次文本 `1`。
- Failure recovery: 如果发送回复失败，系统提供可观察的错误；不得通过无限重复回复来重试。

### Scenario 3: 群成员发送普通文本

- Actor: Telegram 群成员
- Starting context: chat-bot 已连接目标群。
- Action: 群成员发送不匹配固定规则的普通文本消息。
- Expected outcome: chat-bot 能读取消息内容及识别该消息所属群、发送者和消息标识，但不会发送固定回复。
- Failure recovery: 单条消息无法解析时应记录或暴露该失败，并继续处理后续可用消息。

### Scenario 4: 运维人员查找部署与服务资产

- Actor: 负责部署或线上服务维护的人员
- Starting context: 运维人员已取得 0.1 版本仓库。
- Action: 运维人员需要查找 0.1 的部署配置、服务配置、脚本或相关使用说明。
- Expected outcome: 运维人员能从一个明确的专用目录找到这些受版本控制的资产，并能通过目录说明了解其用途和使用入口。
- Failure recovery: 如果某项资产依赖外部密钥或环境值，目录内使用模板、占位符或外部引用进行说明，不要求也不得通过提交真实生产密钥来补齐。

## Functional Requirements

| ID | Requirement | Source | Priority | Confirmation |
| --- | --- | --- | --- | --- |
| REQ-001 | 在提供有效 Telegram bot 身份、目标群接入条件和网络条件后，chat-bot 必须能够启动并进入接收该群消息的运行状态。 | User: “能够连接电报群” | Unprioritized | Confirmed |
| REQ-002 | chat-bot 必须能够接收目标群中 Telegram 实际投递给 bot 的普通文本消息。 | User: “能够读取群里的消息” | Unprioritized | Confirmed |
| REQ-003 | 对每条已接收的普通文本消息，处理链路必须至少能够使用消息文本、群标识、发送者标识和消息标识。 | User: “能够读取群里的消息” | Unprioritized | Confirmed |
| REQ-004 | 当群成员发送精确文本 `1` 时，chat-bot 必须对原消息回复精确文本 `1`。 | User: “能够回复简单的固定消息，如 1” / DEC-001 | Unprioritized | Confirmed |
| REQ-005 | 对不匹配固定规则的普通文本，chat-bot 不得发送该固定回复。 | ASM-003 | Unprioritized | Confirmed |
| REQ-006 | chat-bot 对固定触发消息最多发送一次固定回复，并且其自身发送的回复不得再次触发同一规则。 | ASM-003 | Unprioritized | Confirmed |
| REQ-007 | 身份凭据无效、权限不足或 Telegram 连接失败时，chat-bot 必须给出可观察的失败结果，不得把失败状态报告为已连接；问题修正后必须存在可执行的恢复方式。 | Scenario 1 | Unprioritized | Confirmed |
| REQ-008 | 单条无法解析或处理的消息不得导致后续可用群消息永久停止处理。 | Scenario 3 | Unprioritized | Confirmed |
| REQ-009 | 仓库必须提供一个与应用源代码明确分离的顶层 `deploy/` 目录，用于集中管理 0.1 的部署配置、服务配置、运维脚本及相关说明。 | User request / DEC-003 | Unprioritized | Confirmed |
| REQ-010 | 0.1 新增的、受版本控制的部署与线上服务资产必须存放在 `deploy/` 或其子目录中，不得无说明地散落在应用源代码目录中。 | User request / Scenario 4 | Unprioritized | Confirmed |
| REQ-011 | `deploy/` 必须包含入口说明，能够标明目录内资产的用途、必要外部配置以及面向部署或服务管理人员的使用入口。 | Scenario 4 | Unprioritized | Confirmed |
| REQ-012 | `deploy/` 内的配置和脚本不得包含真实生产密钥、Telegram bot token 或其他敏感凭据；需要敏感值时必须使用模板、占位符或外部引用。 | Scenario 4 / ASM-005 | Unprioritized | Confirmed |

## Acceptance Criteria

| ID | Requirement IDs | Observable criterion | Confirmation |
| --- | --- | --- | --- |
| AC-001 | REQ-001 | Given 有效 bot 身份、bot 已加入目标群且具备必要权限，when 启动 chat-bot，then 服务进入持续接收该群消息的运行状态，且能观察到启动成功。 | Confirmed |
| AC-002 | REQ-002, REQ-003 | Given chat-bot 正常运行，when 群成员发送普通文本消息，then 处理链路能观察到原始文本，并能关联正确的群标识、发送者标识和消息标识。 | Confirmed |
| AC-003 | REQ-004, REQ-006 | Given chat-bot 正常运行，when 群成员发送精确文本 `1`，then bot 对该消息发送且只发送一次精确文本 `1`。 | Confirmed |
| AC-004 | REQ-005 | Given chat-bot 正常运行，when 群成员发送不匹配固定规则的文本，then bot 不发送固定文本 `1`。 | Confirmed |
| AC-005 | REQ-006 | Given bot 已因触发消息回复 `1`，when Telegram 将 bot 自己的回复作为事件暴露给处理链路，then 该回复不会触发新的固定回复。 | Confirmed |
| AC-006 | REQ-007 | Given bot 身份无效、权限不足或 Telegram 不可达，when 启动或运行 chat-bot，then 可观察到失败且不会出现虚假的已连接状态；修正问题并执行恢复操作后可以重新进入正常运行状态。 | Confirmed |
| AC-007 | REQ-008 | Given 一条消息无法解析或处理，when 后续到达一条有效普通文本消息，then chat-bot 仍能接收并处理后续消息。 | Confirmed |
| AC-008 | REQ-009, REQ-010 | Given 0.1 的完整仓库，when 运维人员查找部署和线上服务相关资产，then 仓库顶层存在 `deploy/`，且 0.1 新增的相关配置、脚本与说明均位于该目录或其子目录中。 | Confirmed |
| AC-009 | REQ-011 | Given 运维人员打开 `deploy/`，when 阅读入口说明，then 能识别目录内资产的用途、必要外部配置和使用入口。 | Confirmed |
| AC-010 | REQ-012 | Given 检查 `deploy/` 中受版本控制的文件，when 识别其配置值和凭据引用，then 不存在真实生产密钥或 Telegram bot token，敏感值仅以模板、占位符或外部引用表达。 | Confirmed |

## Constraints

- 第一接入平台是 Telegram。
- 目标版本为 `0.1`，范围仅覆盖最小群聊收发骨架。
- Telegram 必须被配置为向 bot 投递验收所需的普通群文本消息；Telegram 平台权限或隐私模式造成的不可见消息不属于 chat-bot 可读取范围。
- 不在需求文档中指定 long polling、Webhook、SDK 或存储实现；这些属于 Main Work 的技术设计。
- 部署与服务资产必须通过仓库顶层 `deploy/` 集中管理；内部层级由 Main Work 在技术设计中确定。

## Failure And Recovery

- 配置或权限错误：暴露失败原因，修正后通过明确的重新启动或重连操作恢复。
- 暂时网络或 Telegram API 失败：失败必须可观察，且不得伪装成成功回复。
- 单条消息解析失败：隔离该消息，继续接收后续消息。
- 回复发送失败：不得生成回复循环；是否自动重试由后续技术设计决定。
- 部署资产依赖敏感值：使用明确的外部配置说明，不得把真实敏感值提交到仓库作为恢复手段。

## Assumptions

| ID | Assumption | Reason | Impact if wrong | Status |
| --- | --- | --- | --- | --- |
| ASM-001 | 0.1 只需验收一个预先指定的 Telegram 群。 | 用户使用单数“群”，且目标是先搭骨架。 | 如果需要同时支持多个群，需增加群隔离、配置和跨群验收范围。 | Accepted |
| ASM-002 | “读取群消息”在 0.1 中指接收并让处理链路可使用普通文本及必要标识，不等同于长期保存全部消息。 | 用户要求读取，但未要求历史查询或持久化。 | 如果必须持久化，需要补充保存范围、保留时间和隐私要求。 | Accepted |
| ASM-003 | 未命中固定规则时保持静默，并防止 bot 自身回复造成循环。 | 最小群聊 bot 需要避免无关回复和无限循环。 | 如果希望对所有消息回复，需要重新定义触发与防刷屏规则。 | Accepted |
| ASM-004 | 管理员负责创建 bot、将其加入目标群，并配置 Telegram 侧必要权限或隐私设置。 | 这些动作发生在 chat-bot 服务之外。 | 如果产品必须自动引导或验证这些步骤，需要增加接入流程需求。 | Accepted |
| ASM-005 | 部署专用目录只管理适合版本控制的配置模板、服务定义、脚本和说明，不保存线上运行产生的数据、日志或真实密钥。 | 用户要求集中管理配置和脚本，但未要求把运行时状态纳入仓库。 | 如果还要管理运行数据或秘密分发，需要增加独立的数据、备份和密钥管理需求。 | Accepted |

## Resolved Decisions

| ID | Decision | Resolution | Impact | Status |
| --- | --- | --- | --- | --- |
| DEC-001 | 0.1 的固定消息规则具体是什么？ | 成员发送精确文本 `1`，bot 回复精确文本 `1`。 | 决定 `REQ-004` 和 `AC-003` 的确切测试输入与输出。 | Accepted |
| DEC-002 | 0.1 是否要求长期保存读取到的群消息？ | 不作为 0.1 验收条件，仅要求当前处理链路可读取；持久化需求延后定义。 | 如果未来要求保存，需要补充数据范围、保留、访问和删除规则。 | Accepted |
| DEC-003 | 部署与服务专用目录使用什么名称？ | 仓库顶层使用 `deploy/`。 | 决定相关资产的统一入口路径及验收路径。 | Accepted |
| DEC-004 | 0.1 的部署专用目录首批至少包含哪些资产？ | 包含入口说明、非敏感配置模板，以及所选线上运行方式实际需要的服务定义和管理脚本；精确文件清单由技术设计确定。 | 决定 Main Work 的部署资产实现边界，但不扩展到 CI/CD 或集群编排。 | Accepted |

## Traceability

| Source statement or artifact | Derived IDs |
| --- | --- |
| “能够连接电报群” | REQ-001, REQ-007; AC-001, AC-006 |
| “能够回复简单的固定消息，如 1” | REQ-004, REQ-005, REQ-006; AC-003, AC-004, AC-005; DEC-001 |
| “能够读取群里的消息” | REQ-002, REQ-003, REQ-008; AC-002, AC-007; ASM-002, DEC-002 |
| “一个文件夹专门管理部署和服务相关的配置和脚本等相关文件” | REQ-009, REQ-010, REQ-011, REQ-012; AC-008, AC-009, AC-010; ASM-005; DEC-003, DEC-004 |

## Confirmation

- [x] Problem and desired outcome are correct.
- [x] Goals and non-goals match the intended scope.
- [x] Requirements describe the required behavior.
- [x] Acceptance criteria can judge completion.
- [x] Assumptions are accepted or corrected.
- [x] Decisions are resolved or explicitly deferred.

Decision: Confirmed by User in Requirements task at 2026-07-27T01:48:31Z
