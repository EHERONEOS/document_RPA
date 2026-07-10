from app.Spider.WHL.WHL_SI import WhlSiTask
from app.Spider.WHL.WHL_VGM import WhlVgmTask


class FlWhlSiTask(WhlSiTask):
    """FL 客户的 WHL SI 任务。"""

    incognito = False

    def fill_shipper(self) -> None:
        """FL 客户发货人填写个性化入口。"""
        super().fill_shipper()


def fl_whl_si(context):
    """FL_WHL_SI 队列入口。"""
    return FlWhlSiTask(context).run()


def fl_whl_vgm(context):
    """FL_WHL_VGM 队列入口。"""
    return WhlVgmTask(context).run()
