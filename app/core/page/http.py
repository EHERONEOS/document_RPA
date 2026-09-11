import json
import time
from typing import Any
from urllib.parse import parse_qs

import requests
from app.core.logging.logger import log
from DrissionPage import ChromiumPage
from DrissionPage._pages.chromium_base import ChromiumBase

from app.core.task.errors import ElementNotFoundError



class HttpHelper:
    """页面 HTTP 监听和主动请求封装。"""

    def __init__(self, page:ChromiumBase):
        self.page = page

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: Any = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        timeout: int = 30,
        **kwargs: Any,
    ) -> requests.Response:
        """发起 HTTP 请求并返回成功响应。"""
        try:
            response = requests.request(
                method=method,
                url=url,
                params=params,
                data=data,
                json=json,
                headers=headers,
                cookies=cookies,
                timeout=timeout,
                **kwargs,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise ElementNotFoundError(f"HTTP 请求失败：{method.upper()} {url}，{exc}") from exc

    def wait_api_finished(
        self,
        url: str,
        trigger: Any = None,
        timeout: int = 30,
        method: tuple[str, ...] = ("GET", "POST"),
        res_type: bool = True,
        is_regex: bool = False,
        required: bool = True,
        request_params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """监听接口并在触发动作后返回符合请求参数的监听结果。"""
        if not hasattr(self.page, "listen"):
            raise ElementNotFoundError("当前页面不支持接口监听")
        if trigger is not None and not callable(trigger):
            raise ElementNotFoundError("触发动作必须是可调用对象")

        listener = self.page.listen
        listener.start(targets=url, is_regex=is_regex, method=method, res_type=res_type)
        deadline = time.monotonic() + timeout
        try:
            if trigger is not None:
                trigger()

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if required:
                        raise ElementNotFoundError(f"监听接口超时：{url}")
                    return None

                packet = listener.wait(timeout=remaining)
                if packet is False:
                    if required:
                        raise ElementNotFoundError(f"监听接口超时：{url}")
                    return None

                if request_params and not self._request_params_match(packet, request_params):
                    continue

                log(f"监听到接口响应：{packet.url}")
                if packet.is_failed:
                    if required:
                        raise ElementNotFoundError(f"监听接口失败：{packet.url}")
                    return None
                return {
                    "response": packet.response.body,
                    "postData": packet.request.postData,
                    "params": packet.request.params,
                }
        except RuntimeError as e:
            if required:
                raise ElementNotFoundError(e)
            return None
        finally:
            listener.stop()

    @classmethod
    def _request_params_match(
        cls,
        packet: Any,
        expected: dict[str, Any],
    ) -> bool:
        """匹配查询参数、表单参数或 JSON 请求体中的字段。"""
        params = getattr(packet.request, "params", None) or {}
        post_data = cls._parse_post_data(getattr(packet.request, "postData", None))

        if not isinstance(params, dict):
            params = {}
        if not isinstance(post_data, dict):
            post_data = {}

        # 合并后可同时匹配 URL 查询参数和 POST 请求体参数。
        actual = {**params, **post_data}
        return cls._mapping_contains(actual, expected)

    @staticmethod
    def _parse_post_data(post_data: Any) -> dict[str, Any]:
        if isinstance(post_data, dict):
            return post_data
        if not isinstance(post_data, str) or not post_data:
            return {}

        try:
            parsed = json.loads(post_data)
        except json.JSONDecodeError:
            parsed = parse_qs(post_data, keep_blank_values=True)
            return {key: values[0] if len(values) == 1 else values for key, values in parsed.items()}

        return parsed if isinstance(parsed, dict) else {}

    @classmethod
    def _mapping_contains(cls, actual: Any, expected: Any) -> bool:
        if isinstance(expected, dict):
            return (
                isinstance(actual, dict)
                and all(
                    key in actual and cls._mapping_contains(actual[key], value)
                    for key, value in expected.items()
                )
            )
        return actual == expected
