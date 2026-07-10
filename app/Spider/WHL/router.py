from app.core.task.context import TaskContext
from app.core.task.errors import RouteNotFoundError
from app.Spider.WHL.FL_WHL import fl_whl_si, fl_whl_vgm


ROUTES = {
    "FL_WHL_SI": fl_whl_si,
    "FL_WHL_VGM": fl_whl_vgm,
}


def dispatch(context: TaskContext):
    """根据完整队列名分发到客户入口方法。"""
    route = ROUTES.get(context.queue_name.upper())
    if route is None:
        raise RouteNotFoundError(f"WHL 未配置队列入口：{context.queue_name}")
    return route(context)
