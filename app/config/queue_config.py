def parse_queue_names(raw_value):
    """解析需要消费的队列名列表。"""
    return [item.strip().upper() for item in raw_value.split(",") if item.strip()]
