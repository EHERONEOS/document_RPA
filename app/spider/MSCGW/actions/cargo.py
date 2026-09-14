"""MSCGW SI 集装箱与货物动作。"""
from __future__ import annotations

import time
from typing import Any, Mapping

from app.core.flow.runtime import ActionRegistry
from app.core.task.errors import BusinessError, FormValidationError
from app.spider.MSCGW import selectors
from app.spider.MSCGW.si_runtime import MscgwSiRuntime


class CargoActions:
    """封装集装箱和货物明细的填写、校验及保存。"""

    def __init__(self, runtime: MscgwSiRuntime) -> None:
        self.runtime = runtime

    def fill_containers_and_cargo(self, _inputs: Mapping[str, Any]) -> None:
        """完成所有集装箱、货物明细的填写、回读校验与保存。"""
        containers = self.runtime.content.get("containers", [])
        if not containers:
            raise BusinessError("后台下发的集装箱信息为空")
        if len(self.runtime.dom._find_eles(selectors.CONTAINER_ITEM)) != len(containers):
            raise FormValidationError("官网 SI 集装箱数量与填写数量不一致")
        self.runtime.dom.scroll_to_see("c:#Containers", name="定位集装箱列表")
        for container_index, container in enumerate(containers):
            self._fill_container(container_index, container)

    def _fill_container(self, container_index: int, container: Mapping[str, Any]) -> None:
        number = container_index + 1
        self.runtime.si_shadow.click(
            f"c:#panel{number}-header [data-testid=container-options-button]", name=f"{number}号箱操作按钮"
        )
        self.runtime.si_shadow.click(
            f"x://*[@id='panel{number}-header']//*[@id='split-button-menu']/li[normalize-space()='Edit Container']",
            name=f"{number}号箱编辑按钮",
        )
        time.sleep(2)
        self.runtime.si_shadow.input_text(selectors.CONTAINER_NUM_INPUT, container.get("containerNo"), f"{number}号箱号")
        time.sleep(2)
        self.runtime._verify_container_number(container_index)
        if not self.runtime._is_empty_expected_value(container.get("sealNo")):
            self.runtime.si_shadow.input_text(selectors.CONTAINER_SEAL_NO_INPUT, container["sealNo"], f"{number}号箱封条号")
        if not self.runtime._is_empty_expected_value(container.get("remarks")):
            self.runtime.si_shadow.input_text(selectors.CONTAINER_COMMENTS_INPUT, container["remarks"], f"{number}号箱备注")
        self.runtime.si_shadow.click(selectors.CARGO_TAB, name=f"{number}号箱切换货物标签页")
        time.sleep(2)
        for cargo_index, cargo in enumerate(container.get("goods", [])):
            self._fill_cargo(container_index, cargo_index, cargo)
        self.runtime._verify_container_cargo(dict(container), container_index)
        self.runtime.si_shadow.click(selectors.CONTAINER_SAVE_BTN, name=f"保存{number}号箱")
        if not self._wait_for_container_save():
            raise BusinessError(f"集装箱 {number} 保存失败")

    def _fill_cargo(self, container_index: int, cargo_index: int, cargo: Mapping[str, Any]) -> None:
        container_number = container_index + 1
        cargo_number = cargo_index + 1
        cargo_element = self.runtime.si_shadow._find(
            f"x://*[@class='edit-cargo-list']/div[{cargo_number}]", required=False
        )
        if cargo_element:
            cargo_element.click()
        else:
            self.runtime.si_shadow.click(selectors.CARGO_ADD_BTN, name=f"{container_number}号箱新增第{cargo_number}条货物")
            self.runtime.si_shadow.click(
                f"x://*[@class='edit-cargo-list']/div[{cargo_number}]", name=f"选择第{cargo_number}条货物"
            )
        self._fill_hs_code(container_number, cargo_number, cargo)
        self.runtime.si_shadow.select_by_word(
            selectors.CARGO_WEIGHT_UNIT,
            cargo.get("grossWeightUnit"),
            selectors.CARGO_WEIGHT_UNIT_OPTIONS,
            name="选择重量单位",
        )
        time.sleep(1)
        self.runtime.si_shadow.input_text(selectors.CARGO_WEIGHT, cargo.get("grossWeight"), "填写重量")
        if not self.runtime._is_empty_expected_value(cargo.get("volume")):
            self.runtime.si_shadow.select_by_word(
                selectors.CARGO_VOLUME_UNIT, cargo.get("volumeUnit"), selectors.CARGO_VOLUME_UNIT_OPTIONS
            )
            time.sleep(1)
            self.runtime.si_shadow.input_text(selectors.CARGO_VOLUME, cargo["volume"], "填写体积")
        self.runtime.si_shadow.select_by_word(
            selectors.CARGO_PACKAGE_UNIT,
            cargo.get("packageUnit"),
            selectors.CARGO_PACKAGE_UNIT_OPTIONS,
            name="选择包装单位",
        )
        time.sleep(1)
        self.runtime.si_shadow.input_text(selectors.CARGO_PACKAGE, cargo.get("packages"), "填写包装件数")
        self.runtime.si_shadow.input_text(selectors.CARGO_DESC, cargo.get("goodsDesc"), "填写货物描述")
        self.runtime.si_shadow.input_text(selectors.CARGO_MARKS, cargo.get("marks"), "填写唛头")

    def _fill_hs_code(self, container_number: int, cargo_number: int, cargo: Mapping[str, Any]) -> None:
        expected = cargo.get("hsCode")
        if self.runtime.si_shadow.get_value(selectors.CARGO_CODE) == expected:
            return
        self.runtime.http.wait_api_finished(
            url="https://services.mymsc.com/shipping-instruction/graphql",
            method=("POST",),
            trigger=lambda: self.runtime.si_shadow.input_text(
                selectors.CARGO_CODE, expected, f"{container_number}号箱第{cargo_number}条货物 HS Code", blur=False
            ),
            request_params={"operationName": "CommodityList"},
            timeout=10,
            required=False,
        )
        options = self.runtime.si_shadow._find_eles(selectors.CARGO_HS_OPTIONS, name="获取 HS Code 选项", required=False)
        for option in options:
            hs_code = (option.text or "").split("-", 1)[0].strip()
            if hs_code == expected:
                option.click()
                self.runtime.si_shadow.click(selectors.CARGO_CONFIRM, required=False)
                return
        raise BusinessError(f"找不到 HS Code：{expected}")

    def _wait_for_container_save(self) -> bool:
        for _ in range(10):
            if not self.runtime.si_shadow._find(selectors.CONTAINER_SAVE_BTN, required=False, timeout=0.5):
                return True
            time.sleep(1)
        return False

    def register(self, registry: ActionRegistry) -> None:
        """将集装箱和货物动作绑定到显式动作白名单。"""
        registry.register(
            "MSCGW.fill_containers_and_cargo",
            lambda _context, inputs: self.fill_containers_and_cargo(inputs),
        )
