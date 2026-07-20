import time

from app.Spider.ZIM.common import selectors
from app.Spider.ZIM.common.base import ZimBaseTask
from app.core.task.context import TaskContext
from app.core.task.errors import LoginError


class ZimSiTask(ZimBaseTask):
    """ZIM 通用 SI 业务流程。"""

    business_code = "SI"
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
        bo_row = self.query_booking(self.booking_no)
        detail_url = (
            "https://cis.zim-logistics.com.cn/Ebooking/BookEdit/Hbl_Comfirm"
            f"?type=mbl&ord_no={bo_row.get('job_no')}"
        )
        self.page.get(detail_url)
        time.sleep(3)
        # element = self.dom._find("c:.center_box")
        # file_path = self.screenshot.element_shot(element,self.booking_no,"SI",error=False)
        # self.oss_client.oss_upload(file_path)
        
        self.fill_base_fields()
        self.fill_containers()
        self.verify_from()
        self.raise_if_unfilled_fields(stage="ZIM SI 填单流程")
        pass

    def fill_base_fields(self):
        """填写基础提单信息。"""
        for item in selectors.SI_BASE_FILL_FIELDS:
            field_type, locator, field_name = item[:3]
            o_selector = item[4] if len(item) > 4 else None
            self._fill_or_select_if_present(field_type, locator, field_name,o_selector=o_selector)

    def fill_containers(self):
        """填写箱货信息。"""
        contain_list = self.content.get("containers") or []
        self.dom.click_all(selectors.DELETE_CON_BTN, required=False, timeout=2)
        for index, contain in enumerate(contain_list, start=1):
            row_selector = f"{selectors.CON_BODY_ROW}:nth-child({index})"
            self.dom.click(selectors.ADD_CON_BTN, timeout=2)
            for field_type, locator, field_name in selectors.SI_CONTAINER_FILL_FIELDS:
                self._fill_or_select_if_present(
                    field_type,
                    f"{row_selector} {locator}",
                    field_name,
                    contain
                )


    def verify_from(self):
        """验证表单值。"""
        for item in selectors.SI_VERIFY_FIELDS:
            field_type, locator, field_name = item[:3]
            null_check = item[3] if len(item) > 3 else None
            self.verify_from_value(field_type, locator, field_name,null_check=null_check)
        contain_list = self.remain_content.get("containers") or []
        for index, contain in enumerate(contain_list, start=1):
            row_selector = f"{selectors.CON_BODY_ROW}:nth-child({index})"
            for field_type, locator, field_name in selectors.SI_CONTAINER_FILL_FIELDS:
                self.verify_from_value(field_type, f"{row_selector} {locator}", field_name, contain)
        self.mark_field_done("containers")
            
