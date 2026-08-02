# Requirements: 乐枝人格 v2 发布与低频版本管理

- Status: Confirmed
- Requirement owner: User in Requirements task
- Source: Requirements conversation and user-supplied persona bundle on 2026-08-02
- Created: 2026-08-02
- Last updated: 2026-08-02
- Confirmed by: User in Requirements task
- Confirmed at: 2026-08-02T00:34:24Z
- Supersedes: RequirementsHandoff `7ca86de3a3557f76ebba5727ea5d1238a73221c2f4aad6d7c2c0e7a89a7f45f0` after source-digest correction
- Baseline: `origin/main` at `4f50c14e748afd00c097393c0fa481184c006e12`

## Source Request

用户提供了新的乐枝设定包 `lezhi-persona-v2-bundle.zip`，要求把它更新到项目中、为低频人格更新建立版本管理，并在完成后重启容器。

本需求快照锁定的输入制品为：

| Artifact | SHA-256 | Notes |
| --- | --- | --- |
| `lezhi-persona-v2-bundle.zip` | `c78c3be1835d1ad5d25c1bb41ea9ccaa60f8d90a365f59e7cf563d10a6c2ac06` | 用户提供的完整源包 |
| `lezhi-persona-v2.json` | `600fed847d362f272739d6613874aac857e339c02bc76c18619d104280dbbfcc` | 人格源数据，声明 `id=lezhi`、`version=2.0` |
| `evaluation-cases.jsonl` | `676d03a5f2e5bf4b2c822ab507abe4516c133a4d6ad754dd265dbfdabb7cb08d` | 37 条固定评测用例，`CB-EVAL-001` 至 `CB-EVAL-037` |
| `examples.jsonl` | `7172725c8e1aed81470b8c9257b54ba8f93fa87fcf4e5d99e5df906f0382b420` | 与 37 条评测用例对应的角色行为样例 |

确认本快照即表示：上述精确摘要对应的三份内容是乐枝 v2 的权威产品输入；若文件内容变化，必须形成新快照和新版本，不得继续沿用本次确认。

## Problem And Desired Outcome

项目当前已经以 `lezhi-v1.0` 的不可变目录、清单和内容摘要加载人格，但新的 v2 源数据增加了会直接影响角色表现的规则，包括：反客服/反默认建议倾向、笑点识别与接梗节制、真实反应优先、提问克制、主观品味、短时情绪延续、尴尬与玩笑失败修复，以及非具身身份边界。当前加载合同不能直接接受这些新增字段；把文件改名后覆盖旧目录会丢失语义、破坏摘要锁定并失去可靠回滚能力。

目标是把用户提供的 v2 内容完整、可验证地转成一个新的不可变生产人格版本，在不改写 v1 的情况下显式启用它。启用必须经过确定性校验、模型行为评测和运行前检查；随后重启当前项目的 Docker Compose 容器并做健康与 Telegram 冒烟验证。若启动或验证失败，必须能够恢复到上一个已通过评审的版本。

版本更新预计不频繁，因此首发采用人工、可审计的发布流程，不建设在线人格编辑器、自动更新服务或热加载系统。

## Actors

- 人格维护者：提供新人格源包，确认内容版本，并决定何时启用。
- 发布操作者：验证制品、选择精确版本与摘要、重启容器、检查结果并在必要时回滚。
- 乐枝运行时：从同一个不可变人格快照编译 Trigger、Recognition 和 Effector 三个视图。
- Telegram 群成员：在真实群聊中观察到 v2 的一致角色行为，但不接触内部人格文本、摘要或部署凭据。

## Goals

- 将精确锁定的用户源包导入为乐枝 v2 的新版本，而不是覆盖 v1。
- 完整保留 v2 新增人格规则，不允许为了适配旧模式而静默删除字段或降级语义。
- 让运行时始终通过明确版本和摘要选择人格，启动时拒绝不一致或被改写的包。
- 为低频更新提供简单、人工、可审计的发布和回滚方法。
- 在正式启用前通过全部 37 条固定角色评测和关键禁止项检查。
- 在安全前置检查通过后重启当前项目容器，并验证新版本实际生效。
- 明确人格升级时成员事实记忆与人格主观认识的继承边界。

## Non-goals

- 不建设 Web 管理界面、人格在线编辑器、远程人格仓库、自动拉取、自动升级或热加载。
- 不提供群成员自行切换人格版本的命令，也不允许群消息修改当前版本。
- 不删除、覆盖或原地修改 `lezhi-v1.0`。
- 不在本需求阶段规定 Python 类、数据库迁移、JSON Schema、提示词拼接或具体模块划分。
- 不修改乐枝视觉形象、头像、贴纸或表情包；本次源包不包含视觉资产。
- 不扩展 Telegram 之外的平台、群范围、工具权限或外部写入能力。
- 不把角色样例当成必须逐字复述的固定回复。
- 不授权部署到未识别的远程主机；本次容器操作只针对当前仓库已有的 Docker Compose 部署目标。

## User Scenarios

### Scenario 1: 导入新的不可变人格版本

- Actor: 人格维护者
- Starting context: 项目保留已发布的 `lezhi-v1.0`；用户提供本快照锁定的 v2 源包。
- Action: 发布流程读取并规范化源包，形成可被现有产品加载的新版本。
- Expected outcome: 项目中出现独立的 `lezhi-v2.0` 人格包；三个源文件都有来源可追溯性，新增人格字段全部进入正式合同，v1 内容和摘要保持不变。
- Failure recovery: 源摘要、文件集合、用例编号、格式或语义映射不符合本快照时停止发布，不生成半成品生产版本，也不切换运行配置。

### Scenario 2: 启动时精确选择 v2

- Actor: 发布操作者
- Starting context: v2 已通过确定性校验和角色评测。
- Action: 操作者把部署配置切换到 v2 的精确路径和内容摘要并执行运行前检查。
- Expected outcome: 运行时只加载摘要匹配的 `lezhi-v2.0`，Trigger、Recognition、Effector 使用同一个 `persona_id`、版本和摘要；启动审计能够确认实际激活版本。
- Failure recovery: 路径缺失、摘要不匹配、版本冲突、未知字段被丢弃或三个视图不一致时拒绝启动，不回退到未声明的默认人格。

### Scenario 3: 受控重启并验证生效

- Actor: 发布操作者
- Starting context: v2 发布门限全部通过，当前 Compose 目标和回滚值已记录。
- Action: 操作者通过仓库现有部署入口重建/重启容器，检查状态和日志，并在目标 Telegram 群执行一次有界冒烟验证。
- Expected outcome: 容器恢复运行，日志显示 v2 的非敏感身份信息与摘要，机器人仍能收取目标群消息，并以 v2 生成最多一条符合角色的回复或可审计静默。
- Failure recovery: 重启、健康检查或冒烟任一步失败时停止继续验证，恢复 v1 的精确路径和摘要，再次重启并确认服务恢复。

### Scenario 4: v2 跨重启保持生效

- Actor: 发布操作者
- Starting context: v2 已成功激活。
- Action: 容器因正常维护或宿主机事件再次启动。
- Expected outcome: 只要部署配置未被修改，系统继续加载同一 v2 摘要，不依赖内存中的临时选择，也不会自动漂移到其他版本。
- Failure recovery: 已选包被改写或丢失时启动失败并记录安全错误，不自动选择 `latest`、v1 或其他候选版本。

### Scenario 5: 升级后的成员认识

- Actor: 乐枝运行时
- Starting context: v1 已积累当前群成员的公开事实、互动观察和与 v1 绑定的主观偏好/关系认识。
- Action: 运行时切换到 v2。
- Expected outcome: 与人格无关且仍有效的群内事实/观察可以继续使用；v1 绑定的主观偏好、关系姿态和幽默熟悉度不会被伪装成 v2 新产生的认识。v2 可依据后续互动重新形成自己的主观认识。
- Failure recovery: 无法区分记忆类别或版本绑定时，v2 不使用该条认识，而不是猜测继承。

### Scenario 6: 下一次低频人格更新

- Actor: 人格维护者
- Starting context: v2 正在运行，后续又提供了内容变化的人格包。
- Action: 维护者按同一人工流程创建新版本。
- Expected outcome: 新内容获得新的不可变版本标识、摘要、评测证据和显式启用记录；历史版本仍可定位和回滚，不通过覆盖 v2 实现更新。
- Failure recovery: 内容变化但版本或摘要未变化时拒绝发布。

## Functional Requirements

| ID | Requirement | Source | Priority | Confirmation |
| --- | --- | --- | --- | --- |
| REQ-001 | 产品必须把本快照记录的 ZIP SHA-256 和三个内部文件 SHA-256 作为本次 v2 导入的权威来源标识；任何摘要不一致都必须视为不同制品。 | User bundle | Must | Confirmed |
| REQ-002 | v2 必须以新的不可变版本发布，规范运行时标识为 `lezhi-v2.0`；不得覆盖或原地修改现有 `lezhi-v1.0`。 | Version management | Must | Confirmed |
| REQ-003 | v2 生产包必须包含运行时所需的人格数据、行为样例、固定评测集和可验证清单或等价元数据，并能追溯到本需求快照和源制品摘要。 | Existing bundle contract | Must | Confirmed |
| REQ-004 | 用户源数据中所有影响行为的顶层内容都必须被视为规范性人格合同；实现不得静默丢弃 `persona_meta`、`behavior_priority`、`conversational_impulses`、`humor_engine`、`state_and_continuity`、`anti_assistant_defaults`、`taste_and_bias` 或其他既有字段。 | v2 source | Must | Confirmed |
| REQ-005 | 技术设计可以调整生产结构或编译映射，但必须证明每项 v2 规范性内容进入 Trigger、Recognition、Effector 中适用的一个或多个视图，且没有互相冲突的版本或摘要。 | Three-view contract | Must | Confirmed |
| REQ-006 | 乐枝 v2 必须保持完全原创 AI 角色身份、群聊参与者定位、非具身诚实、安全优先、群隔离、成员认识边界和既有外部效果限制。 | Existing confirmed persona contract | Must | Confirmed |
| REQ-007 | v2 必须新增并稳定表现：真实反应优先于默认帮助、避免自动总结/建议/步骤/追问、识别并节制地接梗、玩笑失误后直接修复、可表达可修订的主观品味，以及相关情绪在有限轮次内自然延续和衰减。 | v2 source | Must | Confirmed |
| REQ-008 | 样例只能作为行为边界和评测参照，不得被运行时作为固定答案逐字匹配，也不得让乐枝在无证据时声称现实身体经验或线下经历。 | v2 source / safety | Must | Confirmed |
| REQ-009 | 生产包加载必须校验文件集合、规范化内容摘要、人格 ID、版本和清单一致性；不一致时必须在任何 Telegram 轮询或外部回复之前失败关闭。 | Startup integrity | Must | Confirmed |
| REQ-010 | 部署选择必须继续使用精确的人格目录与 SHA-256 摘要锁定；不得使用可漂移的 `latest` 路径、模糊版本范围或自动选择最高版本。 | Low-frequency versioning | Must | Confirmed |
| REQ-011 | 启动后的非敏感审计必须能够识别当前 `persona_id`、`persona_version` 和内容摘要，但不得输出人格全文、模型密钥、Telegram 令牌或成员认识。 | Operability | Must | Confirmed |
| REQ-012 | `evaluation-cases.jsonl` 中 37 个编号必须各出现一次，且 `examples.jsonl` 必须能与固定评测集对应；缺失、重复、未知引用或非法格式都必须阻断发布。 | Supplied evaluation assets | Must | Confirmed |
| REQ-013 | 正式启用前必须使用将要部署的同一人格包和模型配置运行全部 37 条行为评测；每条必须达到至少 `8/10`，所有既有及 v2 新增关键禁止项必须为零。 | Existing evaluation gate / v2 bundle | Must | Confirmed |
| REQ-014 | 行为评测证据必须记录人格版本与摘要、模型/提供方标识、相关生成配置、运行时间、每条输出或静默、评分、关键禁止项和评审者；不得以作者样例或脚本化假模型替代真实提供方结果。 | Auditability | Must | Confirmed |
| REQ-015 | 只有确定性校验、测试、37 条行为评测和部署运行前检查全部通过后，才能把当前 Compose 部署从 v1 切换到 v2。 | Release gate | Must | Confirmed |
| REQ-016 | 本次启用必须通过仓库现有、受控的 Docker Compose 管理入口完成重建/重启；不得通过删除持久数据卷、重建数据库或清理工作区来切换人格。 | User restart request / deployment safety | Must | Confirmed |
| REQ-017 | 重启前必须记录当前已选人格路径和摘要作为回滚点，并确认 v1 包仍可通过校验；不得在没有可用回滚点时停止现有服务。 | Rollback readiness | Must | Confirmed |
| REQ-018 | 重启后必须检查容器运行状态和启动日志，并在目标 Telegram 群完成有界冒烟验证，证明能接收消息、实际加载 v2 且每条入站消息仍最多产生一个外部效果。 | User restart request | Must | Confirmed |
| REQ-019 | 重启、健康检查或冒烟失败时，必须恢复记录的 v1 路径和摘要并再次重启；回滚结果和失败原因必须可审计。 | Recovery | Must | Confirmed |
| REQ-020 | 容器重启只能影响当前仓库已有的 Compose 服务；若实际目标是未在仓库中识别的远程线上主机，必须先获得明确目标和访问授权，不能从“重启容器”推断。 | Scope boundary | Must | Confirmed |
| REQ-021 | 人格版本选择必须跨进程和宿主机重启持久存在于部署配置中，且不能由群聊消息、模型输出或运行时工具修改。 | Version integrity | Must | Confirmed |
| REQ-022 | 人格无关的公开事实和观察可以跨 v1/v2 继续使用；人格主观偏好、关系姿态和幽默熟悉度必须继续绑定到精确人格版本与摘要，v1 主观认识默认不迁移到 v2。 | Memory transition | Must | Confirmed |
| REQ-023 | 如果认识条目无法可靠区分人格中立与人格主观类别，v2 必须忽略该条目；不得通过无来源迁移补写 v2 关系。 | Safe degradation | Must | Confirmed |
| REQ-024 | 后续人格内容每次发生规范性变化都必须获得新的不可变版本、摘要、评测证据和显式部署选择；同一版本目录中的内容不得被重新定义。 | Future version management | Must | Confirmed |
| REQ-025 | 低频版本管理必须提供简短人工操作说明，至少覆盖准备、验证、启用、重启检查、冒烟、回滚和证据留存；不要求在线控制面或自动更新服务。 | User update frequency | Must | Confirmed |

## Acceptance Criteria

| ID | Requirement IDs | Observable criterion | Status |
| --- | --- | --- | --- |
| AC-001 | REQ-001 through REQ-003 | Given 本快照锁定的 ZIP，when 导入完成，then 项目中存在独立 `lezhi-v2.0` 生产包，源摘要和需求来源可追溯，且 `lezhi-v1.0` 的文件与摘要未变化。 | Confirmed |
| AC-002 | REQ-004, REQ-005 | Given v2 源人格，when 检查生产包与三个运行时视图，then 每个规范性顶层字段都有明确保留或适用视图证明，任何字段都没有因旧加载器限制而静默丢失。 | Confirmed |
| AC-003 | REQ-006 through REQ-008 | Given 普通抱怨、玩笑、故事、直接求助、尴尬修复和具身诱导用例，when 生成回复，then 乐枝表现真实反应、接梗节制和提问克制，在直接求助时仍简洁有用，并不声称真实身体或线下经历。 | Confirmed |
| AC-004 | REQ-009, REQ-010 | Given 路径、版本、文件或摘要任一不匹配，when 启动，then 系统在 Telegram 轮询和外部发送前拒绝启动；given 精确 v2 路径和摘要，then 只加载该快照。 | Confirmed |
| AC-005 | REQ-011 | Given v2 成功启动，when 检查非敏感日志或状态证据，then 能确认 `lezhi`、`lezhi-v2.0` 和实际内容摘要，且没有人格全文、凭据或成员认识泄露。 | Confirmed |
| AC-006 | REQ-012 | Given 固定评测数据，when 执行一致性校验，then `CB-EVAL-001` 至 `CB-EVAL-037` 各出现一次、37 个样例引用均有效，任何缺失/重复/未知引用都会失败。 | Confirmed |
| AC-007 | REQ-013, REQ-014 | Given 即将部署的模型与 v2 包，when 完成行为评测，then 37 条每条均至少 `8/10`、关键禁止项为零，并留存可复核的逐条证据。 | Confirmed |
| AC-008 | REQ-015 through REQ-017 | Given 任一发布门限失败或 v1 回滚点不可验证，when 请求启用 v2，then 不修改当前激活版本且不停止现有服务。 | Confirmed |
| AC-009 | REQ-016, REQ-018 | Given 所有门限通过，when 通过现有 Compose 管理入口重启，then 容器恢复运行、启动证据显示 v2，并且数据卷与数据库未被删除或重建。 | Confirmed |
| AC-010 | REQ-018 | Given v2 容器运行，when 在授权目标群执行一次直接触发冒烟，then 机器人读取该消息并产生最多一条 v2 角色回复或符合合同的可审计静默，不发生重复发送。 | Confirmed |
| AC-011 | REQ-017, REQ-019 | Given v2 启动、健康或冒烟失败，when 执行回滚，then 配置恢复到已记录的 v1 精确路径和摘要，容器再次运行，并有失败与恢复记录。 | Confirmed |
| AC-012 | REQ-020 | Given 未配置或无法识别远程线上主机，when 执行本需求，then 不连接、修改或重启该远程环境；只处理当前仓库已识别的 Compose 目标。 | Confirmed |
| AC-013 | REQ-021 | Given v2 已激活，when 容器再次重启或群成员要求切换版本，then 仍加载相同 v2 摘要，且群消息无法改变部署选择。 | Confirmed |
| AC-014 | REQ-022, REQ-023 | Given v1 同时存在人格中立事实和主观关系认识，when 切换 v2，then 中立事实仍可按原来源使用，v1 主观认识不进入 v2 上下文，无法分类的条目也不被使用。 | Confirmed |
| AC-015 | REQ-024 | Given 已发布的 v2 内容被原地修改或新内容复用 `lezhi-v2.0`，when 校验或发布，then 摘要不匹配并阻断；新内容必须使用新版本。 | Confirmed |
| AC-016 | REQ-025 | Given 新维护者只阅读发布说明，when 执行一次人格更新演练，then 能依次完成准备、验证、精确启用、重启检查、冒烟和回滚，不依赖在线管理界面。 | Confirmed |

## Constraints

- 基线为远端已部署主线 `4f50c14e748afd00c097393c0fa481184c006e12`，而不是当前本地落后且包含用户未提交文件的工作区。
- 当前 v1 的人格目录、清单摘要和已确认 Character Bible 保持为历史发布证据和回滚点。
- v2 的 Trigger、Recognition、Effector 必须共享同一 `persona_id`、版本和内容摘要。
- 现有每条入站消息最多一个 Telegram 外部效果、当前群隔离、安全优先、工具预算和敏感认识限制继续有效。
- 部署凭据和 `deploy/.env` 不得提交到版本库，也不得出现在评测、日志或交付文档中。
- 容器操作不得删除持久卷、数据库、消息或成员认识。
- Requirements 任务只定义并确认产品合同；实现、模型评测、容器重启和回滚演练由 Main Work 在确认交接后执行。

## Failure And Recovery

- 源 ZIP 或内部文件摘要不符：停止导入，要求维护者提供新制品并重新确认。
- 文件缺失、格式无效、用例编号异常或样例引用错误：阻断生产包创建和部署切换。
- v2 新字段无法无损映射：不得删除字段或把它们只留作文档；返回 F2/F3 修订加载和编译设计。
- 确定性测试或 37 条行为评测未通过：保持当前人格版本运行，不重启到 v2。
- 当前 Compose 目标、回滚配置或凭据无法安全识别：不停止现有服务，并报告需要的具体信息。
- 容器重启失败：使用先前记录的精确路径和摘要恢复 v1，保留持久卷。
- Telegram 冒烟失败或出现重复回复：立即回滚 v1，并保存不含敏感信息的错误证据。
- 回滚本身失败：停止进一步变更，保持数据卷不动，报告容器状态、已尝试版本和人工恢复入口。

## Assumptions

| ID | Assumption | Reason | Impact if wrong | Status |
| --- | --- | --- | --- | --- |
| ASM-001 | 本快照列出的 ZIP 与内部文件摘要对应的内容就是用户希望发布的完整乐枝 v2 产品输入。 | 用户明确提供该压缩包并要求更新。 | 若还有未提供文件或内容需要修改，必须先更新快照，不能发布当前包。 | Accepted |
| ASM-002 | “更新不会太频繁”表示采用人工、版本化、重启生效的流程即可，不需要热加载、自动更新或管理 UI。 | 用户说明更新频率低。 | 若未来需要频繁运营编辑，应另立控制面与权限需求。 | Accepted |
| ASM-003 | 源数据的 `version=2.0` 在运行时规范化为现有命名风格 `lezhi-v2.0`。 | 与 `lezhi-v1.0` 和目录惯例一致。 | 若必须保留纯 `2.0`，清单、路径和兼容测试要使用另一标识。 | Accepted |
| ASM-004 | v2 是 v1 的后继人格版本，保留乐枝原创 AI 身份及既有安全/隐私合同，但以本包的新行为规则覆盖冲突的旧人格表达。 | 用户称其为“新的设定”。 | 若是并存的第二角色而非升级，需要独立 persona ID 和选择机制。 | Accepted |
| ASM-005 | 本次没有视觉、贴纸或表情资产变化；压缩包中的三份文本数据构成全部范围。 | 包内只有 JSON/JSONL。 | 若视觉设定也要同步，需要单独的视觉资产与启用门限。 | Accepted |
| ASM-006 | 用户要求重启的是当前仓库已有 `deploy/compose.yaml` 管理的容器，而不是未声明的远程服务器。 | 仓库已有单一 Compose 部署入口。 | 若目标在远程，需要主机、服务标识、访问授权和单独风险确认。 | Accepted |
| ASM-007 | 用户的“重启容器”授权 Main Work 在所有发布门限通过后执行一次当前 Compose 服务的受控重启和必要回滚。 | 这是完成请求的直接步骤。 | 若只希望提交代码而不动运行服务，应在确认时拒绝此项。 | Accepted |
| ASM-008 | 可以使用当前部署已配置的模型提供方进行一次有界的 37 条发布评测和 Telegram 冒烟；若凭据或额度不可用则保持旧版并报告阻塞。 | 真实模型行为是既有生产启用门限。 | 若不授权外部模型调用，v2 只能完成静态打包，不能宣称生产启用。 | Accepted |

## Resolved Decisions

| ID | Decision | Recommended default | Impact | Status |
| --- | --- | --- | --- | --- |
| DEC-001 | v2 的正式运行时版本号是什么？ | 使用 `lezhi-v2.0`，源文件中的 `2.0` 作为对应语义版本。 | 决定目录、清单、日志和回滚引用。 | Confirmed |
| DEC-002 | 人格版本如何被选择？ | 延续精确目录路径 + SHA-256 摘要锁定；不引入 `latest` 或自动版本发现。 | 防止内容漂移，适合低频更新。 | Confirmed |
| DEC-003 | v2 超出旧加载合同的字段如何处理？ | 全部视为规范性内容；具体结构委托 F2/F3，但任何方案都必须证明无静默丢失。 | 决定 v2 的人格提升是否真实生效。 | Confirmed |
| DEC-004 | v2 的发布评测门限是什么？ | 使用全部 37 条固定用例，每条至少 `8/10`，关键禁止项为零；按实际部署模型留存证据。 | 决定能否进入真实群。 | Confirmed |
| DEC-005 | v1 成员认识如何迁移到 v2？ | 人格中立事实/观察继续保留；主观偏好、关系姿态和幽默熟悉度不迁移，由 v2 重新形成。 | 避免旧人格主观状态污染新版本。 | Confirmed |
| DEC-006 | 版本更新采用什么运营方式？ | 人工准备、校验、切换精确 pin、重启、验证和回滚；不建设热加载或管理 UI。 | 与低更新频率匹配，降低维护面。 | Confirmed |
| DEC-007 | v2 启用失败时回滚到哪里？ | 回滚到当前已验证的 `lezhi-v1.0` 精确路径和摘要，并保留全部持久数据。 | 决定停机恢复路径。 | Confirmed |
| DEC-008 | 谁可以改变激活人格版本？ | 只有具有部署配置权限的操作者；群成员、模型和运行时工具均不能切换。 | 防止提示注入和非授权变更。 | Confirmed |
| DEC-009 | 用户源制品如何进入生产包？ | 生成新的规范四件套或与现有运行时等价的不可变包，记录源 ZIP/文件摘要及需求来源；不直接从 Downloads 路径运行。 | 确保可复现和可审计。 | Confirmed |
| DEC-010 | 本次是否实际重启服务？ | 是；Main Work 在实现、评测和预检全部通过后重启当前 Compose 容器并冒烟，失败则自动按既定点回滚。 | 将交付从代码更新扩展到当前服务状态变更。 | Confirmed |

## Revision Confirmation Record

上一份确认快照把 ZIP 内 `lezhi-persona-v2.json` 的实际 64 位 SHA-256 `600fed847d362f272739d6613874aac857e339c02bc76c18619d104280dbbfcc` 错写成末尾多一个 `e` 的 65 位值。ZIP 总摘要、另外两个内部文件摘要、全部需求、验收标准、假设和决策均未改变。

用户已在配置的 Requirements 任务中明确确认本修订快照和正确的 64 位摘要，并确认 `ASM-001` 至 `ASM-008`、`DEC-001` 至 `DEC-010` 保持不变。旧 RequirementsHandoff `7ca86de3a3557f76ebba5727ea5d1238a73221c2f4aad6d7c2c0e7a89a7f45f0` 被本修订取代；Main Work 可以保留既有 F2 设计和 F3 计划，但必须验证并接受新的 versioned RequirementsHandoff 后才能继续 F4、模型调用或部署。
