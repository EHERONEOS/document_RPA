"""FHT 客户的 MSC Shipping Instruction 任务。"""
from email.errors import MessageParseError
import time

from app.core.task.context import TaskContext
from app.core.task.errors import BusinessError, ElementNotFoundError
from app.spider.MSC.base import MscBase
from app.spider.MSC import selectors


class FhtMscSiTask(MscBase):
    """执行 FHT_MSC_SI；当前仅验证并建立 MSC 登录会话。"""

    job_type = "SI"
    def __init__(self, context: TaskContext):
        super().__init__(context)
        self.content = context.content or {}
        self.remain_content = context.remain_content or {}

    def execute_business(self) -> None:
        """预留 SI 业务实现，当前不填写、保存或提交单据。"""
        # self._goto_shippinginstructions(self.content["bookingNo"])
        self.si_shadow = self.dom.get_shadow_root(selectors.SI_SHADOW)
        # self.select_document_group()

        # self._fill_address_info("Shipper")
        # self._fill_address_info("Consignee")
        # self._fill_address_info("Notify Party")
        # self.content.get("secondNotifyName") and  self._fill_address_info("Second Notify")
        # self.content.get("overseasAgentName") and  self._fill_address_info("Forwarding Agency")

        # self._fill_router_details()


        self._fill_container_cargo()
       

    def _fill_container_cargo(self) -> None:
        """填写集装箱信息"""
        containers = self.content.get("containers", [])
        if not containers:
            raise BusinessError("SI 中没有集装箱信息")
        for container in containers:
            self.si_shadow.click("c:#panel1-header [data-testid=container-options-button]")
            pass


    def _fill_router_details(self) -> None:
        """填写港口信息"""
        self.content.get("receiptPlace") and self.si_shadow.input_text(selectors.RECEIPT_INPUT, self.content.get("receiptPlace"), "收货地",required=False)
        self.content.get("pol") and self.si_shadow.input_text(selectors.POL_INPUT, self.content.get("pol"), "起运港")
        self.content.get("pod") and self.si_shadow.input_text(selectors.POD_INPUT, self.content.get("pod"), "卸货港")
        self.content.get("deliveryPlace") and self.si_shadow.input_text(selectors.DELIVERY_INPUT, self.content.get("deliveryPlace"), "交货地",required=False)


    # 收发通
    def _fill_address_info(self, address_type: str) -> None:
        """填写地址和参考"""

        # The dialog uses the same controls for every party; only the content
        # prefix changes between the five party types.
        # 关闭弹窗
        self.si_shadow.click("c:.si-party-modal-title button",required=False,timeout=1)
        self.si_shadow.click("c:.confirm-dialog-box button[data-testid=btnOkConfirm]",required=False,timeout=1)

        content_prefixes = {
            "Shipper": "shipper",
            "Consignee": "consignee",
            "Notify Party": "notify",
            "Second Notify": "secondNotify",
            "Forwarding Agency": "overseasAgent",
        }
        try:
            content_prefix = content_prefixes[address_type]
        except KeyError as exc:
            raise ValueError(f"不支持的地址类型: {address_type}") from exc

        edit_btn = self.si_shadow._find(
            f"x://h5[contains(text(),'{address_type}')]/button", required=False
        )
        if edit_btn:
            edit_btn.click()
        else:
            self.si_shadow.click(selectors.ADD_NEW_PARTY_BUTTON)
            self.si_shadow.click(
                f"x://ul[@data-testid='menuListAddNewParty']//li[contains(text(),'{address_type}')]"
            )

        def content_value(suffix: str):
            return self.content.get(f"{content_prefix}{suffix}")

        self.si_shadow.input_text(
            selectors.DIALOG_NAME, content_value("Name"), f"{address_type} Name"
        )
        self.si_shadow.input_text(
            selectors.DIALOG_ADDRESS_DETAILS,
            content_value("ContactAddress"),
            f"{address_type} Address",
        )
        self.si_shadow.input_text(
            selectors.DIALOG_TITLE, content_value("Title"), f"{address_type} Title"
        )
        self.si_shadow.input_text(
            selectors.DIALOG_ADDRESS, content_value("Address"), f"{address_type} Address"
        )
        self.si_shadow.input_text(
            selectors.DIALOG_CONTACT_REFERENCE,
            content_value("ContactReference"),
            f"{address_type} Reference",
        )
        self.dom.search_select_by_first_word(
            locator=selectors.DIALOG_LOCATION,
            value=content_value("City"),
            option_locator=selectors.DIALOG_LOCATION_OPTION,
            name="选择loaction",
        )

        optional_fields = (
            ("ContactName", selectors.DIALOG_CONTACT_NAME, "Contact Name"),
            ("Email", selectors.DIALOG_CONTACT_EMAIL, "Email"),
            ("Fax", selectors.DIALOG_CONTACT_FAX, "Fax"),
            ("Tel", selectors.DIALOG_CONTACT_PHONE, "Tel"),
        )
        for suffix, locator, label in optional_fields:
            field_value = content_value(suffix)
            if field_value:
                self.si_shadow.input_text(locator, field_value, f"{address_type} {label}")

        self.si_shadow.click(selectors.DIALOG_SAVE_BTN, f"保存{address_type}信息")
        time.sleep(1)
        if self.si_shadow._find(selectors.DIALOG_NAME, required=False):
            raise BusinessError(f"{address_type}保存失败")





    def select_document_group(self) -> None:
        """选择Document Group"""
        self.dom.select_radio(selectors.SELECT_DOCUMENT_RADIO, self.content["selectDocument"], "选择出单类型")
        
        match self.content["selectDocument"]:
            case "Sea Waybill":
                self.select_requested_copies()      
                return 
            case "Original":
                self.select_document_type()
                self.select_requested_copies()
                return 
            case "Original eBL":
                  self.select_document_type()
                  return 

    def select_document_type(self) -> None:
        """选择Document Type"""
        documentType  = self.content["documentType"]
        if documentType.get("Original Unfreighted") and int(documentType["Original Unfreighted"])>0:
            self.dom.select_radio(selectors.DOCUMENT_TYPE_RADIO, "Original Unfreighted", "选择Original Unfreighted")
            self.dom.input_text(selectors.UNFREIGHTED_NUM, documentType["Original Unfreighted"], "Original Unfreighted 数量")
        elif documentType.get("Original Freighted") and int(documentType["Original Freighted"])>0:
            self.dom.select_radio(selectors.DOCUMENT_TYPE_RADIO, "Original Freighted", "选择Original Freighted")
            self.dom.input_text(selectors.FREIGHTED_NUM, documentType["Original Freighted"], "Original Freighted 数量")

    def select_requested_copies(self) -> None:
        """选择Requested Copies"""
        requestedCopies  = self.content["requestedCopies"]
        if requestedCopies.get("Copy Unfreighted") and int(requestedCopies["Copy Unfreighted"])>0:
            dom = self.dom._find(selectors.REQUESTED_COPIES_UNFREIGHTED)
            if not dom.states.is_checked:
                dom.click()
            self.dom.input_text(selectors.COPIES_UNFREIGHTED_NUM, requestedCopies["Copy Unfreighted"], "Copy Unfreighted 数量")
        if requestedCopies.get("Copy Freighted") and int(requestedCopies["Copy Freighted"])>0:
            dom = self.dom._find(selectors.REQUESTED_COPIES_FREIGHTED)
            if not dom.states.is_checked:
                dom.click()
            self.dom.input_text(selectors.COPIES_FREIGHTED_NUM, requestedCopies["Copy Freighted"], "Copy Freighted 数量")



    def _goto_shippinginstructions(self, bookingNo: str) -> None:
        """跳转至 Shipping Instructions 填单页面"""
        last_error = None
        for _ in range(3):
            try:
                self.http.wait_api_finished(
                    selectors.DASHBOARD_GRAPHQL_API,
                    trigger=lambda: self.page.get(selectors.EBOOKINGS_URL),
                )
                break
            except:
                last_error = BusinessError("booking列表查询失败")
        else:
            raise last_error
        self.dom.input_text(selectors.BOOKING_SEARCH_INPUT, bookingNo,"搜索框", timeout=10)
        self.dom.click(selectors.SEARCH_BUTTON,'搜索按钮')
        page_booking_no = self.dom.get_text(selectors.BOOKING_FIRST_NUMBER, "第一条Booking Number", required=False)
        if not page_booking_no:
            raise BusinessError("未找到到Booking Number，可能是因为Booking Number不存在")
        if page_booking_no != bookingNo:
            raise BusinessError(f"Booking Number不匹配,页面值为{page_booking_no},消息值为{bookingNo}")
        page_status = self.dom.get_text(selectors.BOOKING_FIRST_STATUS, "第一条Booking Status", required=False)
        if page_status != "Confirmed":
            raise BusinessError(f"{bookingNo} 状态不是Confirmed,页面值为{page_status}")
        self.dom.click(selectors.BOOKING_FIRST_BUTTON, "跳转填单页面")
        self._wait_for_shippinginstructions()



    def _wait_for_shippinginstructions(self) -> None:
        """等待 跳转shippinginstructions。"""
        for _ in range(30):
            url = str(getattr(self.page, "url", "") or "")
            if selectors.SHIPPING_INSTRUCTIONS_URL in url:
                self.dom._find("css:#documents",timeout=20)
                return True
            time.sleep(1)
        raise BusinessError("MSC 未在 30 秒内跳转至 填单页面")


  

def fht_msc_si(context):
    """提供给 FHT_MSC_SI 路由调用的任务入口。"""
    return FhtMscSiTask(context).run()
