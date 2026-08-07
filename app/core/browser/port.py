import json
import socket
from pathlib import Path

from app.core.task.errors import BrowserStartError


class BrowserPortRegistry:
    """按浏览器标识维护固定端口映射。"""

    def __init__(self, registry_path, port_start, port_end):
        self.registry_path = Path(registry_path)
        self.port_start = port_start
        self.port_end = port_end

    def resolve_port(self, profile_name):
        """获取浏览器标识对应的固定端口。"""
        data = self._load()
        if profile_name in data:
            return int(data[profile_name])

        used_ports = {int(port) for port in data.values()}
        for port in range(self.port_start, self.port_end + 1):
            if port not in used_ports and self._is_port_available(port):
                data[profile_name] = port
                self._save(data)
                return port
        raise BrowserStartError(f"未找到可分配浏览器端口：{self.port_start}-{self.port_end}")

    def release_port(self, profile_name):
        """释放临时浏览器标识占用的端口映射。"""
        data = self._load()
        if profile_name not in data:
            return
        del data[profile_name]
        self._save(data)

    def _load(self):
        if not self.registry_path.exists():
            return {}
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def _save(self, data):
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _is_port_available(port):
        """Avoid selecting a debugging port already occupied by another app."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                return False
        return True
