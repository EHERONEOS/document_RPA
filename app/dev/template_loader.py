import json
from pathlib import Path


def load_message_template(path):
    """读取本地消息模板。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))
