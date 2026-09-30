from __future__ import annotations

from base64 import b64decode
from datetime import datetime
from pathlib import Path
import os
import platform
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Callable

from app.core.browser.window import (
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

    默认不再走 CaptureSDK / WGC（依赖 D3D11 硬件采集，部分 Win10 和核显/集显机器会
    直接启动失败）。优先使用 FFmpeg：

    - Windows：gdigrab（GDI，Win10/Win11 家庭版和专业版都可用，不依赖独立显卡）
    - macOS：avfoundation
    - 兜底：浏览器 CDP screencast → FFmpeg 合成 H264

    输出为 CRF 控制的 H264 MP4，体积明显小于原来的 1080p/2500kbps 码率模式。
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
        self.record_dir = Path(record_dir) / date_dir / safe_queue_name
        self.record_dir.mkdir(parents=True, exist_ok=True)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        self.file_path = self.record_dir / f"{safe_queue_name}_{safe_job_no}_{timestamp}.mp4"
        self.backend: str | None = None
        self._process: subprocess.Popen | None = None
        self._cli_session: Any | None = None
        self._stdin_lock = threading.Lock()
        self._cdp_enabled = False

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
            "cli": [("cli", self._start_cli)],
            "wgc": [("cli", self._start_cli)],
        }
        if requested in mapping:
            return mapping[requested]
        return [("ffmpeg", self._start_ffmpeg_os), ("cdp", self._start_cdp)]

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

        command = build_image_pipe_command(
            ffmpeg=ffmpeg,
            output=self.file_path,
            fps=_env_int("CAPTURE_FPS", 5),
            scale=os.getenv("CAPTURE_VIDEO_SCALE", "1280:-2"),
            encoder_args=h264_encoder_args(ffmpeg, _env_int("CAPTURE_VIDEO_CRF", 28)),
        )
        self._process = popen_ffmpeg(command, stdin=subprocess.PIPE)
        self._ensure_process_running("FFmpeg image2pipe")
        self._start_screencast()
        self._write_cdp_screenshot()

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
        self._run_cdp("Page.startScreencast", format="jpeg", quality=45, everyNthFrame=2)
        self._cdp_enabled = True

    def _stop_screencast(self) -> None:
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
                self._write_jpeg(b64decode(data))
            except Exception:
                pass
        if session_id is not None:
            try:
                self._run_cdp("Page.screencastFrameAck", sessionId=session_id)
            except Exception:
                pass

    def _write_cdp_screenshot(self) -> None:
        try:
            result = self._run_cdp("Page.captureScreenshot", format="jpeg", quality=45)
            data = (result or {}).get("data")
            if data:
                self._write_jpeg(b64decode(data))
        except Exception as exc:
            log(f"CDP 首帧截图失败，等待 screencast 帧：{exc}")

    def _write_jpeg(self, payload: bytes) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            return
        with self._stdin_lock:
            process.stdin.write(payload)
            process.stdin.flush()

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
        try:
            if process.stdin is not None:
                if self.backend == "cdp":
                    process.stdin.close()
                else:
                    process.stdin.write(b"q\n")
                    process.stdin.flush()
                    process.stdin.close()
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
    """Locate a usable ffmpeg binary, preferring the bundled Windows runtime."""
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
    for candidate in candidates:
        resolved = str(candidate)
        if resolved in seen:
            continue
        seen.add(resolved)
        if candidate.is_file() and os.access(candidate, os.X_OK if os.name != "nt" else os.F_OK):
            return candidate
    raise RecorderError(
        "未找到 ffmpeg。请安装 ffmpeg，或设置 FFMPEG_PATH，"
        "Windows 也可使用 capturesdk/third_party/ffmpeg/bin/ffmpeg.exe。"
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


def _probe_h264_encoder(ffmpeg: Path) -> list[str]:
    try:
        result = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
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
        result = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
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


def _safe_filename(value: str, fallback: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(value)).strip(" ._")
    return sanitized or fallback


def _decode(payload: bytes | str | None) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    return payload.decode("utf-8", errors="replace")
