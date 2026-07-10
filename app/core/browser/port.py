import json
from pathlib import Path

from app.core.task.errors import BrowserStartError


class BrowserPortRegistry:
    """按浏览器标识维护固定端口映射。"""

    def __init__(self, registry_path: Path, port_start: int, port_end: int) -> None:
        self.registry_path = registry_path
        self.port_start = port_start
        self.port_end = port_end

    def resolve_port(self, profile_name: str) -> int:
        """获取浏览器标识对应的固定端口。"""
        data = self._load()
        if profile_name in data:
            return int(data[profile_name])

        used_ports = {int(port) for port in data.values()}
        for port in range(self.port_start, self.port_end + 1):
            if port not in used_ports:
                data[profile_name] = port
                self._save(data)
                return port
        raise BrowserStartError(f"未找到可分配浏览器端口：{self.port_start}-{self.port_end}")

    def _load(self) -> dict[str, int]:
        if not self.registry_path.exists():
            return {}
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, int]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
