from app.core.logging.logger import log


class ProcessingNotifier:
    """通知后台任务处理中。"""

    def notify_processing(self, context):
        log(f"通知处理中 rpaMessageId={context.rpa_message_id} queue={context.queue_name}")
