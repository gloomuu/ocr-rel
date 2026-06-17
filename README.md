# ocr-rel

售电公司注册资料 **AI 识别系统（贵方）**。负责接收识别请求、下载 PDF、OCR 识别、回调结构化结果。

## 功能概览

- 生产接口：`POST /api/v1/recognize`
- 测试页面：`GET /test`（模拟业务侧：提交识别 → 进度轮询 → 查看回调 → 历史任务）
- OCR 双引擎：`paddle` / `aliyun`（配置切换）
- 结构化抽取：**方案 A**（OCR 文本 → 大模型 → JSON），regex 兜底
- 任务持久化：SQLite 存储任务进度与回调结果，支持历史查询
- Phase 1 支持附件：`type=1` 营业执照、`type=2` 法人身份证、`type=3` 审计报告（首页抽封面字段 + 分页定位资产负债表）

## 项目结构

```
src/ocr_rel/
├── api/              # HTTP 路由
├── clients/          # 注册平台下载/回调客户端
├── models/           # Pydantic 模型
├── ocr/              # PaddleOCR / 阿里云 OCR
├── llm/              # 大模型结构化抽取（方案 A）
├── parsers/          # regex 兜底解析
├── pdf/              # PDF 转图片
├── services/         # 识别任务编排
├── db/               # SQLite 持久化
├── static/           # 测试页面
└── tasks/            # asyncio 后台任务
```

## 本地开发

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

uvicorn ocr_rel.main:app --reload --host 0.0.0.0 --port 8000
```

访问：

- 健康检查：http://localhost:8000/health
- 测试页面：http://localhost:8000/test
- API 文档：http://localhost:8000/docs

## 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `OCR_ENGINE` | `paddle` 或 `aliyun` | `paddle` |
| `LOG_FILE_ENABLED` | 是否输出日志文件 | `true` |
| `LOG_DIR` | 日志目录 | `logs` |
| `EXTRACTION_STRATEGY` | `llm` 或 `regex` | `llm` |
| `LLM_API_KEY` | 大模型 API Key（OpenAI 兼容） | - |
| `LLM_BASE_URL` | 大模型 API 地址 | DashScope 兼容地址 |
| `LLM_MODEL` | 模型名称 | `qwen-plus` |
| `LLM_FALLBACK_TO_REGEX` | LLM 失败时是否 regex 兜底 | `true` |
| `ALIYUN_ACCESS_KEY_ID` | 阿里云 OCR AK | - |
| `ALIYUN_ACCESS_KEY_SECRET` | 阿里云 OCR SK | - |
| `PLATFORM_BASE_URL` | 注册平台地址 | `http://localhost:8080` |
| `PLATFORM_CALLBACK_ENABLED` | 是否发送回调 | `false` |
| `AUTH_ENABLED` | 接口鉴权开关 | `false` |
| `AUTH_USERNAME` | 登录用户名 | - |
| `AUTH_PASSWORD` | 登录密码 | - |
| `AUTH_SECRET_KEY` | 鉴权秘钥；`token = MD5(username + password + secret_key)` | - |
| `API_KEY` | 兼容旧方式，可作为 `token` 请求头传入 | - |
| `DATABASE_PATH` | SQLite 数据库路径 | `data/ocr-rel.db` |
| `MAX_CONCURRENT_TASKS` | 并发识别任务上限，超出排队等待 | `2` |
| `TEST_PAGE_DEFAULT_OCR_ENGINE` | 测试页默认 OCR 引擎 | `aliyun` |
| `UPLOAD_STORAGE_PATH` | 上传文件本地存储目录 | `data/uploads` |
| `MAX_UPLOAD_FILE_SIZE` | 单文件上传大小上限（字节） | `10485760`（10MB） |
| `MAX_STORED_FILES` | 本地保留的上传文件数量，超出删除最早文件 | `100` |

## 并发与排队

识别任务在后台异步执行。通过 `MAX_CONCURRENT_TASKS` 限制同时运行的任务数；当执行槽位已满时，新任务进入排队（stage=`queued`），有空闲后自动开始处理。

`/health` 返回当前队列状态：`maxConcurrent`、`running`、`waiting`、`available`。

## 任务持久化与历史查询

任务状态、处理步骤、回调结果写入本地 SQLite（默认 `data/ocr-rel.db`）。服务重启后数据保留。

| 接口 | 说明 |
|------|------|
| `GET /api/v1/tasks` | 分页列出历史任务（支持 `registrationId` 筛选） |
| `GET /api/v1/tasks/{taskId}` | 查询任务详情（含 steps、result） |
| `GET /api/v1/tasks/{taskId}/callback` | 获取回调格式结果（仅 success 任务） |
| `GET /api/v1/tasks/{taskId}/file` | 预览本地保留的原始附件（PDF / 图片） |

测试页 `/test` 底部「调用历史」面板可浏览历史任务，点击文件名预览附件，点击「查看回调」查看识别结果。

上传文件会保存到 `UPLOAD_STORAGE_PATH`（默认 `data/uploads`），单文件不超过 `MAX_UPLOAD_FILE_SIZE`（默认 10MB），本地最多保留 `MAX_STORED_FILES`（默认 100）个文件，超出时自动删除最早的文件。

Docker 部署时 `./data` 目录已挂载为数据卷（含 SQLite 与上传文件），请确保有写权限。

## 生产接口

### 提交识别请求

`POST /api/v1/recognize`

```json
{
  "registrationId": "reg-001",
  "files": [
    {
      "type": 1,
      "name": "营业执照",
      "files": [{ "uuid": "temp-file-uuid" }]
    }
  ]
}
```

响应：

```json
{
  "code": 0,
  "message": "accepted",
  "data": { "taskId": "..." }
}
```

识别完成后回调注册平台 `/api/ai/result/callback`（需开启 `PLATFORM_CALLBACK_ENABLED=true`）。

## 结构化抽取（方案 A）

```
PDF/图片 → OCR → 纯文本 → 大模型(JSON Schema Prompt) → 字段校验/标准化 → callback
                              ↓ 失败或未配置
                         regex 规则兜底
```

配置 `EXTRACTION_STRATEGY=llm` 且设置 `LLM_API_KEY` 后生效。支持 OpenAI 兼容接口（如阿里云 DashScope）。

## 测试接口

- `POST /api/v1/test/recognize` — **模拟业务侧**提交识别（uuid + 本地文件映射）
- `GET /api/v1/test/tasks/{taskId}` — 查询任务进度与状态
- `POST /api/v1/test/parse` — 直传解析（兼容旧接口）
- `GET /api/v1/test/supported-types` — 当前支持的 type 列表

历史任务与回调结果请使用 `GET /api/v1/tasks` 系列接口（见上文）。

## 容器化部署

```bash
cp .env.example .env
docker compose up --build -d
docker compose logs -f app
```

## 测试

```bash
pytest
```
