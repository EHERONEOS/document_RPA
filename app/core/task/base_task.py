import json
import platform

from DrissionPage._elements.none_element import NoneElement
from DrissionPage._pages.chromium_base import ChromiumBase 

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
from app.core.browser.manager import BrowserManager



class BaseRpaTask:
    """RPA 任务生命周期基类。"""

    enable_record = False #是否开启录屏
    incognito = False #是否开启无痕模式
    wait_page_load = False #是否等待页面加载完成
    # booking_no = ""
    ignored_unfilled_fields=["carrier","isUserSave","blNo","jobNo"]# 忽略的未填字段列表
    attachments = [] #草稿件
    REDIS_MAIN= 15 # redis 索引(默认15)

    page: ChromiumBase = None # 页面实例



    def __init__(
        self,
        context
    ):
        self.context = context or TaskContext()
        self.job_no = context.content.get("jobNo") or context.content.get("blNo") or ""
        self.website_info = self.context.website_info # 账号信息
        self.page = None
        self.screenshot = None
        self.recorder = None
        self.dom = None
        self.http = None
        
        # 附件属于单次任务，不能与同一进程中的其他任务共享。
        self.logger = Logger()
        self.notifier = ProcessingNotifier() #通知消息实例
        self.publisher = ResultPublisher() #发布消息实例
        self.oss_client =  OssClient() #oss客户端实例
        self.util_redis = RedisClient(self.REDIS_MAIN) # 配置redis客户端实例


        self.browser_lease = getattr(self.context, "browser_lease", None)
        self.account_session_coordinator = getattr(
            self.context, "account_session_coordinator", None
        )

        self.browser_manager = BrowserManager(
            browser_lease=self.browser_lease,
            account_session_coordinator=self.account_session_coordinator,
        )
        


    def run(self):
        """执行完整任务生命周期。"""
        success = False
        code = 0
        screenshot_img = ""
        remark = ""
        try:
            # 任务开始通知消息
            if self.context.enable_notify:
                self.notifier.notify_processing(self.context)
            # 获取浏览器端口并获取初始化页面
            self.page = self.browser_manager.start(self.context, self)
            # 初始化dom助手
            self.dom = DomHelper(self.page)
            # 初始化http助手
            self.http = HttpHelper(self.page)
            # 初始化截图助手
            self.screenshot = Screenshot(self.page)
            # 执行登录 登录完成后释放登录锁
            login_success = False
            try:
                self.login()
                login_success = True
            finally:
                # 通知登录完成放开登录锁
                self._notify_login_finished(login_success)

            # 开启录屏
            self._try_start_recording()
            # 执行业务逻辑
            self.execute_business()
            self.logger.info(f"任务执行成功 queue={self.context.queue_name}")
            success = True
            code = 200
        except Exception as exc:
            self.logger.error(f"任务执行失败 queue={self.context.queue_name} error={exc}")
            success = False
            code = getattr(exc, "code", 500)
            remark = str(exc)
            # 上传错误截图
            if self.context.enable_result_publish:
                screenshot_img = self._upload_error_screenshot()
        finally:
            # 收集录屏文件
            execute_record_files = self._collect_record_files()
            attachments = None
            if self.context.enable_result_publish:
                # 上传草稿件
                if success or len(self.attachments) > 0:
                    attachments = self._get_attachments_safely()
                # 发送任务结束结果
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
                self.job_no,
                getattr(self, "job_type", ""),
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

    def claim_credential_login(self) -> bool:
        """同一账号同一时间只允许一个任务提交登录凭证。"""
        if not self.browser_lease or self.account_session_coordinator is None:
            return True
        result = self.account_session_coordinator.claim_credential_login(
            self.browser_lease["account_key"],
            self.browser_lease["lease_id"],
            int(self.browser_lease.get("login_generation", 0)),
        )
        self.browser_lease["login_generation"] = result["login_generation"]
        return bool(result["is_leader"])

    def _notify_login_finished(self, success: bool) -> None:
        if not self.browser_lease or self.account_session_coordinator is None:
            return
        try:
            self.account_session_coordinator.login_finished(
                self.browser_lease["account_key"],
                self.browser_lease["lease_id"],
                success,
            )
        except Exception as exc:
            self.logger.error(f"上报登录状态失败：{exc}")

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
