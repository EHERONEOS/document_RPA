# Wise RPA 项目启动说明

本文说明如何在 macOS 和 Windows 本地从安装 uv 开始，完成依赖安装并启动本项目。

项目根目录：

```bash
/Users/wangchao/weisi_code/document_RPA
```

Windows 下请替换为你实际克隆或放置项目的目录，例如：

```powershell
D:\workspace\document_RPA
```

## 1. 环境要求

- Python：项目声明版本为 `3.12.12`
- 包管理工具：`uv`
- 队列模式：需要可访问 RabbitMQ
- 真实浏览器自动化：需要安装可用的 Chromium/Chrome，并将 `ENABLE_BROWSER=true`

默认 `.env.example` 中 `ENABLE_BROWSER=false`，本地调试时不会启动真实浏览器，只会跑通消息解析、路由和业务骨架。

## 2. macOS 启动方式

### 2.1 安装 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

如果命令执行后当前终端找不到 `uv`，重开终端，或按安装器提示把 uv 所在目录加入 `PATH`。

检查安装：

```bash
uv --version
```

### 2.2 进入项目目录

```bash
cd /Users/wangchao/weisi_code/document_RPA
```

### 2.3 安装 Python 3.12.12

```bash
uv python install 3.12.12
```

### 2.4 安装项目依赖

```bash
uv sync
```

`uv sync` 会根据 `pyproject.toml` 创建/同步 `.venv`，并安装 `DrissionPage`、`funboost`、`python-dotenv` 等依赖。

### 2.5 创建本地环境变量文件

```bash
cp .env.example .env
```

按需要修改 `.env`：

```dotenv
APP_ENV=local
RPA_QUEUES=FL_WHL_SI
RABBITMQ_HOST=192.168.60.106
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
RABBITMQ_VIRTUAL_HOST=/
RABBITMQ_DEAD_LETTER_EXCHANGE=dlx_exchange
RABBITMQ_DEAD_LETTER_ROUTING_KEY=dlx_routing_key
BROWSER_PORT_START=9000
BROWSER_PORT_END=9200
DOWNLOAD_DIR=runtime/downloads
BROWSER_USER_DATA_DIR=runtime/browser_profiles
ENABLE_RECORD=false
ENABLE_BROWSER=false
```

如果要接管或启动真实浏览器，把：

```dotenv
ENABLE_BROWSER=true
```

### 2.6 本地模板调试启动

不依赖 RabbitMQ，直接读取本地消息模板：

```bash
uv run python -m app.dev.local_runner --message /Users/wangchao/weisi_code/document_RPA/mssage_list/msg_demo.json
```

预期行为：

- 读取 `mssage_list/msg_demo.json`
- 构建 `TaskContext`
- 解析队列名 `FL_WHL_SI`
- 路由到 `app/Spider/WHL/FL_WHL.py` 中的 `fl_whl_si`
- 本地模式跳过处理中通知、录屏和结果回传

### 2.7 队列 Worker 启动

确认 `.env` 中 RabbitMQ 配置可用后启动：

```bash
uv run python -m app.main
```

Worker 会读取：

```dotenv
RPA_QUEUES=FL_WHL_SI
```

并注册对应队列消费者。

## 3. Windows 启动方式

以下命令建议在 PowerShell 中执行。

### 3.1 安装 uv

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安装完成后重开 PowerShell，然后检查：

```powershell
uv --version
```

也可以使用 winget：

```powershell
winget install --id=astral-sh.uv -e
```

### 3.2 进入项目目录

示例：

```powershell
cd D:\workspace\document_RPA
```

### 3.3 安装 Python 3.12.12

```powershell
uv python install 3.12.12
```

### 3.4 安装项目依赖

```powershell
uv sync
```

### 3.5 创建本地环境变量文件

```powershell
Copy-Item .env.example .env
```

按需修改 `.env`。本地骨架调试建议保持：

```dotenv
ENABLE_BROWSER=false
```

如果要运行真实浏览器自动化，改为：

```dotenv
ENABLE_BROWSER=true
```

### 3.6 本地模板调试启动

```powershell
uv run python -m app.dev.local_runner --message .\mssage_list\msg_demo.json
```

### 3.7 队列 Worker 启动

确认 RabbitMQ 可访问后执行：

```powershell
uv run python -m app.main
```

## 4. 常用验证命令

运行单元测试：

```bash
uv run python -m unittest discover -s tests -v
```

运行本地调试：

```bash
uv run python -m app.dev.local_runner --message ./mssage_list/msg_demo.json
```

检查 uv 管理的 Python：

```bash
uv python list
```

检查依赖环境：

```bash
uv pip list
```

## 5. 启动入口说明

- 本地调试入口：`app.dev.local_runner`
- 队列 Worker 入口：`app.main`
- 消息解析：`app/queue/message.py`
- 船司路由：`app/core/task/dispatcher.py`
- WHL 路由表：`app/Spider/WHL/router.py`
- FL + WHL + SI 入口：`app/Spider/WHL/FL_WHL.py`

## 6. 注意事项

- `uv run` 会在运行命令前自动同步项目环境，日常启动优先使用 `uv run ...`。
- 第一次运行 `uv sync` 会下载依赖，网络不可用时会失败。
- 队列模式依赖 RabbitMQ；只想验证业务骨架时优先使用本地模板调试命令。
- `ENABLE_BROWSER=false` 时不会启动真实浏览器，适合开发路由、消息解析和业务骨架。
- `ENABLE_BROWSER=true` 时会尝试使用 DrissionPage 启动或接管 Chromium/Chrome。

## 7. 参考

- uv 安装文档：https://docs.astral.sh/uv/getting-started/installation/
- uv 项目运行命令：https://docs.astral.sh/uv/concepts/projects/run/
- uv 同步依赖说明：https://docs.astral.sh/uv/concepts/projects/sync/
