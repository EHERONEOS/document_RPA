from app.core.integrations.notifier import ProcessingNotifier
from app.core.integrations.oss import OssClient
from app.core.integrations.publisher import ResultPublisher
from app.core.page.recorder import Recorder
from app.core.page.http import HttpHelper
from app.core.page.dom import DomHelper
from app.core.page.screenshot import Screenshot
from app.core.task.errors import FormValidationError
from app.core.task.errors import UnfilledFieldError
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
    FILL_HANDLERS = {
        "input": "_fill_if_present",
        "select": "_select_if_present",
    }

    def __init__(
        self,
        context,
        *,
        browser_manager=None,
        notifier=None,
        publisher=None,
        # recorder=None,
        oss_client=None,
    ):
        self.context = context or TaskContext()
        self.page = None
        self.dom = None
        self.http = None
        self.screenshot = None
        self.recorder = None
        
        self.logger = Logger()
        self.events = []
        if browser_manager is None:
            from app.core.browser.manager import BrowserManager

            self.browser_manager = BrowserManager()
        else:
            self.browser_manager = browser_manager
        self.notifier = notifier or ProcessingNotifier()
        self.publisher = publisher or ResultPublisher()
        # self.recorder = recorder or Recorder()
        self.oss_client = oss_client or OssClient()

    def run(self):
        """执行完整任务生命周期。"""
        record_started = False
        record_url = ""
        success = False
        code = 0
        screenshot_url= ""
        remark = ""
        try:
            if self.context.enable_notify:
                self.notifier.notify_processing(self.context)

            self.page = self.browser_manager.start(self.context, self)
            self.dom = DomHelper(self.page)
            self.http = HttpHelper(self.page)
            self.screenshot = Screenshot(self.page)
            self.oss_client = OssClient()
            
            # self.recorder = Recorder(self.page)

            self.login()
            # if self.should_record():
            #     record_started = True
            self.execute_business()
            self.logger.info(f"任务执行成功 queue={self.context.queue_name}")
            success = True
            code = 200
        except Exception as exc:
            self.logger.error(f"任务执行失败 queue={self.context.queue_name} error={exc}")
            if self.context.enable_result_publish:
                
                file_path = self.screenshot.page_shot(self.booking_no,self.carrier_code,error=True)
                file_info = self.oss_client.oss_upload(file_path)
                screenshot_url = file_info.get("url") or ""
            success = False
            code = getattr(exc, "code", 0)  
            remark = str(exc)  
        finally:
            # if record_started:
            #     self.recorder.stop(self.context.queue_name, self.booking_no)
            if self.context.enable_result_publish:
                if success or len(self.attachments) > 0:
                    attachments = self.get_attachments()
                result = TaskResult(
                    task_id =self.context.task.get("id") or "",
                    success=success,
                    code=code,
                    rpaMessageId = self.context.rpa_message_id,
                    img=screenshot_url or "",
                    executeRecordFiles="",
                    remark=remark,
                    attachments=attachments or ""
                )
                self.publisher.publish_result(result)
            self.logger.info("任务结束，保留浏览器进程以便后续接管")

    def should_record(self):
        """判断当前任务是否录屏。"""
        if self.context.enable_record is not None:
            return self.context.enable_record
        return self.enable_record

    def login(self):
        """船司登录，由船司基类实现。"""
        print(f"执行 {self.carrier_code} 登录入口")
        raise NotImplementedError("子类必须实现 login 方法")

    def execute_business(self):
        """执行业务填单，由具体业务类实现。"""
        raise NotImplementedError("子类必须实现 execute_business 方法")

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



    def _fill_or_select_if_present(self, field_type, locator, field_name, source=None,o_selector=None,frame=None, timeout=2):
        """按字段类型填写。"""
        source = self.content if source is None else source
        source = source or {}
        value = source.get(field_name, "")
        frame = frame or self.dom
        if value in (None, ""):
            return
        if field_type == "input":
            frame.input_text(locator, value, timeout=timeout)
        elif field_type == "select":
            frame.select(locator, value, timeout=timeout)
        elif field_type == "s_select":
            frame.search_select(locator, value,o_selector, timeout=timeout)
        else:
            raise ValueError(f"不支持的字段类型：{field_type}")
        # self.mark_field_done(field_name,source)



    def verify_from_value(self, field_type, locator, field_name,source=None,frame=None,null_check=False):
        """校验单个字段值。"""
        source = self.remain_content if source is None else source
        source = source or {}
        source_value = source.get(field_name, "")
        if source_value is None and null_check:
            return
        frame = frame or self.dom
        if field_type == "input":
            field_value = frame.get_value(locator)
        elif field_type == "select":
            field_value = frame.get_select_value(locator)
        elif field_type == "s_select":
            field_value = frame.get_value(locator)
        if field_value != source_value:
            raise FormValidationError(f"{field_name} 值不匹配：输入值 {field_value} != 期望值 {source_value}")
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
