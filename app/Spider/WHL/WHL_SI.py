from app.Spider.WHL.base import WhlBaseTask


class WhlSiTask(WhlBaseTask):
    """WHL 通用 SI 业务流程。"""

    business_code = "SI"
    incognito = False
    wait_page_load = False

    def execute_business(self) -> None:
        """执行 WHL SI 通用填单流程。"""
        self.fill_booking_no()
        self.fill_shipper()
        self.fill_consignee()
        self.fill_goods()
        self.submit_or_save()

    def fill_booking_no(self) -> None:
        """填写订舱号。"""
        self.mark_field_done("bookingNo")

    def fill_shipper(self) -> None:
        """填写发货人。"""
        self.mark_field_done("shipperTitle")
        self.mark_field_done("shipperAddress")

    def fill_consignee(self) -> None:
        """填写收货人。"""
        self.mark_field_done("consigneeTitle")
        self.mark_field_done("consigneeAddress")

    def fill_goods(self) -> None:
        """填写货物信息。"""
        self.mark_field_done("totalGoodsDesc")
        self.mark_field_done("totalGrossWeight")

    def submit_or_save(self) -> None:
        """保存或提交。"""
        self.log("WHL SI 保存或提交入口")
