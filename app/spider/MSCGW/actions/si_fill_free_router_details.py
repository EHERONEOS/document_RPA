"""MSCGW SI 拆并单港口信息填写。"""

from __future__ import annotations
import re

import time
from typing import TYPE_CHECKING

from app.core.task.errors import ElementNotFoundError

from app.spider.MSCGW import selectors

if TYPE_CHECKING:
    from app.spider.MSCGW.tasks.fht_mscgw_si import FhtMscgwSiTask


class SiFillFreeRouterDetailsMixin:
    """封装拆并单的收发地、港口和运输方式。"""

    def _fill_free_router_details(self: "FhtMscgwSiTask") -> None:
        self.dom.scroll_to_see("c:#routes", name="滚动到路由详情")
        time.sleep(1)
        if self.content.get("preCarriageMode"):
            self.si_shadow.select_by_word(
                selectors.FREE_RECEIPT_CARRIAGE_MODE,
                self.content.get("preCarriageMode"),
                selectors.FREE_RECEIPT_CARRIAGE_MODE_OPTIONS,
                name="选择收货地运输方式",
            )
            time.sleep(1)
            self.search_location_select(
                selectors.FREE_RECEIPT_LOCATION_INPUT,
                self.content.get("receiptPlace"),
                selectors.SEARCH_FREE_LOCATION_API,
                "SearchMdmLocations",
                name="选择收货地城市",
            )
            self.si_shadow.input_text(
                selectors.RECEIPT_INPUT,
                self.content.get("receiptPlacePrintOnBl"),
                name="输入收货地",
            )

        self.search_ports_select(
            selectors.FREE_POL_LOCATION_INPUT,
            self.content.get("pol"),
            name="选择装货港城市",
        )
        self.si_shadow.input_text(selectors.POL_INPUT, self.content.get("polPrintOnBl"), name="输入装货港")

        self.search_ports_select(
            selectors.FREE_POD_LOCATION_INPUT,
            self.content.get("pod"),
            name="选择卸货港城市",
        )
        self.si_shadow.input_text(selectors.POD_INPUT, self.content.get("podPrintOnBl"), name="输入卸货港")

        if self.content.get("onCarriageMode"):
            self.si_shadow.select_by_word(
                selectors.FREE_DELIVERY_CARRIAGE_MODE,
                self.content.get("onCarriageMode"),
                selectors.FREE_DELIVERY_CARRIAGE_MODE_OPTIONS,
                name="选择交货地运输方式",
            )
            time.sleep(1)
            self.search_location_select(
                selectors.FREE_DELIVERY_LOCATION_INPUT,
                self.content.get("deliveryPlace"),
                selectors.SEARCH_FREE_LOCATION_API,
                "SearchMdmLocations",
                name="选择交货地城市",
            )
            self.si_shadow.input_text(
                selectors.DELIVERY_INPUT,
                self.content.get("deliveryPlacePrintOnBl"),
                name="输入交货地",
            )
        self.verify_free_router_details()

    def verify_free_router_details(self: "FhtMscgwSiTask") -> None:
        """验证拆并单路由字段。"""
        required_fields = (
            (
                "preCarriageMode",
                selectors.FREE_RECEIPT_CARRIAGE_MODE,
                "收货地运输方式",
                self.si_shadow,
                True,
                "text",
            ),
            (
                "receiptPlace",
                selectors.FREE_RECEIPT_LOCATION_INPUT,
                "收货地城市",
                self.si_shadow,
                True,
                "value",
            ),
            ("receiptPlacePrintOnBl", selectors.RECEIPT_INPUT, "收货地", self.si_shadow, True, "value"),
            ("polPrintOnBl", selectors.POL_INPUT, "装货港", self.si_shadow, False, "value"),
            ("podPrintOnBl", selectors.POD_INPUT, "卸货港", self.si_shadow, False, "value"),
            (
                "onCarriageMode",
                selectors.FREE_DELIVERY_CARRIAGE_MODE,
                "交货地运输方式",
                self.si_shadow,
                True,
                "text",
            ),
            ("deliveryPlace", selectors.FREE_DELIVERY_LOCATION_INPUT, "交货地城市", self.si_shadow, True, "value"),
            ("deliveryPlacePrintOnBl", selectors.DELIVERY_INPUT, "交货地", self.si_shadow, True, "value"),
        )
        for field_path, selector, name, page, skip_if_empty, selector_type in required_fields:
            self.verify_page_value(
                selector=selector,
                field_path=field_path,
                selector_type=selector_type,
                page=page,
                name=name,
                skip_if_empty=skip_if_empty,
                ignore_case=True,
                mark_done=field_path != "pol",
            )
        pol_name = f"{self.content.get('pol')} [{self.content.get('polCode')}]"
        self.verify_page_value(
            selector=selectors.FREE_POL_LOCATION_INPUT,
            field_path="pol",
            expected_value=pol_name,
            selector_type="value",
            page=self.si_shadow,
            name="装货港城市",
            mark_done=False,
            ignore_case=True,
        )
        self.mark_field_done("pol")
        self.mark_field_done("polCode")

        pod_name = f"{self.content.get('pod')} [{self.content.get('podCode')}]"
        self.verify_page_value(
            selector=selectors.FREE_POD_LOCATION_INPUT,
            field_path="pod",
            expected_value=pod_name,
            selector_type="value",
            page=self.si_shadow,
            name="装货港城市",
            mark_done=False,
        )
        self.mark_field_done("pod")
        self.mark_field_done("podCode")


    def search_ports_select(
        self: "FhtMscgwSiTask",
        location: str,
        value: str,
        name: str = "选择ports",
    ) -> None:
        """搜索并选择地点。"""
        target_text = str(value).strip()
        if not target_text:
            raise ElementNotFoundError(f"{name}目标值为空")
        normalize = lambda text: re.sub(r"\s+", " ", str(text or "")).strip().casefold()
        element = self.si_shadow._find(location, name)
        element.click()
        self.http.wait_api_finished(
            url=selectors.SEARCH_FREE_LOCATION_API,
            method=("POST",),
            trigger=lambda: element.input(target_text, clear=True),
            request_params={"operationName": "SearchMdmPorts"},
            timeout=20,
            required=False,
        )
        for option in self.si_shadow._find_eles(selectors.DIALOG_LOCATION_OPTION, required=False):
            if not normalize(option.text).startswith(normalize(target_text)):
                continue
            option.click()
            self.page.run_js("arguments[0].blur();", element)
            self.logger.info(f"选择{name}: {target_text}")
            return True

        raise ElementNotFoundError(
            f"{name}选项不存在：{target_text}"
        )
