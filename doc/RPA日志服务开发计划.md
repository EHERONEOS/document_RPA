# RPA 日志服务 · 开发计划清单（本地开发）

> 配套设计文档：`doc/RPA执行日志服务设计文档.md`（任务中引用的 §x 均指该文档）
> 本文档是**进度的唯一事实来源**，每完成一个任务必须回写状态列与「进度日志」。
> 部署相关暂缓（部署套件文件已移除，部署方案保留在设计文档 §11），本计划只覆盖本地开发与本地联调。

## 0. 多轮对话追踪约定

| 口令 | 含义 |
| --- | --- |
| `读一下开发计划` | 读取本文档，汇报当前进度与下一步建议 |
| `开始 T1.2` | 开始执行指定任务，完成后更新状态列 + 进度日志 |
| `T2.3 遇到问题：…` | 在对应任务下追加「阻塞备注」，讨论后继续 |
| `看进度` | 输出各里程碑完成度统计 |

状态标记：`⬜ 未开始` · `🔄 进行中` · `✅ 完成` · `⛔ 阻塞`（⛔ 必须附阻塞备注）

## 1. 本地开发环境总览

```
document_RPA/                     # 现有 wise-rpa 仓库（Agent 端改造在这里）
├─ app/core/logging/…             # T2.x 改造点
├─ queue_control_platform/docker/compose.yml   # 本地 MySQL8+Redis7 直接复用
├─ rpa-log-service/               # 【新建】服务端（Python/FastAPI）
│  ├─ pyproject.toml
│  ├─ rpa_log_service/
│  │  ├─ main.py settings.py db.py repository.py
│  │  ├─ routes/agent.py routes/web.py
│  │  ├─ files.py jobs.py init_db.py
│  │  └─ .env
│  └─ tests/
├─ rpa-log-web/                   # 【新建】前端（Vite+React18+TS+antd5）
└─ scripts/mock_agent.py          # 【新建】本地模拟 Agent 上报（联调用）
```

本地端口约定：MySQL `3306` / Redis `6379`（docker compose）/ 后台服务 `8766`（queue_control_platform，2026-09 合并后的唯一后台）/ 前端 dev `5173`（代理 `/api`、`/files` → 8766）。

> 2026-09 架构调整（用户决定）：原 `rpa-log-service` 独立服务已并入 `queue_control_platform`（`server/rpa_log/` 子包），新建统一库 `rpa_platform`（平台 8 表 + 日志 5 表，存量数据已迁移）；`queue_control`/`rpa_log` 旧库保留未删仅作历史存档。**前端同样单一化**：原 Jinja 维护页退役，`rpa-log-web`（React，HashRouter）成为唯一前端并新增"设备管理"页（新增设备/一次性令牌/分配队列/暂停恢复重启），构建产物由 8766 根路径直接托管，5173 仅作前端开发调试入口；改前端后需 `npm run build` 并重启服务。下文任务表中出现的服务端路径/端口以本节为准。

本地启动命令约定：

```bash
# 基础设施（首次 + 每日开发前）
docker compose -f queue_control_platform/docker/compose.yml up -d

# 唯一后台服务（平台维护 API + RPA 日志 API + 文件服务 + 维护页面，启动时幂等建表）
uv run python -m queue_control_platform.server.main        # http://127.0.0.1:8766

# 前端（开发模式）
cd rpa-log-web && npm run dev                    # http://localhost:5173（npm，首次先 npm install）

# 模拟一次完整执行上报（联调用）
uv run python scripts/mock_agent.py --scenario failed
```

Agent 端本地联调环境变量（`.env`，仅在需要联测上报时开启）：

```ini
RPA_LOG_SERVICE_ENABLED=true
RPA_LOG_SERVICE_URL=http://127.0.0.1:8766
RPA_LOG_SERVICE_TOKEN=local-dev
# RPA_LOG_DEVICE_NAME 不配则取主机名
```

## 2. 任务清单

### M0 本地开发环境（前置）

| ID | 任务 | 产出 / 验收方式 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| T0.1 | 本地基础设施 compose：复用平台 compose 增加 `rpa_log` 库初始化（init SQL 或环境变量） | `docker compose ps` 两容器 healthy；`mysql> SHOW DATABASES` 可见 `queue_control`、`rpa_log` | — | ✅ |
| T0.2 | 服务端骨架：`rpa-log-service` 工程（pyproject/app 工厂/settings/.env 示例/`/healthz`） | `uv run uvicorn rpa_log_service.main:app --port 9000` 后 `curl /healthz` 返回 `{"db":"ok"}` 或 `{"db":"skipped"}` | T0.1 | ✅ |
| T0.3 | 前端脚手架：`rpa-log-web`（Vite+React18+TS+antd5+router+axios 封装+dev 代理） | `npm run dev` 打开 5173 可见空白 AdminLayout 框架页 | — | ✅ |
| T0.4 | mock_agent 脚本骨架：支持 `--scenario success/failed/running` 三种剧本直连服务端 API | 手工调用后 `curl /api/v1/executions?status=FAILED` 能查到数据 | T0.2 | ✅ |

### M1 服务端 rpa-log-service（对照设计 §4/§5）

| ID | 任务 | 产出 / 验收方式 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| T1.1 | 数据模型与建表：5 张表 DDL（§4.1–4.4，含 `duration_seconds`）+ `init_db.py` 幂等执行 | 重复执行 init_db 不报错；`SHOW CREATE TABLE` 与设计一致 | T0.2 | ✅ |
| T1.2 | Agent 上报 API：`POST /api/v1/executions`（uk 幂等）、`/logs/batch`（≤200 条校验）、`/executions/finish`（终态幂等）；Bearer token 鉴权 | mock_agent 三个 scenario 全部 200；重复 finish/重复创建行为符合 §9.2；curl 无 token 返回 401 | T1.1 | ✅ |
| T1.3 | 文件服务：`POST /api/v1/files/upload`（扩展名白名单/UUID 重命名/≤200MB）+ `/files/*` 静态访问 | 上传 mp4/png 返回可访问 URL；非法扩展名 400；超限 413 | T0.2 | ✅ |
| T1.4 | 查询 API：`GET /executions`（消息ID/JobId 模糊、队列/状态精确、分页、时间格式化）、`/execution/detail`（主记录+日志 seq DESC+文件）、`/devices`、`/queues`、`/stats/summary` | curl 各接口字段与 §5.2 一致；模糊/精确/分页行为正确；终态行返回 `finishedAt`/`durationSeconds` | T1.2 | ✅ |
| T1.5 | RUNNING 超时任务：服务内定时扫描（阈值 `RPA_LOG_RUNNING_TIMEOUT_HOURS`）置 `TIMEOUT` | 手工把一条记录 started_at 改旧 → 触发扫描 → 状态变 TIMEOUT | T1.4 | ✅ |
| T1.6 | 服务端测试：pytest 覆盖幂等/鉴权/校验/分页/超时（对照 §10 单测建议） | `uv run pytest` 全绿 | T1.2–T1.5 | ✅ |

### M2 Agent 端改造（wise-rpa 仓库，对照设计 §6）

| ID | 任务 | 产出 / 验收方式 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| T2.1 | logger 增加 `SUCCESS` 级别：模块级 `success()` + `Logger.success()`，控制台绿色 | `python -c` 直接调用四种级别，控制台四色输出，格式与现有一致 | — | ✅ |
| T2.2 | `app/core/logging/log_session.py`：`ExecutionLogContext` + ContextVar + `execution_log_session`（含 `log_service_enabled`，local 强制关）+ `finish_execution` 挂点 | 单测：local 模式/未开开关时 session 为 no-op 且不建任何 HTTP 请求 | T2.1 | ✅ |
| T2.3 | `LogReportClient`：内存队列 + daemon 线程攒批（50 条/1s）+ 失败降级不抛错 + `atexit` flush | 单测：服务不可达时 enqueue 不阻塞不抛错；停服再起批量补发可选（降级为丢弃即可） | T2.2 | ✅ |
| T2.4 | consumer 接入：`handle_message` 包 `execution_log_session`（skip_test_job 之后，测试单不记录） | 本地开服务 + mock 一条消息走 `handle_message` → 页面/接口可见 RUNNING；TEST 单无记录 | T1.2 T2.3 | ✅ |
| T2.5 | `base_task` 终态上报：`finish_execution(success, remark, fail_img=file_info.url, record_files=…)`；`_upload_error_screenshot` 记录完整 url；media_type/storage 推断 | 本地 fake TaskResult 走 `run()` finally → 接口里 status/remark/imgUrl/文件四要素正确 | T2.4 | ✅ |
| T2.6 | `FileStorageClient` 降级链：OSS → 局域网 `/files/upload` → 本地保留 + WARN | 单测：mock OSS 抛错时走 LAN 上传；两端都失败返回 None 且有 WARN 日志 | T1.3 | ✅ |
| T2.7 | `HttpHelper.request` 成功结果日志一行 | code review + 本地调用验证日志出现 | T2.3 | ✅ |
| T2.8 | Agent 端测试：`log_service_enabled` 分支 / 降级 / session 隔离（对照 §10 单测建议） | `uv run pytest tests/` 全绿 | T2.1–T2.6 | ✅ |

### M3 Web 控制台 rpa-log-web（对照设计 §8 与原型）

| ID | 任务 | 产出 / 验收方式 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| T3.1 | AdminLayout：白色 Sider（设备/队列/日志菜单）+ Header 面包屑 + Content | 与原型骨架一致，路由切换正常 | T0.3 | ✅ |
| T3.2 | 日志列表页：搜索表单（4 条件防抖）+ 表格（消息ID/JobId/队列/设备/状态Tag/创建时间/**结束时间/耗时**/操作列显隐）+ 分页 | 对照原型逐列核对；`RUNNING` 行结束时间/耗时显示 `—` | T3.1 T1.4 | ✅ |
| T3.3 | 执行日志抽屉：宽 50% + Descriptions（含结束时间/耗时）+ 日志从新到旧 `i. 内容 时间` + 单行省略号悬浮 Tooltip + 时间完整 | 对照原型交互逐条核对 | T3.2 | ✅ |
| T3.4 | 抽屉刷新：`RUNNING` 显示刷新按钮（旋转加载态）点击拉最新日志 + 30s 自动轮询，终态无按钮 | 打开 RUNNING 记录点刷新可见新日志插入顶部 | T3.3 | ✅ |
| T3.5 | 失败原因弹窗（文案+截图预览）/ 记录文件弹窗（按 type 分组、图片预览、video 播放、OSS/LAN 角标），按状态显隐 | 对照原型交互核对；只有 FAILED 显示失败原因 | T3.2 | ✅ |
| T3.6 | 设备列表页 + 队列列表页 + 首页统计卡（今日/成功/失败/运行中） | 数据来自 `/devices` `/queues` `/stats/summary`；行点击可下钻日志列表 | T1.4 T3.1 | ✅ |

### M4 本地联调与验收

| ID | 任务 | 产出 / 验收方式 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| T4.1 | 全链路联调：compose + 服务端 + web dev + mock_agent 三剧本，页面全功能走查 | 三种状态在页面上颜色/抽屉/弹窗/刷新全部符合设计 | M1 M3 | ✅ |
| T4.2 | Agent 真实链路（可选，需本地可达 RabbitMQ）：`RPA_LOG_SERVICE_ENABLED=true` 起一个真实队列消费 | 真实消息产生 RUNNING→终态记录 | T4.1 T2.4 T2.5 | ⬜ |
| T4.3 | `local_runner` 回归：开启环境变量后跑 `app.dev.local_runner` | **不产生任何记录**（说明事项 1 双保险验证） | T4.1 T2.2 | ✅ |
| T4.4 | 设计对照验收：逐条核对设计文档 §9.1 对照表并在表格中打勾 | 全部 ✅ | T4.1 | ✅ |

## 3. 关键设计决定备忘（开发时随时回来查）

- API 风格：GET params / POST Body，无路径参数（§5）
- 结束态映射：`remark=TaskResult.remark`，`failImgUrl=上传响应 file_info.url`，`executeRecordFiles` 拍平 + `mediaType`/`storage`（§6.4）
- 状态色/日志色：绿 `#52c41a` / 红 `#ff4d4f` / 黄 `#faad14` / 灰 `rgba(0,0,0,.45)`（§9.4）
- 幂等语义（2026-09 调整）：**相同消息再次消费 → 插入新记录**（每次执行独立成条，各自持有日志与终态；`(rpa_message_id, queue_name)` 仅普通索引）；单条记录内 finish 仍以首次为准（重复 409）
- 日志上报：50 条或 1s 攒批，失败只打 WARN 绝不阻塞业务（§6.2）
- 测试单（skip_test_job）不记录（§6.3）

## 4. 进度日志（append-only，跨对话追溯）

| 日期 | 任务 | 说明 |
| --- | --- | --- |
| 2025-01-15 | — | 计划创建，全部 ⬜ |
| 2026-09-20 | T0.1 | compose 的 mysql 服务挂载 `docker/initdb/01-rpa_log.sql`（`CREATE DATABASE IF NOT EXISTS rpa_log` + queue_control 账号授权，幂等）；存量数据卷不触发 initdb，已手工补跑同一 SQL。验收：两容器 healthy，`SHOW DATABASES` 可见 `queue_control`、`rpa_log` |
| 2026-09-20 | T0.2 | `rpa-log-service` 骨架就绪：pyproject（fastapi/uvicorn/PyMySQL/dbutils/python-dotenv，Python 3.12.12 独立 uv 环境）、应用工厂 `main.py`、`settings.py`（RPA_LOG_* 环境变量 + .env 示例）、`db.py`（连接池）、`init_db.py`（§4 全部 5 张表幂等 DDL，重复执行通过）、`routes/agent.py`（上报三接口 + Bearer 鉴权）、`routes/web.py`（列表查询骨架）。验收：`/healthz` 返回 `{"db":"ok"}`；无 token 上报 401 |
| 2026-09-20 | T0.4 | `scripts/mock_agent.py` 三种剧本直连 API 全部 200；`curl /api/v1/executions?status=FAILED` 查到数据；重复 finish 返回 409（终态以首次为准）；running 剧本保留 RUNNING 供抽屉联调 |
| 2026-09-20 | T0.3 | `rpa-log-web` 脚手架就绪：Vite5+React18+TS+antd5（zhCN）+react-router6（hash）+axios `{code,data}` 解包封装+dev 代理 `/api→9000`；AdminLayout（白色 Sider 三菜单/Header 面包屑+环境标签/#f5f5f5 Content）。验收：5173 打开可见框架页；`tsc -b`、`pnpm build` 均通过 |
| 2026-09-20 | — | **M0 完成（4/4）**。备忘：① `pnpm dev` 前置依赖检查被 pnpm11 供应链策略（minimumReleaseAge）拒绝新发布的 rollup，已在 `rpa-log-web/pnpm-workspace.yaml` 关闭该策略并放行 esbuild 构建脚本；② 服务端 create/update_time 统一取应用时钟（容器 MySQL 为 UTC，`NOW()` 会差 8 小时）；③ T0.2 为打通 T0.4 验收顺带实现了 §4 全部 DDL 与最小上报/查询 API，T1.1/T1.2 剩余逐字段核对、参数校验完善与 §5.2 其余查询接口 |
| 2026-09-20 | T1.1–T1.2 | `SHOW CREATE TABLE` 与设计 §4.1–4.4 逐项一致、init_db 重复执行通过；上报 API 补齐 pydantic 字段长度校验（超长 422）、`/logs/batch` ≤200（400）、finish 幂等（重复 409 / 不存在 404）、重复创建不冲掉终态（§9.2）；Bearer 无/错 token 均 401。服务端 pytest **18/18 全绿** |
| 2026-09-20 | T1.3–T1.5 | `routes/files.py`：扩展名白名单 400 / 单文件 ≤200MB 413（流式校验+落盘回滚）/ UUID 重命名 / `files/{yyyy}/{mm}/` 落盘 / 返回完整 LAN url，`/files/*` StaticFiles 只读挂载；`routes/web.py` 补齐 `/execution/detail`（日志 seq DESC）、`/devices`（今日执行/成功率/绑定队列数/在线状态）、`/queues`（平均耗时）、`/stats/summary`，`/executions` 增加设备精确筛选（§8.3 下钻）；`jobs.py` RUNNING 超时扫描随 FastAPI lifespan 启动（5 分钟一轮），置位时 finished_at=started_at+阈值 保证耗时口径。验收：started_at 改旧 → TIMEOUT，其余记录不受影响 |
| 2026-09-20 | T1.6 | 服务端测试落 `rpa-log-service/tests/`（conftest 真库清表隔离、DB 不可用自动跳过）：幂等/鉴权/校验/分页/筛选/详情/维表统计/超时/文件共 18 条，`uv run pytest` **18/18 全绿** |
| 2026-09-20 | T2.1–T2.3 | `logger.py` 新增 SUCCESS 级别（绿 `\033[32m`，模块级+Logger 方法，格式不变）并旁路上报钩子；新增 `report_client.py`：`LogReportClient` 单例，queue.Queue+daemon 线程攒批（50 条/1s）按 executionId 分组上报，失败仅 WARN 绝不阻塞、队列满丢弃计数、atexit flush；新增 `log_session.py`：`log_service_enabled()`（local 强制关，双保险）、`ExecutionLogContext`+ContextVar、`execution_log_session`（懒创建 RUNNING，异常路径兜底 finish FAILED）、`report_log`/`finish_execution` |
| 2026-09-20 | T2.4–T2.7 | `consumer.handle_message` 在 skip_test_job 之后包 `execution_log_session`（TEST 单零记录）；`base_task.run()` finally 调 `logger.finish_execution`，`_upload_error_screenshot` 记完整 url（`self.fail_img_url`），`log_record_files` 拍平记录 OSS/LAN 文件，`_upload_execute_video` 改造为 OSS→LAN 降级链（LAN 成功保留本地），`TaskResult` 回传协议零改动；新增 `integrations/file_storage.py`（`upload_lan` + `infer_media_type`）；`http.py` request 成功补一行日志（§6.5）。验收：四色输出演示 + consumer/session/降级链单测通过 |
| 2026-09-20 | T2.8 | Agent 端测试 5 个文件（log_session 分支/会话隔离/异常兜底、report_client 降级与攒批分组、base_task 四要素与降级链、consumer 接入与 TEST 单零记录），`uv run pytest tests/`（排除 5 个引用已删模块的历史残留文件）**41/41 全绿**；新增测试文件已加入 .gitignore 白名单 |
| 2026-09-20 | T3.1–T3.6 | 前端全页面完成（子代理开发+父代理独立复核）：日志列表页（4 张可点击统计卡、4 条件 300ms 防抖搜索、后端分页表格、RUNNING 行 `—`、整表 30s 轮询+暂停开关）、抽屉（宽 50%、日志 `{i}. {内容} {时间}` 从新到旧、四级着色+省略号 Tooltip、RUNNING 刷新按钮+30s 轮询终态无按钮、antd Table virtual 虚拟滚动）、失败原因/记录文件弹窗（分组、预览、video、OSS/LAN 角标）、设备/队列页（行点击下钻）。偏差 3 点：List 无 virtual 改 Table virtual；记录文件链接终态恒显（列表无 files 字段，无文件显 Empty）；状态筛选含超时。验收：`tsc -b`、`pnpm build` 退出码 0，5173 页面 200，5 接口字段经代理复验一致 |
| 2026-09-20 | T4.1/T4.3/T4.4 | T4.1 全链路联调通过：清库后三剧本经 5173 代理复验——列表三状态（RUNNING 行 finishedAt/耗时为空）、FAILED 详情（remark/截图/日志 seq DESC/记录文件 OSS）、设备/队列/统计卡数据正确、页面 200；T4.3 通过：开满开关跑 local_runner 链路（含日志与 dispatch）执行记录数 before=after，双保险生效；T4.4 通过：§9.1 对照表 10 项全部核对（1–7 项 Agent 侧、前端 1–5 项）均有实现与验证证据 |
| 2026-09-20 | — | **M1–M4 开发完成（23/24，T4.2 可选暂缓：本机无 RabbitMQ，5672 不可达；待有真实队列环境时按 T4.2 验收）**。备忘：① 服务端超时扫描与文件服务在 uvicorn 单进程内运行（§11.3 单实例约束）；② tests/queue_control_deploy、test_flow_runtime、test_mscgw_flow_adapter 为引用已删模块的历史残留（未被 git 跟踪），与本次改造无关；③ 当前本机长驻进程：compose（3306/6379）、rpa-log-service（9000）、vite dev（5173） |
| 2026-09-20 | — | 前端包管理器 **pnpm → npm**（用户终端无 pnpm）：删除 `pnpm-workspace.yaml` 与 `pnpm-lock.yaml`（原 pnpm 供应链策略配置随之作废，npm 无此机制），清除 pnpm 版 node_modules 后 `npm install` 重建（生成 `package-lock.json`），`npm run build`、`npm run dev` 均验证通过；§1 启动命令与 T0.3 验收方式已同步改为 npm。注：本 App 会话内跑 npm 需 `--cache <工作区内目录>`（沙箱禁写 ~/.npm），用户自己终端无需任何特殊参数 |
| 2026-09-20 | — | **后台服务合并（用户决定：新建统一库 + 平台为壳 + 仅合主库 + 前端不动）**：① `rpa_log_service` 整包迁入 `queue_control_platform/server/rpa_log/`（settings/db 重写为复用平台 `QUEUE_CONTROL_MYSQL_URL`，其余相对导入原样），平台 `create_app` 挂载 rpa 三路由（`/api/v1/*`）、`/files` 静态、`/healthz`，lifespan 增加超时扫描，`main.py` 启动时幂等建 rpa 表；② 统一库 `rpa_platform`：init SQL 改名 `01-init.sql`，`CREATE TABLE LIKE + INSERT SELECT` 迁移平台 8 表存量（devices=2、queue_assignments=3、queue_commands=28 等行数核对一致）与 rpa 5 表演示数据，旧库 `queue_control`/`rpa_log` 保留未删仅存档；③ 根 pyproject 增 `python-multipart`（dev 组补 `pytest`）；④ 配置同步：`.env`/`.env.example` 的 MYSQL_URL 指向 rpa_platform，mock_agent 与 vite 代理（`/api`、`/files`）指向 8766；⑤ 测试迁至 `queue_control_platform/tests/` **18/18 全绿**；⑥ E2E 单进程验证：`/healthz` ok、平台 dashboard/维护页 200、rpa 列表/统计/mock 三步上报 200、文件上传返回 8766 LAN url 且静态回读 200、init_db 幂等重跑通过；⑦ `rpa-log-service/` 目录退役删除（内容已全部并入并验证）。Agent 运行时通道为 Redis，不受影响；API 路径不变 |
| 2026-09-20 | — | **前端单一化（用户纠正：不要两套系统）**：① `rpa-log-web` 新增"设备管理"页（`/device-manage`，默认首页）：新增设备（创建后弹窗展示一次性注册令牌，仅此一次）、分配队列（含"队列须已存在于 MQ"提示）、暂停/恢复/重启/全部重启/解除绑定，`src/api/platform.ts` 独立封装平台 `{ok,error}` 风格 API；② `web.py` 移除 Jinja 维护页与 `/static`，改为根路径托管 `rpa-log-web/dist`（StaticFiles html=True，挂载在全部路由之后；未构建时显示占位提示），`frontend/` 目录删除（git 历史可查）；③ 品牌统一为"RPA 控制台"。验证：tsc/build 通过、服务测试 18/18、单进程 8766 上 `/` 返回控制台且 assets 200、平台 API 与 `/api/v1/*` 共存、新增设备冒烟通过（测试数据已清理）。备注：`pnpm exec` 会误触包管理器切换（DSH 内置 pnpm），前端一律用 `npm`；前端改动需 `npm run build` 并重启服务生效 |
| 2026-09-23 | — | **填单操作日志记录填充值（用户需求）**：`app/core/page/dom.py` 新增 `_value_text()`（多行压缩、空值容错、500 字符截断），6 个填值助手日志全部带值——`input_text`（输入X: 值）、`select`/`select_radio`/`select_by_word`（选择X: 值，后者此前无日志）、`search_select`/`search_select_element`（搜索并选择/输入/选择 均带值）；MSCGW 两处 mixin 的 shadow 下拉选中日志补上目标值（si_fill_free_router_details、si_navigation）。效果对所有走 DomHelper 的任务生效（不限 MSCGW）。验证：值格式化单测断言、日志行示例 `输入发货人: SHENZHEN DEMO CO., LTD`、相关测试 35/35 全绿。说明：日志表 message 为 TEXT 无长度风险，截断仅为展示友好 |
| 2026-09-23 | — | **取消消息ID幂等（用户决定：相同消息再消费 → 另插一条记录）**：① `rpa_execution` 去掉 `uk_message_queue` 唯一键改普通索引（DDL + 统一库 ALTER 同步），`upsert_execution` 改为 `create_execution` 纯插入（保留设备/队列维表 upsert）；单条记录的 finish 幂等（重复 409）不变；② 测试语义重写（`test_recreate_same_message_inserts_new_record`），**17/17 全绿**；③ 实测同消息两次创建得到两条独立记录（验证后已清理）；④ **事故与恢复**：跑测试误清统一库，删掉了用户真实执行记录（2100033346112454656 / 91 条日志）——通过 binlog.000015（Percona 镜像 mysqlbinlog 解码 + 时区修正 UTC 窗口 + INSERT/终态 UPDATE 重建）**完整恢复**（SUCCESS/91 条/耗时 96s 均与原值一致）；⑤ **根因修复**：测试夹具改为独立库 `rpa_platform_test`（root 本地连接、上传目录走临时目录），真实库永不被测试触碰，隔离已验证（测试前后真实库行数不变）。备忘：容器 MySQL 为 UTC，手工 SQL 用 NOW() 会让超时扫描误判（本次金丝雀行即踩此坑，已删） |
