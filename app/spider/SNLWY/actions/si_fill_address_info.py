"""SNLWY SI 收发通地址填写。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.core.task.errors import FormValidationError
from app.spider.SNLWY import selectors

if TYPE_CHECKING:
    from app.spider.SNLWY.tasks.fz_snlwy_si import FzSnlwySiTask

_SHOW_ON_BL = "提单中显示"
_SELECT_INPUT = "*[contains(@class,'el-select__input')]"
_CONTENT_PART = "*[contains(@class,'cm-content')]"
_CONTENT_CLEAR = "*[contains(@class,'textarea-clear-icon')]"
_INPUT_PART = "*[contains(@class,'el-input__inner')]"
_EMAIL_PART = "*[contains(@class,'editable-input-tag-wrapper')]"
_EMAIL_CLEAR = "*[contains(@class,'editable-input-tag__clear')]"

# TO ORDER 勾选后，收货人其余字段会隐藏或不可编辑。
_TO_ORDER_CONSIGNEE_KEYS = frozenset({
    "consigneeTitle",
    "consigneeAddress",
    "consigneeAddressShowOnBl",
})

_TRUE_TEXTS = {"1", "true", "yes", "y"}
_FALSE_TEXTS = {"0", "false", "no", "n", ""}


_EMAIL_SEPARATORS = re.compile(r"[,，]+")
_PAGE_EMAIL_SPLIT = re.compile(r"[\s,，×✕✖]+")


def _split_email_value(value) -> list[str]:
    """下发邮箱是逗号分隔字符串。"""
    text = "" if value is None else str(value)
    return [part.strip() for part in _EMAIL_SEPARATORS.split(text) if part.strip()]


def _emails_from_page_text(text: str) -> list[str]:
    """从标签展示文本中抽出邮箱，忽略关闭按钮和空白。"""
    return [
        part.strip()
        for part in _PAGE_EMAIL_SPLIT.split(text or "")
        if part.strip() and "@" in part
    ]


def _same_emails(expected, page_text: str) -> bool:
    expected_emails = [item.casefold() for item in _split_email_value(expected)]
    actual_emails = [item.casefold() for item in _emails_from_page_text(page_text)]
    return expected_emails == actual_emails


def _as_bool(value) -> bool:
    """解析下发布尔值，兼容 true/false 字符串。"""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_TEXTS:
            return True
        if normalized in _FALSE_TEXTS:
            return False
    return bool(value)


def _show_on_bl_field(section: str, label: str, key_prefix: str) -> dict:
    return {
        "section": section,
        "label": label,
        "key": f"{key_prefix}ShowOnBl",
        "checkbox": _SHOW_ON_BL,
    }


def _party_fields(section: str, prefix: str, title_label: str, *, show_on_bl: bool) -> list[dict]:
    """生成一个收发通区块的填单配置。第二通知人没有「提单中显示」。"""
    fields: list[dict] = [
        {"section": section, "label": title_label, "key": f"{prefix}Title"},
        {"section": section, "label": "地址", "key": f"{prefix}Address"},
    ]
    if show_on_bl:
        fields.append(_show_on_bl_field(section, "地址", f"{prefix}Address"))

    for label, suffix in (("电话", "Tel"), ("传真", "Fax"), ("邮箱", "Email")):
        field = {"section": section, "label": label, "key": f"{prefix}{suffix}"}
        if suffix == "Email":
            field["part"] = _EMAIL_PART
            field["clear"] = _EMAIL_CLEAR
        fields.append(field)
        if show_on_bl:
            fields.append(_show_on_bl_field(section, label, f"{prefix}{suffix}"))

    fields.extend((
        {"section": section, "label": "省份", "key": f"{prefix}Province"},
        {"section": section, "label": "城市", "key": f"{prefix}City"},
        {"section": section, "label": "邮编", "key": f"{prefix}ZipCode"},
        {
            "section": section,
            "label": "国家及地区",
            "key": f"{prefix}Country",
            "select": _SELECT_INPUT,
        },
        {
            "section": section,
            "label": "企业唯一识别码",
            "key": f"{prefix}AbbreviationCode",
            "select": _SELECT_INPUT,
            "options": selectors.ELEMENT_SELECT_OPTIONS,
        },
        {
            "section": section,
            "label": "企业唯一识别码",
            "key": f"{prefix}EnterpriseCode",
            "part": "*[contains(@class,'el-input__inner')]",
            "from_parent": True,
        },
    ))
    return fields


_PARTY_FIELDS = {
    "发货人信息": _party_fields("发货人信息", "shipper", "发货人名称", show_on_bl=True),
    "收货人信息": _party_fields("收货人信息", "consignee", "收货人名称", show_on_bl=True),
    "通知人信息": _party_fields("通知人信息", "notify", "通知方名称", show_on_bl=True),
    "第二通知人": _party_fields("第二通知人", "secondNotify", "通知方名称", show_on_bl=False),
}
_SELECT_DISPLAY = "*[contains(@class,'el-select')]"


def _consignee_fields(to_order: bool) -> list[dict]:
    """TO ORDER 勾选时只保留仍可填写的收货人字段。

    勾选后收货人名称由富文本 cm-content 变为 el-input__inner。
    """
    fields = _PARTY_FIELDS["收货人信息"]
    if not to_order:
        return fields
    result = []
    for field in fields:
        if field["key"] not in _TO_ORDER_CONSIGNEE_KEYS:
            continue
        if field["key"] == "consigneeTitle":
            field = {**field, "part": _INPUT_PART}
        result.append(field)
    return result


def _skipped_consignee_fields() -> list[dict]:
    return [
        field for field in _PARTY_FIELDS["收货人信息"]
        if field["key"] not in _TO_ORDER_CONSIGNEE_KEYS
    ]


class SiFillAddressInfoMixin:
    """封装 Shipper、Consignee、Notify 等地址信息。"""

    def _fill_address_info(self: "FzSnlwySiTask") -> None:
        """填写收发通地址，并按开关同步三个区块复选框。"""
        to_order = _as_bool(self.content.get("toOrder"))
        same_as_consignee = _as_bool(self.content.get("sameAsConsignee"))
        show_second_notify = _as_bool(self.content.get("isShowSecondNotify"))

        self._fill_party_fields(_PARTY_FIELDS["发货人信息"])

        self._set_checkbox_if_needed(selectors.TO_ORDER_CHECK, "TO ORDER", to_order)
        self._fill_party_fields(_consignee_fields(to_order))

        # TO ORDER 勾选后，页面会自动取消并置灰 SAME AS CONSIGNEE。
        if not to_order:
            self._set_checkbox_if_needed(
                selectors.SAMEASCONSIGNEE_CHECK,
                "SAME AS CONSIGNEE",
                same_as_consignee,
            )
        self._fill_party_fields(_PARTY_FIELDS["通知人信息"])

        self._set_checkbox_if_needed(
            selectors.SECOND_NOTIFY_CHECK,
            "第二通知人",
            show_second_notify,
        )
        if show_second_notify:
            self._fill_party_fields(_PARTY_FIELDS["第二通知人"])

        self._verify_address_info(to_order, same_as_consignee, show_second_notify)

    def _verify_address_info(
        self: "FzSnlwySiTask",
        to_order: bool,
        same_as_consignee: bool,
        show_second_notify: bool,
    ) -> None:
        """校验已填页面值，通过后从 remain_content 删除对应字段。"""
        self._verify_party_fields(_PARTY_FIELDS["发货人信息"])
        self._verify_party_fields(_consignee_fields(to_order))
        if to_order:
            self._mark_fields_done(_skipped_consignee_fields())
        self._verify_party_fields(_PARTY_FIELDS["通知人信息"])
        if show_second_notify:
            self._verify_party_fields(_PARTY_FIELDS["第二通知人"])
        else:
            self._mark_fields_done(_PARTY_FIELDS["第二通知人"])

        self._verify_checkbox(selectors.TO_ORDER_CHECK, "TO ORDER", to_order, "toOrder")
        # TO ORDER 勾选后页面会强制取消 SAME AS CONSIGNEE。
        self._verify_checkbox(
            selectors.SAMEASCONSIGNEE_CHECK,
            "SAME AS CONSIGNEE",
            False if to_order else same_as_consignee,
            "sameAsConsignee",
        )
        self._verify_checkbox(
            selectors.SECOND_NOTIFY_CHECK,
            "第二通知人",
            show_second_notify,
            "isShowSecondNotify",
        )

    def _verify_party_fields(self: "FzSnlwySiTask", fields: list[dict]) -> None:
        for config in fields:
            self._verify_configured_field(config)

    def _verify_configured_field(self: "FzSnlwySiTask", config: dict) -> None:
        section, label, key = config["section"], config["label"], config["key"]
        name = f"{section}{label}"
        if config.get("checkbox"):
            value = self.content.get(key)
            if value is None:
                self.mark_field_done(key)
                return
            self._verify_checkbox(
                selectors.customer_info_selector(
                    section,
                    label,
                    f"label[normalize-space()='{config['checkbox']}']",
                ),
                f"{name}{config['checkbox']}",
                bool(value),
                key,
            )
            return

        if config.get("select"):
            value = self.content.get(key, "")
            if not value:
                self.mark_field_done(key)
                self._mark_country_code_done(label, key)
                return
            actual = self.dom.get_text(
                selectors.customer_info_selector(section, label, _SELECT_DISPLAY),
                name=name,
            )
            if str(value) not in actual:
                raise FormValidationError(f"{name}校验失败，实际值：{actual}，期望值：{value}")
            self.mark_field_done(key)
            self._mark_country_code_done(label, key)
            return

        if key not in self.content:
            self.mark_field_done(key)
            return
        part = config.get("part", _CONTENT_PART)
        if "editable-input-tag" in part:
            self._verify_email_field(config, name)
            return
        selector_type = "value" if "el-input__inner" in part else "text"
        self.verify_page_value(
            selector=selectors.customer_info_selector(
                section,
                label,
                part,
                config.get("from_parent", False),
            ),
            field_path=key,
            selector_type=selector_type,
            name=name,
        )

    def _mark_country_code_done(self: "FzSnlwySiTask", label: str, key: str) -> None:
        """国家及地区校验完成后，顺带删除对应的国家代码。"""
        if label != "国家及地区":
            return
        self.mark_field_done(f"{key}Code")

    def _verify_email_field(self: "FzSnlwySiTask", config: dict, name: str) -> None:
        """页面按标签展示邮箱，下发值是逗号分隔字符串。"""
        key = config["key"]
        selector = selectors.customer_info_selector(
            config["section"],
            config["label"],
            config.get("part", _EMAIL_PART),
            config.get("from_parent", False),
        )
        expected = self.content.get(key, "")
        actual = self.dom.get_text(selector, name)
        if not _same_emails(expected, actual):
            raise FormValidationError(f"{name}校验失败，实际值：{actual}，期望值：{expected}")
        self.mark_field_done(key)

    def _verify_checkbox(
        self: "FzSnlwySiTask",
        selector: str,
        label: str,
        expected: bool,
        field_path: str,
    ) -> None:
        """按 Element Plus 的 is-checked 校验复选框，通过后删除剩余字段。"""
        actual = self._is_checkbox_checked(selector, label)
        if actual != expected:
            raise FormValidationError(f"{label}校验失败，实际值：{actual}，期望值：{expected}")
        self.mark_field_done(field_path)

    def _mark_fields_done(self: "FzSnlwySiTask", fields: list[dict]) -> None:
        """页面上无需填写的字段直接从 remain_content 移除。"""
        for config in fields:
            self.mark_field_done(config["key"])

    def _fill_party_fields(self: "FzSnlwySiTask", fields: list[dict]) -> None:
        for config in fields:
            self._fill_configured_field(config)

    def _fill_configured_field(self: "FzSnlwySiTask", config: dict) -> None:
        section, label, key = config["section"], config["label"], config["key"]
        checkbox = config.get("checkbox")
        select = config.get("select")
        if checkbox:
            value = self.content.get(key)
            if value is not None:
                self._set_checkbox_if_needed(
                    selectors.customer_info_selector(
                        section,
                        label,
                        f"label[normalize-space()='{checkbox}']",
                    ),
                    f"{label}{checkbox}",
                    bool(value),
                )
            return

        if select:
            value = self.content.get(key, "")
            if value:
                self.dom.select_by_word(
                    selectors.customer_info_selector(section, label, select),
                    value,
                    config.get("options", selectors.COUNTRY_OPTIONS),
                    name=label,
                )
            return

        self._fill_field_if_changed(
            selectors.customer_info_selector(
                section,
                label,
                config.get("part", _CONTENT_PART),
                config.get("from_parent", False),
            ),
            selectors.customer_info_selector(section, label, config.get("clear", _CONTENT_CLEAR)),
            label,
            key,
        )

    def _fill_field_if_changed(
        self: "FzSnlwySiTask",
        field_selector: str,
        clear_selector: str,
        label: str,
        content_key: str,
    ) -> None:
        """字段内容与预期不一致时，悬停、清除后重新填写。"""
        expected_value = self.content.get(content_key, "")
        is_input = "el-input__inner" in field_selector
        is_email = "editable-input-tag" in field_selector
        current_value = (
            self.dom.get_value(field_selector, label)
            if is_input
            else self.dom.get_text(field_selector, label)
        )
        changed = (
            not _same_emails(expected_value, current_value)
            if is_email
            else current_value != expected_value
        )
        if changed:
            # 输入框由 input_text 按 el-input__inner 清空，没有富文本清除按钮。
            if not is_input and current_value and current_value.strip() != "请输入":
                self.dom._find(field_selector, label).hover()
                self.dom.click(clear_selector, f"清除{label}")
            self.dom.input_text(field_selector, expected_value)
