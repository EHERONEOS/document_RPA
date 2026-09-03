"""MSCGW Shipping Instruction 页面字段校验编排。"""

from app.core.task.errors import BusinessError
from app.spider.MSCGW import selectors


ADDRESS_OPTIONAL_FIELDS = (
    ("ContactReference", selectors.DIALOG_CONTACT_REFERENCE, "Contact Reference"),
    ("ContactName", selectors.DIALOG_CONTACT_NAME, "Contact Name"),
    ("Email", selectors.DIALOG_CONTACT_EMAIL, "Email"),
    ("Fax", selectors.DIALOG_CONTACT_FAX, "Fax"),
    ("Tel", selectors.DIALOG_CONTACT_PHONE, "Tel"),
)

SECOND_NOTIFY_CONTACT_FIELD_PATHS = {
    "Fax": "secondFax",
    "Tel": "secondTel",
}


def get_address_content_field_path(content_prefix: str, suffix: str) -> str:
    """返回地址字段在任务内容中的路径。"""
    if content_prefix == "secondNotify":
        return SECOND_NOTIFY_CONTACT_FIELD_PATHS.get(suffix, f"{content_prefix}{suffix}")
    return f"{content_prefix}{suffix}"


ROUTER_DETAIL_FIELDS = (
    ("receiptPlace", selectors.RECEIPT_INPUT, "收货地", False),
    ("pol", selectors.POL_INPUT, "起运港", True),
    ("pod", selectors.POD_INPUT, "卸货港", True),
    ("deliveryPlace", selectors.DELIVERY_INPUT, "交货地", False),
)


class MscgwSiFieldVerificationMixin:
    """提供 MSCGW SI 填单后的字段校验方法。"""

    def _verify_container_number(self, container_index: int) -> None:
        """校验已填写的箱号已通过 MSC 官网校验。"""
        verify_tip = self.si_shadow.get_text(selectors.CONTAINER_NUM_VERIFY)
        if verify_tip != "Container verified!":
            raise BusinessError(f"集装箱 {container_index + 1} 号箱号检验失败官网提示:{verify_tip}")

    def _verify_payment_type(self) -> None:
        """校验支付方式。"""
        self.verify_page_value(
            selector=selectors.PAYMENT_TYPE_CHECKED,
            field_path="paymentType",
            selector_type="text",
            page=self.si_shadow,
            name="出单类型",
        )
        if self.content.get("paymentType") == "Payable Elsewhere":
            self.verify_page_value(
                selector=selectors.PAYMENT_LOCATION_INPUT,
                field_path="paymentLocation",
                selector_type="value",
                page=self.si_shadow,
                name="选择Elsewhere Location",
            )
        self.verify_page_value(
            selector=selectors.PAYMENT_REMARK_INPUT,
            field_path="remarks",
            selector_type="value",
            page=self.si_shadow,
            name="填写备注",
            skip_if_empty=True,
        )

    def _verify_container_cargo(self, container: dict, container_index: int) -> None:
        """在保存前切换对应标签，校验箱信息与每条货物信息。"""
        container_number = container_index + 1
        container_path = ["containers", container_index]

        self.si_shadow.click(selectors.CONTAINER_TAB, name=f"第{container_number}个集装箱 Container 标签")
        for field_name, selector, name in (
            ("containerType", selectors.CONTAINER_TYPE_INPUT, "Container Type"),
            ("containerNo", selectors.CONTAINER_NUM_INPUT, "Container Number"),
            ("sealNo", selectors.CONTAINER_SEAL_NO_INPUT, "Carrier Seal Number"),
            ("remarks", selectors.CONTAINER_COMMENTS_INPUT, "Remarks"),
        ):
            self.verify_page_value(
                selector=selector,
                field_path=[*container_path, field_name],
                selector_type="value",
                page=self.si_shadow,
                name=f"第{container_number}个集装箱 {name}",
                skip_if_empty=field_name in {"sealNo", "remarks"},
            )

        self.si_shadow.click(selectors.CARGO_TAB, name=f"第{container_number}个集装箱 Cargo 标签")
        for cargo_index, cargo in enumerate(container.get("goods", [])):
            cargo_number = cargo_index + 1
            self.si_shadow.click(
                selectors.CARGO_LIST_ITEM.format(cargo_number),
                name=f"第{container_number}个集装箱第{cargo_number}条货物",
            )
            self._verify_cargo(container_index, cargo_index, cargo)

    def _verify_cargo(self, container_index: int, cargo_index: int, cargo: dict) -> None:
        """校验当前已选中的货物标签字段。"""
        container_number = container_index + 1
        cargo_number = cargo_index + 1
        cargo_path = ["containers", container_index, "goods", cargo_index]
        volume_is_empty = self._is_empty_expected_value(cargo.get("volume"))
        for field_name, selector, name, selector_type in (
            ("hsCode", selectors.CARGO_CODE, "HS Code", "value"),
            (
                "grossWeightUnit",
                selectors.CARGO_WEIGHT_UNIT_TEXT,
                "Gross Weight Unit",
                "text",
            ),
            ("grossWeight", selectors.CARGO_WEIGHT, "Gross Cargo Weight", "value"),
            ("volumeUnit", selectors.CARGO_VOLUME_UNIT_TEXT, "Volume Unit", "text"),
            ("volume", selectors.CARGO_VOLUME, "Volume", "value"),
            ("packageUnit", selectors.CARGO_PACKAGE_UNIT, "Package Type", "value"),
            ("packages", selectors.CARGO_PACKAGE, "No. of Packages", "value"),
            ("marks", selectors.CARGO_MARKS, "Marks & Numbers", "value"),
            ("goodsDesc", selectors.CARGO_DESC, "Description", "value"),
        ):
            field_path = [*cargo_path, field_name]
            if field_name == "volumeUnit" and volume_is_empty:
                self.verify_page_value(
                    selector=selector,
                    field_path=field_path,
                    selector_type=selector_type,
                    page=self.si_shadow,
                    name=f"第{container_number}个集装箱第{cargo_number}条货物 {name}",
                    expected_value=None,
                    skip_if_empty=True,
                )
                continue
            self.verify_page_value(
                selector=selector,
                field_path=field_path,
                selector_type=selector_type,
                page=self.si_shadow,
                name=f"第{container_number}个集装箱第{cargo_number}条货物 {name}",
                skip_if_empty=field_name == "volume",
            )

    def _verify_router_details(self) -> None:
        """验证港口字段填写值。"""
        for field_path, selector, name, required in ROUTER_DETAIL_FIELDS:
            self.verify_page_value(
                selector=selector,
                field_path=field_path,
                selector_type="value",
                page=self.si_shadow,
                name=name,
                skip_if_empty=not required,
            )

    def _verify_address_info(self, address_type: str, content_prefix: str) -> None:
        """校验地址弹窗字段。"""

        def verify_address_value(
            field_path: str,
            locator: str,
            label: str,
            page,
            *,
            skip_if_empty: bool = False,
            ignore_case: bool = False,
        ) -> None:
            self.verify_page_value(
                selector=locator,
                field_path=field_path,
                selector_type="value",
                page=page,
                name=f"{address_type} {label}",
                skip_if_empty=skip_if_empty,
                ignore_case=ignore_case,
            )

        required_fields = (
            ("Name", selectors.DIALOG_NAME, "Name", self.si_shadow),
            ("AddressDetails", selectors.DIALOG_ADDRESS_DETAILS, "Contact Address", self.si_shadow),
            ("Title", selectors.DIALOG_TITLE, "Title", self.si_shadow),
            ("Address", selectors.DIALOG_ADDRESS, "Address", self.si_shadow),
            ("City", selectors.DIALOG_LOCATION, "City", self.dom),
        )
        for suffix, locator, label, page in required_fields:
            verify_address_value(
                get_address_content_field_path(content_prefix, suffix),
                locator,
                label,
                page,
                ignore_case=suffix == "City",
            )

        for suffix, locator, label in ADDRESS_OPTIONAL_FIELDS:
            verify_address_value(
                get_address_content_field_path(content_prefix, suffix),
                locator,
                label,
                self.si_shadow,
                skip_if_empty=True,
            )

    def verify_document_group(self) -> None:
        """验证 Document Group 及其关联的 Document Type、Copy 字段。"""
        release_mode = self.content["releaseMode"]
        self.verify_page_value(
            selector=selectors.CHECKED_SELECT_DOCUMENT,
            field_path="releaseMode",
            selector_type="text",
            page=self.si_shadow,
            name="出单类型",
        )

        if release_mode in {"Original", "Original eBL"}:
            self.verify_page_value(
                selector=selectors.CHECKED_DOCUMENT_TYPE,
                field_path="originalDocumentType",
                selector_type="text",
                page=self.si_shadow,
                name="Document Type",
            )
            if release_mode == "Original":
                document_type = self.content["originalDocumentType"]
                quantity_fields = {
                    "Original Unfreighted": (
                        selectors.UNFREIGHTED_NUM,
                        "numberOfOriginal",
                        "Original Unfreighted 数量",
                    ),
                    "Original Freighted": (
                        selectors.FREIGHTED_NUM,
                        "numberOfFreightedOriginal",
                        "Original Freighted 数量",
                    ),
                }
                try:
                    selector, field_path, name = quantity_fields[document_type]
                except KeyError as error:
                    raise BusinessError(f"不支持的 Original Document Type：{document_type}") from error
                self.verify_page_value(
                    selector=selector,
                    field_path=field_path,
                    selector_type="value",
                    page=self.si_shadow,
                    name=name,
                )

        if release_mode in {"Sea Waybill", "Original"}:
            self._verify_requested_copy(
                checkbox_selector=selectors.REQUESTED_COPIES_UNFREIGHTED,
                checkbox_field="copyUnfreighted",
                quantity_selector=selectors.COPIES_UNFREIGHTED_NUM,
                quantity_field="numberOfCopy",
                name="Copy Unfreighted",
            )
            self._verify_requested_copy(
                checkbox_selector=selectors.REQUESTED_COPIES_FREIGHTED,
                checkbox_field="copyFreighted",
                quantity_selector=selectors.COPIES_FREIGHTED_NUM,
                quantity_field="numberOfFreightedCopy",
                name="Copy Freighted",
            )

        for field_name in (
            "numberOfOriginal",
            "numberOfFreightedOriginal",
            "numberOfCopy",
            "numberOfFreightedCopy",
        ):
            self.mark_field_done(field_name)

    def _verify_requested_copy(
        self,
        *,
        checkbox_selector: str,
        checkbox_field: str,
        quantity_selector: str,
        quantity_field: str,
        name: str,
    ) -> None:
        """验证 Requested Copy 的勾选状态及启用时的数量。"""
        self.verify_page_value(
            selector=checkbox_selector,
            field_path=checkbox_field,
            selector_type="checked",
            page=self.si_shadow,
            name=name,
        )
        if self.content[checkbox_field]:
            self.verify_page_value(
                selector=quantity_selector,
                field_path=quantity_field,
                selector_type="value",
                page=self.si_shadow,
                name=f"{name} 数量",
            )
