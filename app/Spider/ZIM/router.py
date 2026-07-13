from app.Spider.ZIM.FL_ZIM import fl_zim_si, fl_zim_vgm
from app.core.task.context import TaskContext
from app.core.task.errors import RouteNotFoundError


ROUTES = {
    "FL_ZIM_SI": fl_zim_si,
    "FL_ZIM_VGM": fl_zim_vgm,
}


def dispatch(context: TaskContext):
    """根据完整队列名分发到 ZIM 客户入口方法。"""
    route = ROUTES.get(context.queue_name.upper())
    if route is None:
        raise RouteNotFoundError(f"ZIM 未配置队列入口：{context.queue_name}")
    return route(context)
