"""部署控制库的数据访问实现。"""
from __future__ import annotations

import hashlib
import secrets
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from queue_control_deploy.server.config import DeploySettings
from queue_control_deploy.sync.config import target_connection


def utcnow() -> datetime:
    """返回 MySQL DATETIME 可用的 UTC 时间。

    出参：
        返回去掉 tzinfo 的当前 UTC 时间。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DeployRepository:
    """读写 queue_control_deploy，提供发布、目标和鉴权查询。"""

    def __init__(self, settings: DeploySettings):
        """保存部署服务配置。

        入参：
            ``settings``：部署配置，其中 sync.target_mysql_url 是新库。
        """
        self.settings = settings

    def _serialize_json(self, value: Any) -> str:
        """将结构化值转换为 MySQL JSON 字符串。

        入参：
            ``value``：dict/list 或已序列化文本。

        出参：
            返回 JSON 字符串。
        """
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def create_release(
        self,
        *,
        release_id: str,
        release_unit: str,
        version: str,
        git_commit: str,
        artifact_file_name: str,
        artifact_path: str,
        artifact_url: str,
        sha256: str,
        size_bytes: int,
        manifest: dict[str, Any],
        dependency_changed: bool,
        created_by: str = "release-api",
    ) -> dict[str, Any]:
        """登记一个发布版本。

        入参：
            参数来自制品上传接口，``manifest`` 为服务端构造的发布清单。

        出参：
            返回 API 使用的 release 字典。

        异常：
            ``ValueError``：同单元同版本重复登记时抛出。

        核心逻辑:
            1. 使用 API 预生成的 release_id 保证 manifest 和 URL 一致。
            2. 元数据与制品哈希一并写入事务。
        """
        now = utcnow()
        try:
            with target_connection(self.settings.sync) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO releases
                        (release_id, release_unit, version, git_commit, artifact_file_name,
                         artifact_path, artifact_url, sha256, size_bytes, manifest_json,
                         dependency_changed, status, created_by, created_at, updated_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'REGISTERED',%s,%s,%s)
                        """,
                        (
                            release_id, release_unit, version, git_commit, artifact_file_name,
                            artifact_path, artifact_url, sha256, size_bytes,
                            self._serialize_json(manifest), int(dependency_changed), created_by, now, now,
                        ),
                    )
                connection.commit()
        except Exception as exc:
            text = str(exc)
            if "uk_release_unit_version" in text:
                raise ValueError(f"发布版本已存在: {release_unit}/{version}") from exc
            raise
        return self.get_release(release_id)

    def get_release(self, release_id: str) -> dict[str, Any]:
        """按 ID 查询发布版本。

        入参：
            ``release_id``：发布 ID。

        出参：
            返回 camelCase API 字典。

        异常：
            ``KeyError``：不存在时抛出。
        """
        with target_connection(self.settings.sync) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM releases WHERE release_id = %s", (release_id,))
                row = cursor.fetchone()
        if not row:
            raise KeyError(release_id)
        row["manifest"] = json.loads(row.pop("manifest_json"))
        row["dependencyChanged"] = bool(row.pop("dependency_changed"))
        return {
            "releaseId": row["release_id"], "releaseUnit": row["release_unit"], "version": row["version"],
            "gitCommit": row["git_commit"], "artifactFileName": row["artifact_file_name"],
            "artifactPath": row["artifact_path"], "artifactUrl": row["artifact_url"],
            "sha256": row["sha256"], "sizeBytes": row["size_bytes"], "manifest": row["manifest"],
            "dependencyChanged": row["dependencyChanged"], "status": row["status"],
            "createdBy": row["created_by"], "createdAt": row["created_at"].isoformat(),
            "updatedAt": row["updated_at"].isoformat(),
        }

    def list_releases(self, release_unit: str | None = None) -> list[dict[str, Any]]:
        """列出发布版本，可按发布单元过滤。

        入参：
            ``release_unit``：可选过滤值。

        出参：
            返回按创建时间倒序的 release 列表。
        """
        with target_connection(self.settings.sync) as connection:
            with connection.cursor() as cursor:
                if release_unit:
                    cursor.execute("SELECT release_id FROM releases WHERE release_unit=%s ORDER BY created_at DESC", (release_unit,))
                else:
                    cursor.execute("SELECT release_id FROM releases ORDER BY created_at DESC")
                ids = [row["release_id"] for row in cursor.fetchall()]
        return [self.get_release(release_id) for release_id in ids]

    def authenticate_device(self, device_id: str, token: str) -> bool:
        """校验设备 ID 与设备 token。

        入参：
            ``device_id``：设备 ID。
            ``token``：Agent 请求携带的明文 token。

        出参：
            返回是否通过。

        核心逻辑:
            只查询新库 mirror_devices 的 token_hash，并使用恒时比较，避免时序泄露。
        """
        normalized = (device_id or "").strip()
        if not normalized or not token:
            return False
        with target_connection(self.settings.sync) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT token_hash FROM mirror_devices WHERE device_id=%s", (normalized,))
                row = cursor.fetchone()
        if not row:
            return False
        expected = row["token_hash"]
        # Agent 传输明文 token，数据库只保存 SHA-256；校验前必须先做同一摘要。
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return secrets.compare_digest(token_hash, expected) if expected else False

    def calculate_targets(self, release_unit: str) -> list[dict[str, Any]]:
        """计算发布单元需要更新的设备和受影响队列。

        入参：
            ``release_unit``：例如 ``carrier:ZIM``。

        出参：
            返回 ``[{"deviceId": ..., "affectedQueues": [...]}]``。

        核心逻辑:
            1. queue_catalog 找发布单元下启用队列。
            2. mirror_queue_assignments 找当前绑定设备。
            3. 按设备聚合并排序队列。
        """
        with target_connection(self.settings.sync) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.device_id, GROUP_CONCAT(a.queue_name ORDER BY a.queue_name SEPARATOR ',') AS queues
                    FROM queue_catalog c
                    JOIN mirror_queue_assignments a ON a.queue_name = c.queue_name
                    WHERE c.release_unit = %s AND c.enabled = TRUE
                    GROUP BY a.device_id
                    ORDER BY a.device_id
                    """,
                    (release_unit,),
                )
                rows = cursor.fetchall()
        return [
            {"deviceId": row["device_id"], "affectedQueues": row["queues"].split(",") if row["queues"] else []}
            for row in rows
        ]

    def get_rollout_target(self, rollout_id: str, device_id: str) -> dict[str, Any]:
        """查询发布批次中的一个目标设备。

        入参：
            ``rollout_id``：发布批次 ID。
            ``device_id``：目标设备 ID。

        出参：
            返回批次、发布和目标合并字段。

        异常：
            ``KeyError``：目标不存在时抛出。
        """
        normalized_device = (device_id or "").strip().upper()
        with target_connection(self.settings.sync) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT t.target_id, t.device_id, t.status, t.command_id,
                           t.affected_queues, r.release_id, r.release_unit, r.version,
                           r.artifact_url, r.sha256, r.manifest_json
                    FROM release_targets t
                    JOIN release_rollouts o ON o.rollout_id = t.rollout_id
                    JOIN releases r ON r.release_id = t.release_id
                    WHERE t.rollout_id=%s AND t.device_id=%s
                    """,
                    (rollout_id, normalized_device),
                )
                row = cursor.fetchone()
        if not row:
            raise KeyError(f"{rollout_id}:{normalized_device}")
        row["affectedQueues"] = json.loads(row.pop("affected_queues"))
        row["manifest"] = json.loads(row.pop("manifest_json"))
        return row

    def create_upgrade_command(
        self,
        *,
        release_id: str,
        rollout_id: str,
        device_id: str,
        artifact_base_url: str,
        drain_timeout_seconds: int,
        requested_by: str = "release-api",
    ) -> tuple[dict[str, Any], bool]:
        """为 rollout 目标创建幂等的升级命令记录。

        入参：
            ``release_id``：发布 ID。
            ``rollout_id``：发布批次 ID。
            ``device_id``：目标设备 ID。
            ``artifact_base_url``：Agent 可访问的服务根地址。
            ``drain_timeout_seconds``：Worker 协作排空超时。
            ``requested_by``：操作人或服务身份。

        出参：
            返回 ``(command, created)``；重复请求返回同一命令且 ``created=False``。

        异常：
            ``KeyError``：目标不存在或 release 与 rollout 不匹配时抛出。
            ``ValueError``：目标批次不包含该 release 或设备时抛出。

        核心逻辑:
            1. 校验目标确实属于 rollout 和 release。
            2. 事务内锁定目标；已绑定 command_id 时直接返回旧命令。
            3. 新命令与目标绑定在同一事务写入，保证审计和 rollout 状态一致。
        """
        target = self.get_rollout_target(rollout_id, device_id)
        # rollout 路径天然绑定 release；允许 API 不重复传 releaseId，避免两个来源不一致。
        release_id = target["release_id"] if not release_id else release_id
        if target["release_id"] != release_id:
            raise ValueError("release 与 rollout 目标不匹配")
        if target.get("command_id"):
            return self.get_deploy_command(target["command_id"]), False
        normalized_device = (device_id or "").strip().upper()
        command_id = str(uuid.uuid4())
        manifest = target["manifest"]
        payload = {
            "releaseId": target["release_id"],
            "releaseUnit": target["release_unit"],
            "version": target["version"],
            "artifactUrl": f"{artifact_base_url.rstrip('/')}{target['artifact_url']}",
            "sha256": target["sha256"],
            "manifest": manifest,
            "queues": target["affectedQueues"],
            "drainTimeoutSeconds": drain_timeout_seconds,
        }
        command = {
            "commandId": command_id,
            "deviceId": normalized_device,
            "action": "upgrade",
            "payload": payload,
        }
        now = utcnow()
        with target_connection(self.settings.sync) as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT command_id FROM release_targets WHERE target_id=%s FOR UPDATE",
                        (target["target_id"],),
                    )
                    latest = cursor.fetchone()
                    if latest and latest["command_id"]:
                        existing_id = latest["command_id"]
                    else:
                        cursor.execute(
                            """
                            INSERT INTO deploy_commands
                            (command_id, device_id, action, payload_json, state,
                             requested_by, created_at, updated_at)
                            VALUES (%s,%s,'upgrade',%s,'PENDING',%s,%s,%s)
                            """,
                            (
                                command_id, normalized_device, self._serialize_json(payload),
                                requested_by, now, now,
                            ),
                        )
                        cursor.execute(
                            """
                            UPDATE release_targets
                            SET command_id=%s, status='DISPATCHED', updated_at=%s
                            WHERE target_id=%s
                            """,
                            (command_id, now, target["target_id"]),
                        )
                        existing_id = command_id
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        if existing_id != command_id:
            return self.get_deploy_command(existing_id), False
        return self.get_deploy_command(command_id), True

    def mark_deploy_command_queued(self, command_id: str, redis_stream_id: str) -> None:
        """记录命令已成功写入 Redis 的流 ID。

        入参：
            ``command_id``：部署命令 ID。
            ``redis_stream_id``：XADD 返回的消息 ID。

        异常：
            ``KeyError``：命令不存在时抛出。

        核心逻辑:
            只更新新库审计表，把 PENDING 转为 QUEUED，便于崩溃后对账重发。
        """
        with target_connection(self.settings.sync) as connection:
            with connection.cursor() as cursor:
                affected = cursor.execute(
                    """
                    UPDATE deploy_commands
                    SET state='QUEUED', redis_stream_id=%s, updated_at=%s
                    WHERE command_id=%s
                    """,
                    (redis_stream_id, utcnow(), command_id),
                )
            connection.commit()
        if not affected:
            raise KeyError(command_id)

    def get_deploy_command(self, command_id: str) -> dict[str, Any]:
        """按 ID 查询部署命令审计。

        入参：
            ``command_id``：命令 ID。

        出参：
            返回 camelCase API 字典。

        异常：
            ``KeyError``：命令不存在时抛出。
        """
        with target_connection(self.settings.sync) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM deploy_commands WHERE command_id=%s", (command_id,))
                row = cursor.fetchone()
        if not row:
            raise KeyError(command_id)
        row["payload"] = json.loads(row.pop("payload_json"))
        return {
            "commandId": row["command_id"], "deviceId": row["device_id"],
            "action": row["action"], "payload": row["payload"], "state": row["state"],
            "errorMessage": row.get("error_message"),
            "redisStreamId": row.get("redis_stream_id"),
            "requestedBy": row.get("requested_by"),
            "createdAt": row["created_at"].isoformat(), "updatedAt": row["updated_at"].isoformat(),
        }

    def update_deploy_command_result(
        self, command_id: str, *, success: bool, error_message: str | None = None
    ) -> dict[str, Any]:
        """写入 Agent 上报后的部署命令终态。

        入参：
            ``command_id``：命令 ID。
            ``success``：Agent 执行是否成功。
            ``error_message``：失败原因，成功时通常为空。

        出参：
            返回更新后的命令审计。

        核心逻辑:
            幂等更新为 SUCCESS/FAILED；重复上报只刷新错误与时间。
        """
        state = "SUCCESS" if success else "FAILED"
        with target_connection(self.settings.sync) as connection:
            with connection.cursor() as cursor:
                affected = cursor.execute(
                    """
                    UPDATE deploy_commands
                    SET state=%s, error_message=%s, updated_at=%s
                    WHERE command_id=%s
                    """,
                    (state, error_message, utcnow(), command_id),
                )
            connection.commit()
        if not affected:
            raise KeyError(command_id)
        return self.get_deploy_command(command_id)

    def list_release_units(self) -> list[dict[str, Any]]:
        """列出部署目录中的全部发布单元。

        出参：
            返回发布单元、启用队列数量和最近更新时间。

        核心逻辑:
            只读取新库 ``queue_catalog``，供管理页下拉框使用。
        """
        with target_connection(self.settings.sync) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT release_unit, COUNT(*) AS queue_count,
                           MAX(updated_at) AS updated_at
                    FROM queue_catalog
                    WHERE enabled = TRUE
                    GROUP BY release_unit
                    ORDER BY release_unit
                    """
                )
                rows = cursor.fetchall()
        return [
            {
                "releaseUnit": row["release_unit"],
                "queueCount": int(row["queue_count"]),
                "updatedAt": row["updated_at"].isoformat(),
            }
            for row in rows
        ]

    def list_rollouts(
        self, release_id: str | None = None, *, limit: int = 30
    ) -> list[dict[str, Any]]:
        """列出发布批次及其目标设备。

        入参：
            ``release_id``：可选发布 ID 过滤。
            ``limit``：最多返回批次数，范围 1-100。

        出参：
            返回按创建时间倒序的 rollout 列表，每个 rollout 内嵌 targets。

        核心逻辑:
            1. 先查批次主表，避免一次性加载大量历史数据。
            2. 再按批次 ID 查询目标并按设备聚合到批次对象。
        """
        limit = max(1, min(int(limit), 100))
        conditions = []
        params: list[Any] = []
        if release_id:
            conditions.append("o.release_id = %s")
            params.append(release_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with target_connection(self.settings.sync) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT o.*, r.release_unit, r.version
                    FROM release_rollouts o
                    JOIN releases r ON r.release_id = o.release_id
                    {where}
                    ORDER BY o.created_at DESC
                    LIMIT %s
                    """,
                    (*params, limit),
                )
                rollout_rows = cursor.fetchall()
                if not rollout_rows:
                    return []
                rollout_ids = [row["rollout_id"] for row in rollout_rows]
                placeholders = ",".join("%s" for _ in rollout_ids)
                cursor.execute(
                    f"""
                    SELECT target_id, rollout_id, release_id, device_id, affected_queues,
                           status, attempt_count, command_id, active_version,
                           last_error, started_at, finished_at, created_at, updated_at
                    FROM release_targets
                    WHERE rollout_id IN ({placeholders})
                    ORDER BY device_id
                    """,
                    rollout_ids,
                )
                target_rows = cursor.fetchall()

        targets_by_rollout: dict[str, list[dict[str, Any]]] = {
            row["rollout_id"]: [] for row in rollout_rows
        }
        for row in target_rows:
            rollout_id = row["rollout_id"]
            targets_by_rollout[rollout_id].append(
                {
                    "targetId": row["target_id"],
                    "deviceId": row["device_id"],
                    "affectedQueues": json.loads(row["affected_queues"]),
                    "status": row["status"],
                    "attemptCount": int(row["attempt_count"]),
                    "commandId": row.get("command_id"),
                    "activeVersion": row.get("active_version"),
                    "lastError": row.get("last_error"),
                    "startedAt": row["started_at"].isoformat() if row.get("started_at") else None,
                    "finishedAt": row["finished_at"].isoformat() if row.get("finished_at") else None,
                    "createdAt": row["created_at"].isoformat(),
                    "updatedAt": row["updated_at"].isoformat(),
                }
            )
        return [
            {
                "rolloutId": row["rollout_id"],
                "releaseId": row["release_id"],
                "releaseUnit": row["release_unit"],
                "version": row["version"],
                "mode": row["mode"],
                "status": row["status"],
                "drainTimeoutSeconds": int(row["drain_timeout_seconds"]),
                "requestedBy": row["requested_by"],
                "targets": targets_by_rollout[row["rollout_id"]],
                "createdAt": row["created_at"].isoformat(),
                "updatedAt": row["updated_at"].isoformat(),
            }
            for row in rollout_rows
        ]

    def list_deploy_commands(
        self,
        *,
        device_id: str | None = None,
        state: str | None = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """列出部署命令审计记录。

        入参：
            ``device_id``：可选设备过滤。
            ``state``：可选命令状态过滤。
            ``limit``：最多返回条数，范围 1-100。

        出参：
            返回按创建时间倒序的部署命令列表。

        核心逻辑:
            只查询新库 ``deploy_commands``，支持管理页观察下发、排队和结果。
        """
        limit = max(1, min(int(limit), 100))
        conditions = []
        params: list[Any] = []
        if device_id:
            conditions.append("device_id = %s")
            params.append(device_id.strip().upper())
        if state:
            conditions.append("state = %s")
            params.append(state.strip().upper())
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with target_connection(self.settings.sync) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT command_id, device_id, action, payload_json, state,
                           error_message, redis_stream_id, requested_by,
                           created_at, updated_at
                    FROM deploy_commands
                    {where}
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (*params, limit),
                )
                rows = cursor.fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row.pop("payload_json"))
            result.append(
                {
                    "commandId": row["command_id"],
                    "deviceId": row["device_id"],
                    "action": row["action"],
                    "payload": payload,
                    "state": row["state"],
                    "errorMessage": row.get("error_message"),
                    "redisStreamId": row.get("redis_stream_id"),
                    "requestedBy": row.get("requested_by"),
                    "createdAt": row["created_at"].isoformat(),
                    "updatedAt": row["updated_at"].isoformat(),
                }
            )
        return result

    def create_rollout(
        self,
        release_id: str,
        *,
        mode: str,
        device_ids: list[str],
        drain_timeout_seconds: int,
        requested_by: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """创建发布批次和目标记录。

        入参：
            ``release_id``：发布 ID。
            ``mode``：canary/all。
            ``device_ids``：目标设备；mode=all 时自动计算。
            ``drain_timeout_seconds``：Worker 排空超时。
            ``requested_by``：操作人。
            ``dry_run``：True 只创建目标记录，不用于真实替换。

        出参：
            返回 rollout_id 和目标列表。

        核心逻辑:
            1. 校验 release。
            2. 计算或过滤目标设备。
            3. 事务写入 rollout 与 release_targets，失败统一回滚。
        """
        release = self.get_release(release_id)
        all_targets = self.calculate_targets(release["releaseUnit"])
        if mode == "all":
            selected = all_targets
        else:
            allowed = {item["deviceId"] for item in all_targets}
            unknown = [device_id for device_id in device_ids if device_id not in allowed]
            if unknown:
                raise ValueError(f"设备不在发布单元目标内: {','.join(unknown)}")
            selected = [item for item in all_targets if item["deviceId"] in set(device_ids)]
        if not selected:
            raise ValueError("没有可更新目标设备")
        rollout_id = str(uuid.uuid4())
        now = utcnow()
        status = "PLANNED" if not dry_run else "DRY_RUN"
        with target_connection(self.settings.sync) as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO release_rollouts
                        (rollout_id, release_id, mode, status, drain_timeout_seconds,
                         requested_by, created_at, updated_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (rollout_id, release_id, mode, status, drain_timeout_seconds, requested_by, now, now),
                    )
                    for target in selected:
                        cursor.execute(
                            """
                            INSERT INTO release_targets
                            (target_id, rollout_id, release_id, device_id, affected_queues,
                             status, created_at, updated_at)
                            VALUES (%s,%s,%s,%s,%s,'PENDING',%s,%s)
                            """,
                            (
                                str(uuid.uuid4()), rollout_id, release_id, target["deviceId"],
                                self._serialize_json(target["affectedQueues"]), now, now,
                            ),
                        )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return {"rolloutId": rollout_id, "status": status, "targets": selected}
