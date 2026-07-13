import unittest
from types import SimpleNamespace

from app.core.task.dispatcher import dispatch_context
from app.core.task.errors import BusinessError


class ZimRoutingTest(unittest.TestCase):
    def test_zim_queues_dispatch_to_explicit_placeholder(self):
        for queue_name in ("FL_ZIM_SI", "FL_ZIM_VGM"):
            context = SimpleNamespace(queue_name=queue_name, carrier_code="ZIM")

            with self.assertRaisesRegex(BusinessError, f"ZIM .*{queue_name}"):
                dispatch_context(context)
