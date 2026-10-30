"""SNLWY SI 箱货信息填写。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from DrissionPage._functions.keys import Keys
from DrissionPage.errors import NoRectError

from app.core.task.errors import BusinessError, ElementNotFoundError, FormValidationError
from app.spider.SNLWY import selectors

if TYPE_CHECKING:
    from app.spider.SNLWY.tasks.fz_snlwy_si import FzSnlwySiTask

_CONTENT_PART = "*[contains(@class,'cm-content')]"
_CONTENT_CLEAR = "*[contains(@class,'textarea-clear-icon')]"
_TEXTAREA_PART = "*[contains(@class,'el-textarea__inner')]"
_INPUT_PART = "*[contains(@class,'el-input__inner')]"
_SELECT_INPUT = "*[contains(@class,'el-select__input')]"
_SELECT_DISPLAY = "*[contains(@class,'el-select')]"
_VALUE_INPUT_MARKERS = ("el-input__inner", "el-textarea__inner")

# 添加箱弹窗。箱号标签文本带星号。可搜索下拉需要先输入再点同名选项。
_CONTAINER_FIELDS = (
    {"label": "箱号*", "key": "containerNo", "select": True, "search": True},
    {"label": "箱经营人", "key": "soc", "select": True},
    {"label": "尺寸", "key": "containerSize", "select": True, "search": True},
    {"label": "箱型", "key": "splitContainerType", "select": True, "search": True},
    {"label": "铅封号", "key": "sealNo", "part": _INPUT_PART},
    {"label": "件数", "key": "packages", "part": _INPUT_PART},
    {"label": "毛重(KGS)", "key": "grossWeight", "part": _INPUT_PART},
    {"label": "体积(CBM)", "key": "volume", "part": _INPUT_PART},
)
_VGM_FIELDS = (
    {"label": "称重方法", "key": "method", "select": True},
    {"label": "称重时间", "key": "weightingDate", "part": _INPUT_PART, "date": True},
    {"label": "VGM箱总重", "key": "weight", "part": _INPUT_PART},
    {"label": "称重地点", "key": "weightingPlace", "part": _INPUT_PART},
    {"label": "签名验证", "key": "signature", "part": _INPUT_PART},
)

# 网站字段名、下发字段名、输入节点。
_CARGO_SUMMARY_FIELDS = (
    {"label": "唛头", "key": "totalMarks", "part": _CONTENT_PART},
    {"label": "货物描述", "key": "totalGoodsDesc", "part": _CONTENT_PART},
    {"label": "中文品名", "key": "totalCnGoodsDesc", "part": _TEXTAREA_PART},
    {"label": "HS Code", "key": "totalHsCode", "select": _SELECT_INPUT, "hs_code": True},
    {
        "label": "包装名称",
        "key": "totalAmountUnitName",
        "select": _SELECT_INPUT,
        "options": selectors.COUNTRY_OPTIONS,
    },
    {"label": "包装代码", "key": "totalAmountUnit", "verify_only": True},
    {"label": "箱内件数", "key": "totalAmount", "part": _INPUT_PART},
    {"label": "毛重(KGS)", "key": "totalGrossWeight", "part": _INPUT_PART},
    {"label": "体积(CBM)", "key": "totalVolume", "part": _INPUT_PART},
)


def _text(value) -> str:
    return "" if value is None else str(value)


def _is_value_input(part: str) -> bool:
    return any(marker in part for marker in _VALUE_INPUT_MARKERS)


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _option_visible(option) -> bool:
    style = option.attr("style") or ""
    return "display: none" not in style and "display:none" not in style


def _same_amount(expected: str, actual: str) -> bool:
    """页面重量和体积固定显示 3 位小数，2.2222 会显示成 2.222。"""
    try:
        return round(float(expected), 3) == round(float(actual), 3)
    except ValueError:
        return False


def _hs_option_matches(option_text: str, value: str) -> bool:
    """HS Code 选项是「编码 (说明)」，下发值只比对编码。"""
    text = option_text.strip()
    if text == value:
        return True
    head = text.split(" ", 1)[0].split("(", 1)[0]
    return head == value


class SiFillContainerCargoMixin:
    """封装集装箱及货物信息。"""

    def _fill_container_cargo(self: "FzSnlwySiTask") -> None:
        """填写货物汇总。表单项都在 .cargo-content 内。"""
        self.dom.scroll_to_see("c:.cargo-content", name="货物信息")
        for config in _CARGO_SUMMARY_FIELDS:
            self._fill_cargo_field(config)
        self._verify_cargo_summary()
        self._fill_containers()

    def _fill_cargo_field(self: "FzSnlwySiTask", config: dict) -> None:
        label, key = config["label"], config["key"]
        if config.get("verify_only"):
            return
        if config.get("select"):
            self._fill_cargo_select(config)
            return
        self._fill_cargo_field_if_changed(
            selectors.cargo_content_selector(label, config["part"]),
            label,
            key,
        )

    def _fill_cargo_select(self: "FzSnlwySiTask", config: dict) -> None:
        """下拉与当前展示不一致时才重新选择。"""
        label, key = config["label"], config["key"]
        value = _text(self.content.get(key, "")).strip()
        if not value:
            return
        display = self.dom.get_text(
            selectors.cargo_content_selector(label, _SELECT_DISPLAY),
            label,
        )
        if value in display:
            return
        if config.get("hs_code"):
            self._select_hs_code(label, value)
            return
        self.dom.select_by_word(
            selectors.cargo_content_selector(label, config["select"]),
            value,
            config.get("options", selectors.COUNTRY_OPTIONS),
            name=label,
        )

    def _select_hs_code(self: "FzSnlwySiTask", label: str, value: str) -> None:
        """HS Code 需先输入编码过滤，再点编码完全匹配的选项。"""
        field_selector = selectors.cargo_content_selector(label, _SELECT_INPUT)
        self.dom.input_text(field_selector, value, name=label, blur=False)
        time.sleep(1)
        matched = None
        for option in self.dom._find_eles(selectors.HS_CODE_OPTIONS, name=f"{label}选项"):
            if _hs_option_matches(str(getattr(option, "text", "") or ""), value):
                matched = option
                break
        if matched is None:
            raise ElementNotFoundError(f"{label}选项不存在：{value}")
        matched.click()
        self.dom.page.run_js("arguments[0].blur();", self.dom._find(field_selector, label))

    def _fill_cargo_field_if_changed(
        self: "FzSnlwySiTask",
        field_selector: str,
        label: str,
        content_key: str,
    ) -> None:
        """字段内容与预期不一致时重新填写。

        富文本先悬停并点清除；输入框和文本域由 input_text 清空。
        """
        expected_value = _text(self.content.get(content_key, ""))
        is_value_input = _is_value_input(field_selector)
        current_value = (
            self.dom.get_value(field_selector, label)
            if is_value_input
            else self.dom.get_text(field_selector, label)
        )
        if current_value == expected_value:
            return
        if not is_value_input and current_value and current_value.strip() != "请输入":
            self.dom._find(field_selector, label).hover()
            self.dom.click(
                selectors.cargo_content_selector(label, _CONTENT_CLEAR),
                f"清除{label}",
            )
        self.dom.input_text(field_selector, expected_value, name=label)

    def _verify_cargo_summary(self: "FzSnlwySiTask") -> None:
        """校验已填货物汇总字段，通过后从 remain_content 删除。"""
        for config in _CARGO_SUMMARY_FIELDS:
            label, key = config["label"], config["key"]
            if config.get("verify_only"):
                self.verify_page_value(
                    selector=selectors.cargo_content_text_selector(label),
                    field_path=key,
                    selector_type="text",
                    name=label,
                    skip_if_empty=True,
                )
                continue
            if config.get("select"):
                self._verify_cargo_select(config)
                continue
            if key not in self.content:
                self.mark_field_done(key)
                continue
            part = config["part"]
            selector_type = "value" if _is_value_input(part) else "text"
            self.verify_page_value(
                selector=selectors.cargo_content_selector(label, part),
                field_path=key,
                selector_type=selector_type,
                name=label,
            )

    def _verify_cargo_select(self: "FzSnlwySiTask", config: dict) -> None:
        """下拉展示文本包含下发值即通过，和收发通国家及地区一致。"""
        label, key = config["label"], config["key"]
        value = _text(self.content.get(key, "")).strip()
        if not value:
            self.mark_field_done(key)
            return
        actual = self.dom.get_text(
            selectors.cargo_content_selector(label, _SELECT_DISPLAY),
            label,
        )
        if value not in actual:
            raise FormValidationError(f"{label}校验失败，实际值：{actual}，期望值：{value}")
        self.mark_field_done(key)

    def _fill_containers(self: "FzSnlwySiTask") -> None:
        """点击添加箱，按 containers 逐箱填写后确定添加。"""
        containers = self.content.get("containers") or []
        if not containers:
            raise BusinessError("后台下发的集装箱信息为空")
        pending = [
            (index, container)
            for index, container in enumerate(containers)
            if not self._container_row_exists(_text(container.get("containerNo")).strip())
        ]
        if not pending:
            self._mark_containers_done(containers)
            return

        self.dom.scroll_to_see(selectors.ADD_CONTAINER_BTN, name="添加箱")
        self.dom.click(selectors.ADD_CONTAINER_BTN, name="添加箱")
        self.dom._find(selectors.CONTAINER_DIALOG, "添加箱信息")
        for offset, (index, container) in enumerate(pending):
            if offset:
                self.dom.click(selectors.DIALOG_ADD_CONTAINER_BTN, name=f"添加第{index + 1}个箱")
                time.sleep(0.5)
            self._fill_one_container(container, index)
        self._click_in_dialog(selectors.DIALOG_CONFIRM_BTN, "确定添加")
        self._continue_if_container_type_mismatch()
        for _ in range(10):
            if not self._container_dialog_visible():
                break
            time.sleep(0.3)
        else:
            raise FormValidationError("确定添加后箱信息弹窗未关闭")
        self._verify_container_rows(containers)

    def _container_dialog_visible(self: "FzSnlwySiTask") -> bool:
        """关闭后弹窗节点可能还在，真正隐藏的是外层遮罩。"""
        dialog = self.dom._find(
            selectors.CONTAINER_DIALOG,
            "添加箱信息",
            required=False,
            timeout=0.5,
        )
        if not dialog:
            return False
        return bool(dialog.run_js(
            "const overlay = this.closest('.el-overlay') || this;"
            "const style = getComputedStyle(overlay);"
            "return style.display !== 'none'"
            " && style.visibility !== 'hidden'"
            " && overlay.getClientRects().length > 0;"
        ))

    def _continue_if_container_type_mismatch(self: "FzSnlwySiTask") -> None:
        """尺寸箱型与系统不一致时，保留录入值并点继续。没有弹窗则跳过。"""
        continue_btn = self.dom._find(
            selectors.CONTAINER_TYPE_MISMATCH_CONTINUE,
            "尺寸箱型不符继续",
            required=False,
            timeout=2,
        )
        if continue_btn:
            self.dom.click(selectors.CONTAINER_TYPE_MISMATCH_CONTINUE, "继续")

    def _fill_one_container(self: "FzSnlwySiTask", container: dict, index: int) -> None:
        name = f"第{index + 1}个箱"
        for config in _CONTAINER_FIELDS:
            self._fill_dialog_field(container, config, name)
        if not _as_bool(container.get("isVgm")):
            return
        # VGM 字段折叠时没有布局，不能先读 is_displayed。
        self._click_in_dialog(selectors.DIALOG_VGM_BTN, f"{name}添加 VGM")
        time.sleep(0.5)
        for config in _VGM_FIELDS:
            self._fill_dialog_field(container, config, name)

    def _fill_dialog_field(self: "FzSnlwySiTask", container: dict, config: dict, name: str) -> None:
        label, key = config["label"], config["key"]
        value = _text(container.get(key, "")).strip()
        if not value:
            return
        field_name = f"{name}{label}"
        selector = selectors.container_dialog_selector(
            label,
            config.get("select") and _SELECT_INPUT or config["part"],
        )
        self._scroll_dialog_field(selector, field_name)
        if config.get("select"):
            self._fill_dialog_select(label, value, field_name, config.get("search", False))
            return
        if config.get("date"):
            self.dom.input_text(selector, value, name=field_name, blur=False)
            self.dom._find(selector, field_name).input(Keys.ENTER)
            return
        self.dom.input_text(selector, value, name=field_name)

    def _fill_dialog_select(
        self: "FzSnlwySiTask",
        label: str,
        value: str,
        field_name: str,
        search: bool,
    ) -> None:
        display = self.dom.get_text(
            selectors.container_dialog_selector(label, _SELECT_DISPLAY),
            field_name,
        )
        if value in display and "请选择" not in display:
            return
        field_selector = selectors.container_dialog_selector(label, _SELECT_INPUT)
        if not search:
            self.dom.select_by_word(
                field_selector,
                value,
                selectors.ELEMENT_SELECT_OPTIONS,
                name=field_name,
            )
            return
        self.dom.input_text(field_selector, value, name=field_name, blur=False)
        time.sleep(1)
        if self._click_exact_option(value):
            self.dom.page.run_js("arguments[0].blur();", self.dom._find(field_selector, field_name))
            return
        self.dom._find(field_selector, field_name).input(Keys.ENTER)

    def _click_exact_option(self: "FzSnlwySiTask", value: str) -> bool:
        for option in self.dom._find_eles(
            selectors.ELEMENT_SELECT_OPTIONS,
            name="下拉选项",
            required=False,
            timeout=5,
        ) or []:
            text = str(getattr(option, "text", "") or "").strip()
            if text == value and _option_visible(option):
                option.click()
                return True
        return False

    def _scroll_dialog_field(self: "FzSnlwySiTask", selector: str, name: str) -> None:
        """弹窗内部滚动，避免折叠或视口外元素没有位置。"""
        element = self.dom._find(selector, name)
        element.run_js("this.scrollIntoView({block:'center', inline:'nearest'})")

    def _click_in_dialog(self: "FzSnlwySiTask", selector: str, name: str) -> None:
        element = self.dom._find(selector, name)
        element.run_js("this.scrollIntoView({block:'center', inline:'nearest'})")
        time.sleep(0.2)
        try:
            self.dom.click(selector, name)
        except NoRectError:
            element.click(by_js=True)

    def _container_row_exists(self: "FzSnlwySiTask", container_no: str) -> bool:
        if not container_no:
            return False
        return bool(self.dom._find(
            selectors.container_row_selector(container_no),
            container_no,
            required=False,
            timeout=1,
        ))

    def _verify_container_rows(self: "FzSnlwySiTask", containers: list[dict]) -> None:
        """按页面实际展示校验箱详情和 VGM，通过后删除剩余字段。"""
        self.dom.click(selectors.CNTR_TAB, "箱详情")
        for index, container in enumerate(containers):
            self._verify_cntr_tab_row(container, index)
        if any(_as_bool(container.get("isVgm")) for container in containers):
            self.dom.click(selectors.VGM_TAB, "VGM")
            time.sleep(0.5)
            for index, container in enumerate(containers):
                if _as_bool(container.get("isVgm")):
                    self._verify_vgm_tab_row(container, index)
            self.dom.click(selectors.CNTR_TAB, "箱详情")
        self._mark_containers_done(containers)

    def _container_row_cells(self: "FzSnlwySiTask", container_no: str, name: str) -> dict[str, str]:
        headers = self.dom._find_eles(
            "x://*[contains(@class,'cntr-card')]"
            "//*[contains(@class,'el-table__header-wrapper')][1]//th",
            "箱信息表头",
        )
        row = self.dom._find(selectors.container_row_selector(container_no), name, timeout=5)
        names = [str(getattr(header, "text", "") or "").strip() for header in headers]
        values = [str(getattr(cell, "text", "") or "").strip() for cell in row.eles("css:td")]
        return dict(zip(names, values))

    def _verify_cntr_tab_row(self: "FzSnlwySiTask", container: dict, index: int) -> None:
        """箱详情列：箱号和铅封号同格，尺寸箱型拼成 20RH，体积保留 3 位小数。"""
        name = f"第{index + 1}个箱"
        container_no = _text(container.get("containerNo")).strip()
        if not container_no:
            raise FormValidationError(f"{name}缺少箱号")
        cells = self._container_row_cells(container_no, name)
        number_cell = self._require_container_cell(cells, "箱号/铅封号", name)
        if container_no not in number_cell:
            raise FormValidationError(f"{name}箱号校验失败，实际值：{number_cell}，期望值：{container_no}")
        seal_no = _text(container.get("sealNo")).strip()
        if seal_no and seal_no not in number_cell:
            raise FormValidationError(f"{name}铅封号校验失败，实际值：{number_cell}，期望值：{seal_no}")

        type_value = _text(container.get("splitContainerType")).strip()
        type_code = type_value.split("-", 1)[0]
        size = _text(container.get("containerSize")).strip()
        expected_type = f"{size}{type_code}"
        actual_type = self._require_container_cell(cells, "尺寸箱型", name).replace(" ", "")
        if expected_type and expected_type not in actual_type:
            raise FormValidationError(
                f"{name}尺寸箱型校验失败，实际值：{actual_type}，期望值：{expected_type}"
            )
        self._require_same_cell(cells, "箱经营人", _text(container.get("soc")), name, numeric=False)
        self._require_same_cell(cells, "箱状态", _text(container.get("containerStatus")), name, numeric=False)
        self._require_same_cell(cells, "箱内件数", _text(container.get("packages")), name)
        self._require_same_cell(cells, "毛重(KGS)", _text(container.get("grossWeight")), name)
        self._require_same_cell(cells, "体积(CBM)", _text(container.get("volume")), name)

    def _verify_vgm_tab_row(self: "FzSnlwySiTask", container: dict, index: int) -> None:
        """VGM 列：箱总重显示为 3 位小数，时间和签名按原文比对。"""
        name = f"第{index + 1}个箱"
        container_no = _text(container.get("containerNo")).strip()
        cells = self._container_row_cells(container_no, name)
        self._require_same_cell(cells, "VGM箱重(KGS)", _text(container.get("weight")), name)
        self._require_same_cell(cells, "称重方法", _text(container.get("method")), name, numeric=False)
        self._require_same_cell(cells, "VGM称重时间", _text(container.get("weightingDate")), name, numeric=False)
        self._require_same_cell(cells, "VGM称重地点", _text(container.get("weightingPlace")), name, numeric=False)
        self._require_same_cell(cells, "VGM签名验证", _text(container.get("signature")), name, numeric=False)

    def _require_container_cell(self: "FzSnlwySiTask", cells: dict, header: str, name: str) -> str:
        if header not in cells:
            raise FormValidationError(f"{name}缺少列：{header}，实际列：{list(cells)}")
        return cells[header]

    def _require_same_cell(
        self: "FzSnlwySiTask",
        cells: dict,
        header: str,
        expected: str,
        name: str,
        *,
        numeric: bool = True,
    ) -> None:
        expected = expected.strip()
        if not expected:
            return
        actual = self._require_container_cell(cells, header, name)
        matched = actual == expected or (numeric and _same_amount(expected, actual))
        if not matched:
            raise FormValidationError(f"{name}{header}校验失败，实际值：{actual}，期望值：{expected}")

    def _mark_containers_done(self: "FzSnlwySiTask", containers: list[dict]) -> None:
        keys = [config["key"] for config in (*_CONTAINER_FIELDS, *_VGM_FIELDS)]
        keys.extend(("isVgm", "containerStatus"))
        for index in range(len(containers)):
            for key in keys:
                self.mark_field_done(["containers", index, key])
