from app.spider.ZIM.tasks.zim_si import ZimSiTask
from app.spider.ZIM.tasks.zim_vgm import ZimVGMTask





class QtctZimSiTask(ZimSiTask):
    """QTCT 客户的 ZIM SI 任务。"""   
    incognito = False

class FlZimVGMTask(ZimVGMTask):
    """ZIM 通用 VGM 业务流程。"""

    incognito = False



def qtct_zim_si(context):
    """QTCT_ZIM_SI 队列入口。"""
    return QtctZimSiTask(context).run()


def qtct_zim_vgm(context):
    """QTCT_ZIM_VGM 队列入口。"""
    return FlZimVGMTask(context).run()



