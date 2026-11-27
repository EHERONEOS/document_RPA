"""MSCGW 船司队列路由。"""

from app.core.task.errors import RouteNotFoundError
from app.core.task.router import CarrierRoute
from app.spider.MSCGW.tasks.mscgw_si import mscgw_si


ROUTES = {
    "FHT_MSCGW_SI": CarrierRoute("FHT", "SI", mscgw_si),
    "DAN_MSCGW_SI": CarrierRoute("DAN", "SI", mscgw_si),
}


def dispatch(context):
    """根据完整队列名分发到对应的 MSCGW 业务任务。"""
    route = ROUTES.get(context.queue_name.upper())
    if route is None:
        raise RouteNotFoundError(f"MSCGW 未配置队列入口：{context.queue_name}")
    return route.handler(context)
