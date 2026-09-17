"""MSCGW SI 收发通地址填写。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.core.task.errors import BusinessError
from app.spider.MSCGW import selectors

if TYPE_CHECKING:
    from app.spider.MSCGW.tasks.fht_mscgw_si import FhtMscgwSiTask



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

class SiFillAddressInfoMixin:
    """封装 Shipper、Consignee、Notify 等地址信息。"""

    def _fill_address_info(self: "FhtMscgwSiTask", address_type: str) -> None:
        self.dom.scroll_to_see(selectors.ADD_NEW_PARTY_BUTTON, name="定位到添加新地址按钮")
        self.si_shadow.click("c:.si-party-modal-title button", required=False, timeout=0.5)
        self.si_shadow.click("c:.confirm-dialog-box button[data-testid=btnOkConfirm]", required=False, timeout=0.5)

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
            f"x://h5[contains(text(),'{address_type}')]/button", required=False, timeout=0.5
        )
        if edit_btn:
            edit_btn.click()
        else:
            self.si_shadow.click(selectors.ADD_NEW_PARTY_BUTTON, name="点击添加新地址按钮")
            self.si_shadow.click(
                f"x://ul[@data-testid='menuListAddNewParty']//li[contains(text(),'{address_type}')]",
                name=f"点击添加{address_type}按钮",
            )

        content_value = lambda suffix: self.content.get(
            get_address_content_field_path(content_prefix, suffix)
        )
        self.si_shadow.input_text(selectors.DIALOG_NAME, content_value("Name"), f"{address_type} Name")
        self.si_shadow.input_text(
            selectors.DIALOG_ADDRESS_DETAILS, content_value("AddressDetails"), f"{address_type} Address"
        )
        self.si_shadow.input_text(selectors.DIALOG_TITLE, content_value("Title"), f"{address_type} Title")
        self.si_shadow.input_text(selectors.DIALOG_ADDRESS, content_value("Address"), f"{address_type} Address")
        api = selectors.SEARCH_FREE_LOCATION_API if self.splitOrConsolidatedBill else selectors.SEARCH_LOCATION_API
        self.search_location_select(
            selectors.DIALOG_LOCATION,
            content_value("City"),
            api,
            "GetLocations",
            name=f"{address_type} Location",
        )

        for suffix, locator, label in ADDRESS_OPTIONAL_FIELDS:
            field_value = content_value(suffix)
            if field_value:
                self.si_shadow.input_text(locator, field_value, f"{address_type} {label}")
        self._verify_address_info(address_type, content_prefix)
        self.si_shadow.click(selectors.DIALOG_SAVE_BTN, f"保存{address_type}信息")
        if not self._wait_for_address_save():
            raise BusinessError(f"{address_type}保存失败")

    def _wait_for_address_save(self: "FhtMscgwSiTask") -> bool:
        for _ in range(10):
            save_dialog = self.si_shadow._find(selectors.DIALOG_NAME, required=False, timeout=0.5)
            if not save_dialog:
                return True
            time.sleep(1)
        return False

    def _verify_address_info(
        self: "FhtMscgwSiTask", address_type: str, content_prefix: str
    ) -> None:
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
