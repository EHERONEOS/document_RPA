"""为已抽离的 MSCGW 声明式动作库保留兼容导入。"""

from app.spider.MSCGW.actions import build_mscgw_si_registry

__all__ = ["build_mscgw_si_registry"]
