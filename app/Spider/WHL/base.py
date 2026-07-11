from app.core.task.base_task import BaseRpaTask


class WhlBaseTask(BaseRpaTask):
    """WHL 船司公共能力。"""

    carrier_code = "WHL"

    def login(self):
        """执行 WHL 登录。"""
        self.log("执行 WHL 登录入口")
