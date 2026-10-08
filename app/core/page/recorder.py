from __future__ import annotations

from base64 import b64decode
from datetime import datetime
from pathlib import Path
import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Callable

from app.core.browser.window import (
    browser_hwnd_from_page,
    browser_pid_from_page,
    browser_window_rect,
    ensure_browser_window_ready,
)
from app.core.logging.logger import log


CREATE_NO_WINDOW = 0x08000000
_ENCODER_CACHE: dict[str, list[str]] = {}


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() or (parent / "capturesdk").is_dir():
            return parent
    return here.parents[3]


REPO_ROOT = _repo_root()


class RecorderError(RuntimeError):
    """Raised when screen recording cannot start, stop, or finalize."""


class Recorder:
    """跨平台录屏控制器。

    默认优先走浏览器 CDP screencast（Page.startScreencast JPEG 帧 → FFmpeg
    image2pipe 合成 H264）：像素来自浏览器自身渲染管线，不经过 GDI/DWM/D3D11，
    与显卡驱动和系统采集层解耦，Win10 家庭版/专业版、Win11、macOS 行为一致；
    页面被遮挡或无人值守锁屏时页面内容仍可录。

    auto 降级链：CDP screencast → FFmpeg OS 采集（Windows=gdigrab GDI 软件采集，
    macOS=avfoundation）。旧 CaptureSDK/WGC 仅在 CAPTURE_BACKEND=cli|wgc 时启用。

    浏览器只在页面重绘时推送 screencast 帧，静止页面长时间无帧会导致视频时长
    失真，因此 Python 侧按 CAPTURE_FPS 限流丢帧，并由后台线程按帧间隔重复最后
    一帧，保证视频时长与真实执行时长一致。

    输出为 CRF 控制的 H264 MP4（无音频，+faststart），体积远小于 1080p/2500kbps
    码率模式。
    """

    def __init__(
        self,
        page: Any | None = None,
        *,
        record_dir: str | Path = "runtime/records",
        queue_name: str = "task",
        job_no: str = "",
    ) -> None:
        self.page = page
        now = datetime.now()
        date_dir = now.strftime("%Y-%m-%d")
        safe_queue_name = _safe_filename(queue_name, "task")
        safe_job_no = _safe_filename(job_no, "unknown")
        # 输出路径必须绝对化：popen_ffmpeg 会把 ffmpeg 的 cwd 切到二进制所在目录
        # （imageio-ffmpeg 的 binaries 目录等），相对路径会写到错误的磁盘位置。
        self.record_dir = Path(record_dir).absolute() / date_dir / safe_queue_name
        self.record_dir.mkdir(parents=True, exist_ok=True)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        self.file_path = self.record_dir / f"{safe_queue_name}_{safe_job_no}_{timestamp}.mp4"
        self.backend: str | None = None
        self._process: subprocess.Popen | None = None
        self._cli_session: Any | None = None
        self._stdin_lock = threading.Lock()
        self._cdp_enabled = False
        # CDP 帧节奏：限制写入频率 + 静止时重复最后一帧，保证时长与真实执行一致。
        self._frame_interval = 1.0 / max(1, _env_int("CAPTURE_FPS", 5))
        self._last_frame: bytes | None = None
        self._last_write_at: float | None = None
        self._keepalive_stop = threading.Event()
        self._keepalive_thread: threading.Thread | None = None
        # ack 的裸 websocket 消息 id：避开 DrissionPage 自己的 _cur_id 空间。
        self._ack_id = 900_000_000
        # WGC（windows-capture 包）采集会话状态。
        self._wgc_control: Any = None
        self._wgc_internal_control: Any = None
        self._wgc_hwnd: int | None = None
        self._wgc_size: tuple[int, int] | None = None
        self._wgc_closed = False
        self._wgc_first_frame = threading.Event()
        self._wgc_first_data: tuple[bytes, int, int] | None = None

    def start(self) -> "Recorder":
        """开始录屏。"""
        if self.is_running():
            return self
        if self.page is None:
            raise RecorderError("录屏启动失败：page 不能为空。")

        errors: list[str] = []
        for name, starter in self._backend_starters():
            try:
                starter()
                self.backend = name
                log(f"录屏已开始 backend={name} path={self.file_path}")
                return self
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                log(f"录屏后端 {name} 启动失败，尝试下一个：{exc}")
                self._reset_failed_backend()

        raise RecorderError("录屏启动失败：" + " | ".join(errors))

    def stop(self) -> Path | None:
        """停止录屏。"""
        if not self.is_running():
            return None
        backend = self.backend
        if self._cli_session is not None:
            result = self._cli_session.stop()
            self._cli_session = None
            output = Path(result.output_path)
        else:
            output = self._stop_ffmpeg()

        if not output.is_file() or output.stat().st_size == 0:
            raise RecorderError(f"录屏输出文件无效：{output}")
        log(f"录屏已停止 backend={backend} path={output}")
        self.backend = None
        return output

    def is_running(self) -> bool:
        """录屏是否正在运行。"""
        if self._cli_session is not None:
            return bool(self._cli_session.is_running)
        return bool(self._process is not None and self._process.poll() is None)

    def _backend_starters(self) -> list[tuple[str, Callable[[], None]]]:
        requested = os.getenv("CAPTURE_BACKEND", "auto").strip().lower() or "auto"
        mapping = {
            "gdi": [("ffmpeg", self._start_ffmpeg_os)],
            "ffmpeg": [("ffmpeg", self._start_ffmpeg_os)],
            "avfoundation": [("ffmpeg", self._start_ffmpeg_os)],
            "cdp": [("cdp", self._start_cdp)],
            "browser": [("cdp", self._start_cdp)],
            # wgc = 原生 Windows Graphics Capture（windows-capture 包，Win10 1903+）。
            "wgc": [("wgc", self._start_wgc)],
            # 旧 CaptureSDK（CLI 子进程）保留别名，避免旧配置失效。
            "cli": [("cli", self._start_cli)],
            "capturesdk": [("cli", self._start_cli)],
            "wgcsdk": [("cli", self._start_cli)],
        }
        if requested in mapping:
            return mapping[requested]
        # auto：CDP screencast 优先（不依赖显卡/OS 采集层，兼容性最好），
        # 失败再降级 FFmpeg OS 采集（需要 OS 级画面或浏览器不支持 screencast 时）。
        return [("cdp", self._start_cdp), ("ffmpeg", self._start_ffmpeg_os)]

    def _start_ffmpeg_os(self) -> None:
        ffmpeg = resolve_ffmpeg_path()
        system = platform.system()
        if system not in {"Windows", "Darwin"}:
            raise RecorderError(f"当前系统不支持 OS 采集：{system}")

        hwnd = ensure_browser_window_ready(self.page, pid=browser_pid_from_page(self.page))
        crop = None
        if _env_flag("CAPTURE_CROP_WINDOW", True) and system == "Windows":
            crop = browser_window_rect(self.page, hwnd=hwnd)

        encoder_args = h264_encoder_args(ffmpeg, _env_int("CAPTURE_VIDEO_CRF", 28))
        fps = _env_int("CAPTURE_FPS", 5)
        scale = os.getenv("CAPTURE_VIDEO_SCALE", "1280:-2")
        screen_device = _macos_screen_device(ffmpeg) if system == "Darwin" else None
        attempts: list[tuple[int | None, tuple[int, int, int, int] | None]] = []
        if system == "Windows" and hwnd:
            attempts.append((int(hwnd), None))
        if system == "Windows" and crop:
            attempts.append((None, crop))
        attempts.append((None, None))

        last_error: Exception | None = None
        seen: set[tuple[int | None, tuple[int, int, int, int] | None]] = set()
        for hwnd_value, crop_value in attempts:
            key = (hwnd_value, crop_value)
            if key in seen:
                continue
            seen.add(key)
            try:
                command = build_os_capture_command(
                    ffmpeg=ffmpeg,
                    output=self.file_path,
                    system=system,
                    fps=fps,
                    scale=scale,
                    crop=crop_value,
                    hwnd=hwnd_value,
                    encoder_args=encoder_args,
                    screen_device=screen_device,
                )
                self._process = popen_ffmpeg(command, stdin=subprocess.PIPE)
                self._ensure_process_running("FFmpeg OS 采集")
                return
            except Exception as exc:
                last_error = exc
                log(f"FFmpeg OS 采集尝试失败 hwnd={hwnd_value} crop={crop_value}：{exc}")
                self._reset_failed_backend()
        raise RecorderError(str(last_error) if last_error else "FFmpeg OS 采集启动失败")

    def _start_cdp(self) -> None:
        ffmpeg = resolve_ffmpeg_path()
        if self.page is None:
            raise RecorderError("录屏启动失败：page 不能为空。")

        fps = _env_int("CAPTURE_FPS", 5)
        command = build_image_pipe_command(
            ffmpeg=ffmpeg,
            output=self.file_path,
            fps=fps,
            scale=os.getenv("CAPTURE_VIDEO_SCALE", "1280:-2"),
            encoder_args=h264_encoder_args(ffmpeg, _env_int("CAPTURE_VIDEO_CRF", 28)),
        )
        self._process = popen_ffmpeg(command, stdin=subprocess.PIPE)
        self._ensure_process_running("FFmpeg image2pipe")
        self._frame_interval = 1.0 / max(1, fps)
        self._start_screencast()
        self._write_cdp_screenshot()
        self._start_keepalive()

    def _start_cli(self) -> None:
        from capturesdk import CaptureSDKClient, CaptureSDKError

        client = CaptureSDKClient()
        browser_pid = browser_pid_from_page(self.page)
        if not browser_pid:
            raise CaptureSDKError("DrissionPage 未暴露浏览器 PID，无法使用 WGC 录屏。")
        hwnd = client.wait_for_browser_hwnd(browser_pid, allow_first=True)
        ensure_browser_window_ready(hwnd=hwnd)
        self._cli_session = client.start(
            hwnd=hwnd,
            output=self.file_path,
            fps=_env_int("CAPTURE_FPS", 5),
            width=1280,
            height=720,
            bitrate_kbps=_env_int("CAPTURE_BITRATE_KBPS", 800),
            encoder="cpu",
        )

    def _start_screencast(self) -> None:
        driver = getattr(self.page, "driver", None)
        if driver is None or not hasattr(driver, "set_callback"):
            raise RecorderError("当前页面不支持 CDP screencast。")
        driver.set_callback("Page.screencastFrame", self._on_screencast_frame)
        params: dict[str, Any] = {"format": "jpeg", "quality": 45, "everyNthFrame": 2}
        max_width = _screencast_max_width()
        if max_width:
            # 浏览器端先缩到目标宽度，减小 JPEG 体积与传输开销。
            params["maxWidth"] = max_width
        self._run_cdp("Page.startScreencast", **params)
        self._cdp_enabled = True

    def _stop_screencast(self) -> None:
        self._stop_keepalive()
        if not self._cdp_enabled:
            return
        try:
            driver = getattr(self.page, "driver", None)
            if driver is not None and hasattr(driver, "set_callback"):
                driver.set_callback("Page.screencastFrame", None)
            self._run_cdp("Page.stopScreencast")
        except Exception as exc:
            log(f"停止 CDP screencast 失败，继续收尾：{exc}")
        self._cdp_enabled = False

    def _on_screencast_frame(self, **kwargs: Any) -> None:
        data = kwargs.get("data")
        session_id = kwargs.get("sessionId")
        if data:
            try:
                payload = b64decode(data)
                # 即使被限流丢弃，也更新最后一帧，让 keepalive 重复最新画面。
                with self._stdin_lock:
                    self._last_frame = payload
                self._write_jpeg(payload)
            except Exception:
                pass
        self._ack_screencast_frame(session_id)

    def _start_wgc(self) -> None:
        """Windows Graphics Capture 后端（windows-capture 包，Win10 1903+）。

        按浏览器窗口 HWND 采集窗口表面：能看到地址栏/标签页等整个浏览器，
        且遮挡、置底、被其他窗口覆盖都不影响画面（多浏览器并行友好）。
        帧为 BGRA 原始数据，经 rawvideo 管道送 ffmpeg 编码。
        """
        if platform.system() != "Windows":
            raise RecorderError("wgc 后端仅支持 Windows（Windows Graphics Capture）。")
        try:
            from windows_capture import WindowsCapture
        except ImportError as exc:
            raise RecorderError(
                "未安装 windows-capture 包，无法使用 wgc 后端：pip install windows-capture"
            ) from exc

        hwnd = browser_hwnd_from_page(self.page)
        if not hwnd:
            raise RecorderError(
                "未找到浏览器窗口 HWND（DrissionPage 未暴露浏览器 PID 或窗口不可见），无法启动 WGC 采集。"
            )
        self._wgc_hwnd = int(hwnd)

        fps = _env_int("CAPTURE_FPS", 5)
        self._frame_interval = 1.0 / max(1, fps)
        self._wgc_closed = False
        self._wgc_first_frame.clear()
        self._wgc_first_data = None

        interval_ms = max(1, int(self._frame_interval * 1000))
        try:
            capture = self._create_wgc_capture(hwnd, minimum_update_interval=interval_ms)
            self._wgc_control = capture.start_free_threaded()
        except Exception as exc:
            if "minimum update interval" not in str(exc).lower():
                raise
            # 旧系统（如 Win10）不支持 OS 侧节流（Win11 22H2+ 特性），去掉重试；
            # 帧率控制由 Python 侧限流兜底。
            log("本机不支持 minimum_update_interval，已改为仅 Python 侧限流。")
            capture = self._create_wgc_capture(hwnd)
            self._wgc_control = capture.start_free_threaded()

        # 探活：等首帧确认采集链路可用（显卡驱动不支持时会立刻 on_closed 或无帧）。
        deadline = time.monotonic() + 5.0
        while not self._wgc_first_frame.wait(0.2):
            if self._wgc_closed:
                break
            if time.monotonic() >= deadline:
                break
        if not self._wgc_first_frame.is_set() or self._wgc_first_data is None:
            reason = "采集会话已关闭（窗口无效）" if self._wgc_closed else "5 秒内未收到首帧"
            self._stop_wgc_capture()
            raise RecorderError(
                f"WGC 采集启动失败：{reason}。可能显卡驱动不支持 Windows Graphics Capture，"
                "可改用 CAPTURE_BACKEND=cdp。"
            )

        first_buf, width, height = self._wgc_first_data
        self._wgc_size = (width, height)
        ffmpeg = resolve_ffmpeg_path()
        command = build_rawvideo_command(
            ffmpeg=ffmpeg,
            output=self.file_path,
            fps=fps,
            size=(width, height),
            scale=os.getenv("CAPTURE_VIDEO_SCALE", "1280:-2"),
            encoder_args=h264_encoder_args(ffmpeg, _env_int("CAPTURE_VIDEO_CRF", 28)),
        )
        self._process = popen_ffmpeg(command, stdin=subprocess.PIPE)
        self._ensure_process_running("FFmpeg rawvideo")
        # 写入等待期间攒下的最新一帧，随后进入常规限流写。
        with self._stdin_lock:
            self._wgc_first_data = None
        self._write_raw_frame(first_buf, width, height)
        self._start_keepalive()

    def _create_wgc_capture(self, hwnd: int, minimum_update_interval: int | None = None) -> Any:
        """构造 WGC 采集会话（不启动），统一装配回调。"""
        from windows_capture import WindowsCapture

        kwargs: dict[str, Any] = dict(
            cursor_capture=_env_flag("CAPTURE_WGC_CURSOR", True),
            draw_border=_env_tri_flag("CAPTURE_WGC_DRAW_BORDER"),
            window_hwnd=int(hwnd),
        )
        if minimum_update_interval is not None:
            kwargs["minimum_update_interval"] = minimum_update_interval
        capture = WindowsCapture(**kwargs)
        capture.frame_handler = self._on_wgc_frame
        capture.closed_handler = self._on_wgc_closed
        return capture

    def _on_wgc_frame(self, frame: Any, capture_control: Any) -> None:
        """WGC 帧回调（运行在采集线程上）：拷贝像素后按帧间隔写入 rawvideo 管道。"""
        try:
            # 留存内部控制句柄：停止时可通过它让会话在下一帧后结束（Rust 侧
            # 只在帧回调返回后检查 stop 标志，静态画面下原生 stop 不总是生效）。
            self._wgc_internal_control = capture_control
            with self._stdin_lock:
                if not self._wgc_first_frame.is_set():
                    buffer = frame.frame_buffer.tobytes()  # 立即拷贝，原生缓冲区会被复用
                    self._wgc_first_data = (buffer, int(frame.width), int(frame.height))
                    self._wgc_first_frame.set()
                    return
            if self._wgc_size is None:
                return  # ffmpeg 尚未就绪
            # OS 侧无节流（旧系统）时帧率可能高达 30-60fps：先看节奏再拷贝，
            # 避免每帧 ~8MB 的无效 memcpy。
            now = time.monotonic()
            with self._stdin_lock:
                if self._last_write_at is not None and now - self._last_write_at < self._frame_interval:
                    return
            buffer = frame.frame_buffer.tobytes()
            self._write_raw_frame(buffer, int(frame.width), int(frame.height))
        except Exception:
            pass

    def _on_wgc_closed(self) -> None:
        self._wgc_closed = True
        log("WGC 采集会话已关闭（浏览器窗口可能已关闭），视频将冻结在最后一帧。")

    def _write_raw_frame(self, buffer: bytes, width: int, height: int) -> None:
        """写入一帧 BGRA 原始数据，按帧间隔限流（与 CDP 帧同一套节奏控制）。"""
        if self._wgc_size is None:
            return  # ffmpeg 尚未就绪，帧已在首帧缓冲里
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            return
        now = time.monotonic()
        with self._stdin_lock:
            if self._last_write_at is not None and now - self._last_write_at < self._frame_interval:
                return
            payload = self._fit_wgc_frame(buffer, width, height)
            if payload is None:
                return
            self._last_frame = payload
            process.stdin.write(payload)
            process.stdin.flush()
            self._last_write_at = time.monotonic()

    def _fit_wgc_frame(self, buffer: bytes, width: int, height: int) -> bytes | None:
        """窗口尺寸变化时裁剪/补黑边，保证 rawvideo 流尺寸恒定不花屏。"""
        target = self._wgc_size
        if target is None:
            return None
        target_w, target_h = target
        if (width, height) == target:
            return buffer
        import numpy as np

        frame = np.frombuffer(buffer, dtype=np.uint8)
        expected = width * height * 4
        if frame.size < expected:
            return None
        frame = frame[:expected].reshape(height, width, 4)
        canvas = np.zeros((target_h, target_w, 4), dtype=np.uint8)
        copy_h, copy_w = min(height, target_h), min(width, target_w)
        canvas[:copy_h, :copy_w] = frame[:copy_h, :copy_w]
        return canvas.tobytes()

    def _stop_wgc_capture(self) -> None:
        """双通道停止 WGC 采集会话，静止页面下强制一次窗口重绘保证 stop 生效。

        包的停止机制有两个（Rust 源码确认）：内部 stop 标志只在"下一帧回调
        返回后"被检查；原生 ``control.stop()`` 走线程消息泵。静态画面无新帧
        时两者都可能悬空，因此用 ``InvalidateRect`` 戳一下窗口制造一帧重绘，
        让 stop 标志被检查到，避免每次录制泄漏一个采集线程。
        """
        control = self._wgc_control
        self._wgc_control = None
        internal = self._wgc_internal_control
        self._wgc_internal_control = None
        if control is None and internal is None:
            return
        if internal is not None:
            try:
                internal.stop()
            except Exception:
                pass
        if control is not None:
            try:
                control.stop()
            except Exception:
                pass
        self._nudge_window_repaint()
        deadline = time.monotonic() + 2.0
        while not self._wgc_closed and time.monotonic() < deadline:
            time.sleep(0.05)
        if not self._wgc_closed:
            log("WGC 采集会话未在 2 秒内确认关闭（静态画面已知行为），继续收尾。")

    def _nudge_window_repaint(self) -> None:
        hwnd = self._wgc_hwnd
        if not hwnd or platform.system() != "Windows":
            return
        try:
            import ctypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.InvalidateRect(int(hwnd), None, True)
            user32.UpdateWindow(int(hwnd))
        except Exception:
            pass

    def _ack_screencast_frame(self, session_id: Any) -> None:
        """Ack 一帧 screencast。Chrome 流控要求 ack，否则出帧几次后即停。

        两个坑（macOS + DrissionPage 4.1 实测）：
        1. 不能走 ``driver.run()``：它把 ``sessionId`` 参数劫持到消息顶层，
           而 Chrome 只认 ``params.sessionId`` 形态的 ack；
        2. 不能同步等响应：回调运行在事件分发线程上，等待会卡死整条事件管线。
        因此用裸 websocket 发完即走；响应 id 不在 method_results 里，会被
        DrissionPage 的接收循环自然丢弃。
        """
        driver = getattr(self.page, "driver", None)
        ws = getattr(driver, "_ws", None)
        if ws is None:
            return
        try:
            self._ack_id += 1
            params: dict[str, Any] = {}
            if session_id is not None:
                params["sessionId"] = session_id
            ws.send(
                json.dumps(
                    {"id": self._ack_id, "method": "Page.screencastFrameAck", "params": params}
                )
            )
        except Exception:
            pass

    def _start_keepalive(self) -> None:
        """静止页面无 screencast 帧时按帧间隔重复最后一帧，保持视频时长。"""
        if self._keepalive_thread is not None and self._keepalive_thread.is_alive():
            return
        self._keepalive_stop.clear()
        thread = threading.Thread(
            target=self._keepalive_loop,
            name="recorder-cdp-keepalive",
            daemon=True,
        )
        thread.start()
        self._keepalive_thread = thread

    def _keepalive_loop(self) -> None:
        while not self._keepalive_stop.wait(self._frame_interval):
            frame = self._last_frame
            if frame is None:
                continue
            process = self._process
            if process is None or process.stdin is None or process.poll() is not None:
                return
            now = time.monotonic()
            with self._stdin_lock:
                if self._last_write_at is not None and now - self._last_write_at < self._frame_interval:
                    continue
                try:
                    process.stdin.write(frame)
                    process.stdin.flush()
                    self._last_write_at = time.monotonic()
                except Exception:
                    return

    def _stop_keepalive(self) -> None:
        self._keepalive_stop.set()
        thread = self._keepalive_thread
        self._keepalive_thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def _write_cdp_screenshot(self) -> None:
        try:
            result = self._run_cdp("Page.captureScreenshot", format="jpeg", quality=45)
            data = (result or {}).get("data")
            if data:
                self._write_jpeg(b64decode(data))
        except Exception as exc:
            log(f"CDP 首帧截图失败，等待 screencast 帧：{exc}")

    def _write_jpeg(self, payload: bytes) -> None:
        """写入一帧 JPEG，按帧间隔限流，避免重绘风暴把视频时长拉长。"""
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            return
        now = time.monotonic()
        with self._stdin_lock:
            if self._last_write_at is not None and now - self._last_write_at < self._frame_interval:
                return
            process.stdin.write(payload)
            process.stdin.flush()
            self._last_frame = payload
            self._last_write_at = time.monotonic()

    def _run_cdp(self, command: str, **kwargs: Any) -> Any:
        runner = getattr(self.page, "_run_cdp", None) or getattr(self.page, "run_cdp", None)
        if runner is None:
            raise RecorderError("当前页面不支持 CDP 命令。")
        return runner(command, **kwargs)

    def _stop_ffmpeg(self) -> Path:
        process = self._process
        self._process = None
        if process is None:
            return self.file_path

        self._stop_screencast()
        self._stop_wgc_capture()
        try:
            if process.stdin is not None:
                if self.backend in {"cdp", "wgc"}:
                    # stdin 是帧数据管道（image2pipe/rawvideo），只能 EOF 收尾；
                    # 写 "q" 会被当作帧数据产生花屏。
                    process.stdin.close()
                else:
                    process.stdin.write(b"q\n")
                    process.stdin.flush()
                    process.stdin.close()
                # POSIX 上 communicate() 会 flush 仍挂着的 stdin，关闭后必须摘掉引用。
                process.stdin = None
        except Exception:
            process.kill()

        try:
            stdout, stderr = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            raise RecorderError(
                "FFmpeg 未能在 30 秒内结束录屏。"
                f"\nstdout:\n{_decode(stdout)}\nstderr:\n{_decode(stderr)}"
            )

        if process.returncode not in (0, None) and not (
            self.file_path.is_file() and self.file_path.stat().st_size > 0
        ):
            raise RecorderError(
                f"FFmpeg 退出码 {process.returncode}。"
                f"\nstdout:\n{_decode(stdout)}\nstderr:\n{_decode(stderr)}"
            )
        return self.file_path

    def _ensure_process_running(self, label: str, timeout_seconds: float = 0.4) -> None:
        process = self._process
        if process is None:
            raise RecorderError(f"{label} 进程未启动。")
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                self._process = None
                raise RecorderError(
                    f"{label} 启动后立即退出，退出码 {process.returncode}。"
                    f"\nstdout:\n{_decode(stdout)}\nstderr:\n{_decode(stderr)}"
                )
            time.sleep(0.1)

    def _reset_failed_backend(self) -> None:
        self._stop_screencast()
        self._stop_wgc_capture()
        process = self._process
        self._process = None
        self._cli_session = None
        if process is not None and process.poll() is None:
            try:
                process.kill()
                process.communicate(timeout=3)
            except Exception:
                pass
        if self.file_path.exists() and self.file_path.stat().st_size == 0:
            try:
                self.file_path.unlink()
            except OSError:
                pass


def resolve_ffmpeg_path() -> Path:
    """Locate a usable ffmpeg binary, skipping candidates that cannot execute.

    捆绑的共享 DLL 版 ffmpeg 在缺少 VC++ 运行库的机器（典型：干净的 Win10
    家庭版）上会启动失败，这里对每个候选执行 ``-version`` 校验，坏的可执行
    文件自动跳过，依次落到 PATH 上的 ffmpeg 或 imageio-ffmpeg 的静态构建。
    """
    env_path = os.getenv("FFMPEG_PATH") or os.getenv("CAPTURE_FFMPEG")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path).expanduser())
    if platform.system() == "Windows":
        candidates.append(REPO_ROOT / "capturesdk" / "third_party" / "ffmpeg" / "bin" / "ffmpeg.exe")
    else:
        candidates.append(REPO_ROOT / "capturesdk" / "third_party" / "ffmpeg" / "bin" / "ffmpeg")
    which = shutil.which("ffmpeg")
    if which:
        candidates.append(Path(which))
    try:
        import imageio_ffmpeg

        candidates.append(Path(imageio_ffmpeg.get_ffmpeg_exe()))
    except Exception:
        pass

    seen: set[str] = set()
    broken: list[str] = []
    for candidate in candidates:
        resolved = str(candidate)
        if resolved in seen:
            continue
        seen.add(resolved)
        if not candidate.is_file():
            continue
        if os.name != "nt" and not os.access(candidate, os.X_OK):
            continue
        if not _ffmpeg_executes(candidate):
            broken.append(resolved)
            continue
        return candidate
    detail = f"以下候选无法执行：{'、'.join(broken)}。" if broken else ""
    raise RecorderError(
        "未找到可用的 ffmpeg。请安装 ffmpeg，或设置 FFMPEG_PATH，"
        "Windows 也可使用 capturesdk/third_party/ffmpeg/bin/ffmpeg.exe。"
        + detail
    )


def h264_encoder_args(ffmpeg: Path, crf: int = 28) -> list[str]:
    """Return H264 encoder arguments, preferring small CRF files."""
    cache_key = str(ffmpeg)
    if cache_key not in _ENCODER_CACHE:
        _ENCODER_CACHE[cache_key] = _probe_h264_encoder(ffmpeg)
    encoder = _ENCODER_CACHE[cache_key]
    if encoder == ["libx264"]:
        return [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
        ]
    if encoder == ["h264_mf"]:
        return ["-c:v", "h264_mf", "-b:v", _crf_to_bitrate(crf), "-pix_fmt", "yuv420p"]
    if encoder == ["libopenh264"]:
        return ["-c:v", "libopenh264", "-b:v", _crf_to_bitrate(crf), "-pix_fmt", "yuv420p"]
    raise RecorderError("ffmpeg 不支持 H264 编码，无法生成可在浏览器播放的 MP4。")


def build_os_capture_command(
    *,
    ffmpeg: Path,
    output: Path,
    system: str,
    fps: int,
    scale: str,
    encoder_args: list[str],
    crop: tuple[int, int, int, int] | None = None,
    hwnd: int | None = None,
    screen_device: str | None = None,
) -> list[str]:
    """Build an FFmpeg command that captures the OS screen."""
    command = [str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error", "-stats"]
    if system == "Windows":
        command.extend(["-f", "gdigrab", "-framerate", str(fps), "-draw_mouse", "1"])
        if hwnd:
            command.extend(["-i", f"hwnd={int(hwnd)}"])
        else:
            if crop:
                x, y, width, height = crop
                command.extend(
                    [
                        "-offset_x",
                        str(x),
                        "-offset_y",
                        str(y),
                        "-video_size",
                        f"{width}x{height}",
                    ]
                )
            command.extend(["-i", "desktop"])
    elif system == "Darwin":
        device = screen_device or "1"
        command.extend(
            [
                "-f",
                "avfoundation",
                "-framerate",
                str(fps),
                "-capture_cursor",
                "1",
                "-i",
                f"{device}:none",
            ]
        )
    else:
        raise RecorderError(f"不支持的采集系统：{system}")
    command.extend(_output_args(scale, encoder_args, output))
    return command


def build_image_pipe_command(
    *,
    ffmpeg: Path,
    output: Path,
    fps: int,
    scale: str,
    encoder_args: list[str],
) -> list[str]:
    """Build an FFmpeg command that encodes a JPEG/MJPEG byte stream."""
    command = [
        str(ffmpeg),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-stats",
        "-f",
        "image2pipe",
        "-framerate",
        str(fps),
        "-vcodec",
        "mjpeg",
        "-i",
        "-",
    ]
    command.extend(_output_args(scale, encoder_args, output))
    return command


def build_rawvideo_command(
    *,
    ffmpeg: Path,
    output: Path,
    fps: int,
    size: tuple[int, int],
    scale: str,
    encoder_args: list[str],
) -> list[str]:
    """Build an FFmpeg command that encodes a raw BGRA frame stream (WGC)."""
    width, height = size
    command = [
        str(ffmpeg),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-stats",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgra",
        "-video_size",
        f"{width}x{height}",
        "-framerate",
        str(fps),
        "-i",
        "-",
    ]
    command.extend(_output_args(scale, encoder_args, output))
    return command


def popen_ffmpeg(command: list[str], *, stdin: int | None) -> subprocess.Popen:
    """Start FFmpeg without flashing a console window on Windows."""
    ffmpeg_dir = Path(command[0]).parent
    kwargs: dict[str, Any] = {
        "stdin": stdin,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "cwd": str(ffmpeg_dir if ffmpeg_dir.is_dir() else Path.cwd()),
    }
    if os.name == "nt":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.Popen(command, **kwargs)


def _output_args(scale: str, encoder_args: list[str], output: Path) -> list[str]:
    args = ["-an"]
    scale = (scale or "").strip()
    if scale:
        args.extend(["-vf", f"scale={scale}"])
    args.extend([*encoder_args, "-movflags", "+faststart", str(output)])
    return args


def _run_ffmpeg_quietly(
    args: list[str], *, timeout: float, cwd: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run an ffmpeg probe without flashing a console window on Windows."""
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
    }
    if cwd:
        kwargs["cwd"] = cwd
    if os.name == "nt":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.run(args, **kwargs)


def _ffmpeg_executes(ffmpeg: Path) -> bool:
    """Return True if the binary starts successfully (``-version`` exits 0)."""
    try:
        result = _run_ffmpeg_quietly([str(ffmpeg), "-version"], timeout=8)
    except Exception:
        return False
    return result.returncode == 0


def _screencast_max_width() -> int | None:
    """Derive the screencast maxWidth from CAPTURE_VIDEO_SCALE (e.g. 1280:-2)."""
    scale = os.getenv("CAPTURE_VIDEO_SCALE", "1280:-2").strip()
    match = re.match(r"^(\d+)(?::|$)", scale)
    if not match:
        return None
    width = int(match.group(1))
    return width if width > 0 else None


def _probe_h264_encoder(ffmpeg: Path) -> list[str]:
    try:
        result = _run_ffmpeg_quietly(
            [str(ffmpeg), "-hide_banner", "-encoders"],
            timeout=10,
            cwd=str(ffmpeg.parent),
        )
    except Exception as exc:
        raise RecorderError(f"无法探测 ffmpeg 编码器：{exc}") from exc
    text = f"{result.stdout}\n{result.stderr}"
    for name in ("libx264", "h264_mf", "libopenh264"):
        if re.search(rf"\b{name}\b", text):
            return [name]
    raise RecorderError("ffmpeg 未编译 H264 编码器。")


def _macos_screen_device(ffmpeg: Path) -> str:
    try:
        result = _run_ffmpeg_quietly(
            [str(ffmpeg), "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            timeout=10,
        )
    except Exception:
        return "1"
    text = f"{result.stderr}\n{result.stdout}"
    matches = re.findall(
        r"\[(\d+)\]\s+(Capture screen.*|.*Screen Recording.*|.*screen.*)",
        text,
        flags=re.IGNORECASE,
    )
    if matches:
        return matches[0][0]
    return "1"


def _crf_to_bitrate(crf: int) -> str:
    # CRF 28 ≈ 600kbps for 720p UI; clamp to a small but watchable range.
    kbps = max(350, min(1200, int(2400 - crf * 60)))
    return f"{kbps}k"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_tri_flag(name: str) -> bool | None:
    """三态环境变量：未设置返回 None（交给系统默认），设置了按真假解析。"""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _safe_filename(value: str, fallback: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(value)).strip(" ._")
    return sanitized or fallback


def _decode(payload: bytes | str | None) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    return payload.decode("utf-8", errors="replace")
