"""船司脚本部署专用命令消费器与远程制品下载流程。"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests

from app.control.queue_client.config import QueueClientSettings
from app.control.queue_client.redis_client import QueueControlRedisClient
from app.control.supervisor import QueueSupervisor
from app.control.updater import validate_artifact


@dataclass(frozen=True)
class DeployClientSettings:
    """Agent 部署消费器的身份、Redis 与升级配置。

    字段说明：
    - ``device_id``/``device_token``：下载制品和事件上报身份。
    - ``redis_url``：部署专用 Redis，不使用原队列控制 Redis DB。
    - ``drain_timeout_seconds``：后续排空的缺省超时。
    - ``staging_root``：下载制品校验和解压根目录。
    """

    device_id: str
    device_token: str
    redis_url: str
    drain_timeout_seconds: int
    staging_root: Path

    @classmethod
    def from_queue_settings(
        cls, settings: QueueClientSettings, staging_root: Path | None = None
    ) -> "DeployClientSettings":
        """复用现有 Agent 身份创建部署配置。

        入参：
            ``settings``：已加载的原队列控制客户端配置。
            ``staging_root``：可选 staging 根目录。

        出参：
            返回部署客户端配置。
        """
        return cls(
            device_id=settings.device_id,
            device_token=settings.enrollment_token,
            redis_url=os.getenv(
                "QUEUE_CONTROL_DEPLOY_REDIS_URL", "redis://127.0.0.1:6379/1"
            ),
            drain_timeout_seconds=settings.drain_timeout_seconds,
            staging_root=staging_root
            or Path(os.getenv("DEPLOY_STAGING_ROOT", "runtime/deploy/staging")).resolve(),
        )


class DeployRedisClient:
    """部署 Stream 的最小 Redis 读取、确认和上报客户端。"""

    def __init__(self, redis_url: str):
        """保存连接配置并延迟创建客户端。

        入参：
            ``redis_url``：部署 Redis URL。
        """
        self.redis_url = redis_url
        self._redis: Any = None

    def _client(self) -> Any:
        """创建启用字符串解码的 Redis 客户端。

        出参：
            返回 Redis 客户端。
        """
        if self._redis is None:
            import redis

            self._redis = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    def read_commands(
        self, device_id: str, consumer_name: str, *, block_ms: int = 500, count: int = 10
    ) -> list[tuple[str, dict[str, Any]]]:
        """读取本设备部署命令，优先接管超时未确认消息。

        入参：
            ``device_id``：设备 ID。
            ``consumer_name``：消费组内消费者名。
            ``block_ms``：无新消息时阻塞时间。
            ``count``：单批最大消息数。

        出参：
            返回 ``(Redis message id, command dict)``；非法 JSON 会被跳过。
        """
        stream = self.command_stream(device_id)
        group = f"queue-deploy-agent:{device_id}"
        client = self._client()
        try:
            client.xgroup_create(stream, group, id="0-0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        claimed = client.xautoclaim(
            stream, group, consumer_name, min_idle_time=30_000, start_id="0-0", count=count
        )
        entries = claimed[1] if claimed else []
        if not entries:
            messages = client.xreadgroup(
                groupname=group,
                consumername=consumer_name,
                streams={stream: ">"},
                count=count,
                block=block_ms,
            )
            entries = [item for _, items in messages for item in items]
        decoded: list[tuple[str, dict[str, Any]]] = []
        for message_id, fields in entries:
            try:
                payload = json.loads(fields["payload"])
            except (KeyError, TypeError, ValueError):
                continue
            decoded.append((str(message_id), payload))
        return decoded

    def acknowledge_command(self, device_id: str, message_id: str) -> None:
        """确认一条部署命令已处理完成。

        入参：
            ``device_id``：设备 ID。
            ``message_id``：Redis 消息 ID。
        """
        self._client().xack(
            self.command_stream(device_id), f"queue-deploy-agent:{device_id}", message_id
        )

    def publish_event(self, event: dict[str, Any]) -> str:
        """向部署事件流发布 JSON 事件。

        入参：
            ``event``：事件字典。

        出参：
            返回 Redis 消息 ID。
        """
        return str(
            self._client().xadd(
                self.event_stream(),
                {"payload": json.dumps(event, ensure_ascii=False, separators=(",", ":"))},
            )
        )

    @staticmethod
    def command_stream(device_id: str) -> str:
        """返回部署命令流名。

        入参：
            ``device_id``：设备 ID。

        出参：
            返回独立部署前缀 Stream。
        """
        return f"queue-deploy:commands:{(device_id or '').strip().upper()}"

    @staticmethod
    def event_stream() -> str:
        """返回部署事件流名。

        出参：
            固定 ``queue-deploy:events``。
        """
        return "queue-deploy:events"


class DeployClient:
    """在独立线程消费部署命令，失败不影响原队列控制循环。"""

    def __init__(
        self,
        settings: DeployClientSettings,
        redis_client: DeployRedisClient | None = None,
        supervisor: QueueSupervisor | None = None,
        artifact_validator: Callable[[dict[str, Any], Path, Path], Path] | None = None,
    ):
        """初始化部署消费器。

        入参：
            ``settings``：部署配置。
            ``redis_client``：可注入测试 Redis 客户端。
            ``supervisor``：现有队列监管器，用于获取当前队列状态。
            ``artifact_validator``：可注入的制品校验函数，替代真实 updater。
        """
        self.settings = settings
        self.redis_client = redis_client or DeployRedisClient(settings.redis_url)
        self.supervisor = supervisor
        self._validate = artifact_validator or self._download_and_validate
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """启动独立部署消费线程。

        核心逻辑:
            线程为 daemon，避免部署 Redis 异常阻塞主进程退出。
        """
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self.run_forever,
            name="queue-deploy-client",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """请求部署消费线程退出。

        核心逻辑:
            当前 Redis ``XREADGROUP`` 最多阻塞 500ms 后检查停止标记。
        """
        self._stop_event.set()

    def run_forever(self) -> None:
        """循环读取部署命令直到进程停止。

        核心逻辑:
            单条命令异常被捕获并上报失败，保证后续命令和原队列控制不受影响。
        """
        consumer = socket.gethostname()
        while not self._stop_event.is_set():
            try:
                messages = self.redis_client.read_commands(
                    self.settings.device_id, consumer, block_ms=500
                )
            except Exception:
                if self._stop_event.wait(1):
                    break
                continue
            for message_id, command in messages:
                self._handle_message(message_id, command)

    def _handle_message(self, message_id: str, command: dict[str, Any]) -> None:
        """执行并上报一条部署命令，最后确认消息。

        入参：
            ``message_id``：Redis 消息 ID。
            ``command``：反序列化后的命令。

        核心逻辑:
            无论成功、未知 action 或异常都只影响部署事件；确认放在事件上报后。
        """
        command_id = str(command.get("commandId") or "")
        target_device = str(command.get("deviceId") or "").strip().upper()
        event = {
            "type": "deploy_command_result",
            "deviceId": self.settings.device_id,
            "commandId": command_id,
            "ok": False,
        }
        if target_device and target_device != self.settings.device_id:
            event["error"] = "deviceId mismatch"
        else:
            try:
                result = self._execute_command(command)
                event.update({"ok": True, **result})
            except Exception as exc:
                event["error"] = str(exc)
        try:
            self.redis_client.publish_event(event)
        finally:
            self.redis_client.acknowledge_command(self.settings.device_id, message_id)

    def _execute_command(self, command: dict[str, Any]) -> dict[str, Any]:
        """分发部署命令。

        入参：
            ``command``：命令对象。

        出参：
            返回附加入事件的结果字段。

        异常：
            ``ValueError``：action 未知或载荷不完整时抛出。
        """
        action = str(command.get("action") or "")
        if action != "upgrade":
            raise ValueError(f"不支持的部署命令：{action}")
        return self._upgrade(command.get("payload") or {})

    def _upgrade(self, payload: dict[str, Any]) -> dict[str, Any]:
        """下载、校验并 staging 船司更新制品。

        入参：
            ``payload``：服务端下发 release、URL、sha256、manifest 和队列。

        出参：
            返回 release/version/staging/compile 状态。

        异常：
            ``ValueError``：字段缺失或制品不合法时抛出。
            ``requests.RequestException``：下载网络失败时抛出。

        核心逻辑:
            1. 校验载荷和 manifest 一致性。
            2. 使用设备身份流式下载到临时文件。
            3. 校验哈希、白名单、zip 穿越、解压和 Python 编译。
            4. 本任务只做到安全 staging；目录切换由后续排空任务执行。
        """
        required = {"releaseId", "releaseUnit", "version", "artifactUrl", "sha256", "manifest", "queues"}
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"upgrade payload missing: {','.join(missing)}")
        manifest = payload["manifest"]
        if not isinstance(manifest, dict):
            raise ValueError("upgrade manifest must be an object")
        for command_key, manifest_key in (
            ("releaseId", "releaseId"), ("releaseUnit", "releaseUnit"),
            ("version", "version"), ("sha256", "sha256"),
        ):
            if payload[command_key] != manifest.get(manifest_key):
                raise ValueError(f"manifest mismatch: {command_key}")
        staging = self._validate(payload, Path(tempfile.gettempdir()), self.settings.staging_root)
        return {
            "releaseId": payload["releaseId"],
            "releaseUnit": payload["releaseUnit"],
            "version": payload["version"],
            "staging": str(staging),
            "stagingReady": True,
        }

    def _download_and_validate(
        self, payload: dict[str, Any], download_root: Path, staging_root: Path
    ) -> Path:
        """使用 requests 远程下载并调用 updater 安全校验。

        入参：
            ``payload``：升级载荷。
            ``download_root``：临时下载目录。
            ``staging_root``：staging 根目录。

        出参：
            返回编译通过的 staging 目录。

        核心逻辑:
            下载使用唯一临时名，写入后校验哈希；manifest 由 Agent 另写临时文件。
        """
        download_root.mkdir(parents=True, exist_ok=True)
        artifact_path = download_root / f"deploy-{uuid.uuid4()}.zip"
        headers = {
            "X-Device-Id": self.settings.device_id,
            "X-Device-Token": self.settings.device_token,
        }
        try:
            with requests.get(
                payload["artifactUrl"], headers=headers, stream=True, timeout=(5, 60)
            ) as response:
                if response.status_code != 200:
                    raise ValueError(f"artifact download failed: HTTP {response.status_code}")
                digest = hashlib.sha256()
                size = 0
                with artifact_path.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                if size <= 0:
                    raise ValueError("artifact download is empty")
                if digest.hexdigest() != payload["sha256"]:
                    raise ValueError("downloaded artifact sha256 mismatch")
            staging = validate_artifact(artifact_path, payload["manifest"], staging_root)
            return staging
        finally:
            try:
                artifact_path.unlink(missing_ok=True)
            except OSError:
                pass


def build_deploy_client(
    queue_settings: QueueClientSettings,
    supervisor: QueueSupervisor,
    queue_redis_client: QueueControlRedisClient,
) -> DeployClient:
    """从现有队列控制客户端组件构建部署消费器。

    入参：
        ``queue_settings``：队列控制配置。
        ``supervisor``：已创建的队列监管器。
        ``queue_redis_client``：原队列控制 Redis 客户端，仅用于证明部署流与其独立。

    出参：
        返回部署消费器。

    核心逻辑:
        原队列控制 stream、Redis DB 和命令语义保持不变；部署流使用独立客户端。
    """
    return DeployClient(
        DeployClientSettings.from_queue_settings(queue_settings),
        supervisor=supervisor,
    )
