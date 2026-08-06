import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.task.dispatcher import dispatch_context
from app.core.task.errors import RouteNotFoundError
from app.core.task.router import CarrierRoute
from app.queue.message import build_task_context
from app.spider.ZIM.router import ROUTES


class ZimRoutingTest(unittest.TestCase):
    @patch("app.core.task.dispatcher.import_module")
    def test_dispatcher_uses_full_queue_name_to_load_carrier_router(self, import_module):
        queue_name = "DOCUMENT_IMPORT_2026_08"
        context = SimpleNamespace(queue_name=queue_name, carrier_code="WRONG")
        carrier_router = Mock()
        import_module.return_value = carrier_router

        with patch.dict(
            ROUTES,
            {queue_name: CarrierRoute("QTCT", "SI", Mock())},
        ):
            dispatch_context(context)

        import_module.assert_called_once_with("app.spider.ZIM.router")
        carrier_router.dispatch.assert_called_once_with(context)
        self.assertEqual("ZIM", context.carrier_code)

    def test_message_context_uses_registered_metadata(self):
        queue_name = "DOCUMENT_IMPORT_2026_08"
        task = {
            "rpaTaskTopic": queue_name,
            "rpaMessageId": "message-1",
            "websiteInfo": {},
            "content": {},
        }

        with patch.dict(
            ROUTES,
            {queue_name: CarrierRoute("QTCT", "SI", Mock())},
        ):
            context = build_task_context(task)

        self.assertEqual("QTCT", context.customer_code)
        self.assertEqual("ZIM", context.carrier_code)
        self.assertEqual("SI", context.business_code)

    def test_unregistered_queue_is_not_routed_by_name_segments(self):
        context = SimpleNamespace(queue_name="FL_ZIM_SI", carrier_code="ZIM")

        with self.assertRaisesRegex(RouteNotFoundError, "未配置队列路由"):
            dispatch_context(context)
