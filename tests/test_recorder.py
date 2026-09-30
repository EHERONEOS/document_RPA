"""跨平台 FFmpeg 录屏：命令构造、后端降级和任务开关。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.page import recorder as recorder_mod
from app.core.page.recorder import (
    Recorder,
    RecorderError,
    build_image_pipe_command,
    build_os_capture_command,
    resolve_ffmpeg_path,
)
from app.core.task.base_task import BaseRpaTask


class FakeProcess:
    def __init__(self, *, exit_code=None, stdin=None):
        self._exit_code = exit_code
        self.stdin = stdin if stdin is not None else FakeStdin()
        self.returncode = exit_code
        self.killed = False

    def poll(self):
        return self._exit_code

    def communicate(self, timeout=None):
        if self._exit_code is None:
            self._exit_code = 0
            self.returncode = 0
        return b"", b""

    def kill(self):
        self.killed = True
        self._exit_code = 1
        self.returncode = 1


class FakeStdin:
    def __init__(self):
        self.writes = []
        self.closed = False

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def flush(self):
        return None

    def close(self):
        self.closed = True


def test_resolve_ffmpeg_path_prefers_env(tmp_path, monkeypatch):
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("#!/bin/sh\n")
    ffmpeg.chmod(0o755)
    monkeypatch.setenv("FFMPEG_PATH", str(ffmpeg))
    monkeypatch.setattr(recorder_mod.shutil, "which", lambda _name: None)
    assert resolve_ffmpeg_path() == ffmpeg


def test_windows_command_uses_gdigrab_and_small_profile(tmp_path):
    ffmpeg = tmp_path / "ffmpeg"
    output = tmp_path / "out.mp4"
    command = build_os_capture_command(
        ffmpeg=ffmpeg,
        output=output,
        system="Windows",
        fps=5,
        scale="1280:-2",
        encoder_args=["-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p"],
        crop=(10, 20, 1280, 720),
    )
    assert command[:6] == [str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error", "-stats"]
    assert command[command.index("-f") + 1] == "gdigrab"
    assert "desktop" in command
    assert command[command.index("-video_size") + 1] == "1280x720"
    assert "-crf" in command and "28" in command
    assert command[command.index("-vf") + 1] == "scale=1280:-2"
    assert command[-1] == str(output)


def test_windows_command_prefers_hwnd(tmp_path):
    command = build_os_capture_command(
        ffmpeg=tmp_path / "ffmpeg",
        output=tmp_path / "out.mp4",
        system="Windows",
        fps=5,
        scale="1280:-2",
        encoder_args=["-c:v", "libx264", "-crf", "28"],
        hwnd=0x1234,
        crop=(10, 20, 1280, 720),
    )
    assert "hwnd=4660" in command
    assert "desktop" not in command


def test_macos_command_uses_avfoundation(tmp_path):
    command = build_os_capture_command(
        ffmpeg=tmp_path / "ffmpeg",
        output=tmp_path / "out.mp4",
        system="Darwin",
        fps=5,
        scale="1280:-2",
        encoder_args=["-c:v", "libx264", "-crf", "28"],
        screen_device="1",
    )
    assert "avfoundation" in command
    assert "1:none" in command


def test_image_pipe_command_reads_stdin(tmp_path):
    command = build_image_pipe_command(
        ffmpeg=tmp_path / "ffmpeg",
        output=tmp_path / "out.mp4",
        fps=5,
        scale="1280:-2",
        encoder_args=["-c:v", "libx264", "-crf", "28"],
    )
    assert "image2pipe" in command
    assert "-" in command


def test_recorder_start_stop_ffmpeg(tmp_path, monkeypatch):
    fake = FakeProcess()
    monkeypatch.setattr(recorder_mod, "resolve_ffmpeg_path", lambda: tmp_path / "ffmpeg")
    monkeypatch.setattr(recorder_mod, "h264_encoder_args", lambda *_args, **_kwargs: ["-c:v", "libx264"])
    monkeypatch.setattr(recorder_mod, "_macos_screen_device", lambda _ffmpeg: "1")
    monkeypatch.setattr(recorder_mod, "popen_ffmpeg", lambda command, stdin: fake)
    monkeypatch.setattr(recorder_mod.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(recorder_mod, "ensure_browser_window_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr(recorder_mod, "browser_pid_from_page", lambda _page: 123)
    monkeypatch.setattr(Recorder, "_ensure_process_running", lambda self, label, timeout_seconds=1.0: None)

    rec = Recorder(page=object(), record_dir=tmp_path, queue_name="QTCT_ZIM_SI", job_no="JOB1")
    rec.start()
    assert rec.backend == "ffmpeg"
    assert rec.is_running()
    rec.file_path.write_bytes(b"mp4")
    path = rec.stop()
    assert path == rec.file_path
    assert fake.stdin.writes == [b"q\n"]
    assert fake.stdin.closed
    assert rec.is_running() is False


def test_recorder_falls_back_to_cdp(tmp_path, monkeypatch):
    fake = FakeProcess()
    calls = []

    def fail_os():
        calls.append("ffmpeg")
        raise RecorderError("gdigrab unavailable")

    def start_cdp():
        calls.append("cdp")
        rec._process = fake

    rec = Recorder(page=object(), record_dir=tmp_path, queue_name="task", job_no="1")
    monkeypatch.setenv("CAPTURE_BACKEND", "auto")
    monkeypatch.setattr(rec, "_start_ffmpeg_os", fail_os)
    monkeypatch.setattr(rec, "_start_cdp", start_cdp)

    rec.start()
    assert calls == ["ffmpeg", "cdp"]
    assert rec.backend == "cdp"


def test_should_record_allows_macos(monkeypatch):
    task = object.__new__(BaseRpaTask)
    task.enable_record = True
    task.context = SimpleNamespace(enable_result_publish=True)
    monkeypatch.setattr("app.core.task.base_task.platform.system", lambda: "Darwin")
    assert task.should_record() is True
    monkeypatch.setattr("app.core.task.base_task.platform.system", lambda: "Linux")
    assert task.should_record() is False


def test_start_requires_page(tmp_path):
    rec = Recorder(page=None, record_dir=tmp_path)
    with pytest.raises(RecorderError, match="page 不能为空"):
        rec.start()
