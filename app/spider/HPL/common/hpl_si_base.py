"""HPL Shipping Instruction 任务的客户无关公共流程。"""

import time

from app.core.task.context import TaskContext
from app.core.task.errors import BusinessError, ElementNotFoundError, FormValidationError
from app.spider.HPL import selectors
from app.spider.HPL.base import HplBase


class HplSiBaseTask(HplBase):
    """提供 HPL SI 共用填单流程，并为客户模板保留扩展钩子。"""

    enable_record = True
    job_type = "SI"
    submit_roles = frozenset({"JINHONG", "PENGXIN", "WEIPAI", "ANXINHANG"})
    save_type_one_draft_roles = frozenset({"ZEHUI"})
    supported_templates = frozenset({"COMMON"})
    confirm_submission = False

    def __init__(self, context: TaskContext, **kwargs):
        """初始化消息内容和客户角色，供后续保存策略使用。"""
        super().__init__(context, **kwargs)
        self.content = context.content or {}
        self.customer_role = str(context.task.get("customerRole") or "").upper()

    def execute_business(self):
        """按 HPL 页面区段依次完成查询、填单、校验和确认。"""
        self._open_shipping_instruction()
        self._select_associated_bill()
        self._fill_addresses_and_references()
        self._validate_template_scope()
        self._fill_containers_and_cargo()
        self._fill_template_specific_fields()
        self._fill_freight()
        self._fill_document_issuance()
        self._fill_comments()
        self._finish_metadata_fields()
        self.raise_if_unfilled_fields(stage="HPL SI 填单流程")

        if self.confirm_submission:
            self.page.run_js("window.scrollTo(0, 0);")
            self.capture_business_screenshot("BEFORE_SUBMIT_IMG", "before")
            self._confirm_shipping_instruction()
            self.capture_business_screenshot("AFTER_SUBMIT_IMG", "after")

    def get_result_attachments(self, execute_record_files):
        """将提交前截图复用为与旧流程兼容的草稿件附件。"""
        attachments = super().get_result_attachments(execute_record_files)
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

    def _open_shipping_instruction(self):
        """按 bookingNo 查询 HPL SI，并进入新版截单页面。"""
        booking_no = self._required_value("bookingNo", "订舱号")
        found_booking_no = ""
        for _ in range(10):
            self._fill_and_verify(selectors.BOOKING_SEARCH_INPUT, booking_no, "订舱号搜索框", required=True)
            self.dom.click(selectors.BOOKING_SEARCH_BUTTON, "订舱号查询按钮", timeout=5)
            time.sleep(1)
            found_booking_no = self.dom.get_text(
                selectors.BOOKING_SEARCH_RESULT,
                "订舱号查询结果",
                required=False,
                timeout=2,
            )
            if found_booking_no == booking_no:
                break
        else:
            raise BusinessError(
                f"HPL 查询订舱号失败：官网返回 {found_booking_no or '空'}，期望 {booking_no}"
            )

        error_message = self.dom.get_text(
            selectors.BOOKING_ERROR,
            "订舱号查询错误提示",
            required=False,
            timeout=1,
        )
        if error_message:
            raise BusinessError(f"HPL 查询订舱号失败：{error_message}")

        self.mark_field_done("bookingNo")
        self.page.get(f"{selectors.SI_APPLICATION_URL}{found_booking_no}", show_errmsg=True)
        self.page.wait.doc_loaded()
        if not self.page.eles(selectors.SI_PAGE_MARKER, timeout=10):
            raise BusinessError("HPL SI 页面跳转失败")

        if self.page.eles("x://*[@class='text-body-s h-ma-none']", timeout=1):
            self.dom.click(selectors.CONTINUE_BUTTON, "继续编辑 SI 按钮", required=False, timeout=2)

    def _select_associated_bill(self):
        """选择指定提单，并拦截官网已收到 SI 的重复提交提示。"""
        bl_no = self._required_value("blNo", "提单号")
        self.dom.click(selectors.ASSOCIATED_BL_SELECT, "关联提单下拉框", timeout=5)
        time.sleep(1)
        for option in self.page.eles(selectors.DROPDOWN_OPTIONS, timeout=5):
            option_text = (option.text or "").strip()
            if bl_no not in option_text:
                continue
            if "SI already received" in option_text:
                raise BusinessError(f"HPL 提单 {bl_no} 已经截过单")
            option.click()
            self.mark_field_done("blNo")
            return
        raise BusinessError(f"HPL 未找到可截单的提单：{bl_no}")

    def _fill_addresses_and_references(self):
        """填写发货人、收货人、通知人及港口资料。"""
        self._fill_and_verify(selectors.SHIPPER_INPUT, self.content.get("shipper"), "发货人", required=True)
        self._mark_done("shipper")
        self._fill_optional_and_verify(selectors.SHIPPER_EMAIL_INPUT, "shipperEmail", "发货人邮箱")
        self._fill_phone(
            "shipperCountryCode",
            "shipperPhoneNo",
            selectors.SHIPPER_COUNTRY_INPUT,
            selectors.SHIPPER_PHONE_INPUT,
            "发货人",
        )
        self._fill_shipper_references()
        self._fill_to_order()

        self._fill_and_verify(selectors.CONSIGNEE_INPUT, self.content.get("consignee"), "收货人", required=True)
        self._mark_done("consignee")
        self._fill_optional_and_verify(selectors.CONSIGNEE_EMAIL_INPUT, "consigneeEmail", "收货人邮箱")
        self._fill_optional_and_verify(selectors.CONSIGNEE_REFERENCE_INPUT, "consigneeReference", "收货人参考号")
        self._fill_phone(
            "consigneeCountryCode",
            "consigneePhoneNo",
            selectors.CONSIGNEE_COUNTRY_INPUT,
            selectors.CONSIGNEE_PHONE_INPUT,
            "收货人",
        )

        self._fill_and_verify(selectors.NOTIFY_INPUT, self.content.get("notify"), "通知人", required=True)
        self._mark_done("notify")
        self._fill_optional_and_verify(selectors.NOTIFY_EMAIL_INPUT, "notifyEmail", "通知人邮箱")
        self._fill_phone(
            "notifyCountryCode",
            "notifyPhoneNo",
            selectors.NOTIFY_COUNTRY_INPUT,
            selectors.NOTIFY_PHONE_INPUT,
            "通知人",
        )
        self._fill_additional_notify(2)
        self._fill_additional_notify(3)

        self._fill_and_verify(selectors.POL_INPUT, self.content.get("pol"), "装货港", required=True)
        self._fill_and_verify(selectors.POD_INPUT, self.content.get("pod"), "卸货港", required=True)
        self._mark_done("pol", "pod")

    def _fill_shipper_references(self):
        """填写发货人参考号和海外代理，保证两个关联字段同时处理。"""
        reference = self.content.get("shipperExportReference")
        overseas_agent = self.content.get("overseasAgent")
        if overseas_agent and not reference:
            raise BusinessError("HPL 海外代理有值时必须同时提供发货人参考号")
        if reference:
            self._fill_and_verify(selectors.SHIPPER_REFERENCE_INPUT, reference, "发货人参考号")
            self._fill_and_verify(selectors.FORWARDER_REFERENCE_INPUT, overseas_agent, "海外代理")
        self._mark_done("shipperExportReference", "overseasAgent")

    def _fill_to_order(self):
        """根据 toOrder 字段决定是否勾选 To Order。"""
        if self.content.get("toOrder"):
            self.dom.click(selectors.TO_ORDER_BUTTON, "To Order 选项", timeout=3)
        self._mark_done("toOrder")

    def _fill_phone(self, country_field, phone_field, country_locator, phone_locator, party_name):
        """填写联系人国家区号和电话，并校验两项输入的依赖关系。"""
        country_code = self.content.get(country_field)
        phone_number = self.content.get(phone_field)
        if phone_number and not country_code:
            raise BusinessError(f"HPL {party_name}电话有值时必须同时提供国家区号")
        if country_code:
            self.dom.input_text(country_locator, str(country_code), f"{party_name}国家区号", timeout=3)
            self._choose_dropdown_option(str(country_code), f"{party_name}国家区号", contains=True)
            self._fill_and_verify(phone_locator, phone_number, f"{party_name}电话", required=bool(phone_number))
        self._mark_done(country_field, phone_field)

    def _fill_additional_notify(self, index):
        """填写第二或第三通知人及其邮箱、电话信息。"""
        notify_field = "secondNotify" if index == 2 else "thirdNotify"
        email_field = f"{notify_field}Email"
        country_field = f"{notify_field}CountryCode"
        phone_field = f"{notify_field}PhoneNo"
        notify_value = self.content.get(notify_field)
        if notify_value:
            self.dom.click(selectors.NOTIFY_ADD_BUTTON, f"新增第 {index} 通知人按钮", timeout=3)
            self._fill_and_verify(
                selectors.additional_notify_input_locator(index),
                notify_value,
                f"第 {index} 通知人",
                required=True,
            )
        self._mark_done(notify_field)
        self._fill_optional_and_verify(
            selectors.additional_notify_email_locator(index),
            email_field,
            f"第 {index} 通知人邮箱",
        )
        self._fill_phone(
            country_field,
            phone_field,
            selectors.additional_notify_country_locator(index),
            selectors.additional_notify_phone_locator(index),
            f"第 {index} 通知人",
        )

    def _fill_containers_and_cargo(self):
        """按消息箱货层级重建 HPL 页面箱货，并填写全部基础货物资料。"""
        containers = self.content.get("containers")
        if not isinstance(containers, list) or not containers:
            raise BusinessError("HPL SI 缺少 containers 箱货信息")
        self._prepare_container_rows(containers)

        same_description = str(self.content.get("sameDescriptionForSi") or "NO").upper()
        if same_description not in {"YES", "NO"}:
            raise BusinessError(f"HPL 不支持的 sameDescriptionForSi 值：{same_description}")
        if same_description == "YES":
            self._fill_shared_cargo_description(containers)
        else:
            for container_index, container in enumerate(containers, start=1):
                self._fill_container(container_index, container, include_goods_description=True)
        self._mark_done("sameDescriptionForSi", "containers")

    def _prepare_container_rows(self, containers):
        """清理官网预置的多余箱货并增补到消息指定数量。"""
        containers_section = self.dom._find(selectors.CONTAINERS_SECTION, "箱货区", timeout=5)
        containers_section.scroll.to_center()
        container_count = self.dom.count_clickable(selectors.DELETE_CONTAINER_BUTTON, timeout=2)
        for _ in range(max(container_count - 1, 0)):
            self.dom.click_first_clickable(selectors.DELETE_CONTAINER_BUTTON, "删除预置集装箱", timeout=2)
            time.sleep(0.5)
            self.dom.click_first_clickable(selectors.CONFIRM_BUTTON, "确认删除集装箱", timeout=2)
            time.sleep(0.5)

        cargo_count = self.dom.count_clickable(selectors.DELETE_CARGO_BUTTON, timeout=2)
        for _ in range(max(cargo_count - 1, 0)):
            self.dom.click_first_clickable(selectors.DELETE_CARGO_BUTTON, "删除预置货物", timeout=2)
            time.sleep(0.5)
            self.dom.click_first_clickable(selectors.CONFIRM_BUTTON, "确认删除货物", timeout=2)
            time.sleep(0.5)

        for _ in range(len(containers) - 1):
            self.dom.click(selectors.ADD_CONTAINER_BUTTON, "新增集装箱", timeout=3)
        for container_index, container in enumerate(containers, start=1):
            goods = container.get("goods") if isinstance(container, dict) else None
            if not isinstance(goods, list) or not goods:
                raise BusinessError(f"HPL 第 {container_index} 个集装箱缺少货物信息")
            add_cargo_locator = selectors.container_elements_locator(
                container_index,
                "//*[@data-cy='addCargoButton']",
            )
            for _ in range(len(goods) - 1):
                self.dom.click(add_cargo_locator, f"第 {container_index} 个集装箱新增货物", timeout=3)

    def _fill_shared_cargo_description(self, containers):
        """填写整票统一的唛头、货描和 HS Code，再补充箱号与货物数量。"""
        self.dom.click(selectors.SAME_DESCRIPTION_BUTTON, "整票统一品名唛头选项", timeout=3)
        self._fill_and_verify(selectors.TOTAL_MARKS_INPUT, self.content.get("totalMarks"), "整票唛头", required=True)
        self._fill_and_verify(
            selectors.TOTAL_GOODS_DESC_INPUT,
            self.content.get("totalGoodsDesc"),
            "整票货物描述",
            required=True,
        )
        self._fill_and_verify(selectors.TOTAL_HS_CODE_INPUT, self.content.get("totalHsCode"), "整票 HS Code", required=True)
        self._choose_hs_code(str(self.content["totalHsCode"]), "整票 HS Code")
        self._fill_optional_and_verify(selectors.TOTAL_NCM_CODE_INPUT, "totalNcmCode", "整票 NCM Code")
        self._fill_optional_and_verify(selectors.TOTAL_CHEMICAL_CODE_INPUT, "totalChemicalCode", "整票 Chemical Code")
        self._mark_done("totalMarks", "totalGoodsDesc", "totalHsCode", "totalNcmCode", "totalChemicalCode")
        for container_index, container in enumerate(containers, start=1):
            self._fill_container(container_index, container, include_goods_description=False)

    def _fill_container(self, container_index, container, *, include_goods_description):
        """填写一个集装箱的箱号、封号及其全部货物行。"""
        if not isinstance(container, dict):
            raise BusinessError(f"HPL 第 {container_index} 个集装箱格式错误")
        self._fill_and_verify(
            selectors.container_field_locator(container_index, "Container No."),
            container.get("containerNo"),
            f"第 {container_index} 个集装箱箱号",
            required=True,
            normalizer=self._normalize_container_no,
        )
        seal_elements = self.page.eles(
            selectors.container_field_locator(container_index, "Seal No. (Optional)"),
            timeout=3,
        )
        for seal_index, field_name in enumerate(("sealNo", "sealNo2", "sealNo3")):
            value = container.get(field_name)
            if value and len(seal_elements) <= seal_index:
                raise ElementNotFoundError(f"第 {container_index} 个集装箱{field_name}元素不存在")
            if len(seal_elements) > seal_index:
                self._fill_element_and_verify(
                    seal_elements[seal_index],
                    value,
                    f"第 {container_index} 个集装箱{field_name}",
                    required=False,
                )

        self._fill_container_template_fields(container_index, container)

        for goods_index, goods in enumerate(container.get("goods") or [], start=1):
            self._fill_goods(container_index, goods_index, goods, include_goods_description)

    def _fill_goods(self, container_index, goods_index, goods, include_goods_description):
        """填写一条货物的包装、重量、体积及非统一模式下的货描资料。"""
        if not isinstance(goods, dict):
            raise BusinessError(f"HPL 第 {container_index} 个集装箱第 {goods_index} 条货物格式错误")
        item_index = goods_index - 1
        self._fill_indexed_and_verify(
            selectors.container_elements_locator(container_index, "//*[@data-cy='numberOfPackagesInput']"),
            item_index,
            goods.get("packages"),
            f"第 {container_index} 箱第 {goods_index} 条货物件数",
            required=True,
        )
        package_unit = self._required_goods_value(goods, "packageUnit", container_index, goods_index)
        package_unit_element = self._element_at(
            selectors.container_elements_locator(
                container_index,
                "//*[text()='Kind of Packages / UN Packing Code']/../div[1]",
            ),
            item_index,
            f"第 {container_index} 箱第 {goods_index} 条货物包装单位",
        )
        self.dom.search_select_element(
            package_unit_element,
            package_unit.split("|")[0].strip(),
            selectors.DROPDOWN_OPTIONS,
            package_unit,
            f"第 {container_index} 箱第 {goods_index} 条货物包装单位",
            timeout=5,
        )
        self._fill_indexed_and_verify(
            selectors.container_elements_locator(container_index, "//*[@data-cy='packagingInput']"),
            item_index,
            goods.get("printPackageUnit"),
            f"第 {container_index} 箱第 {goods_index} 条货物提单包装名称",
            required=True,
        )
        self._fill_measurement(container_index, goods_index, goods, "Gross Weight", "grossWeight", "grossWeightUnit")
        self._fill_measurement(
            container_index,
            goods_index,
            goods,
            "Gross Volume (Optional)",
            "volume",
            "volumeUnit",
        )

        if not include_goods_description:
            return
        hs_code = self._required_goods_value(goods, "hsCode", container_index, goods_index)
        self._fill_indexed_and_verify(
            selectors.container_field_locator(container_index, "HS Code"),
            item_index,
            hs_code,
            f"第 {container_index} 箱第 {goods_index} 条货物 HS Code",
            required=True,
        )
        self._choose_hs_code(hs_code, f"第 {container_index} 箱第 {goods_index} 条货物 HS Code")
        if goods.get("ncmCode"):
            self._fill_indexed_and_verify(
                selectors.container_elements_locator(container_index, "//*[@data-testid='ncmCodeInput']"),
                item_index,
                goods["ncmCode"],
                f"第 {container_index} 箱第 {goods_index} 条货物 NCM Code",
                required=False,
            )
        if goods.get("chemicalCode"):
            self._fill_indexed_and_verify(
                selectors.container_elements_locator(container_index, "//*[@data-cy='ecicsValueInput']"),
                item_index,
                goods["chemicalCode"],
                f"第 {container_index} 箱第 {goods_index} 条货物 Chemical Code",
                required=False,
            )
        self._fill_indexed_and_verify(
            selectors.container_elements_locator(container_index, "//*[@data-cy='shippingMarksInput']"),
            item_index,
            goods.get("marks"),
            f"第 {container_index} 箱第 {goods_index} 条货物唛头",
            required=True,
        )
        self._fill_indexed_and_verify(
            selectors.container_elements_locator(container_index, "//*[@data-cy='descriptionOfGoodsInput']"),
            item_index,
            goods.get("goodsDesc"),
            f"第 {container_index} 箱第 {goods_index} 条货物描述",
            required=True,
        )

    def _fill_measurement(self, container_index, goods_index, goods, label, value_field, unit_field):
        """填写货物重量或体积，并根据单位选择 HPL 的替代单位。"""
        item_index = goods_index - 1
        value = self._required_goods_value(goods, value_field, container_index, goods_index)
        unit = self._required_goods_value(goods, unit_field, container_index, goods_index).upper()
        allowed_units = {"KG", "KGS", "LB"} if value_field == "grossWeight" else {"CBM", "FTQ"}
        if unit not in allowed_units:
            raise BusinessError(f"HPL 不支持的 {unit_field}：{unit}")
        self._fill_indexed_and_verify(
            selectors.container_field_locator(container_index, label),
            item_index,
            value,
            f"第 {container_index} 箱第 {goods_index} 条货物{label}",
            required=True,
        )
        alternative_unit = "lb" if unit == "LB" else "ftq" if unit == "FTQ" else None
        if alternative_unit:
            trigger = selectors.container_elements_locator(
                container_index,
                f"//*[@aria-label='{label}']/../../../../../label[2]/div/div[1]",
            )
            self._element_at(trigger, item_index, f"第 {container_index} 箱第 {goods_index} 条货物{label}单位").click()
            self._choose_dropdown_option(alternative_unit, f"第 {container_index} 箱第 {goods_index} 条货物{label}单位")

    def _validate_template_scope(self):
        """校验当前客户任务支持的 HPL 目的港模板。"""
        pod_template = str(self.content.get("podTemplate") or "COMMON").upper()
        if pod_template not in self.supported_templates:
            supported = ", ".join(sorted(self.supported_templates))
            raise BusinessError(f"HPL 不支持 podTemplate={pod_template}，支持：{supported}")
        self._mark_done("podTemplate")

    def _fill_template_specific_fields(self):
        """填写国家和客户模板特有字段；COMMON 模板默认无需处理。"""

    def _fill_container_template_fields(self, container_index, container):
        """填写箱级模板特有字段；默认无额外字段。"""

    def _fill_freight(self):
        """填写三类港口和海运费用的付款方式及付款人。"""
        self._set_charge("originPortCharge", "Origin Port Charge")
        self._set_charge("seaFreightAdditionals", "Sea Freight")
        self._set_charge("destinationPortCharge", "Destination Port Charge")
        self._set_destination_haulage_charge()
        self._fill_payer(
            "prepaidPayer",
            "prepaidPayerNameAndAddress",
            selectors.PREPAID_PAYER_SELECT,
            selectors.PREPAID_PAYER_OTHER_INPUT,
            "预付付款人",
        )
        self._fill_payer(
            "collectPayer",
            "collectPayerNameAndAddress",
            selectors.COLLECT_PAYER_SELECT,
            selectors.COLLECT_PAYER_OTHER_INPUT,
            "到付付款人",
        )
        self._fill_optional_and_verify(selectors.ELSEWHERE_PAYER_INPUT, "elsewherePayer", "异地付款人")
        self._mark_done("neto")

    def _set_charge(self, field_name, charge_name):
        """选择单个费用项目的付款方式。"""
        value = self.content.get(field_name)
        if value:
            option_label = selectors.charge_option_label(value)
            self.dom.click(
                selectors.charge_option_locator(charge_name, option_label),
                f"{charge_name}付款方式",
                timeout=3,
            )
        self._mark_done(field_name)

    def _set_destination_haulage_charge(self):
        """仅在页面出现加拿大拖车费时填写对应的付款方式。"""
        field_name = "destinationHaulageCharge"
        value = self.content.get(field_name)
        has_field = bool(self.page.eles("x://*[text()='Destination Haulage Charge ']", timeout=1))
        if has_field and not value:
            raise BusinessError("HPL 页面要求 Destination Haulage Charge，但消息未下发")
        if value and not has_field:
            raise BusinessError("消息含 Destination Haulage Charge，但当前 HPL 模板没有该字段")
        if value:
            option_label = selectors.charge_option_label(value)
            self.dom.click(
                selectors.charge_option_locator("Destination Haulage Charge", option_label),
                "Destination Haulage Charge 付款方式",
                timeout=3,
            )
        self._mark_done(field_name)

    def _fill_payer(self, payer_field, address_field, select_locator, address_locator, field_name):
        """填写预付或到付付款人，并在 Others 时填写名称地址。"""
        payer = self.content.get(payer_field)
        address = self.content.get(address_field)
        if payer:
            self.dom.click(select_locator, f"{field_name}下拉框", timeout=3)
            self._choose_dropdown_option(str(payer), field_name)
        if payer == "Others":
            self._fill_and_verify(address_locator, address, f"{field_name}名称地址", required=True)
        elif address:
            raise BusinessError(f"{field_name}不是 Others 时不能下发名称地址")
        self._mark_done(payer_field, address_field)

    def _fill_document_issuance(self):
        """填写提单草稿邮箱、提单类型和正副本数量。"""
        self._fill_and_verify(
            selectors.SEND_BL_DRAFT_INPUT,
            self.content.get("sendBlDraft"),
            "提单草稿收件邮箱",
            required=True,
        )
        self._mark_done("sendBlDraft")
        release_mode = self._required_value("releaseMode", "提单类型")
        page_release_mode = "Original (printed)" if release_mode == "Original" else release_mode
        self.dom.click(selectors.DOCUMENT_TYPE_SELECT, "提单类型下拉框", timeout=3)
        self._choose_dropdown_option(page_release_mode, "提单类型")
        self._mark_done("releaseMode")
        self._fill_optional_and_verify(selectors.UNFREIGHTED_ORIGINAL_INPUT, "numberOfOriginal", "未签单正本数")
        self._fill_optional_and_verify(selectors.UNFREIGHTED_COPY_INPUT, "numberOfCopy", "未签单副本数")
        self._fill_optional_and_verify(selectors.FREIGHTED_ORIGINAL_INPUT, "numberOfFreightedOriginal", "签单正本数")
        self._fill_optional_and_verify(selectors.FREIGHTED_COPY_INPUT, "numberOfFreightedCopy", "签单副本数")

    def _fill_comments(self):
        """填写可选备注并完成字段追踪。"""
        self._fill_optional_and_verify(selectors.REMARKS_INPUT, "remarks", "备注")

    def _finish_metadata_fields(self):
        """处理不对应 HPL 页面控件但在消息中存在的兼容元数据。"""
        container_flag = self.content.get("backFillContainerFlag")
        if container_flag and str(container_flag).upper() != "MBL":
            raise BusinessError(f"HPL 当前仅支持 MBL 箱型回填标记，收到：{container_flag}")
        for field_name in (
            "jobNo",
            "carrier",
            "isUserSave",
            "backFillContainerFlag",
            "backfillTransportTerm",
        ):
            self._mark_done(field_name)
        for field_name in ("receiptPlace", "deliveryPlace"):
            if self.content.get(field_name):
                raise BusinessError(f"HPL 顶层字段暂不支持 {field_name}")
            self._mark_done(field_name)

    def _confirm_shipping_instruction(self):
        """按客户角色提交 SI 或保存草稿，并验证官网成功提示。"""
        if self.customer_role in self.submit_roles:
            self.dom.click(selectors.TERMS_CHECKBOX, "HPL 条款确认框", timeout=3)
            self.dom.click(selectors.SUBMIT_BUTTON, "HPL 提交按钮", timeout=3)
            if not self.page.wait.ele_displayed(selectors.SUBMIT_SUCCESS, timeout=120):
                raise BusinessError("HPL SI 提交后未收到成功提示")
            self.result_save_type = 1
            return

        self.dom.click(selectors.SAVE_DRAFT_BUTTON, "HPL 保存草稿按钮", timeout=3)
        self.dom.click(selectors.SAVE_BUTTON, "HPL 确认保存草稿按钮", timeout=3)
        if not self.page.wait.ele_displayed(selectors.SAVE_DRAFT_SUCCESS, timeout=30):
            raise BusinessError("HPL SI 保存草稿后未收到成功提示")
        self.result_save_type = 1 if self.customer_role in self.save_type_one_draft_roles else 0

    def _fill_optional_and_verify(self, locator, field_name, name):
        """填写可选顶层字段，并无论空值与否完成字段追踪。"""
        self._fill_and_verify(locator, self.content.get(field_name), name, required=False)
        self._mark_done(field_name)

    def _fill_and_verify(self, locator, value, name, *, required=False, normalizer=None):
        """填写定位器对应的文本并回读校验，空值按 required 规则处理。"""
        if self._is_empty(value):
            if required:
                raise BusinessError(f"HPL 缺少必填字段：{name}")
            return
        expected_value = str(value)
        self.dom.input_text(locator, expected_value, name, timeout=5)
        actual_value = self.dom.get_value(locator, name, timeout=3)
        normalize = normalizer or self._normalize_text
        if normalize(actual_value) != normalize(expected_value):
            raise FormValidationError(f"HPL {name}填写不一致：{actual_value} != {expected_value}")

    def _fill_element_and_verify(self, element, value, name, *, required=False):
        """填写已定位到的动态元素并回读校验。"""
        if self._is_empty(value):
            if required:
                raise BusinessError(f"HPL 缺少必填字段：{name}")
            return
        expected_value = str(value)
        element.click()
        element.input(expected_value, clear=True)
        self.page.run_js("arguments[0].blur();", element)
        actual_value = getattr(element, "value", "") or ""
        if self._normalize_text(actual_value) != self._normalize_text(expected_value):
            raise FormValidationError(f"HPL {name}填写不一致：{actual_value} != {expected_value}")

    def _fill_indexed_and_verify(self, locator, index, value, name, *, required=False):
        """填写动态列表中指定下标的输入框。"""
        element = self._element_at(locator, index, name)
        self._fill_element_and_verify(element, value, name, required=required)

    def _element_at(self, locator, index, name):
        """取得动态元素列表中的指定元素，不存在时抛出可读错误。"""
        elements = self.page.eles(locator, timeout=3)
        if len(elements) <= index:
            raise ElementNotFoundError(f"HPL {name}元素不存在：{locator}")
        return elements[index]

    def _choose_dropdown_option(self, expected_text, name, *, contains=False):
        """从当前 Quasar 下拉列表选择指定文本的选项。"""
        time.sleep(0.5)
        for option in self.page.eles(selectors.DROPDOWN_OPTIONS, timeout=5):
            option_text = (option.text or "").strip()
            matched = expected_text in option_text if contains else option_text == expected_text
            if matched:
                option.click()
                return
        raise ElementNotFoundError(f"HPL {name}选项不存在：{expected_text}")

    def _choose_hs_code(self, hs_code, name):
        """从 HPL HS Code 候选项中选择唯一或精确匹配的编码。"""
        time.sleep(1)
        options = self.page.eles(selectors.HS_CODE_OPTIONS, timeout=5)
        exact_option = next((option for option in options if (option.text or "").strip() == hs_code), None)
        if exact_option:
            exact_option.click()
            return
        if len(options) == 1:
            options[0].click()
            return
        raise BusinessError(f"HPL {name}未找到唯一匹配项：{hs_code}")

    def _required_value(self, field_name, name):
        """读取必填顶层字段并在空值时抛出业务错误。"""
        value = self.content.get(field_name)
        if self._is_empty(value):
            raise BusinessError(f"HPL 缺少必填字段：{name}")
        return str(value)

    def _required_goods_value(self, goods, field_name, container_index, goods_index):
        """读取必填货物字段并补充箱号、货物行号错误上下文。"""
        value = goods.get(field_name)
        if self._is_empty(value):
            raise BusinessError(f"HPL 第 {container_index} 箱第 {goods_index} 条货物缺少 {field_name}")
        return str(value)

    def _mark_done(self, *field_names):
        """批量标记顶层字段已处理，字段不存在时保持幂等。"""
        for field_name in field_names:
            self.mark_field_done(field_name)

    @staticmethod
    def _is_empty(value):
        """判断消息字段是否为空，同时保留数值 0 的合法性。"""
        return value is None or (isinstance(value, str) and not value.strip())

    @staticmethod
    def _normalize_text(value):
        """统一浏览器回读中的换行符，避免 Windows 文本框误报不一致。"""
        return str(value or "").replace("\r\n", "\n").strip()

    @staticmethod
    def _normalize_container_no(value):
        """标准化集装箱号，兼容 HPL 自动插入的字母与数字间空格。"""
        return "".join(str(value or "").split()).upper()
