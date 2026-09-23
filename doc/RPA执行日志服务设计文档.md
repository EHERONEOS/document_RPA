# RPA 执行日志服务设计文档

> 版本：v1.0（设计稿）。基于当前代码树（`wise-rpa`）整理，文中引用的模块、字段、行为均以现有实现为依据。

## 1. 背景与目标

当前系统的执行过程信息只有两类出口：

1. `app/core/logging/logger.py` 的控制台彩色打印 —— 机器本地可见，无法跨设备检索、无持久化；
2. `app/core/task/base_task.py` 的 `TaskResult` 回传 —— 只含最终结果（`remark` / `img` / `executeRecordFiles`），没有过程日志。

本服务目标：**将每次 RPA 消息的执行过程（日志流水）与执行结果（状态/失败原因/记录文件）集中持久化，并提供 Web 控制台按消息检索、排障。**

| 目标 | 说明 |
| --- | --- |
| 执行记录集中化 | 一条队列消息一次执行 = 一条执行记录（消息ID、JobId、队列、设备、状态、时间） |
| 过程日志可回放 | 任务执行中随时 `self.logger` / `log()` 上报，页面抽屉内从新到旧回放 |
| 结果可解释 | 失败原因（remark）+ 失败截图（img）；成功/失败均展示记录文件（executeRecordFiles） |
| 不影响业务 | 上报全链路异步、降级、不抛错；本地调试（`app.dev.local_runner`）零侵入不记录 |

## 2. 现状分析（以实现为准）

与设计直接相关的现有代码事实：

| 模块 | 现状 | 对设计的影响 |
| --- | --- | --- |
| `app/core/logging/logger.py` | 仅控制台打印；有 `log/info/warn/error` 与 `Logger` 类；**无 `success` 级别** | 需扩展 `success()` 级别与上报管道 |
| `app/core/task/base_task.py` `run()` | `except` 中 `remark=str(exc)`、`img=_upload_error_screenshot()`（返回 OSS objectName；上传响应 `file_info.url` 同时给出**完整地址**）；`finally` 中 `_collect_record_files()` 汇总业务截图分组 + 录屏（`type=SCREEN_RECORDING_FILE`），随后组 `TaskResult` 回传 | 结束态（状态/失败原因/截图/记录文件）在此处一次性可得，是天然采集点 |
| `app/core/task/base_task.py` `_upload_execute_video()` | 录屏 > 10MB（`MAX_RECORDING_UPLOAD_SIZE`）跳过 OSS 上传保留本地；OSS 失败也保留本地 | "OSS 未上传成功"的录屏正是需要局域网兜底的对象 |
| `app/core/integrations/oss.py` | `oss_upload()` 返回 `{objectName, filename, url, ...}`，其中 `url` 为**完整访问地址** | 日志服务直接记录 `file_info.url`，无需任何前缀拼接 |
| `app/core/page/dom.py` / `http.py` | 调用模块级 `log()`，拿不到任务上下文；`HttpHelper.request` 成功时无日志 | 需要线程级上下文绑定 + `request()` 补成功日志 |
| `app/dev/local_runner.py` | `runtime_mode="local"`、`enable_result_publish=False` | 说明事项 1：该入口强制不记录 |
| `app/queue/consumer.py` `handle_message()` | 队列消息唯一入口；此前有 `skip_test_job` 过滤 | 说明事项 2：环境变量开关挂在此处；执行记录（RUNNING）从此处创建 |
| `app/queue/booster.py` | funboost 默认线程并发，`concurrent_num=3` | 同一消息在单线程内同步执行，`contextvars`/线程隔离绑定上下文安全 |
| `app/control/queue_client/config.py` | 设备身份 `QUEUE_CONTROL_DEVICE_ID` | 设备名可直接复用，无需新增注册流程 |
| `queue_control_platform` | 已有 FastAPI + MySQL + 静态前端的中心平台（devices / queue_assignments 表） | 日志服务沿用同一技术栈与 MySQL 实例，设备/队列维表可与其互通 |

## 3. 总体架构

```mermaid
flowchart LR
    subgraph 设备侧 Agent（Windows 业务机器）
        MQ[(RabbitMQ)] --> CON[Queue Worker 进程]
        CON --> TASK["BaseRpaTask.run()"]
        TASK --> LOGGER["app.core.logger<br/>(扩展: success + 上报)"]
        DOM["dom.py / http.py"] --> LOGGER
        LOGGER --> CLIENT["LogReportClient<br/>(内存队列+批量异步)"]
        TASK --> FILEUP["FileStorageClient<br/>(OSS 优先 / 局域网兜底)"]
    end

    subgraph 日志服务 rpa-log-service（Windows 局域网机器）
        API["FastAPI<br/>/api/v1/*"]
        STORE["文件存储<br/>files/yyyy/mm/uuid.ext"]
        DB[(MySQL<br/>执行/日志/文件/设备/队列)]
        API --> DB
        API --> STORE
        CRON["定时任务<br/>RUNNING 超时置位 / 过期文件清理"] --> DB
        CRON --> STORE
    end

    CLIENT -->|批量日志 / 结束态| API
    FILEUP -->|视频/文件 multipart 上传| API
    FE["Web 控制台<br/>React 18 + antd 5"] --> API
```

设计要点：

- **Agent 只依赖两个 HTTP 出口**：日志/结果上报、文件上传。上报失败一律本地降级（打印 WARN，不重试阻塞），保证“日志服务挂了不影响 RPA 干活”。
- **服务端单体内拆模块**：日志入库、文件存储、定时维护在同一个 FastAPI 应用内，部署简单（Windows 一台机器一个服务）。
- **文件三级降级链**：OSS → 局域网文件服务 → 本地保留（见 §7）。

## 4. 数据模型（MySQL）

沿用 `queue_control_platform` 的建表风格（utf8mb4、DATETIME(6)、可重复执行）。

### 4.1 `rpa_execution` 执行记录主表（列表页数据源）

```sql
CREATE TABLE IF NOT EXISTS rpa_execution (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    rpa_message_id   VARCHAR(64)  NOT NULL COMMENT '消息ID task.rpaMessageId',
    job_id           VARCHAR(64)  NOT NULL DEFAULT '' COMMENT 'JobId: content.jobNo/blNo/bookingNo/shippingNo',
    queue_name       VARCHAR(128) NOT NULL COMMENT '完整队列名 task.rpaTaskTopic',
    device_name      VARCHAR(128) NOT NULL COMMENT '设备名 QUEUE_CONTROL_DEVICE_ID 或主机名',
    task_id          VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '回传 task.id',
    customer_code    VARCHAR(32)  NOT NULL DEFAULT '' COMMENT '由队列名解析',
    carrier_code     VARCHAR(32)  NOT NULL DEFAULT '' COMMENT '由队列名解析',
    business_code    VARCHAR(32)  NOT NULL DEFAULT '' COMMENT '由队列名解析',
    status           VARCHAR(16)  NOT NULL DEFAULT 'RUNNING' COMMENT 'RUNNING/SUCCESS/FAILED/TIMEOUT',
    remark           TEXT         NULL COMMENT '失败原因 = TaskResult.remark（仅失败）',
    fail_img_url     VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '失败截图完整地址 = TaskResult.img + OSS 前缀',
    log_count        INT          NOT NULL DEFAULT 0 COMMENT '日志条数（冗余计数）',
    started_at       DATETIME(6)  NOT NULL COMMENT '消息接收时间',
    finished_at      DATETIME(6)  NULL COMMENT '结果回传时间（终态写入）',
    duration_seconds INT          NULL COMMENT '耗时（秒）= finished_at - started_at，终态写入',
    create_time      DATETIME(6)  NOT NULL COMMENT '创建时间（列表页展示列）',
    update_time      DATETIME(6)  NOT NULL,
    UNIQUE KEY uk_message_queue (rpa_message_id, queue_name),
    INDEX idx_job_id (job_id),
    INDEX idx_queue_status_time (queue_name, status, create_time),
    INDEX idx_status_time (status, create_time),
    INDEX idx_device_time (device_name, create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RPA 执行记录';
```

- `uk_message_queue` 保证同一消息重复上报幂等（funboost 手动重投/重复消费不产生脏数据）。
- 执行状态：`RUNNING`（运行中/黄）、`SUCCESS`（成功/绿）、`FAILED`（失败/红）；`TIMEOUT` 为扩展状态（运行超时被定时任务置位，前端同样按红色展示），不在一期必须范围。

### 4.2 `rpa_execution_log` 执行日志明细表（抽屉数据源）

```sql
CREATE TABLE IF NOT EXISTS rpa_execution_log (
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    execution_id   BIGINT       NOT NULL,
    seq            BIGINT       NOT NULL COMMENT '执行内递增序号，Agent 侧生成',
    level          VARCHAR(10)  NOT NULL COMMENT 'INFO/WARN/ERROR/SUCCESS',
    message        TEXT         NOT NULL,
    source_file    VARCHAR(255) NOT NULL DEFAULT '' COMMENT '调用位置文件（现有 _caller() 逻辑复用）',
    source_line    INT          NOT NULL DEFAULT 0,
    log_time       DATETIME(3)  NOT NULL COMMENT 'Agent 侧日志产生时间',
    create_time    DATETIME(3)  NOT NULL,
    INDEX idx_exec_seq (execution_id, seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RPA 执行日志明细';
```

页面展示规则：`ORDER BY seq DESC`（从新到旧），行格式 `下标. 日志内容 时间`，颜色映射见 §9.4。

### 4.3 `rpa_execution_file` 记录文件表（记录文件弹窗数据源）

```sql
CREATE TABLE IF NOT EXISTS rpa_execution_file (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    execution_id  BIGINT        NOT NULL,
    file_type     VARCHAR(64)   NOT NULL COMMENT 'type: SCREEN_RECORDING_FILE / 业务截图类型',
    media_type    VARCHAR(10)   NOT NULL COMMENT 'VIDEO / IMAGE（按后缀推断）',
    file_name     VARCHAR(255)  NOT NULL,
    url           VARCHAR(1024) NOT NULL COMMENT '完整访问地址（OSS 或局域网）',
    storage       VARCHAR(10)   NOT NULL DEFAULT 'OSS' COMMENT 'OSS / LAN',
    file_size     BIGINT        NOT NULL DEFAULT 0,
    create_time   DATETIME(6)   NOT NULL,
    INDEX idx_exec (execution_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RPA 执行记录文件';
```

> 备选方案是把 `executeRecordFiles` 整体存 JSON 列。拆表的原因：文件 URL 在落库后可能因存储迁移变化、前端需要按 `media_type`/`storage` 过滤渲染、后续可单独做文件清理统计。拆表成本很低，收益明确。

### 4.4 设备 / 队列维表（左侧导航两个列表页的数据源）

```sql
CREATE TABLE IF NOT EXISTS rpa_device (
    device_name    VARCHAR(128) PRIMARY KEY,
    os_info        VARCHAR(128) NOT NULL DEFAULT '',
    last_seen_at   DATETIME(6)  NULL,
    create_time    DATETIME(6)  NOT NULL,
    update_time    DATETIME(6)  NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS rpa_queue (
    queue_name     VARCHAR(128) PRIMARY KEY,
    customer_code  VARCHAR(32)  NOT NULL DEFAULT '',
    carrier_code   VARCHAR(32)  NOT NULL DEFAULT '',
    business_code  VARCHAR(32)  NOT NULL DEFAULT '',
    create_time    DATETIME(6)  NOT NULL,
    update_time    DATETIME(6)  NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

上报接口写入执行记录时顺带 upsert 维表（`INSERT ... ON DUPLICATE KEY UPDATE last_seen_at=NOW()`），**无需额外注册流程**。设备/队列列表页的统计列（今日执行数、成功率、平均耗时）用聚合查询实现。若后续与 `queue_control_platform` 同库部署，可直接联其 `devices`/`queue_assignments` 补充绑定关系。

## 5. 服务端 API 设计

统一前缀 `/api/v1`，**接口风格统一为 `GET` 用 query params、`POST` 用 JSON Body，不使用 REST 路径参数**（如不采用 `/executions/{id}` 形式，资源标识统一放在参数里）。Agent 侧接口用 `Authorization: Bearer <RPA_LOG_SERVICE_TOKEN>` 简单鉴权（内网 + token 两层即可）。

### 5.1 Agent 上报接口

| 接口 | 说明 |
| --- | --- |
| `POST /api/v1/executions` | 创建/幂等更新执行记录。Body: `{rpaMessageId, jobId, queueName, deviceName, taskId, startedAt, customerCode?, carrierCode?, businessCode?}`，返回 `executionId`，后续接口均以参数携带 |
| `POST /api/v1/logs/batch` | 批量追加日志。Body: `{executionId, logs:[{seq, level, message, sourceFile, sourceLine, logTime}]}`，单批 ≤200 条 |
| `POST /api/v1/executions/finish` | 结束执行。Body: `{executionId, status, remark?, failImgUrl?, recordFiles:[{type, mediaType, fileName, url, storage, fileSize?}], finishedAt, durationSeconds?}`；重复调用以首次结果为准（幂等） |
| `POST /api/v1/files/upload` | multipart 文件上传（局域网文件服务）。返回 `{url, storage:"LAN", fileName, fileSize}`。限制：内网来源、单文件 ≤200MB、扩展名白名单（mp4/mov/png/jpg/jpeg…） |

`finish` 的字段与 `TaskResult` 的映射关系（关键约定）：

| 日志服务字段 | 来源 | 说明 |
| --- | --- | --- |
| `status` | `result.success` | `True → SUCCESS`，`False → FAILED` |
| `remark` | `TaskResult.remark` | 失败原因文案 = `str(exc)`，仅 FAILED 展示 |
| `failImgUrl` | 失败截图上传响应的 `file_info.url` | OSS 上传接口已返回**完整地址**，直接记录；`TaskResult.img` 保持 objectName 不变，现有回传协议零改动 |
| `recordFiles` | `TaskResult.executeRecordFiles` | 现有分组结构 `{type, files:[{fileObjectName, fileName}]}` 拍平为逐文件记录；`url` 为完整地址，`storage` 标注来源 |

### 5.2 Web 控制台查询接口

| 接口 | 说明 |
| --- | --- |
| `GET /api/v1/executions` | 列表分页。Params: `rpaMessageId`、`jobId`、`queueName`、`status`、`page`、`pageSize`、`beginTime?`、`endTime?`（模糊匹配消息ID/JobId，队列/状态精确）。返回行含 `createTime`、`finishedAt`（终态）、`durationSeconds`（终态） |
| `GET /api/v1/execution/detail` | 详情。Params: `executionId`。返回主记录 + 日志明细（`seq DESC`）+ 文件列表 |
| `GET /api/v1/devices` | 设备列表 + 统计（今日执行、成功率、最近心跳） |
| `GET /api/v1/queues` | 队列列表 + 统计（今日执行、成功率、平均耗时） |
| `GET /api/v1/stats/summary` | 首页统计卡（今日总数/成功/失败/运行中） |

响应统一 `{code, message, data}` 包装；时间字段一律 `yyyy-MM-dd HH:mm:ss` 字符串（服务端格式化，前端不做时区换算）。

## 6. Agent 端改造设计

### 6.1 配置与环境变量（对应说明事项 1、2）

新增（建议进 `.env` / 启动脚本，命名风格与现有 `QUEUE_CONTROL_*` 一致）：

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `RPA_LOG_SERVICE_ENABLED` | `false` | **接收队列时是否记录日志服务的主开关**。队列 Worker 启动时读取；本地开发不配置即天然关闭 |
| `RPA_LOG_SERVICE_URL` | 空 | 服务地址，如 `http://192.168.1.50:9000` |
| `RPA_LOG_SERVICE_TOKEN` | 空 | 上报鉴权 token |
| `RPA_LOG_DEVICE_NAME` | `QUEUE_CONTROL_DEVICE_ID`，无则主机名 | 设备名（列表页“设备名”列） |
| `RPA_LOG_RUNNING_TIMEOUT_HOURS` | `6` | RUNNING 超时判定阈值（服务端定时任务用） |

对应说明事项 1（`app.dev.local_runner` 不记录）的落地为**双保险**：

```python
# app/core/logging/log_session.py（新增）
def log_service_enabled(runtime_mode: str) -> bool:
    """队列模式且环境变量开启时才记录；local_runner 的 runtime_mode='local' 强制关闭。"""
    return (
        runtime_mode == "queue"
        and os.getenv("RPA_LOG_SERVICE_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    )
```

`app/dev/local_runner.py` 走 `build_task_context(runtime_mode="local")`，`log_service_enabled` 恒为 `False` —— 即使开发机误配了环境变量也不会上报。

### 6.2 logger 模块扩展（对应说明事项 3）

`app/core/logging/logger.py` 原地增强，**不改变现有控制台输出格式**：

1. **新增 `SUCCESS` 级别**：模块级 `success()` + `Logger.success()`，控制台色 `\033[32m`（绿），服务端级别 `SUCCESS` → 页面绿色。`info/warn/error` 对应灰/黄/红。
2. **执行上下文绑定**：新增 `app/core/logging/log_session.py`：

```python
@dataclass
class ExecutionLogContext:
    execution_id: int | None   # 服务端执行记录 ID（懒创建）
    rpa_message_id: str
    job_id: str
    queue_name: str
    device_name: str
    seq: int = 0               # 本执行内日志序号，线程安全自增

_current_context: ContextVar[ExecutionLogContext | None] = ContextVar("rpa_log_ctx", default=None)
```

funboost 默认线程并发（`concurrent_num=3`），一条消息在固定单线程内同步跑完 `handle_message → dispatch → task.run()`，`ContextVar` 隔离安全；若未来切到 asyncio 并发模式，`ContextVar` 同样随协程复制，无需改造。

3. **上报管道**：`app/core/logging/report_client.py` 新增 `LogReportClient`：
   - 单例；内部 `queue.Queue` + 单 daemon 线程，**攒批上报**（满 50 条或 1s flush）→ `POST /logs/batch`（Body 携带 `executionId`）；
   - 任何异常仅本地打印 WARN，**绝不向上抛、绝不阻塞业务线程**；进程退出 `atexit` 兜底 flush；
   - `RPA_LOG_SERVICE_ENABLED=false` 或 URL 为空时为 no-op，行为与现状完全一致。

```python
# logger.py 模块级函数最终形态（伪码）
def log(message, level="INFO"):
    _print_console(message, level)          # 现有逻辑原样保留
    ctx = _current_context.get()
    if ctx:                                 # 无上下文（模块导入期、工具脚本）只打印不上报
        REPORT_CLIENT.enqueue(ctx.next_seq(), level, message, *_caller())
```

### 6.3 任务内 `self.logger` 随时上报（对应说明事项 6）

`BaseRpaTask.__init__` 中 `self.logger = Logger()` 不变——它已经能通过 `_current_context` 拿到当前执行的绑定上下文。**消息ID / JobId / 队列名由会话绑定阶段注入，任务内任何位置调用 `self.logger.info/warn/error/success()` 均自动携带**，业务代码无需感知。

会话绑定在队列入口完成（对应说明事项 2 的判断点）：

```python
# app/queue/consumer.py（改造）
@skip_test_job
def handle_message(task, account_session_coordinator=None):
    context = build_task_context(task)
    # queue 模式 + 环境变量开启 → 开启执行日志会话（创建 RUNNING 记录并绑定上下文）
    with execution_log_session(context):          # 内部判断 log_service_enabled("queue")
        ...原 acquired_slot / dispatch 逻辑...
        # session __exit__ 中：若尚未 finish（未走到 base_task 结果上报就异常），
        # 兜底 finish(FAILED, remark=异常文案)，保证任何路径都有终态
```

`execution_log_session` 懒创建执行记录：首次日志/会话开启时 `POST /executions`（`uk_message_queue` 幂等），`job_id` 取 `content.jobNo → blNo → bookingNo → shippingNo`，队列三元组复用 `resolve_queue_route()`。

`skip_test_job` 跳过的测试单**不产生任何记录**：执行日志会话在 `skip_test_job` 校验通过之后才开启（装饰器在外层先执行过滤），测试消息不会创建执行记录、也不会上报日志。

### 6.4 结束态上报（对应说明事项 4、5）

`base_task.run()` 的 `finally` 组好 `TaskResult` 后追加一次上报（同样走降级保护，不影响回传）：

```python
finally:
    execute_record_files = self._collect_record_files()
    ...
    result = TaskResult(...)
    self.logger.finish_execution(          # 新增：日志服务终态上报
        success=success,
        remark=remark,                     # 失败原因 = str(exc)
        fail_img=fail_img_url,             # 失败截图上传响应的 file_info.url（完整地址）
        record_files=execute_record_files, # 分组结构拍平上报，url 取各 file_info.url
    )
```

- **失败截图完整地址**：`_upload_error_screenshot()` 内部已拿到上传响应 `file_info.url`（OSS 返回的完整地址），随终态上报直接使用；`TaskResult.img` 保持 objectName 不变，**现有回传协议零改动**。
- **记录文件**：`_collect_record_files()` 现有分组 `{type, files:[{fileObjectName, fileName}]}` 原样复用；上报时补齐 `url`（上传响应 `file_info.url`，OSS 与局域网上传统一返回完整地址）、`media_type`（后缀 `.mp4/.mov/.avi → VIDEO`，否则 `IMAGE`）与 `storage`（见 §7）。
- **录屏降级链**（`_upload_execute_video` 改造）：OSS 成功 → `storage=OSS`；OSS 失败或超 10MB → 尝试局域网上传 → `storage=LAN`；两者都失败 → 不记文件 + `logger.warn`（本地文件按现状保留）。

### 6.5 dom.py / http.py 最终结果日志（对应说明事项 7）

三个动作满足“所有任务调用都记录最后日志结果”：

1. dom/http 使用的模块级 `log()` 已接入 §6.2 的上报管道——两个文件**零代码改动**即自动上报全部操作流水（点击/输入/选择/下载/监听）。
2. `HttpHelper.request()` 补一行成功结果日志（现状只有失败分支）：`log(f"HTTP {method} {url} 请求成功 status={response.status_code}")`。
3. 元素级异常（`ElementNotFoundError` 等）最终都会冒泡到 `base_task.run()` 的 `except`，由既有的 `任务执行失败 queue=... error=...` ERROR 日志兜底记录最终结果。

### 6.6 执行生命周期时序

```mermaid
sequenceDiagram
    participant MQ as RabbitMQ
    participant W as Queue Worker
    participant S as LogSession(ContextVar)
    participant T as BaseRpaTask
    participant L as LogReportClient
    participant API as rpa-log-service
    participant OSS as OSS

    MQ->>W: 消息(rpaMessageId...)
    W->>S: execution_log_session(context)<br/>[RPA_LOG_SERVICE_ENABLED 才启用]
    S->>API: POST /executions (幂等) → 状态 RUNNING(黄)
    W->>T: dispatch → task.run()
    T->>T: login / execute_business<br/>随时 self.logger.info/warn/error/success
    T->>L: log(...)
    L-->>API: 批量 POST /logs/batch (Body 带 executionId, 1s/50条)
    Note over T: dom.py / http.py 的 log() 同样经 S 上报
    T->>OSS: 失败截图 / 业务文件 / 录屏上传
    OSS-->>T: objectName（失败→局域网文件服务兜底）
    T->>L: finish_execution(SUCCESS/FAILED,<br/>remark, img, recordFiles)
    L-->>API: POST /executions/finish → 绿/红
    Note over API: RUNNING 超过阈值未被 finish<br/>→ 定时任务置 TIMEOUT
```

## 7. 文件存储方案与局域网上传可行性分析（对应说明事项 5）

### 7.1 方案设计

**局域网文件服务内置于 rpa-log-service**（同一个 FastAPI 应用，不单独起进程）：

- `POST /api/v1/files/upload`：multipart 上传，服务端按 `files/{yyyy}/{mm}/{uuid}{ext}` 落盘（Windows 机器本地磁盘，如 `D:/rpa-log-service/files`），返回 `http://{局域网IP}:{端口}/files/2025/01/xxx.mp4`；
- `GET /files/...`：`StaticFiles` 只读挂载，浏览器/前端直接访问；
- Agent 侧抽象 `FileStorageClient`（策略模式）：

```python
class FileStorageClient:          # app/core/integrations/file_storage.py（新增）
    def upload(self, path) -> dict:  # → {url, storage: "OSS" | "LAN"}
        try:
            return self._upload_oss(path)          # 优先 OSS（现状不变）
        except Exception:
            return self._upload_lan(path)          # 兜底局域网（仅日志服务场景）
```

**降级链路与记录结果**：

| 场景 | 记录的 `url` | `storage` | 页面表现 |
| --- | --- | --- | --- |
| OSS 上传成功 | 上传响应的 `file_info.url`（完整地址） | OSS | 视频/图片正常播放（现有主路径） |
| OSS 未上传/失败（含 >10MB） | `http://{LAN}/files/...` | LAN | 局域网内正常播放，前端打“LAN”角标 |
| OSS、LAN 均失败 | 不记录该文件 | — | 该文件缺失 + 一条 WARN 日志（本地文件保留，人工可取） |

### 7.2 可行性分析

| 维度 | 分析 | 结论 |
| --- | --- | --- |
| **网络与带宽** | Agent 与服务机同局域网（部署约束已明确）。千兆局域网实测吞吐 ≥100MB/s，单录屏 ≤10MB 上传 <1s；并发上限 = 队列并发数 3，即使 3 队列同时结束传录屏也是秒级完成，且上传在 `finally` 阶段、不占用浏览器会话时长 | ✅ 无压力 |
| **存储容量** | 现有 `MAX_RECORDING_UPLOAD_SIZE=10MB` 已限制单个录屏。按日均 500 次执行、每次平均 8MB 文件估算 → 日增 ≈4GB；1TB 磁盘可存 8 个月以上。配套：保留天数（默认 90 天）定时清理 + 磁盘水位（80%）告警清理 | ✅ 可控，需配清理策略 |
| **可靠性** | 单机单盘是最大短板（盘坏即丢）。但业务影响被三级降级链隔离：LAN 失败仅丢“留档文件”，任务回传、执行状态、日志文本均不受影响；本地文件保留可人工补传。后续可加第二块盘或 SMB/对象存储备份 | ✅ 故障影响可接受 |
| **安全** | 仅监听内网网卡；上传需 Bearer token；服务端 UUID 重命名杜绝路径穿越；静态目录只读；扩展名白名单；不暴露公网 | ✅ 内网场景够用 |
| **Windows 部署** | uvicorn + NSSM/WinSW 注册为 Windows 服务（开机自启、崩溃拉起）；路径约定纯英文无空格；防火墙放行端口（如 9000）；FastAPI + StaticFiles 在 Windows 上为纯 Python 方案，无编译依赖 | ✅ 成熟做法 |
| **播放兼容性** | `Recorder` 产出 `.mp4`（capturesdk H264/CPU 编码），浏览器 `<video>` 原生支持，无需转码；截图 png/jpg 原生支持 | ✅ 无转码成本 |
| **Linux/未来迁移** | 用户明确“部署到 Linux 后文件系统待定”。`FileStorageClient` 抽象把该不确定性隔离在**服务端**：届时仅替换服务端实现（对象存储/nginx/MinIO）或新增 `storage` 枚举值，Agent 与前端只认 `{url, storage}`，**零协议改动** | ✅ 风险已隔离 |
| **协议一致性** | `execute_record_files` 现有回传结构不动，日志服务仅**旁路**多存一份带完整 URL 的记录；`TaskResult` 协议零改动 | ✅ 无侵入 |

**结论：方案可行，推荐采用。** 核心依据：① 量级小（≤10MB/文件、低频），局域网上传性能充裕；② 三级降级保证故障不伤业务；③ 策略模式让“Linux 待定”不构成设计风险。唯一需要运营约束的是磁盘清理策略，建议一期就带上。

## 8. Web 控制台设计（React + antd，对应前端优化 1–5）

### 8.1 技术选型与布局

| 项 | 选型 |
| --- | --- |
| 构建 | Vite + React 18 + TypeScript |
| 组件库 | Ant Design 5（亮色算法，默认 token） |
| 路由 / 请求 | react-router-dom 6 / axios（统一拦截 `{code,data}`） |
| 时间 | dayjs，统一 `YYYY-MM-DD HH:mm:ss` |
| 布局 | antd `Layout`：左侧白色 `Sider`（Menu）+ 顶部 `Header`（面包屑）+ `Content`（`#f5f5f5` 背景 + 白色卡片），符合 antd 布局规范 |

页面骨架（对应原型图 `doc/prototype/rpa-log-prototype.html`，可直接用浏览器打开体验交互）：

```
<App>
 ├─ Sider（白底）
 │   ├─ Logo：RPA 日志中心
 │   └─ Menu：日志列表 / 设备列表 / 队列列表
 ├─ Header：面包屑 + 环境标签
 └─ Content
     ├─ /logs        LogListPage        （默认首页）
     ├─ /devices     DeviceListPage
     └─ /queues      QueueListPage
```

色调：白色容器 + `#f5f5f5` 画布 + `#1677ff` 主色；状态/日志四色映射见 §9.4，全部使用 antd 语义色（`success/error/warning/default`），不做自定义色值。

### 8.2 页面一：日志列表（核心页）

**搜索区**（`Form` 行内布局，输入即防抖查询 + 查询/重置按钮）：

| 控件 | 字段 | 匹配方式 |
| --- | --- | --- |
| Input | 消息ID | 后缀模糊 |
| Input | JobId | 后缀模糊 |
| Select（可搜索） | 队列名 | 精确，选项来自 `/api/v1/queues` |
| Select | 执行状态 | 精确（成功/失败/运行中） |

**表格列**（`Table`，`rowKey=id`，分页 `pageSize=10/20/50`）：

| 列 | 渲染 |
| --- | --- |
| 消息ID | 等宽字体，可复制 |
| JobId | 等宽字体 |
| 队列名 | 等宽字体 |
| 设备名 | 文本 |
| 执行状态 | `Tag`：成功=绿（success）/ 失败=红（error）/ 运行中=黄（warning，带滚动圆点动画） |
| 创建时间 | `yyyy-MM-dd HH:mm:ss` |
| 结束时间 | `yyyy-MM-dd HH:mm:ss`，**仅成功/失败状态展示**，运行中显示 `—` |
| 耗时 | `durationSeconds` 格式化为 `2m 38s`，**仅成功/失败状态展示**，运行中显示 `—` |
| 操作 | 链接按钮组，按状态显隐（见下） |

**操作列显隐规则**：

| 操作 | 可见条件 | 交互 |
| --- | --- | --- |
| 查看详情 | 恒可见 | 右侧 `Drawer`（width=50%） |
| 失败原因 | 仅 `FAILED` | `Modal`：错误文案（红色 Alert 样式）+ 失败截图（`Image` 可预览放大，url=failImgUrl） |
| 记录文件 | `SUCCESS` / `FAILED` 且有文件 | `Modal`：按 `file_type` 分组，图片 `Image.PreviewGroup` 缩略图，视频 `<video controls>`；每个文件带 `OSS/LAN` 存储角标 |

**执行日志抽屉**（查看详情）：

- 抽屉宽度为屏宽的 **50%**（`Drawer width="50%"`，小屏退化为 `min(50%, 92vw)`）；
- 上半部 `Descriptions`：消息ID / JobId / 队列名 / 设备名 / 执行状态 / 创建时间 / 结束时间 / 耗时（结束时间与耗时仅成功/失败展示）；
- 下半部日志明细，**从新到旧**（`seq DESC`），行格式严格为：

```
{i}. {日志内容} {yyyy-MM-dd HH:mm:ss}
```

  序号 `i` 从新到旧 1 起编；日志内容按级别着色（§9.4）；**每条日志默认单行展示**（`Typography.Text ellipsis` / CSS `text-overflow: ellipsis`），超出抽屉宽度显示省略号，**鼠标悬浮通过 `Tooltip` 展示完整内容**；**时间列始终完整显示** `yyyy-MM-dd HH:mm:ss`（右对齐灰色等宽字体，不参与截断换行）；
- 长列表用 antd `List` + `virtual`（5.9+ 内置虚拟滚动），数千条日志不卡顿；
- `RUNNING` 状态的记录：抽屉标题栏提供**刷新按钮**（`ReloadOutlined`，点击进入旋转加载态），手动点击后调用 `GET /api/v1/execution/detail` 重新拉取该任务**最新日志**并从顶部插入；打开抽屉期间另每 30s 自动轮询（与刷新按钮并存），关闭抽屉即停。终态（成功/失败）不显示刷新按钮。

**辅助能力**：页面顶部统计卡（今日执行/成功/失败/运行中，`/stats/summary`）；`RUNNING` 行整表 30s 轮询自动刷新，可手动暂停。

### 8.3 页面二：设备列表 / 页面三：队列列表

| 页面 | 列 |
| --- | --- |
| 设备列表 | 设备名 / 操作系统 / 绑定队列数 / 今日执行 / 成功率 / 最近心跳 / 在线状态（Tag） |
| 队列列表 | 队列名 / 客户 / 船司 / 业务（队列名解析三元组）/ 今日执行 / 成功率 / 平均耗时 |

行点击可跳转日志列表并带入对应筛选条件（设备名→隐藏筛选；队列名→队列下拉），形成“从概览到明细”的下钻动线。

### 8.4 组件结构

```
src/
 ├─ layouts/AdminLayout.tsx        # Sider + Header + Content
 ├─ pages/
 │   ├─ LogListPage/
 │   │   ├─ index.tsx              # 搜索 + 表格 + 轮询
 │   │   ├─ SearchForm.tsx
 │   │   ├─ ExecutionTable.tsx     # columns 定义、操作列
 │   │   ├─ StatusTag.tsx
 │   │   ├─ ExecutionDrawer.tsx    # 详情 + 日志明细（虚拟滚动）
 │   │   ├─ FailReasonModal.tsx    # 文案 + 截图
 │   │   └─ RecordFilesModal.tsx   # 分组图片/视频
 │   ├─ DeviceListPage/index.tsx
 │   └─ QueueListPage/index.tsx
 ├─ components/（Empty / StorageBadge / LogLevelText）
 ├─ api/（executions.ts, devices.ts, queues.ts, stats.ts）
 └─ utils/format.ts                # 时间格式化、级别色映射
```

## 9. 关键规则与约定

> 2026-09 现状注记：应用户要求取消"消息ID+队列"唯一键——相同消息再次消费插入新记录（每次执行独立成条）；单条记录 finish 幂等保留。下文以首次为准的描述为原始设计存档。

### 9.1 说明事项 ↔ 设计落实对照表

| # | 说明事项 | 落实位置 |
| --- | --- | --- |
| 1 | `app.dev.local_runner` 不记录日志 | §6.1 `log_service_enabled()`：`runtime_mode=="local"` 强制关闭，双保险 |
| 2 | 环境变量判断接收队列是否记录 | §6.1 `RPA_LOG_SERVICE_ENABLED`，判断点在队列 Worker 入口 |
| 3 | `logger.info/error/warn/success` 四级 | §6.2 logger 扩展 `success()`；页面色：灰/红/黄/绿 |
| 4 | 失败原因取 `remark`，截图取 `img` 完整 OSS 地址 | §6.4 映射表（直接使用上传响应 `file_info.url`） |
| 5 | `execute_record_files` 完整地址 + type；视频 OSS 失败传局域网 | §6.4 降级链 + §7 文件服务与可行性分析 |
| 6 | 任务内随时 `self.logger`，消息ID/JobId/队列名任务自行判断 | §6.2/6.3 上下文绑定自动携带，业务代码零感知 |
| 7 | dom.py / http.py 调用都记录最后日志结果 | §6.5 三项动作 |
| 前端 1 | React + antd 重新设计 | §8 |
| 前端 2 | 左侧导航：设备/队列/日志列表 | §8.1 |
| 前端 3 | 白色为主亮色主题 | §8.1（antd 默认亮色算法 + 白色 Sider） |
| 前端 4 | 布局符合 antd 规范 | §8.1（Layout + Sider + Header + Content） |
| 前端 5 | 产品原型图 | `doc/prototype/rpa-log-prototype.html` |

### 9.2 幂等与一致性

- 执行记录以 `(rpa_message_id, queue_name)` 唯一；重复消费/重投覆盖更新而非新增；
- `finish` 幂等：已终态的记录拒绝再次 finish（日志仍可追加）；
- 日志追加允许乱序到达（批量重发），服务端按 `seq` 排序，页面展示不受网络抖动影响。

### 9.3 非功能

- **性能**：Agent 批量上报（50 条/批、1s flush）把 QPS 压到每任务每秒 ≤1 次请求；服务端日志表按 `execution_id` 索引写入；MySQL 单表 `rpa_execution_log` 预计月增百万级，超出后按 `create_time` 归档（一期先按 90 天删除）。
- **可用性**：日志服务不可用时 Agent 全部降级为本地打印（§6.2），RPA 主业务无感知。
- **安全**：内网部署 + Bearer token；查询接口只读；文件服务扩展名白名单 + UUID 重命名。
- **可观测**：服务自带 `/healthz`；Agent 上报失败计数暴露在本地控制台 WARN 中。

### 9.4 颜色映射（前后端统一约定）

| 级别/状态 | 色值（antd token） | 页面表现 |
| --- | --- | --- |
| INFO | 灰 `rgba(0,0,0,0.45)` / Tag default | 普通日志 |
| SUCCESS | 绿 `#52c41a` / Tag success | 成功状态、关键成功节点 |
| WARN | 黄 `#faad14` / Tag warning | 运行中状态、告警日志 |
| ERROR / FAILED | 红 `#ff4d4f` / Tag error | 失败状态、错误日志 |

## 10. 实施计划

| 里程碑 | 内容 | 涉及 |
| --- | --- | --- |
| M1 服务端骨架 | 表结构、`/executions`、`/logs/batch`、`/executions/finish`、`/files/upload`、静态文件服务、NSSM 部署脚本 | 新仓 `rpa-log-service`（FastAPI + PyMySQL） |
| M2 Agent 接入 | logger 扩展（success/上下文/report client）、`consumer` 会话、`base_task` 终态上报、环境变量、`local_runner` 验证不记录 | `app/core/logging/*`、`app/queue/consumer.py`、`app/core/task/base_task.py` |
| M3 Web 控制台 | 按原型实现三个页面 + 抽屉 + 两个弹窗 + 轮询 | 新前端工程（Vite + React + antd5） |
| M4 收尾 | RUNNING 超时定时任务、文件清理策略、设备/队列统计页联调、`HttpHelper.request` 成功日志补齐 | 服务端 + agent |
| M5 部署上线（暂缓） | 按 §11 手工步骤完成 Windows 机器初始化与发布、Agent 接入验证、试运行 | 目标 Windows 机器 |

单测建议：`log_service_enabled` 分支、上报 client 降级（服务不可用不抛错）、`finish` 幂等、`uk_message_queue` 冲突、文件扩展名白名单。

## 11. Windows 部署方案

> 2026-09 现状注记：后台服务已合并——日志 API 并入 queue_control_platform 单服务（默认端口 8766，统一库 rpa_platform）。
> 本节端口/独立部署描述为原始设计存档，实施时以 8766 与合并后单服务为准。


目标形态：**一台 Windows 服务器承载全部服务端组件**（MySQL、后端、前端静态资源、文件存储），与 Agent 同局域网，通过 NSSM 注册为 Windows 服务实现开机自启与崩溃拉起。

### 11.1 组件选型与端口规划

| 组件 | 方案 | 部署形态 |
| --- | --- | --- |
| 数据库 | MySQL 8.4 LTS | 原生 Windows 服务（MySQL Installer 安装时勾选“安装为 Windows 服务”）；若 `queue_control_platform` 已在该机器，**直接复用 MySQL 实例、新建 `rpa_log` 库**，不重复安装 |
| 后端 | FastAPI + uvicorn | NSSM 注册为 Windows 服务 `rpa-log-service`（Python 3.12.12 + uv 管理依赖） |
| 前端 | Vite `build` 产物 `dist/` | 由后端 `StaticFiles` 托管，与 API **同端口**（免 CORS，Agent/浏览器只需记一个地址）；备选 Nginx for Windows 反代（见 11.6） |
| Redis | **平台必需、日志服务本身不需要**（见 11.2） | 中心控制平台的设备命令/事件总线依赖 Redis（Agent 跨机访问）；tporadowski/redis + NSSM 注册为 `redis-rpa`，`requirepass` + 防火墙限 Agent 网段 |
| 文件存储 | 本地磁盘目录 | `D:\rpa-log-service\files`，保留 90 天，Task Scheduler 定时清理 |
| 进程守护 | NSSM | 开机自启、崩溃自动重启、stdout/stderr 落盘并轮转 |

端口规划：

| 端口 | 用途 | 开放范围 |
| --- | --- | --- |
| 9000 | 日志服务（前端页面 + `/api/v1/*` + `/files/*`） | 仅内网网段（防火墙限定 Agent 所在网段） |
| 3306 | MySQL | 仅本机（不开入站防火墙规则；远程管理按需单独放行运维机 IP） |
| 6379 | Redis（可选） | 仅本机 |

目录规划：

```
D:\rpa-log-service\
├─ releases\            # 后端按版本发布：releases\v1.0.0\...
├─ current\             # junction → 指向当前版本（升级即切链）
├─ web\dist\            # 前端构建产物（原子替换）
├─ files\               # 局域网文件存储（yyyy\mm\uuid.ext）
├─ logs\                # 服务运行日志（NSSM 轮转）
├─ backup\              # mysqldump 每日备份
└─ tools\               # nssm.exe 等运维工具
```

### 11.2 关于 Redis 的说明（重要确认点）

**Redis 是否需要，取决于这台机器上是否承载中心控制平台（设备配置/心跳上传）：**

- **日志服务本身不需要 Redis**：Agent 侧批量缓冲在 Agent 进程内存（`LogReportClient`），"运行中日志刷新"靠前端轮询 + 手动刷新按钮，单实例部署无共享状态，MySQL 覆盖全部持久化需求。
- **中心控制平台必须依赖 Redis**：设备命令下发与状态/心跳事件上报走 `RedisStreamBus`（Redis Streams），且各 RPA 机器上的 Queue Agent 需要跨机访问该 Redis —— 因此与平台同机部署时 Redis 必需，`bind 0.0.0.0` + `requirepass`，防火墙仅对 Agent 网段放行 6379。

Windows 上的 Redis 安装推荐 **tporadowski/redis（5.0.14）** 或 **Memurai**（Redis 7 兼容、原生 Windows 服务），经 NSSM 注册为 `redis-rpa` 服务；不建议 Docker Desktop/WSL2 跑生产（许可与运维成本高）。

### 11.3 首次安装步骤

**① 基础环境**

- 固定内网 IP，NTP 对时（日志时间取 Agent 侧上报，服务端时钟仅用于入库顺序，漂移不影响排序正确性）；
- 安装 Python 3.12.12（python.org 安装包）、uv、NSSM（放 `tools\`）；
- 防火墙只放行 9000 给 Agent 网段：

```bat
netsh advfirewall firewall add rule name="rpa-log-service" dir=in action=allow protocol=TCP localport=9000 remoteip=192.168.1.0/24
```

**② MySQL**

- MySQL Installer 选择 Server only，字符集 `utf8mb4`，勾选“Install as Windows Service + Auto start”；PyMySQL 连接 `caching_sha2_password` 认证需补装 `cryptography`（加入服务端依赖即可）；
- 建库建账号（服务同机，仅本机访问）：

```sql
CREATE DATABASE rpa_log DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'rpa_log'@'localhost' IDENTIFIED BY '<密码>';
GRANT ALL PRIVILEGES ON rpa_log.* TO 'rpa_log'@'localhost';
```

**③ 后端发布与服务注册**

```bat
:: 发布代码到 releases\v1.0.0（git clone 或制品 zip），随后
cd D:\rpa-log-service\releases\v1.0.0
uv sync --frozen
:: 配置 .env（服务端配置，命名风格与 PlatformSettings 一致）
::   RPA_LOG_MYSQL_URL=mysql://rpa_log:***@127.0.0.1:3306/rpa_log
::   RPA_LOG_SERVICE_TOKEN=<Agent上报token>
::   RPA_LOG_FILES_DIR=D:\rpa-log-service\files
::   RPA_LOG_RUNNING_TIMEOUT_HOURS=6
:: 建表（幂等，可重复执行，与 queue_control_platform 的 initialize_schema 同模式）
uv run python -m rpa_log_service.init_db
:: 前台试跑验证
uv run uvicorn rpa_log_service.main:app --host 0.0.0.0 --port 9000
:: 验证 http://127.0.0.1:9000/healthz 与页面后停止，切链并注册服务
mklink /J D:\rpa-log-service\current D:\rpa-log-service\releases\v1.0.0

nssm install rpa-log-service "D:\rpa-log-service\current\.venv\Scripts\python.exe" "-m uvicorn rpa_log_service.main:app --host 0.0.0.0 --port 9000"
nssm set rpa-log-service AppDirectory D:\rpa-log-service\current
nssm set rpa-log-service AppStdout D:\rpa-log-service\logs\service-out.log
nssm set rpa-log-service AppStderr D:\rpa-log-service\logs\service-err.log
nssm set rpa-log-service AppRotateFiles 1
nssm set rpa-log-service AppRotateOnlineFileSizeLimit 10485760
nssm set rpa-log-service Start SERVICE_AUTO_START
nssm start rpa-log-service
```

> 单实例部署：uvicorn 保持单进程，RUNNING 超时检查、文件清理等定时任务随服务进程运行；未来确需多 worker 时把定时任务拆为独立的计划任务进程。

**④ 前端发布**

```bash
# 开发机构建
pnpm build   # 产出 dist/
```

将 `dist/` 上传至 `D:\rpa-log-service\web\dist`。前端路由用 **hash 模式**（或后端配置 SPA fallback 到 `index.html`），由后端同端口托管后整站入口即 `http://<服务机IP>:9000/`。升级时先传 `dist_new` 再原子重命名，避免出现半套静态资源。

**⑤ 定时任务（Task Scheduler）**

| 任务 | 频率 | 内容 |
| --- | --- | --- |
| 日志文件清理 | 每天 03:00 | 删除 `files\` 中超过保留期（默认 90 天）的文件 |
| 数据库备份 | 每天 02:00 | `mysqldump -u rpa_log -p<密码> rpa_log > backup\rpa_log_%date%.sql`，保留 30 天 |

**⑥ Agent 侧接入（各 RPA 机器）**

每台业务机器 `.env` 追加：

```ini
RPA_LOG_SERVICE_ENABLED=true
RPA_LOG_SERVICE_URL=http://<服务机IP>:9000
RPA_LOG_SERVICE_TOKEN=<与服务端一致的token>
# RPA_LOG_DEVICE_NAME 不配则默认取 QUEUE_CONTROL_DEVICE_ID / 主机名
```

验证：发一条非 TEST 消息走队列消费，页面应出现 `RUNNING` 记录并在任务结束后变绿/变红；再用 `app.dev.local_runner` 跑一次确认**不产生记录**。

### 11.4 升级与回滚

| 对象 | 升级 | 回滚 |
| --- | --- | --- |
| 后端 | 发布新代码到 `releases\v1.x` → `uv sync --frozen` → 执行幂等 `init_db` → junction 重新指向新版本 → `nssm restart rpa-log-service`，停机秒级 | junction 切回旧版本目录 + `nssm restart` |
| 前端 | `dist_new` 上传 → 原子重命名替换 `dist`（无需重启服务） | 保留上一版 `dist.bak`，重命名切回 |
| 数据库 | `initialize_schema` 幂等建表；破坏性变更另附手工 SQL 脚本并在停机窗口执行 | 恢复最近一日 mysqldump 备份 |

### 11.5 备份与监控

- **备份**：每日 mysqldump（保留 30 天）+ `files\` 目录可选 robocopy 到第二块盘（`robocopy D:\rpa-log-service\files E:\backup\files /MIR /XO`）；
- **健康检查**：`GET /healthz` 返回 DB 连通性与磁盘水位；可用 Task Scheduler 每 5 分钟探测，失败时写 Windows 事件日志或对接通知（思路同 `app.core.integrations.notifier`）；
- **服务恢复**：`services.msc` 中将 `rpa-log-service`、MySQL 服务的失败恢复设为“第一次失败：重新启动服务”；NSSM 自带崩溃重启兜底。

### 11.6 备选：Nginx for Windows 前置（可选）

若后续需要 80/443 入口、gzip 或多后端，可在前面加一层 Nginx for Windows（同样 NSSM 注册）：

```nginx
server {
    listen 80;
    location /api/    { proxy_pass http://127.0.0.1:9000; }
    location /files/  { proxy_pass http://127.0.0.1:9000; }
    location /healthz { proxy_pass http://127.0.0.1:9000; }
    location /        { root D:/rpa-log-service/web/dist; try_files $uri /index.html; }
}
```

一期内网工具不建议引入，减少一个运维对象。

### 11.7 一键部署（暂缓）

> 一键部署套件已按需移除，本节仅保留方案结论：单机承载 MySQL / Redis / 服务端 / 前端；发布模型为 `releases\<服务>-<时间戳>` 版本目录 + `current-<服务>` junction 切链（切链即发布、切回即回滚）+ NSSM 重启与健康检查失败自动回滚；服务端使用独立精简依赖，不安装业务机的浏览器自动化依赖。
>
> 需要部署时：按 §11.3 手工步骤执行，或基于本节结论重建脚本（历史实现可从 git 历史找回）。

## 12. 附录：接口示例

**创建执行记录**

```json
POST /api/v1/executions
{
  "rpaMessageId": "MSG202501150001",
  "jobId": "ZIMUSBKK123456",
  "queueName": "QTCT_ZIM_SI",
  "deviceName": "RPA-DEV-01",
  "taskId": "98123",
  "startedAt": "2025-01-15 10:23:45",
  "customerCode": "QTCT", "carrierCode": "ZIM", "businessCode": "SI"
}
→ { "code": 0, "data": { "executionId": 1024, "status": "RUNNING" } }
```

**列表查询（GET params）**

```
GET /api/v1/executions?jobId=ZIM&status=FAILED&page=1&pageSize=10
→ { "code": 0, "data": { "total": 17, "list": [
    { "executionId": 1024, "rpaMessageId": "MSG202501150001", "jobId": "ZIMUSBKK123456",
      "queueName": "QTCT_ZIM_SI", "deviceName": "RPA-DEV-01", "status": "FAILED",
      "createTime": "2025-01-15 10:23:45", "finishedAt": "2025-01-15 10:26:57",
      "durationSeconds": 192, "remark": "ZIM SI 填单失败：…", "logCount": 10 }
] } }
```

**批量日志（POST Body）**

```json
POST /api/v1/logs/batch
{ "executionId": 1024, "logs": [
  { "seq": 1, "level": "INFO",    "message": "收到队列消息，开始执行任务 queue=QTCT_ZIM_SI", "sourceFile": "app/queue/consumer.py", "sourceLine": 48, "logTime": "2025-01-15 10:23:45.123" },
  { "seq": 2, "level": "SUCCESS", "message": "登录 ZIM 船司门户成功",                       "sourceFile": "app/spider/ZIM/common/login.py", "sourceLine": 57, "logTime": "2025-01-15 10:24:20.456" }
] }
```

**结束上报（POST Body）**

```json
POST /api/v1/executions/finish
{
  "executionId": 1024,
  "status": "FAILED",
  "remark": "ZIM SI 填单失败：【集装箱数】元素不存在：#container-no；等待=5s",
  "failImgUrl": "https://fec.cgofish.com/rpa/shots/2025/01/15/abc123.png",
  "finishedAt": "2025-01-15 10:26:57",
  "durationSeconds": 192,
  "recordFiles": [
    { "type": "SCREEN_RECORDING_FILE", "mediaType": "VIDEO", "fileName": "QTCT_ZIM_SI_102402.mp4", "url": "http://192.168.1.50:9000/files/2025/01/f3a9c8e2.mp4", "storage": "LAN", "fileSize": 9017753 },
    { "type": "SUBMIT_RESULT_SCREENSHOT", "mediaType": "IMAGE", "fileName": "si_submit_error.png", "url": "https://fec.cgofish.com/rpa/shots/2025/01/15/def456.png", "storage": "OSS" }
  ]
}
```
