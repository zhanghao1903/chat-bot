# Telegram 群聊基础骨架 0.1

这是一个只做一件事的 Telegram 群服务：连接一个指定群，读取普通文本消息，并在群成员发送精确文本 `1` 时，对原消息回复一次精确文本 `1`。

0.1 不接入 LLM，不处理私聊或媒体消息，不做群管理，也不会对其他文本回复。

## 行为

| 输入 | 结果 |
| --- | --- |
| 目标群中的精确文本 `1` | 对原消息回复一次 `1` |
| ` 1`、`1 ` 或其他文本 | 读取后保持静默 |
| 其他群、私聊、媒体消息 | 忽略 |
| bot 自己或其他 bot 的消息 | 忽略 |
| 重复投递同一条触发消息 | 不重复回复 |

服务启动前会通过 Telegram `getMe` 验证 bot 身份。验证失败时进程以非零状态退出，不会把失败误报为已连接。

## 前置条件

- Python 3.11 或更高版本。
- 通过 [BotFather](https://t.me/BotFather) 创建的 bot token。
- bot 已加入目标群。
- Telegram 已配置为向 bot 投递普通群文本。通常需要使用 BotFather 的 `/setprivacy` 关闭该 bot 的 privacy mode，或者按 Telegram 当前规则授予足够的群权限。
- 目标群的带符号数字 ID，例如 supergroup 常见的 `-100...`。

bot 创建、入群和 Telegram 权限配置由群管理员完成。

## 本地启动

创建虚拟环境并安装：

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --no-deps .
```

准备外部配置：

```bash
cp .env.example .env
```

填写 `.env` 中的 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`，再启动：

```bash
set -a
. ./.env
set +a
group-llm-agent
```

也可以不安装，直接从源码运行：

```bash
set -a
. ./.env
set +a
PYTHONPATH=src python3 -m group_llm_agent
```

成功启动时会依次出现不含 token 的 `telegram_identity_verified` 和 `telegram_polling_started` 日志。

## 配置

| 变量 | 必需 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | 是 | 无 | 只在运行时提供，不得提交 |
| `TELEGRAM_CHAT_ID` | 是 | 无 | 唯一允许的群/超级群负数 ID |
| `DATABASE_PATH` | 否 | `data/telegram_bot.sqlite3` | 最小投递去重账本 |
| `TELEGRAM_POLLING_TIMEOUT_SECONDS` | 否 | `25` | `1..50` |
| `TELEGRAM_RETRY_DELAY_SECONDS` | 否 | `2` | 拉取失败后的固定等待，`1..60` |
| `LOG_LEVEL` | 否 | `INFO` | Python 标准日志级别 |

配置错误返回退出码 `2`；Telegram 身份验证失败返回 `3`；本地数据库初始化失败返回 `4`。

## 失败与恢复

- Token 无效或 Telegram 不可达：启动验证失败并输出经过脱敏的错误；修正配置或网络后重新启动。
- 运行中拉取失败：记录脱敏错误，等待配置的秒数后继续拉取。
- 单条更新无法解析：跳过该更新并继续后续更新。
- 回复发送失败：在 SQLite 账本中标记 `failed`，继续处理后续消息，不自动无限重试。
- 同一消息重复投递：唯一投递键阻止第二次回复。

SQLite 只保存群 ID、消息 ID、动作类型、状态、错误类别和时间戳；不保存群消息文本、原始 Telegram update 或 token。

## 测试

```bash
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

测试覆盖配置、Telegram 归一化、精确匹配、静默规则、自消息保护、跨重启去重、发送失败、错误脱敏和坏消息隔离。

真实 Telegram smoke test 需要管理员提供运行时 token、目标群和权限，因此不会把凭据放进自动化测试。

## 部署

所有部署和线上服务资产统一放在 [`deploy/`](deploy/README.md)。Docker Compose 入口：

```bash
cp deploy/.env.example deploy/.env
# 填写 deploy/.env
deploy/manage.sh start
deploy/manage.sh logs
```

停止服务但保留投递账本：

```bash
deploy/manage.sh stop
```

## 安全边界

- 不提交真实 token、生产密钥、日志或数据库。
- 日志不输出 token 和完整消息正文。
- 0.1 唯一外部写操作是对精确触发消息调用 `sendMessage`。
- 不执行删消息、禁言、踢人、封禁、工具调用或 LLM 请求。

## 生命周期文档

- [Confirmed requirements](docs/feature/telegram-group-v0-1/requirements.md)
- [Technical design](docs/feature/telegram-group-v0-1/design.md)
- [Implementation plan](docs/feature/telegram-group-v0-1/implementation-plan.md)
