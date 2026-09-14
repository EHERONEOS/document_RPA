from importlib import import_module
import os

from app.core.flow import FlowCache, FlowRuntime
from app.core.task.errors import RouteNotFoundError
from app.core.task.router import resolve_queue_route


def dispatch_context(context):
    """根据完整队列名确定船司，并加载其路由文件完成业务分发。"""
    if context.flow_id:
        if not context.flow_version:
            raise RouteNotFoundError("声明式流程任务必须提供 flowVersion")
        definition = FlowCache(os.getenv("FLOW_CACHE_DIR", "runtime/flow_cache")).get(
            context.flow_id, context.flow_version
        )
        adapter_name = definition.get("metadata", {}).get("adapter")
        if not adapter_name:
            return FlowRuntime().run(definition, context)
        route = resolve_queue_route(context.queue_name)
        context.customer_code = route.customer_code
        context.carrier_code = route.carrier_code
        context.business_code = route.business_code
        router = import_module(route.router_module)
        dispatch_flow = getattr(router, "dispatch_flow", None)
        if dispatch_flow is None:
            raise RouteNotFoundError(f"船司路由不支持声明式适配器：{adapter_name}")
        return dispatch_flow(context, definition)

    # 未绑定流程的任务继续通过原有静态路由执行。
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
