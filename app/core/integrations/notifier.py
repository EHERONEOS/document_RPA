import datetime
import getpass
import json
import os

import requests

from app.core.logging.logger import log


PROCESSING_NOTIFY_TEST_URL = "http://gcp.wise.cn/v1/rpa-mq-message-info/callback"
PROCESSING_NOTIFY_PRO_URL = "https://gcp.56gpt.com/v1/rpa-mq-message-info/callback"

SEND_TYPE_NAMES = {
    1: "新单",
    2: "改单",
    3: "删单",
    4: "重发",
}

SHIP_AGENT_NAMES = {
    "oocl": "东方海外",
    "sh_hanghua": "上海航华",
    "sh_huahang": "上海华港",
    "sh_lianhe": "上港联合",
    "sh_penghai": "上海鹏海",
    "sh_zhonglian": "上海中联",
    "sh_zhongwaiyun": "上海中外运",
    "sh_minsheng": "上海民生",
    "sh_penghua": "上海鹏华",
    "sh_shunde": "上海顺德",
    "sh_waidai": "上海外代",
    "sh_zhenghua": "上海振华",
}


def _as_list(value):
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


# 钉钉消息告警
def send_msg_to_dingtalk(
    title: str = "CCAM 发送报错",
    bill_no=None,
    ship_agent: str = "",
    send_type: int = None,
    msg=None,
    at=None,
    msg_to="default",
    at_all: bool = False,
):
    """
    发送消息到钉钉。

    :param title: 标题，会展示在首页对话框中。
    :param bill_no: 分单号或分单号列表。
    :param ship_agent: 船代代码。
    :param send_type: 发送类型，1=新单，2=改单，3=删单，4=重发。
    :param msg: 消息内容或消息内容列表。
    :param at: @ 人手机号或手机号列表。
    :param msg_to: 发送目标，default=默认预警群，其他值=上海舱单群。
    :param at_all: 是否 @ 所有人。
    """
    bill_no_list = [str(item) for item in _as_list(bill_no) if item]
    msg_list = [str(item) for item in _as_list(msg) if item]
    at_list = [str(item) for item in _as_list(at) if item]

    msg_lines = [f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} \n"]
    if title:
        msg_lines.append(f"> 标题：{title} \n")
    if ship_agent:
        msg_lines.append(f"> 船代：{SHIP_AGENT_NAMES.get(ship_agent.lower(), ship_agent)} \n")
    if bill_no_list:
        msg_lines.append(f"> 单号：{'，'.join(bill_no_list)} \n")
    if send_type:
        msg_lines.append(f"> 类型：{SEND_TYPE_NAMES.get(send_type, '未知')} \n")
    for index, item in enumerate(msg_list, start=1):
        msg_lines.append(f"> 预警-{index}：<font color=\"#FF0000\"> {item} </font> \n")
    if at_list:
        at_str = " ".join(f"@{mobile}" for mobile in sorted(set(at_list)))
        msg_lines.append(f"--- \n\n> <font color=\"#0000FF\"> {at_str} </font>")

    json_data = {
        "msgtype": "markdown",
        "markdown": {
            "title": f"CCAM {title}" if title else f"CCAM {' '.join(bill_no_list)} {' '.join(msg_list)}",
            "text": "\n".join(msg_lines),
        },
        "at": {
            "atMobiles": at_list,
            "isAtAll": at_all,
        },
    }
    api = os.getenv("DINGTALK_ROBOT_API", "") if msg_to.lower() == "default" else os.getenv("DINGTALK_CCAM_API", "")
    if not api:
        return ""

    headers = {"Content-Type": "application/json"}
    return requests.post(api, headers=headers, json=json_data).content.decode()



class ProcessingNotifier:
    """通知后台任务处理中。"""

    def notify_processing(self, context):
        log(f"通知处理中 rpaMessageId={context.rpa_message_id} queue={context.queue_name}")
        return self.send_rpa_mq_message_info(context.rpa_message_id, context.queue_name)

    def send_rpa_mq_message_info(self, message_id, queue_name):
        """回调后台 RPA MQ 消息处理中状态。"""
        headers = {
            "Content-Type": "application/json",
        }
        app_env = os.getenv("APP_ENV", "local")
        if app_env == "prod" or app_env == "local":
            url = PROCESSING_NOTIFY_PRO_URL
        else:
            url = PROCESSING_NOTIFY_TEST_URL

        rpa_robot_info = queue_name + ":" + getpass.getuser()
        data = {
            "messageId": message_id,
            "rpaRobotInfo": rpa_robot_info,
        }

        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            print(response.content)
            if response.status_code == 200:
                response_json = json.loads(response.content)
                response_data = response_json["data"]
                return {
                    "messageId": response_data["messageId"],
                    "status": response_data["status"],
                }
            return {}
        except requests.exceptions.RequestException as exc:
            return {
                "messageId": message_id,
                "status": f"Error: {exc}",
            }
