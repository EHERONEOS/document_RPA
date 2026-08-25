"""EMC 船司队列路由。"""

from app.core.task.errors import RouteNotFoundError
from app.core.task.router import CarrierRoute
from app.spider.EMC.tasks.asy_emc_si import asy_emc_si


ROUTES = {
    "ASY_EMC_SI": CarrierRoute("ASY", "SI", asy_emc_si),
}


def dispatch(context):
    """根据完整队列名分发到 EMC 客户任务。"""
    route = ROUTES.get(context.queue_name.upper())
    if route is None:
        raise RouteNotFoundError(f"EMC 未配置队列入口：{context.queue_name}")
    return route.handler(context)
