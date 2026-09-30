# 局域网 Windows 集中部署方案（MySQL + Redis + 前后端 + 多 Agent）

> 目标：在一台 Windows 目标机上集中部署 MySQL、Redis、后端 API 与前端页面；
> 所有 Agent 机器通过局域网连接这台机器，不再各自连本机 127.0.0.1。

---

## 1. 目标架构总览

```
                        ┌─────────────────────────────────────────────┐
                        │        中央 Windows 机（目标机，静态 IP）       │
                        │                                             │
  浏览器访问 ──────────▶ │  前端静态页 + FastAPI 后端  0.0.0.0:8766      │
  http://<中央IP>:8766  │        │                                    │
                        │        ├── MySQL 8.4  127.0.0.1:3306        │
                        │        │   （统一库 rpa_platform，仅本机）      │
                        │        └── Redis 7.4   0.0.0.0:6379          │
                        │            （AOF 持久化，Agent 命令总线）       │
                        └───────▲──────────────▲──────────────────────┘
                                │              │
                     TCP 6379   │              │  TCP 8766
                    （Redis 命令总线）      （RPA 日志上报 /api/agent/...）
                                │              │
        ┌───────────────────────┴──┐        ┌──┴──────────────────────┐
        │  Agent 机 1  app.main    │        │  Agent 机 N  app.main   │
        │  .env 指向中央机 IP        │        │  .env 指向中央机 IP      │
        └──────────────────────────┘        └─────────────────────────┘
                │                                       │
                └──────────▶ RabbitMQ（沿用现有 Nacos 下发配置，不变）◀──────────┘
```

关键事实（已按当前代码核实）：

| 组件 | 说明 |
|---|---|
| MySQL/Redis | `queue_control_platform/docker/compose.yml`，MySQL 8.4 + Redis 7.4（AOF），Docker volume 持久化 |
| 建库建表 | **无需手工执行 SQL**。后端启动时幂等自动建表：`repository.initialize_schema()` 建 5 张平台表 + `init_rpa_schema()` 建 5 张 `rpa_*` 日志表；`docker/initdb/01-init.sql` 首次起容器时自动建 `rpa_platform` 库和 `queue_control` 账号 |
| 后端 | `uv run python -m queue_control_platform.server.main`，监听 `QUEUE_CONTROL_HOST:QUEUE_CONTROL_PORT`（默认 0.0.0.0:8766） |
| 前端 | `rpa-log-web` 构建产物输出到 `queue_control_platform/dist`，由后端 8766 根路径直接托管，**无需单独部署 nginx** |
| Agent | `uv run python -m app.main`；**Agent 不直连 MySQL**，只需要 Redis + 设备 ID/令牌 + RabbitMQ（Nacos 下发） |
| 日志上报 | Agent 通过 `RPA_LOG_SERVICE_URL=http://<中央IP>:8766` 上报 |
| 录屏文件 | Copyparty，当前 `RPA_COPIYPARTY_URL=http://192.168.40.166:3923`（见 §8 迁移说明） |

---

## 2. 方案选型：MySQL/Redis 用 Docker Desktop（推荐）

| 方案 | 结论 |
|---|---|
| **Docker Desktop（推荐）** | Redis 官方不出 Windows 原生版；项目已有现成 compose；数据卷持久化；与开发环境完全一致 |
| MySQL 原生安装 + Redis 旧移植版 | 不推荐：Redis Windows 移植版多年停更，Streams/XACK 等新特性有风险 |
| MySQL/Redis 放 Linux 虚机 | 可行但多一层运维，Windows 场景收益不大 |

**结论：目标机安装 Docker Desktop（WSL2 后端），直接用项目自带 compose。**

---

## 3. 端口与防火墙规划

中央机需要开放的入站端口（Windows 防火墙）：

| 端口 | 协议 | 用途 | 是否必须对局域网开放 |
|---|---|---|---|
| **6379** | TCP | Agent → Redis 命令总线 | **必须** |
| **8766** | TCP | 浏览器访问前端 + Agent 日志上报 | **必须** |
| 3923 | TCP | Copyparty 录屏文件服务（若随迁） | 用则开 |
| 3306 | TCP | MySQL 远程管理 | **建议不开**（后端本机 127.0.0.1 访问即可；确需远程运维时临时开） |

Agent 机器出站无需特殊配置（默认放行）。

---

## 4. 阶段 A：开发机准备（打包代码 + 可选导数据）

### 4.1 构建前端产物

```bash
cd rpa-log-web
pnpm install
pnpm run build      # 产物自动输出到 ../queue_control_platform/dist
```

### 4.2 同步代码到目标机

任选一种（推荐 git，可追溯）：

- **git**：目标机 `git clone <仓库地址>`，切到 `RPA日志开发` 分支
- **文件夹拷贝**：用 robocopy / 共享文件夹拷贝，**排除** `.venv、node_modules、.uv_cache、runtime、nacos-data、.git、__pycache__`

### 4.3 决策：新库 or 迁移旧数据

| 场景 | 做法 |
|---|---|
| **全新部署（推荐，如果当前数据只是开发测试数据）** | 什么都不用做。目标机后端首次启动自动建全部表；在 Web 页面重新注册每台设备，把新令牌填回各 Agent `.env`。设备令牌是哈希存库的，新库必然要换新令牌 |
| **保留设备注册、队列分配、历史日志** | 在开发机 Docker 里导出再导入（见 §7.3），旧设备令牌可继续用，Agent `.env` 无需改令牌 |

---

## 5. 阶段 B：目标机基础环境

以 Windows 10/11 + PowerShell 管理员为例：

### 5.1 固定 IP

路由器 DHCP 保留，或本机静态 IP。假设中央机 IP 为 `192.168.10.46`（下文统一用这个示例，替换为实际值）。

### 5.2 安装 Docker Desktop

1. 启用 WSL2：管理员 PowerShell
   ```powershell
   wsl --install
   ```
2. 安装 Docker Desktop（官网或 winget），设置里确认 Use WSL 2 based engine
3. Docker Desktop → Settings → General → 勾选 **Start Docker Desktop when you sign in**（开机自启）

### 5.3 安装 uv + 项目依赖

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# 重开 PowerShell
uv --version

cd D:\workspace\document_RPA     # 按实际路径
uv python install 3.12.12
uv sync
```

---

## 6. 阶段 C：加固并启动 MySQL + Redis

### 6.1 修改 compose（生产加固）

编辑 `queue_control_platform/docker/compose.yml`，做 3 处加固：

1. **改默认密码**（`queue_control` / `root_password` 是开发默认值，必须改）
2. **Redis 加密码**（6379 对局域网开放，当前无密码；Agent 直连的就是它）
3. **加自动重启**

```yaml
services:
  mysql:
    image: mysql:8.4
    restart: unless-stopped
    environment:
      MYSQL_DATABASE: rpa_platform          # 与 initdb 统一库保持一致
      MYSQL_USER: queue_control
      MYSQL_PASSWORD: <改成强密码MySQLApp2026>
      MYSQL_ROOT_PASSWORD: <改成强密码Root2026>
    ports:
      - "127.0.0.1:3306:3306"               # 仅本机访问，不对局域网暴露
    volumes:
      - queue-control-mysql:/var/lib/mysql
      - ./initdb:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-uroot", "-p<Root2026>"]
      interval: 5s
      timeout: 3s
      retries: 20

  redis:
    image: redis:7.4-alpine
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes", "--requirepass", "<RedisStrongPwd2026>"]
    ports:
      - "6379:6379"                          # Agent 必须能连
    volumes:
      - queue-control-redis:/data
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "<RedisStrongPwd2026>", "ping"]
      interval: 5s
      timeout: 3s
      retries: 20

volumes:
  queue-control-mysql:
  queue-control-redis:
```

> 注意：`initdb/01-init.sql` 里的 `IDENTIFIED BY 'queue_control'` 只在**空数据卷首次初始化**时生效。
> 如果首启前就把 compose 密码改好，`MYSQL_USER`/`MYSQL_PASSWORD` 创建的就是强密码账号，initdb 的 `CREATE USER IF NOT EXISTS` 不会覆盖它，无需改 SQL。

### 6.2 启动并验证

```powershell
docker compose -f queue_control_platform/docker/compose.yml up -d
docker ps         # 两个容器 healthcheck 均为 healthy
```

### 6.3 配置中央机 `.env`

```dotenv
# ---- 仅中央机使用 ----
QUEUE_CONTROL_MYSQL_URL=mysql://queue_control:<MySQLApp2026>@127.0.0.1:3306/rpa_platform
QUEUE_CONTROL_REDIS_URL=redis://:<RedisStrongPwd2026>@127.0.0.1:6379/0
QUEUE_CONTROL_HOST=0.0.0.0
QUEUE_CONTROL_PORT=8766
```

其余 `NACOS_*`、Copyparty 配置按现状填。

---

## 7. 阶段 D：启动后端（自动建表）+ 验证

### 7.1 启动

```powershell
uv run python -m queue_control_platform.server.main
```

首次启动会自动执行：
- `repository.initialize_schema()` → `devices / queue_assignments / queue_statuses / queue_commands / queue_events`
- `init_rpa_schema()` → `rpa_execution / rpa_execution_log / rpa_execution_file / rpa_device / rpa_queue`

全部 `CREATE TABLE IF NOT EXISTS`，可重复执行，**无需手工导 SQL**。

### 7.2 验证

```powershell
# 本机
curl http://127.0.0.1:8766/api/dashboard

# 局域网任意机器浏览器
http://192.168.10.46:8766
```

能打开控制台首页即部署成功。

### 7.3 （可选）迁移旧数据

开发机导出（在开发机项目目录）：

```bash
docker exec queue_control_platform-mysql-1 \
  mysqldump -uroot -proot_password --databases rpa_platform \
  --add-drop-database > rpa_platform_backup.sql
```

目标机导入：

```powershell
docker cp rpa_platform_backup.sql <mysql容器名>:/tmp/
docker exec -it <mysql容器名> sh -c "mysql -uroot -p<Root2026> < /tmp/rpa_platform_backup.sql"
```

> 注意：如果目标机后端已经自动建过表，dump 里用 `--add-drop-database` 会先删库再导入，历史数据完整覆盖，设备旧令牌继续有效。

---

## 8. 阶段 E：Copyparty 录屏文件服务（按需）

当前 `.env` 指向 `http://192.168.40.166:3923`。两种选择：

| 选择 | 操作 |
|---|---|
| **文件服务不迁移（推荐先这样）** | 保持 Agent `.env` 里 `RPA_COPIYPARTY_URL` 仍指向 192.168.40.166:3923，前提是这台机器继续在线且局域网可达 |
| 文件服务随迁到新中央机 | 在新机上部署 copyparty（3923 端口），迁移原 volume 数据，Agent `.env` 改成 `http://192.168.10.46:3923`，并开放 3923 防火墙 |

---

## 9. 阶段 F：Windows 防火墙 + 开机自启

### 9.1 防火墙（管理员 PowerShell）

```powershell
netsh advfirewall firewall add rule name="RPA Platform 8766" dir=in action=allow protocol=TCP localport=8766
netsh advfirewall firewall add rule name="RPA Redis 6379" dir=in action=allow protocol=TCP localport=6379
# 若迁移 copyparty：
netsh advfirewall firewall add rule name="Copyparty 3923" dir=in action=allow protocol=TCP localport=3923
```

> 安全建议：6379 规则的远程地址可限定为局域网网段（如 192.168.10.0/24），不对全网开放。

### 9.2 后端注册为 Windows 服务（NSSM，推荐）

```powershell
# 下载 nssm 到 D:\tools\nssm\
D:\tools\nssm\nssm.exe install RPAPlatform
# GUI 里填：
#   Path:              D:\workspace\document_RPA\.venv\Scripts\python.exe
#   Startup directory: D:\workspace\document_RPA
#   Arguments:         -m queue_control_platform.server.main
D:\tools\nssm\nssm.exe set RPAPlatform AppStdout D:\workspace\document_RPA\runtime\logs\platform.out.log
D:\tools\nssm\nssm.exe set RPAPlatform AppStderr D:\workspace\document_RPA\runtime\logs\platform.err.log
D:\tools\nssm\nssm.exe start RPAPlatform
```

备选：任务计划程序（开机登录时运行，隐藏窗口）。

自启顺序保障：Docker Desktop 已设置登录自启；NSSM 服务可设依赖，或后端自身的 Redis 重连逻辑已能容忍 Redis 短暂未就绪。

---

## 10. 阶段 G：Agent 机器接入（每台 Windows Agent）

### 10.1 基础环境

每台 Agent：安装 uv → 拉同一份代码 → `uv sync` → 安装 Chrome/Chromium。

### 10.2 在中央机注册设备

浏览器打开 `http://192.168.10.46:8766` → 设备管理 → 新增设备（如 `WIN-RPA-01`）→ **复制一次性注册令牌**。

### 10.3 Agent `.env` 关键配置

```dotenv
APP_ENV=test
QUEUE_ASSIGNMENT_SOURCE=server

# 每台机器唯一
QUEUE_CONTROL_DEVICE_ID=WIN-RPA-01
QUEUE_CONTROL_DEVICE_TOKEN=<中央机页面生成的新令牌>

# ★ 指向中央机，绝不再是 127.0.0.1
QUEUE_CONTROL_REDIS_URL=redis://:<RedisStrongPwd2026>@192.168.10.46:6379/0

# 本地兜底队列（平台失联时用）
RPA_QUEUES=FHT_MSCGW_SI,QTCT_ZIM_SI,QTCT_ZIM_VGM

# 日志上报也指向中央机
RPA_LOG_SERVICE_ENABLED=true
RPA_LOG_SERVICE_URL=http://192.168.10.46:8766
RPA_LOG_SERVICE_TOKEN=local-dev

# Copyparty（不迁移则保持原地址）
RPA_COPIYPARTY_URL=http://192.168.40.166:3923

ENABLE_BROWSER=true
```

RabbitMQ 仍按现有 Nacos 配置下发，无需改动。

### 10.4 启动 Agent

```powershell
uv run python -m app.main
```

### 10.5 绑定队列

中央机 Web 页面 → 把队列分配给该设备 → 设备状态变 RUNNING 即接入成功。

Agent 也可注册成 NSSM 服务（`-m app.main`），实现开机自启、掉线自动拉起。

---

## 11. 验收清单

| # | 检查项 | 命令/操作 | 通过标准 |
|---|---|---|---|
| 1 | Agent → Redis 连通 | Agent 机 `Test-NetConnection 192.168.10.46 -Port 6379` | TcpTestSucceeded : True |
| 2 | Agent → 后端连通 | `Test-NetConnection 192.168.10.46 -Port 8766` | True |
| 3 | Web 可达 | 浏览器开 `http://192.168.10.46:8766` | 控制台正常显示 |
| 4 | 设备上线 | 启动 `app.main` | 页面设备状态 ONLINE |
| 5 | 命令链路 | 页面向设备分配队列 | 设备进程启动，状态 RUNNING |
| 6 | 日志链路 | 投一条测试消息 | 执行记录/日志出现在页面 |
| 7 | 录屏链路 | 触发一次带录屏任务 | 文件记录可下载/可播 |
| 8 | RabbitMQ | 投递真实队列消息 | Agent 正常消费 |
| 9 | 重启恢复 | 重启中央机 | Docker + RPAPlatform 服务自动起来，Agent 自动重连 |
| 10 | 数据持久化 | 重启后查页面 | 设备/分配/历史日志仍在 |

---

## 12. 安全与运维建议

1. **Redis 必须设密码**（6379 对局域网开放，默认无密码是最大风险点）
2. MySQL 密码换强密码，且 `127.0.0.1:3306:3306` 绑定本机，不对局域网暴露
3. 防火墙规则按网段收窄（远程地址 = 局域网网段）
4. **备份**：每周/每日定时任务执行 `mysqldump rpa_platform`，保留 7~30 份；Redis AOF 卷定期快照
5. `.env` 不入库（已在 `.gitignore`），各机器令牌手工分发
6. 升级流程：目标机 `git pull` → `uv sync` → 重建前端（如有改动）→ `nssm restart RPAPlatform`；Agent 机同样 `git pull` + 重启（平台"重启"命令本身会拉起新 Worker 进程加载新代码）
