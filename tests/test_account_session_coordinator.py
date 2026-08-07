import threading
import multiprocessing
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.core.scheduler.account_session import (
    AccountSessionCoordinator,
    AccountSessionSettings,
    create_account_session_manager,
)


def make_settings(root, *, idle_seconds=60):
    return AccountSessionSettings(
        browser_user_data_dir=str(root),
        browser_port_start=13000,
        browser_port_end=13100,
        account_max_concurrent=3,
        account_idle_seconds=idle_seconds,
    )


def acquire_slot_in_spawned_worker(coordinator, result_queue):
    """Exercise the proxy shape passed to a spawned Queue Worker."""
    lease = coordinator.acquire_slot("1001_ZIM", "1001_ZIM")
    result_queue.put(lease)


class AccountSessionCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.coordinator = AccountSessionCoordinator(make_settings(self.directory.name))
        self.account_key = "1001_ZIM"

    def tearDown(self):
        self.coordinator.close()
        self.directory.cleanup()

    def test_first_login_opens_two_temporary_browser_slots_and_fourth_waits(self):
        first = self.coordinator.acquire_slot(self.account_key, self.account_key)
        self.assertTrue(first["is_primary"])
        self.assertTrue(first["is_login_leader"])

        second_result = {}
        second_ready = threading.Event()

        def acquire_second():
            second_result["lease"] = self.coordinator.acquire_slot(self.account_key, self.account_key)
            second_ready.set()

        second_thread = threading.Thread(target=acquire_second)
        second_thread.start()
        self.assertFalse(second_ready.wait(timeout=0.1))

        self.coordinator.login_finished(self.account_key, first["lease_id"], True)
        self.assertTrue(second_ready.wait(timeout=1))
        second = second_result["lease"]
        third = self.coordinator.acquire_slot(self.account_key, self.account_key)

        self.assertFalse(second["is_primary"])
        self.assertFalse(third["is_primary"])
        self.assertEqual(3, len({first["port"], second["port"], third["port"]}))

        fourth_result = {}
        fourth_ready = threading.Event()

        def acquire_fourth():
            fourth_result["lease"] = self.coordinator.acquire_slot(self.account_key, self.account_key)
            fourth_ready.set()

        fourth_thread = threading.Thread(target=acquire_fourth)
        fourth_thread.start()
        self.assertFalse(fourth_ready.wait(timeout=0.1))

        self.coordinator.release_slot(self.account_key, first["lease_id"])
        self.assertTrue(fourth_ready.wait(timeout=1))
        self.assertEqual(0, fourth_result["lease"]["slot_index"])

        for lease in (second, third, fourth_result["lease"]):
            self.coordinator.release_slot(self.account_key, lease["lease_id"])
        second_thread.join(timeout=1)
        fourth_thread.join(timeout=1)

    def test_failed_login_elects_only_one_new_primary_leader(self):
        first = self.coordinator.acquire_slot(self.account_key, self.account_key)
        second_result = {}
        second_ready = threading.Event()

        def acquire_second():
            second_result["lease"] = self.coordinator.acquire_slot(self.account_key, self.account_key)
            second_ready.set()

        second_thread = threading.Thread(target=acquire_second)
        second_thread.start()
        self.coordinator.login_finished(self.account_key, first["lease_id"], False)
        self.assertFalse(second_ready.wait(timeout=0.1))

        self.coordinator.release_slot(self.account_key, first["lease_id"])
        self.assertTrue(second_ready.wait(timeout=1))
        second = second_result["lease"]

        self.assertTrue(second["is_primary"])
        self.assertTrue(second["is_login_leader"])
        self.assertEqual("BOOTSTRAPPING", self.coordinator.snapshot()[self.account_key]["login_state"])
        self.coordinator.release_slot(self.account_key, second["lease_id"])
        second_thread.join(timeout=1)

    def test_idle_reaper_removes_temporary_profile_and_releases_its_port(self):
        first = self.coordinator.acquire_slot(self.account_key, self.account_key)
        self.coordinator.login_finished(self.account_key, first["lease_id"], True)
        second = self.coordinator.acquire_slot(self.account_key, self.account_key)
        temporary_profile = Path(second["user_data_path"])
        temporary_profile.mkdir(parents=True)
        self.coordinator.release_slot(self.account_key, second["lease_id"])
        self.coordinator.release_slot(self.account_key, first["lease_id"])

        self.coordinator._pools[self.account_key]["last_message_at"] = 0
        self.assertEqual(1, self.coordinator.reap_expired_slots())

        snapshot = self.coordinator.snapshot()[self.account_key]
        self.assertEqual(1, len(snapshot["slots"]))
        self.assertFalse(temporary_profile.exists())
        self.assertNotIn(second["profile_name"], self.coordinator._registry._load())

    def test_credential_login_waiter_reuses_newer_session_generation(self):
        first = self.coordinator.acquire_slot(self.account_key, self.account_key)
        self.coordinator.login_finished(self.account_key, first["lease_id"], True)
        second = self.coordinator.acquire_slot(self.account_key, self.account_key)
        third = self.coordinator.acquire_slot(self.account_key, self.account_key)

        leader = self.coordinator.claim_credential_login(
            self.account_key, second["lease_id"], second["login_generation"]
        )
        self.assertTrue(leader["is_leader"])
        self.coordinator.login_finished(self.account_key, second["lease_id"], True)
        follower = self.coordinator.claim_credential_login(
            self.account_key, third["lease_id"], third["login_generation"]
        )

        self.assertFalse(follower["is_leader"])
        self.coordinator.release_slot(self.account_key, first["lease_id"])
        self.coordinator.release_slot(self.account_key, second["lease_id"])
        self.coordinator.release_slot(self.account_key, third["lease_id"])

    def test_worker_exit_releases_its_account_slot(self):
        first = self.coordinator.acquire_slot(self.account_key, self.account_key, owner_pid=12345)
        self.coordinator.login_finished(self.account_key, first["lease_id"], True)
        second = self.coordinator.acquire_slot(self.account_key, self.account_key, owner_pid=23456)

        self.assertEqual(1, self.coordinator.release_worker_slots(12345))
        third = self.coordinator.acquire_slot(self.account_key, self.account_key, owner_pid=34567)

        self.assertEqual(0, third["slot_index"])
        self.coordinator.release_slot(self.account_key, second["lease_id"])
        self.coordinator.release_slot(self.account_key, third["lease_id"])

    def test_manager_proxy_is_shared_with_a_spawned_queue_worker(self):
        manager, coordinator = create_account_session_manager(make_settings(self.directory.name))
        process = None
        try:
            first = coordinator.acquire_slot(self.account_key, self.account_key)
            coordinator.login_finished(self.account_key, first["lease_id"], True)

            process_context = multiprocessing.get_context("spawn")
            result_queue = process_context.Queue()
            process = process_context.Process(
                target=acquire_slot_in_spawned_worker,
                args=(coordinator, result_queue),
            )
            process.start()
            second = result_queue.get(timeout=5)
            process.join(timeout=5)

            self.assertEqual(0, process.exitcode)
            self.assertFalse(second["is_primary"])
            coordinator.release_slot(self.account_key, first["lease_id"])
            coordinator.release_slot(self.account_key, second["lease_id"])
        finally:
            coordinator.close()
            manager.shutdown()
            if process is not None and process.is_alive():
                process.terminate()
                process.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
