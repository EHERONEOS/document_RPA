"""队列控制平台 FastAPI（后台服务合并后的唯一后台 + 唯一前端入口）。

页面：根路径托管 rpa-log-web 构建产物（React 控制台：设备管理/日志/运行视图）。
2026-09 起原 Jinja 维护页退役（git 历史可查）。
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from queue_control_platform.server.rpa_log import db as rpa_db
from queue_control_platform.server.rpa_log.jobs import timeout_scanner_loop
from queue_control_platform.server.rpa_log.routes import agent as rpa_agent
from queue_control_platform.server.rpa_log.routes import files as rpa_files
from queue_control_platform.server.rpa_log.routes import web as rpa_web
from queue_control_platform.server.rpa_log.settings import get_settings as rpa_settings


# 创建使用中心仓储和 Redis 命令总线的 FastAPI 应用。
def create_app(repository, bus, processor=None) -> FastAPI:
    platform_root = Path(__file__).resolve().parents[1]

    # 将事件处理线程与 RPA 日志超时扫描绑定到 FastAPI 生命周期，退出时一并停止。
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        scanner = asyncio.create_task(timeout_scanner_loop())
        if processor is not None:
            processor.start()
        try:
            yield
        finally:
            if processor is not None:
                processor.stop()
            scanner.cancel()
            try:
                await scanner
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="队列控制平台", lifespan=lifespan)

    @app.get("/api/dashboard")
    # 返回设备、队列绑定及 MySQL 中最后一次上报的运行状态。
    def dashboard():
        return repository.dashboard()

    @app.post("/api/devices")
    # 创建可供机器侧队列控制客户端使用的设备 ID 与一次性注册令牌。
    def create_device(payload: dict | None = Body(default=None)):
        try:
            payload = payload or {}
            return JSONResponse(
                {
                    "ok": True,
                    **repository.create_device(
                        str(payload.get("deviceId") or ""),
                        str(payload.get("displayName") or ""),
                    ),
                },
                status_code=201,
            )
        except ValueError as exc:
            return _conflict(str(exc))

    @app.post("/api/devices/{device_id}/queues")
    # 绑定一个队列到设备，并向该设备投递启动监听命令。
    def assign_queue(device_id: str, payload: dict | None = Body(default=None)):
        try:
            payload = payload or {}
            assignment = repository.assign_queue(device_id, str(payload.get("queueName") or ""))
            command = repository.create_command(
                assignment["deviceId"],
                assignment["queueName"],
                "assign",
                payload={"assignmentVersion": assignment["assignmentVersion"]},
            )
            bus.send_command(assignment["deviceId"], command)
            return JSONResponse(
                {"ok": True, "assignment": assignment, "command": command}, status_code=202
            )
        except ValueError as exc:
            return _conflict(str(exc))

    @app.delete("/api/devices/{device_id}/queues/{queue_name}")
    # 发送停止监听命令后解除队列与设备的中心绑定。
    def unassign_queue(device_id: str, queue_name: str):
        try:
            command = repository.create_command(device_id, queue_name, "unassign")
            repository.unassign_queue(device_id, queue_name)
            bus.send_command(device_id, command)
            return JSONResponse({"ok": True, "command": command}, status_code=202)
        except ValueError as exc:
            return _conflict(str(exc))

    @app.post("/api/devices/{device_id}/queues/{queue_name}/commands")
    # 向指定设备上的单个队列投递暂停、恢复或重启命令。
    def queue_command(
        device_id: str, queue_name: str, payload: dict | None = Body(default=None)
    ):
        try:
            payload = payload or {}
            action = str(payload.get("action") or "")
            if action == "pause":
                repository.set_assignment_desired_state(device_id, queue_name, "PAUSED")
            elif action in {"resume", "restart"}:
                repository.set_assignment_desired_state(device_id, queue_name, "RUNNING")
            command = repository.create_command(
                device_id,
                queue_name,
                action,
                force_restart=bool(payload.get("forceRestart", False)),
            )
            bus.send_command(device_id, command)
            return JSONResponse({"ok": True, "command": command}, status_code=202)
        except ValueError as exc:
            return _conflict(str(exc))

    @app.post("/api/devices/{device_id}/commands/restart-all")
    # 向指定设备投递全部队列协作式重启命令。
    def restart_all(device_id: str):
        try:
            command = repository.create_command(device_id, None, "restart_all")
            bus.send_command(device_id, command)
            return JSONResponse({"ok": True, "command": command}, status_code=202)
        except ValueError as exc:
            return _conflict(str(exc))

    # ---- RPA 日志模块（原 rpa-log-service，合并进本服务）----
    files_dir = rpa_settings().files_dir
    files_dir.mkdir(parents=True, exist_ok=True)
    app.include_router(rpa_agent.router, prefix="/api/v1")
    app.include_router(rpa_web.router, prefix="/api/v1")
    app.include_router(rpa_files.router, prefix="/api/v1")
    # 局域网文件服务：/files/* 只读静态访问（设计 §7.1）
    app.mount("/files", StaticFiles(directory=str(files_dir)), name="files")

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict:
        """健康检查：{"db":"ok"} / {"db":"error"}。"""
        try:
            return {"db": "ok"} if rpa_db.ping() else {"db": "error"}
        except Exception:  # noqa: BLE001 - 数据库不可用时返回明确状态而非 500
            return {"db": "error"}

    # ---- 唯一前端：rpa-log-web 构建产物（HashRouter，静态托管无需服务端回退）----
    web_dist = platform_root.parent / "rpa-log-web" / "dist"
    if (web_dist / "index.html").is_file():
        # / 挂载放在最后：Starlette 按注册顺序匹配，保证 /api、/files 优先
        app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="web")
    else:

        @app.get("/", response_class=HTMLResponse)
        async def index_placeholder() -> HTMLResponse:
            return HTMLResponse(
                "<h3>控制台前端未构建</h3><p>请先执行：<code>cd rpa-log-web && npm run build</code> 后重启服务</p>"
            )

    return app


# 统一返回前端可直接显示的冲突和校验错误响应。
def _conflict(message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=409)
