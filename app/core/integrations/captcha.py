class CaptchaSolver:
    """验证码识别入口。"""

    def solve(self, image_path: str) -> str:
        raise RuntimeError(f"当前未配置验证码识别服务：{image_path}")
