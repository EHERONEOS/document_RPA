from app.Spider.WHL.base import WhlBaseTask


class WhlVgmTask(WhlBaseTask):
    """WHL 通用 VGM 业务流程。"""

    business_code = "VGM"
    incognito = False

    def execute_business(self) -> None:
        """执行 WHL VGM 通用填单流程。"""
        self.mark_field_done("bookingNo")
        self.log("WHL VGM 填单入口")
