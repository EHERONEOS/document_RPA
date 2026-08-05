"""独立队列控制平台的 Flask API 与维护页面。"""
from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template, request


# 创建使用中心仓储和 Redis 命令总线的维护平台应用。
def create_app(repository, bus) -> Flask:
    platform_root = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(platform_root / "frontend" / "templates"),
        static_folder=str(platform_root / "frontend" / "static"),
    )

    @app.get("/")
    # 渲染从业务 app 中抽离出的独立维护页面。
    def index():
        return render_template("index.html")

    @app.get("/api/dashboard")
    # 返回设备、队列绑定及 MySQL 中最后一次上报的运行状态。
    def dashboard():
        return jsonify(repository.dashboard())

    @app.post("/api/devices")
    # 创建可供机器侧 Agent 使用的设备 ID 与一次性注册令牌。
    def create_device():
        try:
            payload = request.get_json(silent=True) or {}
            return jsonify(
                {
                    "ok": True,
                    **repository.create_device(
                        str(payload.get("deviceId") or ""),
                        str(payload.get("displayName") or ""),
                    ),
                }
            ), 201
        except ValueError as exc:
            return _conflict(str(exc))

    @app.post("/api/devices/<device_id>/queues")
    # 绑定一个队列到设备，并向该设备投递启动监听命令。
    def assign_queue(device_id: str):
        try:
            payload = request.get_json(silent=True) or {}
            assignment = repository.assign_queue(device_id, str(payload.get("queueName") or ""))
            command = repository.create_command(
                assignment["deviceId"],
                assignment["queueName"],
                "assign",
                payload={"assignmentVersion": assignment["assignmentVersion"]},
            )
            bus.send_command(assignment["deviceId"], command)
            return jsonify({"ok": True, "assignment": assignment, "command": command}), 202
        except ValueError as exc:
            return _conflict(str(exc))

    @app.delete("/api/devices/<device_id>/queues/<queue_name>")
    # 发送停止监听命令后解除队列与设备的中心绑定。
    def unassign_queue(device_id: str, queue_name: str):
        try:
            command = repository.create_command(device_id, queue_name, "unassign")
            repository.unassign_queue(device_id, queue_name)
            bus.send_command(device_id, command)
            return jsonify({"ok": True, "command": command}), 202
        except ValueError as exc:
            return _conflict(str(exc))

    @app.post("/api/devices/<device_id>/queues/<queue_name>/commands")
    # 向指定设备上的单个队列投递暂停、恢复或重启命令。
    def queue_command(device_id: str, queue_name: str):
        try:
            payload = request.get_json(silent=True) or {}
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
            return jsonify({"ok": True, "command": command}), 202
        except ValueError as exc:
            return _conflict(str(exc))

    @app.post("/api/devices/<device_id>/commands/restart-all")
    # 向指定设备投递全部队列协作式重启命令。
    def restart_all(device_id: str):
        try:
            command = repository.create_command(device_id, None, "restart_all")
            bus.send_command(device_id, command)
            return jsonify({"ok": True, "command": command}), 202
        except ValueError as exc:
            return _conflict(str(exc))

    return app


# 统一返回前端可直接显示的冲突和校验错误响应。
def _conflict(message: str):
    return jsonify({"ok": False, "error": message}), 409
