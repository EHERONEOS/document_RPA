"""部署控制服务 FastAPI 接口。"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from queue_control_deploy.server.artifact_store import ArtifactStore
from queue_control_deploy.server.config import DeploySettings
from queue_control_deploy.server.repository import DeployRepository
from queue_control_deploy.server.redis_bus import DeployRedisBus


# 临时开放管理端访问：恢复操作员 Token 校验时改回 True。
OPERATOR_AUTH_ENABLED = False


def get_settings() -> DeploySettings:
    """加载部署服务配置。

    出参：
        返回 DeploySettings。
    """
    return DeploySettings.from_environment()


SettingsDependency = Annotated[DeploySettings, Depends(get_settings)]


def create_app(settings: DeploySettings | None = None) -> FastAPI:
    """创建部署控制 FastAPI 应用。

    入参：
        ``settings``：可选配置，便于测试注入。

    出参：
        返回 FastAPI 实例。

    核心逻辑:
        1. 发布管理接口要求操作员 Bearer Token。
        2. Agent 下载接口要求 mirror_devices 中 token_hash 校验。
        3. 制品路径全部由 ArtifactStore 防穿越保护；管理端鉴权当前由 OPERATOR_AUTH_ENABLED 临时关闭。
    """
    settings = settings or DeploySettings.from_environment()
    app = FastAPI(title="Queue Control Deploy Service")
    repository = DeployRepository(settings)
    artifact_store = ArtifactStore(settings.artifact_root)
    redis_bus = DeployRedisBus(settings.redis_url)
    admin_page = Path(__file__).resolve().parent / "static" / "index.html"

    @app.get("/", include_in_schema=False)
    def admin_console() -> FileResponse:
        """返回部署管理台单页应用。

        出参：
            返回本地静态 HTML。

        核心逻辑:
            管理页本身不携带数据；当前处于临时公开访问状态，恢复鉴权后 API 需要操作员 Token。
        """
        return FileResponse(admin_page, media_type="text/html")

    @app.get("/health", include_in_schema=False)
    def health() -> JSONResponse:
        """提供部署服务基础健康检查。

        出参：
            返回服务名和状态。

        核心逻辑:
            不访问数据库，供容器探活和浏览器快速确认服务可达。
        """
        return JSONResponse({"status": "ok", "service": "queue-control-deploy"})

    def require_operator(authorization: str | None) -> None:
        """校验发布操作员身份；当前临时允许公开访问。

        入参：
            ``authorization``：HTTP Authorization header。

        异常：
            ``HTTPException``：重新启用鉴权后，Bearer Token 不匹配返回 401。
        """
        if not OPERATOR_AUTH_ENABLED:
            return
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or token != settings.operator_token:
            raise HTTPException(status_code=401, detail="operator token required")

    @app.post("/api/deploy/releases")
    def upload_release(
        settings: SettingsDependency,
        releaseUnit: Annotated[str, Form()],
        version: Annotated[str, Form()],
        queues: Annotated[str, Form()],
        artifact: Annotated[UploadFile, File()],
        dependencyChanged: Annotated[bool, Form()] = False,
        gitCommit: Annotated[str, Form()] = "",
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> dict:
        """登记发布版本并保存 zip 制品。

        入参：
            ``releaseUnit``：发布单元。
            ``version``：语义化或项目版本号。
            ``gitCommit``：可选；留空时记录为 unknown。
            ``queues``：逗号分隔受影响队列。
            ``artifact``：zip 制品。
            ``dependencyChanged``：是否依赖变化。
            ``authorization``：操作员 Token。

        出参：
            返回已登记 release。

        核心逻辑:
            1. 服务端重新计算 sha256。
            2. manifest 声明 unit、paths、queues 和哈希。
            3. 依赖变化必须走 platform 发布。
        """
        require_operator(authorization)
        # Git Commit 当前不作为必填校验字段；留空时用 unknown 满足数据库非空约束。
        commit = (gitCommit or "").strip()[:64] or "unknown"
        queue_list = [queue.strip() for queue in queues.split(",") if queue.strip()]
        if not queue_list:
            raise HTTPException(status_code=422, detail="at least one queue is required")
        if dependencyChanged and releaseUnit != "platform":
            raise HTTPException(status_code=422, detail="dependency changes require platform release")
        data = artifact.file.read()
        stored = artifact_store.save_upload(data, artifact.filename or "release.zip", releaseUnit)
        release_id = str(uuid.uuid4())
        manifest = {
            "releaseId": release_id,
            "releaseUnit": releaseUnit,
            "version": version,
            "gitCommit": commit,
            "sha256": stored.sha256,
            "paths": [f"app/spider/{releaseUnit.split(':', 1)[-1]}/**"] if releaseUnit.startswith("carrier:") else ["**"],
            "queues": queue_list,
            "dependencyChanged": dependencyChanged,
        }
        artifact_url = f"/api/deploy/agent/releases/{release_id}/download"
        try:
            return repository.create_release(
                release_id=release_id,
                release_unit=releaseUnit,
                version=version,
                git_commit=commit,
                artifact_file_name=stored.file_name,
                artifact_path=str(stored.absolute_path),
                artifact_url=artifact_url,
                sha256=stored.sha256,
                size_bytes=stored.size_bytes,
                manifest=manifest,
                dependency_changed=dependencyChanged,
                created_by="release-api",
            )
        except Exception:
            # 登记失败时移除孤立的制品文件；路径来自安全存储。
            stored.absolute_path.unlink(missing_ok=True)
            raise

    @app.get("/api/deploy/releases")
    def list_releases(settings: SettingsDependency, releaseUnit: str | None = None, authorization: Annotated[str | None, Header(alias="Authorization")] = None) -> list[dict]:
        """查询发布版本列表。

        入参：
            ``releaseUnit``：可选发布单元过滤。
            ``authorization``：操作员 Token。

        出参：
            返回 release 列表。
        """
        require_operator(authorization)
        return repository.list_releases(releaseUnit)

    @app.get("/api/deploy/releases/{release_id}")
    def get_release(release_id: str, authorization: Annotated[str | None, Header(alias="Authorization")] = None) -> dict:
        """查询单个发布版本。

        入参：
            ``release_id``：发布 ID。
            ``authorization``：操作员 Token。

        出参：
            返回 release 详情。
        """
        require_operator(authorization)
        try:
            return repository.get_release(release_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="release not found") from exc

    @app.get("/api/deploy/agent/releases/{release_id}/download")
    def download_release(release_id: str, request: Request) -> FileResponse:
        """Agent 身份鉴权后下载制品。

        入参：
            ``release_id``：发布 ID。
            ``X-Device-Id``：设备 ID header。
            ``X-Device-Token``：设备 Token header。

        出参：
            返回文件流响应。

        核心逻辑:
            1. 先校验设备身份，再查询 release。
            2. ArtifactStore 二次确认路径不越界。
        """
        # 直接读取原始 header，避免不同 ASGI/客户端对 header 参数命名转换造成歧义。
        if not repository.authenticate_device(request.headers.get("X-Device-Id", ""), request.headers.get("X-Device-Token", "")):
            raise HTTPException(status_code=401, detail="device identity required")
        try:
            release = repository.get_release(release_id)
            path = artifact_store.open_if_exists(release["artifactPath"])
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="release not found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="artifact missing") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return FileResponse(path, filename=release["artifactFileName"], media_type="application/zip")

    @app.get("/api/deploy/targets")
    def targets(releaseUnit: str, authorization: Annotated[str | None, Header(alias="Authorization")] = None) -> list[dict]:
        """计算发布单元目标设备。

        入参：
            ``releaseUnit``：发布单元。
            ``authorization``：操作员 Token。

        出参：
            返回设备与受影响队列。
        """
        require_operator(authorization)
        return repository.calculate_targets(releaseUnit)

    @app.post("/api/deploy/releases/{release_id}/rollout")
    def create_rollout(
        release_id: str,
        body: dict,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> dict:
        """创建灰度或全量发布批次。

        入参：
            ``release_id``：发布 ID。
            ``body``：包含 mode、deviceIds、drainTimeoutSeconds、dryRun。
            ``authorization``：操作员 Token。

        出参：
            返回 rollout ID 和目标列表。
        """
        require_operator(authorization)
        try:
            return repository.create_rollout(
                release_id,
                mode=body.get("mode", "canary"),
                device_ids=list(body.get("deviceIds", [])),
                drain_timeout_seconds=int(body.get("drainTimeoutSeconds", 1800)),
                requested_by="release-api",
                dry_run=bool(body.get("dryRun", False)),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="release not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/deploy/rollouts/{rollout_id}/devices/{device_id}/command")
    def issue_upgrade_command(
        rollout_id: str,
        device_id: str,
        body: dict,
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> dict:
        """向 rollout 目标设备下发幂等 upgrade 命令。

        入参：
            ``rollout_id``：发布批次 ID。
            ``device_id``：批次内目标设备 ID。
            ``body``：可传 ``drainTimeoutSeconds``。
            ``request``：用于推导 Agent 可访问的服务基地址。
            ``authorization``：操作员 Token。

        出参：
            返回命令审计、是否新建和 Redis 消息 ID。

        异常：
            ``HTTPException``：目标不存在返回 404，业务冲突返回 409/422。

        核心逻辑:
            1. 校验命令必须绑定 rollout target。
            2. 首次写 deploy_commands 并绑定 target。
            3. 成功写入部署专用 Redis 后回填流 ID；重复请求不重复下发。
        """
        require_operator(authorization)
        base_url = settings.public_base_url or str(request.base_url).rstrip("/")
        try:
            command, created = repository.create_upgrade_command(
                release_id=body.get("releaseId", ""),
                rollout_id=rollout_id,
                device_id=device_id,
                artifact_base_url=base_url,
                drain_timeout_seconds=int(body.get("drainTimeoutSeconds", 1800)),
                requested_by="release-api",
            )
            if created:
                redis_stream_id = redis_bus.publish_command(command["deviceId"], command)
                repository.mark_deploy_command_queued(command["commandId"], redis_stream_id)
                command = repository.get_deploy_command(command["commandId"])
            return {"created": created, "command": command}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="rollout target not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"deploy redis unavailable: {exc}") from exc

    @app.get("/api/deploy/catalog/release-units")
    def list_release_units(authorization: Annotated[str | None, Header(alias="Authorization")] = None) -> list[dict]:
        """列出发布单元，供管理台构造下拉选项。

        入参：
            ``authorization``：操作员 Token。

        出参：
            返回启用发布单元和队列数量。
        """
        require_operator(authorization)
        return repository.list_release_units()

    @app.get("/api/deploy/rollouts")
    def list_rollouts(
        releaseId: str | None = None,
        limit: int = 30,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> list[dict]:
        """列出发布批次和目标状态。

        入参：
            ``releaseId``：可选发布 ID。
            ``limit``：最多返回 1-100 条。
            ``authorization``：操作员 Token。

        出参：
            返回最近 rollout 列表，每个批次内嵌目标设备。
        """
        require_operator(authorization)
        return repository.list_rollouts(releaseId, limit=limit)

    @app.get("/api/deploy/deploy-commands")
    def list_deploy_commands(
        deviceId: str | None = None,
        state: str | None = None,
        limit: int = 30,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> list[dict]:
        """列出部署命令审计。

        入参：
            ``deviceId``：可选设备 ID。
            ``state``：可选状态。
            ``limit``：最多返回 1-100 条。
            ``authorization``：操作员 Token。

        出参：
            返回新库部署命令，不读取原库 queue_commands。
        """
        require_operator(authorization)
        return repository.list_deploy_commands(device_id=deviceId, state=state, limit=limit)

    @app.post("/api/deploy/deploy-commands/{command_id}/result")
    def record_deploy_command_result(
        command_id: str,
        body: dict,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> dict:
        """记录 Agent 上报的部署命令结果。

        入参：
            ``command_id``：命令 ID。
            ``body``：``ok``、可选 ``error``。
            ``authorization``：操作员 Token。

        出参：
            返回更新后的部署命令审计。

        核心逻辑:
            结果只更新 queue_control_deploy.deploy_commands，不影响原库命令表。
        """
        require_operator(authorization)
        try:
            return repository.update_deploy_command_result(
                command_id, success=bool(body.get("ok")), error_message=body.get("error")
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="command not found") from exc

    return app


app = create_app()
