import os

from funboost import BrokerEnum, PublisherParams, get_publisher
from funboost.core.func_params_model import TaskOptions

from app.core.logging.logger import log
from app.queue.rabbitmq import RabbitmqPublisherWithDlx, build_rabbitmq_broker_config


class ResultPublisher:
    """任务结果回传。"""

    DEFAULT_RESULT_QUEUE = "DOCUMENT_UPDATE"
    RETRY_TIMES = 3

    def __init__(self, queue_name=None):
        self.queue_name = (
            str(queue_name or os.getenv("RESULT_PUBLISH_QUEUE", self.DEFAULT_RESULT_QUEUE)).strip()
            or self.DEFAULT_RESULT_QUEUE
        )

    def publish_result(self, result):
        payload = self.build_reply_data(result)
        log(f"任务结果回传 {payload}")
        self.send_msg_to_queue(self.queue_name, payload)
        return payload

    def build_reply_data(self, result):
        """将任务结果转换为文档更新队列需要的消息结构。"""
        task_id = str(result.task_id or "").strip()
        if not task_id:
            raise ValueError("任务结果回传缺少 task_id")

        payload = {
            "id": task_id,
            "success": result.success,
            "code": self._resolve_code(result),
            "rpaMessageId": result.rpa_message_id,
            "saveType": result.save_type,
            "img": result.screenshot_url,
            "executeRecordFiles": result.record_url,
        }

        if result.content:
            payload["content"] = result.content
        if result.attachments:
            payload["attachments"] = result.attachments

        status_remarks = self._build_status_remarks(result)
        if status_remarks:
            payload["statusRemarks"] = status_remarks

        return payload

    def send_msg_to_queue(self, queue_name, data, delay=0):
        """临时发布一条结果回传消息。"""
        task_options = TaskOptions(countdown=delay) if delay else None
        broker_config = build_rabbitmq_broker_config().copy()
        broker_config.update({"passive": True})

        last_exc = None
        for _ in range(self.RETRY_TIMES):
            publisher = None
            try:
                publisher = get_publisher(
                    PublisherParams(
                        queue_name=queue_name,
                        logger_prefix=queue_name,
                        broker_kind=BrokerEnum.RABBITMQ_AMQPSTORM,
                        broker_exclusive_config=broker_config,
                        should_check_publish_func_params=False,
                        publisher_override_cls=RabbitmqPublisherWithDlx,
                    )
                )
                publisher.publish(msg={"task": data}, task_options=task_options)
                return True
            except Exception as exc:
                last_exc = exc
                log(f"任务结果回传失败 queue={queue_name} error={exc}", level="ERROR")
            finally:
                if publisher is not None:
                    publisher.close()

        if last_exc is not None:
            raise last_exc
        return False

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
