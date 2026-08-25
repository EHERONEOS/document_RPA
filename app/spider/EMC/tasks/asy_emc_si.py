"""ASY 客户的 EMC Shipping Instruction 任务。"""

from app.spider.EMC.common.emc_si_base import EmcSiBaseTask


class AsyEmcSiTask(EmcSiBaseTask):
    """执行 ASY_EMC_SI，并继承 EMC 的通用 SI 页面流程。"""


def asy_emc_si(context):
    """提供给 ASY_EMC_SI 路由调用的任务入口。"""
    return AsyEmcSiTask(context).run()
