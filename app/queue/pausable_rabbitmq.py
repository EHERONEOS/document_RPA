"""支持本地协作式排空的 RabbitMQ 消费者。

Funboost 内置暂停标识依赖 Redis。本消费者直接使用 AMQP 通道：先取消消息投递，
再让已经接收的任务完成正常的 Funboost ACK/NACK 生命周期。
"""
import json
import threading
import time
from typing import Any

from funboost.consumers.rabbitmq_amqpstorm_consumer import RabbitmqConsumerAmqpStorm
from funboost.core.func_params_model import PublisherParams


class PausableRabbitmqConsumer(RabbitmqConsumerAmqpStorm):
    """可停止接收新消息并安全排空的单队列消费者。"""

    # 初始化排空控制信号、任务计数器和 RabbitMQ 资源引用。
    def __init__(self, consumer_params):
        super().__init__(consumer_params)
        self._drain_requested = threading.Event()
        self._ready = threading.Event()
        self._drained = threading.Event()
        self._inflight = 0
        self._inflight_condition = threading.Condition()
        self._channel = None
        self._connection = None
        self._last_error = ""

    @property
    # 返回消费者运行期间记录的最近异常信息。
    def last_error(self) -> str:
        return self._last_error

    @property
    # 返回当前已接收但尚未完成 ACK/NACK 的任务数量。
    def inflight_tasks(self) -> int:
        with self._inflight_condition:
            return self._inflight

    # 等待 RabbitMQ 消费订阅成功建立。
    def wait_until_ready(self, timeout: float | None = None) -> bool:
        return self._ready.wait(timeout)

    # 等待停止订阅和已接收任务处理全部完成。
    def wait_until_drained(self, timeout: float | None = None) -> bool:
        return self._drained.wait(timeout)

    # 设置排空信号，使事件循环停止接收新消息。
    def request_drain(self) -> None:
        """停止接收新消息，并完成当前进程已接收的任务。"""
        self._drain_requested.set()

    # 记录一条已移交给 Funboost 执行的消息。
    def _mark_accepted(self) -> None:
        with self._inflight_condition:
            self._inflight += 1

    # 记录一条消息已完成 ACK/NACK 生命周期并唤醒等待方。
    def _mark_finished(self) -> None:
        with self._inflight_condition:
            self._inflight -= 1
            self._inflight_condition.notify_all()

    # 阻塞等待所有已接收消息完成处理。
    def _wait_for_inflight_tasks(self) -> None:
        with self._inflight_condition:
            while self._inflight:
                self._inflight_condition.wait(timeout=0.5)

    # 在 Funboost 完成消息处理后减少进行中任务计数。
    def _run(self, kw: dict[str, Any]):
        """仅在 Funboost 完成 ACK/NACK 处理后记录任务完成。"""
        try:
            return super()._run(kw)
        finally:
            self._mark_finished()

    # 将排空过程中不再处理的消息重新放回 RabbitMQ 队列。
    def _nack_after_drain(self, message) -> None:
        try:
            message.nack(requeue=True)
        except Exception as exc:
            self.logger.warning(
                "暂停期间回退消息失败 queue=%s error=%s", self.queue_name, exc
            )

    # 驱动 AMQP 事件循环，并在收到排空请求后安全关闭订阅。
    def _shedual_task(self):
        """运行 AMQP 事件循环，直到本地监管器请求排空。"""
        if self._drain_requested.is_set():
            self._drained.set()
            self._stop_flag = 1
            return

        from app.queue.rabbitmq import RabbitmqPublisherWithDlx

        try:
            publisher = RabbitmqPublisherWithDlx(
                PublisherParams(
                    queue_name=self.queue_name,
                    broker_exclusive_config=self.consumer_params.broker_exclusive_config,
                )
            )
            publisher.init_broker()
            self._connection = publisher.connection
            self._channel = publisher.channel
            publisher.channel_wrapper_by_ampqstormbaic.qos(
                self.consumer_params.concurrent_num
            )

            # 处理 RabbitMQ 投递的单条消息，并在排空时将其重新入队。
            def callback(message) -> None:
                if self._drain_requested.is_set():
                    self._nack_after_drain(message)
                    return
                accepted = False
                try:
                    body = json.loads(message.body)
                    self._print_message_get_from_broker("rabbitmq", body)
                    self._mark_accepted()
                    accepted = True
                    self._submit_task({"amqpstorm_message": message, "body": body})
                except Exception:
                    # 消息尚未提交给 Funboost，重新入队以免静默丢失。
                    self._nack_after_drain(message)
                    if accepted:
                        self._mark_finished()
                    raise

            publisher.channel_wrapper_by_ampqstormbaic.consume(
                callback=callback,
                queue=self.queue_name,
                no_ack=False,
            )
            self._ready.set()
            while not self._drain_requested.is_set():
                publisher.channel.process_data_events(auto_decode=True)
                time.sleep(0.01)

            # 先取消 Broker 订阅再等待。prefetch=1 时，该 Worker 最多只会保留
            # 一个未确认任务。
            publisher.channel.stop_consuming()
            self._wait_for_inflight_tasks()
            self._close_broker()
            self._drained.set()
            self._stop_flag = 1
        except Exception as exc:
            self._last_error = str(exc)
            self._drained.set()
            self._stop_flag = 1
            self.logger.error(
                "队列消费者异常退出 queue=%s error=%s", self.queue_name, exc,
                exc_info=True,
            )

    # 关闭当前 RabbitMQ 通道和连接，忽略关闭阶段的次要异常。
    def _close_broker(self) -> None:
        for resource in (self._channel, self._connection):
            if resource is None:
                continue
            try:
                resource.close()
            except Exception:
                pass
