"""SNLWY SI 要求项、运费及附加费和附件上传。"""

from __future__ import annotations

import re
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

import requests

from DrissionPage.errors import NoRectError

from app.core.task.errors import BusinessError, ElementNotFoundError, FormValidationError
from app.spider.SNLWY import selectors

if TYPE_CHECKING:
    from app.spider.SNLWY.tasks.fz_snlwy_si import FzSnlwySiTask

# 页面分组标题、下发字段名。选项是组内复选框，不是下拉。
_REQUIREMENT_FIELDS = (
    {"label": "装船要求", "key": "stowageRequirements"},
    {"label": "订舱要求", "key": "bookingRequirements"},
    {"label": "货物要求", "key": "cargoRequirements"},
)


def _requirement_values(value) -> list[str]:
    """下发值是选项文本列表。单个字符串按一个选项处理，不能按逗号拆。"""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    raise BusinessError(f"要求字段必须是字符串列表，实际类型：{type(value).__name__}")


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _cell_text(value) -> str:
    return " ".join(str(value or "").split())


_FILE_URL_API = "http://fec.cgofish.com/v1/file/url"
_EMAIL_SEPARATORS = re.compile(r"[,，]+")
_PAGE_EMAIL_SPLIT = re.compile(r"[\s,，×✕✖]+")


def _split_email_value(value) -> list[str]:
    """下发邮箱和收货人邮箱一样，是逗号分隔字符串。"""
    text = "" if value is None else str(value)
    return [part.strip() for part in _EMAIL_SEPARATORS.split(text) if part.strip()]


def _emails_from_page_text(text: str) -> list[str]:
    return [
        part.strip()
        for part in _PAGE_EMAIL_SPLIT.split(text or "")
        if part.strip() and "@" in part
    ]


def _same_emails(expected, page_text: str) -> bool:
    expected_emails = [item.casefold() for item in _split_email_value(expected)]
    actual_emails = [item.casefold() for item in _emails_from_page_text(page_text)]
    return expected_emails == actual_emails


class SiFillRequirementMixin:
    """填写装船、订舱、货物要求，以及运费及附加费。"""

    def _fill_requirement(self: "FzSnlwySiTask") -> None:
        """按组同步复选框。含电池在订舱和货物里各有一项，不能混点。"""
        for config in _REQUIREMENT_FIELDS:
            self._fill_requirement_group(config)
        self._verify_requirements()
        self._fill_surcharges()
        self._fill_attachments()
        self._fill_notification_emails()

    def _fill_requirement_group(self: "FzSnlwySiTask", config: dict) -> None:
        label, key = config["label"], config["key"]
        if key not in self.content:
            return
        expected = _requirement_values(self.content.get(key))
        self.dom.scroll_to_see(selectors.requirement_group_selector(label), name=label)
        options = self._requirement_option_texts(label)
        missing = [item for item in expected if item not in options]
        if missing:
            raise ElementNotFoundError(f"{label}选项不存在：{'、'.join(missing)}")

        expected_set = set(expected)
        for option in options:
            self._set_checkbox_if_needed(
                selectors.requirement_checkbox_selector(label, option),
                f"{label}{option}",
                option in expected_set,
            )

    def _requirement_option_texts(self: "FzSnlwySiTask", label: str) -> list[str]:
        elements = self.dom._find_eles(
            selectors.requirement_option_selector(label),
            f"{label}选项",
        )
        return [
            str(getattr(element, "text", "") or "").strip()
            for element in elements
        ]

    def _checked_requirement_texts(self: "FzSnlwySiTask", label: str) -> list[str]:
        elements = self.dom._find_eles(
            selectors.requirement_checked_selector(label),
            f"{label}已选",
            required=False,
            timeout=1,
        ) or []
        texts = []
        for element in elements:
            text = str(getattr(element, "text", "") or "").strip()
            if text:
                texts.append(text)
        return texts

    def _verify_requirements(self: "FzSnlwySiTask") -> None:
        """按已勾选的 label 校验，通过后才从 remain_content 删除。"""
        for config in _REQUIREMENT_FIELDS:
            label, key = config["label"], config["key"]
            if key not in self.content:
                self.mark_field_done(key)
                continue
            expected = _requirement_values(self.content.get(key))
            actual = self._checked_requirement_texts(label)
            if set(actual) != set(expected):
                raise FormValidationError(
                    f"{label}校验失败，实际值：{actual}，期望值：{expected}"
                )
            self.mark_field_done(key)

    def _fill_surcharges(self: "FzSnlwySiTask") -> None:
        """按下发数组顺序逐行填写。第一行费用代码对不上就停止，不按代码找行。"""
        if "surcharges" not in self.content:
            self.mark_field_done("surcharges")
            return
        items = self.content.get("surcharges")
        if not isinstance(items, list):
            raise BusinessError(f"surcharges必须是列表，实际类型：{type(items).__name__}")
        if not items:
            self.mark_field_done("surcharges")
            return
        if not isinstance(items[0], dict):
            raise BusinessError("第1个附加费必须是对象")
        self.dom.scroll_to_see(selectors.SURCHARGE_ROWS, name="运费及附加费")
        codes = self._surcharge_codes()
        if not codes:
            raise FormValidationError("运费及附加费表格为空")
        expected_first = _cell_text(items[0].get("surchargeCode"))
        if codes[0] != expected_first:
            raise FormValidationError(
                f"第1行费用代码不一致，实际值：{codes[0]}，期望值：{expected_first}"
            )
        if len(items) > len(codes):
            raise FormValidationError(
                f"运费及附加费行数不足，实际{len(codes)}行，下发{len(items)}条"
            )
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise BusinessError(f"第{index + 1}个附加费必须是对象")
            code = _cell_text(item.get("surchargeCode"))
            if index == 0:
                self.mark_field_done(["surcharges", index, "isPrintOnBL"])
            self._fill_surcharge_payment(index, code, item)
            self.mark_field_done(["surcharges", index, "surchargeCode"])
            self.mark_field_done(["surcharges", index, "surchargePaymentType"])
            if index != 0:
                self._fill_surcharge_print(index, code, item)
            self.mark_field_done(["surcharges", index, "defaultPaymentType"])

    def _surcharge_codes(self: "FzSnlwySiTask") -> list[str]:
        codes = []
        for row in self.dom._find_eles(selectors.SURCHARGE_ROWS, "运费及附加费"):
            cells = row.eles("css:td")
            text = cells[1].text if len(cells) > 1 else ""
            codes.append(_cell_text(text))
        return codes

    def _scroll_surcharge_field(self: "FzSnlwySiTask", selector: str, name: str):
        """下拉关闭后下一行可能暂时没有布局，用脚本滚入视口并重试。"""
        last_error = None
        for _ in range(3):
            element = self.dom._find(selector, name)
            try:
                element.run_js("this.scrollIntoView({block:'center', inline:'nearest'})")
                time.sleep(0.2)
                _ = element.rect.size
                return element
            except NoRectError as exc:
                last_error = exc
                time.sleep(0.3)
        raise last_error

    def _fill_surcharge_payment(
        self: "FzSnlwySiTask",
        index: int,
        code: str,
        item: dict,
    ) -> None:
        payment = _cell_text(item.get("surchargePaymentType"))
        name = f"第{index + 1}行{code}指定付款方式"
        if not payment:
            return
        selector = selectors.surcharge_payment_selector(index)
        self._scroll_surcharge_field(selector, name)
        actual = _cell_text(self.dom.get_text(selector, name))
        if actual != payment:
            self.dom.select_by_word(
                selector,
                payment,
                selectors.ELEMENT_SELECT_OPTIONS,
                name=name,
            )
            time.sleep(0.3)
            actual = _cell_text(self.dom.get_text(selector, name))
        if actual != payment:
            raise FormValidationError(f"{name}校验失败，实际值：{actual}，期望值：{payment}")

    def _fill_surcharge_print(
        self: "FzSnlwySiTask",
        index: int,
        code: str,
        item: dict,
    ) -> None:
        """第一行没有可编辑的是否打印，调用方已经直接标记完成。"""
        expected = _as_bool(item.get("isPrintOnBL"))
        name = f"第{index + 1}行{code}是否打印"
        selector = selectors.surcharge_print_selector(index)
        self._scroll_surcharge_field(selector, name)
        self._set_checkbox_if_needed(selector, name, expected)
        actual = self._is_checkbox_checked(selector, name)
        if actual != expected:
            raise FormValidationError(f"{name}校验失败，实际值：{actual}，期望值：{expected}")
        self.mark_field_done(["surcharges", index, "isPrintOnBL"])

    def _fill_attachments(self: "FzSnlwySiTask") -> None:
        """按 cloudFileList 下载附件并上传。不点整页提交。"""
        if "cloudFileList" not in self.content:
            self.mark_field_done("cloudFileList")
            return
        files = self.content.get("cloudFileList")
        if not isinstance(files, list):
            raise BusinessError(f"cloudFileList必须是列表，实际类型：{type(files).__name__}")
        if not files:
            self.mark_field_done("cloudFileList")
            return
        self.dom.scroll_to_see(selectors.ATTACHMENT_ADD, name="附件")
        for index, item in enumerate(files):
            if not isinstance(item, dict):
                raise BusinessError(f"第{index + 1}个附件必须是对象")
            self._upload_one_attachment(index, item)

    def _upload_one_attachment(self: "FzSnlwySiTask", index: int, item: dict) -> None:
        filename = Path(str(item.get("filename") or "")).name
        file_type = _cell_text(item.get("fileType"))
        if not filename:
            raise BusinessError(f"第{index + 1}个附件缺少文件名")
        if not file_type:
            raise BusinessError(f"第{index + 1}个附件缺少附件类型")
        shown = _cell_text(self.dom.get_text(selectors.ATTACHMENT_LIST, "附件列表"))
        if filename in shown and file_type in shown:
            self._mark_attachment_done(index)
            return
        local_path = self._download_cloud_file(item, filename)
        try:
            self._open_attachment_dialog()
            self._select_attachment_type(file_type)
            self.dom._find(selectors.UPLOAD_FILE_DRAGGER, "选择附件").click.to_upload(str(local_path))
            self._confirm_attachment_upload()
        finally:
            local_path.unlink(missing_ok=True)
        shown = _cell_text(self.dom.get_text(selectors.ATTACHMENT_LIST, "附件列表"))
        if filename not in shown:
            raise FormValidationError(f"第{index + 1}个附件校验失败，实际值：{shown}，期望值：{filename}")
        self._mark_attachment_done(index)

    def _download_cloud_file(self: "FzSnlwySiTask", item: dict, filename: str) -> Path:
        """用 objectName 换临时地址，再把文件下到本地。"""
        object_name = _cell_text(item.get("objectName"))
        if not object_name:
            raise BusinessError(f"{filename}缺少 objectName")
        response = requests.get(_FILE_URL_API, params={"objectName": object_name}, timeout=30)
        if response.status_code != 200:
            raise BusinessError(f"{filename}获取下载地址失败：HTTP {response.status_code}")
        payload = response.json()
        if payload.get("code") != 200:
            raise BusinessError(f"{filename}获取下载地址失败：{payload.get('message')}")
        url = _cell_text((payload.get("data") or {}).get("url"))
        if not url:
            raise BusinessError(f"{filename}获取下载地址失败：响应没有 url")
        file_response = requests.get(url, timeout=60)
        if file_response.status_code != 200 or not file_response.content:
            raise BusinessError(f"{filename}下载失败：HTTP {file_response.status_code}")
        save_dir = Path(getattr(self.dom, "download_dir", None) or tempfile.gettempdir())
        save_dir.mkdir(parents=True, exist_ok=True)
        local_path = save_dir / filename
        local_path.write_bytes(file_response.content)
        return local_path

    def _attachment_dialog_visible(self: "FzSnlwySiTask") -> bool:
        """弹窗节点关闭后仍留在页面里，真正隐藏的是外层遮罩。"""
        dialog = self.dom._find(selectors.UPLOAD_DIALOG, "附件上传", required=False, timeout=0.5)
        if not dialog:
            return False
        return bool(dialog.run_js(
            "const overlay = this.closest('.el-overlay') || this;"
            "const style = getComputedStyle(overlay);"
            "return style.display !== 'none'"
            " && style.visibility !== 'hidden'"
            " && overlay.getClientRects().length > 0;"
        ))

    def _open_attachment_dialog(self: "FzSnlwySiTask") -> None:
        if self._attachment_dialog_visible():
            return
        self.dom.click(selectors.ATTACHMENT_ADD, "添加附件")
        self.dom._find(selectors.UPLOAD_DIALOG, "附件上传")

    def _select_attachment_type(self: "FzSnlwySiTask", file_type: str) -> None:
        """选项正文是类型名，旁边还有收电子件或收纸质原件，不能整段精确匹配。"""
        display = _cell_text(self.dom.get_text(selectors.UPLOAD_TYPE_SELECT, "附件类型"))
        if display == file_type:
            return
        self.dom.click(selectors.UPLOAD_TYPE_SELECT, "附件类型")
        time.sleep(0.5)
        matched = None
        for option in self.dom._find_eles(selectors.UPLOAD_TYPE_OPTIONS, "附件类型选项"):
            title = option.ele("css:span", timeout=1)
            text = _cell_text(getattr(title, "text", "") if title else "")
            if text == file_type:
                matched = option
                break
        if matched is None:
            raise ElementNotFoundError(f"附件类型不存在：{file_type}")
        matched.click()
        display = _cell_text(self.dom.get_text(selectors.UPLOAD_TYPE_SELECT, "附件类型"))
        if display != file_type:
            raise FormValidationError(f"附件类型校验失败，实际值：{display}，期望值：{file_type}")

    def _confirm_attachment_upload(self: "FzSnlwySiTask") -> None:
        confirm = None
        for _ in range(10):
            confirm = self.dom._find(selectors.UPLOAD_CONFIRM, "确定上传", required=False, timeout=1)
            if confirm:
                break
            time.sleep(0.3)
        if not confirm:
            raise FormValidationError("附件未选中，确定按钮不可用")
        self.dom.click(selectors.UPLOAD_CONFIRM, "确定上传")
        for _ in range(10):
            if not self._attachment_dialog_visible():
                return
            time.sleep(0.3)
        raise FormValidationError("确定上传后附件弹窗未关闭")

    def _mark_attachment_done(self: "FzSnlwySiTask", index: int) -> None:
        for key in ("url", "filename", "objectName", "fileType"):
            self.mark_field_done(["cloudFileList", index, key])

    def _fill_notification_emails(self: "FzSnlwySiTask") -> None:
        """接收通知邮箱和收货人邮箱一样，下发值按逗号拆成标签。"""
        key = "notificationEmails"
        if key not in self.content:
            self.mark_field_done(key)
            return
        expected = self.content.get(key, "")
        wrapper = selectors.notification_email_selector(
            "*[contains(@class,'editable-input-tag-wrapper')]"
        )
        self.dom.scroll_to_see(wrapper, name="接收通知邮箱")
        current = self.dom.get_text(wrapper, "接收通知邮箱")
        if _same_emails(expected, current):
            self.mark_field_done(key)
            return
        emails = _split_email_value(expected)
        if not emails:
            self.dom._find(wrapper, "接收通知邮箱").hover()
            self.dom.click(
                selectors.notification_email_selector(
                    "*[contains(@class,'editable-input-tag__clear')]"
                ),
                "清除接收通知邮箱",
            )
        else:
            self.dom.click(
                selectors.notification_email_selector(
                    "*[contains(@class,'editable-input-tag__bulk-toggle')]"
                ),
                "编辑接收通知邮箱",
            )
            time.sleep(0.3)
            self.dom.input_text(
                selectors.notification_email_selector(
                    "textarea[contains(@class,'editable-input-tag__bulk-textarea')]"
                ),
                ",".join(emails),
                name="接收通知邮箱",
                blur=False,
            )
            self.dom.click(
                selectors.notification_email_selector("button[normalize-space()='确认']"),
                "确认接收通知邮箱",
            )
        actual = self.dom.get_text(wrapper, "接收通知邮箱")
        if not _same_emails(expected, actual):
            raise FormValidationError(
                f"接收通知邮箱校验失败，实际值：{actual}，期望值：{expected}"
            )
        self.mark_field_done(key)
