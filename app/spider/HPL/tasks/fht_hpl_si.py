"""FHT 客户的 HPL Shipping Instruction 任务。"""

from app.spider.HPL.common.hpl_si_base import HplSiBaseTask


class FhtHplSiTask(HplSiBaseTask):
    """执行 FHT_HPL_SI 队列对应的 HPL 截单流程。"""

    supported_templates = frozenset({"COMMON"})
    confirm_submission = False


def fht_hpl_si(context):
    """提供给 FHT_HPL_SI 路由调用的任务入口。"""
    return FhtHplSiTask(context).run()
