from pathlib import Path

from app.config.settings import Settings
from app.core.browser.options import BrowserOptions
from app.core.browser.port import BrowserPortRegistry
from app.core.logging.logger import log
from app.core.task.errors import BrowserStartError


class LocalPage:
    """本地骨架运行使用的空页面对象。"""

    def ele(self, locator, timeout=0):
        return None

    def eles(self, locator, timeout=0):
        return []


class BrowserManager:
    """DrissionPage 浏览器管理器。"""

    def __init__(self, settings=None, registry=None):
        self.settings = settings or Settings.from_env()
        self.registry = registry or BrowserPortRegistry(
            Path(self.settings.browser_user_data_dir) / "port_registry.json",
            self.settings.browser_port_start,
            self.settings.browser_port_end,
        )
        self.page = None
        self.browser = None

    def build_profile_name(self, context):
        """按用户名和船司生成固定浏览器标识。"""
        username = context.website_info.get("websiteUserName") or context.website_info.get("websiteAccount") or "default"
        return f"{username}_{context.carrier_code}"

    def build_options(self, context, task):
        """构建浏览器启动参数。"""
        profile_name = self.build_profile_name(context)
        port = self.registry.resolve_port(profile_name)
        user_data_path = str(Path(self.settings.browser_user_data_dir) / profile_name)
        download_path = str(Path(self.settings.download_dir) / context.queue_name)
        return BrowserOptions(
            port=port,
            user_data_path=user_data_path,
            download_path=download_path,
            incognito=bool(getattr(task, "incognito", False)),
            wait_page_load=bool(getattr(task, "wait_page_load", False)),
        )

    def start(self, context, task):
        """启动或接管 DrissionPage 并返回页面对象。"""
        options = self.build_options(context, task)
        Path(options.user_data_path).mkdir(parents=True, exist_ok=True)
        Path(options.download_path).mkdir(parents=True, exist_ok=True)
        if not getattr(self.settings, "enable_browser", False):
            self.page = LocalPage()
            self.browser = None
            log(f"浏览器开关关闭，使用本地空页面 port={options.port} profile={options.user_data_path}")
            return self.page
        try:
            from DrissionPage import ChromiumOptions, Chromium

            co = ChromiumOptions()
            co.set_local_port(options.port)
            co.set_user_data_path(options.user_data_path)
            for argument in options.arguments:
                co.set_argument(argument)
            if options.incognito:
                co.set_argument("--incognito")
            co.set_pref("download.default_directory", options.download_path)
            for key, value in options.prefs.items():
                co.set_pref(key, value)
            if not options.wait_page_load:
                co.set_load_mode("none")
            self.browser = Chromium(co)
            self.page = self.browser.latest_tab
            log(f"浏览器启动或接管成功 port={options.port} profile={options.user_data_path}")
            return self.page
        except Exception as exc:
            raise BrowserStartError(f"浏览器启动或接管失败：{exc}") from exc

    def close(self):
        """保留浏览器进程，不主动关闭。"""
        log("任务结束后保留浏览器进程")
