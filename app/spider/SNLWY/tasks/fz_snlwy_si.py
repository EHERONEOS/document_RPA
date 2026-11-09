"""SNLWY 客户的 SNLWY Shipping Instruction 任务。"""

from __future__ import annotations

from app.core.task.context import TaskContext
from app.core.task.errors import BusinessError
from app.spider.SNLWY.base import SnlwyBase
from app.spider.SNLWY.actions.si_navigation import SiNavigationMixin
from app.spider.SNLWY.actions.si_fill_port_info import SiFillPortInfoMixin
from app.spider.SNLWY.actions.si_fill_address_info import SiFillAddressInfoMixin
from app.spider.SNLWY.actions.si_fill_container_cargo import SiFillContainerCargoMixin
from app.spider.SNLWY.actions.si_fill_requirement import SiFillRequirementMixin
from app.spider.SNLWY.actions.si_save_submit import SiSaveSubmitMixin



class FzSnlwySiTask(
    SiNavigationMixin,
    SiFillPortInfoMixin,
    SiFillAddressInfoMixin,
    SiFillContainerCargoMixin,
    SiFillRequirementMixin,
    SiSaveSubmitMixin,
    SnlwyBase,
):
    """执行 FZ_SNLWY_SI。"""

    enable_record = True
    job_type = "SI"
    ignored_unfilled_fields = [
        *SnlwyBase.ignored_unfilled_fields,
        "podTemplate",
    ]

    def __init__(self, context: TaskContext):
        super().__init__(context)
        self.content = context.content or {}
        self.remain_content = context.remain_content or {}

    def execute_business(self) -> None:
        """从上到下展示完整填单流程；每个区块填写后立即校验。"""
        with self._step("01 检查下发数据"):
            self._validate_input()
        
        # 查询接口结束且按钮恢复后再操作，避免初始化期间点击无效。
        with self._step("02 查询订舱并进入提单页面"):
            self._goto_booking_page()
        
        with self._step("03 港口与签发信息"):
            self._fill_port_info()
        
        # TO ORDER、通知人同收货人、第二通知人的联动在地址模块处理。
        with self._step("04 收发通地址"):
            self._fill_address_info()
        
        with self._step("04.1 目的地附加要求"):
            self._fill_destination_requirements()
        
        with self._step("05 货物汇总"):
            self._fill_cargo_summary()
        
        # 已存在的箱也要核对详情，不能仅凭箱号存在就视为填单完成。
        with self._step("06 集装箱与VGM"):
            self._fill_containers()
        
        with self._step("07 装船、订舱及货物要求"):
            self._fill_requirements()
        
        with self._step("08 运费及附加费"):
            self._fill_surcharges()
        
        with self._step("09 附件上传"):
            self._fill_attachments()
        
        with self._step("10 接收通知邮箱"):
            self._fill_notification_emails()
        
        with self._step("11 漏填检查与填单截图"):
            self.raise_if_unfilled_fields()
            
        with self._step("12 保存提交"):
            self.upload_record_files_on_failure = True
            self.capture_business_screenshot("BEFORE_SUBMIT_IMG", "提交前")
            self.save_submit() # 保留原有试单保护：填完并截图后交给人工，不保存、不提交。
            self.capture_business_screenshot("AFTER_SUBMIT_IMG", "提交后")
        # # 后续接入保存提交时，应在这里明确处理操作类型与官网成功状态。
        # self.logger.info("[SNLWY][试单结束] 填单及校验完成，等待人工处理")
        # raise BusinessError("试单 请找RPA处理")

    def _validate_input(self) -> None:
        """在操作页面前检查关键数据，避免填到一半才发现结构错误。"""
        if not isinstance(self.content, dict):
            raise BusinessError("下发 content 必须是对象")
        booking_no = self.content.get("bookingNo")
        if not isinstance(booking_no, str) or not booking_no.strip():
            raise BusinessError("下发 bookingNo 必须是非空字符串")
        containers = self.content.get("containers")
        if not isinstance(containers, list) or not containers:
            raise BusinessError("下发 containers 必须是非空列表")
        seen = set()
        for index, container in enumerate(containers):
            if not isinstance(container, dict):
                raise BusinessError(f"第{index + 1}个集装箱必须是对象")
            container_no = str(container.get("containerNo") or "").strip()
            if not container_no:
                raise BusinessError(f"第{index + 1}个集装箱缺少箱号")
            if container_no in seen:
                raise BusinessError(f"下发集装箱号重复：{container_no}")
            seen.add(container_no)
        for key in ("surcharges", "cloudFileList"):
            if key in self.content and not isinstance(self.content[key], list):
                raise BusinessError(f"下发 {key} 必须是列表")


def fz_snlwy_si(context):
    """提供给 FZ_SNLWY_SI 路由调用的任务入口。"""
    return FzSnlwySiTask(context).run()
