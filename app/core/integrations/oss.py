from pathlib import Path


class OssClient:
    """截图和录屏文件地址处理。"""

    def local_screenshot_path(self, rpa_message_id: str) -> str:
        path = Path("runtime/screenshots") / f"{rpa_message_id}_error.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)
