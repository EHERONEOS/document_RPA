from typing import Any

from app.core.logging.logger import log
from DrissionPage import ChromiumPage
from DrissionPage._pages.chromium_base import ChromiumBase

from app.core.task.errors import ElementNotFoundError



class HttpHelper:
    """页面 HTTP 监听封装。"""

    def __init__(self, page:ChromiumBase):
        self.page = page

    def wait_api_finished(
        self,
        url: str,
        trigger: Any = None,
        timeout: int = 30,
        method: tuple[str, ...] = ("GET", "POST"),
        res_type: bool = True,
        is_regex: bool = False,
        required: bool = True,
    ) -> dict[str, Any]:
        """监听接口并在触发动作后返回监听结果。"""
        if not hasattr(self.page, "listen"):
            raise ElementNotFoundError("当前页面不支持接口监听")
        if trigger is not None and not callable(trigger):
            raise ElementNotFoundError("触发动作必须是可调用对象")

        listener = self.page.listen
        listener.start(targets=url, is_regex=is_regex, method=method, res_type=res_type)
        try:
            if trigger is not None:
                trigger()
            packet = listener.wait(timeout=timeout)
            if packet is False:
                if required:
                    raise ElementNotFoundError(f"监听接口超时：{url}")
                return None

            log(f"监听到接口响应：{packet.url}")
            if packet.is_failed:
                if required:
                    raise ElementNotFoundError(f"监听接口失败：{packet.url}")
                return None
            return {
                "response":packet.response.body,
                "postData":packet.request.postData,
                "params":packet.request.params,
            }
        except RuntimeError as e:
            if required:
                raise ElementNotFoundError(e)
            return None
        finally:
            listener.stop()
