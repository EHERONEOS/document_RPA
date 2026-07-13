from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.logging.logger import log



class Recorder:
    """录屏控制器。"""

    def __init__(
        self,
        page: Any | None = None,
        *,
        record_dir: str | Path = "runtime/records",
    ) -> None:
        self.page = page
        self.record_dir = Path(record_dir)
        self._record_started = False
        self._record_base_name = ""
        self._record_save_path: Path | None = None

    def bind_page(self, page: Any) -> "Recorder":
        """绑定页面对象，便于后续复用同一个实例。"""
        self.page = page
        return self

    def start(self) -> str:
        """开始录屏。"""
        self._ensure_page()
        base_name = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = self.record_dir / base_name
        save_path.mkdir(parents=True, exist_ok=True)
        self.page.screencast.set_save_path(str(save_path))
        self.page.screencast.set_mode.video_mode()
        self.page.screencast.start()
        self._record_started = True
        self._record_base_name = base_name
        self._record_save_path = save_path
        return str(save_path)

    def stop(self, queue_name="",jobNo="") -> str:
        """停止录屏。"""
        self._ensure_page()
        if not self._record_started:
            return ""
        # frame_dir = Path(self.page.screencast.stop())
        time_text = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_name = self.build_record_name(queue_name, jobNo, time_text)
        self.page.screencast.stop(video_name=video_name)
        # video_path = self.record_dir / f"{video_name}.mp4"
        # result = self._frames_to_video(frame_dir, video_path)
        # self._record_started = False
        # self._record_base_name = ""
        # self._record_save_path = None
        # return result

    def build_record_name(self, order_no: str, order_type: str, time_text: str | None = None) -> str:
        """生成录屏目录/文件基础名。"""
        order_no = self._safe_filename(order_no)
        order_type = self._safe_filename(order_type)
        time_text = time_text or datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{order_no}_{order_type}_{time_text}"

    def _frames_to_video(self, frame_dir: Path, video_path: Path, fps: int = 5) -> str:
        """将图片帧目录合成为 mp4 文件。"""
        try:
            import cv2
        except ModuleNotFoundError as exc:
            raise RuntimeError("未安装 opencv-python，无法合成 mp4") from exc

        frames = sorted(
            frame_dir.glob("*.jpg"),
            key=lambda path: float(path.stem) if path.stem.replace(".", "", 1).isdigit() else path.stem,
        )
        if not frames:
            raise RuntimeError(f"录屏帧为空，无法生成视频：{frame_dir}")

        first_frame = cv2.imread(str(frames[0]))
        if first_frame is None:
            raise RuntimeError(f"首帧读取失败，无法生成视频：{frames[0]}")

        height, width = first_frame.shape[:2]
        video_path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(
            str(video_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )
        if not writer.isOpened():
            raise RuntimeError(f"无法创建视频文件：{video_path}")

        try:
            for frame_path in frames:
                frame = cv2.imread(str(frame_path))
                if frame is None:
                    continue
                if frame.shape[:2] != (height, width):
                    frame = cv2.resize(frame, (width, height))
                writer.write(frame)
        finally:
            writer.release()

        log(f"录屏文件生成 path={video_path}")
        return str(video_path)

    def _safe_filename(self, value: str) -> str:
        invalid_chars = '<>:"/\\|?*'
        sanitized = "".join("_" if char in invalid_chars else char for char in str(value))
        sanitized = sanitized.strip().strip(".")
        return sanitized or "unknown"

    def _ensure_page(self) -> None:
        if self.page is None:
            raise RuntimeError("未绑定页面对象，无法执行录屏")
