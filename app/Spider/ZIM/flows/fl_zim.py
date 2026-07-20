from app.spider.ZIM.tasks.zim_si import ZimSiTask
from app.spider.ZIM.tasks.zim_vgm import ZimVGMTask





class FlZimSiTask(ZimSiTask):
    """FL 客户的 ZIM SI 任务。"""   
    incognito = False

class FlZimVGMTask(ZimVGMTask):
    """ZIM 通用 VGM 业务流程。"""

    incognito = False



def fl_zim_si(context):
    """FL_ZIM_SI 队列入口。"""
    return FlZimSiTask(context).run()


def fl_zim_vgm(context):
    """FL_ZIM_VGM 队列入口。"""
    return FlZimVGMTask(context).run()



