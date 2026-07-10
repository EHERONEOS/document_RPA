import json
from pathlib import Path
from typing import Any


def load_message_template(path: str) -> dict[str, Any]:
    """读取本地消息模板。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))
