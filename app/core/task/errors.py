class RpaError(Exception):
    """RPA 基础异常。"""


class MessageParseError(RpaError):
    """消息结构不正确。"""


class QueueNameError(RpaError):
    """队列名不符合客户_船司_业务格式。"""


class RouteNotFoundError(RpaError):
    """未找到队列入口路由。"""


class BrowserStartError(RpaError):
    """浏览器启动失败。"""


class LoginError(RpaError):
    """登录失败。"""


class ElementNotFoundError(RpaError):
    """页面元素不存在。"""


class BusinessError(RpaError):
    """业务填单失败。"""


class UnfilledFieldError(RpaError):
    """存在未处理字段。"""
