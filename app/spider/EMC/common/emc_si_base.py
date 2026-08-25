"""EMC Shipping Instruction 的客户无关页面流程。"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from DrissionPage import SessionPage

from app.core.task.context import TaskContext
from app.core.task.errors import BusinessError, ElementNotFoundError, FormValidationError
from app.spider.EMC import selectors
from app.spider.EMC.base import EmcBase


class EmcSiBaseTask(EmcBase):
    """实现旧 EMC SI 的查询、填单、校验、保存或提交流程。"""

    enable_record = True
    job_type = "SI"
    submit_roles = frozenset({
        "FULI", "ZHIYANG", "ANHAI", "DEYI", "KAIYANG", "YOUCHEN", "YILAIYUN",
        "ZHONGJISHILIANDA", "ANXINHANG", "AISHIYI", "WANNIANQING", "JIANHANG",
    })
    save_type_one_roles = frozenset({
        "KAIYANG", "QIANTANG", "CHENLI", "WANNIANQING", "HUILIDASH",
        "HUILIDASZ", "HUILIDAGZ", "DEYI",
    })
    legacy_metadata_fields = frozenset({
        "backfillTotalTareWeight", "backfillReleaseMode", "backfillTotalAmountUnit",
        "preStatus", "bookingType", "customerCode",
    })

    def __init__(self, context: TaskContext, **kwargs):
        super().__init__(context, **kwargs)
        self.content = context.content or {}
        self.customer_role = str(context.customer_role or "").upper()

    def execute_business(self):
        """按旧脚本的页面顺序完成 EMC SI。"""
        self._validate_known_top_level_fields()
        self._precheck_advance_cabinet()
        self._open_shipping_instruction()
        self._search_shipping_instruction()
        self._fill_parties_and_locations()
        self._fill_containers_and_goods()
        self._fill_basic_document_data()
        self._fill_contact_data()
        self._fill_remarks()
        self._finish_metadata_fields()
        self.raise_if_unfilled_fields(stage="EMC SI 填单流程")
        # self.capture_business_screenshot("BEFORE_SUBMIT_IMG", "before")
        # self._save_or_submit()
        # self.capture_business_screenshot("AFTER_SUBMIT_IMG", "after")
        # official_draft = self._try_download_official_draft()
        # if official_draft:
        #     self.attachments.append(official_draft)

    def get_result_attachments(self, execute_record_files):
        """复用提交前截图作为草稿件，匹配旧流程下载失败时的回退协议。"""
        attachments = super().get_result_attachments(execute_record_files)
        if attachments:
            return attachments
        before_record = next(
            (record for record in execute_record_files if record.get("type") == "BEFORE_SUBMIT_IMG"),
            None,
        )
        before_files = (before_record or {}).get("files") or []
        if not before_files:
            return attachments
        booking_no = self.content.get("bookingNo") or self.job_no
        return [{
            "fileName": f"草稿件 {booking_no}",
            "type": "DRAFT",
            "fileObjectName": before_files[0]["fileObjectName"],
        }, *attachments]

    def _try_download_official_draft(self):
        """尽力下载官网草稿 PDF；此步骤失败时由提交前截图作为附件回退。"""
        try:
            booking_no = self._required("bookingNo", "订舱号")
            self.page.get(self.si_url, show_errmsg=True)
            self.page.wait.doc_loaded()
            self._dismiss_never_show_tip()
            self._input_and_verify(selectors.QUICK_SEARCH_INPUT, booking_no, "EMC 草稿件订舱号查询", required=True)
            self.dom.click(selectors.QUICK_SEARCH_BUTTON, "EMC 草稿件查询按钮", timeout=5)

            for row in self.page.eles(selectors.DRAFT_RESULT_ROWS, timeout=10):
                page_booking_no = (row.ele("xpath:./td[1]", timeout=1).text or "").strip()
                if page_booking_no != booking_no:
                    continue
                page_status = (row.ele("xpath:./td[5]", timeout=1).text or "").strip().lower()
                if page_status != "processing":
                    self.logger.info(f"EMC 草稿件尚未就绪，订舱号={booking_no} 状态={page_status or '空'}")
                    return None
                params = row.ele(selectors.DRAFT_PDF, timeout=2).attr("params") or ""
                doc_id = self._query_parameter(params, "docId")
                aio_uniqid = self.dom.get_value(selectors.DRAFT_AIO_UNIQID, "EMC 草稿件会话标识", timeout=2)
                if not doc_id or not aio_uniqid:
                    raise BusinessError("EMC 草稿件下载缺少 docId 或 aio_uniqid")
                bl_no = (row.ele("xpath:./td[3]", timeout=1).text or "").strip() or booking_no
                return self._download_official_draft_pdf(str(aio_uniqid), doc_id, bl_no)
            self.logger.info(f"EMC 未找到可下载草稿件的订舱号：{booking_no}")
        except Exception as exc:
            self.logger.warn(f"EMC 官方草稿件下载失败，将使用截图回退：{exc}")
        return None

    def _download_official_draft_pdf(self, aio_uniqid: str, doc_id: str, bl_no: str):
        """用 DrissionPage SessionPage 复用当前登录 Cookie 下载草稿 PDF。"""
        session_page = SessionPage()
        try:
            session_page.set.cookies(self.page.cookies(all_domains=True))
            session_page.post(
                selectors.PDF_DOWNLOAD_URL,
                data={
                    "action": "BI",
                    "aio_uniqid": aio_uniqid,
                    "href": "/servlet/TUF1_ControllerServlet.do",
                    "mode": "pdfview",
                    "from": "query",
                    "docId": doc_id,
                },
                headers={"Referer": self.si_url, "Origin": "https://www.evergreen-shipping.cn"},
                timeout=30,
            )
            response = session_page.response
            content = getattr(response, "content", b"") if response else b""
            content_type = str(getattr(response, "headers", {}).get("Content-Type", "")).lower() if response else ""
            if not content.startswith(b"%PDF") and "pdf" not in content_type:
                raise BusinessError("EMC 官网草稿件响应不是 PDF")

            output_dir = (
                Path(self.browser_manager.settings.download_dir)
                / self.context.queue_name
                / (self.context.rpa_message_id or "unknown-message")
            )
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{bl_no}_草稿件.pdf"
            output_path.write_bytes(content)
            return output_path
        finally:
            session_page.close()

    @staticmethod
    def _query_parameter(params: str, name: str) -> str:
        for item in params.split("&"):
            key, separator, value = item.partition("=")
            if separator and key == name:
                return value
        return ""

    def _open_shipping_instruction(self):
        """从 EMC 菜单进入提单资料指示页，菜单不可用时直接打开 SI 地址。"""
        if self.si_url in (self.page.url or ""):
            return
        if self.dom.click_if_clickable(selectors.SI_MENU, "EMC 订舱/提单菜单", timeout=3):
            self.dom.click(selectors.SI_MENU_ITEM, "EMC 提单资料指示菜单", timeout=5)
            self.page.wait.doc_loaded()
            return

        self.page.get(self.si_url, show_errmsg=True)
        self.page.wait.doc_loaded()
        self.dom.click_if_clickable(selectors.SI_CONTACT_PAGE, "EMC 联络方式入口", timeout=2)

    def _precheck_advance_cabinet(self):
        """保留旧任务的 advance_cabinet 货柜追踪检查入口。"""
        mode = self.content.get("rpaMode")
        if mode == "advance_cabinet":
            # 旧流程仅允许经过货柜追踪页后继续；当前官网菜单随账号权限变化，未展示时明确失败。
            tracking = self.page.eles("x://*[text()='货柜追踪']", timeout=3)
            if not tracking:
                raise BusinessError("EMC advance_cabinet 未找到货柜追踪入口")
            tracking[0].click()
            self.dom.click("x://a[text()='货柜动态查询']", "EMC 货柜动态查询", timeout=5)
            self.dom.input_text("x://*[@id='NO']", self._required("bookingNo", "订舱号"), "EMC 货柜追踪订舱号")
            self.dom.click(
                "x://*[@id='nav-quick']//input", "EMC 货柜追踪查询按钮", timeout=5,
            )
            self._reject_restricted_transit_ports()
            self._open_shipping_instruction()
        self._done("rpaMode")

    def _reject_restricted_transit_ports(self):
        values = []
        for locator in (
            "x://*[@id='MainBox']/div/div/table[3]//table[3]//tr[5]/td[1]",
            "x://*[@id='MainBox']/div/div/table[3]//table[3]//tr[6]/td[1]",
            "x://*[@id='MainBox']/div/div/table[3]//table[4]//tr[3]/td[1]",
        ):
            value = self.dom.get_text(locator, required=False, timeout=2)
            if value:
                values.append(value.upper())
        blocked = {"DE": "德国", "PT": "葡萄牙", "BE": "比利时", "NL": "荷兰"}
        for country_code, country_name in blocked.items():
            if any(country_code in value for value in values):
                raise BusinessError(f"EMC 货柜追踪结果含{country_name}港口，请将分品名资料填入备注或品名栏")

    def _search_shipping_instruction(self):
        booking_no = self._required("bookingNo", "订舱号")
        if "EGLV" in booking_no.upper():
            raise BusinessError("EMC 订舱号含 EGLV 提单头，请删除后重新发起")
        self._dismiss_never_show_tip()
        if self.content.get("blankBill"):
            self.dom.click(selectors.BLANK_BILL_BUTTON, "EMC 空白提单入口", timeout=5)
            self._input_and_verify(selectors.BLANK_BILL_BOOKING_INPUT, booking_no, "空白提单订舱号", required=True)
            self.dom.click(selectors.MODAL_CONFIRM_BUTTON, "EMC 空白提单确认", timeout=5)
            self._raise_for_alert("EMC 创建空白提单")
            self._done("bookingNo", "blankBill")
            return

        self._input_and_verify(selectors.QUICK_SEARCH_INPUT, booking_no, "EMC 订舱号查询", required=True)
        self.dom.click(selectors.QUICK_SEARCH_BUTTON, "EMC 订舱号查询按钮", timeout=5)
        self._raise_for_alert("EMC 查询订舱号", timeout=2)
        result_row = self._find_search_result_row(booking_no)
        status_link = self._search_result_row_element(
            result_row, selectors.SEARCH_RESULT_STATUS, "EMC SI 状态",
        )
        status = self._normalize_text(status_link.text)

        if self.content.get("splitBill"):
            if status.lower() not in {"processing", "draft"}:
                raise BusinessError(f"EMC 当前状态不能拆单：{status}")
            split_bill_button = self._search_result_row_element(
                result_row, selectors.SEARCH_RESULT_SPLIT_BILL, "EMC 拆单按钮",
            )
            split_bill_button.click()
            self._input_and_verify(selectors.SPLIT_BILL_BOOKING_INPUT, booking_no, "EMC 拆单订舱号", required=True)
            self.dom.click(selectors.SPLIT_BILL_SUBMIT, "EMC 拆单确认", timeout=5)
            self._raise_for_alert("EMC 拆单")
            self._done("bookingNo", "splitBill")
            return

        if status != "Waiting for Creating":
            raise BusinessError(f"EMC 页面状态不是 Waiting for Creating：{status}")
        status_link.click()
        self._wait_for_shipping_instruction_form()
        self._done("bookingNo", "blankBill", "splitBill")

    def _wait_for_shipping_instruction_form(self):
        if not self.page.wait.ele_displayed(selectors.SHIPPER_INPUT, timeout=30):
            raise ElementNotFoundError("EMC 创建 SI 后表单未在 30 秒内加载")

    def _find_search_result_row(self, booking_no: str):
        """在动态查询结果中精确定位目标订舱号所在行。"""
        for row in self.page.eles(selectors.SEARCH_RESULT_ROWS, timeout=15):
            booking_cell = self._search_result_row_element(
                row, selectors.SEARCH_RESULT_BOOKING_NO, "EMC 查询订舱号",
            )
            if self._normalize_text(booking_cell.text) == booking_no:
                return row

        no_result = self.dom.get_text(selectors.NO_SEARCH_RESULT, required=False, timeout=1)
        suffix = f"：{no_result}" if no_result else ""
        raise BusinessError(f"EMC 未查询到订舱号 {booking_no}{suffix}")

    @staticmethod
    def _search_result_row_element(row, locator: str, name: str):
        element = row.ele(locator, timeout=2)
        if not element:
            raise ElementNotFoundError(f"{name}元素不存在：{locator}")
        return element

    def _dismiss_never_show_tip(self):
        if self.dom.click_if_clickable(selectors.NEVER_SHOW_CHECKBOX, "EMC 提示不再显示", timeout=1):
            self.dom.click_if_clickable(selectors.NEVER_SHOW_CONFIRM, "EMC 提示确认", timeout=2)

    def _fill_parties_and_locations(self):
        self._fill_consolidated_bookings()
        if self.content.get("splitBill"):
            self._clear_split_bill_page()
        self._input_and_verify(selectors.SHIPPER_INPUT, self.content.get("shipper"), "发货人", required=True)
        self._input_and_verify(selectors.CONSIGNEE_INPUT, self.content.get("consignee"), "收货人", required=True)
        self._input_and_verify(selectors.NOTIFY_INPUT, self.content.get("notify"), "通知人", required=True)
        self._done("shipper", "consignee", "notify")
        self._fill_optional_text(selectors.SECOND_NOTIFY_INPUT, "secondNotify", "第二通知人")

        self.dom.click(selectors.LOCATION_FORMAT, "EMC 自定义地点名称", timeout=5)
        for locator, field_name, name in (
            (selectors.RECEIPT_PLACE_ALIAS, "receiptPlace", "收货地"),
            (selectors.POL_ALIAS, "pol", "装货港"),
            (selectors.POD_ALIAS, "pod", "卸货港"),
            (selectors.DELIVERY_PLACE_ALIAS, "deliveryPlace", "目的地"),
        ):
            self._input_and_verify(locator, self.content.get(field_name), name, required=True)
            self._done(field_name)
        self.dom.click(selectors.LOCATION_ALIAS_CONFIRM, "EMC 自定义地点确认", timeout=5)

        self._fill_template_fields()
        self._fill_optional_text(
            selectors.TRANS_SHIPMENT_REQUIREMENTS,
            "transshipmentRequirements",
            "内陆转运要求",
        )

    def _fill_consolidated_bookings(self):
        combined = bool(self.content.get("consolidatedBill"))
        bookings = self.content.get("bookingNos")
        if combined:
            if not isinstance(bookings, list) or not bookings:
                raise BusinessError("EMC 并单缺少 bookingNos")
            self.dom.click(selectors.COMBINE_BOOKING_BUTTON, "EMC 并单入口", timeout=10)
            for index, booking in enumerate(bookings, start=1):
                if not isinstance(booking, dict) or not booking.get("bookingNo"):
                    raise BusinessError(f"EMC 第 {index} 条并单订舱号为空")
                self.dom.input_text(selectors.COMBINE_BOOKING_INPUT, str(booking["bookingNo"]), f"EMC 第 {index} 条并单订舱号")
                self.dom.click(selectors.COMBINE_ADD_BUTTON, "EMC 添加并单订舱号", timeout=3)
                self._raise_for_alert("EMC 添加并单订舱号", timeout=1)
            self.dom.click(selectors.COMBINE_CONFIRM_BUTTON, "EMC 并单确认", timeout=5)
        elif self.content.get("blankBill") or self.content.get("splitBill"):
            self.dom.click_if_clickable(selectors.COMBINE_BOOKING_BUTTON, "EMC 并单弹窗", timeout=2)
            self.dom.click_if_clickable(selectors.MODAL_CLOSE, "EMC 关闭并单弹窗", timeout=2)
        self._done("consolidatedBill", "bookingNos")

    def _clear_split_bill_page(self):
        for locator in (
            selectors.SHIPPER_INPUT, selectors.CONSIGNEE_INPUT, selectors.NOTIFY_INPUT,
            selectors.SECOND_NOTIFY_INPUT, selectors.TRANS_SHIPMENT_REQUIREMENTS,
            selectors.VGM_RESPONSIBLE_PARTY, selectors.VGM_AUTHORIZED_PERSON,
            selectors.TOTAL_MARKS, selectors.TOTAL_GOODS_DESCRIPTION, selectors.REMARKS,
        ):
            self.dom.input_text(locator, "", "EMC 拆单清空字段", required=False, timeout=1)
        self.dom.click_if_clickable(selectors.by_id("clearAllEnsData_btn"), "EMC 清空 ENS 资料", timeout=2)

    def _fill_template_fields(self):
        template = str(self.content.get("podTemplate") or "COMMON").upper()
        if template == "EU":
            self._expand_section(selectors.EORI_SECTION, selectors.SHIPPER_EORI)
            for locator, field_name, name in (
                (selectors.SHIPPER_EORI, "shipperEoriNo", "发货人 EORI"),
                (selectors.CONSIGNEE_EORI, "consigneeEoriNo", "收货人 EORI"),
                (selectors.NOTIFY_EORI, "notifyEoriNo", "通知人 EORI"),
                (selectors.SECOND_NOTIFY_EORI, "secondNotifyEoriNo", "第二通知人 EORI"),
            ):
                self._fill_optional_text(locator, field_name, name)
        elif template == "US":
            self._expand_section(selectors.US_SECTION, selectors.US_SHIPPER)
            for locator, field_name, name in (
                (selectors.US_SHIPPER, "shipperAceAci", "美国发货人 ACE/ACI"),
                (selectors.US_CONSIGNEE, "consigneeAceAci", "美国收货人 ACE/ACI"),
                (selectors.US_NOTIFY, "notifyAceAci", "美国通知人 ACE/ACI"),
                (selectors.US_SECOND_NOTIFY, "secondNotifyAceAci", "美国第二通知人 ACE/ACI"),
                (selectors.NVO_SCAC, "nvoScac", "NVO SCAC"),
            ):
                self._fill_optional_text(locator, field_name, name)
            if self.content.get("moreNotifyAceAci"):
                self.dom.click(selectors.US_MORE_NOTIFY_TOGGLE, "EMC 展开第三通知人 ACE/ACI", timeout=3)
                self._input_and_verify(selectors.US_MORE_NOTIFY, self.content["moreNotifyAceAci"], "美国第三通知人 ACE/ACI")
            self._done("moreNotifyAceAci")
            if self.content.get("aciNvocc"):
                self.dom.click(selectors.ACI_NVOCC, "EMC ACI NVOCC 选项", timeout=3)
            self._done("aciNvocc")
        elif template not in {"", "COMMON"}:
            self.logger.info(f"EMC podTemplate={template} 无额外页面字段")
        self._done("podTemplate")

    def _expand_section(self, section_locator, required_locator):
        if self.page.eles(required_locator, timeout=1):
            return
        self.dom.click(section_locator, "EMC 展开模板区", timeout=3)
        if not self.page.eles(required_locator, timeout=3):
            raise ElementNotFoundError("EMC 模板区展开后未出现输入字段")

    def _fill_containers_and_goods(self):
        submit_vgm = bool(self.content.get("submitWithVgm"))
        if submit_vgm:
            self._enable_vgm()
            self._input_and_verify(selectors.VGM_RESPONSIBLE_PARTY, self.content.get("responsibleParty"), "VGM 责任方", required=True)
            self._input_and_verify(selectors.VGM_AUTHORIZED_PERSON, self.content.get("authorizedPerson"), "VGM 授权人", required=True)
        self._done("submitWithVgm", "responsibleParty", "authorizedPerson")

        containers = self.content.get("containers")
        if not isinstance(containers, list) or not containers:
            raise BusinessError("EMC SI 缺少 containers")
        self._remove_default_containers()
        for index, container in enumerate(containers, start=1):
            self._fill_container(index, container, submit_vgm)
            if index < len(containers):
                self.dom.click(selectors.ADD_CONTAINER_BUTTON, "EMC 新增集装箱", timeout=5)
        self._done("containers")

        self._input_and_verify(selectors.TOTAL_MARKS, self.content.get("totalMarks"), "唛头", required=True)
        self._input_and_verify(selectors.TOTAL_GOODS_DESCRIPTION, self.content.get("totalGoodsDesc"), "货物描述", required=True)
        self._done("totalMarks", "totalGoodsDesc")
        self._fill_hs_codes()
        self._fill_filing_information()

    def _enable_vgm(self):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            toggles = self.page.eles(selectors.VGM_TOGGLE, timeout=1)
            if not toggles:
                time.sleep(0.2)
                continue
            if not toggles[0].states.is_checked:
                self.dom.click(selectors.VGM_TOGGLE, "EMC VGM 开关", timeout=3)
                time.sleep(0.2)
                continue
            fields = self.page.eles(selectors.VGM_RESPONSIBLE_PARTY, timeout=1)
            if fields and fields[0].states.has_rect:
                return
            time.sleep(0.2)
        raise ElementNotFoundError("EMC VGM 开启后责任方字段未在 15 秒内显示")

    def _remove_default_containers(self):
        group_count = len(self.page.eles(selectors.CONTAINER_GROUPS, timeout=2))
        for _ in range(max(group_count - 1, 0)):
            self.dom.click(selectors.DELETE_CONTAINER_TOGGLE, "EMC 删除预置集装箱", timeout=3)
            self.dom.click(selectors.DELETE_CONTAINER_BUTTON, "EMC 确认删除预置集装箱", timeout=3)
            self._raise_for_alert("EMC 删除预置集装箱", timeout=2)

    def _fill_container(self, index: int, container: Any, submit_vgm: bool):
        if not isinstance(container, dict):
            raise BusinessError(f"EMC 第 {index} 个集装箱不是对象")
        self._reject_nonempty_unknowns(
            container,
            {
                "containerNo", "grossWeight", "grossWeightUnit", "volume", "volumeUnit", "packages",
                "packageUnit", "sealNo", "sealNo2", "sealNo3", "sealNo4", "sealNo5", "bookingNo",
                "method", "weight", "weightUnit", "shippingMethod", "shippingModality", "soc",
                "backfillContainerType",
            },
            f"containers[{index - 1}]",
        )
        self._input_and_verify(selectors.container_input(index, 1, 1), container.get("containerNo"), f"第 {index} 个集装箱箱号", required=True)
        self._input_and_verify(selectors.container_input(index, 2, 1), container.get("grossWeight"), f"第 {index} 个集装箱总毛重", required=True)
        self._select_and_verify(selectors.container_select(index, 2, 1), container.get("grossWeightUnit"), f"第 {index} 个集装箱总毛重单位", required=True)
        self._input_and_verify(selectors.container_input(index, 3, 1), container.get("volume"), f"第 {index} 个集装箱体积", required=True)
        self._select_and_verify(selectors.container_select(index, 3, 1), container.get("volumeUnit"), f"第 {index} 个集装箱体积单位", required=True)
        self._input_and_verify(selectors.container_input(index, 4, 1), container.get("packages"), f"第 {index} 个集装箱件数", required=True)
        self._select_and_verify(selectors.container_select(index, 4, 1), container.get("packageUnit"), f"第 {index} 个集装箱件数单位", required=True)
        for seal_index, field_name in enumerate(("sealNo", "sealNo2", "sealNo3", "sealNo4", "sealNo5"), start=1):
            self._fill_optional_text(selectors.container_seal(index, seal_index), field_name, f"第 {index} 个集装箱 {field_name}", source=container)

        if any(container.get(field) for field in ("shippingMethod", "shippingModality", "soc")):
            raise BusinessError(f"EMC 第 {index} 个集装箱含当前官网已停用字段 shippingMethod/shippingModality/soc")
        if container.get("backfillContainerType"):
            self.logger.info(f"EMC 忽略第 {index} 个集装箱回填箱型标记")

        if submit_vgm:
            self._fill_container_vgm(index, container)
        elif any(container.get(field) for field in ("bookingNo", "method", "weight", "weightUnit")):
            raise BusinessError(f"EMC 第 {index} 个集装箱含 VGM 字段但 submitWithVgm 为 false")

    def _fill_container_vgm(self, index: int, container: dict):
        booking_no = self._required("bookingNo", "订舱号")
        booking_selects = self.page.eles(selectors.VGM_BOOKING_SELECTS, timeout=3)
        if len(booking_selects) < index:
            raise ElementNotFoundError(f"EMC 第 {index} 个 VGM 订舱号选择框不存在")
        booking_selects[index - 1].select.by_text(booking_no, timeout=3)
        self._fill_optional_select(selectors.vgm_field(index, 1, "/select"), container, "bookingNo", f"第 {index} 个 VGM 订舱号")
        self._select_and_verify(selectors.vgm_field(index, 2, "/select"), container.get("method"), f"第 {index} 个 VGM 方法", required=True)
        self._input_and_verify(selectors.vgm_field(index, 3, "/input"), container.get("weight"), f"第 {index} 个 VGM 重量", required=True)
        self._select_and_verify(selectors.vgm_field(index, 5, "/select"), container.get("weightUnit"), f"第 {index} 个 VGM 重量单位", required=True)

    def _fill_hs_codes(self):
        codes = self.content.get("totalHsCode")
        if not isinstance(codes, list):
            raise BusinessError("EMC totalHsCode 必须是列表")
        nonempty_codes = [str(code).strip() for code in codes if str(code or "").strip()]
        if len(nonempty_codes) != len(set(nonempty_codes)):
            raise BusinessError("EMC 存在重复 HS Code")
        for code in nonempty_codes:
            if len(code) not in {4, 6, 8, 10} or not code.isdigit():
                raise BusinessError("EMC HS Code 只支持 4、6、8、10 位数字")
        if not nonempty_codes:
            self._done("totalHsCode")
            return
        self._input_and_verify(selectors.HS_CODE, nonempty_codes[0], "第一个 HS Code", required=True)
        if len(nonempty_codes) > 1:
            self.dom.click(selectors.MORE_HS_CODE_BUTTON, "EMC 更多 HS Code", timeout=3)
            for index, code in enumerate(nonempty_codes[1:]):
                self._input_and_verify(selectors.additional_hs_code(index), code, f"第 {index + 2} 个 HS Code", required=True)
            self.dom.click(selectors.MORE_HS_CODE_CONFIRM, "EMC 更多 HS Code 确认", timeout=3)
        self._done("totalHsCode")

    def _fill_filing_information(self):
        filing = self.content.get("filingInformation")
        if filing in (None, ""):
            if self.content.get("seqs"):
                raise BusinessError("EMC 下发 seqs 时 filingInformation 必须为 Filling by")
            declaration_bill = self.content.get("checkDeclarationBill")
            if declaration_bill not in (None, "", False, "false", "False"):
                raise BusinessError("EMC 下发 checkDeclarationBill 时 filingInformation 必须为 Filling by")
            self._done("filingInformation", "checkDeclarationBill", "seqs")
            return
        if filing == "Filling at":
            self.dom.click(selectors.FILING_AT, "EMC 自行申报", timeout=3)
            filing_mode = self.content.get("ensFF")
            if filing_mode == "Single":
                self.dom.click(selectors.FILING_SINGLE, "EMC 单票 ENS", timeout=3)
            elif filing_mode == "Multiple/House":
                self.dom.click(selectors.FILING_MULTIPLE, "EMC 多票 ENS", timeout=3)
            elif filing_mode:
                raise BusinessError(f"EMC 不支持 ensFF={filing_mode}")
            self._fill_optional_text(selectors.SUPPLEMENTARY_DECLARANT, "supplernentaryDeclarant", "补充申报人 EORI")
            self._fill_customs_codes()
            if self.content.get("seqs"):
                raise BusinessError("EMC Filling at 不支持下发 seqs")
            self._done("filingInformation", "ensFF", "checkDeclarationBill", "seqs")
            return
        if filing != "Filling by":
            raise BusinessError(f"EMC 不支持 filingInformation={filing}")
        self.dom.click(selectors.FILING_BY, "EMC 船司申报", timeout=3)
        declaration_bill = str(self.content.get("checkDeclarationBill") or "").lower() == "true"
        if declaration_bill:
            self.dom.click(selectors.FILING_HOUSE_BILL, "EMC 申报货代提单", timeout=3)
        self._fill_sequences(declaration_bill)
        self._done("filingInformation", "checkDeclarationBill", "seqs")

    def _fill_customs_codes(self):
        self._fill_optional_text(selectors.CUSTOMS_CODE, "cusCode1", "第一个海关编码")
        rest = [self.content.get(f"cusCode{index}") for index in range(2, 10)]
        if any(self._not_empty(value) for value in rest):
            self.dom.click(selectors.MORE_CUSTOMS_CODE, "EMC 更多海关编码", timeout=3)
            for index, value in enumerate(rest):
                self._input_and_verify(selectors.customs_code(index), value or "", f"第 {index + 2} 个海关编码")
            self.dom.click(selectors.MODAL_CONFIRM_BUTTON, "EMC 海关编码确认", timeout=3)
        self._done(*(f"cusCode{index}" for index in range(2, 10)))

    def _fill_sequences(self, declaration_bill: bool):
        sequences = self.content.get("seqs")
        if not isinstance(sequences, list) or not sequences:
            raise BusinessError("EMC Filling by 缺少 seqs")
        for index, sequence in enumerate(sequences, start=1):
            if not isinstance(sequence, dict):
                raise BusinessError(f"EMC 第 {index} 条 seqs 不是对象")
            self._reject_nonempty_unknowns(
                sequence,
                {
                    "sellerTypeOfPerson", "sellerEORI", "sellerCompanyName", "sellerCompanyAddress",
                    "sellerCountry", "sellerCity", "sellerState", "sellerZIP", "buyerTypeOfPerson",
                    "buyerEORI", "buyerCompanyName", "buyerCompanyAddress", "buyerCountry", "buyerCity",
                    "buyerState", "buyerZIP", "nvohblNo", "shipperTypeOfPerson", "shipperEORI",
                    "shipperCompanyName", "shipperCompanyAddress", "shipperCountry", "shipperCity",
                    "shipperState", "shipperZIP", "consigneeTypeOfPerson", "consigneeEORI",
                    "consigneeCompanyName", "consigneeCompanyAddress", "consigneeCountry", "consigneeCity",
                    "consigneeState", "consigneeZIP", "shipperPorCountry", "shipperPorLocation",
                    "consigneePodCountry", "consigneePodLocation", "commodities",
                },
                f"seqs[{index - 1}]",
            )
            if index > 1:
                self.dom.click(selectors.ADD_SEQUENCE, "EMC 新增 ENS 序列", timeout=3)
            self._fill_sequence_party(index, sequence, "seller", 2, 1, 0)
            self._fill_sequence_party(index, sequence, "buyer", 2, 2, 1)
            if declaration_bill:
                self._fill_sequence_house_bill(index, sequence)
            self._fill_sequence_commodities(index, sequence)

    def _fill_sequence_party(self, index: int, sequence: dict, prefix: str, row: int, column: int, data_index: int):
        self._fill_optional_select(selectors.sequence_select(index, row, column), sequence, f"{prefix}TypeOfPerson", f"第 {index} 条 {prefix} 证件类型")
        self._fill_optional_input(selectors.sequence_eori_input(index, row, column), sequence, f"{prefix}EORI", f"第 {index} 条 {prefix} EORI")
        self._fill_optional_input(selectors.by_id(f"seq{index}_companyName{data_index}"), sequence, f"{prefix}CompanyName", f"第 {index} 条 {prefix} 公司名称", required=True)
        self._fill_optional_input(selectors.by_id(f"seq{index}_companyAddr{data_index}"), sequence, f"{prefix}CompanyAddress", f"第 {index} 条 {prefix} 公司地址", required=True)
        self._fill_optional_select(selectors.by_id(f"seq{index}_seqCtry{data_index}"), sequence, f"{prefix}Country", f"第 {index} 条 {prefix} 国家", required=True)
        self._fill_optional_input(selectors.by_id(f"seq{index}_seqCity{data_index}"), sequence, f"{prefix}City", f"第 {index} 条 {prefix} 城市", required=True)
        self._fill_optional_input(selectors.sequence_row_input(index, row, column), sequence, f"{prefix}State", f"第 {index} 条 {prefix} 州")
        self._fill_optional_input(selectors.by_id(f"seq{index}_seqZip{data_index}"), sequence, f"{prefix}ZIP", f"第 {index} 条 {prefix} 邮编")

    def _fill_sequence_house_bill(self, index: int, sequence: dict):
        self._fill_optional_input(selectors.by_id(f"seq{index}_blnoHouse"), sequence, "nvohblNo", f"第 {index} 条 House Bill 号")
        self._fill_sequence_party(index, sequence, "shipper", 5, 1, 2)
        self._fill_sequence_party(index, sequence, "consignee", 5, 2, 3)
        self._fill_optional_select(selectors.by_id(f"seq{index}_rcthouseCtry"), sequence, "shipperPorCountry", f"第 {index} 条 House Bill 收货地国家")
        self._fill_optional_input(selectors.by_id(f"seq{index}_rctHouseName"), sequence, "shipperPorLocation", f"第 {index} 条 House Bill 收货地")
        self._fill_optional_select(selectors.by_id(f"seq{index}_dlyhouseCtry"), sequence, "consigneePodCountry", f"第 {index} 条 House Bill 交货地国家")
        self._fill_optional_input(selectors.by_id(f"seq{index}_dlyHouseName"), sequence, "consigneePodLocation", f"第 {index} 条 House Bill 交货地")

    def _fill_sequence_commodities(self, index: int, sequence: dict):
        commodities = sequence.get("commodities")
        if not isinstance(commodities, list) or not commodities:
            raise BusinessError(f"EMC 第 {index} 条 seqs 缺少 commodities")
        for commodity_index, commodity in enumerate(commodities, start=1):
            if not isinstance(commodity, dict):
                raise BusinessError(f"EMC 第 {index} 条第 {commodity_index} 个品名不是对象")
            self._reject_nonempty_unknowns(
                commodity,
                {"containers", "htCode", "cusCode", "shippingMarks", "goodsDescription"},
                f"seqs[{index - 1}].commodities[{commodity_index - 1}]",
            )
            containers = commodity.get("containers")
            if not isinstance(containers, list) or not containers:
                raise BusinessError(f"EMC 第 {index} 条第 {commodity_index} 个品名缺少 containers")
            if not containers[0].get("containerNo"):
                continue
            for container_index, container in enumerate(containers, start=1):
                if not isinstance(container, dict):
                    raise BusinessError(
                        f"EMC 第 {index} 条第 {commodity_index} 个品名第 {container_index} 个箱货不是对象"
                    )
                self._reject_nonempty_unknowns(
                    container,
                    {"containerNo", "package", "unit", "grossWeight"},
                    f"seqs[{index - 1}].commodities[{commodity_index - 1}].containers[{container_index - 1}]",
                )
            if commodity_index > 1:
                self.dom.click(f"x://*[@id='seq{index}']/tbody/tr[10]//input", "EMC 新增 ENS 品名", timeout=3)
            self.dom.click(selectors.sequence_commodity_toggle(index, commodity_index), "EMC 选择 ENS 品名集装箱", timeout=5)
            self._select_commodity_containers(index, commodity_index, containers)
            rows = self.page.eles(selectors.sequence_commodity_rows(index, commodity_index), timeout=20)
            if len(rows) != len(containers):
                raise BusinessError(f"EMC 第 {index} 条第 {commodity_index} 个品名箱号添加失败")
            details = {str(item.get("containerNo")): item for item in containers}
            for row_index, row in enumerate(rows, start=1):
                container_no = (row.ele("xpath:./td[2]", timeout=2).text or "").strip()
                detail = details.get(container_no)
                if detail is None:
                    raise BusinessError(f"EMC ENS 品名箱号未匹配：{container_no}")
                prefix = selectors.sequence_commodity_rows(index, commodity_index) + f"[{row_index}]"
                self._input_and_verify(prefix + "/td[7]/input", detail.get("package"), f"ENS 品名箱号 {container_no} 件数", required=True)
                self._select_and_verify(prefix + "/td[8]/select", detail.get("unit"), f"ENS 品名箱号 {container_no} 单位", required=True)
                self._input_and_verify(
                    prefix + "/td[9]/input",
                    detail.get("grossWeight"),
                    f"ENS 品名箱号 {container_no} 毛重",
                    required=True,
                    numeric=True,
                )
            self._fill_commodity_text(index, commodity_index, commodity)

    def _select_commodity_containers(self, index: int, commodity_index: int, containers: list[dict]):
        expected = {str(item.get("containerNo") or "") for item in containers}
        rows = self.page.eles(selectors.MORE_CONTAINER_ROWS, timeout=20)
        for row in rows:
            container_no = (row.ele("xpath:./td[2]", timeout=1).text or "").strip()
            if container_no in expected:
                row.ele("xpath:./td[1]/input", timeout=1).click()
        self.dom.click(selectors.MORE_CONTAINER_CONFIRM, "EMC ENS 品名箱号确认", timeout=5)

    def _fill_commodity_text(self, index: int, commodity_index: int, commodity: dict):
        for suffix, field_name, name in (
            ("htCode", "htCode", "HS Code"),
            ("seq_cusCode", "cusCode", "海关编码"),
            ("marks", "shippingMarks", "唛头"),
            ("goodsDesp", "goodsDescription", "货物描述"),
        ):
            locator = selectors.by_id(f"seq{index}_{suffix}{commodity_index}")
            self._input_and_verify(locator, commodity.get(field_name), f"第 {index} 条第 {commodity_index} 个品名{name}", required=field_name != "cusCode")

    def _fill_basic_document_data(self):
        self._select_and_verify(selectors.BL_NATURE, "Intelligent B/L", "EMC 提单类型重置", required=True)
        self._select_and_verify(selectors.BL_NATURE, self.content.get("releaseMode"), "EMC 提单类型", required=True)
        self._select_and_verify(selectors.RECEIPT_SHIPMENT, self.content.get("releaseModeCode"), "EMC 提单装船条款", required=True)
        self._done("releaseMode", "releaseModeCode")
        if self.content.get("ter"):
            self.dom.click(selectors.EMAIL_RELEASE, "EMC 电放选项", timeout=3)
        self._done("ter")
        self._fill_location_pair(selectors.ISSUE_PLACE_BUTTON, "issueLocationCountry", "issueLocationCity", "提单签发地")
        self._fill_location_pair(selectors.PAYABLE_PLACE_BUTTON, "paymentCountry", "paymentCity", "运费付款地")
        if self.content.get("blankBill"):
            self._fill_location_pair(selectors.BOOKING_PLACE_BUTTON, "bookingLocationCountry", "bookingLocationCity", "订舱地")
            self._select_and_verify(selectors.TRANSPORT_MODE, self.content.get("transportMode"), "EMC 空白提单运输方式", required=True)
            self._select_and_verify(selectors.TRANSPORT_TERM, self.content.get("transportTerm"), "EMC 空白提单运输形态", required=True)
        self._done("bookingLocationCountry", "bookingLocationCity", "transportMode", "transportTerm")
        self._fill_optional_text(selectors.NUMBER_OF_ORIGINAL, "numberOfOriginal", "正本提单份数")
        self._fill_optional_text(selectors.NUMBER_OF_COPY, "numberOfCopy", "副本提单份数")
        self._fill_optional_text(selectors.NUMBER_OF_ORIGINAL_WITH_FREIGHT, "numberOfOriginalWithFreight", "含运费正本份数")
        self._fill_optional_text(selectors.NUMBER_OF_COPY_WITH_FREIGHT, "numberOfCopyWithFreight", "含运费副本份数")

    def _fill_location_pair(self, button, country_field: str, city_field: str, name: str):
        country = self.content.get(country_field)
        city = self.content.get(city_field)
        if self._not_empty(country) != self._not_empty(city):
            raise BusinessError(f"EMC {name}国家和城市必须同时下发")
        if country:
            self.dom.click(button, f"EMC {name}选择按钮", timeout=3)
            self.dom.click(selectors.LOCATION_WORDING_TAB, f"EMC {name}文字选择", timeout=3)
            self._select_and_verify(selectors.LOCATION_COUNTRY, country, f"EMC {name}国家", required=True)
            self._select_and_verify(selectors.LOCATION_CITY, city, f"EMC {name}城市", required=True)
            self.dom.click(selectors.LOCATION_SUBMIT, f"EMC {name}确认", timeout=3)
        self._done(country_field, city_field)

    def _fill_contact_data(self):
        for locator, field_name, name, required in (
            (selectors.CONTACT_PERSON, "customerContact", "文件联系人", True),
            (selectors.PHONE_COUNTRY_CODE, "customerCountryCode", "联系电话国家码", False),
            (selectors.PHONE_AREA_CODE, "customerAreaCode", "联系电话地区码", False),
            (selectors.PHONE_NUMBER, "customerLinePhone", "联系电话", False),
            (selectors.PHONE_EXTENSION, "customerExtension", "联系电话分机", False),
            (selectors.NOTIFY_EMAIL, "customerEmail", "通知邮箱", True),
        ):
            self._input_and_verify(locator, self.content.get(field_name), name, required=required)
            self._done(field_name)
        if self.content.get("customerEmail2") or self.content.get("customerEmail3"):
            self.dom.click_if_clickable(selectors.MORE_EMAIL_TOGGLE, "EMC 更多通知邮箱", timeout=2)
        self._fill_optional_text(selectors.SECOND_EMAIL, "customerEmail2", "第二通知邮箱")
        self._fill_optional_text(selectors.THIRD_EMAIL, "customerEmail3", "第三通知邮箱")

    def _fill_remarks(self):
        self._input_and_verify(selectors.REMARKS, self.content.get("remark") or self.content.get("remarks"), "备注")
        self._done("remark", "remarks")
        self.dom.click(selectors.NOTIFY_EMAIL_BUTTON, "EMC 触发字段校验", timeout=2)
        self._raise_for_alert("EMC 字段校验", timeout=1)

    def _finish_metadata_fields(self):
        payment_type = self.content.get("paymentType")
        if payment_type and payment_type not in {"Prepaid", "Collect"}:
            raise BusinessError(f"EMC 不支持 paymentType={payment_type}")
        official_mode = self.content.get("paymentTypeOfficialMode")
        if official_mode and official_mode != "比对":
            raise BusinessError(f"EMC 不支持 paymentTypeOfficialMode={official_mode}")
        if payment_type:
            self.logger.info(
                f"EMC 保留官网默认运费付款方式，消息值={payment_type} officialMode={official_mode or '空'}"
            )
        self._done("paymentType")
        self._done("paymentTypeOfficialMode")
        self._done("carrier", "isUserSave", "blNo", "jobNo", "needBackfill")
        for field_name in self.legacy_metadata_fields:
            self._done(field_name)

    def _save_or_submit(self):
        operation = str(self.context.task.get("rpaOperate") or "").upper()
        should_submit = operation == "SUBMIT_DIRECT" if operation else self.customer_role in self.submit_roles
        if should_submit:
            self.dom.click(selectors.SUBMIT_BUTTON, "EMC 提交按钮", timeout=5)
            expected = "提交成功"
        else:
            self.dom.click(selectors.SAVE_DRAFT_BUTTON, "EMC 保存草稿按钮", timeout=5)
            expected = "保存成功"
        alert_text = self.dom.handle_alert(timeout=20)
        if expected not in alert_text:
            alert_text = self.dom.handle_alert(timeout=20)
        if expected not in alert_text:
            raise BusinessError(f"EMC 页面未返回{expected}提示：{alert_text or '空'}")
        # 旧队列先按客户角色决定回传 saveType，再决定是否因 rpaOperate 保存草稿。
        self.result_save_type = 1 if (
            self.customer_role in self.submit_roles or self.customer_role in self.save_type_one_roles
        ) else 0

    def _validate_known_top_level_fields(self):
        supported = {
            "bookingNo", "blankBill", "splitBill", "consolidatedBill", "bookingNos", "shipper", "consignee",
            "notify", "secondNotify", "receiptPlace", "pol", "pod", "deliveryPlace", "podTemplate",
            "shipperEoriNo", "consigneeEoriNo", "notifyEoriNo", "secondNotifyEoriNo", "shipperAceAci",
            "consigneeAceAci", "notifyAceAci", "secondNotifyAceAci", "nvoScac", "moreNotifyAceAci",
            "aciNvocc", "transshipmentRequirements", "submitWithVgm", "responsibleParty", "authorizedPerson",
            "containers", "totalMarks", "totalGoodsDesc", "totalHsCode", "filingInformation", "ensFF",
            "supplernentaryDeclarant", "cusCode1", "cusCode2", "cusCode3", "cusCode4", "cusCode5",
            "cusCode6", "cusCode7", "cusCode8", "cusCode9", "checkDeclarationBill", "seqs", "releaseMode",
            "releaseModeCode", "ter", "issueLocationCountry", "issueLocationCity", "paymentCountry", "paymentCity",
            "bookingLocationCountry", "bookingLocationCity", "transportMode", "transportTerm", "numberOfOriginal",
            "numberOfCopy", "numberOfOriginalWithFreight", "numberOfCopyWithFreight", "customerContact",
            "customerCountryCode", "customerAreaCode", "customerLinePhone", "customerExtension", "customerEmail",
            "customerEmail2", "customerEmail3", "remark", "remarks", "paymentType", "paymentTypeOfficialMode",
            "rpaMode", "carrier", "isUserSave", "blNo", "jobNo", "needBackfill", *self.legacy_metadata_fields,
        }
        self._reject_nonempty_unknowns(self.content, supported, "content")

    def _reject_nonempty_unknowns(self, data: dict, supported: set[str], source: str):
        unknown = [key for key, value in data.items() if key not in supported and self._not_empty(value)]
        if unknown:
            raise BusinessError(f"EMC 不支持字段：{source}." + ", ".join(sorted(unknown)))

    def _fill_optional_text(self, locator, field_name, name, *, source=None):
        source = self.content if source is None else source
        self._input_and_verify(locator, source.get(field_name), name)
        if source is self.content:
            self._done(field_name)

    def _fill_optional_input(self, locator, source, field_name, name, *, required=False):
        self._input_and_verify(locator, source.get(field_name), name, required=required)

    def _fill_optional_select(self, locator, source, field_name, name, *, required=False):
        self._select_and_verify(locator, source.get(field_name), name, required=required)

    def _input_and_verify(self, locator, value, name, *, required=False, numeric=False):
        if not self._not_empty(value):
            if required:
                raise BusinessError(f"EMC 缺少必填字段：{name}")
            return
        expected = self._normalize_text(value)
        self.dom.input_text(locator, expected, name, timeout=5)
        actual = self._normalize_text(self.dom.get_value(locator, name, timeout=3))
        matches = self._numeric_text_equal(actual, expected) if numeric else actual == expected
        if not matches:
            raise FormValidationError(f"EMC {name}填写不一致：{actual} != {expected}")

    def _select_and_verify(self, locator, value, name, *, required=False):
        if not self._not_empty(value):
            if required:
                raise BusinessError(f"EMC 缺少必填字段：{name}")
            return
        expected = str(value).strip()
        self.dom.select(locator, expected, name, timeout=5)
        actual = str(self.dom.get_select_text(locator, name, timeout=3) or "").strip()
        if actual != expected:
            raise FormValidationError(f"EMC {name}填写不一致：{actual} != {expected}")

    def _raise_for_alert(self, action: str, *, timeout=2):
        alert_text = self.dom.handle_alert(timeout=timeout)
        if alert_text:
            raise BusinessError(f"{action}提示：{alert_text}")

    def _required(self, field_name, name):
        value = self.content.get(field_name)
        if not self._not_empty(value):
            raise BusinessError(f"EMC 缺少必填字段：{name}")
        return str(value)

    def _done(self, *field_names):
        for field_name in field_names:
            self.mark_field_done(field_name)

    @staticmethod
    def _not_empty(value):
        return value is not None and (not isinstance(value, str) or bool(value.strip()))

    @staticmethod
    def _normalize_text(value):
        return str(value or "").replace("\t", " ").replace("\xa0", " ").replace("\r\n", "\n").strip()

    @staticmethod
    def _numeric_text_equal(actual: str, expected: str) -> bool:
        try:
            return Decimal(actual) == Decimal(expected)
        except InvalidOperation:
            return False
