import atexit
from threading import RLock

from funboost import BrokerEnum, PriorityConsumingControlConfig, PublisherParams, get_publisher

from app.core.logging.logger import log
from app.core.task.errors import MessageParseError, RpaError


class ResultPublisher:
    """任务结果回传。"""

    DOCUMENT_UPDATE = "gcp_document_update"
    RETRY_TIMES = 1
    _shared_publisher = None
    _publisher_lock = RLock()
    _exit_handler_registered = False

    def __init__(self):
        pass

    def publish_result(self, result):
        payload = self.build_reply_data(result)
        log(f"任务结果回传 {payload}")
        self.send_msg_to_queue( payload)
        return payload

    def build_reply_data(self, result):
        """将任务结果转换为文档更新队列需要的消息结构。"""
        task_id = str(result.task_id or "").strip()
        if not task_id:
            raise MessageParseError("任务结果回传缺少 task_id")

        payload = {
            "id": task_id,
            "success": result.success,
            "code": self._resolve_code(result),
            "rpaMessageId": result.rpaMessageId,
            "saveType": result.saveType,
            "img": result.img,
            "executeRecordFiles": result.executeRecordFiles,
        }

        if result.content:
            payload["content"] = result.content
        if result.attachments:
            payload["attachments"] = result.attachments

        status_remarks = {"message": result.remark}
        if status_remarks:
            payload["statusRemarks"] = status_remarks

        return payload

    def send_msg_to_queue(self, data, delay=0):
        """通过进程内复用的发布器发送结果回传消息。"""
        priority_control_config = PriorityConsumingControlConfig(countdown=delay) if delay else None

        last_exc = None
        for attempt in range(1, self.RETRY_TIMES + 1):
            try:
                self._publish_with_shared_connection(data, priority_control_config)
                return True
            except Exception as exc:
                last_exc = exc
                log(
                    f"任务结果回传失败 queue={self.DOCUMENT_UPDATE} "
                    f"attempt={attempt}/{self.RETRY_TIMES} error={exc}",
                    level="ERROR",
                )
                self.close_shared_publisher()

        if last_exc is not None:
            raise RpaError("任务结果回传失败") from last_exc
        return False

    @classmethod
    def _publish_with_shared_connection(cls, data, priority_control_config):
        """复用单个 AMQP 发布连接，并避免多个线程同时写入同一 Channel。"""
        with cls._publisher_lock:
            publisher = cls._get_shared_publisher()
            publisher.publish(
                msg={"task": data},
                priority_control_config=priority_control_config,
            )

    @classmethod
    def _get_shared_publisher(cls):
        if cls._shared_publisher is None:
            cls._shared_publisher = get_publisher(
                PublisherParams(
                    queue_name=cls.DOCUMENT_UPDATE,
                    logger_prefix=cls.DOCUMENT_UPDATE,
                    broker_exclusive_config=cls._broker_config(),
                    broker_kind=BrokerEnum.RABBITMQ_AMQPSTORM,
                )
            )
            if not cls._exit_handler_registered:
                atexit.register(cls.close_shared_publisher)
                cls._exit_handler_registered = True
        return cls._shared_publisher

    @classmethod
    def close_shared_publisher(cls):
        """关闭共享发布器；仅在连接异常、进程退出或显式停机时调用。"""
        with cls._publisher_lock:
            publisher = cls._shared_publisher
            cls._shared_publisher = None
            if publisher is None:
                return
            try:
                publisher.close()
            except Exception as exc:
                log(f"关闭结果回传发布器失败 queue={cls.DOCUMENT_UPDATE} error={exc}", level="ERROR")

    @classmethod
    def _broker_config(cls):
        return {
            "x-max-priority": None,
            "durable": True,
            "passive": True,
            "x-dead-letter-exchange": "timeout_dlx_exchange",
            "x-dead-letter-routing-key": "timeout_dlx_routing_key",
        }

    def _resolve_code(self, result):
        if result.code is not None:
            return result.code
        if result.success:
            return 200
        return 500

    def _build_status_remarks(self, result):
        if not (result.message or result.error_type):
            return {}

        status_remarks = {}
        if result.message:
            status_remarks["message"] = result.message
        if result.error_type:
            status_remarks["errorType"] = result.error_type
        return status_remarks
