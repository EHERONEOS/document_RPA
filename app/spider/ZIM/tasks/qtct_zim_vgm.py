import time

from app.core.task.context import TaskContext
from app.spider.ZIM.base import CarrierBase
from app.spider.ZIM import selectors
from app.core.task.errors import BusinessError, FormValidationError, LoginError
from app.core.page.dom import DomHelper
from app.utils.util_format import format_post_data

class QtctZimVgmTask(CarrierBase):
    """QTCT 客户的 ZIM VGM 任务。"""   
    enable_record = True # 是否开启录屏 
    job_type = "VGM"


    def __init__(self, context: TaskContext):
        super().__init__(context)
        self.content = context.content or {}
        self.remain_content = context.remain_content or {}

    def execute_business(self):
        """执行业务逻辑"""
        bo_row = self.query_booking(self.content.get("blNo"))
        if not bo_row.get('job_no'):
            raise BusinessError(f"ZIM VGM 填单失败，未查询到订单号")
        iframe_dom: DomHelper = self.dom.in_frame(*selectors.DC_LIST_FRAME)
        iframe_dom.click(*selectors.ROW_VGM_A)
        time.sleep(2)
        self.alert_iframe = iframe_dom.in_frame(*selectors.VGM_ALERT_FRAME)
        self.fill_base_fields()
        self.fill_containers()
        self.verify_from()
        self.raise_if_unfilled_fields(stage="ZIM VGM 填单流程")


    def fill_base_fields(self):
        """填写基础提单信息。"""
        for item in selectors.VGM_BASE_FILL_FIELDS:
            value = self.content.get(item["field"], "")
            self._fill_or_select(
                item["type"],
                item["locator"],
                value,
                name=item["name"],
            )

    def fill_containers(self):
        """填写箱货信息。"""
        contain_list = self.content.get("containers") or []
        time.sleep(1)
        self.alert_iframe.click_all(*selectors.VGM_DELETE_BTN, required=False, timeout=2)
        
        for index, contain in enumerate(contain_list, start=1):
            row_selector = f"{selectors.VGM_CON_BODY_ROW[0]}:nth-child({index})"
            self.alert_iframe.click(*selectors.VGM_ADD_BTN, timeout=2)

            for item in selectors.VGM_CONTAINER_FILL_FIELDS:
                value = contain.get(item["field"], "")
                self._fill_or_select(
                    item["type"],
                    f"{row_selector} {item['locator']}",
                    value,
                    name=f"第 {index} 个箱货-{item['name']}",
                    o_selector=item.get("option_selector"),
                )


    def verify_from(self):
        """验证表单值。"""
        for item in selectors.VGM_BASE_FILL_FIELDS:
            null_check = item.get("skip_if_empty", False) # 是否忽略空值

            expected_value = str(self.remain_content.get(item["field"], "") or "") # 期望值，统一转字符串
            if not expected_value and null_check:
                self.mark_field_done(item["field"])
                continue
            actual_value = str(self._get_dom_value(item["type"], item["locator"]) or "") # 实际值，统一转字符串
            value_matched = actual_value == expected_value
            if not value_matched:
                raise FormValidationError(
                    f"{item['name'] or item['locator']} 值不匹配：输入值 {actual_value} != 期望值 {expected_value}"
                )
            self.mark_field_done(item["field"])
        
        contain_list = self.remain_content.get("containers") or []

        for index, contain in enumerate(contain_list, start=1):
            row_selector = f"{selectors.VGM_CON_BODY_ROW[0]}:nth-child({index})"
            for item in selectors.VGM_CONTAINER_FILL_FIELDS:
                null_check = item.get("skip_if_empty", False) # 是否忽略空值
                expected_value = str(contain.get(item["field"], "") or "") # 期望值，统一转字符串
                if not expected_value and null_check:
                    continue
                actual_value = str(self._get_dom_value(item["type"], f"{row_selector} {item['locator']}") or "") # 实际值，统一转字符串
                value_matched = actual_value == expected_value
                if not value_matched:
                    raise FormValidationError(
                        f"第 {index} 个箱货-{item['name']} 值不匹配：输入值 {actual_value} != 期望值 {expected_value}"
                    )
        self.mark_field_done("containers")


    def _fill_or_select(self,field_type,locator,value,name=None,o_selector=None):
        """根据字段类型填写或选择。"""
        if not value:
            return
        if field_type == "input":
            self.alert_iframe.input_text(locator, value, name=name)
        elif field_type == "select":
            self.alert_iframe.select(locator, value, name=name)
        elif field_type == "s_select":
            self.alert_iframe.search_select(locator, value, o_selector, name=name)
        else:
            raise ValueError(f"不支持的字段类型：{field_type}")

    def _get_dom_value(self,field_type,locator):
        """根据字段类型获取 DOM 元素的值。"""
        if field_type == "input":
            return self.alert_iframe.get_value(locator)
        elif field_type == "select":
            return self.alert_iframe.get_select_value(locator)
        elif field_type == "s_select":
            return self.alert_iframe.get_value(locator)
        else:
            raise ValueError(f"不支持的字段类型：{field_type}")

def qtct_zim_vgm(context):
    """QTCT_ZIM_VGM 队列入口。"""
    return QtctZimVgmTask(context).run()
