import json
import platform

from app.core.integrations.notifier import ProcessingNotifier
from app.core.integrations.oss import OssClient
from app.core.integrations.publisher import ResultPublisher
from app.core.integrations.redis_client import RedisClient
from app.core.page.recorder import Recorder
from app.core.page.http import HttpHelper
from app.core.page.dom import DomHelper
from app.core.page.screenshot import Screenshot
from app.core.task.errors import BusinessError, ElementNotFoundError, FormValidationError, LoginError
from app.core.task.errors import ResultPublishError, UnfilledFieldError
from app.core.task.result import TaskResult
from app.core.task.context import TaskContext
from app.core.logging.logger import Logger


class BaseRpaTask:
    """RPA 任务生命周期基类。"""

    enable_record = False
    incognito = False
    wait_page_load = False
    fail_on_unfilled_fields = False
    booking_no = ""
    ignored_unfilled_fields=[]# 忽略的未填字段列表
    attachments = [] #草稿件
    REDIS_MAIN= 15 # redis 索引(默认15)

    def __init__(
        self,
        context,
        *,
        browser_manager=None,
        notifier=None,
        publisher=None,
        oss_client=None,
    ):
        self.context = context or TaskContext()
        self.page = None
        self.dom = None
        self.http = None
        self.screenshot = None
        self.recorder = None
        # 附件属于单次任务，不能与同一进程中的其他任务共享。
        self.attachments = []
        self.logger = Logger()
        if browser_manager is None:
            from app.core.browser.manager import BrowserManager

            self.browser_manager = BrowserManager()
        else:
            self.browser_manager = browser_manager
        self.notifier = notifier or ProcessingNotifier()
        self.publisher = publisher or ResultPublisher()
        self.oss_client = oss_client or OssClient()
        self.util_redis = RedisClient(self.REDIS_MAIN) # 配置cookieredis


    def run(self):
        """执行完整任务生命周期。"""
        success = False
        code = 0
        screenshot_img = ""
        remark = ""
        try:
            if self.context.enable_notify:
                self.notifier.notify_processing(self.context)



            self.page = self.browser_manager.start(self.context, self)
            self.dom = DomHelper(self.page)
            self.http = HttpHelper(self.page)
            self.screenshot = Screenshot(self.page)
            self.login()
            self._try_start_recording()
            self.execute_business()
            self.logger.info(f"任务执行成功 queue={self.context.queue_name}")
            success = True
            code = 200
        except Exception as exc:
            self.logger.error(f"任务执行失败 queue={self.context.queue_name} error={exc}")
            success = False
            code = getattr(exc, "code", 500)
            remark = str(exc)
            if self.context.enable_result_publish:
                screenshot_img = self._upload_error_screenshot()
        finally:
            execute_record_files = self._collect_record_files()
            attachments = None
            if self.context.enable_result_publish:
                if success or len(self.attachments) > 0:
                    attachments = self._get_attachments_safely()
                result = TaskResult(
                    task_id=self.context.task_id or "",
                    success=success,
                    code=code,
                    rpaMessageId=self.context.rpa_message_id,
                    img=screenshot_img or "",
                    executeRecordFiles=execute_record_files,
                    remark=remark,
                    attachments=attachments or None,
                )
                try:
                    self.publisher.publish_result(result)
                except Exception as exc:
                    self.logger.error(
                        f"任务结果回传失败 task_id={result.task_id} "
                        f"rpaMessageId={result.rpaMessageId} error={exc}"
                    )
                    raise ResultPublishError("任务结果回传失败") from exc
            self.logger.info("任务结束，保留浏览器进程以便后续接管")
            return success

    def _try_start_recording(self):
        """尽力启动录屏，失败时不影响业务执行。"""
        if not self.should_record():
            return
        try:
            self.recorder = Recorder(
                self.page,
                queue_name=self.context.queue_name,
            )
            self.recorder.start()
        except Exception as exc:
            self.recorder = None
            self.logger.error(f"录屏启动失败，继续执行业务：{exc}")

    def _collect_record_files(self):
        """尽力停止、上传录屏，不影响业务结果回传。"""
        if self.recorder is None:
            return []
        try:
            record_file_path = self.recorder.stop()
            if record_file_path is None:
                return []
            file_info = self._upload_execute_video(record_file_path)
            if not isinstance(file_info, dict) or not file_info.get("objectName"):
                return []
            return [{
                "type": "SCREEN_RECORDING_FILE",
                "files": [{
                    "fileObjectName": file_info["objectName"],
                    "fileName": file_info.get("filename") or record_file_path.name,
                }],
            }]
        except Exception as exc:
            self.logger.error(f"录屏停止或上传失败，继续回传业务结果：{exc}")
            return []

    def _upload_execute_video(self, record_file_path):
        try:
            return self.oss_client.oss_upload(record_file_path, is_remove=True)
        except Exception as exc:
            self.logger.error(f"上传流程视频 OSS 失败：{exc}")
            return None

    def _upload_error_screenshot(self):
        """尽力上传失败截图，不覆盖触发任务失败的原始异常。"""
        if self.screenshot is None:
            self.logger.warn("截图工具未初始化，跳过失败截图")
            return ""

        try:
            file_path = self.screenshot.page_shot(
                self.booking_no,
                getattr(self, "carrier_code", ""),
                error=True,
            )
            file_info = self.oss_client.oss_upload(file_path)
            return file_info.get("objectName") or ""
        except Exception as exc:
            self.logger.error(f"失败截图或 OSS 上传失败：{exc}")
            return ""

    def _get_attachments_safely(self):
        """尽力上传附件，不让附件上传错误覆盖任务执行结果。"""
        try:
            return self.get_attachments()
        except Exception as exc:
            self.logger.error(f"任务附件上传失败：{exc}")
            return None

    def should_record(self):
        """仅在 Windows 上按业务开关录制并回传视频。"""
        return bool(
            self.enable_record
            and self.context.enable_result_publish
            and platform.system() == "Windows"
        )

    def login(self):
        """船司登录，由船司基类实现。"""
        print(f"执行 {self.carrier_code} 登录入口")
        raise LoginError("子类必须实现 login 方法")

    def execute_business(self):
        """执行业务填单，由具体业务类实现。"""
        raise BusinessError("子类必须实现 execute_business 方法")

    def mark_field_done(self, field_name,source=None):
        """字段填入成功后，从 remain_content 删除。"""
        source = self.remain_content if source is None else source
        source.pop(field_name, None)

    def raise_if_unfilled_fields(self, stage="填单流程"):
        """在具体填单阶段主动触发未填字段校验。"""
        ignored_fields = set(self.ignored_unfilled_fields or [])
        unfilled_fields = [
            field_name
            for field_name in self.context.remain_content.keys()
            if field_name not in ignored_fields
        ]
        if unfilled_fields:
            self.logger.warn(f"存在未处理字段：{unfilled_fields}")
            raise UnfilledFieldError(f"{stage}存在漏填字段：{unfilled_fields}")
        return unfilled_fields



    def _fill_or_select_if_present(self, field_type, locator, field_name, source=None, o_selector=None, frame=None, timeout=2, name=None):
        """按字段类型填写。"""
        source = self.content if source is None else source
        source = source or {}
        value = source.get(field_name, "")
        frame = frame or self.dom
        if value in (None, ""):
            return
        if field_type == "input":
            frame.input_text(locator, value, name=name, timeout=timeout)
        elif field_type == "select":
            frame.select(locator, value, name=name, timeout=timeout)
        elif field_type == "s_select":
            frame.search_select(locator, value, o_selector, name=name, timeout=timeout)
        else:
            raise ElementNotFoundError(f"不支持的字段类型：{field_type}")
        # self.mark_field_done(field_name,source)



    def verify_from_value(self, field_type, locator, field_name, source=None, frame=None, null_check=False, name=None, partial_match=False):
        """校验单个字段值。"""
        source = self.remain_content if source is None else source
        source = source or {}
        source_value = source.get(field_name, "")
        if not source_value and null_check:
            self.mark_field_done(field_name,source)
            return
        frame = frame or self.dom
        if field_type == "input":
            field_value = frame.get_value(locator, name=name)
        elif field_type == "select":
            field_value = frame.get_select_value(locator, name=name)
        elif field_type == "s_select":
            field_value = frame.get_value(locator, name=name)
        value_matched = field_value == source_value
        if partial_match:
            field_value_str = str(field_value)
            source_value_str = str(source_value)
            value_matched = value_matched or source_value_str in field_value_str or field_value_str in source_value_str
        if not value_matched:
            raise FormValidationError(
                f"{name or locator} 值不匹配：输入值 {field_value} != 期望值 {source_value}"
            )
        self.mark_field_done(field_name,source)


    def get_attachments(self):
        """发送草稿件。"""
        attachments = []
        for attachment in self.attachments:
            file_info = self.oss_client.oss_upload(attachment)
            attachments.append({
                "fileName": file_info['filename'],
                "type": "DRAFT",
                "fileObjectName": file_info['objectName']
            })
        return attachments
        # if self.attachments:
            # self.publisher.publish_attachments(self.attachments)
            # self.attachments = {}

    def save_cookies(self, cookies_redis_key):
        """保存浏览器 cookies。"""
        cookies = self.page.cookies()
        self.util_redis.set_redis_key(cookies_redis_key, json.dumps(cookies, ensure_ascii=False))

    def set_page_cookies(self, cookies_redis_key):
        """设置浏览器 cookies。"""
        cookies_str = self.util_redis.get_redis_key(cookies_redis_key)
        if not cookies_str:
            return
        cookies = json.loads(cookies_str)
        self.page.set.cookies(cookies)
