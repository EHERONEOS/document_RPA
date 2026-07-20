
import os
import nacos
import yaml
# from v2.nacos.common.client_config import ClientConfig
# from v2.nacos.config.model.config_param import ConfigParam
# from v2.nacos.config.nacos_config_service import NacosConfigService


DEFAULT_NACOS_IP = "106.14.95.61"
DEFAULT_NACOS_NAMESPACE = "9835862f-b9f7-4f9d-aab1-6c63602d49a6"
DEFAULT_NACOS_GROUP = "DEFAULT_GROUP"

def load_nacos_environment() -> dict[str, str]:
    nacos_client = nacos.NacosClient(server_addresses=os.getenv('nacos_ip', DEFAULT_NACOS_IP), namespace=os.getenv('nacos_namespace', DEFAULT_NACOS_NAMESPACE))
    SPIDER_CONFIG = yaml.load(nacos_client.get_config(data_id='spider-config', group='DEFAULT_GROUP'), yaml.FullLoader)
    # 图鉴验证码
    TTSHITU_USER = SPIDER_CONFIG.get("ttshitu").get('username', '')
    TTSHITU_PWD = SPIDER_CONFIG.get("ttshitu").get('password', '')
    # 钉钉预警api
    DINGTALK_ROBOT_API = SPIDER_CONFIG['dingtalk_api']["spider_warning"]
    # CCAM预警群api
    DINGTALK_CCAM_API = SPIDER_CONFIG['dingtalk_api']["ccam"]

    # 接口前缀
    API_PREFIX = SPIDER_CONFIG["api_prefix"]
    API_HEADERS = SPIDER_CONFIG["api_headers"]

    os.environ["TTSHITU_USER"] = TTSHITU_USER
    os.environ["TTSHITU_PWD"] = TTSHITU_PWD
    os.environ["DINGTALK_ROBOT_API"] = DINGTALK_ROBOT_API
    os.environ["DINGTALK_CCAM_API"] = DINGTALK_CCAM_API
    os.environ["API_PREFIX"] = API_PREFIX
    os.environ["API_HEADERS"] = API_HEADERS
