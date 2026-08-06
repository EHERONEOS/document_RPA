"""统一发现船司路由的入口。"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pkgutil import iter_modules
from typing import Callable

from app.core.task.errors import RouteNotFoundError


@dataclass(frozen=True)
class CarrierRoute:
    """由单个船司维护的完整队列名路由项。"""

    customer_code: str
    business_code: str
    handler: Callable


@dataclass(frozen=True)
class QueueRoute:
    """统一入口解析出的队列路由信息。"""

    customer_code: str
    carrier_code: str
    business_code: str
    router_module: str


def normalize_queue_name(queue_name: str) -> str:
    """统一队列名称的大小写和首尾空白，但不改变名称结构。"""
    return str(queue_name or "").strip().upper()


def resolve_queue_route(queue_name: str) -> QueueRoute:
    """从各船司路由文件中按完整队列名查找归属。"""
    normalized_name = normalize_queue_name(queue_name)
    if not normalized_name:
        raise RouteNotFoundError("队列名不能为空")

    import app.spider

    matches: list[QueueRoute] = []
    for carrier_package in iter_modules(app.spider.__path__):
        if not carrier_package.ispkg:
            continue
        carrier_code = carrier_package.name.upper()
        module_name = f"app.spider.{carrier_package.name}.router"
        try:
            carrier_router = import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise

        route = getattr(carrier_router, "ROUTES", {}).get(normalized_name)
        if route is None:
            continue
        if not isinstance(route, CarrierRoute):
            raise RouteNotFoundError(
                f"{module_name}.ROUTES[{normalized_name!r}] 必须是 CarrierRoute"
            )
        matches.append(
            QueueRoute(
                customer_code=route.customer_code,
                carrier_code=carrier_code,
                business_code=route.business_code,
                router_module=module_name,
            )
        )

    if not matches:
        raise RouteNotFoundError(f"未配置队列路由：{normalized_name}")
    if len(matches) > 1:
        carriers = ", ".join(route.carrier_code for route in matches)
        raise RouteNotFoundError(f"队列 {normalized_name} 在多个船司重复配置：{carriers}")
    return matches[0]
