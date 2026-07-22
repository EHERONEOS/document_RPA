import base64
import os
import time

import requests

from app.core.integrations.notifier import send_msg_to_dingtalk



# 图鉴识别
def get_verify_code( image_path, typeid=7):
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
    raise RuntimeError(f"图鉴识别失败：{error_msg}")

"""
    云码验证码平台
    产品文档https://www.jfbym.com/price.html
    参数：
        token:用户token
        type:"类型" 
            10010 用数英1~4位
            20111 通用双图滑块
            30332 图标通用点选
            ...
        image: 待识别图的base64字符串
        extra: 说明字段
"""
# 云码通用方法
def get_ym_verify_code(img, type,  extra=None):
    """识别图片验证码"""
    with open(img, 'rb') as f:
        base64_data = base64.b64encode(f.read())
        b64 = base64_data.decode()
    token = os.getenv("YUNMA_TOKEN", "FseOxevDVnNP7TGuKCYO-NIRQW4R_8KkTnkRo1IPy3Y")
    error_msg = ""
    for i in range(2):
        data = {"image": b64,"token":token,"type":type};
        if extra:
            data["extra"] = extra
        try:
            result = requests.post("http://api.jfbym.com/api/YmServer/customApi", data=data, timeout=30).json()
        except:
            result = {"success": False, "message": "请求超时", "data": {"result": ""}}

        if result['code'] == 10000:
            return result["data"]
        elif result['success'] is False:
            error_msg = result['msg']
            continue
    else:
        send_msg_to_dingtalk(title="打码平台报警", msg=error_msg)
        raise RuntimeError(f"云码验证码识别失败：{error_msg}")

# 云码特殊方法hcaptcha
"""
    识别 hcaptcha 验证码平台
    产品文档:https://www.jfbym.com/test/220.html
    适配船司：ZIM
    参数:
        token:用户token
        sitekey:站点key； 获取方式：参考云码文档
        type:50013(固定)
        pageurl:验证码页面的所在地址

"""
def get_ym_hcaptcha_code( sitekey,pageurl):
    error_msg = ""
    submit_url = "http://api.jfbym.com/api/YmServer/funnelApi"
    result_url = "http://api.jfbym.com/api/YmServer/funnelApiResult"
    polling_codes = [10005, 10006, 10007, 10008, 10009]
    token = os.getenv("ymtoken", "FseOxevDVnNP7TGuKCYO-NIRQW4R_8KkTnkRo1IPy3Y")
    for i in range(2):
        data = {"token": token, "type": "50013", "sitekey": sitekey, "pageurl": pageurl}
        try:
            result = requests.post(submit_url, data=data, timeout=30).json()
            print(result)
        except:
            result = {"code": -1, "msg": "请求超时", "data": {}}

        if result.get('code') == 10000:
            captcha_data = result.get("data", {})
            captcha_id = captcha_data.get("captchaId")
            record_id = captcha_data.get("recordId")
            if not captcha_id or not record_id:
                error_msg = result.get("msg") or "缺少captchaId或recordId"
                continue

            start_time = time.time()
            while time.time() - start_time < 300:
                poll_data = {"token": token, "captchaId": captcha_id, "recordId": record_id}
                try:
                    poll_result = requests.post(result_url, data=poll_data, timeout=30).json()
                    print(poll_result)
                except:
                    poll_result = {"code": -1, "msg": "请求超时", "data": {}}

                if poll_result.get('code') == 10000 or poll_result.get('code') == 10001:
                    return poll_result["data"]["data"]
                elif poll_result.get('code') in polling_codes:
                    error_msg = poll_result.get('msg', '')
                    if time.time() - start_time < 300:
                        time.sleep(10)
                    continue
                else:
                    send_msg_to_dingtalk(title="打码平台报警", msg=error_msg)
                    raise RuntimeError(f"云码验证码识别失败：{error_msg}")
            error_msg = error_msg or "hcaptcha轮询超时"
            break
        else:
            error_msg = result.get('msg') or result.get('message') or ""
            continue
    send_msg_to_dingtalk(title="打码平台报警", msg=error_msg)
    raise RuntimeError(f"云码验证码识别失败：{error_msg}")

