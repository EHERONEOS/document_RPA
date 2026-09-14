"""独立队列控制平台的 FastAPI 与维护页面。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, Header, Request
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

    @app.get("/api/task-runs/{task_run_id}")
    # 查询单个任务运行快照，供后续任务调试页面复用。
    def get_task_run(task_run_id: str):
        try:
            task_run = repository.get_task_run(task_run_id)
        except ValueError as exc:
            return _conflict(str(exc))
        if task_run is None:
            return JSONResponse({"ok": False, "error": "任务不存在"}, status_code=404)
        return {"ok": True, "taskRun": task_run}

    @app.get("/api/flows")
    def list_flows():
        return {"ok": True, "flows": repository.list_flows()}

    @app.post("/api/flows")
    def create_flow(payload: dict | None = Body(default=None)):
        try:
            payload = payload or {}
            flow = repository.create_flow(
                str(payload.get("flowId") or ""), str(payload.get("displayName") or ""),
                str(payload.get("description") or ""), str(payload.get("createdBy") or "system"),
            )
            return JSONResponse({"ok": True, "flow": flow}, status_code=201)
        except ValueError as exc:
            return _conflict(str(exc))

    @app.get("/api/flows/{flow_id}")
    def get_flow(flow_id: str):
        try:
            flow = repository.get_flow(flow_id)
        except ValueError as exc:
            return _conflict(str(exc))
        if flow is None:
            return _not_found("流程不存在")
        return {"ok": True, "flow": flow}

    @app.get("/api/flows/{flow_id}/versions")
    def list_flow_versions(flow_id: str):
        try:
            return {"ok": True, "versions": repository.list_flow_versions(flow_id)}
        except ValueError as exc:
            return _conflict(str(exc))

    @app.post("/api/flows/{flow_id}/versions/{flow_version}")
    def create_flow_version(flow_id: str, flow_version: str, payload: dict | None = Body(default=None)):
        try:
            payload = payload or {}
            version = repository.create_flow_version(
                flow_id, flow_version, payload.get("definition"), str(payload.get("createdBy") or "system")
            )
            return JSONResponse({"ok": True, "version": version}, status_code=201)
        except ValueError as exc:
            return _conflict(str(exc))

    @app.get("/api/flows/{flow_id}/versions/{flow_version}")
    def get_flow_version(flow_id: str, flow_version: str):
        try:
            version = repository.get_flow_version(flow_id, flow_version)
        except ValueError as exc:
            return _conflict(str(exc))
        if version is None:
            return _not_found("流程版本不存在")
        return {"ok": True, "version": version}

    @app.get("/api/flows/{flow_id}/compare")
    def compare_flow_versions(flow_id: str, leftVersion: str, rightVersion: str):
        try:
            return {
                "ok": True,
                "comparison": repository.compare_flow_versions(flow_id, leftVersion, rightVersion),
            }
        except ValueError as exc:
            return _conflict(str(exc))

    @app.get("/api/flow-bindings")
    def list_flow_bindings():
        return {"ok": True, "bindings": repository.list_flow_bindings()}

    @app.post("/api/flow-bindings")
    def upsert_flow_binding(payload: dict | None = Body(default=None)):
        try:
            payload = payload or {}
            binding = repository.upsert_flow_binding(
                str(payload.get("queueName") or ""), str(payload.get("flowId") or ""),
                enabled=bool(payload.get("enabled", True)), created_by=str(payload.get("createdBy") or "system"),
            )
            _publish_flow_sync(repository, bus, binding["flowId"])
            return JSONResponse({"ok": True, "binding": binding}, status_code=201)
        except ValueError as exc:
            return _conflict(str(exc))

    @app.get("/api/flows/{flow_id}/releases")
    def list_flow_releases(flow_id: str):
        try:
            return {"ok": True, "releases": repository.list_flow_releases(flow_id)}
        except ValueError as exc:
            return _conflict(str(exc))

    @app.post("/api/flows/{flow_id}/releases")
    def release_flow(flow_id: str, payload: dict | None = Body(default=None)):
        try:
            payload = payload or {}
            release = repository.release_flow_version(
                flow_id, str(payload.get("flowVersion") or ""), payload.get("strategy"),
                release_note=str(payload.get("releaseNote") or ""),
                released_by=str(payload.get("releasedBy") or "system"),
            )
            targets = _publish_flow_sync(repository, bus, flow_id)
            return JSONResponse({"ok": True, "release": release, "targetDevices": targets}, status_code=202)
        except ValueError as exc:
            return _conflict(str(exc))

    @app.post("/api/flows/{flow_id}/rollback")
    def rollback_flow(flow_id: str, payload: dict | None = Body(default=None)):
        try:
            payload = payload or {}
            release = repository.rollback_flow(
                flow_id, str(payload.get("targetVersion") or ""), strategy=payload.get("strategy"),
                release_note=str(payload.get("releaseNote") or ""), released_by=str(payload.get("releasedBy") or "system"),
            )
            targets = _publish_flow_sync(repository, bus, flow_id)
            return JSONResponse({"ok": True, "release": release, "targetDevices": targets}, status_code=202)
        except ValueError as exc:
            return _conflict(str(exc))

    @app.get("/api/agent/flows/{flow_id}/{flow_version}")
    def get_agent_flow(
        flow_id: str,
        flow_version: str,
        x_queue_control_device: str = Header(default=""),
        x_queue_control_token: str = Header(default=""),
    ):
        try:
            version = repository.get_agent_flow_version(
                x_queue_control_device, x_queue_control_token, flow_id, flow_version
            )
        except ValueError as exc:
            return _conflict(str(exc))
        if version is None:
            return _not_found("流程版本不存在")
        return {"ok": True, "definition": version["definition"], "checksum": version["checksum"]}

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


def _not_found(message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=404)


def _publish_flow_sync(repository, bus, flow_id: str) -> list[str]:
    """通知所有绑定队列的节点；Redis 仅携带绑定和版本元数据。"""
    targets = repository.list_flow_target_devices(flow_id)
    for device_id in targets:
        bus.send_command(
            device_id,
            {"action": "flow_sync", "bindings": repository.list_device_flow_bindings(device_id)},
        )
    return targets
