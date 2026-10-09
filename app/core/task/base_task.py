import json
import platform
from pathlib import Path

from DrissionPage._elements.none_element import NoneElement
from DrissionPage._pages.chromium_base import ChromiumBase 

from app.core.integrations.notifier import ProcessingNotifier
from app.core.integrations.oss import OssClient
from app.core.integrations.publisher import ResultPublisher
from app.core.integrations.redis_client import get_redis_db_client
from app.core.page.recorder import Recorder
from app.core.page.http import HttpHelper
from app.core.page.dom import DomHelper
from app.core.page.screenshot import Screenshot
from app.core.task.errors import BusinessError, ElementNotFoundError, FormValidationError, LoginError
from app.core.task.errors import ResultPublishError, UnfilledFieldError
from app.core.task.result import TaskResult
from app.core.task.context import TaskContext
from app.core.logging.logger import Logger
from app.core.browser.manager import BrowserManager



VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def infer_media_type(file_path) -> str:
    """按后缀推断 mediaType：视频后缀 → VIDEO，否则 IMAGE。"""
    return "VIDEO" if Path(file_path).suffix.lower() in VIDEO_SUFFIXES else "IMAGE"


class BaseRpaTask:
    """RPA 任务生命周期基类。"""

    enable_record = True #是否开启录屏
    incognito = False #是否开启无痕模式
    wait_page_load = False #是否等待页面加载完成
    use_proxy = False #是否使用代理
    # booking_no = ""
    ignored_unfilled_fields = [
        "carrier", "isUserSave", "blNo", "jobNo", "bookingNo"
    ]
    REDIS_MAIN= 15 # redis 索引(默认15)
    REDIS_HEART_BEAT = 8
    MAX_RECORDING_UPLOAD_SIZE = 10 * 1024 * 1024

    page: ChromiumBase = None # 页面实例



    def __init__(
        self,
        context,
        *,
        browser_manager=None,
        notifier=None,
        publisher=None,
        oss_client=None,
    ):
        self.context = context or TaskContext()
        self.job_no = self.context.content.get("jobNo") or self.context.content.get("blNo") or ""
        self.website_info = self.context.website_info # 账号信息
        self.remain_content = self.context.remain_content
        self.page = None
        self.screenshot = None
        self.recorder = None
        self.dom = None
        self.http = None
        # 这些集合必须是实例属性，避免复用 Worker 时串到下一条消息。
        self.attachments = []
        self.business_record_files = []
        self.result_save_type = 1
        # 日志服务终态/记录文件采集（§6.4，仅旁路上报，不影响回传协议）
        self.fail_img_object_name = "" # 失败截图 objectName（查看页经 /v1/file/url 换临时地址）
        # 拍平的记录文件 [{type, mediaType, fileName, objectName|remark, storage, fileSize}]
        # 录屏与截图统一存 objectName（查看页面经 /v1/file/url?objectName= 换临时地址）；
        # 上传失败的文件存 remark=“上传oss失败 xxx本地路径:xxx” 且 storage=LOCAL。
        self.log_record_files = []

        # 附件属于单次任务，不能与同一进程中的其他任务共享。
        self.logger = Logger()
        self.notifier = notifier or ProcessingNotifier() #通知消息实例
        self.publisher = publisher or ResultPublisher() #发布消息实例
        self.oss_client = oss_client or OssClient() #oss客户端实例
        # 截图/视频统一仅 OSS 上传；失败一律保留本地文件，不再降级局域网。
        self.util_redis = get_redis_db_client(self.REDIS_MAIN) # 配置cookies redis客户端实例
        self.redis_client = get_redis_db_client(self.REDIS_HEART_BEAT) # 配置proxy redis客户端实例

        self.browser_lease = getattr(self.context, "browser_lease", None)
        self.account_session_coordinator = getattr(
            self.context, "account_session_coordinator", None
        )

        self.browser_manager = browser_manager or BrowserManager(
            browser_lease=self.browser_lease,
            account_session_coordinator=self.account_session_coordinator,
        )
        


    def run(self):
        """执行完整任务生命周期。"""
        success = False
        code = 0
        screenshot_img = ""
        remark = ""
        try:
            # 任务开始通知消息
            if self.context.enable_notify:
                self.notifier.notify_processing(self.context)
            # 获取浏览器端口并获取初始化页面
            self.page = self.browser_manager.start(self.context, self)
            # 初始化dom助手
            self.dom = DomHelper(
                self.page,
                download_dir=self.browser_manager.settings.download_dir,
                queue_name=self.context.queue_name,
                rpa_message_id=self.context.rpa_message_id,
            )
            # 初始化http助手
            self.http = HttpHelper(self.page)
            # 初始化截图助手
            self.screenshot = Screenshot(self.page)
            # 执行登录 登录完成后释放登录锁
            login_success = False
            try:
                self.login()
                login_success = True
            finally:
                # 通知登录完成放开登录锁
                self._notify_login_finished(login_success)

            # 开启录屏
            self._try_start_recording()
            # 执行业务逻辑
            self.execute_business()
            self.logger.info(f"任务执行成功 queue={self.context.queue_name}")
            success = True
            code = 200
        except Exception as exc:
            self.logger.error(f"任务执行失败 queue={self.context.queue_name} error={exc}")
            success = False
            code = getattr(exc, "code", 500)
            remark = str(exc)
            # 上传错误截图
            if self.context.enable_result_publish:
                screenshot_img = self._upload_error_screenshot()
        finally:
            # 收集录屏文件
            execute_record_files = self._collect_record_files()
            # 日志服务终态上报（§6.4）：无会话时 no-op，内部全降级，不影响回传
            self.logger.finish_execution(
                success=success,
                remark=remark,
                fail_img_object_name=self.fail_img_object_name,
                record_files=self.log_record_files,
            )
            attachments = None
            if self.context.enable_result_publish:
                # 上传草稿件
                if success or len(self.attachments) > 0:
                    attachments = self._get_attachments_safely(execute_record_files)
                # 发送任务结束结果
                result = TaskResult(
                    task_id=self.context.task_id or "",
                    success=success,
                    code=code,
                    rpaMessageId=self.context.rpa_message_id,
                    saveType=self.get_result_save_type(),
                    img=screenshot_img or "",
                    executeRecordFiles=execute_record_files,
                    remark=remark,
                    attachments=attachments or None,
                )
                try:
                    self.publisher.publish_result(result)
                except Exception as exc:
                    self.logger.error(
                        f"任务结果回传失败 task_id={result.task_id} "
                        f"rpaMessageId={result.rpaMessageId} error={exc}"
                    )
                    raise ResultPublishError("任务结果回传失败") from exc
            self.logger.info("任务结束，保留浏览器进程以便后续接管")
            return success

    def _try_start_recording(self):
        """尽力启动录屏，失败时不影响业务执行。"""
        if not self.should_record():
            return
        try:
            self.recorder = Recorder(
                self.page,
                queue_name=self.context.queue_name,
                job_no=self.job_no,
            )
            self.recorder.start()
        except Exception as exc:
            self.recorder = None
            self.logger.error(f"录屏启动失败，继续执行业务：{exc}")

    def _collect_record_files(self):
        """汇总业务截图和录屏，单个文件上传失败不影响任务回传。"""
        record_files = self._collect_business_record_files()
        if self.recorder is None:
            return record_files
        try:
            record_file_path = self.recorder.stop()
            if record_file_path is None:
                return record_files
            record_file_path = Path(record_file_path)
            upload = self._upload_execute_video(record_file_path)
            if upload is None:
                # OSS 上传失败：视频保留本地（不降级局域网），失败信息记入日志服务，
                # 查看页面可凭本地路径人工补取。
                self.log_record_files.append({
                    "type": "SCREEN_RECORDING_FILE",
                    "mediaType": infer_media_type(record_file_path),
                    "fileName": record_file_path.name,
                    "storage": "LOCAL",
                    "fileSize": self._safe_file_size(record_file_path),
                    "remark": f"上传oss失败 视频本地路径:{record_file_path}",
                })
                return record_files
            # 结果回传协议保持现状：仅 OSS 上传成功的录屏进入 executeRecordFiles
            record_files.append({
                "type": "SCREEN_RECORDING_FILE",
                "files": [{
                    "fileObjectName": upload["objectName"],
                    "fileName": upload.get("fileName") or record_file_path.name,
                }],
            })
            # 日志服务旁路记录：存 objectName（不再存 url）；查看页面经
            # /v1/file/url?objectName={objectName} 换取带签名的临时访问地址。
            self.log_record_files.append({
                "type": "SCREEN_RECORDING_FILE",
                "mediaType": infer_media_type(record_file_path),
                "fileName": upload.get("fileName") or record_file_path.name,
                "objectName": upload["objectName"],
                "storage": "OSS",
                "fileSize": upload.get("fileSize", 0),
            })
            return record_files
        except Exception as exc:
            self.logger.error(f"录屏停止或上传失败，继续回传业务结果：{exc}")
            return record_files

    def add_business_record_file(self, record_type, file_path):
        """登记业务过程文件，任务结束时统一上传并写入执行记录。"""
        self.business_record_files.append((record_type, file_path))

    def capture_business_screenshot(self, record_type, suffix=""):
        """截取业务过程页面并登记为指定类型的执行记录文件。"""
        if not self.context.enable_result_publish:
            return None
        job_type = getattr(self, "job_type", "")
        if suffix:
            job_type = f"{job_type}_{suffix}" if job_type else suffix
        file_path = self.screenshot.page_shot(
            self.job_no,
            job_type,
            error=False,
        )
        self.add_business_record_file(record_type, file_path)
        return file_path

    def _collect_business_record_files(self):
        """按记录类型上传业务过程文件，保持结果协议的 files 分组结构。

        上传链路：仅 OSS；OSS 失败则文件保留本地（不降级局域网），
        失败信息记入日志服务记录，不进结果回传协议。
        """
        grouped_files = {}
        for record_type, file_path in self.business_record_files:
            file_size = self._safe_file_size(file_path)
            try:
                file_info = self.oss_client.oss_upload(file_path)
            except Exception as exc:
                self.logger.error(f"上传业务过程文件失败 type={record_type} error={exc}，文件保留本地")
                file_info = None

            if isinstance(file_info, dict) and file_info.get("objectName"):
                grouped_files.setdefault(record_type, []).append({
                    "fileObjectName": file_info["objectName"],
                    "fileName": Path(file_path).name,
                })
                # 日志服务旁路记录：截图与录屏一致存 objectName（不再存 url）；
                # 查看页面经 /v1/file/url?objectName={objectName} 换临时地址。
                self.log_record_files.append({
                    "type": record_type,
                    "mediaType": infer_media_type(file_path),
                    "fileName": Path(file_path).name,
                    "objectName": file_info["objectName"],
                    "storage": "OSS",
                    "fileSize": file_size,
                })
                continue

            # OSS 失败：本地保留，仅记日志服务（不进结果回传协议）
            self.log_record_files.append({
                "type": record_type,
                "mediaType": infer_media_type(file_path),
                "fileName": Path(file_path).name,
                "storage": "LOCAL",
                "fileSize": file_size,
                "remark": f"上传oss失败 文件本地路径:{file_path}",
            })
        return [
            {"type": record_type, "files": files}
            for record_type, files in grouped_files.items()
            if files
        ]

    def _safe_file_size(self, file_path) -> int:
        """尽力读取文件大小，失败返回 0。"""
        try:
            return Path(file_path).stat().st_size
        except Exception:
            return 0

    def _upload_execute_video(self, record_file_path):
        """录屏上传：仅 OSS（成功才删本地）；失败或超 10MB 不再降级局域网。

        视频保留在本地，由调用方把失败信息（上传oss失败 视频本地路径:xxx）
        记入日志服务记录；返回 ``{objectName, fileName, url, storage, fileSize}``，
        失败返回 None。
        """
        record_file_path = Path(record_file_path)
        file_name = record_file_path.name
        try:
            file_size = record_file_path.stat().st_size
        except Exception as exc:
            self.logger.error(f"读取录屏文件大小失败，本地录屏已保留：{exc}")
            return None

        if file_size > self.MAX_RECORDING_UPLOAD_SIZE:
            self.logger.warn(
                f"录屏文件超过 {self.MAX_RECORDING_UPLOAD_SIZE / (1024 * 1024):g}MB，"
                f"跳过 OSS 上传，视频保留本地：{record_file_path}"
            )
            self.logger.error(f"上传oss失败 视频本地路径:{record_file_path}")
            return None

        try:
            oss_file_info = self.oss_client.oss_upload(record_file_path, is_remove=False)
            if not (isinstance(oss_file_info, dict) and oss_file_info.get("objectName")):
                self.logger.error(f"上传流程视频 OSS 未返回 objectName，视频保留本地：{record_file_path}")
                self.logger.error(f"上传oss失败 视频本地路径:{record_file_path}")
                return None
        except Exception as exc:
            self.logger.error(f"上传流程视频 OSS 失败：{exc}")
            self.logger.error(f"上传oss失败 视频本地路径:{record_file_path}")
            return None

        self._remove_local_file(record_file_path)
        return {
            "objectName": oss_file_info["objectName"],
            "fileName": oss_file_info.get("filename") or file_name,
            "url": oss_file_info.get("url") or "",
            "storage": "OSS",
            "fileSize": file_size,
        }

    def _remove_local_file(self, file_path):
        """上传成功后清理本地文件；删除失败仅告警。"""
        try:
            Path(file_path).unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            self.logger.error(f"上传成功但删除本地文件失败 path={file_path} error={exc}")

    def _upload_error_screenshot(self):
        """尽力上传失败截图，不覆盖触发任务失败的原始异常。

        仅 OSS 上传；失败则截图保留本地并返回空串（``fail_img_object_name`` 同样置空）；
        ``TaskResult.img`` 与日志服务 ``failImgObjectName`` 均存 objectName，
        查看页面经 /v1/file/url?objectName= 换临时地址，回传协议零改动。
        """
        self.fail_img_object_name = ""
        if self.screenshot is None:
            self.logger.warn("截图工具未初始化，跳过失败截图")
            return ""

        file_path = None
        try:
            file_path = self.screenshot.page_shot(
                self.job_no,
                getattr(self, "job_type", ""),
                error=True,
            )
        except Exception as exc:
            self.logger.error(f"失败截图截取失败：{exc}")
            return ""

        try:
            file_info = self.oss_client.oss_upload(file_path)
        except Exception as exc:
            self.logger.error(f"失败截图 OSS 上传失败，截图保留本地：{exc}")
            return ""

        if isinstance(file_info, dict) and file_info.get("objectName"):
            self.fail_img_object_name = file_info["objectName"]
            return file_info["objectName"]
        return ""

    def _get_attachments_safely(self, execute_record_files):
        """尽力生成附件，不让附件上传错误覆盖任务执行结果。"""
        try:
            return self.get_result_attachments(execute_record_files)
        except Exception as exc:
            self.logger.error(f"任务附件上传失败：{exc}")
            return None

    def get_result_save_type(self):
        """返回任务结果的保存类型，子类可在业务完成后按客户策略覆盖。"""
        return self.result_save_type

    def should_record(self):
        """按业务开关录制并回传视频；支持 Windows 与 macOS。"""
        return bool(
            self.enable_record
            and self.context.enable_result_publish
            and platform.system() in {"Windows", "Darwin"}
        )

    def login(self):
        """船司登录，由船司基类实现。"""
        print(f"执行 {self.carrier_code} 登录入口")
        raise LoginError("子类必须实现 login 方法")

    def claim_credential_login(self) -> bool:
        """同一账号同一时间只允许一个任务提交登录凭证。"""
        if not self.browser_lease or self.account_session_coordinator is None:
            return True
        result = self.account_session_coordinator.claim_credential_login(
            self.browser_lease["account_key"],
            self.browser_lease["lease_id"],
            int(self.browser_lease.get("login_generation", 0)),
        )
        self.browser_lease["login_generation"] = result["login_generation"]
        return bool(result["is_leader"])

    def _notify_login_finished(self, success: bool) -> None:
        if not self.browser_lease or self.account_session_coordinator is None:
            return
        try:
            self.account_session_coordinator.login_finished(
                self.browser_lease["account_key"],
                self.browser_lease["lease_id"],
                success,
            )
        except Exception as exc:
            self.logger.error(f"上报登录状态失败：{exc}")

    def execute_business(self):
        """执行业务填单，由具体业务类实现。"""
        raise BusinessError("子类必须实现 execute_business 方法")

    def mark_field_done(self, field_name,source=None):
        """字段填入成功后，从 remain_content 删除。"""
        source = self.remain_content if source is None else source
        source.pop(field_name, None)

    def raise_if_unfilled_fields(self, stage="填单流程"):
        """在具体填单阶段主动触发未填字段校验。"""
        ignored_fields = set(self.ignored_unfilled_fields or [])
        unfilled_fields = [
            field_name
            for field_name in self.context.remain_content.keys()
            if field_name not in ignored_fields
        ]
        if unfilled_fields:
            self.logger.warn(f"存在未处理字段：{unfilled_fields}")
            raise UnfilledFieldError(f"{stage}存在漏填字段：{unfilled_fields}")
        return unfilled_fields



    def get_result_attachments(self, execute_record_files):
        """生成回传附件，子类可利用已上传的执行记录构造业务草稿件。"""
        return self.get_attachments()

    def get_attachments(self):
        """上传本地草稿件；远程已上传的 JSON 附件直接原样透传。"""
        attachments = []
        for attachment in self.attachments:
            # 远程接口预先上传后的草稿件是结构化 JSON，内部包含已上传的 objectName。
            if isinstance(attachment, dict):
                attachments.append(attachment.copy())
                continue

            file_info = self.oss_client.oss_upload(attachment)
            attachments.append({
                "fileName": file_info['filename'],
                "type": "DRAFT",
                "fileObjectName": file_info['objectName']
            })
        return attachments
        # if self.attachments:
            # self.publisher.publish_attachments(self.attachments)
            # self.attachments = {}

    def save_cookies(self, cookies_redis_key, expire_hours=None):
        """保存浏览器 cookies。

        expire_hours: Redis 失效时间（小时）。不传则不过期。
        """
        cookies = self.page.cookies()
        payload = json.dumps({"cookies": cookies}, ensure_ascii=False)
        if expire_hours is None:
            self.util_redis.set(cookies_redis_key, payload)
        else:
            self.util_redis.set(cookies_redis_key, payload, ex=int(expire_hours * 3600))

    def set_page_cookies(self, cookies_redis_key):
        """设置浏览器 cookies。"""
        cookies_str = self.util_redis.get(cookies_redis_key)
        if not cookies_str:
            return
        cookies = json.loads(cookies_str)
        # 兼容两种格式：如果是字典且包含cookies键则取其值，否则直接使用原始cookies
        cookies = cookies["cookies"] if isinstance(cookies, dict) and "cookies" in cookies else cookies
        self.page.set.cookies(cookies)
