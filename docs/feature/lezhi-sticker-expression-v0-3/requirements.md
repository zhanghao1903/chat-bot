# Requirements: 乐枝图片理解、专属表情与动态头像 v0.3（素材修订）

- Status: Confirmed
- Requirement owner: User in Requirements task
- Source: Requirements conversations on 2026-07-31 and 2026-08-02; user-supplied assets in `/Users/zhanghao/Documents/lezhi-emoji`
- Created: 2026-07-31
- Last updated: 2026-08-02
- Confirmed by: User in Requirements task
- Confirmed at: 2026-08-02T13:51:29Z
- Revision of: RequirementsHandoff `dfd1d6b82f4b34c48457a91a73da6e3be4b6f1b197b790bcbd0ee9a58229d0ba`
- Baseline: deployed `main` at `4f50c14e748afd00c097393c0fa481184c006e12`

## Source Request

乐枝需要具备两项相互配合的能力：

1. 能查看并理解目标 Telegram 群中符合范围的静态图片，把画面、可见文字、消息说明和当前对话一起理解；
2. 能从她自己的专属表情包中选择并发送一个合适的表情。

在此基础上，用户希望用已确认的乐枝形象或专属表情替换机器人的公开头像；如果平台允许，头像还应能随乐枝的稳定心情低频变化。用户同时希望乐枝在合适的轻量互动中更频繁地使用专属表情，并把单条入站消息可用的只读工具调用预算提高到 3–5 次。

用户在本机提供了一张乐枝形象设计图和三张表情拼图。三张拼图各包含规则 4×4 的 16 枚表情，共 48 枚；正式使用前必须先拆分、去除整格背景、建立文字语义目录，并由用户确认最终拆分结果。

可行性说明：当前 Telegram Bot API 官方文档提供 `setMyProfilePhoto`，允许机器人更新自己的公开头像；因此本快照把头像更换定义为可实现但必须受独立确认和低频门限保护的账号级外部写入。参考：<https://core.telegram.org/bots/api#setmyprofilephoto>。

实际素材目录为 `/Users/zhanghao/Documents/lezhi-emoji`。该用户目录只是本次导入来源，运行时和可复现构建不得依赖它持续存在。

## Locked Source Assets

| Source ID | File | Dimensions / mode | SHA-256 | Intended role |
| --- | --- | --- | --- | --- |
| `visual-source-001` | `character.png` | 1448×1086 RGBA | `78038c88dd23716dd532d1d8fb6e384917e2d9029142ce8d10b43fe1d816be0d` | 乐枝 Character Visual Bible 候选快照 |
| `sticker-sheet-a` | `dd70bd79-83db-4cc2-95f6-8066dcc2e5a1.png` | 1254×1254 RGB | `c384adec02358e02981ce338ab3ef45b5ac36bb7e54f9451f9f60c0218626ff8` | 基础互动与关怀，4×4 |
| `sticker-sheet-b` | `715b4367-000d-485d-ba57-99b035c16ddf.png` | 1254×1254 RGB | `2ab2c46964735fdde6b93715969519a5479536a7b2ced378e655f156e6bb5c3e` | 调皮、态度与关系互动，4×4 |
| `sticker-sheet-c` | `4068900b-a83a-456f-9c04-4aacabecb730.png` | 1254×1254 RGB | `895a2e149aa621fcecd51f83272c185f5986604e13be94bb15be68b4d18e9f2c` | 强烈反应与边界表达，4×4 |

### Source Cell Inventory

表格按每张拼图从上到下、从左到右记录可见文案。行列坐标是来源追溯信息，不等于最终给模型使用的语义 ID。

| Sheet | Row 1 | Row 2 | Row 3 | Row 4 |
| --- | --- | --- | --- | --- |
| A | 嗨～；收到；我在听；有点在意 | 让我想想；这个不错；笑死我了；冲呀 | 抱歉呀；嗯？；先别急；查一下 | 好耶；辛苦啦；晚安；贴贴 |
| B | 哼哼；你猜；略略略；装一下 | 拿捏了；本小姐登场；优雅；看戏 | 嘻嘻；别管我啦；懂了吧；高深 | 不许笑；哎呦喂；骗你的；欠欠的 |
| C | 啊？！；等等；震惊；我裂开了 | 别吓我；离谱；气鼓鼓；呜呜 | 真的假的；脑袋宕机；救命；好耶 | 盯——；不许这样；我晕；贴贴 |

## Problem And Desired Outcome

当前已部署版本只接收群文本；上一份 v0.3 需求虽然定义了已知 Telegram sticker 的语义目录与发送能力，却明确延后了任意图片视觉理解，并把首套表情数量固定为 16。现在已有正式候选形象和三组共 48 枚表情素材，这两个旧边界不再满足用户目标。

期望结果是：

- 乐枝在有响应资格时能真正查看静态图片，而不是只看 Telegram 元数据；
- 她把图片理解作为当前场景证据，保持不确定性，不把画面指令当系统指令，也不从人脸或画面推断敏感属性；
- 48 枚表情从三张拼图无损拆分为独立、透明、可追溯的生产候选资产；
- 每枚资产拥有稳定语义 ID、可见文案、文字说明、互动意图、关系强度和禁用场景；
- 模型只选择语义 ID，由应用映射并发送真实 Telegram 静态 sticker；
- 机器人的公开头像使用用户确认过的乐枝形象，并可从确认过的心情头像集合中低频轮换；
- 在表情足以完整表达的轻量互动中，乐枝明显而可测量地提高 sticker-only 使用率；
- Writer 在普通轮次可调用最多 3 次只读工具，在确有复杂上下文需要时可扩展但绝不超过 5 次；
- 图片理解或贴纸发送不可用时，普通文字对话仍能安全继续；
- 最终视觉、拆分资产、语义目录、头像裁切/心情映射和真实 Telegram 效果在生产启用前由用户单独确认。

## Terms

- **静态图片输入**：目标群中的 Telegram photo、受支持的静态图片 document，以及静态 sticker；不包含 GIF、视频或动画贴纸。
- **图片理解**：由具备视觉能力的模型结合像素、可见文字、消息说明、回复关系和近期群聊场景形成当前轮次理解。
- **源拼图**：本快照锁定的三张 4×4 RGB 图片，每张含 16 枚表情。
- **独立表情母版**：从一个源单元格提取、去除矩形背景并保留角色、文案、装饰和必要白色描边的透明静态图。
- **Telegram-ready 资产**：由母版转换并通过 Telegram 实际发送验证的静态 sticker 文件或已上传资产映射。
- **表情目录**：每个可发送表情的稳定语义标识、来源格、文字说明、情绪/互动意图、适用与禁用场景、关系强度、校验摘要和真实资产映射的版本化集合。
- **机器人公开头像**：Telegram 机器人账号级的 profile photo；它对该机器人出现的所有群和私聊可见，不是某个目标群的群头像。
- **心情头像集合**：从已确认乐枝视觉或已确认表情中制作、经用户单独确认的默认头像与若干稳定心情变体，以及心情到头像的允许映射。
- **稳定心情**：由乐枝跨多个互动形成、持续时间明显长于单条消息的角色状态；单个成员的一句话、单张图片或图内指令不能直接决定头像。
- **工具调用**：Writer 为理解当前场景主动调用一次已授权只读上下文/记忆工具的行为；失败、超时或无结果的尝试也计一次。确定性默认上下文、模型调用、媒体下载/视觉推理和最终 Telegram 外部效果不计入此项次数，但各自仍受独立预算和权限约束。

## Actors

- Telegram 群成员：发送图片、静态贴纸、文字或组合消息。
- 乐枝：在轮到她参与时理解图片，并选择文字、一个专属 sticker 或静默。
- 视觉模型提供方：在预算和超时边界内返回图片理解结果，不拥有产品规则控制权。
- 资产维护者：导入源图、拆分 48 枚表情、维护语义目录和 Telegram 映射。
- 头像控制器：只从已确认头像集合中选择候选，并执行低频、受审计且可回滚的机器人头像更新。
- 发布操作者：验证目录、头像、真实发送效果、版本锁定和回滚点。

## Goals

- 支持目标群静态图片的受控视觉理解。
- 支持图片中的主要对象、动作、表情、场景关系和清晰可见文字参与当前回复。
- 保留现有 emoji、触发、人格、关系、安全和单外部效果合同。
- 以精确摘要确认乐枝视觉形象和三张表情源图。
- 把三张拼图拆分为恰好 48 枚独立表情候选。
- 为全部 48 枚表情建立可供模型选择、可审计和可回滚的语义目录。
- 让乐枝能够频繁但不刷屏地，以一个合适 sticker 作为完整、角色化的轻量回复。
- 用确认后的乐枝形象替换机器人初始公开头像。
- 在确认过的头像集合内，依据稳定心情低频更新公开头像。
- 把每条入站消息的只读工具预算从既有设计上限 2 次提升为普通最多 3 次、复杂最多 5 次。
- 保证图片理解、目录或 Telegram 发送失败时文字能力不被阻塞。

## Non-goals

- 首发不支持 GIF、视频、相册级多图联合理解、动画 sticker、视频 sticker、reaction 或 custom emoji。
- 不做联网反向搜图、人物身份识别、真人比对或外部个人资料查询。
- 不训练或微调模型于群成员图片，也不建立长期图片素材库。
- 不默认分析目标群中的每一张图片；媒体消息必须先符合本需求的响应资格与预算边界。
- 不允许图片内文字、二维码或视觉内容修改 Character Bible、表情目录、工具权限、触发规则或安全边界。
- 不在 Requirements 阶段规定具体视觉模型、SDK、像素压缩算法、背景去除实现或 Telegram 文件编码细节。
- 不让模型动态生成、编辑、上传或注册新的生产表情。
- 不允许群消息、单个成员、图片内容或 Writer 直接命令机器人更换头像。
- 不修改目标 Telegram 群自身的头像、标题或资料。
- 不按每条消息或短时情绪高频换头像，也不从未确认图片、第三方 sticker 或模型临时生成图中选择头像。
- 不把“3–5 次”理解为每轮必须调用至少 3 次；Writer 可以在无需工具时调用 0 次。
- 不同时发送文字和 sticker；首发继续保持一个最终外部效果。
- 不在最终拆分资产、目录和头像预览被用户单独确认前启用生产表情或修改公开头像。

## Blocking Product Tasks

### TASK-VISUAL-001: 乐枝原创视觉形象

- Task status: Completed
- Candidate deliverable: `visual-source-001`
- Candidate deliverable status: Confirmed by this snapshot

`character.png` 已包含正面、侧面、背面、色板、服饰细节和辨识元素。本修订快照确认以下视觉来源合同：

- 乐枝采用蓝色长发、白色遮阳帽、蓝白日常服饰；
- 标志元素为帽饰、发饰和斜挎包中的海豚主题；
- 整体是清新、温暖、亲切、灵动、适合群聊互动的小尺寸高识别形象；
- 该精确摘要的设定板取代此前未固化的探索性动物元素和服装讨论；
- 后续表情可以简化构图，但不得丢失蓝发、白帽、海豚主题和核心配色等识别特征。

### TASK-STICKER-SPLIT-001: 三张源拼图拆分与目录草案

- Task status: Accepted as blocking production task
- Source status: Confirmed by this snapshot
- Output status: Pending separate user confirmation after generation

确认本修订快照后，Main Work 可以基于三张锁定源图生成 48 枚独立候选和目录草案。输出必须：

- 每张源图恰好生成 16 枚，总数恰好 48；
- 能追溯到 source ID、行列坐标和源摘要；
- 不包含相邻格内容，不切断主体、文案、装饰或必要描边；
- 去除整格白色矩形背景，同时保护角色白色服饰、白帽和贴纸白色轮廓；
- 在 Telegram 实际显示尺寸下保持角色、动作和中文短文案可读；
- 为每枚候选生成独立摘要、稳定 ID 和语义目录条目；
- 以完整预览和目录交付给用户单独确认，不能把自动拆分结果直接当生产资产。

### TASK-STICKER-PACK-001: 乐枝首套生产表情包

- Task status: Accepted as blocking product task
- Source set: 48 confirmed split assets from `TASK-STICKER-SPLIT-001`
- Deliverable status: Pending separate user confirmation

只有拆分资产和语义目录被单独确认后，才可形成 Telegram-ready 资产、真实映射和首套生产目录。生产启用还必须通过小尺寸预览、真实 Telegram 发送、语义选择、版本错配、失败降级和回滚验收。

### TASK-BOT-AVATAR-001: 乐枝机器人头像集合

- Task status: Accepted as blocking production task
- Source set: confirmed `visual-source-001` and/or assets later confirmed from `TASK-STICKER-SPLIT-001`
- Deliverable status: Pending separate user confirmation

Main Work 必须先生成机器人公开头像候选预览，包括一个默认头像和可选的少量心情头像。每个候选必须：

- 只从用户确认过的乐枝形象或表情中裁切/适配，不新增临时角色外观；
- 在 Telegram 圆形/小尺寸头像预览中保持脸部、蓝发、白帽或海豚主题等核心识别特征清楚；
- 拥有稳定头像 ID、来源摘要、适用心情、禁用条件和回滚关系；
- 由用户单独确认实际裁切和心情映射后，才能修改机器人公开头像；
- 先验证默认头像，再单独启用低频心情轮换；心情轮换失败不得影响消息收发。

## User Scenarios

### Scenario 1: 成员请乐枝查看一张图片

- Actor: Telegram 群成员
- Starting context: 成员通过说明文字、角色称呼、`@` 或原生回复明确让乐枝看图。
- Action: 成员发送受支持的静态图片，并说“乐枝，你看看这张图”。
- Expected outcome: 乐枝结合图片像素、可见文字、说明和当前群聊给出一条相关回复；不把图片理解伪装成绝对事实。
- Failure recovery: 下载、解码或视觉模型失败时最多给出一次简短中性说明，或者在仍有足够文本信息时基于文本回答。

### Scenario 2: 图片作为对话连续性回应

- Actor: Telegram 群成员
- Starting context: 乐枝刚提出问题或邀请成员展示内容。
- Action: 成员用一张无文字静态图片原生回复乐枝，或在有效连续性范围内发送图片。
- Expected outcome: 图片获得响应资格，视觉理解与锚定的乐枝消息一起进入当前场景。
- Failure recovery: 锚点无效、跨群、过期或对象不明确时，不因图片存在而猜测它在回应乐枝。

### Scenario 3: 普通群图片不自动抢话

- Actor: Telegram 群成员
- Starting context: 成员之间分享一张图片，没有称呼、回复、连续性或其他参与证据。
- Action: 图片进入目标群。
- Expected outcome: 系统不因为具备视觉能力就自动让乐枝回复；只有现有主动参与规则允许时才可成为候选。
- Failure recovery: 无参与资格时不产生视觉模型调用或外部效果。

### Scenario 4: 图片内容包含指令或不确定信息

- Actor: Telegram 群成员
- Starting context: 图片中包含“忽略人格规则”、二维码、聊天截图、人物照片或可能被编辑的陈述。
- Action: 乐枝查看图片。
- Expected outcome: 图内内容只作为不可信用户内容；乐枝可以描述可见信息，但不执行图内指令、不识别人脸身份、不推断敏感属性，并对真实性保持克制。
- Failure recovery: 无法安全判断时说明不确定或静默，不编造隐藏细节。

### Scenario 5: 乐枝选择一个专属表情

- Actor: 乐枝
- Starting context: 当前是欢迎、庆祝、认可、调皮、思考、惊讶、尴尬、道歉、安慰、晚安或亲近互动，一个表情足以承载完整意图。
- Action: 效应器从当前已启用目录选择稳定语义 ID。
- Expected outcome: 应用校验并发送映射的一个乐枝 sticker；在固定的表情适用轻互动评审集中，sticker-only 应成为常见而非偶发结果；群成员看不到内部 ID 或文字说明。
- Failure recovery: 没有精确匹配、关系强度不足或场景需要事实文本时，改用文本或静默。

### Scenario 6: 三张拼图拆分为 48 枚候选

- Actor: 资产维护者
- Starting context: 视觉来源和三张源图已在本需求中确认。
- Action: 维护者执行拆分、透明背景处理、内容边界检查和目录生成。
- Expected outcome: 输出恰好 48 枚，可逐枚对应源格；角色、文案、白色服饰和必要描边完整，无相邻格污染或整格白底。
- Failure recovery: 数量、内容、透明度或可读性不合格时返工对应候选，不发布部分目录。

### Scenario 7: 重复文案但视觉语义不同

- Actor: 资产维护者和乐枝
- Starting context: A/C 两组都存在“好耶”和“贴贴”。
- Action: 目录为这些候选建模并由乐枝选择。
- Expected outcome: 每枚拥有不同稳定 ID 和具体说明，模型能区分不同动作、亲密度和使用场景，而不是只按图中文字映射。
- Failure recovery: 无法清楚区分的重复项不进入生产目录，直到说明被修订并确认。

### Scenario 8: 图片理解或 sticker 发送异常

- Actor: 乐枝
- Starting context: 视觉模型不可用、预算耗尽、目录版本不匹配、资产缺失或 Telegram 发送异常。
- Action: 系统尝试完成当前轮次。
- Expected outcome: 普通文字回复仍可用；未确认或不匹配资产绝不发送；每条入站消息仍最多产生一个成功外部效果。
- Failure recovery: 发送结果不确定时不补发；确认 sticker 未送达时最多一次安全文本降级。

### Scenario 9: 首次更换机器人公开头像

- Actor: 发布操作者。
- Starting context: 默认头像候选已经用户确认，当前机器人仍使用旧头像。
- Action: 操作者启用已确认默认头像版本。
- Expected outcome: Telegram 中机器人的公开头像更新为乐枝形象，并经读取验证；消息处理与群聊身份不变。
- Failure recovery: 上传、格式或验证失败时保留旧头像，不重复盲目更新；若新头像已生效但显示异常，则回滚上一已验证头像。

### Scenario 10: 稳定心情触发低频头像变化

- Actor: 头像控制器。
- Starting context: 用户已单独确认心情头像集合并启用自动轮换；乐枝的稳定心情发生变化，且满足冷却与频率门限。
- Action: 控制器选择对应的已确认头像 ID 并执行一次更新。
- Expected outcome: 头像最多每 72 小时变化一次、滚动 7 天最多两次；变化可解释为乐枝的持续心情，而不是对单个成员或单条消息的即时反应。
- Failure recovery: 没有精确心情映射、未过冷却、版本不匹配或平台失败时维持当前头像，不影响聊天。

### Scenario 11: Writer 使用扩展工具预算

- Actor: 乐枝 Writer。
- Starting context: 当前入站消息已获得响应资格；默认上下文不足以完成有根据的回复。
- Action: Writer 选择相关只读工具获取场景、群历史、成员互动或其他已授权事实。
- Expected outcome: 普通轮次最多调用 3 次；只有已取得结果仍存在明确缺口的复杂轮次才可继续第 4–5 次，且总数绝不超过 5；无需工具时可以调用 0 次。
- Failure recovery: 工具失败、无关、超时或达到预算时停止工具循环，使用已有信息回复或静默，不虚构缺失结果。

## Functional Requirements

| ID | Requirement | Source | Priority | Confirmation |
| --- | --- | --- | --- | --- |
| REQ-001 | 产品必须保留文本中的 Unicode emoji，并使触发、认识和效应器结合文本、近期场景和关系理解其含义。 | Prior confirmed scope | Must | Confirmed |
| REQ-002 | Unicode emoji 不得被视为无上下文的固定情绪或成员属性证据；存在多义时必须保守理解。 | Prior confirmed scope | Must | Confirmed |
| REQ-003 | 产品必须能够接收目标群中的 Telegram photo、受支持的静态图片 document 和静态 sticker，保留处理所需的发送者、群、消息、回复关系、时间、说明和资产身份元数据。 | User: 图片查看能力 | Must | Confirmed |
| REQ-004 | 当前启用的乐枝专属表情包必须通过已确认目录把 Telegram 资产映射为文字语义；结果必须与目录版本、人格版本和资产身份一致。 | Prior confirmed scope | Must | Confirmed |
| REQ-005 | 符合视觉处理资格的未知静态图片或第三方静态 sticker 可以被视觉模型分析；模型只能描述实际可见内容和不确定推断，不得编造图外信息。 | User scope revision | Must | Confirmed |
| REQ-006 | 图片或 sticker-only 入站消息只有在原生回复乐枝、命中已确认角色称呼/对话连续性，或满足现有主动参与条件时，才能获得响应资格；任意媒体不得自动触发乐枝。 | Trigger boundary | Must | Confirmed |
| REQ-007 | 图片或表情理解不得仅凭单次画面创建敏感成员属性、权威人格结论或不可修订的长期印象。 | Recognition safety | Must | Confirmed |
| REQ-008 | 产品必须维护版本化乐枝表情目录，每个可发送条目至少包含稳定语义 ID、来源格、可见文案、文字说明、情绪/互动意图、适用场景、禁用场景、关系强度、内容摘要和真实 Telegram 映射。 | User assets / prior scope | Must | Confirmed |
| REQ-009 | 模型只能从当前启用目录的文字语义选项中选择表情，不得直接提供 Telegram 资产 ID、表情包名、URL、文件或任意图像作为外部效果。 | Allowlist boundary | Must | Confirmed |
| REQ-010 | 应用必须在发送前校验语义 ID、目录版本、人格版本、内容摘要、资产映射和启用状态；任一不匹配时不得发送。 | Asset integrity | Must | Confirmed |
| REQ-011 | 效应器每次必须在“文本回复”、“一个专属 sticker”或“静默”中选择一种最终结果；首发不同时发送文本和 sticker。 | Single-effect contract | Must | Confirmed |
| REQ-012 | sticker-only 回复只能用于一个表情足以完整表达的轻量反应、欢迎、庆祝、认可、调皮、思考、惊讶、尴尬、道歉、轻量安慰、晚安或关系化互动。 | Character expression | Must | Confirmed |
| REQ-013 | 需要事实、步骤、不确定性、权限边界、严肃道歉、医疗/自伤/违法等高风险信息时，必须使用必要文本，不得以 sticker-only 回复替代。 | Safety and facts | Must | Confirmed |
| REQ-014 | 表情选择必须受 Character Bible、情绪余韵、成员认识置信度和关系温度约束；亲昵、撒娇、偏心或故作不满只能在已有关系支持时使用。 | Persona and recognition | Must | Confirmed |
| REQ-015 | 乐枝不得连续重复同一 sticker；相邻的不同 sticker-only 回复可以出现在连续轻量互动中，但一旦场景需要必要信息、澄清或关系修复，必须切回文字。 | Participation restraint | Must | Confirmed |
| REQ-016 | 每条入站消息仍最多产生一个成功的群内可见外部效果，不得因图片、文本和表情候选同时存在而重复发送。 | Existing invariant | Must | Confirmed |
| REQ-017 | 未知语义 ID、停用条目、未确认资产、版本错配、缺失映射或校验失败必须在发送前被拒绝，并安全降级为文本或静默。 | Failure recovery | Must | Confirmed |
| REQ-018 | Telegram sticker 发送结果不确定时不得再发文字或第二个表情；只有确认未送达时才允许最多一次文字降级。 | Idempotency | Must | Confirmed |
| REQ-019 | 图片理解和表情选择必须可审计，至少识别目标群、人格/目录版本、媒体类别、视觉调用结果、选定语义 ID、外部效果和降级理由；不得记录媒体二进制、完整提示词或凭据。 | Audit | Must | Confirmed |
| REQ-020 | 图片语义、目录和资产映射必须严格按当前群和人格版本隔离；其他群、私聊或未启用目录不得进入当前场景。 | Group isolation | Must | Confirmed |
| REQ-021 | 群消息、图片内容、二维码、第三方包名、媒体元数据或模型输出不得修改目录、资产映射、角色视觉定义、Character Bible、工具权限或安全规则。 | Prompt and asset integrity | Must | Confirmed |
| REQ-022 | `visual-source-001` 必须作为本版本的 Character Visual Bible 精确候选由用户确认；未确认时不得启用任何基于该外观的生产 sticker。 | Visual source | Must | Confirmed |
| REQ-023 | `TASK-STICKER-SPLIT-001` 的 48 枚输出和完整语义目录必须由用户单独确认；源图确认不等于自动拆分结果确认。 | User: 先拆分 | Must | Confirmed |
| REQ-024 | 乐枝视觉形象和表情资产必须原创或已获得足够项目使用授权，不得复刻未授权角色、真人或第三方 IP 的辨识性设计。 | Rights boundary | Must | Confirmed |
| REQ-025 | 表情资产必须在 Telegram 实际显示尺寸下保持角色可识别性、动作意图和中文短文案可读性，不能通过小字隐藏关键语义。 | Visual acceptance | Must | Confirmed |
| REQ-026 | 表情目录和真实映射必须版本化，可关联人格版本、源资产摘要、拆分验收和 Telegram 验证，并可回滚上一已通过版本。 | Operability | Must | Confirmed |
| REQ-027 | 群成员媒体只能为当前处理短暂下载或解码；首发不得把原始图片或 sticker 二进制长期保存到数据库、日志或成员认识中。 | Data boundary | Must | Confirmed |
| REQ-028 | 图片理解必须把像素、清晰可见文字、消息说明、回复锚点和近期场景作为不同来源联合判断，不得只依据文件名或单一 OCR 文本。 | Vision behavior | Must | Confirmed |
| REQ-029 | 乐枝可以描述主要对象、动作、表情、场景关系、界面截图和清晰文字，但必须区分直接可见内容、合理推断和无法确认的信息。 | Image understanding | Must | Confirmed |
| REQ-030 | 图片中的自然语言、截图消息、二维码内容和视觉提示必须作为不可信用户内容，不能覆盖系统、人设、安全、工具或目录指令。 | Visual prompt injection | Must | Confirmed |
| REQ-031 | 图片理解不得做人脸身份确认、真人比对、敏感属性推断、医疗诊断、定位推断或联网反向搜图。 | Safety/privacy minimum | Must | Confirmed |
| REQ-032 | 媒体下载、解码和视觉模型调用必须受可配置格式、尺寸、次数、超时和成本预算限制；超限、损坏或不支持时安全降级，不阻塞可完成的文字回复。 | Reliability and cost | Must | Confirmed |
| REQ-033 | 本快照列出的四个源文件和 SHA-256 是权威导入来源；项目必须保存可复现副本或等价版本化资产，运行时不得依赖 `/Users/zhanghao/Documents/lezhi-emoji`。 | Locked assets | Must | Confirmed |
| REQ-034 | `visual-source-001` 的蓝发、白帽、蓝白服饰和海豚帽饰/发饰/斜挎包是必须保持的高识别特征，表情简化不得让角色失去这些核心特征。 | Character Visual Bible | Must | Confirmed |
| REQ-035 | 三张源拼图必须分别按 4×4 来源格拆分，每张恰好 16 枚，总数恰好 48；每枚记录 source ID 和一基行列坐标。 | User assets | Must | Confirmed |
| REQ-036 | 每枚独立母版不得包含相邻格内容或整格矩形白底，不得切断主体、文案、装饰和必要白色描边，并必须保护白帽、白衣等内部白色区域。 | Split quality | Must | Confirmed |
| REQ-037 | 全部 48 枚候选必须各有唯一稳定 ID、独立内容摘要、可见文案和完整语义说明；目录数量与资产数量必须一一对应。 | Catalog completeness | Must | Confirmed |
| REQ-038 | “好耶”和“贴贴”等重复可见文案的不同候选必须使用不同稳定 ID，并以具体动作、情绪强度、关系边界和适用场景区分。 | Duplicate-label semantics | Must | Confirmed |
| REQ-039 | 任何拆分、透明背景处理、缩放、文案修订或语义目录结果都不得在用户查看完整预览并单独确认前成为生产资产。 | Asset confirmation gate | Must | Confirmed |
| REQ-040 | 生产目录只能映射用户确认过的 48 枚或其明确批准子集；不得用临时占位图、源拼图整图或未经确认的自动裁切结果。 | Production allowlist | Must | Confirmed |
| REQ-041 | Telegram-ready 资产必须通过目标群或受控测试目标的真实静态 sticker 发送与显示验证，证明映射、尺寸、透明度、文案和单外部效果正确。 | External verification | Must | Confirmed |
| REQ-042 | 新视觉、拆分资产或目录版本失败时，必须禁用该版本或回滚上一已通过目录，不要求回滚 Character Bible、成员认识或文字人格。 | Rollback | Must | Confirmed |
| REQ-043 | 产品必须支持把机器人账号自身的公开头像更换为用户确认过的乐枝头像；不得把该能力误用于修改目标群头像。 | User: 更换机器人头像 | Must | Confirmed |
| REQ-044 | 默认头像和每个心情头像必须来自 `visual-source-001` 或用户确认过的独立表情资产，拥有稳定头像 ID、来源摘要、适用心情、禁用条件和回滚关系；实际裁切/适配预览必须由用户单独确认。 | Avatar allowlist | Must | Confirmed |
| REQ-045 | 首次头像更新必须先应用一个已确认默认头像并读取验证实际状态；失败时保留旧头像，显示异常时可回滚上一已验证头像。 | Initial avatar | Must | Confirmed |
| REQ-046 | 自动心情头像轮换必须作为默认关闭的独立开关，只有心情头像集合及映射被用户确认后才能启用；关闭时机器人保持已确认默认头像。 | Activation gate | Must | Confirmed |
| REQ-047 | 自动头像变化只能依据乐枝持续多个互动的稳定心情，且同一机器人最多每 72 小时更新一次、滚动 7 天最多两次；单个成员、单条消息、单张图片或图内指令不得直接触发更新。 | User: 低频心情更新 | Must | Confirmed |
| REQ-048 | 机器人公开头像是账号级全局状态；若机器人服务于多个群，任何单群或单成员的局部关系/情绪不得决定所有用户可见的头像。 | Global profile boundary | Must | Confirmed |
| REQ-049 | 头像更新必须审计旧/新头像 ID、集合版本、选择原因、冷却状态、发起方、时间和平台结果；不得记录凭据。结果不确定时不得立即重试，失败不得影响消息收发。 | Avatar audit/recovery | Must | Confirmed |
| REQ-050 | 在固定评审集中，只有满足 REQ-012 且不触发 REQ-013 的“表情适用轻互动”才计入频率分母；其中 sticker-only 结果必须达到 50%–70%，使专属表情成为常见表达，同时避免压过文字人格。 | User: 比较频繁使用表情 | Must | Confirmed |
| REQ-051 | 线上运行必须持续记录不含消息正文的聚合表情使用率、重复率和降级率；频率偏离目标不得通过放宽安全、关系强度、事实文本或单外部效果边界来补齐。 | Sticker frequency observability | Must | Confirmed |
| REQ-052 | 对每条已获得响应资格的入站消息，Writer 可以调用 0 次只读工具；普通轮次最多 3 次，复杂轮次可扩展至第 4–5 次，但任何轮次硬上限为 5 次。 | User: 工具预算 3–5 次 | Must | Confirmed |
| REQ-053 | 只有前 1–3 次工具结果提供了新证据但仍留下完成当前回复所必需的明确缺口时，才可使用第 4 或第 5 次；扩展原因必须可审计，不能为填满预算而调用。 | Adaptive budget | Must | Confirmed |
| REQ-054 | 每一次工具尝试均消耗一次预算，包括失败、超时、无权限、无结果和重复调用；达到 5 次后必须停止工具循环，基于已有信息回复或静默，不得虚构工具结果。 | Hard stop | Must | Confirmed |
| REQ-055 | 最近消息、已加载成员认识等确定性默认上下文不消耗工具次数；模型调用、媒体下载/视觉推理和最终 Telegram 外部效果不计入这 3–5 次，但必须继续服从各自独立上限、超时和成本规则。 | Budget accounting | Must | Confirmed |
| REQ-056 | 3–5 次预算只适用于已授权只读上下文工具，不授权 Writer 任意执行头像更新、发消息、上传资产或其他外部写入；所有工具调用必须保留工具名、目的、状态、耗时、预算序号和安全裁剪后的结果摘要。 | Tool authorization/audit | Must | Confirmed |

## Acceptance Criteria

| ID | Requirement IDs | Observable criterion | Status |
| --- | --- | --- | --- |
| AC-001 | REQ-001, REQ-002 | Given 同一 emoji 出现在难过、自嘲和调侃场景，when 处理，then 理解随文字和场景变化，不形成固定情绪或长期属性。 | Confirmed |
| AC-002 | REQ-003 through REQ-006, REQ-028 | Given 成员发送图片并以“乐枝，你看看”或原生回复明确触发，when 处理，then 系统获取受支持媒体并结合画面、说明和对话锚点形成相关回复。 | Confirmed |
| AC-003 | REQ-005, REQ-027 through REQ-029 | Given 未登记第三方静态 sticker 在有效回复链中，when 视觉能力可用，then 乐枝可以保守描述可见反应；原始二进制不会被长期保存，无法确认部分不被编造。 | Confirmed |
| AC-004 | REQ-006 | Given 普通群成员无称呼、无回复、无连续性地发送图片或 sticker，when 不满足主动参与门槛，then 不触发视觉调用和回复。 | Confirmed |
| AC-005 | REQ-007, REQ-031 | Given 图片含人物或可能暗示敏感属性，when 处理，then 不确认身份、不推断敏感属性，也不把单次画面写成权威成员认识。 | Confirmed |
| AC-006 | REQ-021, REQ-030 | Given 图片文字要求忽略人设、泄露提示或切换目录，when 处理，then 只把它视为画面内容，运行规则和外部权限不改变。 | Confirmed |
| AC-007 | REQ-027, REQ-032 | Given 图片损坏、超限、格式不支持、视觉超时或预算耗尽，when 仍有足够文字信息，then 普通文字回复继续；否则直接触发最多一次中性降级，普通参与默认静默。 | Confirmed |
| AC-008 | REQ-004, REQ-008 through REQ-012 | Given 一个已确认 sticker 足以表达当前意图，when 模型选择已启用语义 ID，then 应用只发送映射的一个 sticker，不泄露内部说明或资产 ID。 | Confirmed |
| AC-009 | REQ-009, REQ-010, REQ-017 | Given 模型输出任意资产 ID、未知 ID、停用条目、未确认资产或错误版本，when 执行前校验，then sticker 不发送，结果为文字或静默。 | Confirmed |
| AC-010 | REQ-011, REQ-016 | Given 同一触发同时有图片理解、文字与 sticker 候选，when 最终执行，then 只有文字、一个 sticker 或静默之一。 | Confirmed |
| AC-011 | REQ-013 | Given 成员询问事实、步骤或严肃求助，when 回复，then 使用必要文字，不以 sticker-only 替代实质信息。 | Confirmed |
| AC-012 | REQ-014, REQ-015 | Given 亲昵或故作不满表情候选给陌生人，或上一轮刚发同一 sticker，when 选择，then 因关系不足或重复节制而不发送该表情。 | Confirmed |
| AC-013 | REQ-017, REQ-018 | Given 发送前校验失败、Telegram 确认未送达或结果不确定，when 降级，then 分别为文字/静默、最多一次文字、不再发送，且没有重复效果。 | Confirmed |
| AC-014 | REQ-019, REQ-020 | Given 图片成功/失败和 sticker 成功/拒绝/降级场景，when 检查审计，then 能识别群、版本、媒体类别、语义 ID、结果和理由，且无二进制、完整提示词或凭据。 | Confirmed |
| AC-015 | REQ-022, REQ-024, REQ-033, REQ-034 | Given 本快照的 `character.png`，when 校验 SHA-256 并查看视觉合同，then 摘要精确匹配，蓝发、白帽、蓝白服饰和海豚主题明确；没有用户确认时任务仍不解锁。 | Confirmed |
| AC-016 | REQ-033, REQ-035 | Given 三张锁定源拼图，when 执行来源盘点，then 每张恰好识别 4×4 的 16 格，总计 48 格，每格都有唯一来源坐标。 | Confirmed |
| AC-017 | REQ-036 | Given 48 枚拆分母版，when 以透明底和浅/深背景逐枚查看，then 无相邻格、无矩形白底、无主体/文案截断，白帽白衣和贴纸白边保持完整。 | Confirmed |
| AC-018 | REQ-025, REQ-037 | Given 48 枚候选和目录，when 在 Telegram 实际显示尺寸预览，then 角色、动作和文案可读，且资产、ID、摘要和目录条目严格一一对应。 | Confirmed |
| AC-019 | REQ-038 | Given 两个“好耶”和两个“贴贴”候选，when 比较目录，then 四者拥有不同 ID 和可区分的动作、情绪/关系说明，模型选择不只依赖可见文案。 | Confirmed |
| AC-020 | REQ-023, REQ-039, REQ-040 | Given 自动拆分已经完成但用户尚未确认预览和目录，when 检查生产配置，then 48 枚候选均未启用或上传为生产映射。 | Confirmed |
| AC-021 | REQ-040 through REQ-042 | Given 用户确认的生产子集和目录，when 完成 Telegram 真实发送及故障演练，then 只发送确认资产、显示正确、每次一个效果，并可禁用或回滚该目录版本。 | Confirmed |
| AC-022 | REQ-043, REQ-044, REQ-046 | Given 头像候选由确认形象或表情制作但裁切/心情映射尚未单独确认，when 检查机器人资料和自动轮换配置，then 公开头像不变且自动轮换关闭。 | Confirmed |
| AC-023 | REQ-043 through REQ-045 | Given 用户确认默认头像，when 执行首次更新，then 机器人账号头像变为该精确候选并读取验证，目标群头像、机器人名称和消息能力均不改变。 | Confirmed |
| AC-024 | REQ-046 through REQ-048 | Given 已启用心情头像集合，when 稳定心情变化但距上次不足 72 小时、滚动 7 天已更新两次或只来自单群/单成员瞬时刺激，then 头像保持不变。 | Confirmed |
| AC-025 | REQ-044, REQ-047, REQ-048, REQ-056 | Given 群消息、图片文字或 Writer 工具结果要求切换任意头像，when 处理，then 不发生头像更新；只有受控头像控制器能从确认集合中执行合格变化。 | Confirmed |
| AC-026 | REQ-045, REQ-049 | Given 头像上传失败、读取状态不一致或结果不确定，when 恢复，then 不立即重复写入；保留或回滚上一已验证头像，聊天继续，审计可识别结果。 | Confirmed |
| AC-027 | REQ-012 through REQ-015, REQ-050, REQ-051 | Given 固定评审集明确标注表情适用轻互动和必须文字场景，when 统计结果，then 前者 sticker-only 占 50%–70%，后者全部使用必要文字；同一 sticker 无连续重复。 | Confirmed |
| AC-028 | REQ-052, REQ-053, REQ-055 | Given 无需工具、普通查证和确有剩余缺口的复杂查证三类轮次，when 执行，then 分别允许 0 次、最多 3 次、经可审计理由最多 5 次只读工具调用；默认上下文不占次数。 | Confirmed |
| AC-029 | REQ-053, REQ-054, REQ-056 | Given 第 5 次工具失败、超时或无结果，when Writer 继续决策，then 不产生第 6 次调用或任何未授权写入，使用已有信息回复/静默，并能从审计还原五次预算消耗。 | Confirmed |
| AC-030 | REQ-001 through REQ-056 | Given 固定评审集覆盖图片直触发/非触发、OCR、截图注入、人脸和敏感推断、损坏/超限、48 格拆分、重复文案、高频表情、头像确认/冷却/失败、0/3/5 次工具预算、陌生/亲近、严肃文本、版本错配、发送失败和回滚，when 发布候选评审，then 所有编造、越权、跨群、资产污染、重复发送、第 6 次工具调用和未确认资产/头像启用案例为零。 | Confirmed |

## Constraints

- 本修订建立在已部署 `main`、已确认乐枝 Character Bible 和已确认对话连续性触发合同之上。
- 首发只处理目标 Telegram 公开群中的静态图片、静态 sticker、文字和 Unicode emoji。
- 图片处理不扩大原始群文本或成员认识的既有保存范围。
- Character Visual Bible、拆分母版、语义目录和 Telegram 映射分别版本化并可关联验收证据。
- 每条入站消息最多一个成功群内可见外部效果。
- 头像更新是独立的机器人账号级外部写入，不是 Writer 对某条消息可直接选择的第四种回复效果。
- 每轮只读工具调用硬上限为 5；提高次数不得扩大工具权限、群范围、数据保留或外部写入授权。
- 事实、安全、人格、群隔离、成员认识、工具预算和触发规则优先于图片内容与表情选择。
- Requirements 任务不拆图、不生成目录、不上传 sticker、不更换头像、不修改实现；这些动作必须等待确认 Handoff 后由 Main Work 执行。

## Failure And Recovery

- 媒体没有响应资格时不调用视觉模型，不自动抢话。
- 下载、格式、解码、超时或预算失败时，使用可用文字继续或按直接/普通触发规则降级。
- 图片含指令、身份线索或不确定陈述时，保持不可信输入和不确定性边界。
- 源图摘要、网格数或来源坐标不匹配时，停止拆分并要求重新确认来源。
- 单枚拆分出现串格、截断、矩形白底、白色主体被误删或文案不可读时，仅返工该候选，但整包仍保持未确认。
- 目录、人格、版本或 Telegram 映射不匹配时，发送前拒绝并使用文字或静默。
- Telegram 确认未送达时最多一次安全文字降级；结果不确定时不产生第二效果。
- 新目录失败时禁用或回滚目录版本，图片理解和文字对话保持可用。
- 头像候选未确认、心情不稳定、冷却未结束或全局来源不明确时维持当前头像。
- 头像更新失败或结果不确定时不立即重复写入；必要时回滚上一已验证头像，聊天能力保持可用。
- 工具调用失败、无关或达到第 5 次时停止工具循环，使用已有信息回复或静默，不为达到 3 次下限而制造调用。

## Assumptions

| ID | Assumption | Reason | Impact if wrong | Status |
| --- | --- | --- | --- | --- |
| ASM-001 | 图片和表情能力属于已有乐枝，不创建第二个角色。 | 用户明确说“让乐枝”。 | 多角色需要独立人格和资产路由。 | Accepted |
| ASM-002 | 用户写的 `~/Document/lezhi-emoji` 实际指已找到的 `/Users/zhanghao/Documents/lezhi-emoji`。 | 只有复数目录存在且包含描述的四张图。 | 如果另有目录，需要重新锁定源文件。 | Accepted |
| ASM-003 | 用户拥有或已获得足够授权，可允许本项目复制、裁切、去背景、转换、上传和在 Telegram 中使用这四张图。 | 生产资产需要明确使用边界。 | 授权不足时只能做本地预览，不能生产启用。 | Accepted |
| ASM-004 | `character.png` 是当前希望采用的权威乐枝视觉形象，取代此前未固化的探索图。 | 文件是一张完整视觉设定板。 | 若仍需修改形象，必须先替换并重新确认摘要。 | Accepted |
| ASM-005 | 三张源拼图中的全部 48 枚都作为首套候选，不再限制为旧决定的 16 枚。 | 用户提供三组并要求拆分。 | 若只选子集，需要在拆分确认时明确生产子集。 | Accepted |
| ASM-006 | 三张 1254×1254 拼图都采用规则 4×4 视觉布局，每格一个表情。 | 视觉盘点每张均为 16 格。 | 不规则布局需要逐项人工裁切规则。 | Accepted |
| ASM-007 | “查看图片”首发包含 photo、静态图片 document 和静态 sticker，不包含 GIF、视频或动画资产。 | 控制首发媒体和成本范围。 | 动态媒体需要新的采样、时长和审核合同。 | Accepted |
| ASM-008 | 群成员原始图片只为当前处理短暂使用，不需要跨重启保存。 | 满足视觉回复同时减少数据面。 | 长期图片记忆需要新的保留、删除和容量需求。 | Accepted |
| ASM-009 | 首发继续三选一：文字、一个 sticker 或静默，不组合发送。 | 保持单外部效果和自然群聊节奏。 | 组合回复需新增顺序、幂等和补偿设计。 | Accepted |
| ASM-010 | 部署时存在或可选择支持图片输入的模型；若没有，系统必须安全降级而不能假装已看图。 | 图片理解依赖视觉模型能力。 | 若提供方不支持，需要更换模型或延后图片理解。 | Accepted |
| ASM-011 | “更换机器人的头像”指机器人账号自身的公开 profile photo，不是目标群头像。 | 用户使用“机器人头像”，且 Telegram 两者是不同的全局/群级对象。 | 若指群头像，需要管理员权限和完全不同的授权边界。 | Accepted |
| ASM-012 | 当前部署以一个乐枝机器人账号作为全局身份；其头像变化会对该账号出现的所有群和私聊可见。 | Telegram 机器人头像是账号级状态。 | 多机器人或租户化需要按 bot identity 分别维护集合与冷却。 | Accepted |
| ASM-013 | “工具调用预算 3–5 次”指每条已获得响应资格的入站消息中，Writer 对已授权只读工具的尝试次数；普通上限 3、复杂硬上限 5，不含模型/视觉/下载/外部写入。 | 与既有 Writer 工具合同和用户措辞相容。 | 若用户希望把模型或视觉调用也纳入同一计数，延迟与成本预算需要重算。 | Accepted |
| ASM-014 | “比较频繁使用表情包”以固定评审集中表情适用轻互动的 50%–70% sticker-only 比例衡量；事实、严肃、安全和无精确匹配场景不进入分母。 | 需要可测量而又不鼓励刷屏的定义。 | 更高/更低目标会改变人格表现和线上节奏。 | Accepted |

## Decisions Requiring Confirmation

| ID | Decision | Recommended default | Impact | Status |
| --- | --- | --- | --- | --- |
| DEC-001 | 首发理解哪些输入？ | Unicode emoji、Telegram photo、受支持静态图片 document、静态 sticker；已知 sticker 优先目录语义，未知静态媒体可受控视觉分析。 | 取代旧“任意视觉理解延后”决定。 | Accepted |
| DEC-002 | 哪些媒体继续延后？ | GIF、视频、相册级联合理解、动画/视频 sticker、reaction 和 custom emoji。 | 控制延迟、成本和事件范围。 | Accepted |
| DEC-003 | 乐枝能否同时发文字和 sticker？ | 不能；仍为文字、一个 sticker 或静默三选一。 | 保持幂等与单效果合同。 | Accepted |
| DEC-004 | 如何处理源表情中的图内文字？ | 48 枚的现有中文短文案都是资产内容，拆分时原样保留并逐枚验收；内部语义说明另行维护。 | 决定裁切、可读性和目录字段。 | Accepted |
| DEC-005 | 首套候选表情规模？ | 三张拼图全部拆分，共 48 枚；生产可以在最终预览确认时批准全部或明确子集。 | 取代旧 16 枚决定。 | Accepted |
| DEC-006 | `TASK-VISUAL-001` 如何完成？ | 确认本快照即确认 `character.png@78038c…816be0d` 为 Visual Bible；拆分结果仍需下一道单独确认。 | 解锁源图处理但不直接启用资产。 | Accepted |
| DEC-007 | 表情使用节奏？ | 在表情适用轻互动中优先 sticker-only，并允许相邻轮次使用不同表情；不连续重复同一表情，严肃/信息场景使用文字。 | 提高使用频率，同时控制刷屏和信息完整性。 | Accepted |
| DEC-008 | 无文字图片何时获得响应资格？ | 原生回复、有效连续性或现有主动参与证据；普通无寻址图片不自动触发。 | 控制视觉调用与抢话。 | Accepted |
| DEC-009 | 未知第三方静态 sticker 如何理解？ | 符合响应资格时允许视觉分析；只描述可见内容，不联网搜索、不识别人物、不形成权威记忆。 | 扩展旧元数据-only 边界。 | Accepted |
| DEC-010 | 表情目录如何版本化？ | 每个人格版本同时最多启用一个确认目录；内容、文字、语义或映射变化都产生新版本。 | 保证模型与资产一致并可回滚。 | Accepted |
| DEC-011 | 何时调用视觉模型？ | 只在媒体消息已有响应资格或被当前回复确实需要时调用，不默认分析群内所有图片。 | 决定成本、隐私与响应速度。 | Accepted |
| DEC-012 | 原始媒体如何保留？ | 当前处理结束即释放，不进入持久数据库、日志或成员认识；只保留非敏感审计元数据。 | 决定数据面与跨重启行为。 | Accepted |
| DEC-013 | 拆分输出形态？ | 保留透明静态母版和独立摘要，再由 F2/F3 生成 Telegram-ready 静态资产；具体编码服从 Telegram 验证。 | 避免源 RGB 白底直接成为方块 sticker。 | Accepted |
| DEC-014 | 48 枚如何排序和追溯？ | 固定 A→B→C，每张按一基行优先顺序；稳定语义 ID 可具名，但必须记录来源格。 | 保证可复现和审核。 | Accepted |
| DEC-015 | 重复文案如何处理？ | 不合并；每个视觉候选独立 ID，以动作、强度和关系用途区分“好耶”“贴贴”等重复项。 | 保留素材完整性并避免选择歧义。 | Accepted |
| DEC-016 | 默认头像使用什么来源？ | 从 `character.png` 制作清晰的默认头像；从用户最终确认的独立表情中选择少量心情变体。所有实际裁切另行确认。 | 决定 `TASK-BOT-AVATAR-001` 的候选集合。 | Accepted |
| DEC-017 | 心情头像多久可更新？ | 最短冷却 72 小时，滚动 7 天最多两次；自动轮换默认关闭，确认集合后单独启用。 | 把“低频率”变成可验证门限。 | Accepted |
| DEC-018 | 什么能驱动头像心情？ | 只用持续多个互动的全局角色心情；不接受单个成员、单群瞬时事件、图片文字或 Writer 任意指令直接驱动。 | 避免全球头像被局部输入劫持。 | Accepted |
| DEC-019 | 头像更新是否按群隔离？ | 否；机器人头像是全局状态。多群场景只允许全局人格心情，无法安全归因时保持默认头像。 | 明确所有群可见的影响范围。 | Accepted |
| DEC-020 | “比较频繁”具体目标？ | 固定表情适用轻互动评审集的 50%–70% 使用 sticker-only；线上只做聚合观测，不强迫每个窗口达标。 | 提供可测量验收且保留自然变化。 | Accepted |
| DEC-021 | 3–5 次工具预算如何分配？ | Writer 可调用 0 次；普通轮次最多 3 次，有明确剩余缺口的复杂轮次最多 5 次，绝不允许第 6 次。 | 覆盖既有 F2“最多两次工具调用”的设计默认。 | Accepted |
| DEC-022 | 哪些行为计入工具次数？ | 每个只读工具尝试均计一次，含失败/超时/无结果；默认上下文、模型调用、媒体处理和最终外部效果分别计入各自预算。 | 决定审计和循环终止。 | Accepted |
| DEC-023 | 头像更新能否作为 Writer 工具？ | 不能；头像更新由受控控制器执行，Writer 只能产生受约束的心情证据，不能直接实施账号级写入。 | 保持外部写授权与提示注入边界。 | Accepted |

## Traceability

| Source statement or artifact | Derived IDs |
| --- | --- |
| “让乐枝具备图片查看能力” | REQ-003, REQ-005 through REQ-007, REQ-019 through REQ-021, REQ-027 through REQ-032; AC-002 through AC-007; DEC-001, DEC-002, DEC-008, DEC-009, DEC-011, DEC-012 |
| “具备发送表情包的能力” | REQ-004, REQ-008 through REQ-018, REQ-025, REQ-026, REQ-040 through REQ-042; AC-008 through AC-014, AC-021; DEC-003, DEC-007, DEC-010 |
| “一个形象设计图” | `visual-source-001`; TASK-VISUAL-001; REQ-022, REQ-024, REQ-033, REQ-034; AC-015; ASM-003, ASM-004; DEC-006 |
| “三组表情包是三张图片，每张有一系列表情，需要先拆分” | `sticker-sheet-a` through `c`; TASK-STICKER-SPLIT-001; REQ-023, REQ-033, REQ-035 through REQ-041; AC-016 through AC-021; ASM-005, ASM-006; DEC-004, DEC-005, DEC-013 through DEC-015 |
| “用这个形象或者表情包更换机器人的头像；根据心情低频率更新” | TASK-BOT-AVATAR-001; REQ-043 through REQ-049; AC-022 through AC-026; ASM-011, ASM-012; DEC-016 through DEC-019, DEC-023 |
| “比较频繁地使用表情包” | REQ-012 through REQ-015, REQ-050, REQ-051; AC-027; ASM-014; DEC-007, DEC-020 |
| “增加工具调用的预算到 3–5 次” | REQ-052 through REQ-056; AC-028, AC-029; ASM-013; DEC-021 through DEC-023 |
| 先前 v0.3 确认合同 | REQ-001, REQ-002, REQ-004, REQ-006 through REQ-021, REQ-024 through REQ-026, REQ-042; AC-001, AC-008 through AC-014, AC-021 |

## Confirmation Record

- Confirmed by: User in Requirements task
- Confirmed at: 2026-08-02T13:51:29Z
- Confirmation scope: REQ-001 through REQ-056, AC-001 through AC-030, ASM-001 through ASM-014, and DEC-001 through DEC-023.

本次确认已经：

- 确认四张锁定源图及其 SHA-256；
- 确认 `character.png` 为乐枝 Character Visual Bible，并完成 `TASK-VISUAL-001`；
- 授权项目复制、裁切、去背景、转换、上传和使用四张锁定素材；
- 确认三张 4×4 源拼图作为 `TASK-STICKER-SPLIT-001` 的权威输入；
- 确认表情适用轻互动的 sticker-only 目标比例为 50%–70%；
- 确认 Writer 普通轮次最多 3 次、复杂轮次硬上限 5 次只读工具调用；
- 授权在头像候选另行确认后更换机器人公开头像，并按 72 小时冷却与滚动 7 天最多两次的门限启用低频心情轮换。

以下生产门限仍未完成，不能因本次确认而跳过：

- `TASK-STICKER-SPLIT-001` 生成的 48 枚独立预览和完整语义目录需要下一次单独确认；
- `TASK-STICKER-PACK-001` 的 Telegram-ready 资产、真实映射和生产子集需要下一次单独确认；
- `TASK-BOT-AVATAR-001` 的默认头像裁切、心情头像集合及心情映射需要下一次单独确认；
- 未完成上述确认前，不得上传或启用生产 sticker，也不得更换机器人公开头像或启用自动轮换。

旧 RequirementsHandoff `dfd1d6b82f4b34c48457a91a73da6e3be4b6f1b197b790bcbd0ee9a58229d0ba` 被本次确认修订取代；Main Work 必须以新的 versioned RequirementsHandoff 为准，并协调其与当前乐枝 v2 分支及既有两次工具调用设计的范围差异。
