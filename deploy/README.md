# Telegram Bot 部署与服务管理

本目录是 0.1 唯一的部署与线上服务资产入口。

## 目录内容

| 文件 | 用途 |
| --- | --- |
| `Dockerfile` | 构建 Python 3.11、非 root 的服务镜像 |
| `compose.yaml` | 定义服务、重启策略和持久化投递账本 |
| `.env.example` | 不含秘密的运行时配置模板 |
| `manage.sh` | build/start/stop/restart/status/logs 入口 |

真实 token、生产日志和 SQLite 数据不属于版本控制资产。

## Telegram 侧准备

1. 在 BotFather 创建 bot 并取得 token。
2. 把 bot 加入目标群。
3. 配置 Telegram，使普通群文本能够投递给 bot。通常需要通过
   BotFather `/setprivacy` 关闭 privacy mode，或者按 Telegram 当前规则授予足够权限。
4. 取得目标群的带符号数字 ID。

不要把 token 贴到 Issue、PR、日志或命令输出中。

## 首次启动

要求已安装 Docker Engine 和 Docker Compose v2。

```bash
cp deploy/.env.example deploy/.env
```

编辑 `deploy/.env`：

```text
TELEGRAM_BOT_TOKEN=<BotFather token>
TELEGRAM_CHAT_ID=<signed numeric group id>
```

启动并查看状态：

```bash
deploy/manage.sh start
deploy/manage.sh status
deploy/manage.sh logs
```

启动成功的最低证明是日志先出现 `telegram_identity_verified`，再出现
`telegram_polling_started`。

## 群内验证

1. 群成员发送精确文本 `1`。
2. bot 必须对原消息回复一次精确文本 `1`。
3. 发送其他文本和带空格的 ` 1`，bot 必须保持静默。
4. 重启服务后不应再次回复已经处理过的同一消息。

投递账本保存在 Compose volume `telegram-bot-data` 中，容器替换不会丢失。

## 常用操作

```bash
deploy/manage.sh build
deploy/manage.sh start
deploy/manage.sh restart
deploy/manage.sh status
deploy/manage.sh logs
deploy/manage.sh stop
```

`stop` 删除容器和网络，但保留命名 volume。

如果配置文件位于其他位置，可以显式指定：

```bash
TELEGRAM_BOT_ENV_FILE=/secure/path/telegram-bot.env deploy/manage.sh start
```

## 故障恢复

- `configuration_error`：补齐或修正 `.env`，再执行 `restart`。
- `telegram_startup_failed`：检查 token、网络和 Telegram 服务，再执行 `restart`。
- 启动成功但收不到普通文本：检查 bot 是否在正确群中，以及 privacy mode/群权限。
- `poll_failed`：服务会按配置等待并重试；持续失败时检查网络。
- `reply_failed`：失败已记录且不会无限重发；修复 Telegram 权限或网络后，用新消息重新验证。
- SQLite 错误：检查 volume 可写性和磁盘容量。

## 回滚

停止当前服务，切回上一版本或上一镜像，再重新启动。不要删除
`telegram-bot-data`，除非明确接受丢失去重状态及潜在重复回复风险。

## 安全说明

- `deploy/.env` 被 `.gitignore` 排除。
- Compose 以非 root 用户、只读根文件系统和 `no-new-privileges` 运行。
- 唯一可写位置是 `/app/data` 的投递账本 volume。
- 不在镜像、Compose 文件或脚本中写入 token。
- 不把运行日志、数据库或其他运行时数据提交到仓库。
