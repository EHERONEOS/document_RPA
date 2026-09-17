"""MSCGW SI 出单方式填写。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.task.errors import BusinessError
from app.spider.MSCGW import selectors

if TYPE_CHECKING:
    from app.spider.MSCGW.tasks.fht_mscgw_si import FhtMscgwSiTask


class SiFillDocumentGroupMixin:
    """封装 Document Group、Document Type 与 Requested Copies。"""

    def select_document_group(self: "FhtMscgwSiTask") -> None:
        self.si_shadow.select_radio(
            selectors.SELECT_DOCUMENT_RADIO, self.content["releaseMode"], "选择出单类型"
        )
        release_mode = self.content["releaseMode"]
        if release_mode == "Sea Waybill":
            self.select_requested_copies()
        elif release_mode == "Original":
            self.select_document_type(release_mode)
            self.select_requested_copies()
        elif release_mode == "Original eBL":
            self.select_document_type(release_mode)
        self.verify_document_group()

    def select_document_type(self: "FhtMscgwSiTask", release_mode: str) -> None:
        document_type = self.content.get("originalDocumentType")
        self.si_shadow.select_radio(selectors.DOCUMENT_TYPE_RADIO, document_type, "选择Document Type")
        if release_mode == "Original":
            if document_type == "Original Unfreighted":
                self.si_shadow.input_text(
                    selectors.UNFREIGHTED_NUM,
                    self.content.get("numberOfOriginal"),
                    "Original Unfreighted 数量",
                )
            elif document_type == "Original Freighted":
                self.si_shadow.input_text(
                    selectors.FREIGHTED_NUM,
                    self.content.get("numberOfFreightedOriginal"),
                    "Original Freighted 数量",
                )

    def select_requested_copies(self: "FhtMscgwSiTask") -> None:
        if self.content["copyUnfreighted"]:
            dom = self.si_shadow._find(selectors.REQUESTED_COPIES_UNFREIGHTED)
            if not dom.states.is_checked:
                dom.click()
            self.si_shadow.input_text(
                selectors.COPIES_UNFREIGHTED_NUM,
                self.content.get("numberOfCopy"),
                "Copy Unfreighted 数量",
            )
        if self.content["copyFreighted"]:
            dom = self.si_shadow._find(selectors.REQUESTED_COPIES_FREIGHTED)
            if not dom.states.is_checked:
                dom.click()
            self.si_shadow.input_text(
                selectors.COPIES_FREIGHTED_NUM,
                self.content.get("numberOfFreightedCopy"),
                "Copy Freighted 数量",
            )

    def verify_document_group(self: "FhtMscgwSiTask") -> None:
        """验证 Document Group 及其关联字段。"""
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
        self: "FhtMscgwSiTask",
        *,
        checkbox_selector: str,
        checkbox_field: str,
        quantity_selector: str,
        quantity_field: str,
        name: str,
    ) -> None:
        """验证 Requested Copy 的勾选状态及数量。"""
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
