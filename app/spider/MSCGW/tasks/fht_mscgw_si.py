"""FHT 客户的 MSCGW Shipping Instruction 任务。"""

from __future__ import annotations

from app.core.task.context import TaskContext
from app.spider.MSCGW import selectors
from app.spider.MSCGW.base import MscgwBase
from app.spider.MSCGW.actions.si_fill_address_info import SiFillAddressInfoMixin
from app.spider.MSCGW.actions.si_fill_container_cargo import SiFillContainerCargoMixin
from app.spider.MSCGW.actions.si_fill_document_group import SiFillDocumentGroupMixin
from app.spider.MSCGW.actions.si_fill_free_booking_form import SiFillFreeBookingFormMixin
from app.spider.MSCGW.actions.si_fill_free_router_details import SiFillFreeRouterDetailsMixin
from app.spider.MSCGW.actions.si_fill_payment_type import SiFillPaymentTypeMixin
from app.spider.MSCGW.actions.si_fill_router_details import SiFillRouterDetailsMixin
from app.spider.MSCGW.actions.si_navigation import SiNavigationMixin
from app.spider.MSCGW.actions.si_save_submit import SiSaveSubmitMixin


class FhtMscgwSiTask(
    SiNavigationMixin,
    SiFillFreeBookingFormMixin,
    SiFillDocumentGroupMixin,
    SiFillAddressInfoMixin,
    SiFillRouterDetailsMixin,
    SiFillFreeRouterDetailsMixin,
    SiFillContainerCargoMixin,
    SiFillPaymentTypeMixin,
    SiSaveSubmitMixin,
    MscgwBase,
):
    """执行 FHT_MSCGW_SI。"""

    enable_record = True
    job_type = "SI"
    # FHT-specific fields can be added here without changing other task types.
    ignored_unfilled_fields = [
        *MscgwBase.ignored_unfilled_fields,
        "blankBill", "splitBill", "consolidatedBill",
    ]

    def __init__(self, context: TaskContext):
        super().__init__(context)
        self.content = context.content or {}
        self.remain_content = context.remain_content or {}
        self.blankBill = self.content.get("blankBill", False)
        self.splitOrConsolidatedBill = self.content.get("splitBill", False) or self.content.get(
            "consolidatedBill", False
        )

    def execute_business(self) -> None:
        """按页面流程编排各个 SI 操作 Mixin。"""

        self._goto_navigation()

        if self.splitOrConsolidatedBill:
            self.si_shadow = self.dom.get_shadow_root(selectors.FREE_ESI_SHADOW)
            self._fill_free_booking_form()
        else:
            self.si_shadow = self.dom.get_shadow_root(selectors.SI_SHADOW)

        self.select_document_group()
        self._fill_address_info("Shipper")
        self._fill_address_info("Consignee")
        self._fill_address_info("Notify Party")
        if self.content.get("secondNotifyName"):
            self._fill_address_info("Second Notify")
        if self.content.get("overseasAgentName"):
            self._fill_address_info("Forwarding Agency")

        if self.splitOrConsolidatedBill:
            self._fill_free_router_details()
        else:
            self._fill_router_details()

        self._fill_container_cargo()
        self._fill_payment_type()
        self.raise_if_unfilled_fields()
        # self.capture_business_screenshot("BEFORE_SUBMIT_IMG", "提交前")
        # self.save_submit()
        # self.capture_business_screenshot("AFTER_SUBMIT_IMG", "提交后")


def fht_mscgw_si(context):
    """提供给 FHT_MSCGW_SI 路由调用的任务入口。"""
    return FhtMscgwSiTask(context).run()
