from dataclasses import dataclass, field


DEFAULT_BROWSER_ARGS = [
    "--start-maximized",
    "--ignore-certificate-errors",
    "--ignore-certificate-errors-spki-list",
    "--hide-crash-restore-bubble",
    "--disable-save-password-bubble",
    "--disable-password-manager",
    "--lang=zh-CN",
    "--hide-scrollbars",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-prompt-on-repost",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-popup-blocking",
    "--test-type",
    "--disable-sync",
    "--disable-password-generation",
    "--disable-password-manager-reauthentication",
    "--password-store=basic",
    "--disable-notifications",
    "--safebrowsing-disable-download-protection",
    "--disable-features=AutofillServerCommunication,PasswordLeakDetection,PasswordManagerOnboarding,PasswordManagerRedesign,DownloadBubble,DownloadBubbleV2",
]

DEFAULT_PREFS = {
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "download.bubble.enabled": False,
    "download_bubble.partial_view_enabled": False,
    "download.open_pdf_in_system_reader": False,
    "download.restrictions": 0,
    "plugins.always_open_pdf_externally": True,
    "safebrowsing.enabled": False,
    "safebrowsing.download_protection.enabled": False,
    "profile.default_content_setting_values.insecure_content": 1,
    "profile.content_settings.exceptions.automatic_downloads": {
        "[*,*]": {"setting": 1},
    },
    "credentials_enable_service": False,
    "profile.password_manager_enabled": False,
    "profile.password_manager_leak_detection": False,
    "profile.default_content_setting_values.password_manager": 2,
    "profile.content_settings.exceptions.password_manager": {
        "[*,*]": {"setting": 2},
    },
    "profile.default_content_settings.popups": 0,
    "credentials_enable_autosignin": False,
    "autofill.credit_card_enabled": False,
    "autofill.profile_enabled": False,
    "password_manager.account_storage_enabled": False,
    "password_manager.allow_saving": False,
    "password_manager.auto_signin": False,
    "password_manager.saving_enabled": False,
    "profile.default_content_setting_values.automatic_downloads": 1,
    "signin.allowed": False,
}


@dataclass
class BrowserOptions:
    """浏览器启动参数。"""

    port: int
    user_data_path: str
    download_path: str
    incognito: bool = False
    wait_page_load: bool = False
    arguments: list = field(default_factory=lambda: list(DEFAULT_BROWSER_ARGS))
    prefs: dict = field(default_factory=lambda: dict(DEFAULT_PREFS))
