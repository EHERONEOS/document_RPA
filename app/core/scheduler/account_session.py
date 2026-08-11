"""协调由队列 Worker 进程共享的各账号浏览器槽位。"""

from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from multiprocessing.managers import BaseManager
from pathlib import Path
from typing import Any

from app.core.browser.port import BrowserPortRegistry
from app.core.logging.logger import log


@dataclass(frozen=True)
class AccountSessionSettings:
    """设备级账号会话协调器所需的配置。"""

    browser_user_data_dir: str
    browser_port_start: int
    browser_port_end: int
    account_max_concurrent: int = 3
    account_idle_seconds: int = 60

    @classmethod
    def from_app_settings(cls, settings):
        return cls(
            browser_user_data_dir=settings.browser_user_data_dir,
            browser_port_start=settings.browser_port_start,
            browser_port_end=settings.browser_port_end,
            account_max_concurrent=settings.account_max_concurrent,
            account_idle_seconds=settings.account_idle_seconds,
        )


class AccountSessionCoordinator:
    """维护单台设备的浏览器槽位、登录闸门和端口状态。

    队列 Worker 负责实际执行 RPA 任务。该对象只负责分配账号的三个浏览器
    槽位之一，并由多进程管理器托管，使独立启动的队列 Worker 共享同一份状态。
    """

    def __init__(self, settings: AccountSessionSettings):
        self.settings = settings
        self._root = Path(settings.browser_user_data_dir)
        self._ephemeral_root = self._root / ".ephemeral"
        self._registry = BrowserPortRegistry(
            self._root / "port_registry.json",
            settings.browser_port_start,
            settings.browser_port_end,
        )
        self._condition = threading.Condition()
        self._pools: dict[str, dict[str, Any]] = {}
        self._stop_event = threading.Event()
        self._reaper = threading.Thread(
            target=self._reap_loop,
            name="account-session-reaper",
            daemon=True,
        )
        self._reaper.start()

    def acquire_slot(
        self,
        account_key: str,
        primary_profile_name: str,
        owner_pid: int | None = None,
    ) -> dict[str, Any]:
        """阻塞等待，直到该账号获得可执行任务的专用浏览器槽位。"""
        with self._condition:
            pool = self._pools.get(account_key)
            if pool is None:
                pool = self._create_pool(account_key, primary_profile_name)
                self._pools[account_key] = pool
            elif pool["primary_profile_name"] != primary_profile_name:
                raise ValueError("同一账号会话键映射到了不同的主浏览器目录")

            pool["last_message_at"] = time.monotonic()
            while True:
                lease = self._try_acquire_slot(pool, owner_pid)
                if lease is not None:
                    return lease
                self._condition.wait(timeout=0.5)

    def release_slot(self, account_key: str, lease_id: str) -> None:
        """释放已完成任务的浏览器槽位，供下一个等待的消息使用。"""
        with self._condition:
            pool = self._pools.get(account_key)
            if pool is None:
                return
            slot = self._slot_for_lease(pool, lease_id)
            if slot is None:
                return

            self._release_slot_locked(pool, slot, lease_id)
            self._condition.notify_all()

    def release_worker_slots(self, owner_pid: int | None) -> int:
        """释放崩溃或被强制停止的 Worker 遗留的租约。"""
        if owner_pid is None:
            return 0
        released = 0
        with self._condition:
            for pool in self._pools.values():
                for slot in pool["slots"]:
                    if not slot["busy"] or slot.get("owner_pid") != int(owner_pid):
                        continue
                    self._release_slot_locked(pool, slot, slot["lease_id"])
                    released += 1
            if released:
                self._condition.notify_all()
        return released

    def login_finished(self, account_key: str, lease_id: str, success: bool) -> None:
        """上报 BaseRpaTask.login() 的完成结果。

        引导登录成功后会开放该账号的两个临时槽位。登录失败时，槽位池保持
        关闭，直到后续恰有一个任务被选举为下一任主登录任务。
        """
        with self._condition:
            pool = self._pools.get(account_key)
            if pool is None or self._slot_for_lease(pool, lease_id) is None:
                return

            is_bootstrap = pool["bootstrap_lease_id"] == lease_id
            is_credential_leader = pool["credential_login_lease_id"] == lease_id
            if success:
                if is_bootstrap or is_credential_leader or pool["login_state"] != "READY":
                    pool["login_generation"] += 1
                pool["login_state"] = "READY"
                if is_bootstrap:
                    pool["bootstrap_lease_id"] = None
            else:
                pool["login_state"] = "FAILED"
                if is_bootstrap:
                    pool["bootstrap_lease_id"] = None

            if is_credential_leader:
                pool["credential_login_lease_id"] = None
            self._condition.notify_all()

    def claim_credential_login(
        self,
        account_key: str,
        lease_id: str,
        known_login_generation: int,
    ) -> dict[str, Any]:
        """在缓存会话失效后选举一个任务提交凭据。

        观察到更高版本登录成功结果的等待任务会被要求重新加载 Cookie，而
        不会再次提交账号凭据。
        """
        with self._condition:
            pool = self._pools.get(account_key)
            if pool is None or self._slot_for_lease(pool, lease_id) is None:
                raise RuntimeError("浏览器槽位租约已失效")

            while True:
                if pool["login_generation"] > known_login_generation:
                    return {
                        "is_leader": False,
                        "login_generation": pool["login_generation"],
                    }
                owner = pool["credential_login_lease_id"]
                if owner in (None, lease_id):
                    pool["credential_login_lease_id"] = lease_id
                    return {
                        "is_leader": True,
                        "login_generation": pool["login_generation"],
                    }
                self._condition.wait(timeout=0.5)

    def register_browser_started(self, account_key: str, lease_id: str, pid: int | None) -> None:
        """记录浏览器 PID，以便空闲回收器关闭临时槽位。"""
        if pid is None:
            return
        with self._condition:
            pool = self._pools.get(account_key)
            if pool is None:
                return
            slot = self._slot_for_lease(pool, lease_id)
            if slot is not None:
                slot["pid"] = int(pid)

    def snapshot(self) -> dict[str, Any]:
        """返回用于诊断和测试的可序列化状态。"""
        with self._condition:
            return {
                account_key: {
                    "login_state": pool["login_state"],
                    "login_generation": pool["login_generation"],
                    "slots": [
                        {
                            "slot_index": slot["slot_index"],
                            "is_primary": slot["is_primary"],
                            "busy": slot["busy"],
                            "port": slot["port"],
                            "profile_name": slot["profile_name"],
                        }
                        for slot in pool["slots"]
                    ],
                }
                for account_key, pool in self._pools.items()
            }

    def close(self) -> None:
        """停止回收器并清理当前 Agent 所属的临时浏览器。"""
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        self._reaper.join(timeout=2)
        with self._condition:
            cleanup = []
            for pool in self._pools.values():
                retained = []
                for slot in pool["slots"]:
                    if slot["is_primary"]:
                        retained.append(slot)
                    else:
                        cleanup.append(dict(slot))
                pool["slots"] = retained
        self._cleanup_slots(cleanup)

    def _create_pool(self, account_key: str, primary_profile_name: str) -> dict[str, Any]:
        pool = {
            "account_key": account_key,
            "primary_profile_name": primary_profile_name,
            "slots": [],
            "login_state": "BOOTSTRAPPING",
            "bootstrap_lease_id": None,
            "credential_login_lease_id": None,
            "login_generation": 0,
            "last_message_at": time.monotonic(),
            "temp_generation": 0,
        }
        pool["slots"].append(self._new_primary_slot(pool))
        return pool

    def _try_acquire_slot(
        self,
        pool: dict[str, Any],
        owner_pid: int | None,
    ) -> dict[str, Any] | None:
        state = pool["login_state"]
        if state == "READY":
            slot = next((item for item in pool["slots"] if not item["busy"]), None)
            if slot is None and len(pool["slots"]) < self.settings.account_max_concurrent:
                slot = self._new_temporary_slot(pool, len(pool["slots"]))
                pool["slots"].append(slot)
            if slot is None:
                return None
            return self._lease_slot(
                pool,
                slot,
                is_login_leader=False,
                owner_pid=owner_pid,
            )

        # 第一条消息及每次登录失败后的重试都必须使用长期维护的主浏览器，
        # 以串行化凭据提交操作。
        primary = pool["slots"][0]
        if primary["busy"]:
            return None
        pool["login_state"] = "BOOTSTRAPPING"
        return self._lease_slot(
            pool,
            primary,
            is_login_leader=True,
            owner_pid=owner_pid,
        )

    def _new_primary_slot(self, pool: dict[str, Any]) -> dict[str, Any]:
        profile_name = pool["primary_profile_name"]
        return self._new_slot(
            pool,
            slot_index=0,
            profile_name=profile_name,
            user_data_path=self._root / profile_name,
            is_primary=True,
        )

    def _new_temporary_slot(self, pool: dict[str, Any], slot_index: int) -> dict[str, Any]:
        pool["temp_generation"] += 1
        account_digest = hashlib.sha256(pool["account_key"].encode("utf-8")).hexdigest()[:16]
        generation = pool["temp_generation"]
        profile_name = f"ephemeral-{account_digest}-{slot_index}-{generation}"
        return self._new_slot(
            pool,
            slot_index=slot_index,
            profile_name=profile_name,
            user_data_path=self._ephemeral_root / account_digest / f"slot-{slot_index}-{generation}",
            is_primary=False,
        )

    def _new_slot(
        self,
        pool: dict[str, Any],
        *,
        slot_index: int,
        profile_name: str,
        user_data_path: Path,
        is_primary: bool,
    ) -> dict[str, Any]:
        return {
            "slot_index": slot_index,
            "is_primary": is_primary,
            "profile_name": profile_name,
            "user_data_path": str(user_data_path),
            "port": self._registry.resolve_port(profile_name),
            "lease_id": None,
            "busy": False,
            "pid": None,
            "owner_pid": None,
        }

    @staticmethod
    def _slot_for_lease(pool: dict[str, Any], lease_id: str) -> dict[str, Any] | None:
        return next((slot for slot in pool["slots"] if slot["lease_id"] == lease_id), None)

    @staticmethod
    def _release_slot_locked(pool: dict[str, Any], slot: dict[str, Any], lease_id: str) -> None:
        if pool["login_state"] == "BOOTSTRAPPING" and pool["bootstrap_lease_id"] == lease_id:
            # 浏览器可能在执行登录前启动失败。
            pool["login_state"] = "FAILED"
            pool["bootstrap_lease_id"] = None
        if pool["credential_login_lease_id"] == lease_id:
            pool["credential_login_lease_id"] = None
        slot["lease_id"] = None
        slot["owner_pid"] = None
        slot["busy"] = False

    def _lease_slot(
        self,
        pool: dict[str, Any],
        slot: dict[str, Any],
        *,
        is_login_leader: bool,
        owner_pid: int | None,
    ) -> dict[str, Any]:
        lease_id = uuid.uuid4().hex
        slot["lease_id"] = lease_id
        slot["busy"] = True
        slot["owner_pid"] = int(owner_pid) if owner_pid is not None else None
        if is_login_leader:
            pool["bootstrap_lease_id"] = lease_id
        return {
            "account_key": pool["account_key"],
            "lease_id": lease_id,
            "slot_index": slot["slot_index"],
            "is_primary": slot["is_primary"],
            "profile_name": slot["profile_name"],
            "user_data_path": slot["user_data_path"],
            "port": slot["port"],
            "is_login_leader": is_login_leader,
            "login_generation": pool["login_generation"],
        }

    def _reap_loop(self) -> None:
        while not self._stop_event.wait(timeout=1):
            self.reap_expired_slots()

    def reap_expired_slots(self) -> int:
        """账号达到配置的空闲时间后关闭闲置的临时槽位。"""
        now = time.monotonic()
        with self._condition:
            cleanup = []
            for pool in self._pools.values():
                if now - pool["last_message_at"] < self.settings.account_idle_seconds:
                    continue
                retained = []
                for slot in pool["slots"]:
                    if slot["is_primary"] or slot["busy"]:
                        retained.append(slot)
                    else:
                        cleanup.append(dict(slot))
                pool["slots"] = retained
            if cleanup:
                self._condition.notify_all()
        self._cleanup_slots(cleanup)
        return len(cleanup)

    def _cleanup_slots(self, slots: list[dict[str, Any]]) -> None:
        for slot in slots:
            self._terminate_browser(slot.get("pid"))
            self._delete_ephemeral_profile(Path(slot["user_data_path"]))
            try:
                self._registry.release_port(slot["profile_name"])
            except Exception as exc:
                log(f"释放临时浏览器端口失败 profile={slot['profile_name']} error={exc}", level="ERROR")

    def _delete_ephemeral_profile(self, profile_path: Path) -> None:
        try:
            profile_path.resolve().relative_to(self._ephemeral_root.resolve())
        except ValueError:
            return
        try:
            shutil.rmtree(profile_path, ignore_errors=True)
        except Exception as exc:
            log(f"删除临时浏览器目录失败 path={profile_path} error={exc}", level="ERROR")

    @staticmethod
    def _terminate_browser(pid: int | None) -> None:
        if not pid:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    check=False,
                    capture_output=True,
                    timeout=10,
                )
            else:
                os.kill(pid, signal.SIGTERM)
        except (OSError, subprocess.SubprocessError):
            pass


class AccountSessionManager(BaseManager):
    """用于向已创建的队列 Worker 共享协调器的管理器宿主。"""


AccountSessionManager.register("AccountSessionCoordinator", AccountSessionCoordinator)


def create_account_session_manager(settings: AccountSessionSettings):
    """启动设备本地管理器，并返回管理器及其协调器代理。"""
    manager = AccountSessionManager()
    manager.start()
    return manager, manager.AccountSessionCoordinator(settings)
