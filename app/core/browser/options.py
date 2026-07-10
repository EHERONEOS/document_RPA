from dataclasses import dataclass, field


DEFAULT_BROWSER_ARGS = [
    "--start-maximized",
    "--ignore-certificate-errors",
]

DEFAULT_PREFS = {
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
}


@dataclass
class BrowserOptions:
    """浏览器启动参数。"""

    port: int
    user_data_path: str
    download_path: str
    incognito: bool = False
    arguments: list[str] = field(default_factory=lambda: list(DEFAULT_BROWSER_ARGS))
    prefs: dict[str, object] = field(default_factory=lambda: dict(DEFAULT_PREFS))
