"""SNLWY 船司队列路由。"""

from app.core.task.errors import RouteNotFoundError
from app.core.task.router import CarrierRoute
from app.spider.SNLWY.tasks.snlwy_si import snlwy_si


ROUTES = {
    "FZ_SNLWY_SI": CarrierRoute("FZ", "SI", snlwy_si),
    "WNQ_SNLWY_SI": CarrierRoute("WNQ", "SI", snlwy_si),
}


def dispatch(context):
    """根据完整队列名分发到对应的 SNLWY 业务任务。"""
    route = ROUTES.get(context.queue_name.upper())
    if route is None:
        raise RouteNotFoundError(f"SNLWY 未配置队列入口：{context.queue_name}")
    return route.handler(context)
