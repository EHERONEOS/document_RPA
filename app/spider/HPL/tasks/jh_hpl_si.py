"""JH 客户的 HPL Shipping Instruction 任务。"""

import time

from app.core.task.errors import BusinessError, ElementNotFoundError
from app.spider.HPL import selectors
from app.spider.HPL.common.hpl_si_base import HplSiBaseTask


class JhHplSiTask(HplSiBaseTask):
    """执行 JH_HPL_SI 队列，并处理 JH 覆盖的国家模板。"""

    supported_templates = frozenset({"COMMON", "USA", "CAN", "USA-CAN", "EUR-MZ", "UK", "BRA"})
    confirm_submission = True
    ignored_unfilled_fields = [
        *HplSiBaseTask.ignored_unfilled_fields,
        "preStatus",
        "backfillMarks",
        "backfillVessel",
        "backfillVoyage",
        "backfillGoodsDesc",
        "backfillPaymentType",
        "backfillReleaseMode",
    ]

    HOUSE_BILL_REQUEST = "Ask Hapag-Lloyd to file my house bills"
    CARGO_OWNER = "I am, or represent, the cargo owner; no house Bills of Lading are required"
    NVOCC_SELF_FILER = (
        "I am an NVOCC/Freight Forwarder and act as self-filer / supplementary declarant "
        "for house bill and seller and buyer data"
    )
    NVOCC_HPL_FILER = (
        "I am a NVOCC/Freight Forwarder and ask Hapag-Lloyd to file house B/L data on my behalf"
    )
    OWNER_PROVIDES_SELLER_BUYER = "Provide seller and buyer data to Hapag-Lloyd"
    OWNER_SELF_FILER = "File seller and buyer data through self filing / supplementary declarant"

    def _pod_template(self):
        return str(self.content.get("podTemplate") or "COMMON").upper()

    def _fill_container_template_fields(self, container_index, container):
        """填写 BRA 模板的木质包装申报。"""
        if self._pod_template() != "BRA":
            return
        if not isinstance(container, dict):
            raise BusinessError(f"HPL 第 {container_index} 个集装箱格式错误")
        woodpack = container.get("woodpack")
        if self._is_empty(woodpack):
            raise BusinessError(f"HPL BRA 模板第 {container_index} 个集装箱缺少 woodpack")
        self.dom.click(
            selectors.container_wood_declaration_locator(container_index),
            f"第 {container_index} 个集装箱木质包装声明",
            timeout=3,
        )
        self._choose_dropdown_option(str(woodpack), f"第 {container_index} 个集装箱木质包装声明")

    def _fill_template_specific_fields(self):
        """填写 JH 的美国、加拿大、欧洲、英国和巴西模板字段。"""
        template = self._pod_template()
        if template in {"COMMON", "BRA"}:
            return
        if not self.page.eles(selectors.COUNTRY_REQUIREMENTS_SECTION, timeout=2):
            raise BusinessError(f"HPL {template} 模板未展示 Country Specific & Customs Requirements 区域")

        handlers = {
            "USA": self._fill_usa_requirements,
            "CAN": self._fill_can_requirements,
            "USA-CAN": self._fill_usa_can_requirements,
            "EUR-MZ": self._fill_europe_requirements,
            "UK": self._fill_uk_requirements,
        }
        handlers[template]()

    def _fill_usa_requirements(self):
        requirement = self._select_required_top_level_option(
            "specificRequirementsUsa",
            "美国海关申报方式",
        )
        self._fill_top_level_fields((
            ("selfFilerCodeUsa", selectors.SELF_FILER_USA_INPUT, "美国 Self Filer SCAC Code", False),
        ))
        self._mark_done("specificRequirementsUsa")
        self._fill_house_bills_if_requested(requirement)

    def _fill_can_requirements(self):
        requirement = self._select_required_top_level_option(
            "specificRequirementsCanada",
            "加拿大海关申报方式",
        )
        self._fill_top_level_fields((
            ("selfFilerCodeCan", selectors.SELF_FILER_CAN_INPUT, "加拿大 Self Filer CAN8000 Code", False),
        ))
        self._mark_done("specificRequirementsCanada")
        self._fill_house_bills_if_requested(requirement)

    def _fill_usa_can_requirements(self):
        usa_requirement = self._select_required_top_level_option(
            "specificRequirementsUsa",
            "美国海关申报方式",
        )
        can_requirement = self._select_required_top_level_option(
            "specificRequirementsCanada",
            "加拿大海关申报方式",
        )
        self._fill_top_level_fields((
            ("selfFilerCodeUsa", selectors.SELF_FILER_USA_INPUT, "美国 Self Filer SCAC Code", False),
            ("selfFilerCodeCan", selectors.SELF_FILER_CAN_INPUT, "加拿大 Self Filer CAN8000 Code", False),
        ))
        self._mark_done("specificRequirementsUsa", "specificRequirementsCanada")
        self._fill_house_bills_if_requested(usa_requirement, can_requirement)

    def _fill_europe_requirements(self):
        requirement = self._select_required_top_level_option(
            "specificRequirements",
            "欧洲海关申报方式",
        )
        self._mark_done("specificRequirements")
        if requirement == self.CARGO_OWNER:
            owner_requirement = self._select_required_top_level_option(
                "owerSpecificRequirement",
                "欧洲货主申报方式",
            )
            self._mark_done("owerSpecificRequirement")
            if owner_requirement == self.OWNER_PROVIDES_SELLER_BUYER:
                self._fill_seller_buyer_eori_fields()
                return
            if owner_requirement == self.OWNER_SELF_FILER:
                self._fill_self_filer_eori_fields()
                return
            raise BusinessError(f"HPL EUR-MZ 不支持的货主申报方式：{owner_requirement}")
        if requirement == self.NVOCC_SELF_FILER:
            self._fill_self_filer_eori_fields()
            return
        if requirement == self.NVOCC_HPL_FILER:
            self._select_required_top_level_option("houseSpecificRequirement", "欧洲 House Bill 申报方式")
            self._mark_done("houseSpecificRequirement")
            self._fill_house_bills(extended=True)
            return
        raise BusinessError(f"HPL EUR-MZ 不支持的申报方式：{requirement}")

    def _fill_uk_requirements(self):
        requirement = self._select_required_top_level_option(
            "specificRequirementsUk",
            "英国海关申报方式",
        )
        self._mark_done("specificRequirementsUk")
        if requirement == self.CARGO_OWNER:
            self._fill_top_level_fields((("ucrNo", selectors.UCR_NUMBER_INPUT, "UCR Number", False),))
            return
        if requirement == self.NVOCC_SELF_FILER:
            self._fill_self_filer_eori_fields()
            return
        if requirement == self.NVOCC_HPL_FILER:
            self._fill_top_level_fields((("ucrNo", selectors.UCR_NUMBER_INPUT, "UCR Number", False),))
            self._fill_house_bills(extended=True)
            return
        raise BusinessError(f"HPL UK 不支持的申报方式：{requirement}")

    def _fill_seller_buyer_eori_fields(self):
        """填写 EUR-MZ 货主模式的卖买方与 EORI 信息。"""
        self._fill_top_level_fields((
            ("seller", selectors.SELLER_INPUT, "Seller", True),
            ("buyer", selectors.BUYER_INPUT, "Buyer", True),
            ("sellerTaxId", selectors.SELLER_TAX_ID_INPUT, "Seller TAX ID", False),
            ("buyerTaxId", selectors.BUYER_TAX_ID_INPUT, "Buyer TAX ID", False),
            ("sellerEoriNo", selectors.SELLER_EORI_INPUT, "Seller EORI", False),
            ("buyerEoriNo", selectors.BUYER_EORI_INPUT, "Buyer EORI", False),
            ("ucrNo", selectors.UCR_NUMBER_INPUT, "UCR Number", False),
            ("consigneeEoriNo", selectors.CONSIGNEE_EORI_INPUT, "Consignee EORI", False),
            ("shipperEoriNo", selectors.SHIPPER_EORI_INPUT, "Shipper EORI", False),
            ("forwarderEoriNo", selectors.FORWARDER_EORI_INPUT, "Freight Forwarder EORI", False),
            ("notifyEoriNo", selectors.NOTIFY_EORI_INPUT, "Notify EORI", False),
            ("manufacturerEoriNo", selectors.MANUFACTURER_EORI_INPUT, "Manufacturer EORI", False),
            ("warehouseKeeperEoriNo", selectors.WAREHOUSE_KEEPER_EORI_INPUT, "Warehouse Keeper EORI", False),
            ("consolidatorEoriNo", selectors.CONSOLIDATOR_EORI_INPUT, "Consolidator EORI", False),
        ))

    def _fill_self_filer_eori_fields(self):
        """填写 EUR-MZ/UK 自报关模式的 EORI 信息。"""
        self._fill_top_level_fields((
            ("selfSupplemEoriNo", selectors.SELF_SUPPLEMENTARY_EORI_INPUT, "Self Filer EORI", True),
            ("ucrNo", selectors.UCR_NUMBER_INPUT, "UCR Number", False),
            ("consigneeEoriNo", selectors.CONSIGNEE_EORI_SELF_FILER_INPUT, "Consignee EORI", False),
            ("shipperEoriNo", selectors.SHIPPER_EORI_SELF_FILER_INPUT, "Shipper EORI", False),
            ("forwarderEoriNo", selectors.FORWARDER_EORI_INPUT, "Freight Forwarder EORI", False),
            ("notifyEoriNo", selectors.NOTIFY_EORI_INPUT, "Notify EORI", False),
            ("manufacturerEoriNo", selectors.MANUFACTURER_EORI_INPUT, "Manufacturer EORI", False),
            ("warehouseKeeperEoriNo", selectors.WAREHOUSE_KEEPER_EORI_INPUT, "Warehouse Keeper EORI", False),
            ("consolidatorEoriNo", selectors.CONSOLIDATOR_EORI_INPUT, "Consolidator EORI", False),
        ))

    def _fill_top_level_fields(self, fields):
        """填写模板顶层文本字段并完成未填字段追踪。"""
        for field_name, locator, name, required in fields:
            self._fill_and_verify(locator, self.content.get(field_name), name, required=required)
            self._mark_done(field_name)

    def _select_required_top_level_option(self, field_name, name):
        value = self._required_value(field_name, name)
        self.dom.click(selectors.text_locator(value), name, timeout=5)
        return value

    def _fill_house_bills_if_requested(self, *requirements):
        """仅在美加模板要求 HPL 申报 House Bill 时填写基础 House Bill。"""
        requested = any(requirement == self.HOUSE_BILL_REQUEST for requirement in requirements)
        if requested:
            self._fill_house_bills(extended=False)
            return
        if self.content.get("hbls"):
            raise BusinessError("HPL 当前申报方式不需要 hbls，但消息仍下发了 hbls")

    def _fill_house_bills(self, *, extended):
        """新增并填写 House Bill；欧洲和英国模板额外填写扩展字段。"""
        hbls = self.content.get("hbls")
        if not isinstance(hbls, list) or not hbls:
            raise BusinessError("HPL 当前模板要求至少一条 hbls")
        if any(not isinstance(hbl, dict) for hbl in hbls):
            raise BusinessError("HPL hbls 必须为对象列表")

        for _ in range(len(hbls) - 1):
            self.dom.click(selectors.ADD_HOUSE_BILL_BUTTON, "新增 House Bill", timeout=3)
        for index, hbl in enumerate(hbls, start=1):
            self._fill_house_bill_text(index, hbl, "shipperTrue", "True Shipper", "True Shipper", required=True)
            self._fill_house_bill_text(
                index,
                hbl,
                "consigneeUltimate",
                "Ultimate Consignee",
                "Ultimate Consignee",
                required=True,
            )
            if extended:
                self._fill_extended_house_bill(index, hbl)
            self._select_house_bill_containers(index, hbl)
        self._mark_done("hbls")

    def _fill_extended_house_bill(self, index, hbl):
        """填写 EUR-MZ/UK House Bill 的税号、路线和付款方式。"""
        for field_name, label, name in (
            ("shipperTaxIdTrue", "TAX ID of True Shipper", "True Shipper TAX ID"),
            ("consigneeTaxIdUltimate", "TAX ID of Ultimate Consignee", "Ultimate Consignee TAX ID"),
            ("shipperEoriTrue", "EORI No. of True Shipper", "True Shipper EORI"),
            ("consigneeEoriUltimate", "EORI No. of Ultimate Consignee", "Ultimate Consignee EORI"),
            ("hblSeller", "Seller", "House Bill Seller"),
            ("hblBuyer", "Buyer", "House Bill Buyer"),
            ("hblSellerTaxId", "Tax ID of Seller", "House Bill Seller TAX ID"),
            ("hblBuyerTaxId", "Tax ID of Buyer", "House Bill Buyer TAX ID"),
            ("hblSellerEoriNo", "EORI No. of Seller", "House Bill Seller EORI"),
            ("hblBuyerEoriNo", "EORI No. of Buyer", "House Bill Buyer EORI"),
        ):
            self._fill_house_bill_text(index, hbl, field_name, label, name, required=False)

        self._click_house_bill_if_true(
            index,
            hbl,
            "useShipperFromAddressesSection",
            "houseBillsUseShipperDataCheckbox",
            "使用地址区发货人",
        )
        self._click_house_bill_if_true(
            index,
            hbl,
            "useConsigneeFromAddressesSection",
            "houseBillsUseConsigneeDataCheckbox",
            "使用地址区收货人",
        )
        self._click_house_bill_if_true(
            index,
            hbl,
            "isShipperSameAsAbove",
            "houseBillsUseSellerDataCheckbox",
            "使用上方卖方",
        )
        self._click_house_bill_if_true(
            index,
            hbl,
            "isConsigneeSameAsAbove",
            "houseBillsUseBuyerDataCheckbox",
            "使用上方买方",
        )
        self._fill_house_bill_place(index, hbl, "receiptPlace", "receiptPlaceCode", "Select Place of Receipt", "Place of Receipt")
        self._fill_house_bill_place(index, hbl, "deliveryPlace", "deliveryPlaceCode", "Select Place of Delivery", "Place of Delivery")
        self._fill_consignment_countries(index, hbl)
        self._fill_house_bill_payment(index, hbl)

    def _fill_house_bill_text(self, index, hbl, field_name, aria_label, name, *, required):
        self._fill_and_verify(
            selectors.house_bill_field_locator(index, aria_label),
            hbl.get(field_name),
            f"第 {index} 条 House Bill {name}",
            required=required,
        )

    def _click_house_bill_if_true(self, index, hbl, field_name, test_id, name):
        if hbl.get(field_name):
            self.dom.click(
                selectors.house_bill_test_id_locator(index, test_id),
                f"第 {index} 条 House Bill {name}",
                timeout=3,
            )

    def _fill_house_bill_place(self, index, hbl, field_name, code_field, placeholder, name):
        value = hbl.get(field_name)
        code = hbl.get(code_field)
        if self._is_empty(value) and self._is_empty(code):
            return
        if self._is_empty(value) or self._is_empty(code):
            raise BusinessError(f"HPL 第 {index} 条 House Bill {name}必须同时提供名称和代码")
        query = str(value).split()[0]
        self._search_house_bill_option(
            index,
            placeholder,
            query,
            (query, str(code)),
            f"第 {index} 条 House Bill {name}",
        )

    def _fill_consignment_countries(self, index, hbl):
        countries = hbl.get("consignmentCounty") or []
        if not isinstance(countries, list):
            raise BusinessError(f"HPL 第 {index} 条 House Bill consignmentCounty 必须为列表")
        for country in countries:
            self._search_house_bill_option(
                index,
                "Select further visited countries by consignment",
                str(country),
                (str(country),),
                f"第 {index} 条 House Bill 经停国家",
            )

    def _fill_house_bill_payment(self, index, hbl):
        value = hbl.get("methodPayment")
        if self._is_empty(value):
            raise BusinessError(f"HPL 第 {index} 条 House Bill 缺少 methodPayment")
        self.dom.click(
            selectors.house_bill_test_id_locator(index, "houseBillMethodOfPaymentSelect"),
            f"第 {index} 条 House Bill 付款方式",
            timeout=3,
        )
        self._choose_dropdown_option(str(value), f"第 {index} 条 House Bill 付款方式", contains=True)

    def _search_house_bill_option(self, index, placeholder, query, fragments, name):
        locator = selectors.house_bill_placeholder_locator(index, placeholder)
        self.dom.input_text(locator, query, name, timeout=3)
        time.sleep(1)
        options = self.page.eles(selectors.DROPDOWN_OPTIONS, timeout=5)
        if len(options) == 1:
            options[0].click()
            return
        for option in options:
            option_text = (option.text or "").strip()
            if all(fragment in option_text for fragment in fragments):
                option.click()
                return
        raise ElementNotFoundError(f"HPL {name}选项不存在：{query}")

    def _select_house_bill_containers(self, index, hbl):
        labels = hbl.get("chooseHouseAboveLabel") or []
        if not isinstance(labels, list):
            raise BusinessError(f"HPL 第 {index} 条 House Bill chooseHouseAboveLabel 必须为列表")
        for label in labels:
            raw_label = str(label)
            page_label = raw_label[:-7] + "  " + raw_label[-7:] if len(raw_label) > 7 else raw_label
            self.dom.click(
                selectors.house_bill_text_locator(index, page_label),
                f"第 {index} 条 House Bill 关联集装箱 {raw_label}",
                timeout=3,
            )


def jh_hpl_si(context):
    """提供给 JH_HPL_SI 路由调用的任务入口。"""
    return JhHplSiTask(context).run()
