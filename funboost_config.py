from funboost.funboost_config_deafult import (
    BrokerConnConfig as DefaultBrokerConnConfig,
    FunboostCommonConfig as DefaultFunboostCommonConfig,
)

from app.config.rabbitmq import RabbitmqSettings


_rabbitmq = RabbitmqSettings.from_env()


class BrokerConnConfig(DefaultBrokerConnConfig):
    RABBITMQ_USER = _rabbitmq.user
    RABBITMQ_PASS = _rabbitmq.password
    RABBITMQ_HOST = _rabbitmq.host
    RABBITMQ_PORT = _rabbitmq.port
    RABBITMQ_VIRTUAL_HOST = _rabbitmq.virtual_host
    RABBITMQ_URL = _rabbitmq.url


class FunboostCommonConfig(DefaultFunboostCommonConfig):
    NB_LOG_FORMATER_INDEX_FOR_CONSUMER_AND_PUBLISHER = 12
    TIMEZONE = "Asia/Shanghai"
    SHOW_HOW_FUNBOOST_CONFIG_SETTINGS = False
