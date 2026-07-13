def str_to_bool(value):
    """将环境变量字符串转换为布尔值。"""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}
