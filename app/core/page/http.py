from app.core.logging.logger import log
from DrissionPage import ChromiumPage
from DrissionPage._pages.chromium_base import ChromiumBase

from app.core.task.errors import ElementNotFoundError



class HttpHelper:
    """页面 HTTP 监听封装。"""

    def __init__(self, page:ChromiumBase):
        self.page = page

    def wait_api_finished(self, url, trigger=None, timeout=30, method=("GET", "POST"), res_type=True, is_regex=False, required=True):
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
                raise ElementNotFoundError(f"监听接口超时：{url}")
            
            log(f"监听到接口响应：{packet.url}")
            return None if packet.is_failed else packet.response.body
        except RuntimeError as e:
            if required:
                raise ElementNotFoundError(e)
            return None
        finally:
            listener.stop()
