"""MSCGW 船司队列路由。"""

from app.core.task.errors import RouteNotFoundError
from app.core.task.router import CarrierRoute
from app.spider.MSCGW.tasks.fht_mscgw_si import fht_mscgw_si
from app.spider.MSCGW.tasks.fht_mscgw_si import fht_mscgw_si_flow


ROUTES = {
    "FHT_MSCGW_SI": CarrierRoute("FHT", "SI", fht_mscgw_si),
}


def dispatch(context):
    """根据完整队列名分发到对应的 MSCGW 客户任务。"""
    route = ROUTES.get(context.queue_name.upper())
    if route is None:
        raise RouteNotFoundError(f"MSCGW 未配置队列入口：{context.queue_name}")
    return route.handler(context)


def dispatch_flow(context, definition):
    """将已校验的 MSCGW 流程分发到显式业务适配器。"""
    if context.queue_name.upper() != "FHT_MSCGW_SI":
        raise RouteNotFoundError(f"MSCGW 未配置声明式入口：{context.queue_name}")
    if definition.get("metadata", {}).get("adapter") != "MSCGW.SI":
        raise RouteNotFoundError("FHT_MSCGW_SI 仅支持 MSCGW.SI 声明式适配器")
    return fht_mscgw_si_flow(context, definition)
