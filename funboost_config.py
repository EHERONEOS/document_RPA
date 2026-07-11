import os
from urllib.parse import quote_plus

from funboost.funboost_config_deafult import (
    BrokerConnConfig as DefaultBrokerConnConfig,
    FunboostCommonConfig as DefaultFunboostCommonConfig,
)


class BrokerConnConfig(DefaultBrokerConnConfig):
    RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
    RABBITMQ_PASS = os.getenv("RABBITMQ_PASSWORD", "guest")
    RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "192.168.60.106")
    RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
    RABBITMQ_VIRTUAL_HOST = os.getenv("RABBITMQ_VIRTUAL_HOST", "/")
    RABBITMQ_URL = (
        f"amqp://{RABBITMQ_USER}:{quote_plus(RABBITMQ_PASS)}"
        f"@{RABBITMQ_HOST}:{RABBITMQ_PORT}/{RABBITMQ_VIRTUAL_HOST}"
    )


class FunboostCommonConfig(DefaultFunboostCommonConfig):
    SHOW_HOW_FUNBOOST_CONFIG_SETTINGS = False
