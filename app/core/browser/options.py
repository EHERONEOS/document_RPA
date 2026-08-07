from dataclasses import dataclass, field


DEFAULT_BROWSER_ARGS = [
    "--start-maximized",  # 启动后最大化浏览器窗口。
    "--remote-debugging-address=127.0.0.1",  # 调试端口仅允许本机 Worker 接入。
    "--ignore-certificate-errors",  # 忽略 HTTPS 证书错误。
    "--ignore-certificate-errors-spki-list",  # 忽略指定 SPKI 证书错误。
    "--hide-crash-restore-bubble",  # 隐藏崩溃后恢复页面提示。
    "--disable-save-password-bubble",  # 禁用保存密码弹窗。
    "--disable-password-manager",  # 禁用浏览器密码管理器。
    "--lang=zh-CN",  # 设置浏览器语言为简体中文。
    "--hide-scrollbars",  # 隐藏页面滚动条。
    "--disable-dev-shm-usage",  # 禁用 /dev/shm，提升容器环境兼容性。
    "--disable-gpu",  # 禁用 GPU 加速，减少环境差异导致的问题。
    "--disable-prompt-on-repost",  # 禁用表单重复提交确认弹窗。
    "--disable-extensions",  # 禁用浏览器扩展。
    "--disable-background-networking",  # 禁用后台网络请求。
    "--disable-popup-blocking",  # 禁用弹窗拦截。
    "--test-type",  # 使用测试模式启动，减少自动化提示。
    "--disable-sync",  # 禁用 Chrome 账号同步。
    "--disable-password-generation",  # 禁用自动生成密码功能。
    "--disable-password-manager-reauthentication",  # 禁用密码管理器二次认证。
    "--password-store=basic",  # 使用基础密码存储，避免系统钥匙串交互。
    "--disable-notifications",  # 禁用网页通知。
    "--safebrowsing-disable-download-protection",  # 禁用安全浏览的下载保护拦截。
    "--disable-features=AutofillServerCommunication,PasswordLeakDetection,PasswordManagerOnboarding,PasswordManagerRedesign,DownloadBubble,DownloadBubbleV2",  # 禁用自动填充、密码泄露检测、密码管理引导和下载气泡等功能。
]

DEFAULT_PREFS = {
    "download.prompt_for_download": False,  # 下载时不弹出保存位置确认框。
    "download.directory_upgrade": True,  # 允许自动升级或创建下载目录。
    "download.bubble.enabled": False,  # 禁用下载气泡提示。
    "download_bubble.partial_view_enabled": False,  # 禁用下载气泡的简化视图。
    "download.open_pdf_in_system_reader": False,  # 不使用系统阅读器打开 PDF。
    "download.restrictions": 0,  # 不限制文件下载。
    "plugins.always_open_pdf_externally": True,  # PDF 始终作为文件下载，不在浏览器内预览。
    "safebrowsing.enabled": False,  # 关闭安全浏览检查。
    "safebrowsing.download_protection.enabled": False,  # 关闭下载安全检查。
    "profile.default_content_setting_values.insecure_content": 1,  # 允许加载不安全内容。
    "profile.content_settings.exceptions.automatic_downloads": {  # 允许所有站点自动连续下载多个文件。
        "[*,*]": {"setting": 1},
    },
    "credentials_enable_service": False,  # 禁用凭据保存服务。
    "profile.password_manager_enabled": False,  # 禁用密码管理器。
    "profile.password_manager_leak_detection": False,  # 禁用密码泄露检测。
    "profile.default_content_setting_values.password_manager": 2,  # 默认阻止站点使用密码管理能力。
    "profile.content_settings.exceptions.password_manager": {  # 对所有站点禁用密码管理器。
        "[*,*]": {"setting": 2},
    },
    "profile.default_content_settings.popups": 0,  # 允许弹窗。
    "credentials_enable_autosignin": False,  # 禁用自动登录。
    "autofill.credit_card_enabled": False,  # 禁用信用卡自动填充。
    "autofill.profile_enabled": False,  # 禁用地址等个人资料自动填充。
    "password_manager.account_storage_enabled": False,  # 禁用账号级密码存储。
    "password_manager.allow_saving": False,  # 禁止保存密码。
    "password_manager.auto_signin": False,  # 禁用密码管理器自动登录。
    "password_manager.saving_enabled": False,  # 禁用密码保存能力。
    "profile.default_content_setting_values.automatic_downloads": 1,  # 默认允许自动下载多个文件。
    "signin.allowed": False,  # 禁止浏览器登录账号。
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
