import os
import time

from app.Spider.ZIM.common import selectors
from app.Spider.ZIM.common.base import ZimBaseTask
from app.core.page.dom import DomHelper
from app.core.task.context import TaskContext
from app.core.task.errors import LoginError


class ZimVGMTask(ZimBaseTask):
    """ZIM 通用 VGM 业务流程。"""

    business_code = "VGM"
    incognito = False
    wait_page_load = False

    def __init__(self, context: TaskContext):
        super().__init__(context)
        self.content = context.content or {}
        self.remain_content = context.remain_content or {}
        self.booking_no = self.content.get("jobNo")
        self.mark_field_done("jobNo")

    def execute_business(self):
        """执行业务流程。"""

        # img_path = self.screenshot.page_shot(self.booking_no,"SI",is_error=False)
        bo_row = self.query_booking(self.booking_no)
        iframe_dom: DomHelper = self.dom.in_frame(selectors.DC_LIST_FRAME) 
        iframe_dom.click(selectors.ROW_VGM_A)
        self.alert_iframe = iframe_dom.in_frame(selectors.VGM_ALERT_FRAME)
        self.fill_containers()
        self.fill_base_fields()
        self.verify_from()
        self.raise_if_unfilled_fields(stage="ZIM VGM 填单流程")
        pass
        # detail_url = (
        #     "https://cis.zim-logistics.com.cn/Ebooking/BookEdit/Hbl_Comfirm"
        #     f"?type=mbl&ord_no={bo_row.get('job_no')}"
        # )
        # self.page.get(detail_url)
        # time.sleep(3)
        # self.fill_base_fields()
        # self.fill_containers()
        # self.raise_if_unfilled_fields(stage="ZIM SI 填单流程")
        # self.verify_from()


    def fill_base_fields(self):
        """填写基础提单信息。"""
        for field_type, locator, field_name in selectors.VGM_BASE_FILL_FIELDS:
            self._fill_or_select_if_present(field_type, locator, field_name,frame=self.alert_iframe)

    def fill_containers(self):
        """填写箱货信息。"""
        contain_list = self.content.get("containers") or []
        self.alert_iframe.click_all(selectors.VGM_DELETE_BTN, required=False, timeout=2)
        for index, contain in enumerate(contain_list, start=1):
            row_selector = f"{selectors.VGM_CON_BODY_ROW}:nth-child({index})"
            self.alert_iframe.click(selectors.VGM_ADD_BTN, timeout=2)

            for field_type, locator, field_name in selectors.VGM_CONTAINER_FILL_FIELDS:
                self._fill_or_select_if_present(
                    field_type,
                    f"{row_selector} {locator}",
                    field_name,
                    contain,
                    frame=self.alert_iframe
                )


    def verify_from(self):
        """验证表单值。"""
        for item in selectors.VGM_BASE_FILL_FIELDS:
            field_type, locator, field_name = item[:3]
            null_check = item[3] if len(item) > 3 else None
            self.verify_from_value(field_type, locator, field_name,null_check=null_check)
        contain_list = self.remain_content.get("containers") or []
        for index, contain in enumerate(contain_list, start=1):
            row_selector = f"{selectors.VGM_CON_BODY_ROW}:nth-child({index})"
            for field_type, locator, field_name in selectors.VGM_CONTAINER_FILL_FIELDS:
                self.verify_from_value(field_type, f"{row_selector} {locator}", field_name, contain)
        self.mark_field_done("containers")
            
