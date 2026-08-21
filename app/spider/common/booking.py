from typing import Any, Protocol

from app.core.page.dom import DomHelper
from app.core.page.http import HttpHelper
from app.core.task.errors import BusinessError
from app.spider.ZIM import selectors


class BookingTask(Protocol):
    """订舱公共逻辑所需的任务接口。"""

    dom: DomHelper
    http: HttpHelper


def query_booking(self: BookingTask, blNo: str) -> dict[str, Any]:
    """查询订舱单据。

    依赖调用方（CarrierBase 实例）提供的成员：
    - self.http.wait_api_finished
    - self.dom.click / self.dom.in_frame
    """
    # 点击订舱导航菜单并等待订舱列表接口完成
    self.http.wait_api_finished(
        selectors.BOOKING_GET_LIST_API,
        trigger=lambda: self.dom.click(*selectors.DC_MENU),
    )
    iframe_dom: DomHelper = self.dom.in_frame(*selectors.DC_LIST_FRAME)
    iframe_dom.input_text(
        selectors.SEARCH_BOOK_NO[0],
        blNo,
        name=selectors.SEARCH_BOOK_NO[1],
    )
    # 点击搜索按钮并等待订舱列表接口完成
    res = self.http.wait_api_finished(
        selectors.BOOKING_GET_LIST_API,
        trigger=lambda: iframe_dom.click(*selectors.SEARCH_BTN),
    )
    response = res.get("response", {})
    if not response or response.get("total") != 1:
        raise BusinessError("查询订舱单据失败")
    bo_row = response.get("datas", {})[0]
    if not bo_row or bo_row.get("gdNo") != blNo:
        raise BusinessError("订舱列表接口返回数据异常")
    return bo_row
