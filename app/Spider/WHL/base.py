from app.core.task.base_task import BaseRpaTask
from app.core.task.errors import LoginError


class WhlBaseTask(BaseRpaTask):
    """WHL 船司公共能力。"""

    carrier_code = "WHL"

    def login(self):
        """执行 WHL 登录。"""
        self.log("执行 WHL 登录入口")
        raise LoginError("登录失败")
