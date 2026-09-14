"""MSCGW SI 收发通、地址和地点选择动作。"""
from __future__ import annotations

import re
import time
from typing import Any, Mapping

from app.core.flow.runtime import ActionRegistry
from app.core.task.errors import BusinessError, ElementNotFoundError
from app.spider.MSCGW import selectors
from app.spider.MSCGW.common.si_field_verify import (
    ADDRESS_OPTIONAL_FIELDS,
    get_address_content_field_path,
)
from app.spider.MSCGW.si_runtime import MscgwSiRuntime


_CONTENT_PREFIXES: dict[str, str] = {
    "Shipper": "shipper",
    "Consignee": "consignee",
    "Notify Party": "notify",
    "Second Notify": "secondNotify",
    "Forwarding Agency": "overseasAgent",
}


class LocationActions:
    """封装 MSCGW 页面通用的地点搜索和精确选择操作。"""

    def __init__(self, runtime: MscgwSiRuntime) -> None:
        self.runtime = runtime

    def select_location(self, locator: str, value: str | None, *, name: str) -> None:
        """按照逐词扩展策略搜索并选择 MSCGW 地点。"""
        target_text = str(value or "").strip()
        if not target_text:
            raise ElementNotFoundError(f"{name}目标值为空")
        words = re.findall(r"[^\W_]+", target_text, flags=re.UNICODE)
        if not words:
            raise ElementNotFoundError(f"{name}目标值不包含可搜索单词：{target_text}")
        element = self.runtime.si_shadow._find(locator, name)
        element.click()
        search_keywords: list[str] = []
        for index in range(1, len(words) + 1):
            keyword = " ".join(words[:index])
            search_keywords.append(keyword)
            self.runtime.http.wait_api_finished(
                url="https://services.mymsc.com/shipping-instruction/graphql",
                method=("POST",),
                trigger=lambda search=keyword: element.input(search, clear=True),
                request_params={"operationName": "GetLocations"},
                timeout=10,
                required=False,
            )
            for option in self.runtime.si_shadow._find_eles(selectors.DIALOG_LOCATION_OPTION, required=False):
                if self._normalize(option.text) != self._normalize(target_text):
                    continue
                option.click()
                self.runtime.page.run_js("arguments[0].blur();", element)
                return
        raise ElementNotFoundError(
            f"{name}选项不存在：{target_text}；已尝试搜索：{'；'.join(search_keywords)}"
        )

    @staticmethod
    def _normalize(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


class PartyActions:
    """封装收发通弹窗填写、保存和字段校验。"""

    def __init__(self, runtime: MscgwSiRuntime) -> None:
        self.runtime = runtime
        self.locations = LocationActions(runtime)

    def fill_party(self, inputs: Mapping[str, Any]) -> None:
        """完成指定角色的收发通弹窗填写、保存及字段校验。"""
        address_type = str(inputs["party"])
        try:
            content_prefix = _CONTENT_PREFIXES[address_type]
        except KeyError as exc:
            raise BusinessError(f"不支持的地址类型：{address_type}") from exc

        self.runtime.dom.scroll_to_see(selectors.ADD_NEW_PARTY_BUTTON, name="定位添加地址按钮")
        self.runtime.si_shadow.click("c:.si-party-modal-title button", required=False, timeout=0.5)
        self.runtime.si_shadow.click(
            "c:.confirm-dialog-box button[data-testid=btnOkConfirm]", required=False, timeout=0.5
        )
        edit_button = self.runtime.si_shadow._find(
            f"x://h5[contains(text(),'{address_type}')]/button", required=False, timeout=0.5
        )
        if edit_button:
            edit_button.click()
        else:
            self.runtime.si_shadow.click(selectors.ADD_NEW_PARTY_BUTTON, name="点击添加新地址按钮")
            self.runtime.si_shadow.click(
                f"x://ul[@data-testid='menuListAddNewParty']//li[contains(text(),'{address_type}')]",
                name=f"选择{address_type}",
            )

        def content_value(suffix: str) -> Any:
            return self.runtime.content.get(get_address_content_field_path(content_prefix, suffix))

        self.runtime.si_shadow.input_text(selectors.DIALOG_NAME, content_value("Name"), f"{address_type} 名称")
        self.runtime.si_shadow.input_text(
            selectors.DIALOG_ADDRESS_DETAILS, content_value("AddressDetails"), f"{address_type} 联系地址"
        )
        self.runtime.si_shadow.input_text(selectors.DIALOG_TITLE, content_value("Title"), f"{address_type} 职务")
        self.runtime.si_shadow.input_text(selectors.DIALOG_ADDRESS, content_value("Address"), f"{address_type} 地址")
        self.locations.select_location(selectors.DIALOG_LOCATION, content_value("City"), name=f"{address_type} 城市")
        for suffix, locator, label in ADDRESS_OPTIONAL_FIELDS:
            value = content_value(suffix)
            if value:
                self.runtime.si_shadow.input_text(locator, value, f"{address_type} {label}")
        self.runtime._verify_address_info(address_type, content_prefix)
        self.runtime.si_shadow.click(selectors.DIALOG_SAVE_BTN, f"保存{address_type}信息")
        if not self._wait_for_address_save():
            raise BusinessError(f"{address_type} 保存失败")

    def _wait_for_address_save(self) -> bool:
        for _ in range(10):
            if not self.runtime.si_shadow._find(selectors.DIALOG_NAME, required=False, timeout=0.5):
                return True
            time.sleep(1)
        return False

    def register(self, registry: ActionRegistry) -> None:
        """将收发通动作绑定到显式动作白名单。"""
        registry.register("MSCGW.fill_party", lambda _context, inputs: self.fill_party(inputs))
