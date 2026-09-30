"""测试脚本：上传本地视频文件到 Copyparty（192.168.40.166:3923）。

用法：
    python test.py <文件路径>

不传参数则默认上传当前目录下的 20260727.mp4。
"""
import sys
from pathlib import Path

import requests

COPIYPARTY_URL = "http://192.168.40.166:3923"
PASSWORD = "RpaUpload2026"
VOLUME = "inc"


def upload(file_path: str) -> None:
    path = Path(file_path)
    if not path.exists():
        print(f"[错误] 文件不存在: {path.resolve()}")
        sys.exit(1)

    size_kb = path.stat().st_size / 1024
    url = f"{COPIYPARTY_URL}/{VOLUME}/{path.name}"
    print(f"上传: {path.name} ({size_kb:.1f} KB)")
    print(f"目标: {url}")

    with path.open("rb") as f:
        resp = requests.put(url, data=f, params={"pw": PASSWORD}, timeout=1800)

    # Copyparty 成功返回 200 或 201（Created）
    if resp.status_code in (200, 201):
        print(f"[成功] HTTP {resp.status_code}")
        print(f"访问: {url}")
    else:
        print(f"[失败] HTTP {resp.status_code}")
        print(f"响应: {resp.text[:500]}")
        sys.exit(1)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "20260727.mp4"
    upload(target)
