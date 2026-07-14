# Wise RPA Code Wiki

## 1. 项目概览

`wise-rpa` 是一个面向船司网站自动化填单的分布式 RPA Worker 项目。项目以 RabbitMQ 队列消息为任务来源，通过 `funboost` 启动多个消费者，从消息中解析客户、船司、业务类型，再动态路由到对应船司和业务实现，最终使用 `DrissionPage` 接管或启动浏览器完成登录、查询、填单、校验、截图/录屏和结果回传。

项目当前主要覆盖以下方向：

- 队列驱动的 RPA 任务消费。
- 按 `客户_船司_业务` 队列名动态分发。
- 基于 `DrissionPage` 的浏览器自动化能力。
- 船司级公共能力与客户级业务入口拆分。
- 任务生命周期、异常、结果回传、通知后台、截图录屏等通用基础设施。
- 本地模板消息调试入口。

项目描述来自 `pyproject.toml`：`Distributed RPA workers for carrier document automation`。

## 2. 技术栈与依赖

### 2.1 运行环境

- Python：`3.12.12`
- 包管理建议：项目需求文档中提到使用 `uv` 搭建虚拟环境。
- 操作模式：队列 Worker + 本地消息调试。

### 2.2 核心依赖

定义位置：`pyproject.toml`

| 依赖 | 作用 |
| --- | --- |
| `DrissionPage` | 浏览器自动化、页面操作、接口监听、截图、录屏。 |
| `funboost>=54.8` | 队列消费、发布、重试和死信队列能力。 |
| `python-dotenv` | 环境变量加载支持，项目当前配置读取主要通过 `os.getenv`。 |
| `requests` | 后台通知接口调用。 |
| `opencv-python` | 录屏帧转 mp4 的备用能力。 |
| `numpy` | 图像处理相关基础依赖，当前代码中尚未直接大量使用。 |

## 3. 目录结构

```text
.
├── app
│   ├── main.py
│   ├── config
│   │   ├── settings.py
│   │   ├── rabbitmq.py
│   │   ├── queue_config.py
│   │   └── types.py
│   ├── queue
│   │   ├── consumer.py
│   │   ├── booster.py
│   │   ├── message.py
│   │   ├── rabbitmq.py
│   │   └── publisher.py
│   ├── core
│   │   ├── task
│   │   ├── browser
│   │   ├── page
│   │   ├── integrations
│   │   └── logging
│   ├── Spider
│   │   ├── WHL
│   │   └── ZIM
│   └── dev
├── doc
│   ├── 设计需求文档.md
│   └── CodeWiki.md
├── mssage_list
│   └── msg_demo.json
├── .env.example
├── pyproject.toml
├── funboost_config.py
└── nb_log_config.py
```

## 4. 分层架构

项目可以按以下层次理解：

```text
外部 RabbitMQ 队列
        │
        ▼
app.main
        │
        ▼
queue.consumer.start_consumers
        │
        ▼
queue.message.build_task_context
        │
        ▼
core.task.dispatcher.dispatch_context
        │
        ▼
Spider.{船司}.router.dispatch
        │
        ▼
客户/船司/业务 Task 类
        │
        ▼
BaseRpaTask.run 生命周期
        │
        ├── 通知后台处理中
        ├── 启动/接管浏览器
        ├── 初始化 DOM、HTTP、截图、录屏工具
        ├── 登录船司网站
        ├── 执行业务填单
        ├── 回传成功结果
        └── 异常时回传失败结果
```

### 4.1 配置层

位置：`app/config`

负责从环境变量读取运行配置，包括：

- 运行环境。
- 要监听的 RPA 队列列表。
- RabbitMQ 连接信息。
- RabbitMQ 队列声明参数和死信配置。
- 浏览器端口范围。
- 下载目录和浏览器用户目录。
- 是否启用录屏、浏览器。

### 4.2 队列层

位置：`app/queue`

负责将 `funboost` 与项目业务生命周期连接起来：

- 为每个队列创建消费者。
- 兼容不同消息入参格式。
- 解析消息为 `TaskContext`。
- 定义默认消费者参数。
- 扩展 RabbitMQ Publisher，使队列具备死信交换机配置。

### 4.3 任务核心层

位置：`app/core/task`

负责 RPA 任务生命周期抽象：

- `TaskContext` 保存单条消息的上下文。
- `BaseRpaTask` 定义任务运行主流程。
- `TaskResult` 定义结果回传结构。
- `dispatch_context` 根据船司动态加载 router。
- `errors.py` 定义业务异常层级。

### 4.4 浏览器与页面工具层

位置：`app/core/browser`、`app/core/page`

负责浏览器启动、端口分配、页面操作、接口监听、截图、录屏等通用能力。

### 4.5 外部集成层

位置：`app/core/integrations`

负责与外部系统交互：

- 通知后台任务进入处理中。
- 回传 RPA 执行结果。
- 预留 OSS 上传能力。
- 预留验证码识别能力。

### 4.6 船司业务层

位置：`app/Spider`

按船司拆分目录，每个船司目录中再区分：

- 船司公共基类。
- 通用业务流程。
- 客户定制入口。
- 路由表。
- 页面选择器配置。

当前已有船司：

- `WHL`：万海相关任务骨架。
- `ZIM`：以星相关 SI 流程实现雏形。

### 4.7 开发调试层

位置：`app/dev`

提供基于本地 JSON 消息模板直接调试业务的入口，便于不启动队列消费者时验证业务流程。

## 5. 启动入口与运行流程

### 5.1 队列 Worker 入口

入口文件：`app/main.py`

核心流程：

1. 调用 `Settings.from_env()` 读取环境变量。
2. 获取 `settings.rpa_queues`。
3. 调用 `start_consumers(settings.rpa_queues)` 为每个队列启动消费者。

运行方式：

```bash
python3 -m app.main
```

如果使用 `uv`：

```bash
uv run python -m app.main
```

### 5.2 本地调试入口

入口文件：`app/dev/local_runner.py`

运行方式：

```bash
python3 -m app.dev.local_runner --message mssage_list/msg_demo.json
```

如果使用 `uv`：

```bash
uv run python -m app.dev.local_runner --message mssage_list/msg_demo.json
```

本地调试入口会：

1. 读取本地 JSON 消息。
2. 构建 `TaskContext`。
3. 设置 `runtime_mode="local"`。
4. 默认关闭处理中通知和录屏。
5. 调用统一分发器进入真实业务路由。

## 6. 环境变量说明

示例文件：`.env.example`

| 变量 | 默认/示例 | 说明 |
| --- | --- | --- |
| `APP_ENV` | `local` | 当前运行环境。处理中通知里 `prod` 和 `local` 都会使用生产回调地址。 |
| `RPA_QUEUES` | `FL_WHL_SI,FL_WHL_VGM,FL_ZIM_SI,FL_ZIM_VGM` | 需要监听的队列列表，逗号分隔。 |
| `RABBITMQ_HOST` | `192.168.60.106` | RabbitMQ 地址。 |
| `RABBITMQ_PORT` | `5672` | RabbitMQ 端口。 |
| `RABBITMQ_USER` | `guest` | RabbitMQ 用户名。 |
| `RABBITMQ_PASSWORD` | `guest` | RabbitMQ 密码。 |
| `RABBITMQ_VIRTUAL_HOST` | `/` | RabbitMQ virtual host。 |
| `RABBITMQ_DEAD_LETTER_EXCHANGE` | `dlx_exchange` | 消费队列死信交换机。 |
| `RABBITMQ_DEAD_LETTER_ROUTING_KEY` | `dlx_routing_key` | 消费队列死信 routing key。 |
| `RABBITMQ_QUEUE_DURABLE` | `true` | 队列是否持久化。 |
| `RABBITMQ_QUEUE_PASSIVE` | `false` | 队列声明是否 passive。 |
| `RABBITMQ_NO_ACK` | `false` | 是否自动 ack。 |
| `BROWSER_PORT_START` | `9000` | 浏览器调试端口起始值。 |
| `BROWSER_PORT_END` | `9200` | 浏览器调试端口结束值。 |
| `DOWNLOAD_DIR` | `runtime/downloads` | 下载文件目录。 |
| `BROWSER_USER_DATA_DIR` | `runtime/browser_profiles` | 浏览器用户数据目录。 |
| `ENABLE_RECORD` | `false` | 是否默认启用录屏。 |
| `ENABLE_BROWSER` | `true` | 是否启用真实浏览器；为 false 时使用空页面对象。 |
| `ENABLE_REMOTE_KILL_TASK` | `false` | 是否启用 funboost 远程杀任务能力。 |

## 7. 队列命名与消息协议

### 7.1 队列命名规则

队列名格式：

```text
客户代码_船司代码_业务代码
```

示例：

```text
FL_WHL_SI
FL_WHL_VGM
FL_ZIM_SI
FL_ZIM_VGM
```

解析逻辑位于 `app/core/task/context.py`：

- `customer_code`：客户代码，如 `FL`。
- `carrier_code`：船司代码，如 `WHL`、`ZIM`。
- `business_code`：业务代码，如 `SI`、`VGM`。

如果队列名不是三段式，会抛出 `QueueNameError`。

### 7.2 消息结构

示例文件：`mssage_list/msg_demo.json`

核心字段：

```json
{
  "task": {
    "rpaMessageId": "2054390608361074688",
    "rpaTaskTopic": "FL_ZIM_SI",
    "websiteInfo": {
      "websiteType": "ZIM",
      "websiteAccount": "账号",
      "websitePassword": "密码",
      "websiteUserName": "用户名"
    },
    "content": {
      "jobNo": "订舱号或业务号",
      "shp_name": "发货人",
      "totalContainers": []
    }
  }
}
```

`build_task_context` 会校验：

- `task` 必须是对象。
- `task.rpaTaskTopic` 不能为空。
- `task.websiteInfo` 必须是对象。
- `task.content` 必须是对象。
- `task.rpaMessageId` 不能为空。

同时会深拷贝 `content` 到 `remain_content`，用于追踪哪些字段尚未处理。

## 8. 核心模块详解

### 8.1 `app/main.py`

职责：队列 Worker 入口。

关键函数：

- `main()`：读取配置并启动消费者。

依赖关系：

- `Settings.from_env()`
- `start_consumers()`

### 8.2 `app/config/settings.py`

职责：应用级运行配置。

关键类：

#### `Settings`

字段：

- `app_env`
- `rpa_queues`
- `rabbitmq`
- `browser_port_start`
- `browser_port_end`
- `download_dir`
- `browser_user_data_dir`
- `enable_record`
- `enable_browser`

关键方法：

- `from_env()`：从环境变量构建不可变配置对象。

### 8.3 `app/config/rabbitmq.py`

职责：RabbitMQ 连接与队列声明配置。

关键类：

#### `RabbitmqSettings`

关键属性/方法：

- `url`：拼接 AMQP URL。
- `from_env()`：读取 RabbitMQ 环境变量。
- `to_broker_exclusive_config()`：生成 funboost broker 专属配置，包括死信交换机、routing key、durable、passive、no_ack 等。

### 8.4 `app/queue/consumer.py`

职责：队列消费者启动与单条消息处理。

关键函数：

- `handle_message(raw_message)`：将原始消息构建为上下文后分发。
- `build_raw_message(message=None, task=None, **kwargs)`：兼容 funboost 传入整包消息、`task` 参数或 kwargs 的不同形式。
- `start_consumers(queue_names)`：为每个队列创建 `@boost` 消费函数，并调用 `consume.consume()` 启动消费。

设计要点：

- 每个队列动态创建一个消费者函数。
- 消费参数由 `RpaBoosterParams` 统一定义。
- 最终所有消息都会进入 `handle_message`。

### 8.5 `app/queue/booster.py`

职责：项目默认 funboost 消费者参数。

关键类：

#### `RpaBoosterParams`

重要配置：

- `broker_kind = BrokerEnum.RABBITMQ_AMQPSTORM`
- `qps = 1`
- `concurrent_num = 1`
- `is_push_to_dlx_queue_when_retry_max_times = True`
- `publisher_override_cls = RabbitmqPublisherWithDlx`
- `is_support_remote_kill_task` 由 `ENABLE_REMOTE_KILL_TASK` 控制。

### 8.6 `app/queue/message.py`

职责：将原始消息转换为任务上下文。

关键函数：

- `_require_dict(value, name)`：校验字段必须是对象。
- `build_task_context(...)`：构建 `TaskContext`。

输出对象：`TaskContext`。

### 8.7 `app/core/task/context.py`

职责：定义任务上下文与队列名解析。

关键类：

#### `TaskContext`

表示一条 RPA 消息的完整运行上下文。

字段包括：

- 原始消息：`raw_message`
- 任务对象：`task`
- 队列名：`queue_name`
- 消息 ID：`rpa_message_id`
- 客户/船司/业务代码：`customer_code`、`carrier_code`、`business_code`
- 账号信息：`website_info`
- 填单内容：`content`
- 未处理字段副本：`remain_content`
- 运行模式和开关：`runtime_mode`、`enable_notify`、`enable_result_publish`、`enable_record`

关键函数：

- `parse_queue_name(queue_name)`：解析三段式队列名。
- `copy_content(content)`：深拷贝填单内容。

### 8.8 `app/core/task/dispatcher.py`

职责：按船司代码动态加载路由模块。

关键函数：

- `dispatch_context(context)`：根据 `context.carrier_code` 拼出模块名 `app.Spider.{carrier_code}.router`，导入后调用其中的 `dispatch(context)`。

异常：

- 找不到船司路由时抛 `RouteNotFoundError`。
- 路由模块没有 `dispatch` 方法时抛 `RouteNotFoundError`。

### 8.9 `app/core/task/base_task.py`

职责：定义 RPA 任务完整生命周期基类。

关键类：

#### `BaseRpaTask`

类属性：

- `enable_record`：是否默认录屏。
- `incognito`：是否无痕模式。
- `wait_page_load`：是否等待页面完整加载。
- `fail_on_unfilled_fields`：是否因未填字段失败。
- `booking_no`：业务单号。
- `FILL_HANDLERS`：字段类型到填写方法的映射。

关键方法：

- `run()`：任务生命周期主入口。
- `should_record()`：判断是否录屏，优先使用 `context.enable_record`。
- `login()`：船司登录抽象方法。
- `execute_business()`：业务填单抽象方法。
- `mark_field_done(field_name)`：字段处理成功后从 `remain_content` 删除。
- `check_unfilled_fields()`：检查剩余未处理字段。
- `get_unfilled_fields()`：返回未处理字段列表。
- `raise_if_unfilled_fields(stage)`：发现未处理字段时抛出 `UnfilledFieldError`。
- `_fill_if_present(locator, field_name, source=None, timeout=2)`：字段有值时填入 input。
- `_select_if_present(locator, field_name, source=None, timeout=2)`：字段有值时选择 select。
- `_fill_or_select_if_present(field_type, locator, field_name, source=None, timeout=2)`：按字段类型分派填写。
- `verify_from_value(field_type, locator, field_name, source=None)`：校验页面字段值和源数据一致。

`run()` 生命周期详细步骤：

1. 如果启用通知，则调用 `ProcessingNotifier.notify_processing`。
2. 通过 `BrowserManager.start` 启动或接管浏览器。
3. 初始化 `DomHelper`、`HttpHelper`、`Screenshot`、`Recorder`。
4. 调用 `login()`。
5. 如果需要录屏，则启动录屏。
6. 调用 `execute_business()` 执行业务。
7. 构造成功 `TaskResult` 并回传。
8. 捕获异常时构造失败 `TaskResult` 并回传。
9. finally 中停止录屏。
10. 当前代码结束后保留浏览器进程，便于后续接管。

### 8.10 `app/core/task/result.py`

职责：定义任务结果结构。

关键类：

#### `TaskResult`

字段：

- `task_id`
- `success`
- `rpaMessageId`
- `saveType`
- `img`
- `code`
- `executeRecordFiles`
- `remark`
- `attachments`
- `content`

关键方法：

- `to_payload()`：转换为普通字典。

### 8.11 `app/core/task/errors.py`

职责：定义统一异常层级。

主要异常：

| 异常 | 语义 |
| --- | --- |
| `RpaError` | RPA 基础异常，支持错误码。 |
| `MessageParseError` | 消息结构解析失败。 |
| `QueueNameError` | 队列名格式错误。 |
| `RouteNotFoundError` | 船司或业务路由不存在。 |
| `BrowserStartError` | 浏览器启动或接管失败。 |
| `LoginError` | 登录失败。 |
| `ElementNotFoundError` | 页面元素不存在。 |
| `BusinessError` | 业务流程异常。 |
| `FormValidationError` | 表单值校验失败。 |
| `UnfilledFieldError` | 存在未处理字段。 |

### 8.12 `app/core/browser/manager.py`

职责：管理浏览器启动、接管、用户目录和下载目录。

关键类：

#### `LocalPage`

本地骨架运行时使用的空页面对象，仅提供：

- `ele()`：返回 `None`。
- `eles()`：返回空列表。

当 `ENABLE_BROWSER=false` 时使用。

#### `BrowserManager`

关键方法：

- `build_profile_name(context)`：使用 `websiteUserName` 或 `websiteAccount` 加船司代码生成浏览器 profile 名，如 `{用户名}_{船司}`。
- `build_options(context, task)`：构建 `BrowserOptions`，包括端口、用户目录、下载目录、无痕、加载模式。
- `start(context, task)`：启动或接管 DrissionPage Chromium，并返回 `latest_tab`。
- `close()`：当前实现只记录日志，不主动关闭浏览器。

设计要点：

- 同一账号和船司会复用固定浏览器用户目录。
- 浏览器端口由 `BrowserPortRegistry` 按 profile 固定分配。
- 下载目录按队列名隔离。

### 8.13 `app/core/browser/options.py`

职责：定义浏览器默认参数和偏好配置。

关键内容：

- `DEFAULT_BROWSER_ARGS`：启动参数，如最大化、忽略证书错误、禁用密码管理、禁用通知、禁用下载气泡等。
- `DEFAULT_PREFS`：Chrome prefs，如默认下载目录、禁用下载提示、禁用密码保存、允许自动下载等。
- `BrowserOptions`：浏览器启动参数数据类。

### 8.14 `app/core/browser/port.py`

职责：维护浏览器 profile 到端口的固定映射。

关键类：

#### `BrowserPortRegistry`

关键方法：

- `resolve_port(profile_name)`：如果 profile 已有端口则复用，否则在端口范围中找一个未使用端口并保存。
- `_load()`：读取 JSON 映射文件。
- `_save(data)`：写入 JSON 映射文件。

端口映射文件默认位于：

```text
runtime/browser_profiles/port_registry.json
```

### 8.15 `app/core/page/dom.py`

职责：封装页面 DOM 操作。

关键类：

#### `DomHelper`

关键方法：

- `_find(locator, name=None, required=True, timeout=2)`：定位元素，不存在且 required 时抛 `ElementNotFoundError`。
- `click(...)`：点击元素。
- `click_all(...)`：点击所有匹配元素。
- `input_text(...)`：输入文本并清空原值。
- `select(...)`：按 text/value/index 选择 select 选项。
- `get_text(...)`：读取文本。
- `get_value(...)`：读取 input value。
- `get_select_value(...)`：读取 select 当前值或文本。
- `get_select_text(...)`：读取 select 当前展示文本。
- `in_frame(...)`：进入 iframe 并返回新的 `DomHelper`。

### 8.16 `app/core/page/http.py`

职责：基于 DrissionPage 监听页面接口。

关键类：

#### `HttpHelper`

关键方法：

- `wait_api_finished(url, trigger=None, timeout=30, method=("GET", "POST"), res_type=True, is_regex=False)`：开始监听接口，执行触发动作，等待响应并返回响应 body。

适用场景：点击查询按钮后等待列表接口返回，再基于接口数据继续流程。

### 8.17 `app/core/page/screenshot.py`

职责：页面截图和元素截图。

关键类：

#### `Screenshot`

关键方法：

- `bind_page(page)`：绑定页面对象。
- `page_shot(order_no, order_type, is_error=True, full_page=True)`：保存整页截图。
- `element_shot(order_no, order_type, target, is_error=False, locator=None, timeout=2)`：保存元素截图。
- `build_screenshot_path(...)`：生成截图路径。
- `build_screenshot_name(...)`：生成截图文件名。

默认保存目录：

```text
runtime/screenshots
```

命名规则：

```text
error_{order_no}_{order_type}_{YYYYMMDD_HHMMSS}.png
执行截图_{order_no}_{order_type}_{YYYYMMDD_HHMMSS}.png
```

### 8.18 `app/core/page/recorder.py`

职责：录屏控制。

关键类：

#### `Recorder`

关键方法：

- `bind_page(page)`：绑定页面对象。
- `start()`：启动 DrissionPage screencast。
- `stop(queue_name="", jobNo="")`：停止录屏并生成视频名。
- `build_record_name(order_no, order_type, time_text=None)`：生成录屏文件基础名。
- `_frames_to_video(frame_dir, video_path, fps=5)`：将帧目录合成为 mp4，依赖 `opencv-python`。

默认保存目录：

```text
runtime/records
```

### 8.19 `app/core/integrations/notifier.py`

职责：通知后台某条 RPA 消息进入处理中状态。

关键类：

#### `ProcessingNotifier`

关键方法：

- `notify_processing(context)`：使用上下文中的 `rpa_message_id` 和 `queue_name` 通知后台。
- `send_rpa_mq_message_info(message_id, queue_name)`：调用后台接口。

回调地址：

- 测试：`http://gcp.wise.cn/v1/rpa-mq-message-info/callback`
- 生产：`https://gcp.56gpt.com/v1/rpa-mq-message-info/callback`

当前逻辑中，`APP_ENV=prod` 或 `APP_ENV=local` 都会使用生产地址。

### 8.20 `app/core/integrations/publisher.py`

职责：将任务结果回传到文档更新队列。

关键类：

#### `ResultPublisher`

关键常量：

- `DOCUMENT_UPDATE = "gcp_document_update"`
- `RETRY_TIMES = 1`

关键方法：

- `publish_result(result)`：构建回传数据并发送到队列。
- `build_reply_data(result)`：将 `TaskResult` 转为后台期望结构。
- `send_msg_to_queue(data, delay=0)`：通过 funboost publisher 发送消息。
- `_resolve_code(result)`：解析结果 code。
- `_build_status_remarks(result)`：构建状态备注。

回传消息外层结构：

```json
{
  "task": {
    "id": "任务ID",
    "success": true,
    "code": 200,
    "rpaMessageId": "消息ID",
    "saveType": 1,
    "img": "截图地址",
    "executeRecordFiles": "录屏地址",
    "statusRemarks": {
      "message": "备注"
    }
  }
}
```

### 8.21 `app/core/integrations/oss.py`

职责：OSS 能力预留。

当前主要提供：

- `OssClient.local_screenshot_path()`：返回本地截图路径。

### 8.22 `app/core/integrations/captcha.py`

职责：验证码识别能力预留。

当前主要提供：

- `CaptchaSolver.solve()`：验证码解析入口。

### 8.23 `app/core/logging/logger.py`

职责：项目日志输出。

关键内容：

- `log()`、`info()`、`warn()`、`error()` 函数。
- `Logger` 类，提供同名实例方法。
- 日志中会包含时间、调用位置和等级，并带有颜色输出。

## 9. 船司模块详解

## 9.1 WHL 模块

目录：`app/Spider/WHL`

### 文件职责

| 文件 | 职责 |
| --- | --- |
| `base.py` | WHL 船司公共能力。 |
| `WHL_SI.py` | WHL 通用 SI 业务流程骨架。 |
| `WHL_VGM.py` | WHL 通用 VGM 业务流程骨架。 |
| `FL_WHL.py` | FL 客户在 WHL 下的业务入口与定制类。 |
| `router.py` | WHL 队列路由表。 |

### `WhlBaseTask`

继承：`BaseRpaTask`

职责：WHL 船司公共能力。

当前状态：

- 设置 `carrier_code = "WHL"`。
- `login()` 当前直接抛出 `LoginError("登录失败")`，表示 WHL 登录尚未真正实现。

### `WhlSiTask`

继承：`WhlBaseTask`

职责：WHL 通用 SI 业务流程。

关键方法：

- `execute_business()`：依次调用订舱号、发货人、收货人、货物信息、保存/提交。
- `fill_booking_no()`：标记 `bookingNo` 已处理。
- `fill_shipper()`：标记发货人相关字段已处理。
- `fill_consignee()`：标记收货人相关字段已处理。
- `fill_goods()`：标记货物描述和毛重已处理。
- `submit_or_save()`：保存或提交入口。

当前状态：多为骨架逻辑，主要通过 `mark_field_done` 模拟字段完成。

### `FlWhlSiTask`

继承：`WhlSiTask`

职责：FL 客户的 WHL SI 个性化任务。

当前只覆盖：

- `fill_shipper()`：保留客户个性化入口，并调用父类逻辑。

### WHL 路由

`app/Spider/WHL/router.py`

```text
FL_WHL_SI  -> fl_whl_si
FL_WHL_VGM -> fl_whl_vgm
```

## 9.2 ZIM 模块

目录：`app/Spider/ZIM`

### 文件职责

| 文件 | 职责 |
| --- | --- |
| `base.py` | ZIM 船司公共登录、订舱查询能力。 |
| `ZIM_SI.py` | ZIM 通用 SI 填单流程。 |
| `FL_ZIM.py` | FL 客户在 ZIM 下的业务入口。 |
| `router.py` | ZIM 队列路由表。 |
| `selectors.py` | ZIM 页面元素定位器和字段映射。 |

### `ZimBaseTask`

继承：`BaseRpaTask`

职责：ZIM 船司公共能力。

关键属性：

- `carrier_code = "ZIM"`
- `login_url = "https://cis.zim-logistics.com.cn/Account/Login"`
- `index_url = "https://cis.zim-logistics.com.cn/"`
- `siteKey`：验证码相关站点 key。

关键方法：

- `_ensure_browser_ready()`：检查当前 page 是否支持 `get`、`post`、`change_mode`，否则说明不是可用真实浏览器页面。
- `login()`：执行 ZIM 登录。
- `is_login()`：通过当前 URL 是否包含登录页判断是否已登录。
- `query_booking(booking_no)`：进入订舱菜单，监听订舱列表接口，搜索订舱号并返回接口中的订舱行数据。

登录流程：

1. 打开首页。
2. 如果当前已登录，则直接返回。
3. 切换到 session 模式。
4. POST 登录接口，传入账号、密码、OfficeCode、recaptureToken。
5. 登录成功后切回 driver 模式。
6. 再次打开首页并校验登录状态。

### `ZimSiTask`

继承：`ZimBaseTask`

职责：ZIM 通用 SI 业务流程。

关键属性：

- `business_code = "SI"`
- `incognito = False`
- `wait_page_load = False`

初始化逻辑：

- 保存 `context.content` 到 `self.content`。
- 从 `content.jobNo` 设置 `self.booking_no`。
- 标记 `jobNo` 已处理。

关键方法：

- `execute_business()`：执行查询订舱、进入详情页、填写基础字段、填写箱货、检查未填字段、校验表单值。
- `fill_base_fields()`：根据 `selectors.SI_BASE_FILL_FIELDS` 自动填基础字段。
- `fill_containers()`：删除已有箱货行，按 `totalContainers` 添加并填写箱货信息。
- `verify_from()`：按填写配置反向读取页面值并校验。

当前注意事项：

- `execute_business()` 中存在一行测试异常：`raise LoginError("测试异常")`。这会导致后续真实填单逻辑无法执行，当前更像开发调试阶段代码。

### ZIM 选择器与字段映射

文件：`app/Spider/ZIM/selectors.py`

核心设计：使用三元组配置驱动填单：

```text
(字段类型, 页面定位器, content 字段名)
```

基础字段配置：`SI_BASE_FILL_FIELDS`

包括：

- 发货人名称/地址。
- 收货人名称/地址。
- 通知人名称/地址。
- 合约号。
- 付款方式。
- 备注。
- HS Code。
- 包装单位。
- 唛头。
- 货描。
- 提单类型。
- 提单件数。

箱货字段配置：`SI_CONTAINER_FILL_FIELDS`

包括：

- 箱号。
- 封号。
- 尺寸。
- 箱型。
- 件数。
- 毛重。
- 体积。
- 包装单位。

同时派生：

- `SI_BASE_INPUT_FIELDS`
- `SI_BASE_SELECT_FIELDS`
- `SI_CONTAINER_INPUT_FIELDS`
- `SI_CONTAINER_SELECT_FIELDS`

用于避免填写和校验维护两套字段映射。

### `FlZimSiTask`

继承：`ZimSiTask`

职责：FL 客户的 ZIM SI 任务。

当前只设置：

- `incognito = False`

### ZIM 路由

`app/Spider/ZIM/router.py`

```text
FL_ZIM_SI  -> fl_zim_si
FL_ZIM_VGM -> fl_zim_vgm
```

其中：

- `FL_ZIM_SI` 已接入 `FlZimSiTask(context).run()`。
- `FL_ZIM_VGM` 当前抛出 `BusinessError("ZIM VGM 业务暂未实现")`。

## 10. 依赖关系图

### 10.1 运行时调用链

```text
app.main
  └── config.settings.Settings.from_env
  └── queue.consumer.start_consumers
        └── queue.consumer.handle_message
              └── queue.message.build_task_context
                    └── core.task.context.parse_queue_name
              └── core.task.dispatcher.dispatch_context
                    └── Spider.{carrier}.router.dispatch
                          └── Spider.{carrier}.{customer module}.{entry}
                                └── BaseRpaTask.run
                                      ├── ProcessingNotifier.notify_processing
                                      ├── BrowserManager.start
                                      ├── DomHelper
                                      ├── HttpHelper
                                      ├── Screenshot
                                      ├── Recorder
                                      ├── Task.login
                                      ├── Task.execute_business
                                      └── ResultPublisher.publish_result
```

### 10.2 模块依赖关系

```text
config
  └── 被 queue、browser 读取

queue
  ├── 依赖 config.rabbitmq
  ├── 依赖 core.task.dispatcher
  └── 依赖 core.task.context/message

core.task
  ├── 依赖 core.browser
  ├── 依赖 core.page
  ├── 依赖 core.integrations
  └── 被 Spider 业务继承

core.browser
  ├── 依赖 config.settings
  └── 依赖 DrissionPage

core.page
  └── 依赖 DrissionPage 页面能力

core.integrations
  ├── 依赖 requests
  ├── 依赖 funboost
  └── 依赖 queue.rabbitmq

Spider
  ├── 依赖 core.task.BaseRpaTask
  ├── 依赖 core.page.DomHelper/HttpHelper
  └── 由 dispatcher 动态导入
```

## 11. 当前已支持与未完成能力

### 11.1 已具备的基础能力

- 多队列消费者启动。
- 三段式队列名解析。
- 消息协议校验。
- 动态船司路由加载。
- 基础任务生命周期。
- 浏览器 profile、端口、下载目录管理。
- DOM 操作封装。
- 页面接口监听封装。
- 截图、录屏能力封装。
- 后台处理中通知。
- 结果回传队列发布。
- 本地 JSON 消息调试。
- ZIM SI 字段映射驱动填单雏形。

### 11.2 当前明显处于占位或开发阶段的能力

- WHL 登录当前固定抛出登录失败。
- WHL SI 多数字段只是标记完成，未真实操作页面。
- ZIM SI `execute_business()` 中存在测试异常，会中断真实流程。
- ZIM VGM 当前明确未实现。
- OSS 上传当前仅有本地路径占位。
- 验证码识别当前仅有预留类。
- 成功/失败结果中的图片、附件、录屏地址当前仍为固定占位字符串。
- `BrowserManager.close()` 当前不关闭浏览器，只保留进程。

## 12. 关键设计模式

### 12.1 模板方法模式

`BaseRpaTask.run()` 定义通用生命周期，具体船司和业务只需要实现：

- `login()`
- `execute_business()`

这使得不同船司任务可以复用通知、浏览器、录屏、异常捕获、结果回传等通用逻辑。

### 12.2 动态路由模式

`dispatch_context()` 根据 `carrier_code` 动态导入：

```text
app.Spider.{carrier_code}.router
```

每个船司目录内部维护自己的 `ROUTES` 字典，根据完整队列名分发到客户业务入口。

### 12.3 配置驱动填单

ZIM SI 使用 `selectors.SI_BASE_FILL_FIELDS` 和 `selectors.SI_CONTAINER_FILL_FIELDS` 统一维护字段类型、页面定位器和数据字段名。

好处：

- 填写逻辑统一。
- 校验逻辑可复用同一份配置。
- 新增字段时只需要扩展配置。

### 12.4 运行上下文对象

`TaskContext` 将一条消息在运行过程中的所有关键数据集中保存，减少函数之间传参复杂度，也方便后续扩展运行开关和调试模式。

## 13. 如何新增一个船司

假设新增船司代码为 `ABC`。

### 13.1 新建目录

```text
app/Spider/ABC
├── __init__.py
├── base.py
├── ABC_SI.py
├── FL_ABC.py
├── router.py
└── selectors.py
```

### 13.2 实现船司基类

在 `base.py` 中继承 `BaseRpaTask`：

```python
from app.core.task.base_task import BaseRpaTask

class AbcBaseTask(BaseRpaTask):
    carrier_code = "ABC"

    def login(self):
        ...
```

### 13.3 实现业务类

例如 SI：

```python
class AbcSiTask(AbcBaseTask):
    business_code = "SI"

    def execute_business(self):
        ...
```

### 13.4 实现客户入口

例如 FL 客户：

```python
def fl_abc_si(context):
    return FlAbcSiTask(context).run()
```

### 13.5 配置 router

```python
ROUTES = {
    "FL_ABC_SI": fl_abc_si,
}
```

### 13.6 配置环境变量

将新队列加入：

```bash
RPA_QUEUES=FL_ABC_SI
```

## 14. 如何新增一个客户定制流程

假设在已有 ZIM SI 下新增客户 `XX`：

1. 在 `app/Spider/ZIM/XX_ZIM.py` 中定义 `XxZimSiTask(ZimSiTask)`。
2. 只覆盖客户有差异的方法，例如 `fill_base_fields()` 或某个字段处理逻辑。
3. 定义入口函数 `xx_zim_si(context)`。
4. 在 `app/Spider/ZIM/router.py` 的 `ROUTES` 中加入：

```python
"XX_ZIM_SI": xx_zim_si
```

5. 环境变量 `RPA_QUEUES` 增加 `XX_ZIM_SI`。

## 15. 如何新增一个字段

以 ZIM SI 为例：

1. 在 `selectors.py` 中增加页面定位器常量。
2. 在 `SI_BASE_FILL_FIELDS` 或 `SI_CONTAINER_FILL_FIELDS` 中增加三元组：

```python
("input", "#new_field", "new_field")
```

或：

```python
("select", "#new_select", "new_select")
```

3. 确保消息 `task.content` 中包含对应字段。
4. 如果字段填完后不应出现在未处理字段中，必须确保 `_fill_or_select_if_present` 成功调用，或手动调用 `mark_field_done()`。
5. 如果启用表单校验，确保 `verify_from()` 能正确读取该字段。

## 16. 错误处理与结果回传

### 16.1 异常处理策略

`BaseRpaTask.run()` 捕获所有异常，并统一构造失败 `TaskResult`。

失败结果包括：

- `success=False`
- `code=getattr(exc, "code", None)`
- `remark=str(exc)`
- `rpaMessageId=context.rpa_message_id`

### 16.2 结果回传策略

如果 `context.enable_result_publish=True`，无论成功还是失败都会调用：

```text
ResultPublisher.publish_result(result)
```

回传目标队列：

```text
gcp_document_update
```

### 16.3 未填字段追踪

项目使用 `remain_content` 追踪未填字段：

- 初始化时深拷贝 `content`。
- 字段填入成功后调用 `mark_field_done(field_name)` 删除字段。
- 可通过 `raise_if_unfilled_fields(stage)` 强制校验。

## 17. 安全与配置注意事项

### 17.1 密码与账号

队列消息中的 `websiteInfo` 包含网站账号和密码，代码中不应打印完整账号密码，也不应将真实消息样本提交到仓库。

当前示例消息中存在演示账号密码字段，实际生产应使用脱敏示例。

### 17.2 验证码 token

`app/Spider/ZIM/base.py` 中存在硬编码的 `recapture_token`。这类 token 通常具有时效性和安全风险，建议改为：

- 环境变量读取。
- 验证码服务动态解析。
- 或通过安全配置中心下发。

### 17.3 后台回调地址

`APP_ENV=local` 当前会使用生产回调地址。若本地调试不希望影响生产系统，应显式关闭通知或调整环境判断。

本地调试入口中已默认设置：

```text
enable_notify=False
```

## 18. 常用命令

### 18.1 安装依赖

使用 uv：

```bash
uv sync
```

或使用 pip：

```bash
python3 -m pip install -e .
```

### 18.2 启动队列 Worker

```bash
python3 -m app.main
```

使用 uv：

```bash
uv run python -m app.main
```

### 18.3 本地调试消息

```bash
python3 -m app.dev.local_runner --message mssage_list/msg_demo.json
```

使用 uv：

```bash
uv run python -m app.dev.local_runner --message mssage_list/msg_demo.json
```

### 18.4 运行测试

`pyproject.toml` 已配置 pytest：

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

如果后续补充测试目录，可运行：

```bash
pytest
```

当前仓库未发现 `tests` 目录。

## 19. 代码阅读路线

建议按以下顺序阅读项目：

1. `doc/设计需求文档.md`：理解业务目标和设计背景。
2. `pyproject.toml`：理解运行环境和依赖。
3. `.env.example`：理解运行配置。
4. `app/main.py`：理解 Worker 入口。
5. `app/queue/consumer.py`：理解队列消费。
6. `app/queue/message.py` 和 `app/core/task/context.py`：理解消息如何变成上下文。
7. `app/core/task/dispatcher.py`：理解动态路由。
8. `app/core/task/base_task.py`：理解任务生命周期。
9. `app/core/browser/manager.py`：理解浏览器启动和接管。
10. `app/core/page/dom.py`、`app/core/page/http.py`：理解页面操作工具。
11. `app/Spider/ZIM/router.py`、`app/Spider/ZIM/base.py`、`app/Spider/ZIM/ZIM_SI.py`：理解一个较完整船司实现。
12. `app/Spider/WHL`：理解另一个船司的骨架结构。
13. `app/core/integrations/publisher.py`：理解结果回传。

## 20. 维护建议

### 20.1 优先补齐真实业务闭环

建议优先处理：

- 移除 ZIM SI 中的测试异常。
- 完成 WHL 登录。
- 将截图、录屏、附件地址替换为真实上传后地址。
- 完成 OSS 上传实现。
- 完成验证码解析接入。

### 20.2 统一环境隔离

建议明确区分：

- local
- test
- prod

特别是处理中通知、结果回传和 RabbitMQ 配置，应避免本地调试误触生产服务。

### 20.3 增加测试覆盖

可优先为以下纯逻辑模块补测试：

- `parse_queue_name`
- `build_task_context`
- `RabbitmqSettings.to_broker_exclusive_config`
- `BrowserPortRegistry.resolve_port`
- `ResultPublisher.build_reply_data`
- ZIM selector 字段映射完整性。

### 20.4 减少硬编码

建议迁移以下硬编码内容：

- ZIM recapture token。
- 回调 URL。
- 结果图片/附件占位值。
- 部分业务 URL 和 headers。

### 20.5 规范字段命名

当前消息样例中同时存在：

- `bookingNo`
- `jobNo`
- `blNo`
- `commonContent`
- `content`

建议明确各业务中使用哪个字段作为主业务单号，并在各船司任务中保持一致。

## 21. 总结

该项目的核心思想是：用 RabbitMQ 队列承载待处理 RPA 任务，用 `funboost` 作为分布式 Worker 框架，用 `TaskContext` 统一任务上下文，用 `BaseRpaTask` 固化任务生命周期，再按船司和客户拆分具体自动化实现。

当前项目已经搭建了较完整的 RPA Worker 基础框架，包括队列消费、动态路由、浏览器管理、页面工具、结果回传和船司业务分层。业务实现层仍处于迭代中，ZIM SI 已具备较明确的字段配置驱动填单雏形，WHL 侧更多是结构占位。后续重点应放在补齐真实登录与填单逻辑、完善上传/回传链路、强化环境隔离和增加自动化测试。