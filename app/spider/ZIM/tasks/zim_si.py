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
        # self.dom.click(*selectors.SI_SAVE_BTN) #点击保存
        err_tip = self.dom.get_text(*selectors.ERR_TIP_INFO,required=False, timeout=2)
        if err_tip:
            raise BusinessError(f"ZIM SI 填单失败，官网提示：{err_tip}")
        file_path = self.screenshot.page_shot(self.booking_no,self.carrier_code,error=False)
        self.attachments.append(file_path)
        # self.http.wait_api_finished(
        #     selectors.SAVE_SI_API,
        #     trigger=lambda: self.dom.click(*selectors.SI_SAVE_BTN),
        #     timeout=20
        # )
        pass

    def fill_base_fields(self):
        """填写基础提单信息。"""
        for item in selectors.SI_BASE_FILL_FIELDS:
            field_type, locator, field_name, name = item[:4]
            o_selector = item[5] if len(item) > 5 else None
            self._fill_or_select_if_present(
                field_type,
                locator,
                field_name,
                o_selector=o_selector,
                name=name,
            )

    def fill_containers(self):
        """填写箱货信息。"""
        contain_list = self.content.get("containers") or []
        self.dom.click_all(*selectors.DELETE_CON_BTN, required=False, timeout=2)
        for index, contain in enumerate(contain_list, start=1):
            row_selector = f"{selectors.CON_BODY_ROW[0]}:nth-child({index})"
            self.dom.click(*selectors.ADD_CON_BTN, timeout=2)
            for field_type, locator, field_name, name in selectors.SI_CONTAINER_FILL_FIELDS:
                self._fill_or_select_if_present(
                    field_type,
                    f"{row_selector} {locator}",
                    field_name,
                    contain,
                    name=f"第 {index} 个箱货-{name}",
                )


    def verify_from(self):
        """验证表单值。"""
        for item in selectors.SI_VERIFY_FIELDS:
            field_type, locator, field_name, name = item[:4]
            null_check = item[4] if len(item) > 4 else False
            self.verify_from_value(
                field_type,
                locator,
                field_name,
                null_check=null_check,
                name=name,
            )
        contain_list = self.remain_content.get("containers") or []
        for index, contain in enumerate(contain_list, start=1):
            row_selector = f"{selectors.CON_BODY_ROW[0]}:nth-child({index})"
            for field_type, locator, field_name, name in selectors.SI_CONTAINER_FILL_FIELDS:
                self.verify_from_value(
                    field_type,
                    f"{row_selector} {locator}",
                    field_name,
                    contain,
                    name=f"第 {index} 个箱货-{name}",
                )
        self.mark_field_done("containers")
            
