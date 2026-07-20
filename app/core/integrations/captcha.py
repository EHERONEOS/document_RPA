import base64
import os

import requests

from app.core.integrations.notifier import send_msg_to_dingtalk


class CaptchaSolver:
    """验证码识别入口。"""


    # 图鉴识别
    def get_verify_code(self, image_path, typeid=7):
        with open(image_path, "rb") as file:
            image_base64 = base64.b64encode(file.read()).decode()

        username = os.getenv("TTSHITU_USER", "a1072842511")
        password = os.getenv("TTSHITU_PWD", "wolegequ")
        if not username or not password:
            raise RuntimeError("缺少图鉴账号配置：TTSHITU_USER/TTSHITU_PWD")

        error_msg = ""
        for _ in range(2):
            data = {
                "username": username,
                "password": password,
                "typeid": typeid,
                "image": image_base64,
            }
            try:
                result = requests.post("http://api.ttshitu.com/predict", json=data, timeout=30).json()
            except requests.exceptions.RequestException:
                result = {"success": False, "message": "请求超时", "data": {"result": ""}}

            if result.get("success"):
                return result["data"]["result"]

            error_msg = result.get("message", "验证码识别失败")
            if error_msg == "PredictProviderException: 不是有效的图片!":
                return ""

        send_msg_to_dingtalk(title="打码平台报警", msg=error_msg)
        raise RuntimeError("图鉴识别失败")
