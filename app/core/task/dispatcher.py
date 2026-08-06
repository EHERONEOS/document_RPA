from importlib import import_module

from app.core.task.errors import RouteNotFoundError
from app.core.task.router import resolve_queue_route


def dispatch_context(context):
    """根据完整队列名确定船司，并加载其路由文件完成业务分发。"""
    route = resolve_queue_route(context.queue_name)
    context.customer_code = route.customer_code
    context.carrier_code = route.carrier_code
    context.business_code = route.business_code
    try:
        router = import_module(route.router_module)
    except ModuleNotFoundError as exc:
        raise RouteNotFoundError(f"未找到船司路由：{route.carrier_code}") from exc

    dispatch = getattr(router, "dispatch", None)
    if dispatch is None:
        raise RouteNotFoundError(f"船司路由缺少 dispatch 方法：{route.carrier_code}")
    return dispatch(context)
