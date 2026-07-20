class RpaError(Exception):
    """RPA 基础异常。"""

    code = 500

    def __init__(self, message="", *, code=None):
        super().__init__(message)
        self.code = self.code if code is None else code


class MessageParseError(RpaError):
    """消息结构不正确。"""

    code = 400


class QueueNameError(RpaError):
    """队列名不符合客户_船司_业务格式。"""

    code = 400


class RouteNotFoundError(RpaError):
    """未找到队列入口路由。"""

    code = 500


class BrowserStartError(RpaError):
    """浏览器启动失败。"""

    code = 500


class LoginError(RpaError):
    """登录失败。"""

    code = 403


class ElementNotFoundError(RpaError):
    """页面元素不存在。"""

    code = 404


class BusinessError(RpaError):
    """业务填单失败。"""

    code = 405


class FormValidationError(RpaError):
    """官网字段校验不通过。"""

    code = 401


class UnfilledFieldError(RpaError):
    """存在未处理字段。"""

    code = 402
