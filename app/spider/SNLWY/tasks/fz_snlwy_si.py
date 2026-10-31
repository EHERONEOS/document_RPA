"""SNLWY 客户的 SNLWY Shipping Instruction 任务。"""

from __future__ import annotations

from app.core.task.context import TaskContext
from app.core.task.errors import BusinessError
from app.spider.SNLWY import selectors
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
        """按页面流程编排各个 SI 操作 Mixin。"""
        self._goto_booking_page()
        self._fill_port_info()
        self._fill_address_info()
        self._fill_container_cargo()
        self._fill_requirement()
        self.raise_if_unfilled_fields()
        raise BusinessError("试单 请找RPA处理")
        self.capture_business_screenshot("BEFORE_SUBMIT_IMG", "提交前")
        # self.save_submit()
        self.capture_business_screenshot("AFTER_SUBMIT_IMG", "提交后")

        pass


def fz_snlwy_si(context):
    """提供给 FZ_SNLWY_SI 路由调用的任务入口。"""
    return FzSnlwySiTask(context).run()
