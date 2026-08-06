
"""Nacos 环境配置加载逻辑。"""
import json
import os
from pathlib import Path

import nacos
import yaml
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)


DEFAULT_NACOS_IP = "106.14.95.61"
DEFAULT_NACOS_NAMESPACE = "9835862f-b9f7-4f9d-aab1-6c63602d49a6"
DEFAULT_NACOS_GROUP = "DEFAULT_GROUP"

nacos_client = nacos.NacosClient(
    server_addresses=os.getenv("nacos_ip", DEFAULT_NACOS_IP),
    namespace=os.getenv("nacos_namespace", DEFAULT_NACOS_NAMESPACE),
)


def _load_yaml_config(data_id: str) -> dict:
    return yaml.load(
        nacos_client.get_config(data_id=data_id, group=DEFAULT_NACOS_GROUP),
        yaml.FullLoader,
    ) or {}


__DATA_SOURCE_CONFIG = _load_yaml_config("shared-datasource")
__DATA_RABBITMQ_CONFIG = _load_yaml_config("rabbitmq.yml")


REDIS_CONFIG = {
    "host": __DATA_SOURCE_CONFIG["redis"]["host"],
    "port": __DATA_SOURCE_CONFIG["redis"]["port"],
    "password": __DATA_SOURCE_CONFIG["redis"]["password"],
    "db": "15",
}
__RABBITMQ_ENV_CONFIG = __DATA_RABBITMQ_CONFIG[os.getenv("APP_ENV", "test")]

RABBITMQ_CONFIG = {
    "user": __RABBITMQ_ENV_CONFIG["user"],
    "password": __RABBITMQ_ENV_CONFIG["password"],
    "host": __RABBITMQ_ENV_CONFIG["host"],
    "port": __RABBITMQ_ENV_CONFIG["port"],
    "virtual_host": __RABBITMQ_ENV_CONFIG["virtual_host"],
}


def load_nacos_environment() -> dict[str, str]:
    spider_config = _load_yaml_config("spider-config")
    data_source_config = __DATA_SOURCE_CONFIG

    ttshitu_user = spider_config.get("ttshitu", {}).get("username", "")
    ttshitu_pwd = spider_config.get("ttshitu", {}).get("password", "")
    dingtalk_robot_api = spider_config.get("dingtalk_api", {}).get(
        "spider_warning", ""
    )
    dingtalk_ccam_api = spider_config.get("dingtalk_api", {}).get("ccam", "")
    yunma_token = data_source_config.get("yunma", {}).get("token", "")

    os.environ["TTSHITU_USER"] = ttshitu_user
    os.environ["TTSHITU_PWD"] = ttshitu_pwd
    os.environ["DINGTALK_ROBOT_API"] = dingtalk_robot_api
    os.environ["DINGTALK_CCAM_API"] = dingtalk_ccam_api
    os.environ["YUNMA_TOKEN"] = yunma_token

    return {
        "TTSHITU_USER": ttshitu_user,
        "TTSHITU_PWD": ttshitu_pwd,
        "DINGTALK_ROBOT_API": dingtalk_robot_api,
        "DINGTALK_CCAM_API": dingtalk_ccam_api,
        "YUNMA_TOKEN": yunma_token,
    }


