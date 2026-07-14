from app.core.task.errors import BusinessError
from app.Spider.ZIM.ZIM_SI import ZimSiTask
from app.Spider.ZIM.ZIM_VGM import ZimVGMTask



def _raise_unimplemented(context, business_code):
    """终止尚未实现的 ZIM 业务，避免任务被标记为成功。"""
    raise BusinessError(f"ZIM {business_code} 业务暂未实现：{context.queue_name}")


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



