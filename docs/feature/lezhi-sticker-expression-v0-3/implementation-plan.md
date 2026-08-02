# Implementation Plan: 乐枝图片理解、专属表情与动态头像 v0.3

- Phase: F3 Implementation Plan
- Status: Complete
- Requirements handoff: `42a2438556f8ae245d13c13b0452e1f5364ec3755cb950a1ba89c044f4821311`
- Design commit: `7d84902cb3a56c1a94a8a0e65f7b20f79ab7d443`
- Branch: `codex/lezhi-sticker-expression-v0-3`

## 1. Delivery Contract

本计划实施已确认的 REQ-001–056 和 AC-001–030。交付完成意味着：

- 静态媒体可以在既有触发资格成立后被安全、短暂地理解；
- 目录启用后，Writer 能选择一个已确认专属 sticker，应用侧安全发送；
- 48 枚候选、目录和头像预览可复现、可审阅、可确认；
- 工具循环满足 0/3/5 和第 6 次硬拒绝；
- 默认头像与低频心情头像具备受控、可审计、可回滚能力；
- 全套代码、资产、包、Compose、真实 provider 和 Telegram 证明达到要求；
- 所有生产资产和头像写入严格停在用户二次确认门限之前。

候选生成、代码实现和本地验证可以连续推进。只有 `approved -> telegram_ready -> enabled`
以及头像写入需要用户确认后再执行。

## 2. Planned Package Boundaries

| File/package | Planned responsibility |
| --- | --- |
| `events.py` | media/message/final-effect immutable contracts |
| `platforms/telegram.py` | media normalization, bounded file transport, sticker/profile APIs |
| `media.py` | in-memory validation and normalization |
| `vision.py` | multimodal provider protocol and evidence validation |
| `expression.py` | catalog/avatar manifest load, digest and allowlist validation |
| `asset_pipeline.py` | deterministic source import, 48 split, WebP and preview generation |
| `effector.py` / `model.py` | sticker decision, mood signal and adaptive tool loop |
| `database.py` / `messages.py` / `runs.py` | migration and metadata-only audit |
| `runtime.py` / `app.py` / `config.py` | orchestration and disabled-by-default integration |
| `avatar.py` / `__main__.py` | operator-only avatar and asset promotion commands |
| `expression_assets/lezhi/lezhi-expression-v0.3/` | immutable source/candidate/approved artifacts |

新增生产 Python 文件保持单一职责，目标不超过 500 行；Telegram transport 若接近 800 行，
在同一切片拆成 JSON client 与 multipart/media client，而不是继续扩大单文件。

## 3. Slice 0 — Baseline and Contract Skeleton

### Files

- `src/group_llm_agent/events.py`
- `src/group_llm_agent/database.py`
- `src/group_llm_agent/messages.py`
- `src/group_llm_agent/runs.py`
- `tests/test_database.py`
- `tests/test_messages.py`
- `tests/test_runtime.py`

### Changes

- 引入 `TelegramMessage`、`InboundMedia`、媒体/最终效果枚举并保留兼容别名；
- 添加 migration 3 的列、表、索引和 CHECK 枚举；
- 只持久化允许的媒体身份元数据；media-only 不生成认识任务；
- 扩展 external-effect claim 为 requested/delivered kind，保持事件唯一约束；
- 添加 vision、catalog、mood、avatar 的元数据审计仓库接口。

### Checks

- 旧 migration 1/2 数据库原位升级；
- 文本消息读写字节级兼容；
- 媒体 `file_id` 和二进制不入库；
- 旧 effect 状态迁移后仍可读取；
- `python -m compileall`、相关 unittest、Ruff、Mypy。

### Commit intent

`feat: add media and expression persistence contracts`

## 4. Slice 1 — Deterministic Candidate Assets

### Files

- `src/group_llm_agent/asset_pipeline.py`
- `src/group_llm_agent/expression.py`
- `src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3/**`
- `tests/test_asset_pipeline.py`
- `tests/test_expression.py`
- `pyproject.toml`

### Changes

- 增加固定 Pillow 运行依赖；
- 导入四个源文件并重新校验需求摘要；
- 按 A/B/C、行优先确定性拆分 48 格；
- 用边界 flood-fill 去除相连近白背景，保护内部白色内容；
- 生成 512 PNG 母版、512 WebP、浅/深预览和联系表；
- 生成 48 条语义目录草案，重复文案使用不同稳定 ID；
- 生成默认头像和少量心情头像候选及圆形预览；
- manifest/catalog/avatar catalog 均保持 `candidate`，确认字段为空。

### Checks

- 四个源摘要、三个 4×4、总数 48；
- 无串格、非透明包围盒、角落透明、白帽/白衣保护像素探针；
- 一边 512、WebP 可重新打开、每项摘要唯一；
- 两次干净构建的 manifest/catalog 摘要一致；
- wheel/sdist 包含运行时需要的目录，不包含构建临时文件。

### Gate and evidence

生成后立即向用户展示 A/B/C 联系表、完整目录和头像圆形预览。用户确认前不得运行任何
上传或 promotion 命令，但后续纯代码切片可以继续。

### Commit intent

`feat: generate Lezhi expression candidates`

## 5. Slice 2 — Telegram Media Intake and Bounded Download

### Files

- `src/group_llm_agent/platforms/telegram.py`
- `src/group_llm_agent/media.py`
- `src/group_llm_agent/events.py`
- `tests/test_telegram_adapter.py`
- `tests/test_telegram_client.py`
- `tests/test_media.py`

### Changes

- normalize photo、static document、static sticker、caption 和 media-only；
- 拒绝动画/video sticker、动态图片和不支持 MIME；
- `get_file` 返回严格校验的相对 `file_path`；
- download 采用 token-redacted URL、有界读取和分类异常；
- Pillow verify、像素/尺寸限制、EXIF 归一化、缩放和去 metadata 重编码；
- 成功/失败都释放原始字节，不创建持久临时文件。

### Checks

- update fixture 正/负矩阵；
- 声明超限不联网、流式超限多读一字节、路径穿越拒绝；
- timeout/open/read/decode 错误均为 redacted category；
- token、file_id、file_path 不出现在异常/repr/捕获日志；
- 图片炸弹、损坏、错误 MIME 和 EXIF 回归。

### Commit intent

`feat: ingest bounded Telegram static media`

## 6. Slice 3 — Vision Provider and Trigger-After-Eligibility Flow

### Files

- `src/group_llm_agent/vision.py`
- `src/group_llm_agent/model.py`
- `src/group_llm_agent/context.py`
- `src/group_llm_agent/trigger.py`
- `src/group_llm_agent/runtime.py`
- `src/group_llm_agent/app.py`
- `src/group_llm_agent/config.py`
- `tests/test_vision.py`
- `tests/test_model_client.py`
- `tests/test_trigger.py`
- `tests/test_runtime.py`

### Changes

- 新增独立 `VisionModelPort` 和 OpenAI-compatible 图片内容请求；
- 严格解析 `VisionEvidence`，应用侧拦截身份/敏感/诊断/定位声明；
- known enabled sticker 直接使用目录语义，不调用视觉模型；
- unknown media 只有 effect request 已产生后才下载/调用视觉；
- 将视觉证据以不可信块加入 Writer context，不进入 recognition；
- 配置 capability、model、download/pixel/timeout，默认 disabled；
- 失败按 direct/contextual 和 caption 充分性降级。

### Checks

- 无寻址媒体为零下载/零视觉；
- reply/name/continuity 媒体可进入视觉；
- OCR/截图注入、身份/敏感推断、损坏/超时；
- provider payload 包含图片而日志/DB 不包含图片或完整 response；
- 真实配置 provider 做一组有限图片 probe。

### Commit intent

`feat: add qualified image understanding`

## 7. Slice 4 — Sticker Decision and Adaptive 0/3/5 Loop

### Files

- `src/group_llm_agent/expression.py`
- `src/group_llm_agent/model.py`
- `src/group_llm_agent/effector.py`
- `src/group_llm_agent/tools.py`
- `src/group_llm_agent/config.py`
- `tests/test_expression.py`
- `tests/test_model_client.py`
- `tests/test_effector.py`
- `tests/test_tools.py`

### Changes

- Writer schema 增加 `sticker` 和 allowlist `mood_signal`；
- prompt 只暴露当前目录文本语义，不暴露 Telegram mapping；
- final validator 重查 persona/catalog/entry digest 和关系/禁用场景；
- model/tool budget 改为 6/3/5；
- 第 4–5 次强制合法 extension reason 和 novel successful result；
- 失败/协议/无结果均计数，达到 5 后工具从 schema 中消失；
- 审计预算序号、扩展原因和 novelty；
- 加入固定表情适用/必须文字评审集和 50%–70% verifier。

### Checks

- 0、1–3、4–5、第 6 次、失败与重复工具矩阵；
- unknown/raw file ID/version/digest/disabled/relationship 拒绝；
- 同 sticker 连续重复拒绝，严肃/事实文本禁止 sticker-only；
- 评审集频率、必须文字和角色约束；
- 现有 Writer/trigger/recognition provider contract 不回归。

### Commit intent

`feat: add expressive sticker decisions and adaptive tools`

## 8. Slice 5 — Single External Effect Sticker Delivery

### Files

- `src/group_llm_agent/platforms/telegram.py` or split multipart client
- `src/group_llm_agent/runtime.py`
- `src/group_llm_agent/runs.py`
- `src/group_llm_agent/messages.py`
- `tests/test_telegram_client.py`
- `tests/test_runtime.py`
- `tests/test_conversation_trigger_runtime.py`

### Changes

- `send_sticker(file_id)` 与 reply parameters；
- 发送前最后一次目录重载/摘要校验；
- 同一 external claim 记录 sticker 成功或明确失败后的文本成功；
- timeout/transport/invalid response 标记 uncertain 且不降级；
- confirmed failure 最多一次安全文本；
- outbound scene 记录语义占位文本而不是 asset ID；
- 聚合 sticker eligible/selected/sent/degraded/repeated 指标，不存正文。

### Checks

- 文字/sticker/静默互斥；
- pre-claim crash 可重算，post-claim replay 不重发；
- definite failure 一次 fallback，uncertain 零 fallback；
- success message/file identity 和目录映射一致；
- 批量 update 与 continuity 不引入因果倒置。

### Commit intent

`feat: deliver one validated sticker effect`

## 9. Slice 6 — Operator Upload and Avatar Controller

### Files

- `src/group_llm_agent/avatar.py`
- `src/group_llm_agent/expression.py`
- `src/group_llm_agent/platforms/telegram.py` or multipart client
- `src/group_llm_agent/__main__.py`
- `deploy/manage.sh`
- `tests/test_avatar.py`
- `tests/test_expression_manage.py`
- `tests/test_persona_manage.py`

### Changes

- candidate promotion 命令要求精确目录/批准摘要；
- `uploadStickerFile`、create/update set 和 mapping carrier；
- 真实抽样发送完成后才允许 `telegram_ready`；
- 头像 apply 前保存当前头像或 none，JPG multipart 更新后读取验证；
- 默认头像、冷却、滚动 7 天、稳定心情、全局作用域和 auto-disabled；
- deployment lock 覆盖 apply/verify/rollback，HUP/INT/TERM 走同一回滚；
- Writer 和群消息没有任何调用这些命令的 capability。

### Checks

- 所有 promotion 状态机和摘要错配负例；
- fake Telegram multipart 协议和响应校验；
- 未确认头像、单消息 mood、<72h、7d 两次、跨 scope 拒绝；
- apply/verify 各阶段普通失败与信号失败，旧头像/none 精确恢复；
- 锁在终态前不释放，失败记录 attempted/succeeded/failed。

### User gate

只有用户明确确认 Slice 1 的预览/目录/心情映射后，才运行本切片的真实上传、头像 apply 和
auto-rotation enable；代码与 fake tests 可提前完成。

### Commit intent

`feat: manage approved stickers and bot avatar`

## 10. Slice 7 — Integration, Verification and Release Carrier

### Files

- `deploy/.env.example`
- `deploy/compose.yaml`
- `deploy/README.md`
- `README.md`
- `CHANGELOG.md`
- `docs/feature/lezhi-sticker-expression-v0-3/verification.md`
- package-data configuration and full test suite

### Required proof

- compileall and full unittest discovery；
- Ruff check/format and Mypy；
- migration from v1/v2 fixtures；
- wheel/sdist content and isolated entry point；
- deterministic candidate rebuild and exact digest；
- credential/private-key/media-binary leakage scan；
- Compose render and Docker image build/run；
- candidate-disabled startup preserves current text behavior；
-真实 vision provider probe；
- 用户确认后的 sticker upload/representative send；
- 用户确认后的默认头像 apply/readback/rollback rehearsal；
- 目标群图片/sticker/text UAT 和单效果审计。

### Verification carrier

`verification.md` 逐项记录命令、精确 commit/image/manifest/catalog 摘要、通过结果、未执行原因和
剩余运营限制。真实 provider body、完整 prompt、群消息正文、媒体和凭据不进入 carrier。

### Commit intent

`docs: verify Lezhi expression v0.3`

## 11. Execution Order and Stop Conditions

1. Slice 0 contract/migration；
2. Slice 1 候选生成并向用户展示，同时继续纯代码 Slice 2–6；
3. Slice 2/3 媒体与视觉；
4. Slice 4/5 Writer 与单效果交付；
5. Slice 6 operator/头像代码和 fake proof；
6. 用户确认候选后执行真实 upload/avatar 外部写入；
7. Slice 7 完整验证、PR 和独立评审。

立即停止并回到 Requirements 的情况：素材摘要发生变化、用户要求组合文字+sticker、动态媒体、
Writer 直接头像写入、多 bot/多租户全局心情，或生产候选范围不再是已确认 48 枚/明确子集。

只停止外部写入而继续本地工作的情况：用户尚未确认预览、Telegram/model 暂时不可达、权限
不足、目标群不可用。所有这些都必须作为未完成验证记录，不能被 fake proof 代替。
