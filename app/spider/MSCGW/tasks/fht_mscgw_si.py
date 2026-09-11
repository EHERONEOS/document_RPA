"""FHT 客户的 MSCGW Shipping Instruction 任务。"""
from email.errors import MessageParseError
import re
import time

from app.core.task.context import TaskContext
from app.core.task.errors import BusinessError, ElementNotFoundError, FormValidationError
from app.spider.MSCGW.base import MscgwBase
from app.spider.MSCGW import selectors
from app.spider.MSCGW.common.si_field_verify import (
    ADDRESS_OPTIONAL_FIELDS,
    ROUTER_DETAIL_FIELDS,
    MscgwSiFieldVerificationMixin,
    get_address_content_field_path,
)


class FhtMscgwSiTask(MscgwSiFieldVerificationMixin, MscgwBase):
    """执行 FHT_MSCGW_SI；当前仅验证并建立 MSCGW 登录会话。"""
    enable_record = True # 是否开启录屏
    job_type = "SI"
    def __init__(self, context: TaskContext):
        super().__init__(context)
        self.content = context.content or {}
        self.remain_content = context.remain_content or {}
        self.blankBill = self.content.get("blankBill", False)

    def execute_business(self) -> None:
        """预留 SI 业务实现，当前不填写、保存或提交单据。"""

        
        if self.blankBill:
            self._goto_create_shippinginstruction()
        else:
            self._goto_shippinginstructions(self.content["bookingNo"])
        self.si_shadow = self.dom.get_shadow_root(selectors.SI_SHADOW)

        self.select_document_group()
        
        self._fill_address_info("Shipper")
        self._fill_address_info("Consignee")
        self._fill_address_info("Notify Party")
        self.content.get("secondNotifyName") and  self._fill_address_info("Second Notify")
        self.content.get("overseasAgentName") and  self._fill_address_info("Forwarding Agency")
        
        self._fill_router_details()


        self._fill_container_cargo()

        self._fill_payment_type()
        self.raise_if_unfilled_fields()
        self.save_submit()
        pass


    def save_submit(self) -> None:
        """保存并提交单据"""
        self.si_shadow.click(selectors.SAVE_BOOKING_BTN, name="保存按钮")
        is_save_success = self.si_shadow._find(selectors.SAVE_SUCCESS_MSG, name="保存成功消息",timeout=10,required=False)
        if not is_save_success:
            raise BusinessError("截单保存失败")
        self.si_shadow.click(selectors.SAVE_SUCCESS_OK, name="保存成功确认按钮")
        self.page.wait.doc_loaded()
        self.si_shadow = self.dom.get_shadow_root(selectors.SI_SHADOW, timeout=20)
        for _ in range(30):
            preview_btn = self.si_shadow._find(selectors.PREVIEW_BTN, name="预览按钮",timeout=1,required=False)
            if preview_btn and preview_btn.states.is_enabled:
                preview_btn.click()
                break
            time.sleep(1)
        else:
            raise BusinessError("页面刷新后预览按钮未可用")
        for _ in range(30):
            download_preview_btn = self.si_shadow._find(selectors.DOWNLOAD_PREVIEW_BTN, name="下载预览按钮",timeout=1,required=False)
            if download_preview_btn and download_preview_btn.states.is_enabled:
                file_path = self.dom.click_to_download(
                    download_preview_btn,
                    name="下载预览按钮",
                )
                self.attachments.append(file_path)
                break
            time.sleep(1)
        self.si_shadow.click(selectors.DOWNLOAD_CLOSE_BTN, name="关闭下载预览按钮")



    def _fill_payment_type(self) -> None:
        """填写支付方式"""
        self.si_shadow.select_radio(selectors.PAYMENT_TYPE_RADIO,self.content.get("paymentType"),name="选择支付方式")
        if self.content.get("paymentType") == "Payable Elsewhere":
            self.dom.scroll_to_see(selectors.PAYMENT_LOCATION_INPUT)
            self.dom.search_select_by_first_word(
                locator=selectors.PAYMENT_LOCATION_INPUT,
                value=self.content.get("paymentLocation"),
                option_locator=selectors.DIALOG_LOCATION_OPTION,
                name="选择Elsewhere Location",
            )
        if self.content.get("remarks"):
            self.dom.scroll_to_see(selectors.PAYMENT_REMARK_INPUT)
            self.si_shadow.input_text(selectors.PAYMENT_REMARK_INPUT,self.content.get("remarks"),name="填写备注")
        self._verify_payment_type()

    def _fill_container_cargo(self) -> None:
        """填写集装箱信息"""
        containers = self.content.get("containers", [])
        if not containers:
            raise BusinessError("后台下发的集装箱信息为空")
        container_ele = self.dom._find_eles(selectors.CONTAINER_ITEM)
        if(len(container_ele) != len(containers)):
            raise FormValidationError("官网 SI 集装箱数量与填写数量不一致")
        self.dom.scroll_to_see("c:#Containers", name="定位到集装箱列表")
        for index,container in enumerate(containers):

            self.si_shadow.click(f"c:#panel{index+1}-header [data-testid=container-options-button]",name=f"{index+1}集装箱操作按钮")
            self.si_shadow.click(f"x://*[@id='panel{index+1}-header']//*[@id='split-button-menu']/li[normalize-space()='Edit Container']",name=f"{index+1}集装箱编辑按钮")
            time.sleep(2)
            self.si_shadow.input_text(
                selectors.CONTAINER_NUM_INPUT, container.get("containerNo"), f"{index+1} 集装箱Container Number"
            )
            time.sleep(2)
            self._verify_container_number(index)
            if not self._is_empty_expected_value(container.get("sealNo")):
                self.si_shadow.input_text(
                    selectors.CONTAINER_SEAL_NO_INPUT, container["sealNo"], f"{index+1} 集装箱Carrier Seal Number"
                )
            if not self._is_empty_expected_value(container.get("remarks")):
                self.si_shadow.input_text(
                    selectors.CONTAINER_COMMENTS_INPUT, container["remarks"], f"{index+1} 集装箱Remarks"
                )
            self.si_shadow.click(selectors.CARGO_TAB,name=f"{index+1}集装箱切换货物标签页")
            time.sleep(2)

            for _,cargo in enumerate(container.get("goods", [])):
                cargo_index = _ + 1
                cargo_ele =  self.si_shadow._find(f"x://*[@class='edit-cargo-list']/div[{cargo_index}]", required=False)
                if cargo_ele:
                    cargo_ele.click()
                else:
                    self.si_shadow.click(selectors.CARGO_ADD_BTN,name=f"{index+1}集装箱 {_+1}添加货物")
                    self.si_shadow.click(f"x://*[@class='edit-cargo-list']/div[{cargo_index}]",name=f"{index+1}集装箱 {_+1}货物")


                actual_hs_code = self.si_shadow.get_value(selectors.CARGO_CODE)
                if actual_hs_code != cargo.get("hsCode"):
                    self.si_shadow.input_text(
                        selectors.CARGO_CODE, cargo.get("hsCode"), f"{index+1}集装箱 {_+1}货物HS Code",blur=False
                    )  
                    time.sleep(2)
                    options = self.si_shadow._find_eles(selectors.CARGO_HS_OPTIONS)
                    matched = False
                    for option in options:
                        hs_code = (option.text or "").split("-", 1)[0].strip()
                        if hs_code == cargo.get("hsCode"):
                            option.click()
                            self.si_shadow.click(selectors.CARGO_CONFIRM, required=False)
                            matched = True
                            break
                    if not options or not matched:
                        raise BusinessError(f"找不到该hscode: {cargo.get('hsCode')}")           
                self.si_shadow.select_by_word(selectors.CARGO_WEIGHT_UNIT,cargo.get("grossWeightUnit"),selectors.CARGO_WEIGHT_UNIT_OPTIONS,name="选择Weight Unit")
                time.sleep(1)
                self.si_shadow.input_text(
                    selectors.CARGO_WEIGHT, cargo.get("grossWeight"), f"{index+1}集装箱 {_+1}货物Weight"
                )
                if not self._is_empty_expected_value(cargo.get("volume")):
                    self.si_shadow.select_by_word(selectors.CARGO_VOLUME_UNIT,cargo.get("volumeUnit"),selectors.CARGO_VOLUME_UNIT_OPTIONS)
                    time.sleep(1)
                    self.si_shadow.input_text(
                        selectors.CARGO_VOLUME, cargo["volume"], f"{index+1}集装箱 {_+1}货物Volume"
                    )
                self.si_shadow.select_by_word(
                    selectors.CARGO_PACKAGE_UNIT,cargo.get("packageUnit"),selectors.CARGO_PACKAGE_UNIT_OPTIONS,name="选择Package Unit"
                )
                time.sleep(1)
                self.si_shadow.input_text(
                    selectors.CARGO_PACKAGE, cargo.get("packages"), f"{index+1}集装箱 {_+1}货物NumberOfPackages"
                )
                self.si_shadow.input_text(
                    selectors.CARGO_DESC, cargo.get("goodsDesc"), f"{index+1}集装箱 {_+1}货物Description"
                )
                self.si_shadow.input_text(
                    selectors.CARGO_MARKS, cargo.get("marks"), f"{index+1}集装箱 {_+1}货物MarksAndNumbers"
                )



            self._verify_container_cargo(container, index)
            self.si_shadow.click(selectors.CONTAINER_SAVE_BTN,name=f"保存{index+1}集装箱")
            if not self._wait_for_container_save():
                raise BusinessError(f"集装箱 {index+1} 保存失败")


    def _wait_for_container_save(self) -> bool:
        """等待 集装箱保存成功。返回 True 如果保存成功，否则返回 False。"""
        for _ in range(10):
            save_dialog = self.si_shadow._find(selectors.CONTAINER_SAVE_BTN, required=False,timeout=0.5)
            if not save_dialog:
                return True
            time.sleep(1)
        return False


    def _fill_router_details(self) -> None:
        """填写港口信息"""
        for field_path, selector, name, required in ROUTER_DETAIL_FIELDS:
            value = self.content.get(field_path)
            if value:
                self.dom.scroll_to_see(selector, name, required=required)
                self.si_shadow.input_text(selector, value, name, required=required)
        self._verify_router_details()


    # 收发通
    def _fill_address_info(self, address_type: str) -> None:
        """填写地址和参考 {address_type 类型}"""

        # The dialog uses the same controls for every party; only the content
        # prefix changes between the five party types.
        # 关闭弹窗
        self.dom.scroll_to_see(selectors.ADD_NEW_PARTY_BUTTON, name="定位到添加新地址按钮")
        self.si_shadow.click("c:.si-party-modal-title button",required=False,timeout=0.5)
        self.si_shadow.click("c:.confirm-dialog-box button[data-testid=btnOkConfirm]",required=False,timeout=0.5)

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
            f"x://h5[contains(text(),'{address_type}')]/button", required=False,timeout=0.5
        )
        if edit_btn:
            edit_btn.click()
        else:
            self.si_shadow.click(selectors.ADD_NEW_PARTY_BUTTON, name="点击添加新地址按钮")
            self.si_shadow.click(
                f"x://ul[@data-testid='menuListAddNewParty']//li[contains(text(),'{address_type}')]", name=f"点击添加{address_type}按钮"
            )

        def content_value(suffix: str):
            return self.content.get(get_address_content_field_path(content_prefix, suffix))

        self.si_shadow.input_text(
            selectors.DIALOG_NAME, content_value("Name"), f"{address_type} Name"
        )
        self.si_shadow.input_text(
            selectors.DIALOG_ADDRESS_DETAILS,
            content_value("AddressDetails"),
            f"{address_type} Address",
        )
        self.si_shadow.input_text(
            selectors.DIALOG_TITLE, content_value("Title"), f"{address_type} Title"
        )
        self.si_shadow.input_text(
            selectors.DIALOG_ADDRESS, content_value("Address"), f"{address_type} Address"
        )
        self.search_location_select(selectors.DIALOG_LOCATION,content_value("City"),name=f"{address_type} Location")

        # 非必填
        for suffix, locator, label in ADDRESS_OPTIONAL_FIELDS:
            field_value = content_value(suffix)
            if field_value:
                self.si_shadow.input_text(locator, field_value, f"{address_type} {label}")
        # 校验字段
        self._verify_address_info(address_type, content_prefix)
        self.si_shadow.click(selectors.DIALOG_SAVE_BTN, f"保存{address_type}信息")
        if not self._wait_for_address_save():
            raise BusinessError(f"{address_type}保存失败")

    def _wait_for_address_save(self) -> bool:
        """等待 地址保存成功。返回 True 如果保存成功，否则返回 False。"""
        for _ in range(10):
            save_dialog = self.si_shadow._find(selectors.DIALOG_NAME, required=False,timeout=0.5)
            if not save_dialog:
                return True
            time.sleep(1)
        return False

    def search_location_select(self, location: str,value: str,name="选择loaction") -> None:
        """搜索并选择地址"""
        target_text = str(value).strip()
        if not target_text:
            raise ElementNotFoundError(f"{name}目标值为空")

        normalize = lambda text: re.sub(r"\s+", " ", str(text or "")).strip().casefold()
        words = re.findall(r"[^\W_]+", target_text, flags=re.UNICODE)
        if not words:
            raise ElementNotFoundError(f"{name}目标值不包含可搜索单词：{target_text}")

        element  = self.si_shadow._find(location,name)
        element.click()

        search_keywords = []
        for index in range(1, len(words) + 1):
            search_keyword = " ".join(words[:index])
            search_keywords.append(search_keyword)
            self.logger.info(f"搜索并选择{name}，搜索关键词：{search_keyword}")
            self.http.wait_api_finished(
                url="https://services.mymsc.com/shipping-instruction/graphql",
                method=("POST",),
                trigger=lambda keyword=search_keyword: element.input(keyword, clear=True),
                request_params={
                    "operationName": "GetLocations",
                },
                timeout=10,
                required=False
            )
            for option in self.si_shadow._find_eles(selectors.DIALOG_LOCATION_OPTION,required=False):
                if normalize(option.text) != normalize(target_text):
                    continue
                option.click()
                self.page.run_js("arguments[0].blur();", element)
                self.logger.info(f"选择{name}")
                return True

        raise ElementNotFoundError(
                f"{name}选项不存在：{target_text}；已尝试搜索：{'；'.join(search_keywords)}"
            )


    def select_document_group(self) -> None:
        """选择Document Group"""
        self.si_shadow.select_radio(selectors.SELECT_DOCUMENT_RADIO, self.content["releaseMode"], "选择出单类型")
        release_mode = self.content["releaseMode"]
        if release_mode == "Sea Waybill":
            self.select_requested_copies()
        elif release_mode == "Original":
            self.select_document_type(release_mode)
            self.select_requested_copies()
        elif release_mode == "Original eBL":
            self.select_document_type(release_mode)
        self.verify_document_group()

    def select_document_type(self, release_mode: str) -> None:
        """选择Document Type"""
        document_type  = self.content.get("originalDocumentType")
        self.si_shadow.select_radio(selectors.DOCUMENT_TYPE_RADIO, document_type, "选择Document Type")
        if release_mode == "Original":
            if document_type == "Original Unfreighted":
                self.si_shadow.input_text(selectors.UNFREIGHTED_NUM, self.content.get("numberOfOriginal"), "Original Unfreighted 数量")
            elif document_type == "Original Freighted":
                self.si_shadow.input_text(selectors.FREIGHTED_NUM, self.content.get("numberOfFreightedOriginal"), "Original Freighted 数量")

    def select_requested_copies(self) -> None:
        """选择Requested Copies"""
        if self.content["copyUnfreighted"]:
            dom = self.si_shadow._find(selectors.REQUESTED_COPIES_UNFREIGHTED)
            if not dom.states.is_checked:
                dom.click()
            self.si_shadow.input_text(selectors.COPIES_UNFREIGHTED_NUM, self.content.get("numberOfCopy"), "Copy Unfreighted 数量")
        if self.content["copyFreighted"]:
            dom = self.si_shadow._find(selectors.REQUESTED_COPIES_FREIGHTED)
            if not dom.states.is_checked:
                dom.click()
            self.si_shadow.input_text(selectors.COPIES_FREIGHTED_NUM, self.content.get("numberOfFreightedCopy"), "Copy Freighted 数量")



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


    def _goto_create_shippinginstruction(self) -> None:
        """跳转至 空白提单 页面"""
        self.page.get(selectors.CREATE_SHIPPING_INSTRUCTIONS_URL)
        self.page._wait_loaded()
        self.dom.input_text(selectors.CREATE_BOOKING_INPUT, self.content["bookingNo"], "Booking Number")
        self.http.wait_api_finished(
            selectors.CHECK_BOOKING_API,
            trigger=lambda: self.dom.click(selectors.CREATE_CHECK_BOOKING_BTN),
        )
        create_btn = self.dom._find(selectors.CREATE_BOOKING_BTN, required=False,name="创建提单")
        if create_btn:
            create_btn.click()
            self._wait_for_shippinginstructions()
            return
        reset_create_btn = self.dom._find(selectors.RESET_CREATE_BOOKING_BTN, required=False,name="重置创建")
        if reset_create_btn and reset_create_btn.states.is_clickable:
            reset_create_btn.click()
            time.sleep(1)
            self.dom.click(selectors.RESET_CREATE_SUBMIT,name="确认重置创建")
            self.dom.click(selectors.RESET_CREATE_CANCEL,name="取消弹窗",required=False)
            self._wait_for_shippinginstructions()
            return

        no_booking = self.dom._find(selectors.CHECK_NO_BOOKING, required=False)
        if no_booking:
            raise BusinessError(f"单号{self.content.get('bookingNo')} 不存在")
        error_doms = self.dom._find_eles(selectors.CHECK_ERROR_LI, required=False) or []
        error_msgs = [
            (getattr(dom, "text", "") or "").strip()
            for dom in error_doms
            if (getattr(dom, "text", "") or "").strip()
        ]
        raise BusinessError(f"单号{self.content.get('bookingNo')}已创建,错误信息为{error_msgs}")



    def _wait_for_shippinginstructions(self) -> None:
        """等待 跳转shippinginstructions。"""
        for _ in range(30):
            url = str(getattr(self.page, "url", "") or "")
            if selectors.SHIPPING_INSTRUCTIONS_URL in url:
                self.dom._find("css:#documents",timeout=20)
                return True
            time.sleep(1)
        raise BusinessError("MSC 未在 30 秒内跳转至 填单页面")


  

def fht_mscgw_si(context):
    """提供给 FHT_MSCGW_SI 路由调用的任务入口。"""
    return FhtMscgwSiTask(context).run()
