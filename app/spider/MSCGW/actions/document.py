"""MSCGW SI 单证组、单证类型和副本动作。"""
from __future__ import annotations

from typing import Any, Mapping

from app.core.flow.runtime import ActionRegistry
from app.spider.MSCGW import selectors
from app.spider.MSCGW.si_runtime import MscgwSiRuntime


class DocumentActions:
    """封装 SI 单证信息的填写和回读校验。"""

    def __init__(self, runtime: MscgwSiRuntime) -> None:
        self.runtime = runtime

    def select_document_group(self, _inputs: Mapping[str, Any]) -> None:
        """选择出单方式、单证类型和副本，并回读校验结果。"""
        release_mode = self.runtime.content["releaseMode"]
        self.runtime.si_shadow.select_radio(selectors.SELECT_DOCUMENT_RADIO, release_mode, "选择出单类型")
        if release_mode == "Sea Waybill":
            self._select_requested_copies()
        elif release_mode == "Original":
            self._select_document_type(release_mode)
            self._select_requested_copies()
        elif release_mode == "Original eBL":
            self._select_document_type(release_mode)
        self.runtime.verify_document_group()

    def _select_document_type(self, release_mode: str) -> None:
        document_type = self.runtime.content.get("originalDocumentType")
        self.runtime.si_shadow.select_radio(selectors.DOCUMENT_TYPE_RADIO, document_type, "选择单证类型")
        if release_mode != "Original":
            return
        if document_type == "Original Unfreighted":
            self.runtime.si_shadow.input_text(
                selectors.UNFREIGHTED_NUM, self.runtime.content.get("numberOfOriginal"), "填写未预付正本数量"
            )
        elif document_type == "Original Freighted":
            self.runtime.si_shadow.input_text(
                selectors.FREIGHTED_NUM,
                self.runtime.content.get("numberOfFreightedOriginal"),
                "填写预付正本数量",
            )

    def _select_requested_copies(self) -> None:
        if self.runtime.content["copyUnfreighted"]:
            element = self.runtime.si_shadow._find(selectors.REQUESTED_COPIES_UNFREIGHTED)
            if not element.states.is_checked:
                element.click()
            self.runtime.si_shadow.input_text(
                selectors.COPIES_UNFREIGHTED_NUM, self.runtime.content.get("numberOfCopy"), "填写未预付副本数量"
            )
        if self.runtime.content["copyFreighted"]:
            element = self.runtime.si_shadow._find(selectors.REQUESTED_COPIES_FREIGHTED)
            if not element.states.is_checked:
                element.click()
            self.runtime.si_shadow.input_text(
                selectors.COPIES_FREIGHTED_NUM,
                self.runtime.content.get("numberOfFreightedCopy"),
                "填写预付副本数量",
            )

    def register(self, registry: ActionRegistry) -> None:
        """将单证组动作绑定到显式动作白名单。"""
        registry.register(
            "MSCGW.select_document_group",
            lambda _context, inputs: self.select_document_group(inputs),
        )
