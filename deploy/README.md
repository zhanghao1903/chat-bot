# Telegram Bot 部署与服务管理

本目录是固定回复和“乐枝”人格模式的部署入口。Compose 使用非 root 用户、只读根文件
系统、`no-new-privileges`、`/tmp` tmpfs 和持久化 SQLite volume。

## 目录内容

| 文件 | 用途 |
| --- | --- |
| `Dockerfile` | 构建 Python 3.11、非 root 的服务镜像 |
| `compose.yaml` | 定义服务、重启策略、安全选项和持久数据 |
| `.env.example` | 不含秘密的运行时配置模板 |
| `manage.sh` | build/start/stop/restart/status/logs 入口 |

真实 Telegram token、模型密钥、生产日志和 SQLite 数据不属于版本控制资产。

## Telegram 侧准备

1. 在 BotFather 创建 bot 并取得 token。
2. 把 bot 加入唯一目标群。
3. 通过 BotFather `/setprivacy` 关闭 privacy mode，或按 Telegram 当前规则授予接收普通
   群文本所需权限。
4. 取得目标群的负数数字 ID。

服务通过出站 HTTPS 长轮询连接 Telegram，不需要家庭路由器端口转发或入站 NAT 配置。

## 首次启动

要求 Docker Engine 和 Docker Compose v2：

```bash
cp deploy/.env.example deploy/.env
```

先填写：

```text
TELEGRAM_BOT_TOKEN=<BotFather token>
TELEGRAM_CHAT_ID=<signed numeric group id>
DATABASE_PATH=/app/data/telegram_bot.sqlite3
TELEGRAM_BOT_DATA_VOLUME=telegram-bot-data
BOT_MODE=fixed
```

启动兼容模式并完成 `1 → 1` smoke：

```bash
deploy/manage.sh start
deploy/manage.sh status
deploy/manage.sh logs
```

成功日志先出现 `telegram_identity_verified`，再出现 `telegram_polling_started`。

## 分阶段启用乐枝

只有在 22 个固定人格案例已针对所选模型通过后，才填写：

```text
BOT_MODE=persona_direct
PERSONA_BUNDLE_PATH=/app/src/group_llm_agent/persona_bundles/lezhi/lezhi-v1.0
PERSONA_EXPECTED_SHA256=25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a
MODEL_PROVIDER=openai_compatible
MODEL_BASE_URL=https://api.openai.com/v1
MODEL_API_KEY=<runtime secret>
WRITER_MODEL=<model id>
TRIGGER_MODEL=<model id>
RECOGNITION_MODEL=<model id>
MEMBER_MEMORY_CAPABILITY=disabled
```

执行 `deploy/manage.sh restart` 后，在群里依次用 @bot、回复 bot 和“乐枝，你看看……”验证
直接人格回复。乐枝发言后，还可以在 10 分钟、其后不超过 5 条真人消息的范围内发送不带
@ 的明确回答或追问，验证连续对话；单纯“收到”应自然静默。确认直接模式稳定后，才把
`BOT_MODE` 改成 `persona_full`：与乐枝无关的普通群聊仍需满足至少 15 分钟和 5 条真人消息
的硬门限，之后由人格 Trigger 选择回复或静默。

正式称呼来自不可变 Character Bundle，不会从群消息学习昵称。连续性只锚定当前群最近
一次实际成功发送的乐枝消息，且成员消息的 Telegram 秒级时间必须严格晚于锚点；超窗、
同秒或更早、对象不明、无关内容和模型失败回到原普通规则或静默。
此功能继续使用出站 Telegram/model HTTPS，不新增 webhook、监听端口或环境变量。

## 图片理解与专属表情 v0.3

图片理解和表情目录均默认关闭。纯图片不会自动抢话；只有既有触发规则已经生成一次 effect
request，运行时才会下载静态媒体。要试验视觉能力，先配置 `VISION_MODEL`，再显式设置：

```text
VISION_CAPABILITY=available
```

专属表情不得直接把候选目录设为 enabled。操作者必须使用
`group-llm-agent-operator` 依次完成 `expression-approve`、`expression-publish`、
`expression-attach` 和 `expression-enable`，每条命令都提供精确前态 SHA-256 和相应用户确认/
Telegram smoke 引用。映射 carrier 应写入 `/app/data` 或其他受保护持久目录，权限保持 0600。
只有启用后的精确目录路径和摘要才能写入：

```text
EXPRESSION_CAPABILITY=enabled
EXPRESSION_CATALOG_PATH=/app/src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3/catalog.json
EXPRESSION_CATALOG_SHA256=<enabled catalog sha256>
```

头像使用同一 operator 入口的 `avatar-approve`、`avatar-apply`、
`avatar-enable-rotation` 和 `avatar-rotate`。更新对象是 bot 账号公开头像，不是群头像。外部写入
期间独占锁覆盖 apply、读取验证和旧头像/none 回滚；HUP/INT/TERM 会先走回滚再释放锁。
自动轮换默认关闭，即使启用也要求至少三次、跨两小时、70% 一致的全局心情证据，并受 72
小时冷却和滚动 7 天最多两次限制。

在用户分别确认 48 枚联系表与目录、生产子集及 Telegram 显示、头像裁切和心情映射以前，
不得运行上述真实 publish/apply/enable 命令。

## 低频发布乐枝 v2

`lezhi-v1.0` 是固定回滚点；`lezhi-v2.0` 的生产摘要为：

```text
0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603
```

发布前必须让 `deploy/.env` 明确保留当前 `DATABASE_PATH` 和
`TELEGRAM_BOT_DATA_VOLUME`，不得通过换文件名或新建卷切换人格。依次执行：

```bash
deploy/manage.sh persona-preflight \
  /app/src/group_llm_agent/persona_bundles/lezhi/lezhi-v2.0 \
  0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603 \
  docs/feature/lezhi-persona-v2-release/provider-evaluation.json

deploy/manage.sh persona-release \
  /app/src/group_llm_agent/persona_bundles/lezhi/lezhi-v2.0 \
  0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603 \
  docs/feature/lezhi-persona-v2-release/provider-evaluation.json
```

第二条命令只会在 v1 回滚点、v2 包、37 条真实模型评测和 Compose 状态全部通过时改写
两个人格选择行。评测门禁还要求报告字节的已批准 SHA-256、provider/reviewer 身份及每条
case 的 dimension/critical 契约完全一致；仅保持 JSON 结构和高分的替代报告不能发布。
启动成功后，在目标群只发送一条明确直接呼叫，再执行：

```bash
deploy/manage.sh persona-smoke
```

冒烟要求精确新增一条入站，并且产生零或一条绑定 v2 摘要的外部效果。从候选 pin 写入
之后，Compose 停启、运行状态、人格身份、环境读取、基线访问/记录和冒烟中的任一失败都
进入同一自动 v1 回滚路径；候选 pin 生效后的 HUP/INT/TERM 也会在锁内完成非递归回滚后
再非零退出。发布、冒烟和人工回滚各自持有同一部署锁直到操作或回滚终态，避免并发流程
同时改写 Compose 与环境。也可以人工执行 `deploy/manage.sh persona-rollback`。发布状态只
保存非敏感摘要、路径、冒烟边界、失败阶段与回滚结果，位于被 Git 忽略的
`deploy/state/`。

## 启用成员认识

1. 把 `MEMBER_MEMORY_CAPABILITY` 改成 `available` 并重启。
2. 由目标群管理员发送 `/memory_enable`。
3. 确认 bot 在群里成功发送数据使用说明；只有这一步成功后才开始持久化。

任意成员可发送 `/memory_forget_me`。管理员可发送 `/memory_disable`；回复目标成员消息并
发送 `/memory_forget_member` 可清除该成员；发送 `/memory_forget_group CONFIRM` 可清除
当前群全部认识和留存原文。

## 验收顺序

1. `fixed`：精确文本 `1` 回复一次 `1`，其他文本静默。
2. `persona_direct`：@bot、回复 bot 和明确“乐枝”称呼各产生至多一条乐枝回复。
3. 乐枝提问后发送不带寻址的明确回答，确认连续性锚定实际已发送消息并回复。
4. 乐枝完成回答后发送“收到”，确认自然收尾静默且不记录为失败。
5. 紧随乐枝但内容无关、多人对象不明、超过 10 分钟或第 6 条真人消息，均不得提升为
   连续性回复；`persona_direct` 中保持静默。
6. 启用认识前，重启后不应出现持久成员认识。
7. 管理员 `/memory_enable` 后出现公开说明；重启后认识可继续演进。
8. `/memory_forget_me` 后，后续互动不得使用已清除认识。
9. `persona_full` 中与乐枝无关的消息仍受 15 分钟/5 条真人消息门槛约束。
10. 检查日志不含 Telegram/model token、完整 prompt 或 provider 原始响应体。

模型人格评分和真实群 smoke 是运营证明，不会由仓库内 scripted-model 测试替代。

## 常用操作

```bash
deploy/manage.sh build
deploy/manage.sh start
deploy/manage.sh restart
deploy/manage.sh status
deploy/manage.sh logs
deploy/manage.sh stop
```

`stop` 删除容器和 Compose 网络，但保留 `TELEGRAM_BOT_DATA_VOLUME` 指定的命名 volume。

外部环境文件可显式指定：

```bash
TELEGRAM_BOT_ENV_FILE=/secure/path/telegram-bot.env deploy/manage.sh start
```

## 故障恢复

- `configuration_error`：修正缺失、范围或秘密格式，再重启。
- `persona_startup_failed`：检查人格路径/摘要、模型 URL、key 和模型名；校验发生在轮询前。
- `telegram_startup_failed`：检查 token、出站 HTTPS、bot 身份和目标群权限。
- 收不到普通文本：检查 bot 所在群、privacy mode 和权限。
- `poll_failed`：长轮询按配置退避重试；持续失败时检查家庭网络/DNS/HTTPS。
- 直接触发无回复：检查模型 endpoint、预算和日志中的脱敏错误类别。
- 自然连续对话未回复：确认锚点是当前群实际发送消息，未超过 10 分钟/5 条真人消息；
  成员消息还必须在 Telegram 时间上至少晚一个整秒；同秒、无关、歧义和自然收尾会按
  设计降级或静默。
- 认识未启用：确认 capability 为 `available`，命令发送者是管理员，且公开说明发送成功。
- SQLite 错误：检查 `telegram-bot-data` 可写性和磁盘容量。

## 回滚

人格版本回滚执行 `deploy/manage.sh persona-rollback`，恢复记录的 v1 精确路径和摘要并重启
同一 Compose 服务。不要删除 `TELEGRAM_BOT_DATA_VOLUME` 指定的数据卷，否则会丢失投递
去重、审计、认识重置代次和可能仍需保留的数据清除证据。若必须删除数据，应先按群内
透明控制流程清除，并明确接受恢复影响。

## 安全说明

- `deploy/.env` 被 `.gitignore` 排除。
- 镜像不包含运行时 token 或模型密钥。
- Compose 以 `app` 用户、只读根文件系统和 `no-new-privileges` 运行。
- 唯一持久可写位置是 `/app/data`。
- 服务只建立出站 Telegram/model HTTPS 连接，不监听公网端口。
- 数据、工具和模型上下文被固定在目标公开群；不访问私聊、其他群或外部成员档案。
