from app.core.integrations.notifier import ProcessingNotifier
from app.core.integrations.oss import OssClient
from app.core.integrations.publisher import ResultPublisher
from app.core.integrations.recorder import Recorder
from app.core.logging.logger import log
from app.core.task.result import TaskResult


class BaseRpaTask:
    """RPA 任务生命周期基类。"""

    enable_record = False
    incognito = False
    wait_page_load = False
    fail_on_unfilled_fields = False

    def __init__(
        self,
        context,
        *,
        browser_manager=None,
        notifier=None,
        publisher=None,
        recorder=None,
        oss_client=None,
    ):
        self.context = context
        self.page = None
        self.events = []
        if browser_manager is None:
            from app.core.browser.manager import BrowserManager

            self.browser_manager = BrowserManager()
        else:
            self.browser_manager = browser_manager
        self.notifier = notifier or ProcessingNotifier()
        self.publisher = publisher or ResultPublisher()
        self.recorder = recorder or Recorder()
        self.oss_client = oss_client or OssClient()

    def run(self):
        """执行完整任务生命周期。"""
        record_started = False
        record_url = ""
        try:
            if self.context.enable_notify:
                self.notifier.notify_processing(self.context)

            self.page = self.browser_manager.start(self.context, self)

            if self.should_record():
                self.recorder.start(self.context)
                record_started = True

            self.login()
            self.execute_business()
            unfilled_fields = self.check_unfilled_fields()
            if record_started:
                record_url = self.recorder.stop(self.context)
                record_started = False
            result = TaskResult(
                rpa_message_id=self.context.rpa_message_id,
                queue_name=self.context.queue_name,
                success=True,
                message="任务执行成功",
                unfilled_fields=unfilled_fields,
                record_url=record_url,
            )
            if self.context.enable_result_publish:
                self.publisher.publish_result(result)
            self.log(f"任务执行成功 queue={self.context.queue_name}")
            return result
        except Exception as exc:
            screenshot_url = self.oss_client.local_screenshot_path(self.context.rpa_message_id)
            result = TaskResult(
                rpa_message_id=self.context.rpa_message_id,
                queue_name=self.context.queue_name,
                success=False,
                message=str(exc),
                error_type=exc.__class__.__name__,
                unfilled_fields=list(self.context.remain_content.keys()),
                screenshot_url=screenshot_url,
                record_url=record_url,
            )
            if self.context.enable_result_publish:
                self.publisher.publish_result(result)
            self.log(f"任务执行失败 queue={self.context.queue_name} error={exc}")
            return result
        finally:
            if record_started:
                self.recorder.stop(self.context)
            self.log("任务结束，保留浏览器进程以便后续接管")

    def should_record(self):
        """判断当前任务是否录屏。"""
        if self.context.enable_record is not None:
            return self.context.enable_record
        return self.enable_record

    def log(self, message):
        """打印任务日志。"""
        log(message)

    def login(self):
        """船司登录，由船司基类实现。"""
        raise NotImplementedError("子类必须实现 login 方法")

    def execute_business(self):
        """执行业务填单，由具体业务类实现。"""
        raise NotImplementedError("子类必须实现 execute_business 方法")

    def mark_field_done(self, field_name):
        """字段填入成功后，从 remain_content 删除。"""
        self.context.remain_content.pop(field_name, None)

    def check_unfilled_fields(self):
        """检查未填字段。"""
        unfilled_fields = list(self.context.remain_content.keys())
        if unfilled_fields:
            self.log(f"存在未处理字段：{unfilled_fields}")
        return unfilled_fields
