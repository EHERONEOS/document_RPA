
"""可选的 Nacos 环境配置加载逻辑。

控制面不依赖 Nacos，因此仅在显式要求加载 Nacos 配置文档时才创建客户端。
"""
import os

import nacos


DEFAULT_NACOS_IP = "106.14.95.61"
DEFAULT_NACOS_NAMESPACE = "9835862f-b9f7-4f9d-aab1-6c63602d49a6"
DEFAULT_NACOS_GROUP = "DEFAULT_GROUP"


def parse_nacos_env_content(content: str | None) -> dict[str, str]:
    """解析 ``KEY=value`` 或 ``KEY: value`` 格式的 Nacos 配置文本。"""
    values = {}
    for raw_line in (content or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        separator = "=" if "=" in line else ":" if ":" in line else None
        if separator is None:
            continue
        key, value = line.split(separator, 1)
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def _as_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_nacos_environment() -> dict[str, str]:
    """将配置文档加载到 ``os.environ``。

    ``NACOS_OVERRIDE_ENV=false`` 时保留本地环境中已有的值。本函数不会在导入时
    自动调用。
    """
    server_addresses = os.getenv(
        "NACOS_SERVER_ADDRESSES", os.getenv("NACOS_IP", DEFAULT_NACOS_IP)
    )
    namespace = os.getenv("NACOS_NAMESPACE", DEFAULT_NACOS_NAMESPACE)
    group = os.getenv("NACOS_GROUP", DEFAULT_NACOS_GROUP)
    data_id = os.getenv("NACOS_ENV_DATA_ID", "wise-rpa.properties")
    client = nacos.NacosClient(server_addresses=server_addresses, namespace=namespace)
    values = parse_nacos_env_content(client.get_config(data_id=data_id, group=group))
    override = _as_bool(os.getenv("NACOS_OVERRIDE_ENV"), default=True)
    for key, value in values.items():
        if override or key not in os.environ:
            os.environ[key] = value
    return values
