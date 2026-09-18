"""部署控制专用 Redis 命令/事件总线。"""
from __future__ import annotations

import json
from typing import Any


class DeployRedisBus:
    """向独立部署 Stream 写入命令和事件，不接触原队列控制 Stream。

    核心逻辑:
        - 延迟创建 Redis 客户端，便于单元测试注入假总线。
        - 命令流按设备隔离，事件流全平台共用。
        - 所有消息统一放入 ``payload`` JSON 字段，与 Agent 解码协议保持一致。
    """

    def __init__(self, redis_url: str):
        """保存部署 Redis 连接配置。

        入参：
            ``redis_url``：例如 ``redis://127.0.0.1:6379/1``。
        """
        self.redis_url = redis_url
        self._redis: Any = None

    def _client(self) -> Any:
        """获取启用字符串解码的 Redis 客户端。

        出参：
            返回延迟初始化的 redis.Redis 客户端。

        异常：
            ``RuntimeError``：运行环境缺少 redis 依赖时抛出。
        """
        if self._redis is None:
            try:
                import redis
            except ImportError as exc:
                raise RuntimeError("缺少 redis，请执行 uv sync 安装依赖") from exc
            self._redis = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    def publish_command(self, device_id: str, command: dict[str, Any]) -> str:
        """向指定设备部署命令流发布一条命令。

        入参：
            ``device_id``：目标设备 ID。
            ``command``：完整命令对象，必须包含 ``commandId`` 和 ``action``。

        出参：
            返回 Redis Stream 消息 ID。

        异常：
            ``redis.RedisError``：Redis 不可用或写入失败时抛出。
        """
        message_id = self._client().xadd(
            self.command_stream(device_id),
            {"payload": json.dumps(command, ensure_ascii=False, separators=(",", ":"))},
        )
        return str(message_id)

    def publish_event(self, event: dict[str, Any]) -> str:
        """向全平台部署事件流发布 Agent 或服务事件。

        入参：
            ``event``：事件对象，推荐包含 ``type`` 和 ``deviceId``。

        出参：
            返回 Redis Stream 消息 ID。
        """
        message_id = self._client().xadd(
            self.event_stream(),
            {"payload": json.dumps(event, ensure_ascii=False, separators=(",", ":"))},
        )
        return str(message_id)

    @staticmethod
    def command_stream(device_id: str) -> str:
        """返回部署专用设备命令流名称。

        入参：
            ``device_id``：设备 ID。

        出参：
            返回大写设备 ID 对应的独立 Stream 名称。
        """
        return f"queue-deploy:commands:{(device_id or '').strip().upper()}"

    @staticmethod
    def event_stream() -> str:
        """返回部署专用事件流名称。

        出参：
            返回 ``queue-deploy:events``。
        """
        return "queue-deploy:events"
