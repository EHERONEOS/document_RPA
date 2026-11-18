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
_SELECT_DISPLAY = "*[contains(@class,'el-select')]"
_CONTENT_PART = "*[contains(@class,'cm-content')]"
_CONTENT_CLEAR = "*[contains(@class,'textarea-clear-icon')]"
_INPUT_PART = "*[contains(@class,'el-input__inner')]"
_EMAIL_PART = "*[contains(@class,'editable-input-tag-wrapper')]"
_EMAIL_CLEAR = "*[contains(@class,'editable-input-tag__clear')]"

_TRUE_TEXTS = {"1", "true", "yes", "y"}
_FALSE_TEXTS = {"0", "false", "no", "n", ""}


_EMAIL_SEPARATORS = re.compile(r"[,，]+")
# 仅去掉邮箱前、以中英文冒号结尾的标签，避免吞掉含 @ 的邮箱内容。
_EMAIL_PREFIX = re.compile(r"^[^@,，]*[:：]\s*")
_PAGE_EMAIL_SPLIT = re.compile(r"[\s,，×✕✖]+")


def _split_email_value(value) -> list[str]:
    """下发邮箱是逗号分隔字符串，每项可带任意「标签:」前缀。"""
    text = "" if value is None else str(value)
    return [_EMAIL_PREFIX.sub("", part.strip())
            for part in _EMAIL_SEPARATORS.split(text) if part.strip()]


def _emails_from_page_text(text: str) -> list[str]:
    """从标签展示文本中抽出邮箱，忽略关闭按钮和空白。"""
    return [
        _EMAIL_PREFIX.sub("", part.strip())
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


class SiFillAddressInfoMixin:
    """封装 Shipper、Consignee、Notify 等地址信息。"""

    def _fill_address_info(self: "FzSnlwySiTask") -> None:
        """按页面顺序逐项填写；联动分支在对应字段前处理，最后统一校验。"""
        to_order = _as_bool(self.content.get("toOrder"))
        same_as_consignee = _as_bool(self.content.get("sameAsConsignee"))
        show_second_notify = _as_bool(self.content.get("isShowSecondNotify"))

        # 1. 发货人：名称 → 地址 → 联系方式 → 地区 → 企业识别码。
        self._fill_rich_text("发货人信息", "发货人名称", "shipperTitle")
        self._fill_rich_text("发货人信息", "地址", "shipperAddress")
        self._fill_show_on_bl("发货人信息", "地址", "shipperAddressShowOnBl")
        self._fill_rich_text("发货人信息", "电话", "shipperTel")
        self._fill_show_on_bl("发货人信息", "电话", "shipperTelShowOnBl")
        self._fill_rich_text("发货人信息", "传真", "shipperFax")
        self._fill_show_on_bl("发货人信息", "传真", "shipperFaxShowOnBl")
        self._fill_email("发货人信息", "邮箱", "shipperEmail")
        self._fill_show_on_bl("发货人信息", "邮箱", "shipperEmailShowOnBl")
        self._fill_rich_text("发货人信息", "省份", "shipperProvince")
        self._fill_rich_text("发货人信息", "城市", "shipperCity")
        self._fill_rich_text("发货人信息", "邮编", "shipperZipCode")
        self._fill_address_select("发货人信息", "国家及地区", "shipperCountry")
        self._fill_address_select("发货人信息", "企业唯一识别码", "shipperAbbreviationCode", options=selectors.ELEMENT_SELECT_OPTIONS)
        self._fill_address_input("发货人信息", "企业唯一识别码", "shipperEnterpriseCode", from_parent=True)

        # 2. 收货人：先同步 TO ORDER，勾选后名称变为普通输入框。
        self._set_checkbox_if_needed(selectors.TO_ORDER_CHECK, "TO ORDER", to_order)
        self._fill_rich_text("收货人信息", "收货人名称", "consigneeTitle")
        self._fill_rich_text("收货人信息", "地址", "consigneeAddress")
        self._fill_show_on_bl("收货人信息", "地址", "consigneeAddressShowOnBl")

        # TO ORDER 下其余收货人字段隐藏或不可编辑，无需填写。
        if not to_order:
            self._fill_rich_text("收货人信息", "电话", "consigneeTel")
            self._fill_show_on_bl("收货人信息", "电话", "consigneeTelShowOnBl")
            self._fill_rich_text("收货人信息", "传真", "consigneeFax")
            self._fill_show_on_bl("收货人信息", "传真", "consigneeFaxShowOnBl")
            self._fill_email("收货人信息", "邮箱", "consigneeEmail")
            self._fill_show_on_bl("收货人信息", "邮箱", "consigneeEmailShowOnBl")
            self._fill_rich_text("收货人信息", "省份", "consigneeProvince")
            self._fill_rich_text("收货人信息", "城市", "consigneeCity")
            self._fill_rich_text("收货人信息", "邮编", "consigneeZipCode")
            self._fill_address_select("收货人信息", "国家及地区", "consigneeCountry")
            self._fill_address_select("收货人信息", "企业唯一识别码", "consigneeAbbreviationCode", options=selectors.ELEMENT_SELECT_OPTIONS)
            self._fill_address_input("收货人信息", "企业唯一识别码", "consigneeEnterpriseCode", from_parent=True)

        # 3. 通知人：TO ORDER 会强制取消并置灰 SAME AS CONSIGNEE。
        if not to_order:
            self._set_checkbox_if_needed(
                selectors.SAMEASCONSIGNEE_CHECK,
                "SAME AS CONSIGNEE",
                same_as_consignee,
            )
        # 同收货人时由页面自动带出；否则逐项填写通知人。
        if not same_as_consignee:
            self._fill_rich_text("通知人信息", "通知方名称", "notifyTitle")
            self._fill_rich_text("通知人信息", "地址", "notifyAddress")
            self._fill_show_on_bl("通知人信息", "地址", "notifyAddressShowOnBl")
            self._fill_rich_text("通知人信息", "电话", "notifyTel")
            self._fill_show_on_bl("通知人信息", "电话", "notifyTelShowOnBl")
            self._fill_rich_text("通知人信息", "传真", "notifyFax")
            self._fill_show_on_bl("通知人信息", "传真", "notifyFaxShowOnBl")
            self._fill_email("通知人信息", "邮箱", "notifyEmail")
            self._fill_show_on_bl("通知人信息", "邮箱", "notifyEmailShowOnBl")
            self._fill_rich_text("通知人信息", "省份", "notifyProvince")
            self._fill_rich_text("通知人信息", "城市", "notifyCity")
            self._fill_rich_text("通知人信息", "邮编", "notifyZipCode")
            self._fill_address_select("通知人信息", "国家及地区", "notifyCountry")
            self._fill_address_select("通知人信息", "企业唯一识别码", "notifyAbbreviationCode", options=selectors.ELEMENT_SELECT_OPTIONS)
            self._fill_address_input("通知人信息", "企业唯一识别码", "notifyEnterpriseCode", from_parent=True)

        # 4. 第二通知人：先同步显示开关，启用后填写，不包含提单显示选项。
        self._set_checkbox_if_needed(
            selectors.SECOND_NOTIFY_CHECK,
            "第二通知人",
            show_second_notify,
        )
        if show_second_notify:
            self._fill_rich_text("第二通知人", "通知方名称", "secondNotifyTitle")
            self._fill_rich_text("第二通知人", "地址", "secondNotifyAddress")
            self._fill_rich_text("第二通知人", "电话", "secondNotifyTel")
            self._fill_rich_text("第二通知人", "传真", "secondNotifyFax")
            self._fill_email("第二通知人", "邮箱", "secondNotifyEmail")
            self._fill_rich_text("第二通知人", "省份", "secondNotifyProvince")
            self._fill_rich_text("第二通知人", "城市", "secondNotifyCity")
            self._fill_rich_text("第二通知人", "邮编", "secondNotifyZipCode")
            self._fill_address_select("第二通知人", "国家及地区", "secondNotifyCountry")
            self._fill_address_select("第二通知人", "企业唯一识别码", "secondNotifyAbbreviationCode", options=selectors.ELEMENT_SELECT_OPTIONS)
            self._fill_address_input("第二通知人", "企业唯一识别码", "secondNotifyEnterpriseCode", from_parent=True)

        # 5. 统一校验字段和开关，按原有规则移除已处理及隐藏字段。
        self._verify_address_info(to_order, same_as_consignee, show_second_notify)

    def _fill_rich_text(
        self: "FzSnlwySiTask", section: str, label: str, key: str,
        *, part: str = _CONTENT_PART, clear: str = _CONTENT_CLEAR,
        from_parent: bool = False,
    ) -> None:
        """内容不同时清空重填，默认按富文本读取并保留原始空白。"""
        self._fill_field_if_changed(
            selectors.customer_info_selector(section, label, part, from_parent),
            selectors.customer_info_selector(section, label, clear),
            f"{section}{label}",
            key,
        )

    def _fill_address_input(
        self: "FzSnlwySiTask", section: str, label: str, key: str,
        *, from_parent: bool = False,
    ) -> None:
        """普通输入框使用 value 比较，并由 input_text 清空。"""
        self._fill_rich_text(section, label, key, part=_INPUT_PART, from_parent=from_parent)

    def _fill_email(self: "FzSnlwySiTask", section: str, label: str, key: str) -> None:
        """邮箱按标签内容比较，兼容逗号分隔值及邮箱标签前缀。"""
        self._fill_rich_text(section, label, key, part=_EMAIL_PART, clear=_EMAIL_CLEAR)

    def _fill_show_on_bl(self: "FzSnlwySiTask", section: str, label: str, key: str) -> None:
        """仅在下发值非 None 时同步「提单中显示」。"""
        value = self.content.get(key)
        if value is not None:
            self._set_checkbox_if_needed(
                selectors.customer_info_selector(
                    section, label, f"label[normalize-space()='{_SHOW_ON_BL}']",
                ),
                f"{section}{label}{_SHOW_ON_BL}",
                _as_bool(value),
            )

    def _fill_address_select(
        self: "FzSnlwySiTask", section: str, label: str, key: str,
        *, options: str = selectors.COUNTRY_OPTIONS,
    ) -> None:
        """仅在下发值非空时选择国家或企业识别码类型。"""
        value = self.content.get(key, "")
        if value:
            self.dom.select_by_word(
                selectors.customer_info_selector(section, label, _SELECT_INPUT),
                value,
                options,
                name=f"{section}{label}",
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
        if is_input:
            current_value = self.dom.get_value(field_selector, label)
        elif is_email:
            current_value = self.dom.get_text(field_selector, label)
        else:
            current_value = self.dom.get_raw_text(field_selector, label)
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
            self.dom.input_text(field_selector, expected_value, name=label)

    def _verify_address_info(
        self: "FzSnlwySiTask",
        to_order: bool,
        same_as_consignee: bool,
        show_second_notify: bool,
    ) -> None:
        """校验已填页面值，通过后从 remain_content 删除对应字段。"""
        # 1. 发货人：按填写顺序逐字段校验。
        self._verify_address_text("发货人信息", "发货人名称", "shipperTitle")
        self._verify_address_text("发货人信息", "地址", "shipperAddress")
        self._verify_show_on_bl("发货人信息", "地址", "shipperAddressShowOnBl")
        self._verify_address_text("发货人信息", "电话", "shipperTel")
        self._verify_show_on_bl("发货人信息", "电话", "shipperTelShowOnBl")
        self._verify_address_text("发货人信息", "传真", "shipperFax")
        self._verify_show_on_bl("发货人信息", "传真", "shipperFaxShowOnBl")
        self._verify_address_email("发货人信息", "邮箱", "shipperEmail")
        self._verify_show_on_bl("发货人信息", "邮箱", "shipperEmailShowOnBl")
        self._verify_address_text("发货人信息", "省份", "shipperProvince")
        self._verify_address_text("发货人信息", "城市", "shipperCity")
        self._verify_address_text("发货人信息", "邮编", "shipperZipCode")
        self._verify_address_select("发货人信息", "国家及地区", "shipperCountry")
        self._verify_address_select("发货人信息", "企业唯一识别码", "shipperAbbreviationCode")
        self._verify_address_input("发货人信息", "企业唯一识别码", "shipperEnterpriseCode", from_parent=True)

        # 2. 收货人：
        self._verify_address_text("收货人信息", "收货人名称", "consigneeTitle")
        self._verify_address_text("收货人信息", "地址", "consigneeAddress")
        self._verify_show_on_bl("收货人信息", "地址", "consigneeAddressShowOnBl")

        # 未开启 TO ORDER 时，继续校验联系方式、地区和企业识别码。
        if not to_order:
            self._verify_address_text("收货人信息", "电话", "consigneeTel")
            self._verify_show_on_bl("收货人信息", "电话", "consigneeTelShowOnBl")
            self._verify_address_text("收货人信息", "传真", "consigneeFax")
            self._verify_show_on_bl("收货人信息", "传真", "consigneeFaxShowOnBl")
            self._verify_address_email("收货人信息", "邮箱", "consigneeEmail")
            self._verify_show_on_bl("收货人信息", "邮箱", "consigneeEmailShowOnBl")
            self._verify_address_text("收货人信息", "省份", "consigneeProvince")
            self._verify_address_text("收货人信息", "城市", "consigneeCity")
            self._verify_address_text("收货人信息", "邮编", "consigneeZipCode")
            self._verify_address_select("收货人信息", "国家及地区", "consigneeCountry")
            self._verify_address_select("收货人信息", "企业唯一识别码", "consigneeAbbreviationCode")
            self._verify_address_input("收货人信息", "企业唯一识别码", "consigneeEnterpriseCode", from_parent=True)

        # 3. 通知人：同收货人时只校验只读名称，其余字段隐藏。
        if not same_as_consignee:
            self._verify_address_text("通知人信息", "通知方名称", "notifyTitle")
            self._verify_address_text("通知人信息", "地址", "notifyAddress")
            self._verify_show_on_bl("通知人信息", "地址", "notifyAddressShowOnBl")
            self._verify_address_text("通知人信息", "电话", "notifyTel")
            self._verify_show_on_bl("通知人信息", "电话", "notifyTelShowOnBl")
            self._verify_address_text("通知人信息", "传真", "notifyFax")
            self._verify_show_on_bl("通知人信息", "传真", "notifyFaxShowOnBl")
            self._verify_address_email("通知人信息", "邮箱", "notifyEmail")
            self._verify_show_on_bl("通知人信息", "邮箱", "notifyEmailShowOnBl")
            self._verify_address_text("通知人信息", "省份", "notifyProvince")
            self._verify_address_text("通知人信息", "城市", "notifyCity")
            self._verify_address_text("通知人信息", "邮编", "notifyZipCode")
            self._verify_address_select("通知人信息", "国家及地区", "notifyCountry")
            self._verify_address_select("通知人信息", "企业唯一识别码", "notifyAbbreviationCode")
            self._verify_address_input("通知人信息", "企业唯一识别码", "notifyEnterpriseCode", from_parent=True)
        else:
            self.mark_field_done("notifyTitle")

        # 4. 第二通知人：仅在启用时逐字段校验。
        if show_second_notify:
            self._verify_address_text("第二通知人", "通知方名称", "secondNotifyTitle")
            self._verify_address_text("第二通知人", "地址", "secondNotifyAddress")
            self._verify_address_text("第二通知人", "电话", "secondNotifyTel")
            self._verify_address_text("第二通知人", "传真", "secondNotifyFax")
            self._verify_address_email("第二通知人", "邮箱", "secondNotifyEmail")
            self._verify_address_text("第二通知人", "省份", "secondNotifyProvince")
            self._verify_address_text("第二通知人", "城市", "secondNotifyCity")
            self._verify_address_text("第二通知人", "邮编", "secondNotifyZipCode")
            self._verify_address_select("第二通知人", "国家及地区", "secondNotifyCountry")
            self._verify_address_select("第二通知人", "企业唯一识别码", "secondNotifyAbbreviationCode")
            self._verify_address_input("第二通知人", "企业唯一识别码", "secondNotifyEnterpriseCode", from_parent=True)


        # 5. 校验三个联动开关的最终页面状态。
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

    def _verify_address_text(
        self: "FzSnlwySiTask", section: str, label: str, key: str,
        *, part: str = _CONTENT_PART, selector_type: str = "raw_text",
        from_parent: bool = False,
    ) -> None:
        """校验文本；未下发字段按原有规则标记完成。"""
        if key not in self.content:
            self.mark_field_done(key)
            return
        self.verify_page_value(
            selector=selectors.customer_info_selector(section, label, part, from_parent),
            field_path=key,
            selector_type=selector_type,
            name=f"{section}{label}",
        )

    def _verify_address_input(
        self: "FzSnlwySiTask", section: str, label: str, key: str,
        *, from_parent: bool = False,
    ) -> None:
        """普通输入框按 value 校验。"""
        self._verify_address_text(
            section, label, key, part=_INPUT_PART,
            selector_type="value", from_parent=from_parent,
        )

    def _verify_address_email(
        self: "FzSnlwySiTask", section: str, label: str, key: str,
    ) -> None:
        """邮箱标签按规范化后的邮箱列表校验。"""
        if key not in self.content:
            self.mark_field_done(key)
            return
        name = f"{section}{label}"
        expected = self.content.get(key, "")
        actual = self.dom.get_text(
            selectors.customer_info_selector(section, label, _EMAIL_PART), name,
        )
        if not _same_emails(expected, actual):
            raise FormValidationError(f"{name}校验失败，实际值：{actual}，期望值：{expected}")
        self.mark_field_done(key)

    def _verify_show_on_bl(
        self: "FzSnlwySiTask", section: str, label: str, key: str,
    ) -> None:
        """校验提单显示开关；未下发值时保留页面状态。"""
        value = self.content.get(key)
        if value is None:
            self.mark_field_done(key)
            return
        self._verify_checkbox(
            selectors.customer_info_selector(
                section, label, f"label[normalize-space()='{_SHOW_ON_BL}']",
            ),
            f"{section}{label}{_SHOW_ON_BL}",
            _as_bool(value),
            key,
        )

    def _verify_address_select(
        self: "FzSnlwySiTask", section: str, label: str, key: str,
    ) -> None:
        """校验下拉展示文本，国家字段完成时同步移除国家代码。"""
        value = self.content.get(key, "")
        if value:
            name = f"{section}{label}"
            actual = self.dom.get_text(
                selectors.customer_info_selector(section, label, _SELECT_DISPLAY),
                name=name,
            )
            if str(value) not in actual:
                raise FormValidationError(f"{name}校验失败，实际值：{actual}，期望值：{value}")
        self.mark_field_done(key)
        if label == "国家及地区":
            self.mark_field_done(f"{key}Code")

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
