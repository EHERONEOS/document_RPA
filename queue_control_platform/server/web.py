"""独立队列控制平台的 FastAPI 与维护页面。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


# 创建使用中心仓储和 Redis 命令总线的 FastAPI 应用。
def create_app(repository, bus, processor=None) -> FastAPI:
    platform_root = Path(__file__).resolve().parents[1]
    templates = Jinja2Templates(directory=str(platform_root / "frontend" / "templates"))

    # 将事件处理线程绑定到 FastAPI 生命周期，确保服务退出时停止消费。
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if processor is not None:
            processor.start()
        try:
            yield
        finally:
            if processor is not None:
                processor.stop()

    app = FastAPI(title="队列控制平台", lifespan=lifespan)
    app.mount(
        "/static",
        StaticFiles(directory=str(platform_root / "frontend" / "static")),
        name="static",
    )

    @app.get("/", response_class=HTMLResponse)
    # 渲染从业务 app 中抽离出的独立维护页面。
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request=request, name="index.html")

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

    return app


# 统一返回前端可直接显示的冲突和校验错误响应。
def _conflict(message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=409)
