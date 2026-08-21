"""HPL 船司队列路由。"""

from app.core.task.errors import RouteNotFoundError
from app.core.task.router import CarrierRoute
from app.spider.HPL.tasks.fht_hpl_si import fht_hpl_si
from app.spider.HPL.tasks.jh_hpl_si import jh_hpl_si


ROUTES = {
    "FHT_HPL_SI": CarrierRoute("FHT", "SI", fht_hpl_si),
    "JH_HPL_SI": CarrierRoute("JH", "SI", jh_hpl_si),
}


def dispatch(context):
    """根据完整队列名分发到对应的 HPL 客户任务。"""
    route = ROUTES.get(context.queue_name.upper())
    if route is None:
        raise RouteNotFoundError(f"HPL 未配置队列入口：{context.queue_name}")
    return route.handler(context)
