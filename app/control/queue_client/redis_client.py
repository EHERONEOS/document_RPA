"""机器侧队列控制客户端使用的 Redis Streams 通道。"""
from __future__ import annotations

import json
from typing import Any


class QueueControlRedisClient:
    """读取本设备命令并上报设备事件的 Redis 客户端。"""

    # 保存 Redis 地址，客户端在首次实际收发消息时创建。
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._redis = None

    # 获取启用字符串解码的 Redis 客户端。
    def _client(self):
        if self._redis is None:
            try:
                import redis
            except ImportError as exc:
                raise RuntimeError("缺少 redis，请执行 uv sync 安装依赖") from exc
            self._redis = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    # 将本机状态、心跳或命令结果写入中心事件流。
    def publish_event(self, event: dict[str, Any]) -> str:
        return self._client().xadd(
            self.event_stream(), {"payload": json.dumps(event, ensure_ascii=False)}
        )

    # 读取本设备尚未确认的控制命令。
    def read_commands(
        self, device_id: str, consumer_name: str, *, block_ms: int = 1000, count: int = 10
    ) -> list[tuple[str, dict[str, Any]]]:
        stream = self.command_stream(device_id)
        group = f"queue-control-agent:{device_id}"
        self._ensure_group(stream, group)
        return self._read_group(stream, group, consumer_name, block_ms, count)

    # 确认本设备已经接收并处理了一条控制命令。
    def acknowledge_command(self, device_id: str, message_id: str) -> None:
        self._client().xack(
            self.command_stream(device_id), f"queue-control-agent:{device_id}", message_id
        )

    # 返回指定设备的命令流名称，必须与中心平台使用的命名保持一致。
    @staticmethod
    def command_stream(device_id: str) -> str:
        return f"queue-control:commands:{device_id.upper()}"

    # 返回所有设备共用的状态事件流名称，必须与中心平台使用的命名保持一致。
    @staticmethod
    def event_stream() -> str:
        return "queue-control:events"

    # 创建消费组；已存在时保持原有消费位置。
    def _ensure_group(self, stream: str, group: str) -> None:
        try:
            self._client().xgroup_create(stream, group, id="0-0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    # 优先重领超时未确认消息，再读取该消费组的新消息。
    def _read_group(
        self, stream: str, group: str, consumer_name: str, block_ms: int, count: int
    ) -> list[tuple[str, dict[str, Any]]]:
        client = self._client()
        claimed = client.xautoclaim(
            stream,
            group,
            consumer_name,
            min_idle_time=5_000,
            start_id="0-0",
            count=count,
        )
        if claimed[1]:
            return self._decode_messages([(stream, claimed[1])])
        messages = client.xreadgroup(
            groupname=group,
            consumername=consumer_name,
            streams={stream: ">"},
            count=count,
            block=block_ms,
        )
        return self._decode_messages(messages)

    # 将 Redis 返回的嵌套消息结构转换为命令 ID 与 JSON 载荷列表。
    @staticmethod
    def _decode_messages(messages) -> list[tuple[str, dict[str, Any]]]:
        decoded = []
        for _, entries in messages:
            for message_id, fields in entries:
                try:
                    payload = json.loads(fields["payload"])
                except (KeyError, TypeError, ValueError):
                    continue
                decoded.append((message_id, payload))
        return decoded
