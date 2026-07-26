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
- `/`：简单 HTML 测试页面
- `/docs`：FastAPI Swagger 文档

本阶段未集成 Dify、n8n、Chatwoot、Redis 或日历系统。

## Windows 本地启动

前置条件：Python 3.12、Docker Desktop，PowerShell。

1. 启动 PostgreSQL：

   ```powershell
   docker compose up -d db
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
