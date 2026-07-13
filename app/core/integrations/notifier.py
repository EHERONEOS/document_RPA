import getpass
import json
import os

import requests

from app.core.logging.logger import log


PROCESSING_NOTIFY_TEST_URL = "http://gcp.wise.cn/v1/rpa-mq-message-info/callback"
PROCESSING_NOTIFY_PRO_URL = "https://gcp.56gpt.com/v1/rpa-mq-message-info/callback"


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
