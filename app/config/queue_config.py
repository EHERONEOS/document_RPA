QUEUE_ASSIGNMENT_SOURCE_SERVER = "server"
QUEUE_ASSIGNMENT_SOURCE_LOCAL = "local"
QUEUE_ASSIGNMENT_SOURCES = {QUEUE_ASSIGNMENT_SOURCE_SERVER, QUEUE_ASSIGNMENT_SOURCE_LOCAL}


def parse_queue_names(raw_value):
    """解析需要消费的队列名列表。"""
    return [item.strip().upper() for item in str(raw_value or "").split(",") if item.strip()]


def parse_queue_assignment_source(raw_value=None):
    """解析队列监听来源开关，仅允许 server 或 local。"""
    source = str(raw_value or QUEUE_ASSIGNMENT_SOURCE_SERVER).strip().lower()
    if source not in QUEUE_ASSIGNMENT_SOURCES:
        raise RuntimeError(
            "QUEUE_ASSIGNMENT_SOURCE 必须是 server 或 local，"
            f"当前值：{raw_value!r}"
        )
    return source
