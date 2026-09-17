"""MSCGW SI 箱货信息填写。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.core.task.errors import BusinessError, FormValidationError
from app.spider.MSCGW import selectors

if TYPE_CHECKING:
    from app.spider.MSCGW.tasks.fht_mscgw_si import FhtMscgwSiTask


class SiFillContainerCargoMixin:
    """封装集装箱及货物信息。"""

    def _fill_container_cargo(self: "FhtMscgwSiTask") -> None:
        containers = self.content.get("containers", [])
        if not containers:
            raise BusinessError("后台下发的集装箱信息为空")
        self.dom.scroll_to_see("c:#Containers", name="定位到集装箱列表")

        if not self.splitOrConsolidatedBill:
            container_ele = self.dom._find_eles(selectors.CONTAINER_ITEM)
            if len(container_ele) != len(containers):
                raise FormValidationError("官网 SI 集装箱数量与填写数量不一致")

        for index, container in enumerate(containers):
            if self.splitOrConsolidatedBill:
                self.si_shadow.click(selectors.FREE_ADD_CONTAINER_BTN, name="集装箱添加按钮")
                self.si_shadow.select_by_word(
                    selectors.CONTAINER_TYPE_INPUT,
                    container.get("containerType"),
                    selectors.FREE_AGENCY_OPTIONS,
                    name=f"{index + 1}集装箱选择集装箱类型",
                )
            else:
                self.si_shadow.click(
                    f"c:#panel{index + 1}-header [data-testid=container-options-button]",
                    name=f"{index + 1}集装箱操作按钮",
                )
                self.si_shadow.click(
                    f"x://*[@id='panel{index + 1}-header']//*[@id='split-button-menu']/li["
                    "normalize-space()='Edit Container']",
                    name=f"{index + 1}集装箱编辑按钮",
                )
                time.sleep(2)

            self.si_shadow.input_text(
                selectors.CONTAINER_NUM_INPUT,
                container.get("containerNo"),
                f"{index + 1} 集装箱Container Number",
            )
            time.sleep(2)
            self._verify_container_number(index)
            if not self._is_empty_expected_value(container.get("sealNo")):
                self.si_shadow.input_text(
                    selectors.CONTAINER_SEAL_NO_INPUT,
                    container["sealNo"],
                    f"{index + 1} 集装箱Carrier Seal Number",
                )
            if not self._is_empty_expected_value(container.get("remarks")):
                self.si_shadow.input_text(
                    selectors.CONTAINER_COMMENTS_INPUT,
                    container["remarks"],
                    f"{index + 1} 集装箱Remarks",
                )
            self.si_shadow.click(selectors.CARGO_TAB, name=f"{index + 1}集装箱切换货物标签页")
            time.sleep(2)

            for cargo_index, cargo in enumerate(container.get("goods", []), start=1):
                cargo_ele = self.si_shadow._find(
                    f"x://*[@class='edit-cargo-list']/div[{cargo_index}]", required=False
                )
                if cargo_ele:
                    cargo_ele.click()
                else:
                    self.si_shadow.click(
                        selectors.CARGO_ADD_BTN,
                        name=f"{index + 1}集装箱 {cargo_index}添加货物",
                    )
                    self.si_shadow.click(
                        f"x://*[@class='edit-cargo-list']/div[{cargo_index}]",
                        name=f"{index + 1}集装箱 {cargo_index}货物",
                    )

                actual_hs_code = self.si_shadow.get_value(selectors.CARGO_CODE)
                if actual_hs_code != cargo.get("hsCode"):
                    self.http.wait_api_finished(
                        url=(
                            selectors.SEARCH_FREE_LOCATION_API
                            if self.splitOrConsolidatedBill
                            else selectors.SEARCH_LOCATION_API
                        ),
                        method=("POST",),
                        trigger=lambda: self.si_shadow.input_text(
                            selectors.CARGO_CODE,
                            cargo.get("hsCode"),
                            f"{index + 1}集装箱 {cargo_index}货物HS Code",
                            blur=False,
                        ),
                        request_params={"operationName": "CommodityList"},
                        timeout=10,
                        required=False,
                    )
                    options = self.si_shadow._find_eles(
                        selectors.CARGO_HS_OPTIONS, name="获取HS Code选项", required=False
                    )
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

                self.si_shadow.select_by_word(
                    selectors.CARGO_WEIGHT_UNIT,
                    cargo.get("grossWeightUnit"),
                    selectors.CARGO_WEIGHT_UNIT_OPTIONS,
                    name="选择Weight Unit",
                )
                time.sleep(1)
                self.si_shadow.input_text(
                    selectors.CARGO_WEIGHT,
                    cargo.get("grossWeight"),
                    f"{index + 1}集装箱 {cargo_index}货物Weight",
                )
                if not self._is_empty_expected_value(cargo.get("volume")):
                    self.si_shadow.select_by_word(
                        selectors.CARGO_VOLUME_UNIT,
                        cargo.get("volumeUnit"),
                        selectors.CARGO_VOLUME_UNIT_OPTIONS,
                    )
                    time.sleep(1)
                    self.si_shadow.input_text(
                        selectors.CARGO_VOLUME,
                        cargo["volume"],
                        f"{index + 1}集装箱 {cargo_index}货物Volume",
                    )
                self.si_shadow.select_by_word(
                    selectors.CARGO_PACKAGE_UNIT,
                    cargo.get("packageUnit"),
                    selectors.CARGO_PACKAGE_UNIT_OPTIONS,
                    name="选择Package Unit",
                )
                time.sleep(1)
                self.si_shadow.input_text(
                    selectors.CARGO_PACKAGE,
                    cargo.get("packages"),
                    f"{index + 1}集装箱 {cargo_index}货物NumberOfPackages",
                )
                self.si_shadow.input_text(
                    selectors.CARGO_DESC,
                    cargo.get("goodsDesc"),
                    f"{index + 1}集装箱 {cargo_index}货物Description",
                )
                self.si_shadow.input_text(
                    selectors.CARGO_MARKS,
                    cargo.get("marks"),
                    f"{index + 1}集装箱 {cargo_index}货物MarksAndNumbers",
                )

            self._verify_container_cargo(container, index)
            self.si_shadow.click(selectors.CONTAINER_SAVE_BTN, name=f"保存{index + 1}集装箱")
            if not self._wait_for_container_save():
                raise BusinessError(f"集装箱 {index + 1} 保存失败")

    def _wait_for_container_save(self: "FhtMscgwSiTask") -> bool:
        for _ in range(10):
            save_dialog = self.si_shadow._find(selectors.CONTAINER_SAVE_BTN, required=False, timeout=0.5)
            if not save_dialog:
                return True
            time.sleep(1)
        return False

    def _verify_container_number(self: "FhtMscgwSiTask", container_index: int) -> None:
        """校验箱号已通过 MSC 官网校验。"""
        verify_tip = self.si_shadow.get_text(selectors.CONTAINER_NUM_VERIFY)
        if verify_tip != "Container verified!":
            raise BusinessError(f"集装箱 {container_index + 1} 号箱号检验失败官网提示:{verify_tip}")

    def _verify_container_cargo(self: "FhtMscgwSiTask", container: dict, container_index: int) -> None:
        """在保存前校验箱信息与每条货物信息。"""
        container_number = container_index + 1
        container_path = ["containers", container_index]
        self.si_shadow.click(selectors.CONTAINER_TAB, name=f"第{container_number}个集装箱 Container 标签")
        time.sleep(3)
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
        time.sleep(2)
        for cargo_index, cargo in enumerate(container.get("goods", [])):
            cargo_number = cargo_index + 1
            self.si_shadow.click(
                selectors.CARGO_LIST_ITEM.format(cargo_number),
                name=f"第{container_number}个集装箱第{cargo_number}条货物",
            )
            self._verify_cargo(container_index, cargo_index, cargo)

    def _verify_cargo(
        self: "FhtMscgwSiTask", container_index: int, cargo_index: int, cargo: dict
    ) -> None:
        """校验当前货物标签字段。"""
        container_number = container_index + 1
        cargo_number = cargo_index + 1
        cargo_path = ["containers", container_index, "goods", cargo_index]
        volume_is_empty = self._is_empty_expected_value(cargo.get("volume"))
        for field_name, selector, name, selector_type in (
            ("hsCode", selectors.CARGO_CODE, "HS Code", "value"),
            ("grossWeightUnit", selectors.CARGO_WEIGHT_UNIT_TEXT, "Gross Weight Unit", "text"),
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
