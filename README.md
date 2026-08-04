# Telegram 群聊人格机器人

这是一个面向单个 Telegram 公开群的长轮询机器人。它保留 0.1 的确定性
`1 → 1` 模式，并提供原创人格“乐枝”、自然称呼与连续对话触发、选择性群聊参与、
限次作家效应器、当前群上下文工具，以及需管理员公开启用的成员认识。

`fixed` 仍是默认模式；人格能力不会因升级而静默开启。

## 运行模式

| `BOT_MODE` | 行为 |
| --- | --- |
| `fixed` | 仅在目标群收到精确文本 `1` 时回复一次 `1`；不调用模型 |
| `persona_direct` | 响应 @bot、回复 bot、bot command、明确呼叫“乐枝”，以及对乐枝近期实际发言的语义连续回应；不主动参与无关普通消息 |
| `persona_full` | 包含 `persona_direct` 的全部响应式触发；无关普通消息仍需至少间隔 15 分钟且累计 5 条真人消息，才允许人格 Trigger 判断回复或静默 |

所有模式只处理配置的一个群，忽略私聊、其他群、bot 消息和重复 update。受支持的静态
图片只有先通过同一寻址/连续性/主动参与门槛，才会被短暂下载并理解；媒体本身不会抬高
触发资格。普通人格回复最多产生一个逻辑 bundle：一条文本、一个 sticker，或先文本后一个
sticker；定时推荐、控制命令和其他外部写入仍各自最多一个外部效果。

## 对话连续性触发 v0.2

运行时只从当前 Character Bundle 读取正式名“乐枝”，不会从群消息学习永久昵称。类似
“乐枝，你看看这个”“乐枝 你怎么看？”和“你觉得呢，乐枝？”会按直接触发处理；第三
人称谈论、引用、历史发言讨论或名单中的名字不会仅凭名字出现触发。

乐枝成功发言后，系统可在当前群最近一次实际已发送消息后的 10 分钟内、且其后不超过
5 条真人消息时评估对话连续性。成员消息的 Telegram 秒级时间必须严格晚于该发言；早于
它或同一秒、因而无法证明先后顺序的消息不会作为连续回应。时间相邻只决定是否值得评估，
语义模型仍必须区分：

- `continue`：回答、追问、接受/拒绝建议、反应或继续邀请，进入一次相关回复；
- `close`：致谢、确认、笑声或自然收尾，记录为正常静默；
- `not_addressed` / `ambiguous`：与乐枝无关或对象不明确，回到原有普通参与规则。

优先级固定为群范围/控制命令 → Telegram 显式直接触发 → 正式名称呼 → 对话连续性 →
普通主动参与。群文本不能修改称呼集合、窗口、优先级、人格或安全合同。审计只记录类别、
结果、理由码和锚点消息 ID，不额外延长消息全文保留期。

## 人格与作家效应器

当前生产人格 v2 位于
`src/group_llm_agent/persona_bundles/lezhi/lezhi-v2.0`，内容摘要为：

```text
0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603
```

`lezhi-v1.0` 及其摘要
`25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a`
保持不变，作为精确回滚点。人格版本不能原地覆盖；每次低频更新都必须使用新目录、新摘要
和独立评测证据。

Trigger、Recognition 和 Effector 都从同一不可变人格快照编译。普通轮次可调用 3 次
既有群上下文工具，只有前序新证据仍留下明确缺口时才可扩展到第 4–5 次，第 6 次上下文
工具调用不存在。工具包括：

- 查询当前场景内成员在当前群的有效认识；
- 检索当前群保留期内的近期消息。

模型不能指定群范围、凭据、外部写操作或任意工具。只有 Telegram 回复提交器可以发送
消息；模型失败时 Telegram 显式直接触发和正式名称呼会给出一次安全失败回复，连续性
判断/回复和选择性群聊触发则安全降级或保持静默。

v0.4 把模型调用硬上限提高到 11，以容纳两个互不借用额度的只读工具预算：既有群上下文
仍为普通 3 次、复杂轮次最多 5 次；Tavily Web 工具独立最多 5 次。两类工具共享整个 effect
截止时间、16 KiB 已接纳结果上限和最终回复保留位，因此理论上的 `5 + 5 + 1` 不是最低
调用次数，也不是无限 loop。

v2 的 37 条真实模型评测证据见
[provider-evaluation.json](docs/feature/lezhi-persona-v2-release/provider-evaluation.json)，发布与
回滚证据见 [verification.md](docs/feature/lezhi-persona-v2-release/verification.md)。

## 图片理解、专属表情和头像 v0.3.1

`VISION_CAPABILITY=available` 后，只有已经获得回复资格的 photo、静态图片 document 或
静态 sticker 才会被有界下载、清除元数据并交给视觉模型。图中文字、二维码和截图消息始终
是不可信内容；应用会拒绝身份、敏感属性、医疗诊断和定位推断。原始媒体不写数据库或日志。

48 枚专属表情的不可变候选资产位于
`src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3`；生产运行使用另行批准、映射且
摘要锁定的 enabled 目录，仓库 candidate 字节不会原地晋级。Writer 只看语义说明并选择语义
ID，无法读取或提交 Telegram `file_id`。一次人格回复可以是一条单句/多句文本、一个 sticker、
或先发送一条文本再发送一个 sticker；两组件共享持久 bundle identity，组件结果不确定时不会
重发或追加替代内容。线上指标只统计最近 7 天最多 100 个 sticker-eligible 且至少有一个成功
组件的 bundle，少于 30 个只显示 insufficient-data。

头像和表情写操作只通过 `group-llm-agent-operator` 执行。v0.3.1 唯一授权的头像写入是摘要
锁定的 `lezhi-default`：先用 `getMe` 绑定 bot identity，再恰好调用一次 Telegram 官方
`setMyProfilePhoto`。官方接口明确 `result=true` 即记录 `success`；明确拒绝记录 `failed`，超时、
传输中断、5xx 或结果无法解析记录 `uncertain`。系统不会读取旧头像、不会上传后 readback、
不会把头像发给视觉模型，也不会自动重试或回滚。显示异常由用户人工上报，并通过 operation ID
关联审计。四张 mood 头像、VISION 和自动头像轮换继续关闭。

## 订阅式工作日美食推荐 v0.4

自动化和 Tavily 默认均关闭。部署者把 `AUTOMATION_CAPABILITY` 设为 `available` 只会加载
调度与控制能力，不会替任何群启用功能，也不会自动创建订阅。随后必须由目标群管理员发送
`/food_enable`，再由至少一名成员发送 `/food_subscribe`。默认使用 `Asia/Shanghai`，仅在工作日
11:30 和 17:30 各形成一个稳定 occurrence，并只在 30 分钟宽限期内处理；多个订阅者合并为
一条群级推荐。

| 命令 | 权限与效果 |
| --- | --- |
| `/food_enable` | 管理员；启用当前群默认工作日午/晚餐计划 |
| `/food_disable CONFIRM` | 管理员；关闭并清除当前订阅 |
| `/food_pause` / `/food_resume` | 管理员；暂停或恢复，不影响普通聊天 |
| `/food_config timezone=... lunch=HH:MM dinner=HH:MM location=...` | 管理员；更新有界配置并生成新版本 |
| `/food_subscribe` / `/food_unsubscribe` | 成员；订阅或退订自己 |
| `/food_preferences cuisine=... budget=... dietary=... avoid=...` | 已订阅成员；更新有限、非敏感偏好 |
| `/food_status` | 成员；查看状态、订阅数、自己的订阅状态和下一次时间 |

`TAVILY_WEB_CAPABILITY=available` 且外部安全配置存在有效 `TAVILY_API_KEY` 时，Writer 才能
使用 Tavily Search/Extract 对应的 `web_search` / `web_fetch`。它只能 fetch 本轮搜索产生且
通过 URL 安全校验的候选，不使用 Crawl、Map、Research、登录、Cookie、脚本或网页写操作。
Tavily 不可用时会降级为不声称实时商家状态的通用推荐，或安全跳过；普通 Telegram 聊天
继续工作。发送结果不确定时 occurrence 标为 `uncertain`，不会自动补发。

## 成员认识与透明控制

`MEMBER_MEMORY_CAPABILITY=available` 只表示运行时具备能力，不会自动启用持久认识。目标群
管理员必须发送 `/memory_enable`；只有机器人成功向群里发送公开说明后，持久消息与认识任务
才开始写入。

| 命令 | 权限与效果 |
| --- | --- |
| `/memory_enable` | 管理员；公开说明后启用当前群认识 |
| `/memory_disable` | 管理员；立即停止新持久化与认识任务 |
| `/memory_forget_me` | 任意成员；清除自己在当前群的认识和留存原文 |
| `/memory_forget_member` | 管理员回复目标成员消息使用；仅清除该成员在当前群的数据 |
| `/memory_forget_group CONFIRM` | 管理员；清除当前群全部认识和留存原文 |

即时上下文最多 20 条。启用持久认识时，原文保留期可配置为 1～7 天；派生认识带来源、
置信度和版本，可被后续证据修订、降置信或撤销。私聊、其他群、外部档案和敏感属性推断
不进入认识系统。

## 前置条件

- Python 3.11 或更高版本，或 Docker Engine + Compose v2；
- 通过 [BotFather](https://t.me/BotFather) 创建的 bot token；
- bot 已加入目标群并能接收普通群文本；
- 目标群的负数 ID，例如 supergroup 常见的 `-100...`；
- 人格模式所用的 OpenAI-compatible HTTPS endpoint、API key 和模型名；
- 人格模式上线前完成固定人格评测和管理员授权的真实群 smoke。

普通群消息通常要求通过 BotFather `/setprivacy` 关闭 privacy mode，或按 Telegram 当前规则
授予足够权限。真实 token、模型密钥、日志和数据库不得提交。

## 本地启动

创建环境并安装：

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --no-deps .
cp .env.example .env
```

### 兼容模式

填写 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`，保留：

```text
BOT_MODE=fixed
```

### 乐枝直接回复模式

除 Telegram 配置外，填写：

```text
BOT_MODE=persona_direct
PERSONA_BUNDLE_PATH=src/group_llm_agent/persona_bundles/lezhi/lezhi-v2.0
PERSONA_EXPECTED_SHA256=0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603
MODEL_PROVIDER=openai_compatible
MODEL_BASE_URL=https://api.openai.com/v1
MODEL_API_KEY=<runtime secret>
WRITER_MODEL=<model id>
TRIGGER_MODEL=<model id>
RECOGNITION_MODEL=<model id>
MEMBER_MEMORY_CAPABILITY=disabled
VISION_CAPABILITY=disabled
EXPRESSION_CAPABILITY=disabled
AUTOMATION_CAPABILITY=disabled
TAVILY_WEB_CAPABILITY=disabled
```

`TRIGGER_MODEL` 和 `RECOGNITION_MODEL` 留空时会使用 `WRITER_MODEL`。要在完成评测和群内说明
后启用认识能力，将 `MEMBER_MEMORY_CAPABILITY` 改为 `available`，重启，再由管理员发送
`/memory_enable`。验证直接模式后才建议把 `BOT_MODE` 改为 `persona_full`。

启动：

```bash
set -a
. ./.env
set +a
group-llm-agent
```

也可从源码运行：

```bash
set -a
. ./.env
set +a
PYTHONPATH=src python3 -m group_llm_agent
```

成功启动时日志依次出现不含凭据的 `telegram_identity_verified` 和
`telegram_polling_started`。

## 配置

| 变量 | 人格模式 | 默认值/范围 | 说明 |
| --- | --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | 全部必需 | 无 | BotFather token；危险字符会被安全拒绝 |
| `TELEGRAM_CHAT_ID` | 全部必需 | 无 | 唯一允许的负数群 ID |
| `DATABASE_PATH` | 可选 | `data/telegram_bot.sqlite3` | 去重、运行审计、消息和认识数据库 |
| `BOT_MODE` | 可选 | `fixed` | `fixed`、`persona_direct`、`persona_full` |
| `PERSONA_BUNDLE_PATH` | 必需 | 无 | 明确选择的人格包目录 |
| `PERSONA_EXPECTED_SHA256` | 必需 | 无 | 小写 64 位摘要；不匹配则联网前失败 |
| `MODEL_PROVIDER` | 必需 | `openai_compatible` | 当前仅支持该协议 |
| `MODEL_BASE_URL` | 必需 | 无 | HTTPS API 根地址 |
| `MODEL_API_KEY` | 必需 | 无 | 运行时秘密；不会出现在安全错误或 repr 中 |
| `WRITER_MODEL` | 必需 | 无 | 作家效应器模型 |
| `TRIGGER_MODEL` | 可选 | `WRITER_MODEL` | 选择性参与模型 |
| `RECOGNITION_MODEL` | 可选 | `WRITER_MODEL` | 后台认识模型 |
| `VISION_CAPABILITY` | 可选 | `disabled` | `available` 才允许合格媒体调用视觉模型 |
| `VISION_MODEL` | 视觉启用时必需 | 无 | OpenAI-compatible 多模态模型 ID |
| `VISION_TIMEOUT_SECONDS` | 可选 | `15`，范围 `3..30` | 单次视觉调用时限 |
| `MEDIA_MAX_DOWNLOAD_BYTES` | 可选 | `8388608`，最大 `20971520` | Telegram 媒体下载硬限制 |
| `MEDIA_MAX_PIXELS` | 可选 | `12000000`，最大 `20000000` | 解码像素上限 |
| `EXPRESSION_CAPABILITY` | 可选 | `disabled` | 只有目录状态 `enabled` 时才可设为 `enabled` |
| `EXPRESSION_CATALOG_PATH` | 表情启用时必需 | 无 | 已确认、已映射目录路径 |
| `EXPRESSION_CATALOG_SHA256` | 表情启用时必需 | 无 | 精确目录摘要；不匹配则联网前失败 |
| `MEMBER_MEMORY_CAPABILITY` | 可选 | `disabled` | `available` 仍需群管理员公开启用 |
| `RAW_MESSAGE_RETENTION_DAYS` | 可选 | `7`，范围 `1..7` | 启用认识后的原文保留期 |
| `EFFECT_MAX_MODEL_CALLS` | 可选 | `11`，范围 `1..11` | 每次效应器最大模型调用，含最终回复保留位 |
| `EFFECT_ORDINARY_TOOL_CALLS` | 可选 | `3`，范围 `0..3` | 普通轮次只读工具上限 |
| `EFFECT_MAX_TOOL_CALLS` | 可选 | `5`，范围 `0..5` | 复杂轮次绝对上限，必须小于模型调用上限 |
| `WEB_TOOL_LIMIT` | 可选 | `5`，范围 `0..5` | 独立 Tavily Web 工具尝试上限，不借用上下文额度 |
| `TOOL_RESULT_TOTAL_CHARS` | 可选 | `16384`，范围 `1024..16384` | 两类工具共同的已接纳结果字符上限 |
| `EFFECT_DEADLINE_SECONDS` | 可选 | `20`，范围 `5..30` | 整个效应器截止时间 |
| `TRIGGER_DECISION_TIMEOUT_SECONDS` | 可选 | `5`，范围 `2..10` | Trigger 调用时限 |
| `RECOGNITION_TIMEOUT_SECONDS` | 可选 | `15`，范围 `5..30` | Recognition 调用时限 |
| `RECOGNITION_MAX_ATTEMPTS` | 可选 | `3`，范围 `1..3` | 后台认识最大尝试次数 |
| `AUTOMATION_CAPABILITY` | 可选 | `disabled` | `available` 只加载调度/控制，仍需管理员启用群 |
| `AUTOMATION_TICK_SECONDS` | 可选 | `15`，范围 `5..60` | 后台到期扫描间隔 |
| `SCHEDULED_EFFECT_DEADLINE_SECONDS` | 可选 | `60`，范围 `15..90` | 单个调度推荐共享截止时间 |
| `TAVILY_WEB_CAPABILITY` | 可选 | `disabled` | `available` 才注册 Tavily Search/Extract |
| `TAVILY_API_KEY` | Web 启用时运行所需 | 无 | 外部秘密；不进入提示、审计或日志 |
| `TAVILY_PROJECT_ID` | 可选 | 无 | 有界部署项目标识 |
| `TAVILY_TIMEOUT_SECONDS` | 可选 | `8`，范围 `3..10` | 每次 Tavily 请求时限，无隐藏重试 |
| `TELEGRAM_POLLING_TIMEOUT_SECONDS` | 可选 | `25`，范围 `1..50` | Telegram 长轮询 |
| `TELEGRAM_RETRY_DELAY_SECONDS` | 可选 | `2`，范围 `1..60` | 拉取失败后的等待 |
| `LOG_LEVEL` | 可选 | `INFO` | Python 标准日志级别 |

配置/人格启动错误返回退出码 `2`；Telegram 身份验证失败返回 `3`；本地数据库初始化失败
返回 `4`。

## 失败、回滚与安全

- 人格包、摘要、模型配置在 Telegram 轮询前校验；失败时不会误报已连接。
- 模型/工具有截止时间和固定预算，不存在无限 loop。
- 选择性 Trigger 失败即静默；Recognition 失败按上限退避重试，最终进入 dead 状态。
- 发送结果不确定时记为 `uncertain`，不会盲目重发造成重复外部效果。
- 调度在群关闭、暂停、无订阅、周末或超过 30 分钟宽限时不调用 Writer/Tavily，也不发送；
  `prepared` 可安全恢复，已 claim 的 `sending` 在重启后变为 `uncertain` 而不重发。
- 日志不记录 token、模型密钥、完整 prompt、工具结果或原始 provider body。
- 所有持久数据按单一公开群隔离；模型参数不能扩大范围。
- 人格发布失败使用 `deploy/manage.sh persona-rollback` 恢复精确 v1 路径与摘要；不要删除
  数据库或命名卷，否则会丢失去重和认识证据。

## 验证与部署

```bash
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
uvx ruff check .
uvx ruff format --check .
mypy src
uv build
sh -n deploy/manage.sh
docker compose -f deploy/compose.yaml config
```

完整证据、验收矩阵和未执行的外部证明见
[verification.md](docs/feature/lezhi-scheduled-food-recommendations-v0-4/verification.md)。部署步骤见
[deploy/README.md](deploy/README.md)。

## 生命周期文档

- [Confirmed requirements](docs/feature/maomao-persona-chat/requirements.md)
- [Confirmed Character Bible](docs/feature/maomao-persona-chat/character-bible.md)
- [Technical design](docs/feature/maomao-persona-chat/design.md)
- [Implementation plan](docs/feature/maomao-persona-chat/implementation-plan.md)
- [Persona evaluation](docs/feature/maomao-persona-chat/persona-evaluation.md)
- [Verification](docs/feature/maomao-persona-chat/verification.md)
- [Conversation trigger v0.2 requirements](docs/feature/lezhi-conversation-triggers-v0-2/requirements.md)
- [Conversation trigger v0.2 design](docs/feature/lezhi-conversation-triggers-v0-2/design.md)
- [Conversation trigger v0.2 implementation plan](docs/feature/lezhi-conversation-triggers-v0-2/implementation-plan.md)
- [Conversation trigger v0.2 verification](docs/feature/lezhi-conversation-triggers-v0-2/verification.md)
- [Scheduled food v0.4 requirements](docs/feature/lezhi-scheduled-food-recommendations-v0-4/requirements.md)
- [Scheduled food v0.4 design](docs/feature/lezhi-scheduled-food-recommendations-v0-4/design.md)
- [Scheduled food v0.4 implementation plan](docs/feature/lezhi-scheduled-food-recommendations-v0-4/implementation-plan.md)
- [Scheduled food v0.4 verification](docs/feature/lezhi-scheduled-food-recommendations-v0-4/verification.md)
- [Lezhi persona v2 requirements](docs/feature/lezhi-persona-v2-release/requirements.md)
- [Lezhi persona v2 design](docs/feature/lezhi-persona-v2-release/design.md)
- [Lezhi persona v2 implementation plan](docs/feature/lezhi-persona-v2-release/implementation-plan.md)
- [Lezhi persona v2 provider evaluation](docs/feature/lezhi-persona-v2-release/provider-evaluation.json)
- [Lezhi persona v2 verification](docs/feature/lezhi-persona-v2-release/verification.md)
- [Lezhi visual expression v0.3 requirements](docs/feature/lezhi-sticker-expression-v0-3/requirements.md)
- [Lezhi visual expression v0.3 design](docs/feature/lezhi-sticker-expression-v0-3/design.md)
- [Lezhi visual expression v0.3 implementation plan](docs/feature/lezhi-sticker-expression-v0-3/implementation-plan.md)
- [Lezhi visual expression v0.3 verification](docs/feature/lezhi-sticker-expression-v0-3/verification.md)
- [Lezhi avatar and expression v0.3.1 requirements](docs/feature/lezhi-avatar-and-expression-v0-3-1/requirements.md)
- [Lezhi avatar and expression v0.3.1 design](docs/feature/lezhi-avatar-and-expression-v0-3-1/design.md)
- [Lezhi avatar and expression v0.3.1 implementation plan](docs/feature/lezhi-avatar-and-expression-v0-3-1/implementation-plan.md)
- [Lezhi avatar and expression v0.3.1 fixed evaluation](docs/feature/lezhi-avatar-and-expression-v0-3-1/evaluation-cases.json)
- [Lezhi avatar and expression v0.3.1 verification](docs/feature/lezhi-avatar-and-expression-v0-3-1/verification.md)
