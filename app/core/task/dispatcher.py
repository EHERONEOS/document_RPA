from importlib import import_module

from app.core.task.context import TaskContext
from app.core.task.errors import RouteNotFoundError


def dispatch_context(context: TaskContext):
    """根据船司代码加载 router 并分发任务。"""
    module_name = f"app.Spider.{context.carrier_code}.router"
    try:
        router = import_module(module_name)
    except ModuleNotFoundError as exc:
        raise RouteNotFoundError(f"未找到船司路由：{context.carrier_code}") from exc

    dispatch = getattr(router, "dispatch", None)
    if dispatch is None:
        raise RouteNotFoundError(f"船司路由缺少 dispatch 方法：{context.carrier_code}")
    return dispatch(context)
