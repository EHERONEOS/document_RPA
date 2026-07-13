import time

from app.Spider.ZIM import selectors
from app.Spider.ZIM.base import ZimBaseTask
from app.core.task.context import TaskContext


class ZimSiTask(ZimBaseTask):
    """ZIM 通用 SI 业务流程。"""

    business_code = "SI"
    incognito = False
    wait_page_load = False

    def __init__(self, context: TaskContext):
        super().__init__(context)
        self.content = context.content or {}
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
        self.fill_base_fields()
        self.fill_containers()
        self.raise_if_unfilled_fields(stage="ZIM SI 填单流程")
        self.verify_from()
        # self.verify_form_values(
        #     form_name="ZIM SI 表单",
        #     source=self.content,
        #     input_fields=selectors.SI_BASE_INPUT_FIELDS,
        #     select_fields=selectors.SI_BASE_SELECT_FIELDS,
        #     repeating_groups=(
        #         {
        #             "path": "totalContainers",
        #             "items": self.content.get("totalContainers") or [],
        #             "row_selector": selectors.CON_BODY_ROW,
        #             "input_fields": selectors.SI_CONTAINER_INPUT_FIELDS,
        #             "select_fields": selectors.SI_CONTAINER_SELECT_FIELDS,
        #         },
        #     ),
        # )

    def fill_base_fields(self):
        """填写基础提单信息。"""
        for field_type, locator, field_name in selectors.SI_BASE_FILL_FIELDS:
            self._fill_or_select_if_present(field_type, locator, field_name)

    def fill_containers(self):
        """填写箱货信息。"""
        contain_list = self.content.get("totalContainers") or []
        self.dom.click_all(selectors.DELETE_CON_BTN, required=False, timeout=2)

        for index, contain in enumerate(contain_list, start=1):
            row_selector = f"{selectors.CON_BODY_ROW}:nth-child({index})"
            self.dom.click(selectors.ADD_CON_BTN, timeout=2)
            for field_type, locator, field_name in selectors.SI_CONTAINER_FILL_FIELDS:
                self._fill_or_select_if_present(
                    field_type,
                    f"{row_selector} {locator}",
                    field_name,
                    contain,
                    timeout=2,
                )

        if contain_list:
            self.mark_field_done("totalContainers")


    def verify_from(self):
        """验证表单值。"""
        for field_type, locator, field_name in selectors.SI_BASE_FILL_FIELDS:
            self.verify_from_value(field_type, locator, field_name)
        contain_list = self.content.get("totalContainers") or []
        for index, contain in enumerate(contain_list, start=1):
            row_selector = f"{selectors.CON_BODY_ROW}:nth-child({index})"
            for field_type, locator, field_name in selectors.SI_CONTAINER_FILL_FIELDS:
                self.verify_from_value(field_type, f"{row_selector} {locator}", field_name, contain)
            
