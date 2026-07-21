import time

from app.spider.ZIM.common import selectors
from app.spider.ZIM.common.base import ZimBaseTask
from app.core.task.context import TaskContext
from app.core.task.errors import BusinessError, LoginError


class ZimSiTask(ZimBaseTask):
    """ZIM 通用 SI 业务流程。"""

    business_code = "SI"
    incognito = False # 是否使用无痕模式
    wait_page_load = False # 是否等待页面加载完成
    ignored_unfilled_fields = ["jobNo","blNo","carrier","isUserSave"]# 忽略的未填字段列表
    

    def __init__(self, context: TaskContext):
        super().__init__(context)
        self.content = context.content or {}
        self.remain_content = context.remain_content or {}
        self.booking_no = self.content.get("jobNo")
        # self.mark_field_done("jobNo")
        # self.mark_field_done("carrier")
        # self.mark_field_done("isUserSave")

    def execute_business(self):
        """执行业务流程。"""
        raise LoginError("ZIM SI 登录失败")
        bo_row = self.query_booking(self.content.get("blNo"))
        # self.mark_field_done("blNo")
        detail_url = (
            "https://cis.zim-logistics.com.cn/Ebooking/BookEdit/Hbl_Comfirm"
            f"?type=mbl&ord_no={bo_row.get('job_no')}"
        )
        self.page.get(detail_url,show_errmsg=True)
        time.sleep(3)
        
        self.fill_base_fields()
        self.fill_containers()
        self.verify_from()
        self.raise_if_unfilled_fields(stage="ZIM SI 填单流程")
        file_path = self.screenshot.page_shot(self.booking_no,self.carrier_code,error=False)
        self.attachments.append(file_path)
        result = self.http.wait_api_finished(
            selectors.SAVE_SI_API,
            trigger=lambda: self.dom.click(selectors.SI_SAVE_BTN),
            timeout=20,
            required=False
        )
        if not result:
            raise BusinessError("ZIM SI 保存失败")
        print(result)

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
            
