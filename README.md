# AI 客服助手 MVP

一个本地运行的最小版本：粘贴客服聊天记录，由大模型返回 Pydantic
结构化分析；结果先供人工审阅，只有点击确认后才写入 PostgreSQL。

## 功能

- `POST /api/analyze`：结构化识别意图、任务、状态、优先级、截止时间、
  情绪、风险和建议回复
- `POST /api/tasks/confirm`：人工确认后保存任务
- `GET /api/tasks`：查询已确认任务
- `GET /api/memories`：查询会话中未完成或延期的长期记忆
- `PATCH /api/memories/{id}`：更新记忆状态或恢复处理时间
- `PATCH /api/tasks/{id}`、`DELETE /api/tasks/{id}`：编辑和删除任务
- `/api/customers`：客户资料的新增、查询、编辑和删除
- `/api/reminders`：到期任务与延期事项提醒
- `POST /api/reminders/scan`：立即执行一次到期扫描
- `GET /api/dashboard`：任务、风险、提醒、延期记忆和客户统计
- `/api/calendar/events`：内部日历事件的新增、查询、编辑和删除
- `/api/conversations`：统一管理微信、邮件、在线客服和网页会话
- `/api/conversations/{id}/messages`：多轮消息历史和发送
- `/api/ws/conversations/{id}`：WebSocket 实时聊天
- `/api/inbound/wechat`、`/api/inbound/support`：外部消息 Webhook
- `/api/conversations/{id}/attachments`：附件上传、列表和下载
- `/`：简单 HTML 测试页面
- `/docs`：FastAPI Swagger 文档

本阶段未集成 Dify、n8n、Chatwoot、Redis 或日历系统。

## Windows 本地启动

前置条件：Python 3.12、Docker Desktop，PowerShell。

1. 启动 PostgreSQL 和 Redis：

   ```powershell
   docker compose up -d db redis
   ```

2. 创建虚拟环境并安装依赖：

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements-dev.txt
   ```

   如果 PowerShell 阻止激活，可先在当前窗口执行：

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   ```

3. 创建本地配置：

   ```powershell
   Copy-Item .env.example .env
   ```

   编辑 `.env`，至少填写 `OPENAI_API_KEY`。`OPENAI_MODEL` 可按账号可用模型
   调整；如使用 OpenAI 兼容网关，可填写 `OPENAI_BASE_URL`，但该网关必须支持
   Chat Completions 的结构化输出。

4. 执行数据库迁移：

   ```powershell
   alembic upgrade head
   ```

5. 启动应用：

   ```powershell
   uvicorn app.main:app --reload
   ```

6. 浏览器访问 <http://127.0.0.1:8000>。

### Windows 自动启动

如果希望关闭 Codex 或终端后仍可访问，可把
`scripts/run_local_server.ps1` 注册为 Windows 登录任务。该脚本每 15 秒检查一次
`/health`，服务退出后会自动重启；日志保存在 `data/logs/local-server.log`。

Docker Compose 也包含 `web` 服务，网络可访问 Docker Hub 时可执行：

```powershell
docker compose up -d --build web
```

`web`、PostgreSQL 和 Redis 均配置了持续运行或自动重启。

## 运行测试

测试使用内存数据库和假的大模型服务，不消耗 API 配额：

```powershell
pytest -q
```

测试覆盖至少五类聊天：待办、办理中、已完成、投诉风险和无任务聊天，
并验证确认保存、列表查询及无任务不可确认。

## 配置项

| 变量 | 说明 |
|---|---|
| `DATABASE_URL` | SQLAlchemy PostgreSQL 连接串 |
| `OPENAI_API_KEY` | 大模型 API 密钥 |
| `OPENAI_MODEL` | 支持结构化输出的模型名 |
| `OPENAI_BASE_URL` | 可选的兼容 API 地址 |
| `APP_NAME` | 应用名称 |
| `APP_ENV` | 运行环境标识 |
| `REMINDER_SCAN_INTERVAL_SECONDS` | 后台到期扫描间隔，默认 60 秒 |
| `REDIS_URL` | Redis 连接地址，默认 `redis://localhost:6379/0` |
| `WEBHOOK_SHARED_SECRET` | 微信和在线客服 Webhook 共享密钥 |
| `UPLOAD_DIR` | 附件存储目录，默认 `data/uploads` |
| `MAX_UPLOAD_BYTES` | 单个附件大小上限，默认 10MB |
| `EMAIL_IMAP_ENABLED` | 是否启动邮件自动收取 |
| `EMAIL_IMAP_HOST` | IMAP 服务器地址 |
| `EMAIL_IMAP_PORT` | IMAP SSL 端口，默认 993 |
| `EMAIL_IMAP_USERNAME` | 邮箱账号 |
| `EMAIL_IMAP_PASSWORD` | 邮箱密码或应用专用密码 |
| `EMAIL_IMAP_FOLDER` | 收件文件夹，默认 `INBOX` |
| `EMAIL_POLL_INTERVAL_SECONDS` | 邮件轮询间隔，默认 60 秒 |

密钥只从 `.env`/环境变量读取，`.env` 已加入 `.gitignore`。

## 数据流

浏览器先调用 `/api/analyze`。服务端通过 OpenAI SDK 的 Pydantic
`response_format` 请求模型，响应必须通过 `AnalysisResult` 校验。
浏览器展示响应；用户确认后才将同一结构连同原始聊天发送至
`/api/tasks/confirm` 并保存。

页面中的“会话编号”用于隔离不同客户或工单的记忆。分析时，服务端会召回
该会话尚未完成的 `pending`/`deferred` 记忆并交给模型参考；用户确认任务
后才写入新记忆。“稍后再做”等事项保存为 `deferred`，可带 `resume_at`，
完成后可在页面中标记完成，后续分析不再召回。

## 自动提醒与管理功能

应用启动后会在后台定时扫描 PostgreSQL：

- 截止时间已到、状态不是 `completed` 的任务会生成提醒；
- `deferred` 且 `resume_at` 已到的记忆会生成恢复处理提醒；
- 同一任务或记忆只生成一条提醒，避免重复通知；
- 任务或记忆标记完成后，关联提醒自动关闭。

提醒目前显示在本地 Web 工作台中，不发送邮件、短信或日历通知。单机 MVP
使用 FastAPI 进程内扫描器；生产环境多实例部署时应迁移到独立调度服务。

工作台还支持客户资料 CRUD、任务编辑与删除，以及任务状态、逾期、高风险、
提醒、延期记忆和客户数量统计。

## Redis 与日历

Redis 用于：

- 多进程或多实例之间的提醒扫描分布式锁；
- 统计仪表盘的短时缓存；
- 连接失败时自动熔断并降级到 PostgreSQL，不影响核心业务。

内置日历使用 PostgreSQL 持久化：

- 有截止时间的未完成任务自动同步为日历事件；
- 有恢复时间的延期记忆自动同步为日历事件；
- AI 根据聊天上下文自动总结日历标题；
- 明确日期时间优先，支持“明天、下周一”等相对时间推导；
- 没有明确时间时按优先级建议合理处理时间，并记录时间依据；
- 修改或完成任务、记忆时自动更新或移除对应事件；
- 支持手动日历事件的新增、编辑、删除和时间范围查询。

当前日历是应用内部日历，尚未连接 Google Calendar、Outlook Calendar 或
企业日历账号。

## 多渠道消息与附件

消息中心把不同渠道统一保存到 `conversations`、`messages` 和
`attachments` 表：

- 微信和在线客服平台将消息转换为 README 所示的 JSON 后调用对应 Webhook；
- Webhook 使用 `X-Webhook-Token` 校验，并按渠道和外部消息 ID 去重；
- 邮件连接器通过 IMAP SSL 定时读取 `UNSEEN` 邮件；
- 浏览器通过 WebSocket 实时收发消息，同时保留完整历史；
- 支持 JPG、PNG、GIF、WebP、PDF、TXT、CSV、DOCX 和 XLSX；
- 文件采用随机存储名，限制大小并拒绝不在白名单中的类型；
- `.env`、附件目录和本地凭据均不会提交到 GitHub 或复制进 Docker 镜像。

Webhook 请求示例：

```powershell
$headers = @{
  "Content-Type" = "application/json"
  "X-Webhook-Token" = "你的 WEBHOOK_SHARED_SECRET"
}
$body = @{
  external_conversation_id = "customer-openid"
  external_message_id = "platform-message-id"
  sender_id = "customer-openid"
  sender_name = "客户"
  content = "我的订单什么时候发货？"
  subject = "订单咨询"
} | ConvertTo-Json
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/inbound/wechat `
  -Headers $headers -Body $body
```

微信公众平台、企业微信和第三方在线客服的原始回调格式各不相同；生产接入时
需要在平台侧配置回调 URL，并将其字段映射到上述统一 JSON。没有平台凭据时，
可以直接在本地消息中心使用 `web` 渠道和 WebSocket 测试完整流程。

## 上下文记忆、自动回复与转人工

消息中心现在支持按会话启用 AI 自动回复。默认关闭，避免尚未完成平台和业务 API
配置时误发消息。选中会话后可在页面切换“机器人接待”“等待人工”和“人工接待中”。

客户主动发送消息后，系统执行以下流程：

1. 按外部消息 ID 保存并去重；同一条入站消息只处理一次。
2. 选取最近消息，并按当前问题关键词召回较早的相关消息。
3. 合并会话滚动摘要、客户资料、未完成任务和延期记忆。
4. 使用 `AutoReplyDecision` Pydantic 结构要求模型返回回复、风险、转人工判断和新摘要。
5. 低风险且信息充分时生成一条与入站消息关联的机器人回复。
6. 投诉、人工请求、高风险、业务事实不足或模型异常时停止自动回复并转人工。

机器人回复通过 `messages.reply_to_message_id` 与客户消息一一对应，并由数据库唯一索引
保证并发请求也不会重复回复。会话进入 `pending` 或 `human` 后会持续锁定自动回复，
直到客服在工作台手动切回 `bot`。

管理与排查接口：

- `PATCH /api/conversations/{id}`：设置 `automation_enabled`、`handoff_status` 和原因。
- `POST /api/conversations/{id}/messages/{message_id}/process`：手动处理一条客户消息；
  已经处理过时返回原结果，不重复调用模型。
- `GET /api/conversations/{id}/messages`：查看处理状态和回复关联。

相关配置：

| 变量 | 说明 |
|---|---|
| `AUTO_REPLY_DEFAULT_ENABLED` | 新会话是否默认自动回复，建议生产初期保持 `false` |
| `AUTO_REPLY_RECENT_MESSAGES` | 固定召回的最近消息数量 |
| `AUTO_REPLY_RELEVANT_MESSAGES` | 额外召回的关键词相关历史数量 |
| `AUTO_REPLY_MAX_CONTEXT_CHARS` | 发送给模型的最大上下文字符数 |
| `AUTO_REPLY_RISK_HANDOFF_LEVELS` | 强制转人工的风险等级，默认 `high,critical` |

当前微信和在线客服 Webhook 会自动执行上述流程，并把 AI 回复写入统一消息记录及实时
WebSocket。正式接入微信或企业微信后，平台适配器还需要将这条回复调用相应平台发送 API
发给客户；模型不会绕过平台适配器直接向外发送。
