from app.spider.ZIM.tasks.qtct_zim_si import qtct_zim_si
from app.spider.ZIM.tasks.qtct_zim_vgm import qtct_zim_vgm
from app.core.task.context import TaskContext
from app.core.task.errors import RouteNotFoundError
from app.core.task.router import CarrierRoute


ROUTES = {
    "QTCT_ZIM_SI": CarrierRoute("QTCT", "SI", qtct_zim_si),
    "QTCT_ZIM_VGM": CarrierRoute("QTCT", "VGM", qtct_zim_vgm),
}


def dispatch(context: TaskContext):
    """根据完整队列名分发到 ZIM 客户入口方法。"""
    route = ROUTES.get(context.queue_name.upper())
    if route is None:
        raise RouteNotFoundError(f"ZIM 未配置队列入口：{context.queue_name}")
    return route.handler(context)
