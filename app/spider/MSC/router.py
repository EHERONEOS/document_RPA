"""MSC 船司队列路由。"""

from app.core.task.errors import RouteNotFoundError
from app.core.task.router import CarrierRoute
from app.spider.MSC.tasks.fht_msc_si import fht_msc_si


ROUTES = {
    "FHT_MSC_SI": CarrierRoute("FHT", "SI", fht_msc_si),
}


def dispatch(context):
    """根据完整队列名分发到对应的 MSC 客户任务。"""
    route = ROUTES.get(context.queue_name.upper())
    if route is None:
        raise RouteNotFoundError(f"MSC 未配置队列入口：{context.queue_name}")
    return route.handler(context)
