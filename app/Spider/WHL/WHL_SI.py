from app.Spider.WHL.base import WhlBaseTask


class WhlSiTask(WhlBaseTask):
    """WHL 通用 SI 业务流程。"""

    business_code = "SI"
    incognito = False
    wait_page_load = False

    def execute_business(self):
        """执行 WHL SI 通用填单流程。"""
        self.fill_booking_no()
        self.fill_shipper()
        self.fill_consignee()
        self.fill_goods()
        self.submit_or_save()

    def fill_booking_no(self):
        """填写订舱号。"""
        self.mark_field_done("bookingNo")

    def fill_shipper(self):
        """填写发货人。"""
        self.mark_field_done("shipperTitle")
        self.mark_field_done("shipperAddress")

    def fill_consignee(self):
        """填写收货人。"""
        self.mark_field_done("consigneeTitle")
        self.mark_field_done("consigneeAddress")

    def fill_goods(self):
        """填写货物信息。"""
        self.mark_field_done("totalGoodsDesc")
        self.mark_field_done("totalGrossWeight")

    def submit_or_save(self):
        """保存或提交。"""
        self.logger.info("WHL SI 保存或提交入口")
